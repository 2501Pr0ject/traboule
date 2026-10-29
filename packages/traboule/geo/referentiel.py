"""Référentiel géographique : communes de la Métropole (COG 2026), arrondissements de Lyon,
passage des codes historiques vers le COG 2026 (conventions §3, règles 4 à 6).

Entrées (SRC-004a, SRC-004b, SRC-004c), lues en tables DuckDB par `load_inputs` :
- `cog` (v_commune_2026) : TYPECOM, COM, LIBELLE, COMPARENT ;
- `mvt` (v_mvt_commune_2026) : TYPECOM_AV, COM_AV, TYPECOM_AP, COM_AP, DATE_EFF, MOD ;
- `appart_com` / `appart_arm` (table d'appartenance, onglets COM et ARM) : CODGEO, COM, EPCI ;
- `passage_src` (table de passage 2003 → 2026) : CODGEO_INI, CODGEO_2026.
Aucun code commune en dur : l'EPCI, le code de Lyon et les effectifs attendus viennent de
configs/sources.yaml.

Usage : `uv run python -m traboule.geo.referentiel [--force]`.
"""

import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from traboule.config import INTERIM_DIR, RAW_DIR, load_sources
from traboule.measure import measured, write_metrics

RAW_DATE = "2026-10-28"
ARCHIVES = {
    "SRC-004a": f"SRC-004a/{RAW_DATE}/cog_ensemble/cog_ensemble_2026_csv.zip",
    "SRC-004b": f"SRC-004b/{RAW_DATE}/table_appartenance/table-appartenance-geo-communes-2026.zip",
    "SRC-004c": (f"SRC-004c/{RAW_DATE}/table_passage_2003_2026/table_passage_geo2003_geo2026.zip"),
}
OUTPUTS = ("ref_communes_ml", "ref_arrondissements_lyon", "passage_communes")


class ReferentielError(RuntimeError):
    """Contrôle bloquant du référentiel."""


@dataclass(frozen=True)
class Territory:
    """Territoire attendu, lu dans configs/sources.yaml."""

    epci: str
    lyon: str
    communes_count: int
    arrondissements: tuple[str, ...]

    @classmethod
    def from_config(cls, config: dict) -> "Territory":
        t = config["metadata"]["territory"]
        return cls(
            epci=t["epci_code"],
            lyon=t["lyon_commune_code"],
            communes_count=t["communes_count_cog_2026"],
            arrondissements=tuple(t["lyon_arrondissements"]),
        )


def _scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def _xlsx(path: Path, sheet: str, cols: str = "Z") -> str:
    # En-tête des classeurs INSEE en ligne 6.
    return (
        f"read_xlsx('{path}', sheet='{sheet}', range='A6:{cols}200000', "
        "header=true, all_varchar=true)"
    )


def extract_archives(raw_dir: Path, dest_root: Path) -> dict[str, Path]:
    """Décompresse les archives SRC-004* dans dest_root/<source_id>/ (données dérivées)."""
    extracted = {}
    for source_id, rel in ARCHIVES.items():
        dest = dest_root / source_id
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        with zipfile.ZipFile(raw_dir / rel) as zf:
            zf.extractall(dest)
        extracted[source_id] = dest
    return extracted


def load_inputs(con: duckdb.DuckDBPyConnection, src: dict[str, Path]) -> None:
    """Crée les vues d'entrée à partir des fichiers INSEE décompressés."""
    con.load_extension("excel")
    appart = next(src["SRC-004b"].glob("*.xlsx"))
    passage = next(src["SRC-004c"].glob("*.xlsx"))
    con.execute(
        "create or replace view cog as select * from "
        f"read_csv('{src['SRC-004a'] / 'v_commune_2026.csv'}', all_varchar=true)"
    )
    con.execute(
        "create or replace view mvt as select * from "
        f"read_csv('{src['SRC-004a'] / 'v_mvt_commune_2026.csv'}', all_varchar=true)"
    )
    con.execute(f"create or replace view appart_com as select * from {_xlsx(appart, 'COM')}")
    con.execute(f"create or replace view appart_arm as select * from {_xlsx(appart, 'ARM')}")
    con.execute(
        "create or replace view passage_src as select * from "
        f"{_xlsx(passage, 'Table de passage', 'C')}"
    )


def build_communes(con: duckdb.DuckDBPyConnection, territory: Territory) -> int:
    """Table ref_communes_ml : communes de l'EPCI au COG 2026, jointes par code."""
    con.execute(f"""
        create or replace table ref_communes_ml as
        select a.CODGEO as code_commune, c.LIBELLE as libelle, a.EPCI as epci,
               2026 as cog_millesime, 'commune' as niveau
        from appart_com a
        join cog c on c.TYPECOM = 'COM' and c.COM = a.CODGEO
        where a.EPCI = '{territory.epci}'
        order by 1""")
    n = _scalar(con, "select count(*) from ref_communes_ml")
    if n != territory.communes_count:
        raise ReferentielError(f"{n} communes dans l'EPCI (attendu {territory.communes_count})")
    if not _scalar(
        con, f"select count(*) from ref_communes_ml where code_commune = '{territory.lyon}'"
    ):
        raise ReferentielError(f"Lyon ({territory.lyon}) absente des communes de l'EPCI")
    return n


def build_arrondissements(con: duckdb.DuckDBPyConnection, territory: Territory) -> int:
    """Table ref_arrondissements_lyon : subdivisions de Lyon, jamais des communes (règle 5)."""
    con.execute(f"""
        create or replace table ref_arrondissements_lyon as
        select c.COM as code_arrondissement, c.LIBELLE as libelle,
               c.COMPARENT as code_commune_parent, 2026 as cog_millesime,
               'arrondissement_municipal' as niveau
        from cog c where c.TYPECOM = 'ARM' and c.COMPARENT = '{territory.lyon}'
        order by 1""")
    codes = tuple(
        r[0]
        for r in con.execute("select code_arrondissement from ref_arrondissements_lyon").fetchall()
    )
    if codes != territory.arrondissements:
        raise ReferentielError(f"arrondissements {codes} ≠ attendus {territory.arrondissements}")
    in_epci = _scalar(
        con,
        f"""select count(*) from appart_arm a
            join ref_arrondissements_lyon r on r.code_arrondissement = a.CODGEO
            where a.COM = '{territory.lyon}' and a.EPCI = '{territory.epci}'""",
    )
    if in_epci != len(codes):
        raise ReferentielError("arrondissements discordants avec l'onglet ARM (EPCI, parent)")
    return len(codes)


def build_passage(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Table passage_communes : code source (commune historique ou arrondissement) → COG 2026.

    Renvoie les codes historiques (code source ≠ code 2026) avec leur date d'effet.
    """
    con.execute("""
        create or replace table passage_communes as
        with p as (
            select CODGEO_INI as code_source, CODGEO_2026 as code_cog_2026
            from passage_src
            where CODGEO_2026 in (select code_commune from ref_communes_ml)
        ),
        m as (
            select COM_AV, COM_AP, min(DATE_EFF) as date_effet,
                   string_agg(distinct MOD, ',') as mod
            from mvt where TYPECOM_AV = 'COM' and TYPECOM_AP = 'COM'
            group by all
        )
        select p.code_source, 'commune' as niveau_source, p.code_cog_2026,
               null::varchar as code_arrondissement_2026,
               m.date_effet, m.mod as type_mouvement, 'SRC-004c + v_mvt_commune_2026' as source
        from p left join m on m.COM_AV = p.code_source and m.COM_AP = p.code_cog_2026
                          and p.code_source <> p.code_cog_2026
        union all
        select code_arrondissement, 'arrondissement_municipal', code_commune_parent,
               code_arrondissement, null, null, 'SRC-004a (ARM)'
        from ref_arrondissements_lyon
        order by 1""")
    ambiguous = con.execute(
        """select code_source from passage_communes
           group by 1 having count(distinct code_cog_2026) > 1"""
    ).fetchall()
    if ambiguous:
        raise ReferentielError(f"code(s) source ambigu(s) : {[r[0] for r in ambiguous]}")
    cur = con.execute(
        """select code_source, code_cog_2026, date_effet, type_mouvement from passage_communes
           where niveau_source = 'commune' and code_source <> code_cog_2026 order by 1"""
    )
    cols = [d[0] for d in cur.description]
    historical = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    missing = [h["code_source"] for h in historical if not h["date_effet"]]
    if missing:
        raise ReferentielError(f"date d'effet introuvable pour {missing}")
    return historical


def build(con: duckdb.DuckDBPyConnection, territory: Territory) -> dict:
    """Construit les trois tables à partir des vues d'entrée et renvoie les mesures."""
    return {
        "communes": build_communes(con, territory),
        "arrondissements": build_arrondissements(con, territory),
        "codes_historiques": build_passage(con),
        "lignes_passage": _scalar(con, "select count(*) from passage_communes"),
    }


app = typer.Typer(add_completion=False)


@app.command()
def main(
    force: Annotated[bool, typer.Option(help="Écraser les Parquet existants")] = False,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    interim_dir: Annotated[Path, typer.Option(help="Dossier des données dérivées")] = INTERIM_DIR,
) -> None:
    """Construit ref_communes_ml, ref_arrondissements_lyon et passage_communes."""
    existing = [n for n in OUTPUTS if (interim_dir / f"{n}.parquet").exists()]
    if existing and not force:
        typer.echo(f"Sorties existantes {existing} : relancer avec --force.", err=True)
        sys.exit(1)
    territory = Territory.from_config(load_sources())
    steps: dict = {}
    con = duckdb.connect()
    try:
        with measured(steps, "extraction"):
            src = extract_archives(raw_dir, interim_dir / "sources")
        with measured(steps, "construction"):
            load_inputs(con, src)
            result = build(con, territory)
            for name in OUTPUTS:
                con.execute(f"copy {name} to '{interim_dir / name}.parquet' (format parquet)")
    except ReferentielError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    write_metrics(
        interim_dir / "metrics" / "referentiel.json",
        {"steps": steps, **result},
        {"raw_date": RAW_DATE, "epci": territory.epci},
    )
    typer.echo(
        f"OK : {result['communes']} communes, {result['arrondissements']} arrondissements, "
        f"{result['lignes_passage']} lignes de passage"
    )


if __name__ == "__main__":
    app()
