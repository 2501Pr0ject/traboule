"""Tirage de l'échantillon A : contrôle de l'indice de confiance (protocole d'évaluation, §2).

- population : établissements actifs rattachés à une seule zone (`etat = 'A'`,
  `categorie = 'une_zone'`), en trois strates par niveau de confiance ;
- ordre : `md5(siret || graine)` croissant dans chaque strate ; la graine est propre au
  tirage et obligatoire (ADR-0012) ;
- grille : rangs 1 à `per_stratum` de chaque strate ; remplacements : rangs suivants, dans
  un fichier masqué tant que le porteur ne les demande pas ;
- colonnes de tirage seulement ; les colonnes de revue restent vides (aucune pré-lecture).

La grille contient des SIRET et des adresses : elle reste locale (`data/interim/controles/`,
exclu de Git) et n'est jamais réécrite.

Usage : `uv run python -m traboule.evaluation.tirage --graine <graine>`.
"""

import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from traboule.config import INTERIM_DIR, RAW_DIR, ROOT

STRATA = ("haute", "moyenne", "faible")
PER_STRATUM = 10
REPLACEMENTS = 10
STOCK = "SRC-001a/2026-10-28/stock_etablissement/stock-stocketablissement-parquet.parquet"
GRID = "grille_confiance.csv"
MASKED = "remplacements_confiance.masque.csv"
META = "tirage_confiance.meta.json"
REVIEW_COLUMNS = (
    "zone_observee", "a_cheval", "statut", "cause", "methode", "relu_par_humain", "commentaire",
)  # fmt: skip
HEADER = (
    "rang",
    "strate",
    "siret",
    "adresse_declaree",
    "zone_jointure",
    "lien_gpu",
    *REVIEW_COLUMNS,
)
GPU_VIEWER = "https://www.geoportail-urbanisme.gouv.fr/map/#lon={lon:.6f}&lat={lat:.6f}&zoom=19"


class TirageError(RuntimeError):
    """Tirage refusé (graine absente, grille existante, strate incomplète)."""


def draw(
    con: duckdb.DuckDBPyConnection, zones: Path, seed: str, ranks: int = PER_STRATUM + REPLACEMENTS
) -> list[dict]:
    """Rangs 1 à `ranks` de chaque strate, dans l'ordre `md5(siret || graine)`."""
    if not seed:
        raise TirageError("graine obligatoire")
    order = "case strate when 'haute' then 1 when 'moyenne' then 2 else 3 end, rang"
    cur = con.execute(
        f"""with pop as (
              select siret, confiance as strate, zone as zone_jointure,
                     row_number() over (partition by confiance order by md5(siret || ?)) as rang
              from read_parquet(?)
              where etat = 'A' and categorie = 'une_zone'
            )
            select strate, rang, siret, zone_jointure from pop where rang <= ? order by {order}""",
        [seed, str(zones), ranks],
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    for strate in STRATA:
        if sum(r["strate"] == strate for r in rows) < ranks:
            raise TirageError(f"strate {strate} : moins de {ranks} établissements")
    return rows


def enrich(
    con: duckdb.DuckDBPyConnection, rows: list[dict], sirene_ml: Path, stock: Path
) -> list[dict]:
    """Ajoute l'adresse déclarée (stock SRC-001a) et le lien GPU (point de la géolocalisation)."""
    con.load_extension("spatial")
    sirets = [r["siret"] for r in rows]
    placeholders = ", ".join("?" for _ in sirets)
    found = con.execute(
        f"""select st.siret,
                   concat_ws(' ', st.numeroVoieEtablissement, st.indiceRepetitionEtablissement,
                             st.typeVoieEtablissement, st.libelleVoieEtablissement) as voie,
                   st.complementAdresseEtablissement as complement,
                   st.codePostalEtablissement as code_postal,
                   st.libelleCommuneEtablissement as commune,
                   ST_X(ST_Transform(ST_Point(s.x, s.y), 'EPSG:2154', 'EPSG:4326',
                                     always_xy := true)) as lon,
                   ST_Y(ST_Transform(ST_Point(s.x, s.y), 'EPSG:2154', 'EPSG:4326',
                                     always_xy := true)) as lat
            from read_parquet(?) st join read_parquet(?) s using (siret)
            where st.siret in ({placeholders})""",
        [str(stock), str(sirene_ml), *sirets],
    ).fetchall()
    by_siret = {r[0]: r[1:] for r in found}
    out = []
    for r in rows:
        voie, complement, code_postal, commune, lon, lat = by_siret[r["siret"]]
        town = f"{code_postal or ''} {commune or ''}".strip()
        adresse = ", ".join(x for x in (voie, complement, town) if x)
        out.append(
            r | {"adresse_declaree": adresse, "lien_gpu": GPU_VIEWER.format(lon=lon, lat=lat)}
        )
    return out


def write_grid(path: Path, rows: list[dict]) -> None:
    """Écrit une grille ; refuse de réécrire une grille existante."""
    if path.exists():
        raise TirageError(f"{path} existe déjà : tirage non réécrit")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        for r in rows:
            drawn = [r[c] for c in ("rang", "strate", "siret", "adresse_declaree", "zone_jointure")]
            writer.writerow([*drawn, r["lien_gpu"], *[""] * len(REVIEW_COLUMNS)])


def run(out_dir: Path, seed: str, zones: Path, sirene_ml: Path, stock: Path) -> dict:
    """Tirage complet : grille, remplacements masqués et métadonnées."""
    con = duckdb.connect()
    rows = enrich(con, draw(con, zones, seed), sirene_ml, stock)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_grid(out_dir / GRID, [r for r in rows if r["rang"] <= PER_STRATUM])
    write_grid(out_dir / MASKED, [r for r in rows if r["rang"] > PER_STRATUM])
    meta = {
        "protocole": "docs/evaluation/protocole.md, échantillon A",
        "graine": seed,
        "tire_le": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit_code": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "table": str(zones),
        "table_sha256": hashlib.sha256(zones.read_bytes()).hexdigest(),
        "table_produite_par": "uv run python -m traboule.geo.jointure",
        "population": "etat = 'A' et categorie = 'une_zone', strates par confiance",
        "ordre": f"md5(siret || '{seed}') croissant dans chaque strate",
        "grille": f"rangs 1 à {PER_STRATUM} par strate",
        "remplacements": f"rangs {PER_STRATUM + 1} à {PER_STRATUM + REPLACEMENTS} (masqués)",
        "produit_par": "uv run python -m traboule.evaluation.tirage",
    }
    (out_dir / META).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    return {s: sum(r["strate"] == s for r in rows) for s in STRATA}


app = typer.Typer(add_completion=False)


@app.command()
def main(
    graine: Annotated[str, typer.Option(help="Graine propre au tirage (obligatoire)")],
    out_dir: Annotated[Path, typer.Option(help="Dossier local des grilles")] = INTERIM_DIR
    / "controles",
) -> None:
    """Tire l'échantillon A et écrit la grille locale (colonnes de tirage seulement)."""
    try:
        counts = run(
            out_dir,
            graine,
            INTERIM_DIR / "etablissements_zones.parquet",
            INTERIM_DIR / "sirene_ml.parquet",
            RAW_DIR / STOCK,
        )
    except TirageError as exc:
        typer.echo(f"TIRAGE REFUSÉ : {exc}", err=True)
        sys.exit(1)
    typer.echo(f"OK : {counts} lignes tirées (grille et remplacements) dans {out_dir}")


if __name__ == "__main__":
    app()
