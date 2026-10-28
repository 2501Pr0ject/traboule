"""Test 2 : tirage du cas de remplacement de la validation (rang suivant, même graine).

Script jetable. Règle décidée le 2026-10-28, après la vérification des contrôles #2, #8,
#9, #10 : un contrôle de validation indéterminable est remplacé par le rang suivant de la
séquence de tirage. Vérifie que les rangs 1 à 10 redonnent la grille existante, signale si
le rang tiré figure déjà dans l'échantillon d'arbitrage, puis ajoute une ligne à
controles.csv (local). N'affiche ni adresse ni SIRET.
"""

import csv
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

import duckdb
import typer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "spikes" / "output" / "test2"
CONTROLS = OUTPUT_DIR / "controles.csv"
ZONES = ROOT / "data" / "interim" / "etablissements_zones.parquet"
SIRENE_ML = ROOT / "data" / "interim" / "sirene_ml.parquet"
STOCK = (
    ROOT
    / "data/raw/SRC-001a/2026-10-28/stock_etablissement/stock-stocketablissement-parquet.parquet"
)
SEED = 20261028
GPU_VIEWER = "https://www.geoportail-urbanisme.gouv.fr/map/#lon={lon:.6f}&lat={lat:.6f}&zoom=19"
TOLERANCE_DEG = 1e-5

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


def link_point(link: str) -> tuple[float, float] | None:
    if not link:
        return None
    fragment = parse_qs(urlsplit(link).fragment)
    return float(fragment["lon"][0]), float(fragment["lat"][0])


def same_point(a: tuple[float, float], b: tuple[float, float] | None) -> bool:
    return b is not None and abs(a[0] - b[0]) < TOLERANCE_DEG and abs(a[1] - b[1]) < TOLERANCE_DEG


@app.command()
def main(rank: Annotated[int, typer.Option(help="Rang à tirer dans la séquence")] = 11) -> None:
    """Tire le rang demandé de la séquence de validation et l'ajoute à la grille."""
    con = duckdb.connect()
    con.load_extension("spatial")
    seq = con.execute(
        f"""select e.siret, e.code_commune_cog2026, e.code_arrondissement, e.zone, e.zone_stock,
                   round(e.ecart_sources_m, 1) ecart, e.qualite_xy,
                   round(e.dist_autre_zone_m, 1) dist, e.confiance,
                   ST_X(ST_Transform(ST_Point(s.x, s.y), 'EPSG:2154', 'EPSG:4326',
                        always_xy := true)) lon,
                   ST_Y(ST_Transform(ST_Point(s.x, s.y), 'EPSG:2154', 'EPSG:4326',
                        always_xy := true)) lat,
                   try_cast(s.coordonneeLambertAbscisseEtablissement as double) sx,
                   try_cast(s.coordonneeLambertOrdonneeEtablissement as double) sy
            from read_parquet('{ZONES}') e join read_parquet('{SIRENE_ML}') s using (siret)
            where e.etat = 'A' and e.diffusion = 'O' and e.categorie = 'une_zone'
            order by hash(e.siret || '{SEED}') limit {rank}"""
    ).fetchall()
    rows = list(csv.DictReader(CONTROLS.open(encoding="utf-8")))
    validation = [
        link_point(r["lien_gpu_principal"]) for r in rows if r["echantillon"] == "validation"
    ]
    arbitrage = [
        link_point(r["lien_gpu_principal"]) for r in rows if r["echantillon"] == "arbitrage"
    ]
    first = [(r[9], r[10]) for r in seq[:10]]
    if not all(any(same_point(p, v) for v in validation) for p in first):
        raise typer.Exit("ERREUR : les rangs 1 à 10 ne redonnent pas la grille de validation")
    typer.echo("  ✓ rangs 1 à 10 identiques à la grille de validation")
    pick = seq[rank - 1]
    point = (pick[9], pick[10])
    if any(same_point(point, v) for v in validation):
        raise typer.Exit(f"ERREUR : le rang {rank} est déjà dans la validation")
    in_arbitrage = [r["num"] for r, a in zip(
        [r for r in rows if r["echantillon"] == "arbitrage"], arbitrage, strict=True
    ) if same_point(point, a)]  # fmt: skip
    typer.echo(
        f"  rang {rank} : zone {pick[3]}, stock {pick[4]}, qualité {pick[6]}, confiance {pick[8]}"
        + (f" — DÉJÀ dans l'arbitrage (#{in_arbitrage[0]})" if in_arbitrage else "")
    )
    stock_ll = None
    if pick[11] is not None and pick[12] is not None:
        stock_ll = con.execute(
            """select ST_X(p), ST_Y(p) from (select ST_Transform(ST_Point(?, ?), 'EPSG:2154',
               'EPSG:4326', always_xy := true) p)""",
            [pick[11], pick[12]],
        ).fetchone()
    address = con.execute(
        f"""select statutDiffusionEtablissement,
                   concat_ws(' ', numeroVoieEtablissement, indiceRepetitionEtablissement,
                             typeVoieEtablissement, libelleVoieEtablissement),
                   codePostalEtablissement, libelleCommuneEtablissement
            from read_parquet('{STOCK}') where siret = ?""",
        [pick[0]],
    ).fetchone()
    if address[0] != "O":
        raise typer.Exit("ERREUR : établissement non diffusible dans le stock brut")
    num = str(max(int(r["num"]) for r in rows) + 1)
    rows.append(
        {
            "num": num, "echantillon": f"validation_remplacement_rang{rank}",
            "code_commune": pick[2] or pick[1], "zone_principale": pick[3],
            "zone_stock": pick[4] or "", "ecart_sources_m": pick[5], "qualite_xy": pick[6],
            "dist_autre_zone_m": pick[7] if pick[7] is not None else "", "confiance": pick[8],
            "adresse_voie": address[1], "code_postal": address[2], "commune": address[3],
            "lien_gpu_principal": GPU_VIEWER.format(lon=point[0], lat=point[1]),
            "lien_gpu_stock": (
                GPU_VIEWER.format(lon=stock_ll[0], lat=stock_ll[1]) if stock_ll else ""
            ),
            "zone_attendue": "", "source_juste": "",
            "commentaire": f"doublon arbitrage #{in_arbitrage[0]}" if in_arbitrage else "",
        }
    )  # fmt: skip
    with CONTROLS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    typer.echo(f"  ajouté à la grille : contrôle #{num}")


if __name__ == "__main__":
    app()
