"""Minorant d'un comptage spatial (conventions §3, règle 7).

Un établissement est sans position publique s'il n'a pas de coordonnées ou s'il est en
statut `P` (`not position_publique` dans sirene_ml). Pour un comptage dans une zone, le
minorant porte sur les unités géographiques dont l'intersection avec la zone dépasse
`MIN_INTERSECTION_M2`, ce qui écarte les contacts de bordure ; il se formule « jusqu'à N
établissements supplémentaires pourraient se trouver dans la zone ».

Unités : les communes (COG 2026), Lyon étant remplacée par ses 9 arrondissements quand
leurs contours sont chargés (REF-ARRONDISSEMENTS-LYON). Un établissement de Lyon est alors
rattaché par son code d'arrondissement ; celui qui n'en a pas (code 69123 dans le stock)
n'entre dans aucun périmètre.

Tables attendues : `z` (zonage, EPSG:2154, geo.jointure) et `unites(code, niveau, geom)`
en EPSG:2154 (`load_units`).
"""

from pathlib import Path

import duckdb

from traboule.config import MIN_INTERSECTION_M2
from traboule.contracts.etablissement import LYON
from traboule.contracts.reponse import Minorant
from traboule.geo.crs import LAMBERT93, require_crs, to_lambert93


def load_units(
    con: duckdb.DuckDBPyConnection, communes: Path, arrondissements: Path | None = None
) -> int:
    """Table unites(code, niveau, geom) en EPSG:2154.

    `communes` : couche REF-COMMUNES-ML-2024 (EPSG:4326) ; `arrondissements` : couche
    REF-ARRONDISSEMENTS-LYON (EPSG:2154), qui remplace alors Lyon.
    """
    require_crs(con, communes, "EPSG:4326")
    exclude_lyon = f"where insee <> '{LYON}'" if arrondissements else ""
    con.execute(f"""
        create or replace table unites as
        select insee as code, 'commune' as niveau, {to_lambert93("geom")} as geom
        from ST_Read('{communes}') {exclude_lyon}""")
    if arrondissements:
        require_crs(con, arrondissements, LAMBERT93)
        con.execute(f"""
            insert into unites
            select insee, 'arrondissement_municipal', geom from ST_Read('{arrondissements}')""")
    return con.execute("select count(*) from unites").fetchone()[0]


def units_intersecting(
    con: duckdb.DuckDBPyConnection, zone: str, min_area_m2: float = MIN_INTERSECTION_M2
) -> list[str]:
    """Codes des unités dont l'intersection avec la zone dépasse `min_area_m2`."""
    rows = con.execute(
        f"""select u.code
            from unites u join z on z.code = ? and ST_Intersects(z.geom, u.geom)
            group by 1
            having sum(ST_Area(ST_Intersection(z.geom, u.geom))) > {min_area_m2}
            order by 1""",
        [zone],
    ).fetchall()
    return [r[0] for r in rows]


def without_public_position(
    con: duckdb.DuckDBPyConnection,
    sirene_ml: Path,
    units: list[str],
    activity_sql: str = "true",
) -> int:
    """Établissements actifs sans position publique dans `units`, filtrés par activité.

    Une unité est une commune (code commune COG 2026) ou un arrondissement de Lyon (code
    d'arrondissement) ; les deux jeux de codes sont disjoints. `activity_sql` est une
    condition SQL sur les colonnes de sirene_ml, écrite par le code appelant (jamais par une
    entrée utilisateur).
    """
    if not units:
        return 0
    placeholders = ", ".join("?" for _ in units)
    return con.execute(
        f"""select count(*) from read_parquet('{sirene_ml}')
            where etatAdministratifEtablissement = 'A' and not position_publique
              and (code_commune_cog2026 in ({placeholders})
                   or code_arrondissement in ({placeholders}))
              and ({activity_sql})""",
        units + units,
    ).fetchone()[0]


def zone_lower_bound(
    con: duckdb.DuckDBPyConnection, sirene_ml: Path, zone: str, activity_sql: str = "true"
) -> Minorant:
    """Minorant d'un comptage dans `zone` : périmètre = unités qui intersectent la zone."""
    units = units_intersecting(con, zone)
    n = without_public_position(con, sirene_ml, units, activity_sql)
    return Minorant(n=n, perimetre=f"{len(units)} unités géographiques qui intersectent {zone}")
