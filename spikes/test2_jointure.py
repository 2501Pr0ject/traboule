"""Test 2 du spike : jointure spatiale établissements ↔ zonage du PLU-H.

Script jetable. Entrées : data/interim/sirene_ml.parquet (Test 1) et le zonage SRC-002.
Source de coordonnées principale : fichier de géolocalisation ; coordonnées du stock en
sensibilité. Écrit data/interim/etablissements_zones.parquet et, dans spikes/output/test2/
(jamais versionné) : metrics.json, zones.csv, controles.csv, carte_controles.html.
Un résultat spatial est une analyse de localisation, jamais un constat réglementaire.
"""

import csv
import json
import platform
import re
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import duckdb
import psutil
import typer

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
OUTPUT_DIR = ROOT / "spikes" / "output" / "test2"
RAW_DATE = "2026-10-28"
SIRENE_ML = INTERIM / "sirene_ml.parquet"
OUT_PARQUET = INTERIM / "etablissements_zones.parquet"
ZONAGE = RAW / f"SRC-002/{RAW_DATE}/zonage/zonage.geojson"
COMMUNES = RAW / f"REF-COMMUNES-ML-2024/{RAW_DATE}/communes/communes.geojson"
STOCK = RAW / f"SRC-001a/{RAW_DATE}/stock_etablissement/stock-stocketablissement-parquet.parquet"
REGLEMENT = RAW / f"SRC-005/{RAW_DATE}/reglement_ecrit/200046977_reglement_20260326.pdf"

PILOT_ARRONDISSEMENT = "69387"
SEARCH_RADIUS_M = 200  # au-delà, distance à une autre zone notée « ≥ 200 m »
NEAR_LIMIT_M, FAR_LIMIT_M = 10, 25  # seuils de l'indice de confiance, à réviser
DIVERGENCE_M = 50
SEED = 20261028
SAMPLE_SIZE = 10
# Paramètres lus dans gpu-client.js (parseUrlParams : #lon=…&lat=…&zoom=…, WGS84)
GPU_VIEWER = "https://www.geoportail-urbanisme.gouv.fr/map/#lon={lon:.6f}&lat={lat:.6f}&zoom=19"
# Couche et jeu de tuiles vérifiés par GetCapabilities de la Géoplateforme (2026-10-28)
ORTHO_URL = (
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM_0_19"
    "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg"
)
LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4"
ATTRIBUTES = [
    "plafond",
    "ces",
    "ces_bande_principale",
    "ces_bande_secondaire",
    "cpt",
    "cpt_bande_principale",
    "cpt_bande_secondaire",
    "hauteur_bande_principale",
    "hauteur_bande_secondaire",
    "stecal",
]

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


class CheckError(RuntimeError):
    """Contrôle bloquant non satisfait."""


@contextmanager
def measured(name: str, steps: dict):
    """Chronomètre une étape et échantillonne le pic RSS du processus toutes les 100 ms."""
    proc, peak, stop = psutil.Process(), [0], threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            stop.wait(0.1)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    start = time.perf_counter()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        peak[0] = max(peak[0], proc.memory_info().rss)
        steps[name] = {
            "seconds": round(time.perf_counter() - start, 2),
            "peak_rss_mb": round(peak[0] / 1e6),
        }
        typer.echo(
            f"  {name} : {steps[name]['seconds']} s, pic RSS {steps[name]['peak_rss_mb']} Mo"
        )


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)
    typer.echo(f"    ✓ {message}")


def load_zonage(con) -> dict:
    meta = scalar(
        con, f"select layers[1].geometry_fields[1].crs.auth_code from ST_Read_Meta('{ZONAGE}')"
    )
    check(meta == "2154", f"CRS déclaré du zonage : EPSG:{meta}")
    con.execute(f"""
        create or replace table z as
        select OGC_FID as zid,
               coalesce(zonage, zone) as code,
               case when zone = 'SECTSAUV' then 'secteur_sauvegarde' else 'plu' end as kind,
               coalesce(regexp_extract(zonage, '^[A-Z]+'), zone) as famille,
               {", ".join(ATTRIBUTES)}, geom
        from ST_Read('{ZONAGE}')""")
    z: dict = {"crs": f"EPSG:{meta}"}
    z["objets"] = scalar(con, "select count(*) from z")
    z["invalides"] = scalar(con, "select count(*) from z where not ST_IsValid(geom)")
    check(z["invalides"] == 0, f"{z['objets']} géométries, toutes valides")
    z["types"] = rows(con, "select ST_GeometryType(geom) type, count(*) n from z group by 1")
    z["codes_distincts"] = scalar(con, "select count(distinct code) from z")
    z["secteur_sauvegarde"] = rows(
        con,
        "select code, round(ST_Area(geom) / 1e4, 2) ha from z where kind = 'secteur_sauvegarde'",
    )
    z["chevauchements"] = rows(
        con,
        """select a.code code_a, b.code code_b,
                  round(ST_Area(ST_Intersection(a.geom, b.geom)), 1) aire_m2
           from z a join z b on a.zid < b.zid and ST_Intersects(a.geom, b.geom)
           where ST_Area(ST_Intersection(a.geom, b.geom)) > 1 order by 3 desc""",
    )
    con.execute(f"""
        create or replace table territoire as
        select ST_Union_Agg(ST_Transform(geom, 'EPSG:4326', 'EPSG:2154', always_xy := true)) g
        from ST_Read('{COMMUNES}')""")
    con.execute("create or replace table zonage_union as select ST_Union_Agg(geom) g from z")
    z["couverture"] = rows(
        con,
        """select round(ST_Area(t.g) / 1e6, 2) territoire_km2,
                  round(ST_Area(u.g) / 1e6, 2) zonage_km2,
                  round(ST_Area(ST_Difference(t.g, u.g)) / 1e4, 2) territoire_non_zone_ha,
                  round(ST_Area(ST_Difference(u.g, t.g)) / 1e4, 2) zonage_hors_territoire_ha
           from territoire t, zonage_union u""",
    )[0]
    return z


def build_points(con) -> None:
    con.execute(f"""
        create or replace table p as
        select siret, etatAdministratifEtablissement etat, statutDiffusionEtablissement diffusion,
               code_commune_cog2026, code_arrondissement, codeCommuneEtablissement code_stock_brut,
               qualite_xy,
               ST_Point(x, y) g,
               case when try_cast(coordonneeLambertAbscisseEtablissement as double) is not null
                     and try_cast(coordonneeLambertOrdonneeEtablissement as double) is not null
                    then ST_Point(try_cast(coordonneeLambertAbscisseEtablissement as double),
                                  try_cast(coordonneeLambertOrdonneeEtablissement as double))
               end gs
        from read_parquet('{SIRENE_ML}') where geoloc_present""")


def locate(con, point_col: str, table: str, where: str = "true") -> None:
    """Table <table>(siret, n_codes, code, kind, famille) : zone(s) contenant le point."""
    con.execute(f"""
        create or replace table {table}_hits as
        select p.siret, z.code, z.kind, z.famille
        from p join z on ST_Contains(z.geom, p.{point_col})
        where p.{point_col} is not null and {where}""")
    con.execute(f"""
        create or replace table {table} as
        select siret, count(distinct code) n_codes,
               case when count(distinct code) = 1 then any_value(code) end code,
               case when count(distinct code) = 1 then any_value(kind) end kind,
               case when count(distinct code) = 1 then any_value(famille) end famille,
               list(distinct code order by code) codes
        from {table}_hits group by 1""")


def classify(con) -> None:
    con.execute("""
        create or replace table etab as
        select p.siret, p.etat, p.diffusion, p.code_commune_cog2026, p.code_arrondissement,
               p.qualite_xy, p.g, p.gs,
               case when m.siret is null then 'aucune_zone'
                    when m.n_codes > 1 then 'multi_zones'
                    when m.kind = 'secteur_sauvegarde' then 'secteur_sauvegarde'
                    else 'une_zone' end categorie,
               m.code, m.famille, m.codes,
               s.code code_stock, s.n_codes n_codes_stock,
               (p.gs is not null) stock_present,
               case when p.gs is not null then ST_Distance(p.g, p.gs) end ecart_sources_m
        from p left join main_zone m using (siret) left join stock_zone s using (siret)""")


def distance_to_other_zone(con) -> None:
    """Distance au polygone le plus proche dont le code de zone est différent (≤ rayon)."""
    con.execute(f"""
        create or replace table dist_autre as
        select e.siret, min(ST_Distance(e.g, z.geom)) d
        from etab e join z on ST_DWithin(e.g, z.geom, {SEARCH_RADIUS_M})
        where e.code is not null and z.code <> e.code
        group by 1""")
    con.execute(f"""
        create or replace table etab2 as
        select e.*, d.d dist_autre_zone_m,
               case
                 when e.code is null then null
                 when e.qualite_xy <> '11' or coalesce(d.d, {SEARCH_RADIUS_M}) < {NEAR_LIMIT_M}
                      or (e.stock_present and e.code_stock is distinct from e.code) then 'faible'
                 when coalesce(d.d, {SEARCH_RADIUS_M}) >= {FAR_LIMIT_M} and e.stock_present
                      and e.code_stock = e.code then 'haute'
                 else 'moyenne'
               end confiance
        from etab e left join dist_autre d using (siret)""")


def join_measures(con) -> dict:
    m: dict = {}
    m["categories"] = rows(
        con,
        """select categorie, count(*) n,
                  count(*) filter (where etat = 'A') actifs,
                  round(100.0 * count(*) / sum(count(*)) over (), 3) pct,
                  round(100.0 * count(*) filter (where etat = 'A')
                        / sum(count(*) filter (where etat = 'A')) over (), 3) pct_actifs
           from etab2 group by 1 order by 2 desc""",
    )
    m["multi_zones_codes"] = rows(
        con,
        """select codes, count(*) n from etab2 where categorie = 'multi_zones'
           group by 1 order by 2 desc limit 20""",
    )
    m["sans_zone"] = rows(
        con,
        """with s as (
             select e.siret, e.g,
                    (select min(ST_Distance(e.g, z.geom)) from z
                     where ST_DWithin(e.g, z.geom, 1000)) d,
                    ST_Contains((select g from territoire), e.g) dans_territoire
             from etab2 e where categorie = 'aucune_zone')
           select case when d is not null and d < 1 then 'bord (< 1 m)'
                       when not dans_territoire then 'hors territoire'
                       when d is null then 'trou du zonage (> 1 km de toute zone)'
                       else 'trou du zonage' end explication,
                  count(*) n, round(median(d), 2) distance_mediane_m
           from s group by 1 order by 2 desc""",
    )
    m["distance_autre_zone"] = rows(
        con,
        f"""select count(*) n,
                  round(quantile_cont(coalesce(dist_autre_zone_m, {SEARCH_RADIUS_M}), 0.1), 1) p10,
                  round(quantile_cont(coalesce(dist_autre_zone_m, {SEARCH_RADIUS_M}), 0.5), 1) p50,
                  round(100.0 * count(*) filter (where dist_autre_zone_m < {NEAR_LIMIT_M})
                        / count(*), 2) pct_moins_10m,
                  round(100.0 * count(*) filter (where dist_autre_zone_m < {FAR_LIMIT_M})
                        / count(*), 2) pct_moins_25m,
                  round(100.0 * count(*) filter (where dist_autre_zone_m is null)
                        / count(*), 2) pct_plus_200m
           from etab2 where code is not null""",
    )[0]
    m["distance_autre_zone_par_famille"] = rows(
        con,
        f"""select famille, count(*) n,
                  round(100.0 * count(*) filter (where dist_autre_zone_m < {NEAR_LIMIT_M})
                        / count(*), 2) pct_moins_10m,
                  round(100.0 * count(*) filter (where dist_autre_zone_m < {FAR_LIMIT_M})
                        / count(*), 2) pct_moins_25m
           from etab2 where code is not null group by 1 order by 2 desc""",
    )
    m["distance_autre_zone_par_qualite"] = rows(
        con,
        f"""select qualite_xy, count(*) n,
                  round(100.0 * count(*) filter (where dist_autre_zone_m < {NEAR_LIMIT_M})
                        / count(*), 2) pct_moins_10m,
                  round(100.0 * count(*) filter (where dist_autre_zone_m < {FAR_LIMIT_M})
                        / count(*), 2) pct_moins_25m
           from etab2 where code is not null group by 1 order by 2 desc""",
    )
    m["sensibilite"] = rows(
        con,
        """select stock_present,
                  case when not stock_present then 'pas de coordonnées stock'
                       when code is not distinct from code_stock then 'même zone'
                       when code is null then 'sans zone → zone (stock)'
                       when code_stock is null then 'zone → sans zone (stock)'
                       else 'zone différente' end resultat,
                  count(*) n
           from etab2 group by all order by all""",
    )
    m["sensibilite_par_qualite"] = rows(
        con,
        """select qualite_xy, count(*) n,
                  round(100.0 * count(*) filter (where code is distinct from code_stock)
                        / count(*), 2) pct_change
           from etab2 where stock_present group by 1 order by 2 desc""",
    )
    m["sensibilite_par_famille"] = rows(
        con,
        """select famille, count(*) n,
                  round(100.0 * count(*) filter (where code is distinct from code_stock)
                        / count(*), 2) pct_change
           from etab2 where stock_present and code is not null group by 1 order by 2 desc""",
    )
    m["sensibilite_par_ecart"] = rows(
        con,
        f"""select ecart_sources_m > {DIVERGENCE_M} ecart_sup_50m, count(*) n,
                  count(*) filter (where code is distinct from code_stock) change_zone
           from etab2 where stock_present group by 1 order by 1""",
    )
    m["confiance"] = rows(
        con,
        """select confiance, count(*) n, count(*) filter (where etat = 'A') actifs,
                  round(100.0 * count(*) / sum(count(*)) over (), 2) pct
           from etab2 where code is not null group by 1 order by 1""",
    )
    m["confiance_par_famille"] = rows(
        con,
        """select famille, count(*) n,
                  round(100.0 * count(*) filter (where confiance = 'haute') / count(*), 1) haute,
                  round(100.0 * count(*) filter (where confiance = 'moyenne') / count(*), 1)
                      moyenne,
                  round(100.0 * count(*) filter (where confiance = 'faible') / count(*), 1) faible
           from etab2 where code is not null group by 1 order by 2 desc""",
    )
    m["confiance_par_commune"] = rows(
        con,
        """select coalesce(code_arrondissement, code_commune_cog2026) code, count(*) n,
                  round(100.0 * count(*) filter (where confiance = 'haute') / count(*), 1) haute,
                  round(100.0 * count(*) filter (where confiance = 'faible') / count(*), 1) faible
           from etab2 where code is not null group by 1 order by 1""",
    )
    return m


def attribute_inventory(con) -> dict:
    inv: dict = {}
    for col in ATTRIBUTES:
        inv[col] = {
            "remplis": scalar(
                con, f"select count(*) from z where nullif(trim({col}), '') is not null"
            ),
            "valeurs": rows(
                con,
                f"""select {col} valeur, count(*) n from z
                    where nullif(trim({col}), '') is not null
                    group by 1 order by 2 desc limit 15""",
            ),
            "par_famille": rows(
                con,
                f"""select famille, count(*) objets,
                       count(*) filter (where nullif(trim({col}), '') is not null) remplis
                    from z group by 1 having remplis > 0 order by 3 desc""",
            ),
        }
    return inv


def zone_codes(con) -> list[dict]:
    return rows(
        con,
        """select z.code, any_value(z.famille) famille, any_value(z.kind) kind,
                  count(distinct z.zid) polygones, round(sum(ST_Area(z.geom)) / 1e4, 1) surface_ha,
                  coalesce(any_value(e.n), 0) etablissements,
                  coalesce(any_value(e.actifs), 0) actifs
           from z left join (select code, count(*) n, count(*) filter (where etat='A') actifs
                             from etab2 group by 1) e using (code)
           group by 1 order by 6 desc""",
    )


def reglement_matches(codes: list[str]) -> dict:
    """Cherche chaque code de zone dans les titres puis le texte du règlement écrit."""
    import pymupdf

    doc = pymupdf.open(REGLEMENT)
    toc = doc.get_toc()
    text_pages = [page.get_text() for page in doc]
    result = {"pages": doc.page_count, "entrees_toc": len(toc), "codes": {}}
    for code in codes:
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])")
        in_toc = [t[1] for t in toc if pattern.search(t[1])]
        pages = [i + 1 for i, txt in enumerate(text_pages) if pattern.search(txt)]
        result["codes"][code] = {
            "toc": in_toc[:3],
            "pages_texte": len(pages),
            "premiere_page": pages[0] if pages else None,
        }
    return result


def draw_samples(con) -> dict:
    hashed = f"hash(siret || '{SEED}')"
    con.execute(f"""
        create or replace table validation as
        select 'validation' echantillon, * from etab2
        where etat = 'A' and diffusion = 'O' and categorie = 'une_zone'
        order by {hashed} limit {SAMPLE_SIZE}""")
    counts = rows(
        con,
        f"""select count(*) filter (where code is distinct from code_stock) zones_differentes,
                  count(*) filter (where code is not distinct from code_stock) meme_zone
           from etab2 where etat = 'A' and diffusion = 'O' and stock_present
                      and ecart_sources_m > {DIVERGENCE_M}""",
    )[0]
    con.execute(f"""
        create or replace table arbitrage as
        select 'arbitrage' echantillon, * exclude (prio) from (
            select *, (code is distinct from code_stock) prio from etab2
            where etat = 'A' and diffusion = 'O' and stock_present
                  and ecart_sources_m > {DIVERGENCE_M}
                  and siret not in (select siret from validation)  -- échantillons distincts
            order by prio desc, {hashed} limit {SAMPLE_SIZE})""")
    return {"graine": SEED, "arbitrage_disponibles": counts}


def write_controls(con) -> list[dict]:
    """controles.csv (local) avec l'adresse déclarée relue dans le stock brut."""
    controls = rows(
        con,
        f"""with c as (select * from validation union all by name select * from arbitrage),
            a as (select siret, statutDiffusionEtablissement diffusion_brute,
                         concat_ws(' ', numeroVoieEtablissement, indiceRepetitionEtablissement,
                                   typeVoieEtablissement, libelleVoieEtablissement) voie,
                         codePostalEtablissement code_postal,
                         libelleCommuneEtablissement commune
                  from read_parquet('{STOCK}') where siret in (select siret from c))
            select row_number() over (order by c.echantillon desc, c.siret) num,
                   c.echantillon,
                   coalesce(c.code_arrondissement, c.code_commune_cog2026) code_commune,
                   c.code zone_principale, c.code_stock zone_stock,
                   round(c.ecart_sources_m, 1) ecart_m, c.qualite_xy,
                   round(c.dist_autre_zone_m, 1) dist_autre_zone_m, c.confiance,
                   a.diffusion_brute, a.voie, a.code_postal, a.commune,
                   ST_X(ST_Transform(c.g, 'EPSG:2154', 'EPSG:4326', always_xy := true)) lon,
                   ST_Y(ST_Transform(c.g, 'EPSG:2154', 'EPSG:4326', always_xy := true)) lat,
                   ST_X(ST_Transform(c.gs, 'EPSG:2154', 'EPSG:4326', always_xy := true)) lon_stock,
                   ST_Y(ST_Transform(c.gs, 'EPSG:2154', 'EPSG:4326', always_xy := true)) lat_stock
            from c join a using (siret) order by num""",
    )
    check(len(controls) == 2 * SAMPLE_SIZE, f"{len(controls)} contrôles tirés")
    check(
        len({(c["lon"], c["lat"]) for c in controls}) == len(controls),
        "aucun établissement commun aux deux échantillons",
    )
    check(
        all(c["diffusion_brute"] == "O" for c in controls),
        "tous les contrôles sont en diffusion O dans le stock brut",
    )
    with (OUTPUT_DIR / "controles.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "num", "echantillon", "code_commune", "zone_principale", "zone_stock",
                "ecart_sources_m", "qualite_xy", "dist_autre_zone_m", "confiance",
                "adresse_voie", "code_postal", "commune", "lien_gpu_principal", "lien_gpu_stock",
                "zone_attendue", "source_juste", "commentaire",
            ]
        )  # fmt: skip
        for c in controls:
            writer.writerow(
                [
                    c["num"], c["echantillon"], c["code_commune"], c["zone_principale"],
                    c["zone_stock"], c["ecart_m"], c["qualite_xy"], c["dist_autre_zone_m"],
                    c["confiance"], c["voie"], c["code_postal"], c["commune"],
                    GPU_VIEWER.format(lon=c["lon"], lat=c["lat"]),
                    GPU_VIEWER.format(lon=c["lon_stock"], lat=c["lat_stock"])
                    if c["lon_stock"] is not None else "",
                    "", "", "",
                ]
            )  # fmt: skip
    return controls


def write_map(con, controls: list[dict]) -> None:
    """Carte Leaflet : zones autour de chaque point, positions principale et stock.

    Aucune adresse, aucun SIRET, aucun nom : seulement numéro de contrôle et codes de zone.
    """
    zones = rows(
        con,
        """with c as (select g, gs from validation union all by name select g, gs from arbitrage)
           select distinct z.zid, z.code,
                  ST_AsGeoJSON(ST_Transform(z.geom, 'EPSG:2154', 'EPSG:4326', always_xy := true)) gj
           from z, c where ST_DWithin(z.geom, c.g, 150)
                        or (c.gs is not null and ST_DWithin(z.geom, c.gs, 150))""",
    )
    features = [
        {"type": "Feature", "properties": {"code": r["code"]}, "geometry": json.loads(r["gj"])}
        for r in zones
    ]
    points = [
        {
            "num": c["num"],
            "echantillon": c["echantillon"],
            "zone": c["zone_principale"],
            "zone_stock": c["zone_stock"],
            "lat": c["lat"],
            "lon": c["lon"],
            "lat_stock": c["lat_stock"],
            "lon_stock": c["lon_stock"],
            "gpu": GPU_VIEWER.format(lon=c["lon"], lat=c["lat"]),
        }
        for c in controls
    ]
    html = MAP_TEMPLATE.replace("__LEAFLET__", LEAFLET).replace("__ORTHO__", ORTHO_URL)
    html = html.replace(
        "__ZONES__", json.dumps({"type": "FeatureCollection", "features": features})
    )
    html = html.replace("__POINTS__", json.dumps(points))
    (OUTPUT_DIR / "carte_controles.html").write_text(html, encoding="utf-8")


MAP_TEMPLATE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contrôles Test 2</title>
<link rel="stylesheet" href="__LEAFLET__/leaflet.min.css">
<script src="__LEAFLET__/leaflet.min.js"></script>
<style>
  body { margin: 0; font: 14px system-ui, sans-serif; display: flex; height: 100vh; }
  #list { width: 300px; overflow-y: auto; padding: 8px; box-sizing: border-box; }
  #map { flex: 1; }
  .item { padding: 6px; border-bottom: 1px solid #ddd; cursor: pointer; }
  .item:hover { background: #eef; }
  .tag { font-size: 11px; color: #555; }
  .lbl { background: #fff; border: 1px solid #333; padding: 1px 4px; font-weight: 600; }
</style></head><body>
<div id="list"><b>Contrôles Test 2</b><br>
<span class="tag">● bleu = géolocalisation (principale) ; ● orange = stock (sensibilité).
Contours = zones PLU-H.</span></div>
<div id="map"></div>
<script>
const ZONES = __ZONES__;
const POINTS = __POINTS__;
const map = L.map('map');
map.fitBounds(POINTS.map(p => [p.lat, p.lon]), {padding: [20, 20]});
const ortho = L.tileLayer('__ORTHO__', {maxZoom: 19, attribution: 'IGN – Géoplateforme'});
const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19, attribution: '© OpenStreetMap'});
ortho.addTo(map);
L.control.layers({'Orthophoto IGN': ortho, 'OpenStreetMap': osm}).addTo(map);
L.geoJSON(ZONES, {style: {color: '#ffeb3b', weight: 2, fillOpacity: 0.05},
  onEachFeature: (f, l) => l.bindTooltip(f.properties.code, {sticky: true})}).addTo(map);
const list = document.getElementById('list');
POINTS.forEach(p => {
  const m = L.circleMarker([p.lat, p.lon], {radius: 7, color: '#1565c0', fillOpacity: 0.9})
    .bindTooltip(`#${p.num} ${p.zone ?? '—'}`, {permanent: true, className: 'lbl'}).addTo(map);
  if (p.lat_stock !== null) {
    L.circleMarker([p.lat_stock, p.lon_stock], {radius: 6, color: '#ef6c00', fillOpacity: 0.9})
      .bindTooltip(`#${p.num} stock ${p.zone_stock ?? '—'}`).addTo(map);
    L.polyline([[p.lat, p.lon], [p.lat_stock, p.lon_stock]], {color: '#ef6c00', dashArray: '4'})
      .addTo(map);
  }
  const d = document.createElement('div');
  d.className = 'item';
  d.innerHTML = `<b>#${p.num}</b> <span class="tag">${p.echantillon}</span><br>` +
    `principale : ${p.zone ?? '—'} · stock : ${p.zone_stock ?? '—'}<br>` +
    `<a href="${p.gpu}" target="_blank" rel="noopener">Géoportail de l'Urbanisme</a>`;
  d.onclick = (e) => { if (e.target.tagName !== 'A') map.setView([p.lat, p.lon], 19); };
  list.appendChild(d);
});
</script></body></html>
"""


@app.command()
def main(
    force: Annotated[bool, typer.Option(help="Écraser les sorties existantes")] = False,
) -> None:
    """Jointure spatiale, sensibilité, indice de confiance et contrôles du Test 2."""
    if OUT_PARQUET.exists() and not force:
        typer.echo(f"{OUT_PARQUET} existe : relancer avec --force.", err=True)
        sys.exit(1)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("set memory_limit = '6GB'")
    con.load_extension("spatial")
    steps: dict = {}
    result: dict = {"started_at": datetime.now(UTC).isoformat(), "steps": steps}
    try:
        with measured("1_zonage", steps):
            result["zonage"] = load_zonage(con)
        with measured("2a_points", steps):
            build_points(con)
            n_points = scalar(con, "select count(*) from p")
        with measured(f"2b_jointure_{PILOT_ARRONDISSEMENT}", steps):
            locate(con, "g", "pilot_zone", f"p.code_arrondissement = '{PILOT_ARRONDISSEMENT}'")
            result["pilote"] = {
                "points": scalar(
                    con,
                    f"select count(*) from p where code_arrondissement = '{PILOT_ARRONDISSEMENT}'",
                ),
                "avec_zone": scalar(con, "select count(*) from pilot_zone"),
                "multi_zones": scalar(con, "select count(*) from pilot_zone where n_codes > 1"),
            }
        with measured("2c_jointure_metropole", steps):
            locate(con, "g", "main_zone")
        with measured("5_jointure_stock", steps):
            locate(con, "gs", "stock_zone")
        with measured("2d_classement", steps):
            classify(con)
            total = scalar(con, "select count(*) from etab")
            check(total == n_points, f"{total:,} établissements géolocalisés, une catégorie chacun")
            bellecour = scalar(
                con, "select code from z where ST_Contains(geom, ST_Point(842395.13, 6519229.36))"
            )
            check(bellecour == "UCe1b", f"point de contrôle place Bellecour → {bellecour}")
        with measured("3_distance_autre_zone", steps):
            distance_to_other_zone(con)
        with measured("mesures", steps):
            result["mesures"] = join_measures(con)
            result["attributs"] = attribute_inventory(con)
            codes = zone_codes(con)
            result["codes_zone"] = codes
        with measured("8_reglement", steps):
            result["reglement"] = reglement_matches(
                [c["code"] for c in codes if c["kind"] == "plu"]
            )
        with measured("7_controles", steps):
            result["echantillons"] = draw_samples(con)
            controls = write_controls(con)
            write_map(con, controls)
        with (OUTPUT_DIR / "zones.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(codes[0]))
            writer.writeheader()
            writer.writerows(codes)
        con.execute(f"""
            copy (select siret, etat, diffusion, code_commune_cog2026, code_arrondissement,
                         qualite_xy, categorie, code zone, famille, code_stock zone_stock,
                         ecart_sources_m, dist_autre_zone_m, confiance
                  from etab2) to '{OUT_PARQUET}' (format parquet)""")
    except CheckError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        result["erreur"] = str(exc)
        sys.exit(1)
    finally:
        result["parametres"] = {
            "rayon_recherche_m": SEARCH_RADIUS_M,
            "seuils_confiance_m": [NEAR_LIMIT_M, FAR_LIMIT_M],
            "ecart_divergence_m": DIVERGENCE_M,
            "graine": SEED,
        }
        result["environment"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "versions": {p: version(p) for p in ("duckdb", "psutil", "pymupdf")},
            "sources_sha256": {
                str(p.parent.relative_to(RAW)): json.loads(p.read_text())["sha256"]
                for p in sorted(RAW.glob(f"*/{RAW_DATE}/*/manifest.json"))
            },
        }
        out = OUTPUT_DIR / "metrics.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n")
        typer.echo(f"Mesures : {out}")


if __name__ == "__main__":
    app()
