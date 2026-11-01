"""Correspondance code de zone (SRC-002) → chapitre du règlement écrit (SRC-005).

Le règlement est organisé par zone mère (33 chapitres « Zone … »). Règles, dans cet ordre
(colonne `methode`) :
- `exact` : le code est le titre d'un chapitre ;
- `suffixe` : le code sans ses minuscules finales après un chiffre est un chapitre
  (`UCe1a` → `UCe1`) ;
- `au_differee` : `AU1`, `AU2`, `AU3` → chapitre « Zone AU » (ouverture différée) ;
- `au_reference` : `AU<X>` → chapitre « Zone AUs.co », zone U de référence `U<X>` ;
- `stecal` : code `<zone>s` dont la nomenclature (partie I, §0.2) nomme les déclinaisons
  numérotées (`A2s1`, `A2s2`…), régies par la partie III du règlement, non ingérée : pas de
  chapitre, motif d'abstention `document_non_ingere` (ADR-0010) ; `numeros_stecal` liste les
  numéros présents dans le zonage, le numéro d'un objet se lisant dans son attribut `stecal` ;
- `secteur` : code nommé « secteur <code> » dans le chapitre de sa zone (`UPpa` → `UPp`) ;
- `autre_document` : `SECTSAUV`, régi par le PSMV du Vieux-Lyon (non ingéré) ;
- `libelong_gpu` : le libellé long que renvoie le GPU pour le code (preuve enregistrée dans
  `configs/preuves_gpu/<code>.json`) est le texte du règlement qui décrit une zone mère ; le
  secteur ne se rapproche que par la table d'alias fermée `configs/zones_alias.csv`, jamais
  par une normalisation générale des codes (`alias_statut` : probable ou confirmé) ;
- `non_rattache` : aucune règle ne s'applique ; interdit (contrôle bloquant).

Chaque rattachement porte une citation extraite du texte du règlement (jamais écrite à la
main) et la page où elle se trouve. `secteur` désigne le code dont les dispositions propres
doivent être vérifiées dans le chapitre applicable (`dispositions_secteur`, ADR-0009).

Usage : `uv run python -m traboule.geo.zones_reglement [--check]` ; enregistrer une preuve GPU :
`uv run python -m traboule.geo.zones_reglement --preuve-gpu UCe3-p --chapitre UCe3`.
"""

import csv
import io
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from traboule.config import RAW_DIR, ROOT
from traboule.contracts.reponse import MotifAbstention

RAW_DATE = "2026-10-28"
REGLEMENT = f"SRC-005/{RAW_DATE}/reglement_ecrit/200046977_reglement_20260326.pdf"
ZONAGE = f"SRC-002/{RAW_DATE}/zonage/zonage.geojson"
VERSION_GPU = "200046977_PLUi_20260326"
OUTPUT = ROOT / "configs" / "zones_reglement.csv"
EXPECTED_CHAPTERS = 33
EVIDENCE_DIR = ROOT / "configs" / "preuves_gpu"
ALIASES = ROOT / "configs" / "zones_alias.csv"
ALIAS_STATUSES = ("probable", "confirmé")
GPU_ZONE_URBA = "https://apicarto.ign.fr/api/gpu/zone-urba"
GPU_FIELDS = ("libelle", "libelong", "typezone", "idurba", "partition", "datvalid", "nomfic")
GPU_SEED = "20261101"
DEFERRED_AU = ("AU1", "AU2", "AU3")
SAFEGUARDED = "SECTSAUV"
# Document qui porte les règles, selon la méthode ; un document non ingéré est un signal
# structurel d'abstention (ADR-0010).
DOCUMENTS = {
    "exact": "règlement écrit, partie II",
    "suffixe": "règlement écrit, partie II",
    "au_differee": "règlement écrit, partie II",
    "au_reference": "règlement écrit, partie II",
    "secteur": "règlement écrit, partie II",
    "stecal": "partie III, non ingérée",
    "autre_document": "PSMV du Vieux-Lyon, non ingéré",
    "libelong_gpu": "règlement écrit, partie II",
    "non_rattache": "",
}
ABSTENTION = {
    "stecal": MotifAbstention.DOCUMENT_NON_INGERE.value,
    "autre_document": MotifAbstention.AUTRE_DOCUMENT.value,
}
# Repères des citations des règles (texte du règlement, cherchés dans la page indiquée).
NOMENCLATURE_START = "0.2 - Nomenclature des zones et des secteurs de zones"
NOMENCLATURE_END = "0.3 - Règles applicables"
ANCHOR_AUSCO = re.compile(
    r"Dès lors que les conditions d’ouverture à l’urbanisation sont réunies[^.]*\."
)
ANCHOR_AU = "AU1 : mixte"
ANCHOR_PSMV = re.compile(r"Le présent PLU-H s’applique[^.]*?\(PSMV\)[^.]*\.")
ANCHOR_PARTIE_I = "0.1 - Champ d’application du PLU-H"
VERSION_HEADER = re.compile(
    r"PLU-H – ((?:MODIFICATION|REVISION|RÉVISION|MISE EN COMPATIBILITE)[^0-9]*\d+"
    r" – APPROBATION \d{4})"
)


class CorrespondanceError(RuntimeError):
    """Contrôle bloquant de la correspondance."""


@dataclass(frozen=True)
class Rattachement:
    code_zone: str
    methode: str
    document: str
    chapitre: str
    page_chapitre: int | None
    secteur: str
    dispositions_secteur: str
    pages_dispositions_secteur: str
    numeros_stecal: str
    alias_statut: str
    zone_u_reference: str
    chapitre_u: str
    page_chapitre_u: int | None
    citation: str
    source_citation: str
    citation_page_pdf: int | None
    preuve: str
    version_piece: str
    version_gpu: str
    abstention_motif: str


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def token(code: str) -> re.Pattern:
    """Le code comme mot entier (pas de lettre, chiffre ou tiret collé)."""
    return re.compile(rf"(?<![A-Za-z0-9-]){re.escape(code)}(?![A-Za-z0-9-])")


def chapters(toc: list[tuple[int, str, int]], page_count: int) -> dict[str, tuple[int, int]]:
    """Chapitres « Zone X » : nom sans espaces → (page de début, page de fin)."""
    entries = sorted((page, title) for _, title, page in toc)
    result = {}
    for i, (page, title) in enumerate(entries):
        if m := re.match(r"\s*Zone\s+(.+?)\s*$", title):
            following = [p for p, _ in entries[i + 1 :] if p > page]
            end = (following[0] - 1) if following else page_count
            result[m.group(1).replace(" ", "")] = (page, end)
    return result


def strip_suffix(code: str) -> str:
    """Retire les minuscules finales qui suivent un chiffre (`URm1c` → `URm1`)."""
    return re.sub(r"(?<=\d)[a-z]+$", "", code)


def sentence_with(text: str, pattern: re.Pattern, width: int = 200) -> str | None:
    """Phrase de `text` (normalisé) qui contient `pattern` ; extrait borné si elle est longue."""
    m = pattern.search(text)
    if not m:
        return None
    starts = [s.end() for s in re.finditer(r"[.!?](?=\s)", text[: m.start()])]
    start = starts[-1] if starts else 0
    end_m = re.search(r"[.!?](?=\s|$)", text[m.end() :])
    end = m.end() + end_m.end() if end_m else len(text)
    if end - start > 2 * width + 1:
        start, end = max(start, m.start() - width), min(end, m.end() + width)
    return text[start:end].strip()


def extract(
    pages: dict[int, str], page_range: range, pattern: re.Pattern
) -> tuple[str, int] | tuple[None, None]:
    """Texte exact du plus court passage qui correspond à `pattern`, avec sa page."""
    for p in page_range:
        matches = [m.group(0) for m in pattern.finditer(pages.get(p, ""))]
        if matches:
            return min(matches, key=len), p
    return None, None


def find(
    pages: dict[int, str], page_range: range, pattern: re.Pattern
) -> tuple[str, int] | tuple[None, None]:
    """Première phrase contenant `pattern` dans les pages données, avec sa page."""
    for p in page_range:
        if p in pages and (s := sentence_with(pages[p], pattern)):
            return s, p
    return None, None


def pages_citing(pages: dict[int, str], page_range: tuple[int, int], code: str) -> list[int]:
    pattern = token(code)
    return [p for p in range(page_range[0], page_range[1] + 1) if pattern.search(pages.get(p, ""))]


def section_pages(pages: dict[int, str], start: str, end: str) -> range:
    """Pages d'une section de la partie I, de son titre au titre de la suivante (incluse).

    Une page qui contient les deux titres (sommaire) n'est pas le début de la section.
    """
    first = next(p for p in sorted(pages) if start in pages[p] and end not in pages[p])
    last = next(p for p in sorted(pages) if p > first and end in pages[p])
    return range(first, last + 1)


def version_of(pages: dict[int, str], page: int | None) -> str:
    m = VERSION_HEADER.search(pages.get(page, "")) if page else None
    return m.group(1) if m else ""


def fold(text: str) -> str:
    """Texte replié (minuscules sans accents, ponctuation en espaces), de même longueur."""
    out = []
    for ch in text:
        d = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode().lower()
        out.append(d[0] if d and d[0].isalnum() else " ")
    return "".join(out)


def find_folded(
    pages: dict[int, str], page_range: range, phrase: str, words: int = 12
) -> tuple[str, int] | tuple[None, None]:
    """Phrase du règlement qui contient les `words` premiers mots de `phrase`, repliés."""
    keys = re.findall(r"[a-z0-9]+", fold(phrase))[:words]
    if not keys:
        return None, None
    pattern = re.compile(r"(?<![a-z0-9])" + r"\s+".join(keys) + r"(?![a-z0-9])")
    for p in page_range:
        text = pages.get(p, "")
        if m := pattern.search(fold(text)):
            span = text[m.start() : m.end()]
            return sentence_with(text, re.compile(re.escape(span))), p
    return None, None


def load_evidence(directory: Path = EVIDENCE_DIR) -> dict[str, dict]:
    """Preuves GPU enregistrées (`configs/preuves_gpu/<code>.json`), par code de zonage."""
    if not directory.exists():
        return {}
    evidence = {}
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        evidence[data["code_zonage"]] = data | {"fichier": path.relative_to(ROOT).as_posix()}
    return evidence


def load_aliases(path: Path = ALIASES) -> dict[str, dict]:
    """Table d'alias fermée : code du zonage → code du règlement, statut et preuve."""
    if not path.exists():
        return {}
    aliases = {}
    for row in csv.DictReader(path.open(encoding="utf-8")):
        if row["statut"] not in ALIAS_STATUSES:
            raise CorrespondanceError(f"alias {row['code_zonage']} : statut {row['statut']!r}")
        if row["code_zonage"] in aliases:
            raise CorrespondanceError(f"alias en double : {row['code_zonage']}")
        aliases[row["code_zonage"]] = row
    return aliases


def gpu_libelong(code: str, evidence: dict) -> str:
    """Libellé long renvoyé par le GPU, après contrôle de la cohérence de la preuve."""
    zones = [z for point in evidence["points"] for z in point["zones"]]
    if not zones or any(len(point["zones"]) != 1 for point in evidence["points"]):
        raise CorrespondanceError(f"{code} : preuve GPU sans zone unique par point")
    if any(z["libelle"] != code for z in zones):
        raise CorrespondanceError(f"{code} : le GPU renvoie un autre libellé")
    if any((z["idurba"] or "").lower() != VERSION_GPU.lower() for z in zones):
        raise CorrespondanceError(f"{code} : preuve GPU d'une autre version du document")
    libelongs = {z["libelong"] for z in zones}
    if len(libelongs) != 1 or not next(iter(libelongs)):
        raise CorrespondanceError(f"{code} : libellés longs absents ou divergents")
    return libelongs.pop()


def match_code(
    code: str,
    chaps: dict[str, tuple[int, int]],
    pages: dict[int, str],
    evidence: dict[str, dict] | None = None,
    aliases: dict[str, dict] | None = None,
) -> Rattachement:
    """Rattache un code de zone selon les règles, dans l'ordre."""
    evidence, aliases = evidence or {}, aliases or {}
    nomenclature = section_pages(pages, NOMENCLATURE_START, NOMENCLATURE_END)
    row = dict.fromkeys(f.name for f in fields(Rattachement))
    row |= {"code_zone": code, "chapitre": "", "secteur": "", "dispositions_secteur": "",
            "pages_dispositions_secteur": "", "numeros_stecal": "", "alias_statut": "",
            "zone_u_reference": "", "chapitre_u": "", "preuve": "",
            "citation": "", "version_gpu": VERSION_GPU}  # fmt: skip

    def chapter_cite(name: str, pattern: re.Pattern) -> tuple[str | None, int | None]:
        start, end = chaps[name]
        return find(pages, range(start, end + 1), pattern)

    def sector(sector_code: str, chapter_name: str) -> None:
        cited = pages_citing(pages, chaps[chapter_name], sector_code)
        row.update(
            secteur=sector_code,
            dispositions_secteur="oui" if cited else "non",
            pages_dispositions_secteur=" ".join(map(str, cited)),
        )

    if code in chaps:
        # Titre du chapitre et libellé court de la zone (avant « CARACTÈRE DE LA ZONE », sans
        # le tiret long de l'en-tête courant) ;
        # à défaut (libellé long), le titre du chapitre seul.
        spaced = r"\s*".join(map(re.escape, code))
        start, end = chaps[code]
        chapter_pages = range(start, end + 1)
        labelled = re.compile(rf"Zone\s+{spaced}(?![A-Za-z0-9])\s+[^.–]{{1,120}}?(?=\s+CARACT)")
        cite, page = extract(pages, chapter_pages, labelled)
        if not cite:
            cite, page = extract(
                pages, chapter_pages, re.compile(rf"Zone\s+{spaced}(?![A-Za-z0-9])")
            )
        row |= {"methode": "exact", "chapitre": f"Zone {code}", "citation": cite or ""}
        row["citation_page_pdf"] = page
    elif code == SAFEGUARDED:
        partie_i = section_pages(pages, ANCHOR_PARTIE_I, NOMENCLATURE_START)
        cite, page = extract(pages, partie_i, ANCHOR_PSMV)
        row |= {"methode": "autre_document", "citation": cite or "", "citation_page_pdf": page}
    elif code in DEFERRED_AU and "AU" in chaps:
        cite, page = chapter_cite("AU", re.compile(re.escape(ANCHOR_AU)))
        row |= {"methode": "au_differee", "chapitre": "Zone AU", "citation": cite or "",
                "citation_page_pdf": page}  # fmt: skip
        sector(code, "AU")
    elif strip_suffix(code) != code and strip_suffix(code) in chaps:
        parent = strip_suffix(code)
        cite, page = find(pages, nomenclature, token(code))
        if not cite:
            cite, page = chapter_cite(parent, token(code))
        methode = "suffixe"
        if not cite and code == f"{parent}s":
            # STECAL : la nomenclature nomme ses déclinaisons numérotées (A2s1, A2s2, etc.).
            cite, page = find(pages, nomenclature, re.compile(rf"{re.escape(code)}\d"))
            methode = "stecal"
        if cite:
            row |= {"methode": methode, "chapitre": f"Zone {parent}", "citation": cite,
                    "citation_page_pdf": page}  # fmt: skip
            sector(code, parent)
        else:
            row["methode"] = "non_rattache"
    elif code.startswith("AU") and "AUs.co" in chaps:
        ref = "U" + code[2:]
        target = ref if ref in chaps else strip_suffix(ref) if strip_suffix(ref) in chaps else None
        if target is None:
            row["methode"] = "non_rattache"
        else:
            start, end = chaps["AUs.co"]
            cite, page = extract(pages, range(start, end + 1), ANCHOR_AUSCO)
            row |= {"methode": "au_reference", "chapitre": "Zone AUs.co", "zone_u_reference": ref,
                    "chapitre_u": f"Zone {target}", "page_chapitre_u": chaps[target][0],
                    "citation": cite or "", "citation_page_pdf": page}  # fmt: skip
            if target != ref:
                sector(ref, target)
    else:
        parent = re.sub(r"[a-z]+$", "", code)
        candidates = [p for p in (parent, code[:-1]) if p != code and p in chaps]
        named = re.compile(rf"secteurs?\s+{re.escape(code)}(?![A-Za-z0-9])")
        hits = [(p, *chapter_cite(p, named)) for p in candidates]
        hit = next((h for h in hits if h[1]), None)
        if hit:
            row |= {"methode": "secteur", "chapitre": f"Zone {hit[0]}", "citation": hit[1],
                    "citation_page_pdf": hit[2]}  # fmt: skip
            sector(code, hit[0])
        elif code in evidence and evidence[code]["chapitre_candidat"] in chaps:
            ev, target = evidence[code], evidence[code]["chapitre_candidat"]
            libelong = gpu_libelong(code, ev)
            start, end = chaps[target]
            in_chapter, _ = find_folded(pages, range(start, end + 1), libelong)
            cite, page = find_folded(pages, nomenclature, libelong)
            if cite and in_chapter:
                zones = [z for point in ev["points"] for z in point["zones"]]
                row |= {"methode": "libelong_gpu", "chapitre": f"Zone {target}", "citation": cite,
                        "citation_page_pdf": page,
                        "preuve": f"API Carto GPU zone-urba, {ev['requete_le'][:10]} : "
                                  f"{len(ev['points'])} points, libelle {code}, idurba "
                                  f"{zones[0]['idurba']} ({ev['fichier']})"}  # fmt: skip
                if code in aliases:
                    alias = aliases[code]["code_reglement"]
                    if any(token(code).search(text) for text in pages.values()):
                        raise CorrespondanceError(
                            f"{code} figure dans le règlement : alias inutile"
                        )
                    if not pages_citing(pages, chaps[target], alias):
                        raise CorrespondanceError(f"alias {alias} absent du chapitre {target}")
                    sector(alias, target)
                    row["alias_statut"] = aliases[code]["statut"]
            else:
                row["methode"] = "non_rattache"
        else:
            row["methode"] = "non_rattache"
    if row["methode"] == "stecal":
        # Règles dans la partie III, non ingérée : pas de chapitre applicable.
        row |= {"chapitre": "", "dispositions_secteur": "", "pages_dispositions_secteur": ""}
    if row["chapitre"]:
        row["page_chapitre"] = chaps[row["chapitre"].removeprefix("Zone ")][0]
    page = row.get("citation_page_pdf")
    if row["methode"] == "exact":
        row["source_citation"] = "titre"
    elif row["methode"] in ("suffixe", "stecal", "libelong_gpu"):
        row["source_citation"] = "§0.2" if page in nomenclature else "chapitre"
    elif row["methode"] == "secteur":
        row["source_citation"] = "chapitre"
    elif row["methode"] == "non_rattache":
        row["source_citation"] = ""
    else:
        row["source_citation"] = "page dédiée"
    row["document"] = DOCUMENTS[row["methode"]]
    row["abstention_motif"] = ABSTENTION.get(row["methode"], "")
    row["version_piece"] = version_of(pages, page)
    return Rattachement(**row)


def build(
    codes: list[str],
    toc: list[tuple[int, str, int]],
    pages: dict[int, str],
    stecal: dict[str, list[str]] | None = None,
    evidence: dict[str, dict] | None = None,
    aliases: dict[str, dict] | None = None,
) -> list[Rattachement]:
    """Rattache tous les codes et applique les contrôles bloquants.

    `stecal` : numéros de STECAL présents dans le zonage, par code (attribut `stecal`) ;
    `evidence` : preuves GPU ; `aliases` : table d'alias fermée.
    """
    chaps = chapters(toc, max(pages))
    stecal, aliases = stecal or {}, aliases or {}
    rows = [
        replace(
            match_code(c, chaps, pages, evidence, aliases),
            numeros_stecal=" ".join(stecal.get(c, [])),
        )
        for c in sorted(set(codes))
    ]
    unused = sorted(set(aliases) - {r.code_zone for r in rows if r.alias_statut})
    if unused:
        raise CorrespondanceError(f"alias non appliqués : {unused}")
    orphans = [
        c
        for c in stecal
        if c in set(codes) and c not in {r.code_zone for r in rows if r.methode == "stecal"}
    ]
    if orphans:
        raise CorrespondanceError(f"numéros de STECAL sur des codes non STECAL : {orphans}")
    for r in rows:
        if r.methode != "non_rattache":
            if not r.citation:
                raise CorrespondanceError(f"{r.code_zone} : rattachement sans citation")
            if r.citation not in pages[r.citation_page_pdf]:
                raise CorrespondanceError(f"{r.code_zone} : citation absente de sa page")
    unmatched = sorted(r.code_zone for r in rows if r.methode == "non_rattache")
    if unmatched:
        raise CorrespondanceError(f"codes non rattachés : {unmatched}")
    return rows


def to_csv(rows: list[Rattachement]) -> str:
    buffer = io.StringIO()
    names = [f.name for f in fields(Rattachement)]
    writer = csv.DictWriter(buffer, fieldnames=names, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: "" if v is None else v for k, v in asdict(r).items()})
    return buffer.getvalue()


def read_reglement(path: Path) -> tuple[list[tuple[int, str, int]], dict[int, str]]:
    """Table des matières et texte normalisé de chaque page (PyMuPDF, extra `pdf`)."""
    import pymupdf

    with pymupdf.open(path) as pdf:
        toc = [(level, title, page) for level, title, page in pdf.get_toc()]
        pages = {i + 1: normalize(pdf[i].get_text()) for i in range(pdf.page_count)}
    return toc, pages


def zone_codes(path: Path) -> list[str]:
    import duckdb

    con = duckdb.connect()
    con.load_extension("spatial")
    rows = con.execute(f"select distinct coalesce(zonage, zone) from ST_Read('{path}')").fetchall()
    return [r[0] for r in rows]


def stecal_numbers(path: Path) -> dict[str, list[str]]:
    """Numéros de STECAL (attribut `stecal` du zonage) présents pour chaque code.

    Le numéro d'un objet donné se lit dans son attribut `stecal`, objet par objet ; la
    correspondance n'en donne que la liste par code.
    """
    import duckdb

    con = duckdb.connect()
    con.load_extension("spatial")
    rows = con.execute(
        f"""select coalesce(zonage, zone), list(distinct stecal order by stecal)
            from ST_Read('{path}') where stecal is not null group by 1"""
    ).fetchall()
    return {code: list(numbers) for code, numbers in rows}


def sample_points(path: Path, code: str, n: int = 3, seed: str = GPU_SEED) -> list[dict]:
    """Points intérieurs (ST_PointOnSurface, EPSG:4326) de `n` objets du code, tirés par md5."""
    import duckdb

    con = duckdb.connect()
    con.load_extension("spatial")
    rows = con.execute(
        f"""select OGC_FID, gid,
                   ST_X(ST_Transform(ST_PointOnSurface(geom), 'EPSG:2154', 'EPSG:4326',
                                     always_xy := true)),
                   ST_Y(ST_Transform(ST_PointOnSurface(geom), 'EPSG:2154', 'EPSG:4326',
                                     always_xy := true))
            from ST_Read('{path}') where coalesce(zonage, zone) = ?
            order by md5(cast(OGC_FID as varchar) || ?) limit ?""",
        [code, seed, n],
    ).fetchall()
    return [{"ogc_fid": f, "gid": g, "lon": round(x, 6), "lat": round(y, 6)} for f, g, x, y in rows]


def query_gpu(client, points: list[dict]) -> list[dict]:
    """Zones du GPU (API Carto, zone-urba) en chaque point : champs `GPU_FIELDS`."""
    out = []
    for point in points:
        geom = json.dumps({"type": "Point", "coordinates": [point["lon"], point["lat"]]})
        response = client.get(GPU_ZONE_URBA, params={"geom": geom})
        response.raise_for_status()
        zones = [
            {k: f["properties"].get(k) for k in GPU_FIELDS}
            for f in response.json().get("features", [])
        ]
        out.append(point | {"zones": zones})
    return out


app = typer.Typer(add_completion=False)


@app.command()
def main(
    check: Annotated[bool, typer.Option(help="Échoue si le CSV versionné diffère")] = False,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    output: Annotated[Path, typer.Option(help="CSV de correspondance")] = OUTPUT,
    preuve_gpu: Annotated[
        str | None, typer.Option(help="Enregistrer la preuve GPU d'un code")
    ] = None,
    chapitre: Annotated[str | None, typer.Option(help="Chapitre candidat de la preuve")] = None,
) -> None:
    """Génère (ou vérifie) configs/zones_reglement.csv, ou enregistre une preuve GPU."""
    if preuve_gpu:
        import httpx

        path = EVIDENCE_DIR / f"{preuve_gpu}.json"
        if path.exists() or not chapitre:
            typer.echo(f"{path} existe déjà, ou --chapitre manque", err=True)
            sys.exit(1)
        with httpx.Client(timeout=30, headers={"User-Agent": "traboule-controle"}) as client:
            points = query_gpu(client, sample_points(raw_dir / ZONAGE, preuve_gpu))
        evidence = {
            "code_zonage": preuve_gpu,
            "chapitre_candidat": chapitre,
            "source": "API Carto, module GPU, zone-urba",
            "url": GPU_ZONE_URBA,
            "requete_le": datetime.now(UTC).isoformat(timespec="seconds"),
            "points_tires_par": f"ST_PointOnSurface, md5(OGC_FID || '{GPU_SEED}')",
            "points": points,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"preuve écrite : {path}")
        return
    toc, pages = read_reglement(raw_dir / REGLEMENT)
    chaps = chapters(toc, max(pages))
    try:
        if len(chaps) != EXPECTED_CHAPTERS:
            found = len(chaps)
            raise CorrespondanceError(f"{found} chapitres « Zone » (attendu {EXPECTED_CHAPTERS})")
        zonage = raw_dir / ZONAGE
        rows = build(
            zone_codes(zonage), toc, pages, stecal_numbers(zonage), load_evidence(), load_aliases()
        )
    except CorrespondanceError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    content = to_csv(rows)
    if check:
        if not output.exists() or output.read_text(encoding="utf-8") != content:
            typer.echo(f"{output.name} diffère de la régénération", err=True)
            sys.exit(1)
        typer.echo("OK : CSV à jour")
        return
    output.write_text(content, encoding="utf-8")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.methode] = counts.get(r.methode, 0) + 1
    typer.echo(f"OK : {len(rows)} codes, {counts}")


if __name__ == "__main__":
    app()
