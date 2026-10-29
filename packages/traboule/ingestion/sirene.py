"""Établissements Sirene de la Métropole : stock SRC-001a filtré en streaming + géolocalisation
SRC-001b (ADR-0003, ADR-0006 ; conventions §1, §3).

- rattachement au COG 2026 par la table `passage_communes` (geo.referentiel), sur le code ;
- géolocalisation limitée à `epsg = '2154'` ;
- règle 10 : un établissement en statut `P` dans le stock n'a aucune position. Ses
  coordonnées éventuelles (géolocalisation ou stock) sont mises à null ; `geoloc_present`
  garde le fait brut (présent dans le fichier de géolocalisation) pour le registre.
- `position_publique` = présent dans la géolocalisation et statut `O`.

Usage : `uv run python -m traboule.ingestion.sirene [--force]`.
"""

import sys
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from traboule.config import INTERIM_DIR, RAW_DIR
from traboule.measure import measured, write_metrics

RAW_DATE = "2026-10-28"
STOCK = f"SRC-001a/{RAW_DATE}/stock_etablissement/stock-stocketablissement-parquet.parquet"
GEOLOC = (
    f"SRC-001b/{RAW_DATE}/geolocalisation/"
    "geoloc-geolocalisationetablissement-sirene-pour-etudes-statistiques-parquet.parquet"
)
OUTPUT = "sirene_ml.parquet"
MEMORY_LIMIT = "6GB"


class SireneError(RuntimeError):
    """Contrôle bloquant du filtrage Sirene."""


def _scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def build_sirene_ml(con: duckdb.DuckDBPyConnection, stock: Path, geoloc: Path, out: Path) -> dict:
    """Écrit out (Parquet) si les contrôles passent ; `passage_communes` doit exister dans con."""
    partial = out.with_name(out.name + ".partial")
    public = "s.statutDiffusionEtablissement = 'O'"
    con.execute(f"""
        copy (
            with g as (
                select siret, x, y, qualite_xy, plg_code_commune, plg_iris, distance_precision
                from read_parquet('{geoloc}') where epsg = '2154'
            )
            select s.siret, s.siren, s.nic, s.etablissementSiege, s.statutDiffusionEtablissement,
                   s.etatAdministratifEtablissement, s.dateCreationEtablissement, s.dateDebut,
                   s.dateDernierTraitementEtablissement, s.activitePrincipaleEtablissement,
                   s.nomenclatureActivitePrincipaleEtablissement,
                   s.activitePrincipaleNAF25Etablissement, s.trancheEffectifsEtablissement,
                   s.caractereEmployeurEtablissement, s.codeCommuneEtablissement,
                   case when {public} then s.coordonneeLambertAbscisseEtablissement end
                       as coordonneeLambertAbscisseEtablissement,
                   case when {public} then s.coordonneeLambertOrdonneeEtablissement end
                       as coordonneeLambertOrdonneeEtablissement,
                   p.code_cog_2026 as code_commune_cog2026,
                   p.code_arrondissement_2026 as code_arrondissement,
                   case when {public} then g.x end as x,
                   case when {public} then g.y end as y,
                   case when {public} then g.qualite_xy end as qualite_xy,
                   case when {public} then g.plg_code_commune end as plg_code_commune,
                   case when {public} then g.plg_iris end as plg_iris,
                   case when {public} then g.distance_precision end as distance_precision,
                   g.siret is not null as geoloc_present,
                   g.siret is not null and {public} as position_publique
            from read_parquet('{stock}') s
            join passage_communes p on p.code_source = s.codeCommuneEtablissement
            left join g using (siret)
        ) to '{partial}' (format parquet, compression zstd)""")
    view = f"read_parquet('{partial}')"
    try:
        statuts = {
            r[0]
            for r in con.execute(
                f"select distinct statutDiffusionEtablissement from {view}"
            ).fetchall()
        }
        if not statuts <= {"O", "P"}:
            raise SireneError(
                f"statut(s) de diffusion inattendu(s) : {sorted(statuts - {'O', 'P'})}"
            )
        if _scalar(con, f"select count(*) - count(distinct siret) from {view}"):
            raise SireneError("SIRET en double")
        if _scalar(
            con, f"select count(*) from {view} where not position_publique and x is not null"
        ):
            raise SireneError("coordonnées présentes sans position publique")
        result = {
            "lignes": _scalar(con, f"select count(*) from {view}"),
            "statut_p_presents_dans_geolocalisation": _scalar(
                con,
                f"select count(*) from {view} where statutDiffusionEtablissement = 'P' "
                "and geoloc_present",
            ),
            "position_publique": _scalar(
                con, f"select count(*) from {view} where position_publique"
            ),
        }
    except SireneError:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(out)
    return result


app = typer.Typer(add_completion=False)


@app.command()
def main(
    force: Annotated[bool, typer.Option(help="Écraser le Parquet existant")] = False,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    interim_dir: Annotated[Path, typer.Option(help="Dossier des données dérivées")] = INTERIM_DIR,
) -> None:
    """Filtre le stock Sirene sur la Métropole et le joint à la géolocalisation."""
    out = interim_dir / OUTPUT
    if out.exists() and not force:
        typer.echo(f"{out} existe : relancer avec --force.", err=True)
        sys.exit(1)
    tmp = interim_dir / ".duckdb_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"set memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"set temp_directory = '{tmp}'")
    passage = interim_dir / "passage_communes.parquet"
    con.execute(f"create table passage_communes as select * from read_parquet('{passage}')")
    steps: dict = {}
    try:
        with measured(steps, "sirene_ml"):
            result = build_sirene_ml(con, raw_dir / STOCK, raw_dir / GEOLOC, out)
    except SireneError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    write_metrics(
        interim_dir / "metrics" / "sirene.json",
        {"steps": steps, **result},
        {"raw_date": RAW_DATE, "memory_limit": MEMORY_LIMIT},
    )
    typer.echo(f"OK : {result}")


if __name__ == "__main__":
    app()
