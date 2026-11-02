"""Cahiers communaux et d'arrondissement : structure, passages et mesures de qualité.

- texte Docling (ordre des colonnes), titres repérés sur PyMuPDF (ADR-0008) ;
- chemin d'un passage = entrées actives de la table des matières du cahier ; dans la partie 4
  (OAP), le titre d'OAP (« OAP / numéro / nom ») ouvre un passage ;
- en-têtes et pieds de page courants retirés (lignes présentes sur plus de la moitié des
  pages), pages graphiques écartées, passages longs découpés aux limites de phrase ;
- payload ADR-0009 : secteur PLU-H, commune COG 2026 et commune historique, OAP, version de
  la pièce lue dans ses en-têtes.

Mesures par cahier : temps, pages graphiques, doublons Docling retirés, ligatures réparées,
en-têtes retirés, couverture du texte Docling par rapport à PyMuPDF, OAP détectées.

Usage : `uv run python -m traboule.retrieval.cahiers --ressource cahier_communal_sect65 …`.
"""

import hashlib
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from traboule.config import INTERIM_DIR, RAW_DIR
from traboule.contracts.passage import Passage
from traboule.measure import peak_rss_bytes, write_metrics
from traboule.retrieval.extraction import (
    Page,
    apply_docling,
    docling_converter,
    docling_markdown,
    read_pages,
    repair_ligatures,
)

RAW_DATE = "2026-11-01"
VERSION_GPU = "200046977_PLUi_20260326"
OUT_DIR = INTERIM_DIR / "extraction" / "cahiers"
MAX_CHARS = 2000
# Titre de la partie 4 dans la table des matières (parfois altéré : « … et de4. Orientation… »).
OAP_PART = re.compile(r"^\s*4\.\s*Orientations?\s+d.Am[ée]nagement", re.I)
OAP_NUMBER = re.compile(r"^(\d+(?:\s*[.-]\s*\d+)*)\s*(.*)$")  # « 7.4 », « 11-1 », « 11 -1 »
# Fragments laissés par une ligature « ti », « tt », « ff », « fi », « fl » codée avec une espace
# dans certains PDF (« parti e », « créati on ») : comptés, non réparés (règle à valider).
SPLIT_LIGATURE = re.compile(
    r"\b\w*(?:ti|tt|ff|fi|fl) (?:e|es|er|ers|on|ons|que|ques|f|fs|ve|ves|el|elle|elles|ère|ères)\b"
)
OAP_REFERENCE = re.compile(r"\bOAP\s*\n?\s*(\d+(?:\.\d+)*)\b")
PIECE_VERSION = re.compile(
    r"PLU-H\s*[-–]\s*[^\n]*?[-–]\s*((?:Modification|Mise en compatibilit[ée]|R[ée]vision)"
    r"[^\n]*?[-–]\s*Approbation\s+\d{4})",
    re.I,
)
RUNNING_SHARE = 0.5


class CahierError(RuntimeError):
    """Contrôle bloquant de l'extraction d'un cahier."""


def piece_version(pages: dict[int, Page]) -> str:
    """Procédure la plus fréquente dans les en-têtes de la pièce."""
    found = [" ".join(m.group(1).split()) for p in pages.values()
             if (m := PIECE_VERSION.search(p.texte_pymupdf))]  # fmt: skip
    if not found:
        raise CahierError("version de la pièce introuvable dans ses en-têtes")
    return Counter(found).most_common(1)[0][0]


def oap_part(toc: list[tuple[int, str, int]], page_count: int) -> range | None:
    """Pages de la partie 4 (OAP), d'après les entrées de niveau 1 de la table des matières."""
    top = sorted((page, title) for level, title, page in toc if level == 1)
    for i, (page, title) in enumerate(top):
        if OAP_PART.match(title):
            end = next((p for p, _ in top[i + 1 :] if p > page), page_count + 1)
            return range(page, end)
    return None


def oap_titles(pages: dict[int, Page], part: range | None) -> dict[int, str]:
    """Page → « OAP n Nom » pour les titres d'OAP de la partie 4.

    Un titre est la ligne « OAP », suivie du numéro et du nom (sur la même ligne ou la
    suivante) ; un renvoi sans nom (« OAP 0.1 » suivi d'un autre « OAP ») n'est pas un titre.
    """
    titles = {}
    for number in part or []:
        lines = [line.strip() for line in pages[number].texte_pymupdf.splitlines()]
        for i, line in enumerate(lines[:-1]):
            if line != "OAP" or not (m := OAP_NUMBER.match(lines[i + 1])):
                continue
            name = m.group(2) or (lines[i + 2] if i + 2 < len(lines) else "")
            if name and not name.startswith("OAP"):
                name, _ = repair_ligatures(" ".join(name.split()))
                numero = re.sub(r"\s+", "", m.group(1))
                titles[number] = f"OAP {numero} {name}"
    return titles


def chemins(toc: list[tuple[int, str, int]], page_count: int) -> dict[int, list[str]]:
    """Page → titres actifs de la table des matières (un par niveau)."""
    active: dict[int, str] = {}
    by_page: dict[int, list[tuple[int, str]]] = {}
    for level, title, page in toc:
        by_page.setdefault(page, []).append((level, title))
    out = {}
    for number in range(1, page_count + 1):
        for level, title in by_page.get(number, []):
            active = {k: v for k, v in active.items() if k < level} | {level: title}
        out[number] = [active[k] for k in sorted(active)] or ["Début du cahier"]
    return out


def running_lines(pages: dict[int, Page]) -> set[str]:
    """Lignes présentes sur plus de la moitié des pages de texte (en-têtes, pieds de page)."""
    text_pages = [p for p in pages.values() if not p.graphique]
    counts = Counter(line for p in text_pages for line in set(p.lignes))
    limit = RUNNING_SHARE * len(text_pages)
    return {line for line, n in counts.items() if n > limit or re.fullmatch(r"\d{1,3}", line)}


def split_long(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Découpe un texte trop long aux limites de phrase."""
    if len(text) <= max_chars:
        return [text]
    chunks, buf = [], ""
    for sentence in re.split(r"(?<=[.;:!?])\s+", text):
        if buf and len(buf) + len(sentence) + 1 > max_chars:
            chunks.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    return [*chunks, buf]


def passage_id(doc_id: str, page: int, chemin: list[str], partie: int) -> str:
    key = f"{doc_id}|{page}|{' > '.join(chemin)}|{partie}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def build_passages(
    doc_id: str,
    toc: list[tuple[int, str, int]],
    pages: dict[int, Page],
    commune: dict[str, str],
) -> tuple[list[Passage], dict]:
    """Passages d'un cahier dont les pages portent déjà leurs lignes Docling nettoyées."""
    version = piece_version(pages)
    part = oap_part(toc, len(pages))
    oaps = oap_titles(pages, part)
    paths = chemins(toc, len(pages))
    running = running_lines(pages)
    groups: list[dict] = []
    current_oap = None
    for number, page in pages.items():
        in_part = part is not None and number in part
        current_oap = oaps.get(number, current_oap) if in_part else None
        chemin = paths[number] + ([current_oap] if current_oap else [])
        lines = [line for line in page.lignes if line not in running]
        if not groups or groups[-1]["chemin"] != chemin:
            groups.append({"chemin": chemin, "oap": current_oap, "debut": number, "lignes": []})
        groups[-1]["fin"] = number
        groups[-1]["lignes"].extend(lines)
    passages = []
    for g in groups:
        text = " ".join(g["lignes"]).strip()
        if not text:
            continue
        for partie, chunk in enumerate(split_long(text), start=1):
            passages.append(
                Passage(
                    passage_id=passage_id(doc_id, g["debut"], g["chemin"], partie),
                    texte=chunk,
                    doc_id=doc_id,
                    source_id="SRC-005",
                    version_piece=version,
                    version_gpu=VERSION_GPU,
                    page_debut=g["debut"],
                    page_fin=g["fin"],
                    chemin=g["chemin"],
                    extracteur="docling",
                    oap=g["oap"],
                    **commune,
                )  # fmt: skip
            )
    referenced = {
        m.group(1) for p in pages.values() for m in OAP_REFERENCE.finditer(p.texte_pymupdf)
    }
    detected = {t.split()[1] for t in oaps.values()}
    return passages, {
        "version_piece": version,
        "en_tetes_retires": sum(1 for p in pages.values() for line in p.lignes if line in running),
        "oap_detectees": sorted(set(oaps.values()), key=oap_order),
        "oap_citees_non_detectees": sorted(referenced - detected - {"0"}),
    }  # fmt: skip


def oap_order(title: str) -> list[int]:
    """Clé de tri d'un titre « OAP 7.4 Nom » : numéros dans l'ordre."""
    return [int(x) for x in re.split(r"[.-]", title.split()[1])]


def coverage(pages: dict[int, Page]) -> dict:
    """Rapport caractères Docling / caractères PyMuPDF sur les pages de texte."""
    ratios = [
        len("".join("".join(p.lignes).split())) / p.caracteres
        for p in pages.values()
        if not p.graphique and p.caracteres
    ]
    if not ratios:
        return {"pages": 0}
    return {
        "pages": len(ratios),
        "mediane": round(statistics.median(ratios), 3),
        "pages_sous_0_5": sum(r < 0.5 for r in ratios),
        "pages_au_dela_1_5": sum(r > 1.5 for r in ratios),
    }


PLAN_DE_SECTEURS = "SRC-005/2026-10-28/plan_de_secteurs/200046977_plan_de_secteurs_20260326.pdf"
SECTOR_ENTRY = re.compile(r"(\d{5}):\s*Se(?:ct|tc)eur\s*(\d{2})")  # « Setceur » : coquille du plan


def sector_codes(plan_pdf: Path) -> dict[str, str]:
    """Secteur PLU-H (01–67) → code commune ou arrondissement, lu dans le plan de secteurs."""
    import pymupdf

    with pymupdf.open(plan_pdf) as pdf:
        text = " ".join(pdf[0].get_text().split())
    codes = {sector: code for code, sector in SECTOR_ENTRY.findall(text)}
    if len(codes) != 67:
        raise CahierError(f"{len(codes)} secteurs lus dans le plan de secteurs (attendu 67)")
    return codes


def commune_of(
    file_name: str, sectors: dict[str, str], passage_communes: dict[str, str]
) -> dict[str, str]:
    """Secteur PLU-H (nom de fichier), commune COG 2026 et commune historique."""
    m = re.search(r"_SECT(\d{2})_", file_name)
    if not m or m.group(1) not in sectors:
        raise CahierError(f"secteur introuvable pour {file_name}")
    code = sectors[m.group(1)]
    return {
        "secteur_pluh": m.group(1),
        "code_commune_cog2026": passage_communes.get(code, code),
        "commune_historique": code,
    }


def load_passage_communes(path: Path = INTERIM_DIR / "passage_communes.parquet") -> dict[str, str]:
    import duckdb

    rows = duckdb.execute(
        f"select code_source, code_cog_2026 from read_parquet('{path}')"
    ).fetchall()
    return dict(rows)


def resource_folder(resource: str, raw_dir: Path = RAW_DIR) -> Path:
    """Dossier le plus récent d'une ressource SRC-005, quel que soit son dossier daté."""
    folders = sorted((raw_dir / "SRC-005").glob(f"*/{resource}"))
    if not folders:
        raise CahierError(f"ressource {resource} absente de data/raw/SRC-005")
    return folders[-1]


def extract(
    resource: str,
    converter,
    communes: dict[str, str],
    sectors: dict[str, str],
    raw_dir: Path = RAW_DIR,
) -> dict:
    """Extrait un cahier : passages écrits dans OUT_DIR/<ressource>/, mesures renvoyées."""
    pdf = next(resource_folder(resource, raw_dir).glob("*.pdf"))
    out = OUT_DIR / resource
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    toc, pages = read_pages(pdf)
    t_pymupdf = time.perf_counter() - t0
    cache = out / "docling_pages.json"
    if cache.exists():
        markdown = {int(k): v for k, v in json.loads(cache.read_text()).items()}
        t_docling = None
    else:
        t1 = time.perf_counter()
        markdown = docling_markdown(converter, pdf, len(pages))
        t_docling = time.perf_counter() - t1
        cache.write_text(json.dumps(markdown, ensure_ascii=False))
    apply_docling(pages, markdown)
    passages, quality = build_passages(
        pdf.name, toc, pages, commune_of(pdf.name, sectors, communes)
    )
    # Texte brut ; la réparation des ligatures écrit passages.jsonl (traboule.retrieval.ligatures).
    (out / "passages_brut.jsonl").write_text(
        "".join(p.model_dump_json() + "\n" for p in passages), encoding="utf-8"
    )
    graphic = [n for n, p in pages.items() if p.graphique]
    return {
        "pages": len(pages),
        "pages_graphiques": len(graphic),
        "secondes_pymupdf": round(t_pymupdf, 1),
        "secondes_docling": round(t_docling, 1) if t_docling is not None else "cache",
        "pages_par_seconde_docling": round(len(pages) / t_docling, 2) if t_docling else None,
        "lignes": sum(len(p.lignes) for p in pages.values()),
        "doublons_docling_retires": sum(p.doublons_retires for p in pages.values()),
        "ligatures_reparees": sum(p.ligatures_reparees for p in pages.values()),
        "couverture": coverage(pages),
        "passages": len(passages),
        "passages_oap": sum(1 for p in passages if p.oap),
        "fragments_ligature_suspects": sum(len(SPLIT_LIGATURE.findall(p.texte)) for p in passages),
        **quality,
    }


app = typer.Typer(add_completion=False)


@app.command()
def main(
    ressource: Annotated[list[str], typer.Option(help="Ressource SRC-005 du 2026-11-01")],
) -> None:
    """Extrait les cahiers demandés (un seul processus) et écrit les mesures."""
    converter = docling_converter()
    communes = load_passage_communes()
    sectors = sector_codes(RAW_DIR / PLAN_DE_SECTEURS)
    results = {}
    try:
        for name in ressource:
            typer.echo(f"  {name} …")
            results[name] = extract(name, converter, communes, sectors)
    except CahierError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    write_metrics(
        INTERIM_DIR / "metrics" / "extraction_cahiers.json",
        {"cahiers": results, "pic_rss_mo": round(peak_rss_bytes() / 2**20)},
        {"ressources": ressource, "max_chars": MAX_CHARS, "raw_date": RAW_DATE},
    )
    for name, r in results.items():
        typer.echo(f"{name} : {r['passages']} passages, {len(r['oap_detectees'])} OAP, "
                   f"docling {r['secondes_docling']} s")  # fmt: skip


if __name__ == "__main__":
    app()
