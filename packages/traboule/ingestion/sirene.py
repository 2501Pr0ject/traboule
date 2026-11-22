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

import json
import sys
from datetime import date as Date
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from traboule.config import INTERIM_DIR, RAW_DIR
from traboule.ingestion.raw import DATE_HELP, MANIFEST, RawDataError, resource_file, used
from traboule.measure import measured, write_metrics

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


def manifest_month(data_file: Path) -> str | None:
    """Mois (AAAA-MM) d'un fichier Sirene : date de référence, sinon de publication."""
    path = data_file.parent / MANIFEST
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    day = manifest.get("reference_date") or manifest.get("published_at")
    return str(day)[:7] if day else None


def check_pairing(stock: Path, geoloc: Path, raw_dir: Path = RAW_DIR) -> str:
    """Contrôle bloquant : stock (SRC-001a) et géolocalisation (SRC-001b) du même mois.

    La géolocalisation d'un mois correspond au stock du 1er de ce mois (registre, SRC-001) ;
    deux mois différents ne décrivent pas le même état du répertoire. Renvoie le mois.
    """
    months = {"SRC-001a": manifest_month(stock), "SRC-001b": manifest_month(geoloc)}
    files = {"SRC-001a": used(stock, raw_dir), "SRC-001b": used(geoloc, raw_dir)}
    if None in months.values():
        unknown = [s for s, m in months.items() if m is None]
        raise SireneError(f"mois inconnu pour {unknown} : manifeste absent ou sans date")
    if months["SRC-001a"] == months["SRC-001b"]:
        return months["SRC-001a"]
    older = min(months, key=months.get)
    raise SireneError(
        f"stock SRC-001a de {months['SRC-001a']} ({files['SRC-001a']}) et géolocalisation "
        f"SRC-001b de {months['SRC-001b']} ({files['SRC-001b']}) : mois différents, appariement "
        f"impossible. Retélécharger la version courante de {older} : `uv run python -m "
        f"traboule.ingestion.download {older} --date {Date.today().isoformat()}` (la "
        "géolocalisation d'un mois paraît en fin de mois), ou lire une paire du même mois "
        "avec --date."
    )


def stock_path(date: str | None = None, raw_dir: Path = RAW_DIR) -> Path:
    """Stock Sirene des établissements (SRC-001a), dossier daté résolu par `ingestion.raw`."""
    return resource_file("SRC-001a", "stock_etablissement", date, raw_dir, "*.parquet")


def geoloc_path(date: str | None = None, raw_dir: Path = RAW_DIR) -> Path:
    """Géolocalisation des établissements (SRC-001b)."""
    return resource_file("SRC-001b", "geolocalisation", date, raw_dir, "*.parquet")


app = typer.Typer(add_completion=False)


@app.command()
def main(
    force: Annotated[bool, typer.Option(help="Écraser le Parquet existant")] = False,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    interim_dir: Annotated[Path, typer.Option(help="Dossier des données dérivées")] = INTERIM_DIR,
    date: Annotated[str | None, typer.Option("--date", help=DATE_HELP)] = None,
) -> None:
    """Filtre le stock Sirene sur la Métropole et le joint à la géolocalisation."""
    try:
        stock, geoloc = stock_path(date, raw_dir), geoloc_path(date, raw_dir)
        month = check_pairing(stock, geoloc, raw_dir)
    except RawDataError as exc:
        typer.echo(f"ERREUR : {exc}", err=True)
        sys.exit(1)
    except SireneError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
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
            result = build_sirene_ml(con, stock, geoloc, out)
    except SireneError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    write_metrics(
        interim_dir / "metrics" / "sirene.json",
        {"steps": steps, **result},
        {
            "donnees_brutes": [used(stock, raw_dir), used(geoloc, raw_dir)],
            "mois": month,
            "memory_limit": MEMORY_LIMIT,
        },  # fmt: skip
    )
    typer.echo(f"OK : {result}")


if __name__ == "__main__":
    app()
