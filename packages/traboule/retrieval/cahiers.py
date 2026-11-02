"""Cahiers communaux et d'arrondissement : structure, passages et mesures de qualité.

- texte Docling (ordre des colonnes), titres repérés sur PyMuPDF (ADR-0008) ;
- chemin d'un passage = entrées actives de la table des matières du cahier (signets du PDF,
  sinon parties du sommaire imprimé page 2) ; dans la partie 4 (OAP), le titre d'OAP
  (« OAP / numéro / nom ») ouvre un passage ;
- partie 4 : pages couvertes selon les signets ou selon le sommaire imprimé (les signets de
  certains cahiers sont décalés) ; titre d'OAP sans numéro (numéro seulement sur la carte de la
  page) repris de la première ligne de la page ;
- contrôle bloquant : chaque OAP citée dans le cahier (renvois, signets) est détectée ou figure
  dans `configs/oap_exceptions.yaml` avec son motif ;
- pièces identiques (`configs/index.yaml`) : sha256 et texte de chaque exemplaire contrôlés ;
  la référence porte tous les secteurs et le titre à citer ;
- en-têtes et pieds de page courants retirés (lignes présentes sur plus de la moitié des
  pages), pages graphiques écartées, passages longs découpés aux limites de phrase ;
- payload ADR-0009 : secteur PLU-H, commune COG 2026 et commune historique, OAP ; version lue
  dans l'en-tête de chaque page (page précédente la plus proche si la page n'en porte pas) ;
  un passage est coupé à chaque changement de version, et porte une seule version.

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
import yaml

from traboule.config import INTERIM_DIR, OAP_EXCEPTIONS, RAW_DIR
from traboule.contracts.passage import Passage
from traboule.measure import peak_rss_bytes, write_metrics
from traboule.retrieval.decoupage import (
    MAX_CHARS,
    MAX_PAGES,
    DecoupageError,
    long_ranges,
    split_block,
    text_page_numbers,
)
from traboule.retrieval.extraction import (
    Page,
    apply_docling,
    docling_converter,
    docling_markdown,
    read_pages,
    repair_ligatures,
)
from traboule.retrieval.index_config import (
    IndexConfigError,
    PieceIdentique,
    check_identical,
    load_identical,
)

RAW_DATE = "2026-11-01"
VERSION_GPU = "200046977_PLUi_20260326"
OUT_DIR = INTERIM_DIR / "extraction" / "cahiers"
# Titre de la partie 4 dans la table des matières (parfois altéré : « … et de4. Orientation… »).
OAP_PART = re.compile(r"^\s*4\.\s*Orientations?\s+d.Am[ée]nagement", re.I)
OAP_NUMBER = re.compile(r"^(\d+(?:\s*[.-]\s*\d+)*)\s*(.*)$")  # « 7.4 », « 11-1 », « 11 -1 »
# Partie du sommaire imprimé : « 4.\tOrientations d'Aménagement et de Programmation (OAP)....52 ».
SOMMAIRE_PART = re.compile(r"^\s*([1-6])\.\s*(.+?)\s*\.{3,}\s*(\d+)\s*$")
SOMMAIRE_PAGES = (2, 3)
# Renvoi à une OAP définie dans une autre pièce : « Site UNESCO (se référer au cahier communal) ».
OAP_REFERRAL = re.compile(r"se\s+r[ée]f[ée]rer", re.I)
# Lignes d'en-tête d'une page de la partie 4, sautées pour lire le titre d'une OAP sans numéro.
OAP_PAGE_HEADER = re.compile(
    r"^(\d{1,3}|PLU-H\b.*|4\.?\s*(Orientations? d.Am[ée]nagement.*)?|"
    r"Orientations? d.Am[ée]nagement.*|Programmation.*)$",
    re.I,
)
# Fragments laissés par une ligature « ti », « tt », « ff », « fi », « fl » codée avec une espace
# dans certains PDF (« parti e », « créati on ») : comptés, non réparés (règle à valider).
SPLIT_LIGATURE = re.compile(
    r"\b\w*(?:ti|tt|ff|fi|fl) (?:e|es|er|ers|on|ons|que|ques|f|fs|ve|ves|el|elle|elles|ère|ères)\b"
)
OAP_REFERENCE = re.compile(r"\bOAP\s*\n?\s*(\d+(?:\.\d+)*)\b")
# En-tête courant : « PLU-H – <commune> – Modification n°4 – Approbation 2024 ».
HEADER_VERSION = re.compile(
    r"PLU-H\s*[-–][^\n]*?[-–]\s*((?:Modification|Mise en compatibilit[ée]|R[ée]vision)"
    r"[^\n]*?[-–]\s*Approbation\s+\d{4})",
    re.I,
)
# Procédure, sur l'en-tête ou la couverture (« MODIFICATION N°4 / Approbation 2024 »).
VERSION = re.compile(
    r"(Modification|Mise\s+en\s+compatibilit[ée]|R[ée]vision)\s*n\s*°\s*(\d+)\s*[-–]?\s*"
    r"Approbation\s*[-–]?\s*(\d{4})",
    re.I,
)
RUNNING_SHARE = 0.5


class CahierError(RuntimeError):
    """Contrôle bloquant de l'extraction d'un cahier."""


def canonical_version(text: str) -> str | None:
    """Procédure sous une graphie unique : « Modification n°4 - Approbation 2024 »."""
    if not (m := VERSION.search(text)):
        return None
    kind = " ".join(m.group(1).split()).lower()
    label = {"modification": "Modification", "révision": "Révision", "revision": "Révision"}
    return f"{label.get(kind, 'Mise en compatibilité')} n°{m.group(2)} - Approbation {m.group(3)}"


def page_versions(pages: dict[int, Page]) -> dict[int, str | None]:
    """Version lue sur chaque page : en-tête courant, sinon couverture (page 1)."""
    versions = {}
    for number, page in pages.items():
        header = HEADER_VERSION.search(page.texte_pymupdf)
        text = header.group(1) if header else page.texte_pymupdf if number == 1 else ""
        versions[number] = canonical_version(text)
    if versions.get(1) is None:
        raise CahierError("version de la pièce introuvable sur la couverture")
    return versions


def version_at(versions: dict[int, str | None], page: int) -> tuple[str, bool]:
    """Version de la page, sinon de la page précédente la plus proche ; indique le repli."""
    for number in range(page, 0, -1):
        if versions.get(number):
            return versions[number], number != page
    raise CahierError(f"aucune version lue jusqu'à la page {page}")


def printed_parts(pages: dict[int, Page]) -> list[tuple[int, str, int]]:
    """Parties (niveau 1) lues dans le sommaire imprimé des pages 2 et 3."""
    parts: dict[str, tuple[int, str, int]] = {}
    for number in SOMMAIRE_PAGES:
        for line in pages[number].texte_pymupdf.splitlines() if number in pages else []:
            if m := SOMMAIRE_PART.match(line):
                title = f"{m.group(1)}. {' '.join(m.group(2).split())}"
                parts.setdefault(m.group(1), (1, title, int(m.group(3))))
    return sorted(parts.values(), key=lambda t: t[2])


def shows_part_heading(page: Page | None, title: str) -> bool:
    """La page porte le titre de partie « n. Mot » (ex. « 4. Orientations »)."""
    number, _, rest = title.partition(".")
    if page is None or not rest.split():
        return False
    heading = re.compile(rf"(?<!\d){number}\.\s*{re.escape(rest.split()[0])}", re.I)
    return bool(heading.search(" ".join(page.texte_pymupdf.split())))


def structure_toc(
    toc: list[tuple[int, str, int]], pages: dict[int, Page]
) -> tuple[list[tuple[int, str, int]], str, list[str]]:
    """Table des matières : signets du PDF, sinon parties du sommaire imprimé.

    Un signet de partie dont la page ne porte pas le titre, alors que la page du sommaire
    imprimé le porte, est corrigé ; chaque correction est consignée.
    """
    printed = {title.split(".")[0]: page for _, title, page in printed_parts(pages)}
    if not any(level == 1 for level, _, _ in toc):
        return printed_parts(pages), "sommaire imprimé", []
    out, corrections = [], []
    for level, title, page in toc:
        number = title.split(".")[0].strip()
        other = printed.get(number) if level == 1 else None
        if (
            other
            and other != page
            and shows_part_heading(pages.get(other), title)
            and not shows_part_heading(pages.get(page), title)
        ):
            corrections.append(f"{title} : page {page} → {other}")
            page = other
        out.append((level, title, page))
    return out, "signets", corrections


def _part_range(toc: list[tuple[int, str, int]], page_count: int) -> range | None:
    top = sorted((page, title) for level, title, page in toc if level == 1)
    for i, (page, title) in enumerate(top):
        if OAP_PART.match(title):
            end = next((p for p, _ in top[i + 1 :] if p > page), page_count + 1)
            return range(page, end)
    return None


def oap_part(
    toc: list[tuple[int, str, int]],
    page_count: int,
    printed: list[tuple[int, str, int]] | None = None,
) -> range | None:
    """Pages de la partie 4 (OAP) : union des plages des signets et du sommaire imprimé."""
    candidates = (_part_range(toc, page_count), _part_range(printed or [], page_count))
    ranges = [r for r in candidates if r]
    if not ranges:
        return None
    return range(min(r.start for r in ranges), max(r.stop for r in ranges))


def oap_titles(pages: dict[int, Page], part: range | None) -> dict[int, str]:
    """Page → « OAP n Nom » pour les titres d'OAP de la partie 4.

    Un titre est la ligne « OAP », suivie du numéro et du nom (sur la même ligne ou la
    suivante) ; un renvoi sans nom (« OAP 0.1 » suivi d'un autre « OAP ») ou vers une autre
    pièce (« se référer au cahier communal ») n'est pas un titre.
    Seul le premier titre d'une page compte (les suivants sont des légendes de carte). Une page
    sans titre qui porte un seul numéro d'OAP sans nom, non titré ailleurs, ouvre cette OAP sous
    le nom de sa première ligne.
    """
    titles, unnamed, referrals = {}, {}, set()
    for number in part or []:
        lines = [line.strip() for line in pages[number].texte_pymupdf.splitlines()]
        labels = set()
        for i, line in enumerate(lines):
            if line != "OAP" or i + 1 >= len(lines) or not (m := OAP_NUMBER.match(lines[i + 1])):
                continue
            numero = re.sub(r"\s+", "", m.group(1))
            name = m.group(2) or (lines[i + 2] if i + 2 < len(lines) else "")
            if OAP_REFERRAL.search(name):
                referrals.add(numero)
                continue
            if name and not name.startswith(("OAP", "PIP")):
                name, _ = repair_ligatures(" ".join(name.split()))
                titles[number] = f"OAP {numero} {name}"
                break
            labels.add(numero)
        labels -= referrals
        if number not in titles and len(labels) == 1:
            first = next((x for x in lines if x and not OAP_PAGE_HEADER.match(x)), None)
            if first and not OAP_REFERRAL.search(first):
                unnamed[number] = (labels.pop(), repair_ligatures(" ".join(first.split()))[0])
    named = {t.split()[1] for t in titles.values()}
    for number, (numero, name) in unnamed.items():
        if numero not in named:
            titles[number] = f"OAP {numero} {name}"
    return dict(sorted(titles.items()))


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
    versions = page_versions(pages)
    printed = printed_parts(pages)
    toc, toc_source, toc_corrections = structure_toc(toc, pages)
    part = oap_part(toc, len(pages), printed)
    oaps = oap_titles(pages, part)
    paths = chemins(toc, len(pages))
    part_title = next(
        (t for level, t, _ in toc + printed if level == 1 and OAP_PART.match(t)), None
    )
    text_pages = text_page_numbers(pages)
    running = running_lines(pages)
    groups: list[dict] = []
    current_oap = None
    version_cuts = 0
    for number, page in pages.items():
        in_part = part is not None and number in part
        current_oap = oaps.get(number, current_oap) if in_part else None
        base = paths[number]
        # Signets décalés : une page de la partie 4 est rattachée à la partie 4.
        if in_part and part_title and not OAP_PART.match(base[0]):
            base = [part_title]
        chemin = base + ([current_oap] if current_oap else [])
        lines = [line for line in page.lignes if line not in running]
        version, fallback = version_at(versions, number)
        same_path = bool(groups) and groups[-1]["chemin"] == chemin
        if not same_path or groups[-1]["version"] != version:
            version_cuts += same_path
            groups.append(
                {"chemin": chemin, "oap": current_oap, "debut": number, "lignes": [],
                 "version": version, "repli": fallback}
            )  # fmt: skip
        groups[-1]["lignes"].extend((number, line) for line in lines)
    passages, fallbacks, too_long = [], 0, []
    for g in groups:
        chunks = split_block(g["lignes"], text_pages=text_pages)
        too_long += [(c.page_debut, c.page_fin) for c in long_ranges(chunks)]
        fallbacks += g["repli"] * len(chunks)
        for partie, chunk in enumerate(chunks, start=1):
            passages.append(
                Passage(
                    passage_id=passage_id(doc_id, g["debut"], g["chemin"], partie),
                    texte=chunk.texte,
                    doc_id=doc_id,
                    source_id="SRC-005",
                    version_piece=g["version"],
                    version_gpu=VERSION_GPU,
                    page_debut=chunk.page_debut,
                    page_fin=chunk.page_fin,
                    chemin=g["chemin"],
                    extracteur="docling",
                    oap=g["oap"],
                    **commune,
                )  # fmt: skip
            )
    cited_texts = [p.texte_pymupdf for p in pages.values()] + [t for _, t, _ in toc]
    referenced = {m.group(1) for text in cited_texts for m in OAP_REFERENCE.finditer(text)}
    detected = {t.split()[1] for t in oaps.values()}
    return passages, {
        "structure": toc_source,
        "signets_corriges": toc_corrections,
        "partie_oap": [part.start, part.stop - 1] if part else None,
        "version_piece": versions[1],
        "passages_version_hors_couverture": sum(p.version_piece != versions[1] for p in passages),
        "passages_version_par_repli": fallbacks,
        "coupures_de_version": version_cuts,
        f"passages_au_dela_de_{MAX_PAGES}_pages": too_long,
        "en_tetes_retires": sum(1 for p in pages.values() for line in p.lignes if line in running),
        "oap_detectees": sorted(set(oaps.values()), key=oap_order),
        "oap_citees_non_detectees": sorted(referenced - detected - {"0"}),
    }  # fmt: skip


def load_oap_exceptions(path: Path = OAP_EXCEPTIONS) -> dict[tuple[str, str], str]:
    """(ressource, numéro d'OAP) → motif ; une exception sans motif ni décision est refusée."""
    entries = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("exceptions") or []
    exceptions = {}
    for entry in entries:
        if not all(entry.get(k) for k in ("ressource", "oap", "motif", "decision")):
            raise CahierError(f"exception d'OAP incomplète : {entry}")
        exceptions[(entry["ressource"], str(entry["oap"]))] = entry["motif"]
    return exceptions


def check_oaps(resource: str, missing: list[str], exceptions: dict[tuple[str, str], str]) -> dict:
    """Contrôle bloquant : chaque OAP citée non détectée figure dans les exceptions."""
    unexplained = [n for n in missing if (resource, n) not in exceptions]
    if unexplained:
        raise CahierError(f"{resource} : OAP citées non détectées sans exception {unexplained}")
    return {n: exceptions[(resource, n)] for n in missing}


def shared_payload(group: PieceIdentique) -> dict:
    """Payload d'une pièce commune à plusieurs secteurs : secteurs, commune et titre à citer."""
    return {
        "secteurs_pluh": list(group.secteurs),
        "code_commune_cog2026": group.code_commune_cog2026,
        "commune_historique": group.code_commune_cog2026,
        "titre_piece": group.titre,
    }


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
    exceptions: dict[tuple[str, str], str] | None = None,
    shared: dict[str, PieceIdentique] | None = None,
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
    group = (shared or {}).get(resource)
    commune = shared_payload(group) if group else commune_of(pdf.name, sectors, communes)
    passages, quality = build_passages(pdf.name, toc, pages, commune)
    quality["oap_exceptions"] = check_oaps(
        resource, quality["oap_citees_non_detectees"], exceptions or {}
    )
    # Texte brut ; la réparation des ligatures écrit passages.jsonl (traboule.retrieval.ligatures).
    (out / "passages_brut.jsonl").write_text(
        "".join(p.model_dump_json() + "\n" for p in passages), encoding="utf-8"
    )
    graphic = [n for n, p in pages.items() if p.graphique]
    return {
        "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
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


def check_group(group: PieceIdentique, results: dict[str, dict]) -> None:
    """Contrôle bloquant des pièces identiques, sur les passages bruts extraits."""
    texts = {
        r: "\n".join(
            json.loads(line)["texte"] for line in (OUT_DIR / r / "passages_brut.jsonl").open()
        )
        for r in group.exemplaires
    }
    check_identical(group, {r: results[r]["sha256"] for r in group.exemplaires}, texts)


app = typer.Typer(add_completion=False)


@app.command()
def main(
    ressource: Annotated[list[str], typer.Option(help="Ressource SRC-005 du 2026-11-01")],
) -> None:
    """Extrait les cahiers demandés (un seul processus) et écrit les mesures."""
    converter = docling_converter()
    communes = load_passage_communes()
    sectors = sector_codes(RAW_DIR / PLAN_DE_SECTEURS)
    exceptions = load_oap_exceptions()
    groups = load_identical()
    shared = {g.reference: g for g in groups}
    results = {}
    try:
        for name in ressource:
            typer.echo(f"  {name} …")
            results[name] = extract(name, converter, communes, sectors, RAW_DIR, exceptions, shared)
        for group in groups:
            if all(r in results for r in group.exemplaires):
                check_group(group, results)
    except (CahierError, DecoupageError, IndexConfigError) as exc:
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
