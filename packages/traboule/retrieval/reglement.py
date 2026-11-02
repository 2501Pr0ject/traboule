"""Règlement écrit (parties I et II) : structure, tableaux et passages (ADR-0008, 0009, 0011).

- texte et structure lus par PyMuPDF, ligne par ligne avec leur position ; en-têtes et pieds
  de page retirés (« METROPOLE DE LYON – … », version, numéro de page, « Zone X » de l'en-tête) ;
- partie, groupe de zones et zone lus dans les signets ; chapitres (« CHAPITRE n - … ») et
  articles numérotés (« 1.1.2 - … », premier numéro = chapitre) lus dans le texte ; un titre
  sur deux lignes est recollé ;
- partie II : zone mère, libellé de zone, préambule (« Caractère de la zone ») signalé et
  conservé ; « Dispositions communes » des zones UPr1 à UPr7 sans zone ;
- tableaux : pages où PyMuPDF détecte un tableau ; les lignes du tableau sont remplacées par
  les cellules lues par Docling (page convertie seule), à la position du tableau ; si le nombre
  de tableaux diffère entre les deux extracteurs, la page entière est lue par Docling ; si les
  cellules Docling couvrent moins de `MIN_TABLE_COVERAGE` des mots que PyMuPDF lit dans les
  tableaux (cellules écartées par Docling), la page garde le texte PyMuPDF, signalée ;
- pages de navigation écartées et comptées : sommaires, index, pages de garde ; l'index des
  termes définis est gardé comme table (terme, page de la définition dans la partie I) ;
- libellé de zone lu sous le titre « Zone X » ; à défaut (zones UPr1 à UPr7), première phrase
  de la description de la zone dans la nomenclature (§0.2 de la partie I), avec sa page ;
- `zones_applicables` : zone du passage, ou zones du groupe pour les « Dispositions communes »
  des zones UPr1 à UPr7 (le filtre par zone porte sur ce champ) ;
- version lue sur chaque page, passage coupé à chaque changement ; découpage commun
  (`traboule.retrieval.decoupage`) avec les pages réelles de chaque passage ;
- payload : codes de secteur de la zone cités dans le texte (colonne `secteur` de
  `configs/zones_reglement.csv`) et leurs alias (`configs/zones_alias.csv`) ; renvois aux
  chapitres et articles de la partie I (`renvoi_vers`, ADR-0011).

Usage : `uv run python -m traboule.retrieval.reglement`.
"""

import hashlib
import json
import re
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

import typer

from traboule.config import INTERIM_DIR, RAW_DIR
from traboule.contracts.passage import AliasCode, Passage
from traboule.geo.zones_reglement import (
    ALIASES,
    NOMENCLATURE_END,
    NOMENCLATURE_START,
    OUTPUT,
    REGLEMENT,
    VERSION_GPU,
    normalize,
    section_pages,
    token,
)
from traboule.measure import peak_rss_bytes, write_metrics
from traboule.retrieval.cahiers import canonical_version
from traboule.retrieval.decoupage import (
    MAX_PAGES,
    DecoupageError,
    split_block,
    text_page_numbers,
)
from traboule.retrieval.extraction import clean_markdown, docling_converter, read_pages
from traboule.retrieval.renvois import RenvoiError, link_partie_i

OUT_DIR = INTERIM_DIR / "extraction" / "reglement"
SOURCE_ID = "SRC-005"
RUNNING = re.compile(
    r"^(METROPOLE DE LYON\b.*|PLU-H\s*[-–]\s*(MODIFICATION|R[ÉE]VISION|MISE EN COMPATIBILIT).*"
    r"|\d{1,3})$",
    re.I,
)
HEADER_LINES = 5
LIBELLE_MAX_LINES = 3
LIST_ITEM = re.compile(r"^([a-z]|[ivx]+|\d+)[.)]\s|^[-•–]\s?")
MIN_TABLE_COVERAGE = 0.98
WORD = re.compile(r"\w+")
CHAPTER = re.compile(r"^CHAPITRE\s+(\d+|PR[ÉE]LIMINAIRE)\s*[-–]\s*(.+)$", re.I)
# Article numéroté : « 1.1.2 - Titre », « 1.1. Titre » ; au moins deux numéros.
ARTICLE = re.compile(r"^(\d+(?:\.\d+)+)\.?\s*[-–]?\s+(\S.*)$")
PREAMBLE = re.compile(r"^CARACT[ÈE]RE DE LA ZONE$", re.I)
NAVIGATION = re.compile(r"^(SOMMAIRE|INDEX)\b", re.I)
PREAMBLE_PATH = "Caractère de la zone"
COMMON_UPR = "Dispositions communes"
# Entrée de l'index des termes : « Accès du terrain ........ 91 » ou « Orientations … 24 ».
INDEX_ENTRY = re.compile(r"^(.+?)\s*(?:\.{2,}\s*|\s)(\d{1,3})$")


class ReglementError(RuntimeError):
    """Contrôle bloquant de l'extraction du règlement."""


@dataclass
class Bloc:
    chemin: list[str]
    zone: str | None
    zone_libelle: str | None
    est_preambule: bool
    version: str
    debut: int
    lignes: list[tuple[int, str]] = field(default_factory=list)
    libelle_source: str | None = None
    zones_applicables: list[str] | None = None


def zone_code(title: str) -> str:
    """« Zone A 1 » → « A1 » ; « Zone AUs.co » → « AUs.co »."""
    return re.sub(r"^Zone\s+", "", title).replace(" ", "")


def navigation_pages(toc: list[tuple[int, str, int]], page_count: int) -> set[int]:
    """Sommaires, index et pages de garde.

    Page de garde : page d'une entrée qui précède sa première entrée fille (couverture d'une
    partie ou d'un groupe de zones). Les pages sans entrée active (couverture) en font partie.
    """
    pages = set(range(1, min((pg for _, _, pg in toc), default=page_count + 1)))
    for i, (level, title, start) in enumerate(toc):
        end = next((pg for lvl, _, pg in toc[i + 1 :] if lvl <= level), page_count + 1)
        if NAVIGATION.match(title):
            pages |= set(range(start, end))
            continue
        children = [pg for lvl, _, pg in toc[i + 1 :] if lvl > level and start <= pg < end]
        if children:
            pages |= set(range(start, min(children)))
    return pages


def toc_context(toc: list[tuple[int, str, int]], page_count: int) -> dict[int, dict]:
    """Page → partie, groupe de zones et entrée de niveau 3 actifs (signets)."""
    out, active = {}, {}
    starts: dict[int, list[tuple[int, str]]] = {}
    for level, title, page in toc:
        starts.setdefault(page, []).append((level, title))
    for number in range(1, page_count + 1):
        for level, title in starts.get(number, []):
            active = {k: v for k, v in active.items() if k < level} | {level: title}
        out[number] = {
            "partie": active.get(1, ""),
            "groupe": active.get(2) if 3 in active else None,
            "entree": active.get(3),
        }
    return out


def is_title_continuation(line: str) -> bool:
    """Seconde ligne d'un titre : courte, sans ponctuation finale, capitales ou minuscule, et
    pas un élément de liste (« a. … », « - … »)."""
    return (
        not LIST_ITEM.match(line)
        and len(line) < 90
        and not line.endswith((".", ":", ";"))
        and (line.isupper() or line[:1].islower())
    )


def clean_page(lines: list[str], zone_title: str | None) -> list[str]:
    """Lignes d'une page sans en-tête ni pied de page.

    Le « Zone X » de l'en-tête (premières lignes) est retiré une fois : sur la première page
    d'une zone, le titre « Zone X » du corps, qui le suit, est conservé.
    """
    out, header_zone_removed = [], False
    key = zone_title.replace(" ", "").lower() if zone_title else None
    for i, line in enumerate(lines):
        s = " ".join(line.split())
        if not s or RUNNING.match(s):
            continue
        if (
            i < HEADER_LINES
            and key
            and not header_zone_removed
            and s.replace(" ", "").lower() == key
        ):
            header_zone_removed = True
            continue
        out.append(s)
    return out


def article_allowed(numero: str, title: str, chapter_number: str | None, preamble: bool) -> bool:
    """Un article numéroté appartient au chapitre en cours (premier numéro = chapitre) ; hors
    chapitre (dispositions communes UPr), tout numéro est accepté, sauf dans un préambule.
    Son titre ne commence pas par une minuscule (« 5.2.3 - ci-après. » est un renvoi coupé)."""
    if title[:1].islower():
        return False
    if chapter_number is None:
        return not preamble
    return numero.split(".")[0] == chapter_number


def structure(
    pages: dict[int, list[str]],
    context: dict[int, dict],
    versions: dict[int, str],
) -> list[Bloc]:
    """Blocs de texte avec leur chemin : partie > (groupe > zone) > chapitre > articles.

    Libellé de zone : lignes entre le titre « Zone X » et « CARACTÈRE DE LA ZONE » (au plus
    `LIBELLE_MAX_LINES`) ; sans cette ligne, pas de libellé et le texte reste au préambule.
    """
    blocs: list[Bloc] = []
    entry = chapter = chapter_number = zone = libelle = source = None
    articles: list[tuple[str, str]] = []
    preamble = pending = heading = False
    buffer: list[tuple[int, str]] = []
    queue = deque((n, line) for n, lines in pages.items() for line in lines)
    while queue or buffer:
        if not queue:  # fin du texte pendant la lecture d'un libellé : lignes rendues au texte
            queue.extend(buffer)
            buffer, heading = [], False
            continue
        number, line = queue.popleft()
        ctx = context[number]
        if heading and ctx["entree"] != entry:
            queue.extendleft(reversed([*buffer, (number, line)]))
            buffer, heading = [], False
            continue
        if ctx["entree"] != entry:
            entry, chapter, chapter_number, articles = ctx["entree"], None, None, []
            zone = zone_code(entry) if entry and entry.startswith("Zone") else None
            libelle, source, preamble, heading = None, None, zone is not None, False
        base = [ctx["partie"]] + ([ctx["groupe"]] if ctx["groupe"] else [])
        base += [entry] if entry else []
        if heading:
            if PREAMBLE.match(line):
                libelle, buffer, heading = " ".join(t for _, t in buffer), [], False
                source = f"titre de la zone, page {number}"
                continue
            if len(buffer) < LIBELLE_MAX_LINES and not CHAPTER.match(line):
                buffer.append((number, line))
                continue
            queue.extendleft(reversed([*buffer, (number, line)]))
            buffer, heading = [], False
            continue
        title = None
        if m := CHAPTER.match(line):
            chapter_number = "0" if not m.group(1).isdigit() else m.group(1)
            chapter = f"CHAPITRE {m.group(1).upper()} - {m.group(2).strip()}"
            articles, preamble, title = [], False, "chapitre"
        elif (m := ARTICLE.match(line)) and article_allowed(
            m.group(1), m.group(2), chapter_number, preamble
        ):
            numero = m.group(1)
            articles = [a for a in articles if numero.startswith(a[0] + ".")]
            articles.append((numero, f"{numero} - {m.group(2).strip()}"))
            title = "article"
        elif (
            preamble
            and zone
            and libelle is None
            and line.replace(" ", "").lower() == (f"zone{zone}".lower())
        ):
            heading = True
            continue
        elif preamble and PREAMBLE.match(line):
            continue
        elif pending and blocs and not blocs[-1].lignes and is_title_continuation(line):
            bloc = blocs[-1]
            if bloc.chemin[-1] == chapter:
                chapter = f"{chapter} {line}"
            else:
                numero, text = articles[-1]
                articles[-1] = (numero, f"{text} {line}")
            bloc.chemin = bloc.chemin[:-1] + [f"{bloc.chemin[-1]} {line}"]
            continue
        pending = title is not None
        chemin = base + ([chapter] if chapter else []) + [a[1] for a in articles]
        if preamble:
            chemin = base + [PREAMBLE_PATH]
        version = versions[number]
        last = blocs[-1] if blocs else None
        if title or last is None or last.chemin != chemin or last.version != version:
            blocs.append(
                Bloc(chemin, zone, libelle, preamble and zone is not None, version, number)
            )
            blocs[-1].libelle_source = source
            blocs[-1].zones_applicables = [zone] if zone else None
        if not title:
            blocs[-1].lignes.append((number, line))
    for bloc in blocs:
        if bloc.zone and bloc.zone_libelle is None:
            first = next((b for b in blocs if b.zone == bloc.zone and b.zone_libelle), None)
            if first:
                bloc.zone_libelle, bloc.libelle_source = first.zone_libelle, first.libelle_source
    return [b for b in blocs if b.lignes]


def group_zones(toc: list[tuple[int, str, int]]) -> dict[str, list[str]]:
    """Groupe de zones (niveau 2) → codes de ses zones (entrées « Zone X » de niveau 3)."""
    groups: dict[str, list[str]] = {}
    group = None
    for level, title, _ in toc:
        if level <= 2:
            group = title if level == 2 else None
        elif group and title.startswith("Zone "):
            groups.setdefault(group, []).append(zone_code(title))
    return groups


def apply_common_zones(blocs: list[Bloc], groups: dict[str, list[str]]) -> None:
    """« Dispositions communes » d'un groupe : applicables à toutes les zones du groupe."""
    for bloc in blocs:
        if bloc.zone is None and len(bloc.chemin) > 2 and bloc.chemin[2] == COMMON_UPR:
            if not groups.get(bloc.chemin[1]):
                raise ReglementError(f"dispositions communes sans zones : {bloc.chemin[1]}")
            bloc.zones_applicables = groups[bloc.chemin[1]]


def nomenclature_labels(texts: dict[int, str], codes: list[str]) -> dict[str, tuple[str, int]]:
    """Code → (première phrase de sa description, page) dans la nomenclature (§0.2, partie I).

    Dans la nomenclature, le code est seul sur sa ligne, suivi de la description.
    """
    pages = section_pages({n: normalize(t) for n, t in texts.items()}, NOMENCLATURE_START,
                          NOMENCLATURE_END)  # fmt: skip
    lines = [(n, " ".join(x.split())) for n in pages for x in texts[n].splitlines() if x.strip()]
    labels = {}
    for code in codes:
        start = next((i for i, (_, x) in enumerate(lines) if x == code), None)
        if start is None:
            raise ReglementError(f"{code} absent de la nomenclature (§0.2)")
        words = []
        for _, x in lines[start + 1 :]:
            words.append(x)
            if x.endswith("."):
                break
        labels[code] = (" ".join(words), lines[start][0])
    return labels


def apply_nomenclature_labels(blocs: list[Bloc], texts: dict[int, str]) -> list[str]:
    """Libellé des zones sans libellé sous leur titre, repris de la nomenclature."""
    missing = sorted({b.zone for b in blocs if b.zone and b.zone_libelle is None})
    labels = nomenclature_labels(texts, missing) if missing else {}
    for bloc in blocs:
        if bloc.zone in labels:
            text, page = labels[bloc.zone]
            bloc.zone_libelle = text
            bloc.libelle_source = f"§0.2 de la partie I (nomenclature), page {page}"
    return missing


def index_terms(texts: dict[int, str], pages: list[int], printed: dict[int, int]) -> list[dict]:
    """Index des termes définis : terme, page imprimée et page du PDF de sa définition.

    Un terme sur deux lignes est recollé ; les lettres et en-têtes sont ignorés.
    """
    to_pdf = {v: k for k, v in printed.items()}
    terms, pending = [], ""
    for n in pages:
        for raw in texts[n].splitlines():
            line = " ".join(raw.split())
            if not line or RUNNING.match(line) or line == "INDEX" or re.fullmatch(r"[A-Z]", line):
                continue
            if m := INDEX_ENTRY.match(line):
                term = f"{pending} {m.group(1)}".strip(" .")
                page = int(m.group(2))
                terms.append({"terme": term, "page_imprimee": page, "page_pdf": to_pdf.get(page)})
                pending = ""
            else:
                pending = f"{pending} {line}".strip()
    if pending or any(t["page_pdf"] is None for t in terms):
        raise ReglementError("index des termes : entrée incomplète ou page introuvable")
    return terms


def printed_numbers(texts: dict[int, str]) -> dict[int, int]:
    """Page du PDF → numéro imprimé (ligne numérique de l'en-tête)."""
    out = {}
    for n, text in texts.items():
        head = [x.strip() for x in text.splitlines() if x.strip()][:HEADER_LINES]
        number = next((int(x) for x in head if re.fullmatch(r"\d{1,3}", x)), None)
        if number is not None:
            out[n] = number
    return out


def index_term_pages(toc: list[tuple[int, str, int]], page_count: int) -> list[int]:
    """Pages de l'entrée « INDEX » des signets (index des termes de la partie I)."""
    for i, (level, title, start) in enumerate(toc):
        if title.strip().upper() == "INDEX":
            end = next((pg for lvl, _, pg in toc[i + 1 :] if lvl <= level), page_count + 1)
            return list(range(start, end))
    raise ReglementError("index des termes introuvable dans les signets")


def write_index_terms(terms: list[dict], path: Path | None = None) -> None:
    import csv

    path = path or OUT_DIR / "index_termes.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["terme", "page_imprimee", "page_pdf"])
        writer.writeheader()
        writer.writerows(terms)


def page_lines(pdf) -> dict[int, list[tuple[float, float, str]]]:
    """Lignes PyMuPDF de chaque page avec leur position verticale (haut, bas)."""
    out = {}
    for number, page in enumerate(pdf, start=1):
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"])
                if text.strip():
                    lines.append((line["bbox"][1], line["bbox"][3], text))
        out[number] = lines
    return out


def table_boxes(pdf, cache: Path) -> dict[int, list[tuple[float, float]]]:
    """Pages où PyMuPDF détecte un tableau → (haut, bas) de chaque tableau ; mis en cache."""
    if cache.exists():
        return {int(k): [tuple(b) for b in v] for k, v in json.loads(cache.read_text()).items()}
    boxes = {}
    for number, page in enumerate(pdf, start=1):
        found = page.find_tables().tables
        if found:
            boxes[number] = sorted((t.bbox[1], t.bbox[3]) for t in found)
    cache.write_text(json.dumps(boxes))
    return boxes


def table_rows(markdown: str) -> list[str]:
    """Lignes d'un tableau Markdown : cellules non vides séparées par « | », sans répétition."""
    rows = []
    for raw in markdown.splitlines():
        if not raw.strip() or re.fullmatch(r"\|?[-| :]+\|?", raw.strip()):
            continue
        cells = []
        for cell in (" ".join(c.split()) for c in raw.strip().strip("|").split("|")):
            if cell and (not cells or cells[-1] != cell):
                cells.append(cell)
        if cells:
            rows.append(" | ".join(cells))
    return rows


def docling_tables(converter, path: Path, number: int) -> dict:
    """Tableaux Docling d'une page convertie seule (haut, lignes) et Markdown de la page."""
    doc = converter.convert(path, page_range=(number, number)).document
    height = doc.pages[number].size.height
    tables = []
    for table in doc.tables:
        box = table.prov[0].bbox
        top = height - box.t if box.coord_origin.name == "BOTTOMLEFT" else box.t
        tables.append({"haut": top, "lignes": table_rows(table.export_to_markdown(doc=doc))})
    return {
        "tableaux": sorted(tables, key=lambda t: t["haut"]),
        "page": doc.export_to_markdown(page_no=number),
    }


def in_tables(top: float, bottom: float, boxes: list[tuple[float, float]]) -> bool:
    return any(t - 2 <= (top + bottom) / 2 <= b + 2 for t, b in boxes)


def table_coverage(
    lines: list[tuple[float, float, str]], boxes: list[tuple[float, float]], docling: list[str]
) -> float:
    """Part des mots PyMuPDF des tableaux retrouvés dans les cellules Docling."""
    expected = {
        w.lower() for top, bottom, text in lines if in_tables(top, bottom, boxes)
        for w in WORD.findall(text)
    }  # fmt: skip
    found = {w.lower() for line in docling for w in WORD.findall(line)}
    return len(expected & found) / len(expected) if expected else 1.0


def merge_tables(
    lines: list[tuple[float, float, str]], boxes: list[tuple[float, float]], docling: dict
) -> tuple[list[str], set[str], str]:
    """Lignes d'une page à tableaux : texte PyMuPDF hors tableaux, cellules Docling à la place.

    Renvoie (lignes, lignes venues de Docling, mode : « tableaux », « page_docling » si le
    nombre de tableaux diffère, « pymupdf » si la couverture des cellules est insuffisante).
    """
    tables = docling["tableaux"]
    if len(tables) != len(boxes):
        page, _, _ = clean_markdown(docling["page"])
        return page, set(page), "page_docling"
    cells = [line for table in tables for line in table["lignes"]]
    if table_coverage(lines, boxes, cells) < MIN_TABLE_COVERAGE:
        return [text for _, _, text in lines], set(), "pymupdf"
    out: list[tuple[float, list[str]]] = []
    for top, bottom, text in lines:
        if not in_tables(top, bottom, boxes):
            out.append((top, [text]))
    from_docling: set[str] = set()
    for (top, _), table in zip(boxes, tables, strict=True):
        out.append((top, table["lignes"]))
        from_docling |= set(table["lignes"])
    out.sort(key=lambda item: item[0])
    return [line for _, group in out for line in group], from_docling, "tableaux"


def page_versions(texts: dict[int, str]) -> dict[int, str]:
    """Version lue sur chaque page (en-tête), sinon celle de la page précédente."""
    versions, last = {}, None
    for number, text in texts.items():
        last = canonical_version(text) or last
        if last is None:
            raise ReglementError(f"aucune version lue jusqu'à la page {number}")
        versions[number] = last
    return versions


def zone_sectors(path: Path = OUTPUT) -> dict[str, list[str]]:
    """Zone mère → codes de secteur (colonne `secteur` de la correspondance code → chapitre)."""
    import csv

    sectors: dict[str, set[str]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["secteur"] and row["chapitre"].startswith("Zone "):
                sectors.setdefault(zone_code(row["chapitre"]), set()).add(row["secteur"])
    return {zone: sorted(codes) for zone, codes in sectors.items()}


def load_alias(path: Path = ALIASES) -> dict[str, list[AliasCode]]:
    """Code du règlement → alias du zonage (`configs/zones_alias.csv`)."""
    import csv

    out: dict[str, list[AliasCode]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            alias = AliasCode(code_zonage=row["code_zonage"], code_reglement=row["code_reglement"],
                              statut=row["statut"])  # fmt: skip
            out.setdefault(row["code_reglement"], []).append(alias)
    return out


def sector_payload(
    text: str, zone: str | None, sectors: dict[str, list[str]], aliases: dict[str, list[AliasCode]]
) -> dict:
    """Secteurs de la zone cités dans le texte (mot entier) et leurs alias."""
    cited = [code for code in sectors.get(zone or "", []) if token(code).search(text)]
    alias = [a for code in cited for a in aliases.get(code, [])]
    return {"secteurs": cited or None, "alias": alias or None}


def passage_id(doc_id: str, page: int, chemin: list[str], partie: int) -> str:
    key = f"{doc_id}|{page}|{' > '.join(chemin)}|{partie}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def build_passages(
    blocs: list[Bloc],
    doc_id: str,
    text_pages: set[int],
    docling_lines: dict[int, set[str]],
    sectors: dict[str, list[str]] | None = None,
    aliases: dict[str, list[AliasCode]] | None = None,
) -> list[Passage]:
    passages = []
    for bloc in blocs:
        for partie, chunk in enumerate(split_block(bloc.lignes, text_pages=text_pages), start=1):
            from_docling = any(
                line in chunk.texte
                for n in range(chunk.page_debut, chunk.page_fin + 1)
                for line in docling_lines.get(n, ())
            )
            passages.append(
                Passage(
                    passage_id=passage_id(doc_id, bloc.debut, bloc.chemin, partie),
                    texte=chunk.texte,
                    doc_id=doc_id,
                    source_id=SOURCE_ID,
                    version_piece=bloc.version,
                    version_gpu=VERSION_GPU,
                    page_debut=chunk.page_debut,
                    page_fin=chunk.page_fin,
                    chemin=bloc.chemin,
                    extracteur="docling" if from_docling else "pymupdf",
                    zone=bloc.zone,
                    zone_libelle=bloc.zone_libelle,
                    zone_libelle_source=bloc.libelle_source,
                    zones_applicables=bloc.zones_applicables,
                    est_preambule=bloc.est_preambule,
                    **sector_payload(chunk.texte, bloc.zone, sectors or {}, aliases or {}),
                )
            )
    return passages


def attachment(p: Passage) -> str:
    """Niveau de rattachement d'un passage, pour la part du texte rattachée."""
    articles = [c for c in p.chemin if ARTICLE.match(c)]
    has_chapter = any(c.startswith("CHAPITRE") for c in p.chemin)
    if p.est_preambule:
        return "préambule de zone"
    if p.zone:
        return (
            "zone > chapitre > article"
            if articles
            else ("zone > chapitre" if has_chapter else "zone seule")
        )
    if p.chemin[0].startswith("Partie I "):
        return (
            "partie I > chapitre > article"
            if articles
            else ("partie I > chapitre" if has_chapter else "partie I seule")
        )
    return "partie II hors zone"


def extract(path: Path, converter) -> tuple[list[Passage], dict]:
    import pymupdf

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    toc, pages = read_pages(path)
    with pymupdf.open(path) as pdf:
        positioned = page_lines(pdf)
        boxes = table_boxes(pdf, OUT_DIR / "tableaux_pymupdf.json")
    nav = navigation_pages(toc, len(pages))
    context = toc_context(toc, len(pages))
    versions = page_versions({n: p.texte_pymupdf for n, p in pages.items()})
    cache_path = OUT_DIR / "tableaux_docling.json"
    cache = (
        {int(k): v for k, v in json.loads(cache_path.read_text()).items()}
        if (cache_path.exists())
        else {}
    )
    content, docling_lines, modes = {}, {}, {}
    for number, page in pages.items():
        if number in nav or page.graphique:
            continue
        lines = positioned[number]
        if number in boxes:
            if number not in cache:
                cache[number] = docling_tables(converter, path, number)
                cache_path.write_text(json.dumps(cache, ensure_ascii=False))
            merged, docling_lines[number], modes[number] = merge_tables(
                lines, boxes[number], cache[number]
            )
        else:
            merged = [text for _, _, text in lines]
        content[number] = clean_page(merged, context[number]["entree"])
    blocs = structure(content, context, versions)
    texts = {n: p.texte_pymupdf for n, p in pages.items()}
    apply_common_zones(blocs, group_zones(toc))
    labels_from_nomenclature = apply_nomenclature_labels(blocs, texts)
    index_pages = index_term_pages(toc, len(pages))
    terms = index_terms(texts, index_pages, printed_numbers(texts))
    write_index_terms(terms)
    passages = build_passages(
        blocs, path.name, text_page_numbers(pages), docling_lines, zone_sectors(), load_alias()
    )
    passages, renvois = link_partie_i(passages)
    residue = [p.passage_id for p in passages if "METROPOLE DE LYON" in p.texte.upper()
               or re.search(r"APPROBATION \d{4}", p.texte)]  # fmt: skip
    if residue:
        raise ReglementError(f"{len(residue)} passages contiennent un en-tête ou un pied de page")
    covered = {n for p in passages for n in range(p.page_debut, p.page_fin + 1)}
    sizes: Counter = Counter()
    for p in passages:
        sizes[attachment(p)] += len(p.texte)
    total = sum(sizes.values())
    quality = {
        "pages": len(pages),
        "pages_navigation": sorted(nav),
        "index_termes": {"pages": index_pages, "termes": len(terms)},
        "libelles_nomenclature": labels_from_nomenclature,
        "passages_dispositions_communes": sum(
            bool(p.zones_applicables) and p.zone is None for p in passages
        ),
        "pages_graphiques": sorted(n for n, p in pages.items() if p.graphique),
        "pages_tableaux": sorted(boxes),
        "pages_tableaux_docling_entiere": sorted(
            n for n, m in modes.items() if m == "page_docling"
        ),
        "pages_tableaux_pymupdf_couverture": sorted(n for n, m in modes.items() if m == "pymupdf"),
        "pages_texte_sans_passage": sorted(n for n in content if content[n] and n not in covered),
        "passages": len(passages),
        "passages_docling": sum(p.extracteur == "docling" for p in passages),
        "passages_preambule": sum(p.est_preambule for p in passages),
        "zones": len({p.zone for p in passages if p.zone}),
        "part_du_texte": {k: round(v / total, 4) for k, v in sizes.most_common()},
        "versions": dict(Counter(p.version_piece for p in passages)),
        f"passages_au_dela_de_{MAX_PAGES}_pages": [
            (p.page_debut, p.page_fin)
            for p in passages
            if p.page_fin - p.page_debut + 1 > MAX_PAGES
        ],
        "passages_avec_secteurs": sum(bool(p.secteurs) for p in passages),
        "passages_avec_alias": sum(bool(p.alias) for p in passages),
        "renvois_partie_i": dict(renvois.most_common()),
        "passages_avec_renvoi_partie_i": sum(bool(p.renvoi_vers) for p in passages),
        "secondes": round(time.perf_counter() - t0, 1),
    }
    return passages, quality


app = typer.Typer(add_completion=False)


@app.command()
def main() -> None:
    """Extrait les parties I et II du règlement (un seul processus) et écrit les mesures."""
    path = RAW_DIR / REGLEMENT
    try:
        passages, quality = extract(path, docling_converter())
    except (ReglementError, DecoupageError, RenvoiError) as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    (OUT_DIR / "passages.jsonl").write_text(
        "".join(p.model_dump_json() + "\n" for p in passages), encoding="utf-8"
    )
    quality["pic_rss_mo"] = round(peak_rss_bytes() / 2**20)
    write_metrics(INTERIM_DIR / "metrics" / "extraction_reglement.json", quality,
                  {"document": REGLEMENT, "raw_dir": str(RAW_DIR.name)})  # fmt: skip
    typer.echo(f"OK : {quality['passages']} passages, {quality['zones']} zones, "
               f"{len(quality['pages_tableaux'])} pages à tableaux")  # fmt: skip


if __name__ == "__main__":
    app()
