"""Extraction du texte des pièces PDF du PLU-H (ADR-0008).

- PyMuPDF : texte page par page, indicateurs de page graphique (plans, cartes), repérage des
  titres ; règle graphique du spike (fixée avant son tirage, « à revoir » selon l'ADR-0008) :
  moins de 300 caractères et au moins 50 % de la page couverte d'images, ou plus de 2 000
  tracés vectoriels ;
- Docling : texte des cahiers communaux (ordre des colonnes respecté), page par page ;
- nettoyage : ligatures cassées réparées, lignes répétées à l'identique sur une page retirées
  (doublons de Docling), balisage Markdown retiré. Chaque correction est comptée.
"""

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

GRAPHIC_MAX_CHARS = 300
GRAPHIC_MIN_IMAGE_SHARE = 0.5
GRAPHIC_MIN_DRAWINGS = 2000
# Glyphes de ligature mal décodés dans les cahiers (« résidenƟ el », « Aﬃ  rmer ») : le
# glyphe est suivi d'espaces parasites. Correspondance glyphe → lettres.
LIGATURES = {"Ɵ": "ti", "Ʃ": "tt", "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}
LIGATURE = re.compile(f"([{''.join(LIGATURES)}])[ \\t]*")


@dataclass
class Page:
    """Une page : texte PyMuPDF, indicateurs graphiques, texte Docling nettoyé."""

    numero: int
    texte_pymupdf: str
    caracteres: int
    part_image: float
    traces: int
    graphique: bool
    lignes: list[str] = field(default_factory=list)
    doublons_retires: int = 0
    ligatures_reparees: int = 0


def repair_ligatures(text: str) -> tuple[str, int]:
    """Remplace les glyphes de ligature et les espaces qui les suivent ; renvoie le nombre."""
    count = 0

    def fix(m: re.Match) -> str:
        nonlocal count
        count += 1
        return LIGATURES[m.group(1)]

    return LIGATURE.sub(fix, text), count


def is_graphic(chars: int, image_share: float, drawings: int) -> bool:
    return chars < GRAPHIC_MAX_CHARS and (
        image_share >= GRAPHIC_MIN_IMAGE_SHARE or drawings > GRAPHIC_MIN_DRAWINGS
    )


def read_pages(path: Path) -> tuple[list[tuple[int, str, int]], dict[int, Page]]:
    """Table des matières et pages lues par PyMuPDF (extra `pdf`)."""
    import pymupdf

    pages = {}
    with pymupdf.open(path) as pdf:
        toc = [(level, " ".join(title.split()), page) for level, title, page in pdf.get_toc()]
        for i, page in enumerate(pdf, start=1):
            text = page.get_text("text")
            area = page.rect.width * page.rect.height
            images = sum(
                pymupdf.Rect(info["bbox"]).intersect(page.rect).get_area()
                for info in page.get_image_info()
            )
            share = round(min(images / area, 1.0), 3) if area else 0.0
            drawings = len(page.get_drawings())
            chars = len("".join(text.split()))
            pages[i] = Page(i, text, chars, share, drawings, is_graphic(chars, share, drawings))
    return toc, pages


def clean_markdown(markdown: str) -> tuple[list[str], int, int]:
    """Lignes du Markdown d'une page : balisage retiré, ligatures réparées, doublons retirés.

    Renvoie (lignes, doublons retirés, ligatures réparées).
    """
    seen: set[str] = set()
    lines, duplicates, ligatures = [], 0, 0
    for raw in markdown.splitlines():
        s = html.unescape(re.sub(r"^#+\s*", "", raw.strip()))
        if not s or s == "<!-- image -->" or re.fullmatch(r"\|?[-| :]+\|?", s):
            continue
        s, n = repair_ligatures(" ".join(s.split()))
        ligatures += n
        if s in seen:
            duplicates += 1
            continue
        seen.add(s)
        lines.append(s)
    return lines, duplicates, ligatures


def docling_converter():
    """Convertisseur Docling sans OCR (PDF natifs), avec structure des tableaux."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def docling_markdown(converter, path: Path, page_count: int) -> dict[int, str]:
    """Markdown Docling de chaque page du document."""
    doc = converter.convert(path).document
    return {i: doc.export_to_markdown(page_no=i) for i in range(1, page_count + 1)}


def apply_docling(pages: dict[int, Page], markdown: dict[int, str]) -> None:
    """Remplit les lignes nettoyées de chaque page non graphique."""
    for number, page in pages.items():
        if page.graphique:
            continue
        page.lignes, page.doublons_retires, page.ligatures_reparees = clean_markdown(
            markdown.get(number, "")
        )
