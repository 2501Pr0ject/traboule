"""Jointure spatiale établissements ↔ zonage du PLU-H (ADR-0002, ADR-0006 ; conventions §3, §4).

- seuls les établissements à position publique entrent dans la jointure : un statut `P`
  n'a aucune position (règle 10, déjà appliquée dans sirene_ml, revérifiée ici) ;
- source principale : géolocalisation INSEE ; coordonnées du stock en sensibilité ;
- catégories : `une_zone`, `multi_zones`, `aucune_zone`, `secteur_sauvegarde` (SECTSAUV) ;
- distance au polygone le plus proche d'une autre zone (rayon de recherche) et indice de
  confiance de l'ADR-0006 (geo.confiance).
Un résultat est une analyse de localisation, jamais un constat réglementaire.

Usage : `uv run python -m traboule.geo.jointure [--force]`.
"""

import sys
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from traboule.config import INTERIM_DIR, RAW_DIR, SEARCH_RADIUS_M
from traboule.geo.confiance import confiance_sql
from traboule.geo.crs import LAMBERT93, require_crs
from traboule.measure import measured, write_metrics

RAW_DATE = "2026-10-28"
ZONAGE = f"SRC-002/{RAW_DATE}/zonage/zonage.geojson"
OUTPUT = "etablissements_zones.parquet"
MEMORY_LIMIT = "6GB"
# Point de contrôle : place Bellecour (conventions §4), dans la zone UCe1b du zonage SRC-002.
BELLECOUR = (842395.13, 6519229.36, "UCe1b")
OUTPUT_COLUMNS = (
    "siret, etat, diffusion, code_commune_cog2026, code_arrondissement, qualite_xy, categorie, "
    "zone, famille, zone_stock, ecart_sources_m, dist_autre_zone_m, confiance"
)


class JointureError(RuntimeError):
    """Contrôle bloquant de la jointure."""


def _scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def load_zonage(con: duckdb.DuckDBPyConnection, path: Path) -> dict:
    """Table z(zid, code, kind, famille, geom) ; le CRS déclaré doit être EPSG:2154."""
    require_crs(con, path, LAMBERT93)
    con.execute(f"""
        create or replace table z as
        select OGC_FID as zid,
               coalesce(zonage, zone) as code,
               case when zone = 'SECTSAUV' then 'secteur_sauvegarde' else 'plu' end as kind,
               coalesce(regexp_extract(zonage, '^[A-Z]+'), zone) as famille,
               geom
        from ST_Read('{path}')""")
    if _scalar(con, "select count(*) from z where not ST_IsValid(geom)"):
        raise JointureError("géométries de zonage invalides")
    return {
        "objets": _scalar(con, "select count(*) from z"),
        "codes_distincts": _scalar(con, "select count(distinct code) from z"),
    }


def load_points(con: duckdb.DuckDBPyConnection, sirene_ml: Path) -> int:
    """Table p : établissements à position publique, point principal et point du stock."""
    con.execute(f"""
        create or replace table p as
        select siret, etatAdministratifEtablissement as etat,
               statutDiffusionEtablissement as diffusion,
               code_commune_cog2026, code_arrondissement, qualite_xy,
               ST_Point(x, y) as g,
               case when try_cast(coordonneeLambertAbscisseEtablissement as double) is not null
                     and try_cast(coordonneeLambertOrdonneeEtablissement as double) is not null
                    then ST_Point(try_cast(coordonneeLambertAbscisseEtablissement as double),
                                  try_cast(coordonneeLambertOrdonneeEtablissement as double))
               end as gs
        from read_parquet('{sirene_ml}')
        where position_publique and statutDiffusionEtablissement = 'O'""")
    return _scalar(con, "select count(*) from p")


def locate(con: duckdb.DuckDBPyConnection, point_col: str, table: str) -> None:
    """Table <table>(siret, n_codes, code, kind, famille) : zone(s) contenant le point."""
    con.execute(f"""
        create or replace table {table} as
        select p.siret, count(distinct z.code) as n_codes,
               case when count(distinct z.code) = 1 then any_value(z.code) end as code,
               case when count(distinct z.code) = 1 then any_value(z.kind) end as kind,
               case when count(distinct z.code) = 1 then any_value(z.famille) end as famille
        from p join z on ST_Contains(z.geom, p.{point_col})
        where p.{point_col} is not null
        group by 1""")


def classify(con: duckdb.DuckDBPyConnection) -> None:
    """Table etab : catégorie, zone principale, zone selon le stock, écart entre sources."""
    con.execute("""
        create or replace table etab as
        select p.siret, p.etat, p.diffusion, p.code_commune_cog2026, p.code_arrondissement,
               p.qualite_xy, p.g,
               case when m.siret is null then 'aucune_zone'
                    when m.n_codes > 1 then 'multi_zones'
                    when m.kind = 'secteur_sauvegarde' then 'secteur_sauvegarde'
                    else 'une_zone' end as categorie,
               case when m.n_codes = 1 then m.code end as zone,
               case when m.n_codes = 1 then m.famille end as famille,
               s.code as zone_stock,
               p.gs is not null as stock_present,
               case when p.gs is not null then ST_Distance(p.g, p.gs) end as ecart_sources_m
        from p left join main_zone m using (siret) left join stock_zone s using (siret)""")


def distance_and_confidence(con: duckdb.DuckDBPyConnection) -> None:
    """Table etab2 : distance à une autre zone (≤ rayon) et indice de confiance."""
    con.execute(f"""
        create or replace table dist_autre as
        select e.siret, min(ST_Distance(e.g, z.geom)) as d
        from etab e join z on ST_DWithin(e.g, z.geom, {SEARCH_RADIUS_M})
        where e.zone is not null and z.code <> e.zone
        group by 1""")
    con.execute(f"""
        create or replace table etab2 as
        select e.*, d.d as dist_autre_zone_m, {confiance_sql()} as confiance
        from etab e left join dist_autre d using (siret)""")


def build(con: duckdb.DuckDBPyConnection, sirene_ml: Path, zonage: Path) -> dict:
    """Jointure complète ; renvoie les mesures. La table finale est etab2."""
    result = {"zonage": load_zonage(con, zonage), "points": load_points(con, sirene_ml)}
    if _scalar(con, "select count(*) from p where diffusion <> 'O'"):
        raise JointureError("un établissement sans position publique est entré dans la jointure")
    locate(con, "g", "main_zone")
    locate(con, "gs", "stock_zone")
    classify(con)
    distance_and_confidence(con)
    total = _scalar(con, "select count(*) from etab2")
    if total != result["points"]:
        raise JointureError(f"{total} lignes classées pour {result['points']} points")
    cur = con.execute("select categorie, count(*) from etab2 group by 1 order by 1")
    result["categories"] = dict(cur.fetchall())
    cur = con.execute("select confiance, count(*) from etab2 group by 1 order by 1")
    result["confiance"] = {str(k): v for k, v in cur.fetchall()}
    return result


def write(con: duckdb.DuckDBPyConnection, out: Path) -> None:
    """Écrit etab2 dans out (fichier partiel renommé à la fin)."""
    partial = out.with_name(out.name + ".partial")
    con.execute(f"copy (select {OUTPUT_COLUMNS} from etab2) to '{partial}' (format parquet)")
    partial.replace(out)


app = typer.Typer(add_completion=False)


@app.command()
def main(
    force: Annotated[bool, typer.Option(help="Écraser le Parquet existant")] = False,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    interim_dir: Annotated[Path, typer.Option(help="Dossier des données dérivées")] = INTERIM_DIR,
) -> None:
    """Rattache chaque établissement à position publique à sa zone du PLU-H."""
    out = interim_dir / OUTPUT
    if out.exists() and not force:
        typer.echo(f"{out} existe : relancer avec --force.", err=True)
        sys.exit(1)
    con = duckdb.connect()
    con.execute(f"set memory_limit = '{MEMORY_LIMIT}'")
    con.load_extension("spatial")
    steps: dict = {}
    try:
        with measured(steps, "jointure"):
            result = build(con, interim_dir / "sirene_ml.parquet", raw_dir / ZONAGE)
            x, y, expected = BELLECOUR
            found = _scalar(con, f"select code from z where ST_Contains(geom, ST_Point({x}, {y}))")
            if found != expected:
                raise JointureError(f"point de contrôle Bellecour → {found}, attendu {expected}")
            write(con, out)
    except JointureError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    write_metrics(
        interim_dir / "metrics" / "jointure.json",
        {"steps": steps, **result},
        {"raw_date": RAW_DATE, "memory_limit": MEMORY_LIMIT, "rayon_m": SEARCH_RADIUS_M},
    )
    typer.echo(f"OK : {result['points']} points, {result['confiance']}")


if __name__ == "__main__":
    app()
