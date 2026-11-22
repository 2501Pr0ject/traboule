"""Base DuckDB locale documentée : data/processed/traboule.duckdb (conventions §3, règles 5, 6).

Chaque table est construite depuis sa source (Parquet de data/interim, fichiers bruts, CSV
de correspondance), ses colonnes sont confrontées au catalogue (`traboule.catalogue`), et
elle reçoit ses commentaires `COMMENT ON TABLE` / `COMMENT ON COLUMN`. Les tables `_catalogue`
et `_sources` décrivent la base et les ressources téléchargées. La base contient des SIRET :
elle reste locale (`*.duckdb` exclu de Git). Elle est écrite dans un fichier partiel, renommé
seulement si tous les contrôles passent.

Usage : `uv run python -m traboule.ingestion.database [--force]`.
"""

import json
import sys
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from traboule.catalogue import META_TABLES, TABLES, Table
from traboule.config import INTERIM_DIR, RAW_DIR, ROOT
from traboule.contracts.etablissement import LYON
from traboule.geo.crs import LAMBERT93, require_crs
from traboule.geo.jointure import zonage_path
from traboule.geo.minorant import load_units
from traboule.ingestion.raw import (
    DATE_HELP,
    RawDataError,
    data_files,
    reference_date,
    resource_file,
)
from traboule.ingestion.sirene import SireneError, check_pairing, geoloc_path, stock_path
from traboule.measure import measured, write_metrics

OUTPUT = Path("data/processed/traboule.duckdb")
ZONES_REGLEMENT = ROOT / "configs" / "zones_reglement.csv"
PARQUETS = {
    "communes": "ref_communes_ml",
    "arrondissements": "ref_arrondissements_lyon",
    "passage_communes": "passage_communes",
    "etablissements": "sirene_ml",
    "etablissements_zones": "etablissements_zones",
}


class DatabaseError(RuntimeError):
    """Contrôle bloquant de la construction de la base."""


@dataclass(frozen=True)
class Inputs:
    """Emplacements des sources de la base."""

    interim_dir: Path
    zonage: Path
    communes: Path
    arrondissements: Path
    zones_reglement: Path
    raw_dir: Path
    # Millésimes des tables tirés des données réellement lues (sinon ceux du catalogue).
    millesimes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def default(
        cls, interim_dir: Path = INTERIM_DIR, raw_dir: Path = RAW_DIR, date: str | None = None
    ) -> "Inputs":
        """Dossiers datés résolus par `ingestion.raw` (référence, sinon le plus récent)."""
        zonage = zonage_path(date, raw_dir)
        arrondissements = resource_file(
            "REF-ARRONDISSEMENTS-LYON", "arrondissements", date, raw_dir, "*.geojson"
        )
        return cls(
            interim_dir=interim_dir,
            zonage=zonage,
            communes=resource_file("REF-COMMUNES-ML-2024", "communes", date, raw_dir, "*.geojson"),
            arrondissements=arrondissements,
            zones_reglement=ZONES_REGLEMENT,
            raw_dir=raw_dir,
            millesimes=millesimes(
                sirene_month(interim_dir, date, raw_dir),
                zonage.parent.parent.name,
                arrondissements.parent.parent.name,
                zonage.parent.parent.name == reference_date("SRC-002", "zonage"),
            ),
        )


MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
          "octobre", "novembre", "décembre")  # fmt: skip


def month_label(month: str) -> str:
    """`2026-10` → « d'octobre 2026 » ; `2026-11` → « de novembre 2026 »."""
    name = MONTHS[int(month[5:7]) - 1]
    return ("d'" if name[0] in "aeiouéâ" else "de ") + f"{name} {month[:4]}"


def sirene_month(interim_dir: Path, date: str | None, raw_dir: Path) -> str:
    """Mois de la paire Sirene qui a construit sirene_ml (mesures, sinon manifestes)."""
    metrics = interim_dir / "metrics" / "sirene.json"
    if metrics.exists():
        month = json.loads(metrics.read_text(encoding="utf-8")).get("config", {}).get("mois")
        if month:
            return month
    try:
        return check_pairing(stock_path(date, raw_dir), geoloc_path(date, raw_dir), raw_dir)
    except SireneError as exc:
        raise DatabaseError(str(exc)) from exc


def millesimes(stock_month: str, zonage_day: str, arrondissements_day: str,
               reference_zonage: bool) -> dict[str, str]:  # fmt: skip
    """Millésimes des tables construites depuis Sirene, le zonage et les arrondissements.

    Le stock Sirene d'un mois décrit le répertoire au 1er de ce mois ; la version opposable du
    zonage n'est affirmée que pour le zonage de référence.
    """
    stock = f"stock Sirene du {stock_month}-01"
    zonage = f"zonage téléchargé le {zonage_day}"
    return {
        "etablissements": (
            f"{stock} ; géolocalisation {month_label(stock_month)} ; communes au COG 2026"
        ),
        "etablissements_zones": f"{stock} × {zonage}",
        "zonage": zonage
        + (" (version opposable 200046977_PLUi_20260326)" if reference_zonage else ""),  # fmt: skip
        "unites": (
            "communes 2024 (référentiel adr_voie_lieu, 58 communes) ; arrondissements "
            f"téléchargés le {arrondissements_day}"
        ),
    }


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def load_tables(con: duckdb.DuckDBPyConnection, inputs: Inputs) -> None:
    """Crée les tables de données depuis leurs sources."""
    for name, parquet in PARQUETS.items():
        path = inputs.interim_dir / f"{parquet}.parquet"
        con.execute(f"create table {name} as select * from read_parquet({_quote(str(path))})")
    require_crs(con, inputs.zonage, LAMBERT93)
    con.execute(f"""
        create table zonage as
        select OGC_FID as zid,
               coalesce(zonage, zone) as code,
               case when zone = 'SECTSAUV' then 'secteur_sauvegarde' else 'plu' end as kind,
               coalesce(regexp_extract(zonage, '^[A-Z]+'), zone) as famille,
               stecal, plafond, ces, ces_bande_principale, ces_bande_secondaire, cpt,
               cpt_bande_principale, cpt_bande_secondaire, hauteur_bande_principale,
               hauteur_bande_secondaire, last_update, geom
        from ST_Read({_quote(str(inputs.zonage))})""")
    load_units(con, inputs.communes, inputs.arrondissements)
    con.execute(
        "create table zones_reglement as select * from read_csv("
        f"{_quote(str(inputs.zones_reglement))}, header = true)"
    )


def check_columns(con: duckdb.DuckDBPyConnection, entry: Table) -> None:
    """Les colonnes de la table sont exactement celles du catalogue, dans l'ordre."""
    found = [r[0] for r in con.execute(f"describe {entry.name}").fetchall()]
    expected = [c.name for c in entry.columns]
    if found != expected:
        missing, extra = sorted(set(expected) - set(found)), sorted(set(found) - set(expected))
        raise DatabaseError(f"{entry.name} : colonnes hors catalogue {extra}, absentes {missing}")


def check_geographic_levels(con: duckdb.DuckDBPyConnection) -> None:
    """Règle 5 : Lyon et ses arrondissements ne sont ni additionnés ni confondus."""
    if _scalar(con, "select count(*) from communes where code_commune like '6938%'"):
        raise DatabaseError("un arrondissement figure dans la table communes")
    if _scalar(
        con, "select count(*) from arrondissements where code_arrondissement not like '6938%'"
    ):
        raise DatabaseError("un code qui n'est pas un arrondissement figure dans arrondissements")
    both = _scalar(
        con,
        f"""select count(*) filter (where code = '{LYON}') > 0
                   and count(*) filter (where niveau = 'arrondissement_municipal') > 0
            from unites""",
    )
    if both:
        raise DatabaseError("unites contient à la fois Lyon (69123) et ses arrondissements")


def comment(con: duckdb.DuckDBPyConnection, entry: Table) -> None:
    """Commentaires de table (rôle, niveau, millésime, sources, avertissement) et de colonnes."""
    text = (
        f"{entry.description} Niveau : {entry.niveau}. Millésime : {entry.millesime}. "
        f"Sources : {', '.join(entry.sources) or '—'}."
    )
    if entry.avertissement:
        text += f" {entry.avertissement}"
    con.execute(f"comment on table {entry.name} is {_quote(text)}")
    for col in entry.columns:
        con.execute(f'comment on column {entry.name}."{col.name}" is {_quote(col.description)}')


def write_meta(
    con: duckdb.DuckDBPyConnection, raw_dir: Path, built_at: str, tables: tuple = TABLES
) -> None:
    """Tables _catalogue et _sources."""
    con.execute("""create table _catalogue (nom varchar, description varchar, niveau varchar,
                   millesime varchar, sources varchar[], produite_par varchar,
                   avertissement varchar, lignes bigint, construite_le varchar)""")
    for t in tables:
        con.execute(
            "insert into _catalogue values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [t.name, t.description, t.niveau, t.millesime, list(t.sources), t.produite_par,
             t.avertissement, _scalar(con, f"select count(*) from {t.name}"), built_at],
        )  # fmt: skip
    con.execute("""create table _sources (source_id varchar, ressource varchar, source_url varchar,
                   sha256 varchar, retrieved_at varchar, licence varchar)""")
    for path in sorted(raw_dir.glob("*/*/*/manifest.json")):
        if not data_files(path.parent):
            continue  # manifeste de référence sans données (clone neuf, ressource modifiée)
        m = json.loads(path.read_text(encoding="utf-8"))
        ressource = f"{path.parent.parent.name}/{path.parent.name}"
        con.execute(
            "insert into _sources values (?, ?, ?, ?, ?, ?)",
            [m["source_id"], ressource, m["source_url"], m["sha256"], m["retrieved_at"],
             m["license"]],
        )  # fmt: skip
    for meta in META_TABLES:
        check_columns(con, meta)
        comment(con, meta)


def build_database(out: Path, inputs: Inputs) -> dict:
    """Construit la base dans un fichier partiel, contrôle, puis renomme. Renvoie les lignes."""
    partial = out.with_name(out.name + ".partial")
    partial.unlink(missing_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(partial))
    try:
        con.load_extension("spatial")
        load_tables(con, inputs)
        tables = tuple(replace(t, millesime=inputs.millesimes.get(t.name, t.millesime))
                       for t in TABLES)  # fmt: skip
        for entry in tables:
            check_columns(con, entry)
            comment(con, entry)
        check_geographic_levels(con)
        write_meta(con, inputs.raw_dir, datetime.now(UTC).isoformat(timespec="seconds"), tables)
        counts = dict(con.execute("select nom, lignes from _catalogue order by nom").fetchall())
        counts["_sources"] = _scalar(con, "select count(*) from _sources")
    except Exception:
        con.close()
        partial.unlink(missing_ok=True)
        raise
    con.close()
    partial.replace(out)
    return counts


app = typer.Typer(add_completion=False)


@app.command()
def main(
    force: Annotated[bool, typer.Option(help="Écraser la base existante")] = False,
    out: Annotated[Path, typer.Option(help="Fichier DuckDB")] = ROOT / OUTPUT,
    date: Annotated[str | None, typer.Option("--date", help=DATE_HELP)] = None,
) -> None:
    """Construit data/processed/traboule.duckdb depuis les sources et le catalogue."""
    try:
        inputs = Inputs.default(date=date)
    except RawDataError as exc:
        typer.echo(f"ERREUR : {exc}", err=True)
        sys.exit(1)
    except DatabaseError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    if out.exists() and not force:
        typer.echo(f"{out} existe : relancer avec --force.", err=True)
        sys.exit(1)
    steps: dict = {}
    try:
        with measured(steps, "base"):
            counts = build_database(out, inputs)
    except DatabaseError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    write_metrics(
        INTERIM_DIR / "metrics" / "database.json",
        {"steps": steps, "lignes": counts},
        {"tables": [t.name for t in TABLES], "sortie": str(OUTPUT)},
    )
    typer.echo(f"OK : {counts}")


if __name__ == "__main__":
    app()
