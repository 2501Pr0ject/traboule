"""Composante structurée : DuckDB en lecture seule, vues en liste blanche (conventions §5).

- connexion `read_only=True` ; l'extension spatial est chargée, puis l'accès aux fichiers est
  coupé (`enable_external_access = false`) : rien n'est lu hors de la base ;
- seules les vues temporaires de `VIEWS` sont interrogeables : contrôle sur l'arbre syntaxique
  (`json_serialize_sql`) d'une instruction SELECT unique, sans fonction de table ni colonne
  `siret` ;
- les vues ne portent aucun identifiant (ni SIRET, ni coordonnées) et les gabarits ne renvoient
  que des agrégats : aucune ligne individuelle, en statut P ou non, n'est exposée ;
- aucun SQL n'est écrit par un modèle : les paramètres viennent de l'analyse déterministe et
  sont liés (`?`), jamais concaténés.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from traboule.config import MIN_INTERSECTION_M2, PROCESSED_DIR
from traboule.contracts.reponse import Composante, Minorant, SourceDonnees, VentilationConfiance
from traboule.routing.analyse import (
    NAF_SECTIONS,
    Activity,
    Analysis,
    Lexicon,
    Place,
    build_lexicon,
)
from traboule.routing.routeur import Decision

DATABASE = PROCESSED_DIR / "traboule.duckdb"
MAX_ROWS = 500
CELL_M = 200  # côté des carreaux du carroyage (m), vue v_etablissements_carreaux
LOCATION_LIMIT = (
    "Analyse de localisation, pas un constat réglementaire : zone rattachée au point d'adresse "
    "géolocalisé (ADR-0006)."
)
VIEWS = {
    "v_etablissements": """
        select etatAdministratifEtablissement as etat,
               statutDiffusionEtablissement as diffusion,
               code_commune_cog2026, code_arrondissement,
               codeCommuneEtablissement as code_commune_stock,
               activitePrincipaleEtablissement as naf, position_publique
        from etablissements""",
    "v_etablissements_zones": """
        select z.etat, z.code_commune_cog2026, z.code_arrondissement, z.zone, z.confiance,
               e.activitePrincipaleEtablissement as naf
        from etablissements_zones z join etablissements e using (siret)
        where z.diffusion = 'O'""",
    # Carroyage : coin sud-ouest du carreau de CELL_M m seulement, jamais les coordonnées de
    # l'établissement ; positions publiques seulement (statut P exclu, règle 10).
    "v_etablissements_carreaux": f"""
        select z.etat, z.code_commune_cog2026, z.code_arrondissement, z.zone, z.confiance,
               e.activitePrincipaleEtablissement as naf,
               floor(e.x / {CELL_M}) * {CELL_M} as cx, floor(e.y / {CELL_M}) * {CELL_M} as cy
        from etablissements_zones z join etablissements e using (siret)
        where z.diffusion = 'O' and e.position_publique""",
    "v_zonage": "select code, geom from zonage",
    "v_unites": "select code, niveau, geom from unites",
    "v_communes": "select code_commune as code, libelle from communes",
    "v_arrondissements": "select code_arrondissement as code, libelle from arrondissements",
    "v_zones_reglement": """
        select code_zone, methode, chapitre, page_chapitre, zone_u_reference, chapitre_u,
               abstention_motif, version_piece
        from zones_reglement""",
    "v_catalogue": "select nom, millesime, sources from _catalogue",
}
# Table du catalogue (millésime, sources) derrière chaque vue, pour citer les données.
VIEW_TABLES = {
    "v_etablissements": "etablissements",
    "v_etablissements_zones": "etablissements_zones",
    "v_etablissements_carreaux": "etablissements_zones",
    "v_zonage": "zonage",
    "v_unites": "unites",
}
FORBIDDEN_COLUMNS = {"siret", "siren", "nic", "x", "y"}

logger = logging.getLogger(__name__)


class SqlGuardError(ValueError):
    """Requête refusée par les garde-fous SQL."""


def connect(database: Path = DATABASE) -> duckdb.DuckDBPyConnection:
    """Connexion en lecture seule, vues en liste blanche, accès aux fichiers coupé."""
    con = duckdb.connect(str(database), read_only=True)
    con.execute("load spatial")
    for name, body in VIEWS.items():
        con.execute(f"create temp view {name} as {body}")
    con.execute("set enable_external_access = false")
    return con


def _references(node, tables: set, ctes: set, functions: set, columns: set) -> None:
    if isinstance(node, dict):
        kind = node.get("type")
        if kind == "BASE_TABLE":
            tables.add(node.get("table_name"))
        elif kind == "TABLE_FUNCTION":
            functions.add(str(node.get("function", {}).get("function_name")))
        elif node.get("class") == "COLUMN_REF":
            columns.update(str(c).lower() for c in node.get("column_names", []))
        for entry in (node.get("cte_map") or {}).get("map", []):
            ctes.add(entry.get("key"))
        for value in node.values():
            _references(value, tables, ctes, functions, columns)
    elif isinstance(node, list):
        for value in node:
            _references(value, tables, ctes, functions, columns)


def check_query(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Une seule instruction SELECT, sur les vues de la liste blanche seulement."""
    statements = duckdb.extract_statements(sql)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise SqlGuardError("une seule instruction SELECT est acceptée")
    tree = json.loads(con.execute("select json_serialize_sql(?)", [sql]).fetchone()[0])
    if tree.get("error"):
        raise SqlGuardError(tree.get("error_message", "requête illisible"))
    tables, ctes, functions, columns = set(), set(), set(), set()
    _references(tree, tables, ctes, functions, columns)
    if functions:
        raise SqlGuardError(f"fonction de table refusée : {sorted(functions)}")
    if outside := tables - ctes - set(VIEWS):
        raise SqlGuardError(f"hors liste blanche : {sorted(outside)}")
    if forbidden := columns & FORBIDDEN_COLUMNS:
        raise SqlGuardError(f"colonne interdite : {sorted(forbidden)}")


def query(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list | None = None,
    max_rows: int = MAX_ROWS,
) -> list[dict]:
    """Exécute une requête contrôlée ; refuse un résultat de plus de `max_rows` lignes."""
    check_query(con, sql)
    logger.info("sql : %s | paramètres : %s", " ".join(sql.split()), params)
    cursor = con.execute(sql, params or [])
    names = [d[0] for d in cursor.description]
    rows = cursor.fetchmany(max_rows + 1)
    if len(rows) > max_rows:
        raise SqlGuardError(f"plus de {max_rows} lignes")
    return [dict(zip(names, row, strict=True)) for row in rows]


def activity_condition(activity: Activity | None) -> tuple[str, list]:
    """Condition sur la colonne `naf` (NAF rév. 2) des vues d'établissements."""
    if activity is None:
        return "true", []
    if activity.niveau == "section":
        first, last, _ = NAF_SECTIONS[activity.code]
        return "try_cast(substr(naf, 1, 2) as int) between ? and ?", [first, last]
    length = {"division": 2, "groupe": 4, "classe": 5}.get(activity.niveau)
    if length:
        return f"substr(naf, 1, {length}) = ?", [activity.code]
    return "naf = ?", [activity.code]


def place_condition(places: tuple[Place, ...] | list[Place]) -> tuple[str, list]:
    if not places:
        return "true", []
    communes = [p.code for p in places if p.niveau == "commune"]
    arrondissements = [p.code for p in places if p.niveau == "arrondissement_municipal"]
    parts, params = [], []
    if communes:
        parts.append(f"code_commune_cog2026 in ({', '.join('?' * len(communes))})")
        params += communes
    if arrondissements:
        parts.append(f"code_arrondissement in ({', '.join('?' * len(arrondissements))})")
        params += arrondissements
    return "(" + " or ".join(parts) + ")", params


def place_label(place: Place | None) -> str:
    if place is None:
        return "dans la Métropole de Lyon"
    if place.niveau == "arrondissement_municipal":
        n = int(place.code[-1])
        return f"dans le {'1er' if n == 1 else f'{n}e'} arrondissement de Lyon ({place.code})"
    if place.code == "69123":
        return "à Lyon (69123, arrondissements compris)"
    return f"à {place.libelle} ({place.code})"


def of_place(place: Place) -> str:
    """« de Vénissieux (69259) », « d'Écully (69081) », « du 7e arrondissement de Lyon (69387) »."""
    if place.niveau == "arrondissement_municipal":
        n = int(place.code[-1])
        return f"du {'1er' if n == 1 else f'{n}e'} arrondissement de Lyon ({place.code})"
    if place.code == "69123":
        return "de Lyon (69123, arrondissements compris)"
    article = "d'" if place.libelle[:1] in "AEIOUYÉÈÊÂÎÔ" else "de "
    return f"{article}{place.libelle} ({place.code})"


def units_of(units: list[Place], named: int = 3) -> str:
    """Unités du minorant, nommées jusqu'à `named` ; au-delà, leur nombre."""
    if not units:
        return "d'aucune unité géographique"
    if len(units) > named:
        return f"des {len(units)} communes ou arrondissements que touche la zone"
    parts = [of_place(p) for p in units]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " et " + parts[-1]


def places_label(places: tuple[Place, ...]) -> str:
    return " ; ".join(place_label(p) for p in places) if places else place_label(None)


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fmt_pct(x: float) -> str:
    return f"{x:.2f}".replace(".", ",") + " %"


def with_params(sql: str, params: list) -> str:
    return " ".join(sql.split()) + (f"\n-- paramètres : {params}" if params else "")


@dataclass
class StructuredComponent:
    """Construit la composante structurée d'une réponse à partir de l'analyse."""

    con: duckdb.DuckDBPyConnection
    lexicon: Lexicon

    def __post_init__(self) -> None:
        rows = query(self.con, "select nom, millesime, sources from v_catalogue")
        self.catalogue = {
            r["nom"]: SourceDonnees(
                table=r["nom"], millesime=r["millesime"], sources=list(r["sources"])
            )
            for r in rows
        }

    def sources(self, *views: str) -> list[SourceDonnees]:
        return [self.catalogue[VIEW_TABLES[v]] for v in views if VIEW_TABLES[v] in self.catalogue]

    def build(self, analysis: Analysis, decision: Decision) -> list[Composante]:
        if decision.structured_abstention:
            motif, text = decision.structured_abstention
            return [Composante(type="structuree", abstention=True, motif=motif, texte=text,
                               limites=[text])]  # fmt: skip
        zones = list(analysis.zones) or (["SECTSAUV"] if analysis.safeguarded else [])
        if analysis.measure == "distribution":
            return [self.distribution(analysis)]
        if analysis.measure == "share":
            return [self.share(analysis, place) for place in analysis.places or [None]]
        if zones:
            return [self.zone_count(analysis, zone) for zone in zones]
        return [self.count(analysis, place) for place in analysis.places or [None]]

    def _labels(self, analysis: Analysis) -> tuple[str, str]:
        state = "actifs" if analysis.etat == "A" else "fermés"
        activity = f" relevant de la {analysis.activity.label}" if analysis.activity else ""
        return state, activity

    def count(self, analysis: Analysis, place: Place | None) -> Composante:
        act_sql, act_params = activity_condition(analysis.activity)
        pl_sql, pl_params = place_condition([place] if place else [])
        sql = f"""select count(*) as n,
                         count(*) filter (where code_arrondissement is null
                                          and code_commune_stock <> code_commune_cog2026) as anciens
                  from v_etablissements where etat = ? and {pl_sql} and {act_sql}"""
        params = [analysis.etat, *pl_params, *act_params]
        row = query(self.con, sql, params)[0]
        state, activity = self._labels(analysis)
        stock = self.catalogue["etablissements"].millesime.split(";")[0].strip()
        text = (
            f"{fmt(row['n'])} établissements {state}{activity} {place_label(place)}, "
            f"d'après le {stock}."
        )
        queries = [with_params(sql, params)]
        if place and place.niveau == "commune" and place.code != "69123" and row["anciens"]:
            old_sql = """select code_commune_stock as code, count(*) as n from v_etablissements
                         where etat = ? and code_commune_cog2026 = ? and code_commune_stock <> ?
                           and {act} group by 1 order by 1""".replace("{act}", act_sql)
            old_params = [analysis.etat, place.code, place.code, *act_params]
            old = query(self.con, old_sql, old_params)
            detail = ", ".join(f"{fmt(r['n'])} sous le code {r['code']}" for r in old)
            text += f" Dont {detail} (code commune antérieur au COG 2026, porté par le stock)."
            queries.append(with_params(old_sql, old_params))
        return Composante(
            type="structuree",
            valeur=row["n"],
            texte=text,
            sources=self.sources("v_etablissements"),
            requete="\n".join(queries),
        )

    def share(self, analysis: Analysis, place: Place | None) -> Composante:
        pl_sql, pl_params = place_condition([place] if place else [])
        state, _ = self._labels(analysis)
        if analysis.partial_diffusion:
            cond, cond_params = "diffusion = 'P'", []
            what = "sont en diffusion partielle (statut P)"
            limits = ["Un établissement en statut P n'a aucune position publique (conventions §3, "
                      "règle 10) : il n'entre dans aucun comptage par zone."]  # fmt: skip
        else:
            cond, cond_params = activity_condition(analysis.activity)
            what, limits = f"relèvent de la {analysis.activity.label}", []
        sql = f"""select count(*) as total, count(*) filter (where {cond}) as n
                  from v_etablissements where etat = ? and {pl_sql}"""
        params = [*cond_params, analysis.etat, *pl_params]
        row = query(self.con, sql, params)[0]
        pct = round(100 * row["n"] / row["total"], 2) if row["total"] else 0.0
        stock = self.catalogue["etablissements"].millesime.split(";")[0].strip()
        text = (f"{fmt_pct(pct)} des établissements {state} {place_label(place)} {what} : "
                f"{fmt(row['n'])} sur {fmt(row['total'])}, d'après le {stock}.")  # fmt: skip
        return Composante(type="structuree", valeur=pct, texte=text, limites=limits,
                          sources=self.sources("v_etablissements"),
                          requete=with_params(sql, params))  # fmt: skip

    def _lower_bound(self, analysis: Analysis, codes: list[str]) -> tuple[Minorant, str]:
        act_sql, act_params = activity_condition(analysis.activity)
        state, activity = self._labels(analysis)
        if analysis.places:
            pl_sql, pl_params = place_condition(analysis.places)
            sql = f"""select count(*) as n from v_etablissements
                      where etat = ? and not position_publique and {pl_sql} and {act_sql}"""
            params = [analysis.etat, *pl_params, *act_params]
            n = query(self.con, sql, params)[0]["n"]
            units = list(analysis.places)
        else:
            marks = ", ".join("?" * len(codes))
            sql = f"""with g as (select geom from v_zonage where code in ({marks})),
                      u as (select u.code from v_unites u, g
                            where ST_Intersects(u.geom, g.geom) group by u.code
                            having sum(ST_Area(ST_Intersection(u.geom, g.geom))) > ?)
                      select (select list(code order by code) from u) as unites, count(*) as n
                      from v_etablissements
                      where etat = ? and not position_publique
                        and (code_commune_cog2026 in (select code from u)
                             or code_arrondissement in (select code from u))
                        and {act_sql}"""
            params = [*codes, MIN_INTERSECTION_M2, analysis.etat, *act_params]
            row = query(self.con, sql, params)[0]
            n = row["n"]
            by_code = {p.code: p for p in self.lexicon.places.values()}
            units = [by_code.get(c, Place(c, "commune", c)) for c in row["unites"] or []]
        minorant = Minorant(n=n, perimetre=units_of(units), qui=f"établissements {state}{activity}")
        return minorant, with_params(sql, params)

    def zone_count(self, analysis: Analysis, zone: str) -> Composante:
        codes = self.lexicon.zonage_codes(zone)
        act_sql, act_params = activity_condition(analysis.activity)
        pl_sql, pl_params = place_condition(analysis.places)
        marks = ", ".join("?" * len(codes))
        sql = f"""select count(*) filter (where confiance = 'haute') as haute,
                         count(*) filter (where confiance = 'moyenne') as moyenne,
                         count(*) filter (where confiance = 'faible') as faible
                  from v_etablissements_zones
                  where etat = ? and zone in ({marks}) and {pl_sql} and {act_sql}"""
        params = [analysis.etat, *codes, *pl_params, *act_params]
        row = query(self.con, sql, params)[0]
        split = VentilationConfiance(**row)
        minorant, bound_sql = self._lower_bound(analysis, codes)
        state, activity = self._labels(analysis)
        covered = f" (codes {', '.join(codes)})" if codes != [zone] else ""
        where = f" {places_label(analysis.places)}" if analysis.places else ""
        text = (f"{fmt(split.total)} établissements {state}{activity} sont géolocalisés en zone "
                f"{zone}{covered}{where}. Confiance de zone : {fmt(split.haute)} haute, "
                f"{fmt(split.moyenne)} moyenne, {fmt(split.faible)} faible. "
                f"{minorant.formulation}")  # fmt: skip
        return Composante(
            type="structuree", valeur=split.total, texte=text, comptage_spatial=True,
            ventilation_confiance=split, minorant=minorant, limites=[LOCATION_LIMIT],
            sources=self.sources("v_etablissements_zones", "v_etablissements",
                                 *(() if analysis.places else ("v_zonage", "v_unites"))),
            requete=with_params(sql, params) + "\n" + bound_sql,
        )  # fmt: skip

    def distribution(self, analysis: Analysis) -> Composante:
        act_sql, act_params = activity_condition(analysis.activity)
        pl_sql, pl_params = place_condition(analysis.places)
        sql = f"""select zone, count(*) as n,
                         count(*) filter (where confiance = 'haute') as haute,
                         count(*) filter (where confiance = 'moyenne') as moyenne,
                         count(*) filter (where confiance = 'faible') as faible
                  from v_etablissements_zones
                  where etat = ? and zone is not null and {pl_sql} and {act_sql}
                  group by zone order by n desc, zone"""
        params = [analysis.etat, *pl_params, *act_params]
        rows = query(self.con, sql, params)
        split = VentilationConfiance(haute=sum(r["haute"] for r in rows),
                                     moyenne=sum(r["moyenne"] for r in rows),
                                     faible=sum(r["faible"] for r in rows))  # fmt: skip
        minorant, bound_sql = self._lower_bound(analysis, [r["zone"] for r in rows])
        state, activity = self._labels(analysis)
        shown = ", ".join(f"{r['zone']} {fmt(r['n'])}" for r in rows[:12])
        more = f", et {len(rows) - 12} autres zones" if len(rows) > 12 else ""
        text = (f"Répartition des {fmt(split.total)} établissements {state}{activity} "
                f"géolocalisés {places_label(analysis.places)} par zone du PLU-H : {shown}{more}. "
                f"{minorant.phrase("dans l'une de ces zones")}")  # fmt: skip
        value = [{"zone": r["zone"], "n": r["n"], "faible": r["faible"]} for r in rows]
        return Composante(
            type="structuree", valeur=value, texte=text, comptage_spatial=True,
            ventilation_confiance=split, minorant=minorant, limites=[LOCATION_LIMIT],
            sources=self.sources("v_etablissements_zones", "v_etablissements"),
            requete=with_params(sql, params) + "\n" + bound_sql,
        )  # fmt: skip


def load_lexicon(con: duckdb.DuckDBPyConnection) -> Lexicon:
    """Lexique de l'analyse : zones du règlement, lieux, date du stock, année du règlement."""
    zone_rows = query(con, "select * from v_zones_reglement")
    places = [
        Place(r["code"], "commune", r["libelle"])
        for r in query(con, "select code, libelle from v_communes")
    ] + [
        Place(r["code"], "arrondissement_municipal", r["libelle"])
        for r in query(con, "select code, libelle from v_arrondissements")
    ]
    millesime = query(con, "select millesime from v_catalogue where nom = 'etablissements'")
    stock = re.search(r"\d{4}-\d{2}-\d{2}", millesime[0]["millesime"]) if millesime else None
    if stock is None:
        raise SqlGuardError("date du stock Sirene introuvable dans le catalogue")
    years = [
        int(y) for r in zone_rows for y in re.findall(r"\b(20\d{2})\b", r["version_piece"] or "")
    ]
    return build_lexicon(zone_rows, places, date.fromisoformat(stock.group()), max(years))
