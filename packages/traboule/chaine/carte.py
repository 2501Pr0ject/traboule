"""Carte de la réponse (Folium, Leaflet) : zones visées, contour du lieu, carroyage des effectifs.

- **Zones** : polygones du zonage des zones citées, simplifiés (SIMPLIFY_M m), reprojetés de
  EPSG:2154 vers EPSG:4326 avec `always_xy` ; infobulle : code, libellé, chapitre du règlement.
- **Comptage** : aucun établissement individuel. Carroyage de CELL_M m calculé dans DuckDB
  sur la vue `v_etablissements_carreaux` (coin du carreau seulement, positions publiques
  seulement : statut P exclu) ; les carreaux de moins de MIN_CELL établissements ne sont pas
  affichés ; ventilation de confiance de zone dans la légende.
- **Lieu** cité (commune ou arrondissement) : son contour.
- Pas de carte si la réponse ne porte sur aucune zone (ni zone citée, ni comptage par zone).
- Hors ligne : la carte n'est créée que si Leaflet s'est chargé ; sinon un message court la
  remplace, sans erreur. Seuls Leaflet et le fond OpenStreetMap (attribution affichée) sont
  chargés depuis le réseau.
"""

import html as html_lib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

import duckdb

from traboule.chaine.sql import CELL_M, activity_condition, fmt, place_condition, query
from traboule.contracts.reponse import Composante, Reponse
from traboule.routing.analyse import Analysis, Lexicon, Place

MIN_CELL = 5  # effectif minimal d'un carreau affiché
MAX_CELLS = 20_000
SIMPLIFY_M = 5.0
PRECISION = 1e-6  # degrés : environ 0,1 m
LEAFLET_JS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"
LEAFLET_CSS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"
OFFLINE = "Carte indisponible : fond de carte et bibliothèque cartographique non chargés."
# Bornes basses des classes d'effectif par carreau, et couleurs (séquentielles, bleu).
BINS = (5, 10, 20, 50, 100)
COLORS = ("#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c")
ZONE_COLOR = "#8a3b12"
PLACE_COLOR = "#1d1f22"


def wgs84(expr: str) -> str:
    """Expression SQL : géométrie EPSG:2154 → EPSG:4326, ordre x/y explicite (conventions §4)."""
    return (
        f"ST_ReducePrecision(ST_Transform({expr}, 'EPSG:2154', 'EPSG:4326', always_xy := true), "
        f"{PRECISION})"
    )


@dataclass(frozen=True)
class Layer:
    features: list[dict]

    def collection(self) -> dict:
        return {"type": "FeatureCollection", "features": self.features}


def feature(geometry: str, **properties) -> dict:
    return {"type": "Feature", "geometry": json.loads(geometry), "properties": properties}


def zone_layer(
    con: duckdb.DuckDBPyConnection, lexicon: Lexicon, cited: Iterable[str], labels: dict
) -> Layer:
    """Polygones des codes du zonage couverts par les zones citées, avec leur chapitre."""
    codes = sorted({c for z in cited for c in lexicon.zonage_codes(z)})
    if not codes:
        return Layer([])
    marks = ", ".join("?" * len(codes))
    chapters = {
        r["code_zone"]: (r["chapitre"], r["page_chapitre"])
        for r in query(
            con,
            f"select code_zone, chapitre, page_chapitre from v_zones_reglement "
            f"where code_zone in ({marks})",
            codes,
        )
    }
    rows = query(
        con,
        f"select code, ST_AsGeoJSON({wgs84('ST_SimplifyPreserveTopology(geom, ?)')}) as g "
        f"from v_zonage where code in ({marks})",
        [SIMPLIFY_M, *codes],
        max_rows=MAX_CELLS,
    )
    features = []
    for r in rows:
        chapter, page = chapters.get(r["code"], (None, None))
        mother = lexicon.chapters_of(r["code"])
        features.append(
            feature(
                r["g"],
                code=r["code"],
                libelle=labels.get(mother[0] if mother else r["code"], "—"),
                chapitre=f"{chapter}, p. {page}" if chapter and page else (chapter or "—"),
            )
        )
    return Layer(features)


def place_layer(con: duckdb.DuckDBPyConnection, places: Iterable[Place]) -> Layer:
    """Contour de chaque lieu cité ; Lyon (69123) : ses 9 arrondissements."""
    features = []
    for place in places:
        where = "code like '6938%'" if place.code == "69123" else "code = ?"
        params = [] if place.code == "69123" else [place.code]
        rows = query(
            con,
            f"select ST_AsGeoJSON({wgs84('ST_Union_Agg(ST_SimplifyPreserveTopology(geom, 5))')})"
            f" as g from v_unites where {where}",
            params,
        )
        if rows and rows[0]["g"]:
            features.append(feature(rows[0]["g"], lieu=place.libelle, code=place.code))
    return Layer(features)


def grid_layer(
    con: duckdb.DuckDBPyConnection, analysis: Analysis, codes: list[str]
) -> tuple[Layer, int, int]:
    """Carreaux d'au moins MIN_CELL établissements ; (couche, affichés, masqués)."""
    zone_sql = f"zone in ({', '.join('?' * len(codes))})" if codes else "zone is not null"
    pl_sql, pl_params = place_condition(analysis.places)
    act_sql, act_params = activity_condition(analysis.activity)
    where = f"etat = ? and {zone_sql} and {pl_sql} and {act_sql}"
    params = [analysis.etat, *codes, *pl_params, *act_params]
    cell = f"ST_MakeEnvelope(cx, cy, cx + {CELL_M}, cy + {CELL_M})"
    rows = query(
        con,
        f"select ST_AsGeoJSON({wgs84(cell)}) as g, count(*) as n from v_etablissements_carreaux "
        f"where {where} group by cx, cy having count(*) >= ?",
        [*params, MIN_CELL],
        max_rows=MAX_CELLS,
    )
    total = query(con, f"select count(*) as n from v_etablissements_carreaux where {where}",
                  params)[0]["n"]  # fmt: skip
    shown = sum(r["n"] for r in rows)
    return Layer([feature(r["g"], n=r["n"]) for r in rows]), shown, total - shown


def color(n: int) -> str:
    return next((c for low, c in reversed(list(zip(BINS, COLORS, strict=True))) if n >= low))


def bounds(layers: Iterable[Layer]) -> list[list[float]] | None:
    points = []

    def walk(coords):
        if coords and isinstance(coords[0], (int, float)):
            points.append(coords)
        else:
            for c in coords:
                walk(c)

    for layer in layers:
        for f in layer.features:
            walk(f["geometry"]["coordinates"])
    if not points:
        return None
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def legend(spatial: Composante | None, shown: int, hidden: int) -> str:
    """Légende repliable (en haut à droite) : classes du carroyage, confiance de zone, tracés."""
    parts = []
    if spatial is not None:
        swatches = "".join(
            f'<span class="classe"><i style="background:{c}"></i>{low}'
            f"{'+' if i == len(BINS) - 1 else ''}</span>"
            for i, (low, c) in enumerate(zip(BINS, COLORS, strict=True))
        )
        parts.append(
            f"<p><strong>Établissements par carreau de {CELL_M} m</strong></p>"
            f'<p class="classes">{swatches}</p>'
            f"<p>{shown} affichés ; carreaux de moins de {MIN_CELL} masqués "
            f"({hidden} établissements).</p>"
        )
        v = spatial.ventilation_confiance
        if v is not None:
            parts.append(
                f"<p><strong>Confiance de zone</strong> : {v.haute} haute, {v.moyenne} moyenne, "
                f"{v.faible} faible.</p>"
            )
    parts.append(
        f'<p><i class="trait" style="border-color:{ZONE_COLOR}"></i>Zone '
        f'<i class="trait pointille" style="border-color:{PLACE_COLOR}"></i>Lieu</p>'
    )
    return (
        "<style>.legende{position:absolute;top:10px;right:10px;z-index:1000;background:#fff;"
        "padding:6px 9px;border-radius:6px;font:11px/1.35 system-ui,sans-serif;max-width:210px;"
        "box-shadow:0 1px 4px rgba(0,0,0,.3)}.legende summary{cursor:pointer;font-weight:600}"
        ".legende p{margin:4px 0 0}.legende i{display:inline-block;width:12px;height:9px;"
        "margin-right:3px;vertical-align:middle}.legende .classe{margin-right:5px;"
        "white-space:nowrap}.legende .trait{height:0;width:14px;border-top:2px solid}"
        ".legende .pointille{border-top-style:dashed;margin-left:8px}"
        # Échelle métrique seulement.
        ".leaflet-control-scale-line+.leaflet-control-scale-line{display:none}"
        # Écran étroit : l'échelle passe au-dessus de l'attribution.
        "@media (max-width:480px){.leaflet-bottom.leaflet-left{bottom:20px}}</style>"
        f'<details class="legende" open><summary>Légende</summary>{"".join(parts)}</details>'
        # Écran étroit : légende repliée (au chargement et si la fenêtre rétrécit).
        "<script>(function () { const l = document.querySelector('.legende');"
        " const fit = () => { if (window.innerWidth < 480) l.removeAttribute('open'); };"
        " fit(); window.addEventListener('resize', fit); })();</script>"
    )


def guard(page: str) -> str:
    """Le script de la carte ne s'exécute que si Leaflet s'est chargé ; sinon, un message."""
    message = html_lib.escape(OFFLINE)
    fallback = (
        "document.body.innerHTML = '<p style=\"font:14px system-ui,sans-serif;"
        f"color:#5d636b;margin:12px 16px\">{message}</p>';"
        # Cadre réduit à la hauteur du message (srcdoc : même origine que la page).
        " if (window.frameElement) window.frameElement.style.height = '48px';"
    )

    def wrap(m: re.Match) -> str:
        return f"<script>\nif (window.L) {{{m.group(1)}}} else {{ {fallback} }}\n</script>"

    return re.sub(r"<script>((?:(?!</script>).)*?L\.map\((?:(?!</script>).)*)</script>",
                  wrap, page, count=1, flags=re.S)  # fmt: skip


def needs_map(reponse: Reponse, analysis: Analysis) -> bool:
    """Une carte seulement si la réponse porte sur au moins une zone."""
    if reponse.route == "ABSTAIN":
        return False
    spatial = any(c.comptage_spatial and not c.abstention for c in reponse.composantes)
    return bool(analysis.zones) or spatial


def build_map(
    con: duckdb.DuckDBPyConnection,
    lexicon: Lexicon,
    analysis: Analysis,
    reponse: Reponse,
    labels: dict[str, str],
) -> dict | None:
    """HTML autonome de la carte, et rappel du minorant ; None sans zone."""
    import folium

    if not needs_map(reponse, analysis):
        return None
    zones = zone_layer(con, lexicon, analysis.zones, labels)
    places = place_layer(con, analysis.places)
    spatial = next(
        (c for c in reponse.composantes if c.comptage_spatial and not c.abstention), None
    )
    codes = sorted({c for z in analysis.zones for c in lexicon.zonage_codes(z)})
    grid, shown, hidden = grid_layer(con, analysis, codes) if spatial else (Layer([]), 0, 0)
    box = bounds([zones, places, grid])
    if box is None:
        return None
    m = folium.Map(tiles="OpenStreetMap", control_scale=True, prefer_canvas=True)
    m.default_js = [("leaflet", LEAFLET_JS)]
    m.default_css = [("leaflet_css", LEAFLET_CSS)]
    if grid.features:
        folium.GeoJson(
            grid.collection(),
            name="Carroyage",
            style_function=lambda f: {
                "fillColor": color(f["properties"]["n"]),
                "color": "#fff",
                "weight": 0.5,
                "fillOpacity": 0.75,
            },  # fmt: skip
            tooltip=folium.GeoJsonTooltip(fields=["n"], aliases=["Établissements"]),
        ).add_to(m)
    if zones.features:
        folium.GeoJson(
            zones.collection(),
            name="Zones",
            style_function=lambda f: {"color": ZONE_COLOR, "weight": 2, "fillOpacity": 0.08},
            tooltip=folium.GeoJsonTooltip(
                fields=["code", "libelle", "chapitre"],
                aliases=["Code", "Libellé", "Chapitre du règlement"],
            ),
        ).add_to(m)
    if places.features:
        folium.GeoJson(
            places.collection(),
            name="Lieu",
            style_function=lambda f: {
                "color": PLACE_COLOR,
                "weight": 2,
                "dashArray": "6 4",
                "fillOpacity": 0,
            },  # fmt: skip
            tooltip=folium.GeoJsonTooltip(fields=["lieu"], aliases=["Lieu"]),
        ).add_to(m)
    m.fit_bounds(box)
    m.get_root().html.add_child(folium.Element(legend(spatial, shown, hidden)))
    minorant = None
    if spatial and spatial.minorant and spatial.ventilation_confiance:
        total = spatial.ventilation_confiance.total
        where = "dans la zone" if analysis.zones else "dans ces zones"
        located = (f"{fmt(total)} établissements sont géolocalisés {where}." if total != 1
                   else f"1 établissement est géolocalisé {where}.")  # fmt: skip
        ou = "dans la zone" if analysis.zones else "dans l'une de ces zones"
        minorant = f"{located} {spatial.minorant.phrase(ou)}"
    return {"html": guard(m.get_root().render()), "minorant": minorant}


def zone_labels(path) -> dict[str, str]:
    """Libellé de chaque zone du règlement (passages extraits), ex. UEp → « … »."""
    from traboule.contracts.passage import Passage

    labels: dict[str, str] = {}
    if not path.exists():
        return labels
    for line in path.open(encoding="utf-8"):
        p = Passage.model_validate_json(line)
        if p.zone and p.zone_libelle:
            labels.setdefault(p.zone, p.zone_libelle)
    return labels
