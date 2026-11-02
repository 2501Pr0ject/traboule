"""Découpage des blocs de texte en passages, chacun avec ses pages réelles.

Commun à toutes les pièces (cahiers, règlement) : un bloc est une suite de lignes, chacune avec
sa page. Au-delà de `MAX_CHARS` caractères, il est découpé aux limites de phrase ; chaque
passage porte la plage des pages de ses propres lignes, jamais celle du bloc entier.

Redécoupage par paragraphe (décision du porteur, 2026-11-02) : un passage qui couvre au moins
`MIN_TEXT_PAGES_TO_SPLIT` pages de texte (pages non graphiques d'au moins `TEXT_PAGE_MIN_CHARS`
caractères), ou qui dépasse `MAX_CHARS` faute de fin de phrase, est redécoupé aux limites de
ligne (paragraphes). Un passage long à cause de cartes intercalées reste tel quel.

Contrôles :
- bloquant : un bloc de plusieurs pages découpé en plusieurs passages qui reprendraient tous sa
  plage entière (`DecoupageError`) ;
- signalement : passages dont la plage dépasse `MAX_PAGES` pages (`long_ranges`).
"""

import re
from dataclasses import dataclass

MAX_CHARS = 2000
# Seuil fixé d'après la distribution observée sur les 76 cahiers (2026-11-02) : 99 % des
# passages couvrent au plus 4 pages ; au-delà, des pages graphiques sont intercalées.
MAX_PAGES = 4
TEXT_PAGE_MIN_CHARS = 400
MIN_TEXT_PAGES_TO_SPLIT = 4
SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+")


class DecoupageError(RuntimeError):
    """Contrôle bloquant du découpage."""


@dataclass(frozen=True)
class Chunk:
    texte: str
    page_debut: int
    page_fin: int

    @property
    def pages(self) -> int:
        return self.page_fin - self.page_debut + 1


def chunk_spans(text: str, max_chars: int = MAX_CHARS) -> list[tuple[int, int]]:
    """Intervalles (début, fin) des morceaux, coupés aux limites de phrase."""
    if len(text) <= max_chars:
        return [(0, len(text))]
    sentences, start = [], 0
    for m in SENTENCE_END.finditer(text):
        sentences.append((start, m.start()))
        start = m.end()
    sentences.append((start, len(text)))
    spans: list[tuple[int, int]] = []
    for s, e in sentences:
        if spans and e - spans[-1][0] <= max_chars:
            spans[-1] = (spans[-1][0], e)
        else:
            spans.append((s, e))
    return spans


def split_long(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Découpe un texte trop long aux limites de phrase."""
    return [text[s:e] for s, e in chunk_spans(text, max_chars)]


def text_page_numbers(pages: dict, min_chars: int = TEXT_PAGE_MIN_CHARS) -> set[int]:
    """Pages de texte : non graphiques, d'au moins `min_chars` caractères (PyMuPDF)."""
    return {n for n, p in pages.items() if not p.graphique and p.caracteres >= min_chars}


def needs_paragraph_split(
    length: int, pages: set[int], text_pages: set[int], max_chars: int = MAX_CHARS
) -> bool:
    return length > max_chars or len(pages & text_pages) >= MIN_TEXT_PAGES_TO_SPLIT


def paragraph_spans(
    bounds: list[tuple[int, int, int]], text_pages: set[int], max_chars: int = MAX_CHARS
) -> list[tuple[int, int]]:
    """Regroupe des lignes (début, fin, page) en morceaux, coupés aux limites de ligne."""
    spans: list[tuple[int, int, set[int]]] = []
    for s, e, page in bounds:
        if spans:
            start, _, pages = spans[-1]
            if not needs_paragraph_split(e - start, pages | {page}, text_pages, max_chars):
                spans[-1] = (start, e, pages | {page})
                continue
        spans.append((s, e, {page}))
    return [(s, e) for s, e, _ in spans]


def split_block(
    lines: list[tuple[int, str]],
    max_chars: int = MAX_CHARS,
    text_pages: set[int] | None = None,
) -> list[Chunk]:
    """Découpe un bloc de lignes (page, texte) ; chaque morceau porte les pages de ses lignes.

    `text_pages` (pages de texte du document) active le redécoupage par paragraphe.
    """
    lines = [(page, line.strip()) for page, line in lines if line.strip()]
    if not lines:
        return []
    bounds, pos = [], 0
    for page, line in lines:
        bounds.append((pos, pos + len(line), page))
        pos += len(line) + 1
    text = " ".join(line for _, line in lines)

    def pages_of(s: int, e: int) -> set[int]:
        return {page for ls, le, page in bounds if ls < e and le > s}

    spans = []
    for s, e in chunk_spans(text, max_chars):
        pages = pages_of(s, e)
        if text_pages is not None and needs_paragraph_split(e - s, pages, text_pages, max_chars):
            inner = [(max(ls, s), min(le, e), p) for ls, le, p in bounds if ls < e and le > s]
            spans += paragraph_spans(inner, text_pages, max_chars)
        else:
            spans.append((s, e))
    chunks = []
    for s, e in spans:
        pages = pages_of(s, e)
        chunks.append(Chunk(text[s:e], min(pages), max(pages)))
    first, last = lines[0][0], lines[-1][0]
    if (
        len(chunks) > 1
        and last > first
        and all((c.page_debut, c.page_fin) == (first, last) for c in chunks)
    ):
        raise DecoupageError(f"bloc des pages {first}-{last} : passages sur la plage entière")
    return chunks


def long_ranges(chunks: list[Chunk], max_pages: int = MAX_PAGES) -> list[Chunk]:
    """Passages dont la plage dépasse `max_pages` pages, à signaler."""
    return [c for c in chunks if c.pages > max_pages]
