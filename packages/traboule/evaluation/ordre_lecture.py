"""Tirage de l'échantillon C : ordre de lecture des cahiers (protocole d'évaluation, §2 bis).

- population : pages non graphiques des cahiers extraits (`traboule.retrieval.cahiers`) ;
- ordre : `md5(ressource || '|' || page || '|' || graine)` dans chaque cahier ; graine
  obligatoire et propre au tirage (ADR-0012) ;
- grille : rangs 1 à `per_resource` ; remplacements : rangs suivants, fichier masqué ;
- page de revue locale : rendu de chaque page tirée et son texte Docling nettoyé, côte à côte.
Colonnes de revue vides (aucune pré-lecture) ; une grille existante n'est jamais réécrite.

Usage : `uv run python -m traboule.evaluation.ordre_lecture --graine <graine> --ressource …`.
"""

import base64
import csv
import hashlib
import html
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from traboule.config import INTERIM_DIR, RAW_DIR
from traboule.retrieval.cahiers import OUT_DIR, resource_folder
from traboule.retrieval.extraction import clean_markdown, read_pages

PER_RESOURCE = 5
REPLACEMENTS = 5
GRID = "ordre_lecture_cahiers.csv"
MASKED = "ordre_lecture_cahiers_remplacements.masque.csv"
REVIEW = "revue_ordre_lecture.html"
HEADER = ("ressource", "rang", "page", "statut", "commentaire", "methode", "relu_par_humain")


class RevueError(RuntimeError):
    """Tirage refusé (graine absente, grille existante, cahier trop court)."""


def order_key(resource: str, page: int, seed: str) -> str:
    return hashlib.md5(f"{resource}|{page}|{seed}".encode()).hexdigest()


def draw_pages(
    candidates: dict[str, list[int]], seed: str, ranks: int = PER_RESOURCE + REPLACEMENTS
) -> list[dict]:
    """Rangs 1 à `ranks` de chaque cahier, dans l'ordre md5 (ressource, page, graine)."""
    if not seed:
        raise RevueError("graine obligatoire")
    rows = []
    for resource in sorted(candidates):
        pages = sorted(candidates[resource], key=lambda p: order_key(resource, p, seed))
        if len(pages) < ranks:
            raise RevueError(f"{resource} : moins de {ranks} pages de texte")
        rows += [{"ressource": resource, "rang": r, "page": p}
                 for r, p in enumerate(pages[:ranks], start=1)]  # fmt: skip
    return rows


def write_grid(path: Path, rows: list[dict]) -> None:
    if path.exists():
        raise RevueError(f"{path} existe déjà : tirage non réécrit")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        for r in rows:
            writer.writerow([r["ressource"], r["rang"], r["page"], "", "", "", ""])


def write_review(path: Path, rows: list[dict], raw_dir: Path) -> None:
    """Page HTML locale : rendu de chaque page tirée et texte Docling nettoyé."""
    import pymupdf

    style = (
        "body{font-family:sans-serif}section{display:flex;gap:1em;border-top:1px solid #999;"
        "padding:1em 0}img{max-width:55%}pre{white-space:pre-wrap;font-size:13px}"
    )
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Revue ordre de lecture</title>",
        f"<style>{style}</style>",
    ]
    for r in rows:
        pdf_path = next(resource_folder(r["ressource"], raw_dir).glob("*.pdf"))
        markdown = json.loads((OUT_DIR / r["ressource"] / "docling_pages.json").read_text())
        lines, _, _ = clean_markdown(markdown[str(r["page"])])
        with pymupdf.open(pdf_path) as pdf:
            png = pdf[r["page"] - 1].get_pixmap(dpi=80).tobytes("png")
        image = base64.b64encode(png).decode()
        parts.append(
            f"<section><img src='data:image/png;base64,{image}'><div><h3>{r['ressource']} — "
            f"rang {r['rang']}, page {r['page']}</h3><pre>{html.escape(chr(10).join(lines))}"
            "</pre></div></section>"
        )
    path.write_text("\n".join(parts), encoding="utf-8")


def text_pages(resource: str, raw_dir: Path = RAW_DIR) -> list[int]:
    """Pages non graphiques d'un cahier (règle graphique de l'extraction)."""
    pdf_path = next(resource_folder(resource, raw_dir).glob("*.pdf"))
    _, pages = read_pages(pdf_path)
    return [n for n, p in pages.items() if not p.graphique]


app = typer.Typer(add_completion=False)


@app.command()
def main(
    graine: Annotated[str, typer.Option(help="Graine propre au tirage (obligatoire)")],
    ressource: Annotated[list[str], typer.Option(help="Cahier extrait (SRC-005)")],
    out_dir: Annotated[Path, typer.Option(help="Dossier local des grilles")] = INTERIM_DIR
    / "controles",
) -> None:
    """Tire l'échantillon C et écrit la grille, les remplacements masqués et la page de revue."""
    try:
        rows = draw_pages({r: text_pages(r) for r in ressource}, graine)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_grid(out_dir / GRID, [r for r in rows if r["rang"] <= PER_RESOURCE])
        write_grid(out_dir / MASKED, [r for r in rows if r["rang"] > PER_RESOURCE])
        write_review(out_dir / REVIEW, [r for r in rows if r["rang"] <= PER_RESOURCE], RAW_DIR)
    except RevueError as exc:
        typer.echo(f"TIRAGE REFUSÉ : {exc}", err=True)
        sys.exit(1)
    typer.echo(f"OK : {len(rows)} pages tirées dans {out_dir}")


if __name__ == "__main__":
    app()
