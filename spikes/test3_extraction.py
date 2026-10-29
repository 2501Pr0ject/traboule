"""Test 3 du spike : extraction des PDF du PLU-H (PyMuPDF puis Docling), corpus pilote GPU.

Script jetable. Corpus (pièces du document GPU 200046977_PLUi_20260326) :
- A : règlement écrit, zones économiques (p. 581–680) et zones à urbaniser (p. 729–748) ;
- B : OAP du cahier communal d'Oullins (p. 56–73, dont l'OAP 7 « ZA de la Saulaie ») ;
- C : cahier communal de Pierre-Bénite (p. 1–67).
Sorties dans spikes/output/pdf/ (non versionné) : textes, Markdown Docling, grille.csv,
revue.html, passages.jsonl (corpus figé du Test 4), metrics.json.
Les règles d'échantillonnage et de classement « graphique » sont fixées avant le tirage.
"""

import csv
import gc
import hashlib
import html
import json
import platform
import re
import sys
import threading
import time
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import psutil
import pymupdf
import typer

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "SRC-005" / "2026-10-28"
OUT = ROOT / "spikes" / "output" / "pdf"
GPU_VERSION = "200046977_PLUi_20260326"
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"

DOCS = {
    "A_reglement": {
        "resource": "reglement_ecrit",
        "pages": list(range(581, 681)) + list(range(729, 749)),
        "titre": "Règlement écrit — zones économiques et zones à urbaniser",
        "graine": 3101,
    },
    "B_oap_oullins": {
        "resource": "cahier_communal_oullins",
        "pages": list(range(56, 74)),
        "titre": "OAP du cahier communal d'Oullins",
        "graine": 3102,
    },
    "C_cahier_pierre_benite": {
        "resource": "cahier_communal_pierre_benite",
        "pages": list(range(1, 68)),
        "titre": "Cahier communal de Pierre-Bénite",
        "graine": 3103,
    },
}
SAMPLE_SIZE = 10
# Règle « graphique » (fixée avant le tirage) : moins de 300 caractères de texte extractible
# et au moins 50 % de la page couverte d'images, ou plus de 2 000 tracés vectoriels.
GRAPHIC_MAX_CHARS = 300
GRAPHIC_MIN_IMAGE_SHARE = 0.5
GRAPHIC_MIN_DRAWINGS = 2000

ZONE_HEADER = re.compile(r"PARTIE II\s+Zone\s+([A-Za-z0-9.\-]+)", re.I)
VERSION_LINE = re.compile(
    r"PLU-H\s*[–-]\s*((?:MODIFICATION|MISE EN COMPATIBILIT|REVISION|MODIF)[^\n]*?APPROBATION\s+\d{4})",  # noqa: E501
    re.I,
)
PIECE_VERSION = re.compile(
    r"PLU-H\s*-\s*[A-ZÉÈ' \-]+\s*-\s*((?:Modification|Mise en compatibilité|Révision)[^-\n]*-\s*Approbation\s+\d{4})"  # noqa: E501
)
CHAPTER = re.compile(r"^\s*CHAPITRE\s+(\d+)\s*[-–]\s*(.+)$")
SECTION = re.compile(r"^\s*(\d+\.\d+)\s*[-–]\s*(.+)$")
SUBSECTION = re.compile(r"^\s*(\d+\.\d+\.\d+)\s*[-–]\s*(.+)$")
# Titre d'OAP : « OAP 7 ZA de la Saulaie » ou, après tri spatial, « OAP ZA de la Saulaie 7 »
OAP_TITLE = re.compile(r"^\s*OAP\s+(?:(\d+)\s+(\S.*?)|(\S.*?)\s+(\d+))\s*$")

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


@contextmanager
def measured(name: str, steps: dict):
    """Chronomètre une étape et échantillonne le pic RSS du processus toutes les 100 ms."""
    proc, peak, stop = psutil.Process(), [0], threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            stop.wait(0.1)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    start = time.perf_counter()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        peak[0] = max(peak[0], proc.memory_info().rss)
        steps[name] = {
            "seconds": round(time.perf_counter() - start, 2),
            "peak_rss_mb": round(peak[0] / 1e6),
        }
        typer.echo(
            f"  {name} : {steps[name]['seconds']} s, pic RSS {steps[name]['peak_rss_mb']} Mo"
        )


def source_pdf(resource: str) -> Path:
    return next((RAW / resource).glob("*.pdf"))


def cache_size() -> int:
    # Sans suivre les liens symboliques (le cache Hugging Face lie snapshots et blobs)
    return (
        sum(p.lstat().st_size for p in HF_CACHE.rglob("*") if p.is_file() and not p.is_symlink())
        if HF_CACHE.exists()
        else 0
    )


def sample_pages(doc_id: str, pages: list[int], seed: int) -> list[int]:
    key = lambda p: hashlib.md5(f"{doc_id}|{p}|{seed}".encode()).hexdigest()  # noqa: E731
    return sorted(sorted(pages, key=key)[:SAMPLE_SIZE])


def pymupdf_pass(doc_id: str, spec: dict) -> dict:
    """Texte trié, tableaux, indicateurs graphiques et version lue, page par page."""
    pdf = pymupdf.open(source_pdf(spec["resource"]))
    pages = {}
    for pno in spec["pages"]:
        page = pdf[pno - 1]
        text = page.get_text("text", sort=True)
        area = page.rect.width * page.rect.height
        image_area = sum(
            pymupdf.Rect(i["bbox"]).intersect(page.rect).get_area() for i in page.get_image_info()
        )
        drawings = len(page.get_drawings())
        tables = page.find_tables().tables
        chars = len("".join(text.split()))
        pages[pno] = {
            "text": text,
            "chars": chars,
            "image_share": round(min(image_area / area, 1.0), 3),
            "drawings": drawings,
            "tables": [t.extract() for t in tables],
            "graphique": chars < GRAPHIC_MAX_CHARS
            and (image_area / area >= GRAPHIC_MIN_IMAGE_SHARE or drawings > GRAPHIC_MIN_DRAWINGS),
        }
    return pages


def make_subset_pdf(doc_id: str, spec: dict) -> Path:
    """PDF ne contenant que les pages du corpus (entrée de Docling)."""
    src = pymupdf.open(source_pdf(spec["resource"]))
    sub = pymupdf.open()
    for pno in spec["pages"]:
        sub.insert_pdf(src, from_page=pno - 1, to_page=pno - 1)
    path = OUT / "sub" / f"{doc_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    sub.save(path)
    return path


def docling_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False  # PDF natifs
    options.do_table_structure = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def docling_pass(converter, doc_id: str, spec: dict, subset: Path) -> dict:
    result = converter.convert(subset)
    doc = result.document
    (OUT / "docling").mkdir(parents=True, exist_ok=True)
    (OUT / "docling" / f"{doc_id}.md").write_text(doc.export_to_markdown())
    (OUT / "docling" / f"{doc_id}.json").write_text(json.dumps(doc.export_to_dict()))
    pages = {}
    for i, pno in enumerate(spec["pages"], start=1):
        pages[pno] = {
            "text": doc.export_to_markdown(page_no=i),
            "tables": sum(
                1 for item, _ in doc.iterate_items(page_no=i) if type(item).__name__ == "TableItem"
            ),
        }
    return pages


def read_version(doc_id: str, pages: dict) -> str | None:
    """Procédure lue dans la pièce (en-tête ou pied de page)."""
    pattern = VERSION_LINE if doc_id.startswith("A_") else PIECE_VERSION
    found = [m.group(1).strip() for p in pages.values() if (m := pattern.search(p["text"]))]
    return max(set(found), key=found.count) if found else None


def clean_lines(text: str) -> list[str]:
    """Retire en-têtes et pieds de page récurrents du règlement."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if (
            not s
            or "METROPOLE DE LYON" in s.upper()
            or VERSION_LINE.search(s)
            or re.fullmatch(r"\d{1,3}", s)
        ):
            continue
        lines.append(" ".join(s.split()))
    return lines


def page_versions(doc_id: str, pages: dict) -> dict[int, str | None]:
    """Procédure lue page par page (pied de page du règlement, en-tête des cahiers)."""
    pattern = VERSION_LINE if doc_id.startswith("A_") else PIECE_VERSION
    return {pno: (m.group(1).strip() if (m := pattern.search(p["text"])) else None)
            for pno, p in pages.items()}  # fmt: skip


def is_title_continuation(line: str) -> bool:
    """Seconde ligne d'un titre : courte, sans ponctuation finale, en capitales ou en minuscule."""
    return (
        len(line) < 90
        and not line.endswith((".", ":", ";"))
        and (line.isupper() or line[:1].islower())
    )


def structure_reglement(pages: dict, versions: dict) -> list[dict]:
    """Zone (en-tête) → chapitre → section → sous-section → paragraphe."""
    passages, current = [], None
    path = {"chapitre": None, "section": None, "sous_section": None}
    last_level = None

    def flush():
        if current and current["lignes"]:
            current["texte"] = " ".join(current.pop("lignes"))
            passages.append(current)

    for pno, page in pages.items():
        m = ZONE_HEADER.search(page["text"])
        zone = m.group(1) if m else None
        if zone and zone.lower() == "aus.co":
            zone = "AUs.co"  # coquille de l'en-tête du PDF (« Aus.co »)
        for line in clean_lines(page["text"]):
            zone_changed = current is not None and current["zone"] != zone
            if zone_changed:
                path = {"chapitre": None, "section": None, "sous_section": None}
                last_level = None
            level = None
            if mm := CHAPTER.match(line):
                path = {"chapitre": f"CHAPITRE {mm.group(1)} - {mm.group(2)}",
                        "section": None, "sous_section": None}  # fmt: skip
                level = "chapitre"
            elif mm := SUBSECTION.match(line):
                path["sous_section"] = f"{mm.group(1)} - {mm.group(2)}"
                level = "sous_section"
            elif mm := SECTION.match(line):
                path["section"] = f"{mm.group(1)} - {mm.group(2)}"
                path["sous_section"] = None
                level = "section"
            elif (
                last_level and current is not None and not current["lignes"]
                and is_title_continuation(line)
            ):  # fmt: skip
                path[last_level] = f"{path[last_level]} {line}"
                current["chemin"] = " > ".join(v for v in path.values() if v)
                continue
            if level or zone_changed or current is None:
                flush()
                current = {
                    "doc_id": "A_reglement", "source_id": "SRC-005", "version_gpu": GPU_VERSION,
                    "version_piece": versions.get(pno), "page_debut": pno, "page_fin": pno,
                    "zone": zone,
                    "chemin": " > ".join(v for v in path.values() if v)
                    or ("CARACTÈRE DE LA ZONE / préambule" if zone else "page de garde de section"),
                    "lignes": [], "extracteur": "pymupdf",
                }  # fmt: skip
                last_level = level
                if level:
                    continue  # le titre est porté par le chemin
            last_level = None
            current["lignes"].append(line)
            current["page_fin"] = pno
    flush()
    return passages


def structure_share(passages: list[dict]) -> dict:
    """Part du texte (en caractères) du règlement par niveau de rattachement."""
    sizes = {"zone > chapitre > article": 0, "préambule de zone": 0, "page de garde de section": 0}
    for p in passages:
        if p["doc_id"] != "A_reglement":
            continue
        if p["zone"] is None:
            sizes["page de garde de section"] += len(p["texte"])
        elif "préambule" in p["chemin"]:
            sizes["préambule de zone"] += len(p["texte"])
        else:
            sizes["zone > chapitre > article"] += len(p["texte"])
    total = sum(sizes.values())
    return {"unite": "caractères", "total": total,
            "parts": {k: round(v / total, 4) for k, v in sizes.items()}}  # fmt: skip


def normalized(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", ascii_text).split())


def deduplicate(passages: list[dict]) -> tuple[list[dict], dict]:
    """Retire les doublons exacts (texte normalisé) d'un même document, zone et chemin.

    Les articles identiques d'une zone à l'autre sont conservés : chacun porte sa zone.
    """
    seen, kept, removed = set(), [], []
    for p in passages:
        key = (p["doc_id"], p["zone"], p["chemin"], normalized(p["texte"]))
        if key in seen:
            removed.append(p)
            continue
        seen.add(key)
        kept.append(p)
    groups: dict[str, set] = {}
    for p in kept:
        groups.setdefault(normalized(p["texte"]), set()).add((p["doc_id"], p["zone"]))
    cross = {k: v for k, v in groups.items() if len(v) > 1}
    return kept, {
        "retires_meme_zone_et_chemin": len(removed),
        "groupes_identiques_entre_zones": len(cross),
        "passages_dans_ces_groupes": sum(len(v) for v in cross.values()),
    }


def docling_lines(markdown: str) -> list[str]:
    """Lignes du Markdown Docling, sans balisage, sans doublons exacts sur la page."""
    seen, lines = set(), []
    for raw in markdown.splitlines():
        s = html.unescape(re.sub(r"^#+\s*", "", raw.strip()))
        if not s or s == "<!-- image -->" or re.fullmatch(r"\|?[-| ]+\|?", s) or s in seen:
            continue
        seen.add(s)
        lines.append(" ".join(s.split()))
    return lines


def structure_cahier(
    doc_id: str, spec: dict, pages: dict, versions: dict, docling: dict
) -> list[dict]:
    """Cahier : découpage par la table des matières (et par OAP pour le document B).

    Repérage des titres sur PyMuPDF ; texte des passages pris dans Docling, qui respecte
    l'ordre des colonnes (PyMuPDF trié les entrelace sur ces pages).
    """
    pdf = pymupdf.open(source_pdf(spec["resource"]))
    toc = [(lvl, " ".join(title.split()), page) for lvl, title, page in pdf.get_toc()]
    passages, current = [], None
    for pno, page in pages.items():
        heads = [t for t in toc if t[2] == pno]
        oap = next(
            (
                f"OAP {m.group(1) or m.group(4)} {' '.join((m.group(2) or m.group(3)).split())}"
                for line in page["text"].splitlines()
                if (m := OAP_TITLE.match(line))
            ),
            None,
        )
        if heads or oap or current is None:
            if current and current["lignes"]:
                current["texte"] = " ".join(current.pop("lignes"))
                passages.append(current)
            chemin = (
                " > ".join(t[1] for t in heads) if heads else (current or {}).get("chemin", "début")
            )
            if oap:
                chemin = f"4. Orientations d'Aménagement et de Programmation (OAP) > {oap}"
            current = {
                "doc_id": doc_id, "source_id": "SRC-005", "version_gpu": GPU_VERSION,
                "version_piece": versions.get(pno), "page_debut": pno, "page_fin": pno, "zone": None,  # noqa: E501
                "chemin": chemin, "lignes": [], "extracteur": "docling",
            }  # fmt: skip
        lines = docling_lines(docling[pno]["text"])
        if not page["graphique"]:
            current["lignes"].extend(lines)
        current["page_fin"] = pno
    if current and current["lignes"]:
        current["texte"] = " ".join(current.pop("lignes"))
        passages.append(current)
    return [p for p in passages if p.get("texte")]


def au_correspondence(reglement_pages_all: dict, codes: list[str]) -> list[dict]:
    """Rattachement des codes AU* et des codes résiduels, avec la page qui le justifie."""
    pdf = pymupdf.open(source_pdf("reglement_ecrit"))
    chapters = {}
    for _, title, page in pdf.get_toc():
        if m := re.match(r"\s*Zone\s+(.+?)\s*$", title):
            chapters[m.group(1).replace(" ", "")] = page
    full = {i + 1: pdf[i].get_text() for i in range(pdf.page_count)}
    rows = []
    for code in codes:
        row = {"code": code}
        if code in ("AU1", "AU2", "AU3"):
            row |= {"chapitre": "Zone AU", "page_pdf": chapters.get("AU"),
                    "justification": "p. 739 : AU1 mixte, AU2 à dominante d'habitat, AU3 à dominante "  # noqa: E501
                    "d'activité ; ouverture à l'urbanisation différée"}  # fmt: skip
        elif code.startswith("AU"):
            ref = "U" + code[2:]  # le sigle AU précède le code U sans son « U »
            base = re.sub(r"(?<=\d)[a-z]+$", "", ref)
            target = ref if ref in chapters else base if base in chapters else None
            row |= {"chapitre": "Zone AUs.co", "page_pdf": chapters.get("AUs.co"),
                    "zone_u_reference": ref, "chapitre_u": f"Zone {target}" if target else None,
                    "page_u": chapters.get(target) if target else None,
                    "justification": "p. 731 : le règlement de la zone U correspondante s'applique "
                    "après ouverture ; p. 734-737 : règles de la zone « U » de référence indiquée "
                    "après le sigle AU"}  # fmt: skip
        else:
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])")
            hits = [p for p, t in full.items() if pattern.search(t)]
            row |= {"chapitre": None, "pages_texte": hits[:10],
                    "extrait": next((" ".join(m.group(0).split()) for p in hits[:1]
                                     for m in [re.search(rf".{{0,120}}{re.escape(code)}.{{0,120}}", full[p], re.S)] if m), None)}  # fmt: skip  # noqa: E501
        rows.append(row)
    return rows


def write_review(samples: dict, mu: dict, dl: dict) -> None:
    """grille.csv (pré-remplie, à relire) et revue.html (PNG + deux textes côte à côte)."""
    (OUT / "png").mkdir(parents=True, exist_ok=True)
    sections, grid = [], []
    for doc_id, pages in samples.items():
        pdf = pymupdf.open(source_pdf(DOCS[doc_id]["resource"]))
        for pno in pages:
            png = OUT / "png" / f"{doc_id}_p{pno}.png"
            pdf[pno - 1].get_pixmap(dpi=90).save(png)
            m, d = mu[doc_id][pno], dl[doc_id][pno]
            for extracteur, text, tables in (
                ("pymupdf", m["text"], len(m["tables"])),
                ("docling", d["text"], d["tables"]),
            ):
                grid.append({
                    "doc_id": doc_id, "page_pdf": pno, "extracteur": extracteur,
                    "graphique_auto": "oui" if m["graphique"] else "non",
                    "caracteres": len("".join(text.split())), "tableaux_detectes": tables,
                    "texte_lisible": "", "ordre_lecture": "", "titres_zone_article": "",
                    "tableaux": "", "parasites": "", "relu_par_humain": "non", "commentaire": "",
                })  # fmt: skip
            sections.append(
                f"<section id='{doc_id}-{pno}'><h2>{doc_id} — page {pno}"
                f"{' — graphique (auto)' if m['graphique'] else ''}</h2>"
                f"<div class='row'><img src='png/{png.name}' loading='lazy'>"
                f"<div><h3>PyMuPDF ({len(m['tables'])} tableau(x))</h3><pre>{html.escape(m['text'])}</pre></div>"  # noqa: E501
                f"<div><h3>Docling ({d['tables']} tableau(x))</h3><pre>{html.escape(d['text'])}</pre></div>"  # noqa: E501
                "</div></section>"
            )
    grid_path = OUT / "grille.csv"
    if grid_path.exists():
        typer.echo(f"  {grid_path} existe : conservée (relecture éventuelle en cours)")
    else:
        with grid_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(grid[0]))
            writer.writeheader()
            writer.writerows(grid)
    nav = " · ".join(f"<a href='#{d}-{p}'>{d[:1]}{p}</a>" for d, ps in samples.items() for p in ps)
    (OUT / "revue.html").write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Revue Test 3</title>"
        "<style>body{font:13px system-ui;margin:12px}.row{display:grid;grid-template-columns:"
        "38% 31% 31%;gap:8px}img{width:100%;border:1px solid #ccc}pre{white-space:pre-wrap;"
        "font-size:11px;max-height:900px;overflow:auto;background:#f6f6f6;padding:6px}"
        "section{border-top:2px solid #333;margin-top:16px}</style></head><body>"
        f"<h1>Revue Test 3</h1><p>{nav}</p>{''.join(sections)}</body></html>",
        encoding="utf-8",
    )


MAX_CHARS = 2000  # ≈ 500 tokens


def split_long(passages: list[dict]) -> list[dict]:
    """Découpe les passages trop longs aux limites de phrase ; métadonnées conservées."""
    out = []
    for p in passages:
        if len(p["texte"]) <= MAX_CHARS:
            out.append(p | {"partie": 1, "parties": 1})
            continue
        sentences = re.split(r"(?<=[.;:!?])\s+", p["texte"])
        chunks, buf = [], ""
        for s in sentences:
            if buf and len(buf) + len(s) + 1 > MAX_CHARS:
                chunks.append(buf)
                buf = s
            else:
                buf = f"{buf} {s}".strip()
        chunks.append(buf)
        out += [
            p | {"texte": c, "partie": i, "parties": len(chunks)} for i, c in enumerate(chunks, 1)
        ]
    return out


def token_count(passages: list[dict]) -> int | None:
    """Tokens BGE-M3 (tokenizer seul, sans charger le modèle)."""
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")
    return sum(len(tok(p["texte"], add_special_tokens=False)["input_ids"]) for p in passages)


@app.command()
def main(
    reuse: bool = typer.Option(False, help="Réutiliser les extractions du passage précédent"),
) -> None:
    """Extraction, échantillonnage, revue, structure et corpus figé du Test 3."""
    OUT.mkdir(parents=True, exist_ok=True)
    steps: dict = {}
    result: dict = {"started_at": datetime.now(UTC).isoformat(), "steps": steps, "documents": {}}
    samples = {d: sample_pages(d, s["pages"], s["graine"]) for d, s in DOCS.items()}
    result["echantillons"] = samples
    cache = OUT / "cache_pages.json"
    if reuse:
        previous = json.loads((OUT / "metrics.json").read_text())
        steps.update(previous["steps"])
        result["docling_modeles_telecharges_mo"] = previous["docling_modeles_telecharges_mo"]
        data = json.loads(cache.read_text())
        mu = {d: {int(k): v for k, v in pages.items()} for d, pages in data["mu"].items()}
        dl = {d: {int(k): v for k, v in pages.items()} for d, pages in data["dl"].items()}
    else:
        mu, dl = extract_all(steps, result)
        cache.write_text(json.dumps({"mu": mu, "dl": dl}, ensure_ascii=False))
    finish(steps, result, samples, mu, dl)


def extract_all(steps: dict, result: dict) -> tuple[dict, dict]:
    mu, dl = {}, {}
    for doc_id, spec in DOCS.items():
        with measured(f"pymupdf_{doc_id}", steps):
            mu[doc_id] = pymupdf_pass(doc_id, spec)
        (OUT / "pymupdf").mkdir(parents=True, exist_ok=True)
        (OUT / "pymupdf" / f"{doc_id}.txt").write_text(
            "".join(f"\n===== page {p}\n{v['text']}" for p, v in mu[doc_id].items())
        )
    cache_before = cache_size()
    with measured("docling_import_et_chauffe (exclu)", steps):
        converter = docling_converter()
        warm = make_subset_pdf("chauffe", {"resource": "plan_de_secteurs", "pages": [1]})
        converter.convert(warm)
    result["docling_modeles_telecharges_mo"] = round((cache_size() - cache_before) / 1e6)
    for doc_id, spec in DOCS.items():
        subset = make_subset_pdf(doc_id, spec)
        gc.collect()
        with measured(f"docling_{doc_id}", steps):
            dl[doc_id] = docling_pass(converter, doc_id, spec, subset)
    return mu, dl


def finish(steps: dict, result: dict, samples: dict, mu: dict, dl: dict) -> None:
    for doc_id, spec in DOCS.items():
        n = len(spec["pages"])
        version_piece = read_version(doc_id, mu[doc_id])
        result["documents"][doc_id] = {
            "titre": spec["titre"], "ressource": spec["resource"], "pages": n,
            "version_piece": version_piece,
            "pages_graphiques": sum(p["graphique"] for p in mu[doc_id].values()),
            "pages_sans_texte_pymupdf": sum(p["chars"] == 0 for p in mu[doc_id].values()),
            "tableaux_pymupdf": sum(len(p["tables"]) for p in mu[doc_id].values()),
            "tableaux_docling": sum(p["tables"] for p in dl[doc_id].values()),
            "pages_par_s_pymupdf": round(n / steps[f"pymupdf_{doc_id}"]["seconds"], 1),
            "pages_par_s_docling": round(n / steps[f"docling_{doc_id}"]["seconds"], 2),
        }  # fmt: skip
    write_review(samples, mu, dl)
    versions = {d: page_versions(d, mu[d]) for d in DOCS}
    result["versions_par_page"] = {
        d: dict(Counter(v or "non lue" for v in versions[d].values())) for d in DOCS
    }
    passages = structure_reglement(mu["A_reglement"], versions["A_reglement"])
    for doc_id in ("B_oap_oullins", "C_cahier_pierre_benite"):
        passages += structure_cahier(doc_id, DOCS[doc_id], mu[doc_id], versions[doc_id], dl[doc_id])
    passages = split_long(passages)
    passages, result["doublons"] = deduplicate(passages)
    result["structure_reglement"] = structure_share(passages) | {
        "zones": sorted({p["zone"] for p in passages if p["doc_id"] == "A_reglement" and p["zone"]})
    }
    with (OUT / "passages.jsonl").open("w", encoding="utf-8") as fh:
        for i, p in enumerate(passages, start=1):
            fh.write(json.dumps({"passage_id": f"P{i:05d}", **p}, ensure_ascii=False) + "\n")
    data = (OUT / "passages.jsonl").read_bytes()
    with measured("tokens_bge_m3", steps):
        tokens = token_count(passages)
    result["passages"] = {
        "fichier": "spikes/output/pdf/passages.jsonl",
        "sha256": hashlib.sha256(data).hexdigest(),
        "nombre": len(passages),
        "par_document": {d: sum(p["doc_id"] == d for p in passages) for d in DOCS},
        "tokens_bge_m3": tokens,
    }
    zone_codes = [
        r["code"]
        for r in json.loads((ROOT / "spikes/output/test2/metrics.json").read_text())["codes_zone"]
    ]
    manual = [c for c in zone_codes if c.startswith("AU") or c in ("UCe3-p", "UPpa")]
    result["correspondance_codes"] = au_correspondence(mu["A_reglement"], manual)
    result["environment"] = {
        "python": platform.python_version(), "platform": platform.platform(),
        "versions": {p: version(p) for p in ("pymupdf", "docling", "transformers", "psutil")},
        "sources_sha256": {
            spec["resource"]: json.loads((RAW / spec["resource"] / "manifest.json").read_text())["sha256"]  # noqa: E501
            for spec in DOCS.values()
        },
        "graines": {d: s["graine"] for d, s in DOCS.items()},
        "regle_graphique": {"max_caracteres": GRAPHIC_MAX_CHARS, "min_part_image": GRAPHIC_MIN_IMAGE_SHARE,  # noqa: E501
                            "min_traces": GRAPHIC_MIN_DRAWINGS},
    }  # fmt: skip
    (OUT / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    typer.echo(f"Mesures : {OUT / 'metrics.json'}")


if __name__ == "__main__":
    sys.exit(app())
