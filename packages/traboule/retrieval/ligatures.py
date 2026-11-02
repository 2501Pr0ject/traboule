"""Réparation des mots coupés par une ligature codée avec une espace (« parti e », « créati on »).

Certains cahiers codent les ligatures « ti », « tt », « ff », « fi », « fl » par les lettres
suivies d'une espace ; Docling restitue la coupure. Règle (décision du porteur, 2026-11-01) :
deux ou trois fragments voisins sont recollés seulement si
- le premier se termine par une de ces ligatures (les suivants aussi, sauf le dernier) ;
- les fragments qui suivent le premier sont en minuscules ;
- la forme recollée apparaît intacte au moins `MIN_OCCURRENCES` fois dans le vocabulaire de
  référence : règlement écrit et cahiers sans fragments (Vénissieux, Saint-Fons, Lyon communal).
Deux vrais mots voisins ne sont donc jamais fusionnés si leur concaténation n'est pas un mot du
corpus.

Docling remplace aussi certains glyphes de ligature par « \ufffd » (« Orienta\ufffd ons »),
alors que PyMuPDF les garde sur la même page. Règle (décision du porteur, 2026-11-02) : le
caractère est remplacé seulement si une seule ligature donne une forme vue au moins
`MIN_OCCURRENCES` fois dans le vocabulaire de référence, et si cette forme figure dans le
texte PyMuPDF des pages du passage ; sinon il reste.

Les noms d'OAP et les chemins (titres) sont réparés selon la même règle des fragments
(décision du porteur, 2026-11-02).

Le texte brut est conservé (`passages_brut.jsonl`) ; chaque réparation est consignée ; chaque
passage réparé porte `qualite_texte` (caractères illisibles et fragments restants).

Usage : `uv run python -m traboule.retrieval.ligatures` (après `traboule.retrieval.cahiers`).
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

import typer

from traboule.config import INTERIM_DIR, RAW_DIR
from traboule.contracts.passage import Passage, QualiteTexte
from traboule.measure import write_metrics
from traboule.retrieval.cahiers import OUT_DIR, SPLIT_LIGATURE, resource_folder
from traboule.retrieval.extraction import LIGATURES, read_pages, repair_ligatures

MIN_OCCURRENCES = 3
LIGATURE_END = ("ti", "tt", "ff", "fi", "fl")
REFERENCE_CAHIERS = ("cahier_communal_sect65", "cahier_communal_sect53", "cahier_communal_sect37")
WORD = re.compile(r"\w+")
TOKEN = re.compile(r"\w+|\W+")
UNREADABLE = "\ufffd"
# Mot qui contient le caractère illisible : début, espace simple éventuelle, suite du mot.
UNREADABLE_WORD = re.compile(r"(\w*)\ufffd( ?)(\w*)")
LIGATURE_LETTERS = sorted(set(LIGATURES.values()))


def vocabulary(texts: list[str]) -> Counter:
    """Fréquence des mots (en minuscules) dans les textes de référence."""
    counts: Counter = Counter()
    for text in texts:
        counts.update(w.lower() for w in WORD.findall(text))
    return counts


def repair(
    text: str, vocab: Counter, min_occurrences: int = MIN_OCCURRENCES
) -> tuple[str, Counter]:
    """Recolle les fragments selon la règle ; renvoie le texte et les réparations (avant, après)."""
    tokens = TOKEN.findall(text)
    out, repairs, i = [], Counter(), 0
    while i < len(tokens):
        joined = None
        # Morceaux possibles : mot, espace simple, mot (, espace simple, mot).
        for parts in (3, 2):
            span = tokens[i : i + 2 * parts - 1]
            if len(span) < 2 * parts - 1 or any(span[k] != " " for k in range(1, len(span), 2)):
                continue
            words = span[0::2]
            # Une ligature coupe le mot au milieu : les fragments suivants sont en minuscules.
            if not all(w.isalpha() for w in words) or not all(w.islower() for w in words[1:]):
                continue
            if not all(w.lower().endswith(LIGATURE_END) for w in words[:-1]):
                continue
            candidate = "".join(words)
            if vocab[candidate.lower()] >= min_occurrences:
                joined = (" ".join(words), candidate, 2 * parts - 1)
                break
        if joined:
            before, after, width = joined
            out.append(after)
            repairs[(before, after)] += 1
            i += width
        else:
            out.append(tokens[i])
            i += 1
    return "".join(out), repairs


def repair_unreadable(
    text: str, vocab: Counter, page_words: set[str], min_occurrences: int = MIN_OCCURRENCES
) -> tuple[str, Counter]:
    """Remplace « \ufffd » selon la règle ; renvoie le texte et les remplacements (avant, après)."""
    repairs: Counter = Counter()

    def fix(m: re.Match) -> str:
        prefix, space, suffix = m.groups()
        # Une ligature coupe le mot au milieu : la suite éventuelle est en minuscules.
        joinable = suffix.isalpha() and suffix.islower()
        found: dict[str, str] = {}
        for letters in LIGATURE_LETTERS:
            joined, alone = prefix + letters + suffix, prefix + letters
            if joinable and vocab[joined.lower()] >= min_occurrences:
                found[letters] = joined
            elif (space or not suffix) and vocab[alone.lower()] >= min_occurrences:
                found[letters] = alone + space + suffix
        if len(found) != 1:
            return m.group(0)
        replacement = next(iter(found.values()))
        if replacement.split(" ")[0].lower() not in page_words:
            return m.group(0)
        repairs[(m.group(0), replacement)] += 1
        return replacement

    return UNREADABLE_WORD.sub(fix, text), repairs


def pymupdf_words(resource: str) -> dict[int, set[str]]:
    """Mots (en minuscules) du texte PyMuPDF de chaque page, glyphes de ligature remplacés."""
    _, pages = read_pages(next(resource_folder(resource).glob("*.pdf")))
    return {
        n: {w.lower() for w in WORD.findall(repair_ligatures(p.texte_pymupdf)[0])}
        for n, p in pages.items()
    }


def reference_texts(raw_dir: Path = RAW_DIR) -> list[str]:
    """Texte du règlement écrit et des cahiers de référence (passages bruts)."""
    from traboule.geo.zones_reglement import REGLEMENT, read_reglement

    _, pages = read_reglement(raw_dir / REGLEMENT)
    texts = [repair_ligatures(t)[0] for t in pages.values()]
    for name in REFERENCE_CAHIERS:
        path = OUT_DIR / name / "passages_brut.jsonl"
        texts += [json.loads(line)["texte"] for line in path.open(encoding="utf-8")]
    return texts


def repair_titles(p: Passage, vocab: Counter, cache: dict[str, str]) -> dict:
    """Nom d'OAP et chemin réparés ; `cache` : titre → titre réparé (une entrée par titre)."""

    def fix(title: str) -> str:
        if title not in cache:
            cache[title] = repair(title, vocab)[0]
        return cache[title]

    return {"oap": fix(p.oap) if p.oap else None, "chemin": [fix(t) for t in p.chemin]}


def repair_cahier(folder: Path, vocab: Counter) -> dict:
    """Écrit passages.jsonl (réparé) et reparations.csv à partir de passages_brut.jsonl."""
    raw = [Passage.model_validate_json(line) for line in (folder / "passages_brut.jsonl").open()]
    words = pymupdf_words(folder.name) if any(UNREADABLE in p.texte for p in raw) else {}
    repaired, repairs, replaced, titles = [], Counter(), Counter(), {}
    for p in raw:
        page_words = set().union(
            *(words.get(n, set()) for n in range(p.page_debut, p.page_fin + 1))
        )
        text, found = repair_unreadable(p.texte, vocab, page_words)
        replaced.update(found)
        text, found = repair(text, vocab)
        repairs.update(found)
        quality = QualiteTexte(
            illisibles=text.count(UNREADABLE), fragments=len(SPLIT_LIGATURE.findall(text))
        )
        update = {"texte": text, "qualite_texte": quality, **repair_titles(p, vocab, titles)}
        repaired.append(p.model_copy(update=update))
    (folder / "passages.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in repaired))
    with (folder / "reparations.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["regle", "avant", "apres", "nombre"])
        fixed = Counter({(b, a): 1 for b, a in titles.items() if b != a})
        for rule, counts in (
            ("caractere_illisible", replaced),
            ("fragments", repairs),
            ("titres", fixed),
        ):
            for (before, after), n in counts.most_common():
                writer.writerow([rule, before, after, n])
    return {
        "illisibles_avant": sum(p.texte.count(UNREADABLE) for p in raw),
        "illisibles_remplaces": sum(replaced.values()),
        "illisibles_apres": sum(p.texte.count(UNREADABLE) for p in repaired),
        "reparations": sum(repairs.values()),
        "formes": len(repairs),
        "fragments_avant": sum(len(SPLIT_LIGATURE.findall(p.texte)) for p in raw),
        "fragments_apres": sum(len(SPLIT_LIGATURE.findall(p.texte)) for p in repaired),
        "titres_repares": sum(b != a for b, a in titles.items()),
    }


app = typer.Typer(add_completion=False)


@app.command()
def main() -> None:
    """Répare tous les cahiers extraits et écrit les mesures avant / après."""
    vocab = vocabulary(reference_texts())
    results = {f.name: repair_cahier(f, vocab) for f in sorted(OUT_DIR.iterdir())
               if (f / "passages_brut.jsonl").exists()}  # fmt: skip
    keys = ("illisibles_avant", "illisibles_remplaces", "illisibles_apres", "reparations",
            "fragments_avant", "fragments_apres", "titres_repares")  # fmt: skip
    totals = {k: sum(r[k] for r in results.values()) for k in keys}
    write_metrics(
        INTERIM_DIR / "metrics" / "ligatures.json",
        {"total": totals, "cahiers": results},
        {"min_occurrences": MIN_OCCURRENCES, "references": ["règlement", *REFERENCE_CAHIERS]},
    )
    typer.echo(f"OK : {totals}")


if __name__ == "__main__":
    app()
