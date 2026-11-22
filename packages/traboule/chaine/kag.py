"""Stratégie KAG léger : parcours déterministe d'un graphe de la structure explicite (ADR-0014).

Le graphe est construit sans modèle, à partir des données déjà extraites :
- chapitre de zone → article → passage (chemin des passages, `zones_applicables`) ; les codes du
  zonage sont rattachés à leur chapitre par `zones_reglement` (AU → AUs.co et zone U) ;
- passage → article de la partie I, ou OAP, cité par renvoi (`renvoi_vers`) ;
- terme défini → passage de définition (index des termes de la partie I, page du lexique) ;
- OAP → passages.
Parcours : chapitres visés (sinon OAP citée, sinon partie I) → caractère de la zone et
articles dont l'intitulé partage un mot avec la question, du plus au moins pertinent (à
défaut, les premiers articles du chapitre) → leurs passages → articles cités par renvoi qui
partagent aussi un mot → définitions des termes cités dans la question. Le chemin du parcours
est rendu dans les notes. Ni OpenSPG ni GraphRAG : aucun graphe n'est extrait du texte par un
modèle.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from traboule.chaine.contexte import Corpus
from traboule.config import INTERIM_DIR
from traboule.contracts.passage import Passage
from traboule.generation.redaction import Contexte
from traboule.routing.analyse import Analysis, normalize

TERMS = INTERIM_DIR / "extraction" / "reglement" / "index_termes.csv"
MAX_ARTICLES = 6
MAX_DEFINITIONS = 4
NOISE = {
    "etablissements", "etablissement", "actifs", "situes", "division", "section", "naf",
    "rev", "combien", "quelle", "quelles", "quel", "quels", "maximale", "maximal", "minimale",
    "zone", "zones", "regle", "regles", "reglement", "prevoit", "applique", "appliquent",
}  # fmt: skip
PART_ONE = "partie_i"


def stems(text: str) -> set[str]:
    """Mots pleins réduits à leurs 6 premières lettres (racine grossière, sans dictionnaire)."""
    words = normalize(text).replace(".", " ").split()
    return {w[:6] for w in words if len(w) >= 4 and w not in NOISE}


def article_key(chemin: list[str]) -> tuple[str, ...]:
    """Article d'un passage : chemin jusqu'au titre numéroté sous le chapitre (`2.5 - …`)."""
    for i, title in enumerate(chemin):
        if title.startswith("Zone ") or title.startswith("Dispositions communes"):
            return tuple(chemin[: i + 3])
    return tuple(chemin[:3])


@dataclass
class Graph:
    """Graphe typé : chapitres, articles, passages, renvois, termes, OAP."""

    articles_of: dict[str, list[tuple[str, ...]]] = field(default_factory=lambda: defaultdict(list))
    passages_of: dict[tuple[str, ...], list[Passage]] = field(
        default_factory=lambda: defaultdict(list)
    )
    titles: dict[tuple[str, ...], set[str]] = field(default_factory=lambda: defaultdict(set))
    renvois: dict[tuple[str, ...], list[tuple[str, tuple[str, ...]]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    definitions: dict[str, Passage] = field(default_factory=dict)
    oaps: dict[str, list[Passage]] = field(default_factory=lambda: defaultdict(list))

    def add_article(self, chapter: str, key: tuple[str, ...]) -> None:
        if key not in self.articles_of[chapter]:
            self.articles_of[chapter].append(key)


def build_graph(corpus: Corpus, terms: list[dict] | None = None) -> Graph:
    g = Graph()
    article_of_passage: dict[str, tuple[str, ...]] = {}
    for p in corpus.passages:
        if p.oap:
            g.oaps[p.oap].append(p)
            continue
        if "reglement" not in p.doc_id:
            continue
        key = article_key(p.chemin)
        article_of_passage[p.passage_id] = key
        g.passages_of[key].append(p)
        g.titles[key] |= stems(" ".join(p.chemin[len(key) - 1 :]))
        for chapter in p.zones_applicables or [PART_ONE]:
            g.add_article(chapter, key)
    for p in corpus.passages:
        key = article_of_passage.get(p.passage_id)
        for r in p.renvoi_vers or []:
            for target in dict.fromkeys(article_of_passage.get(i) for i in r.passage_ids):
                if key and target and (r.cible, target) not in g.renvois[key]:
                    g.renvois[key].append((r.cible, target))
    for term in terms or []:
        page, wanted = int(term["page_pdf"]), normalize(term["terme"])
        candidates = [
            p
            for p in corpus.passages
            if p.passage_id in article_of_passage
            and not p.zones_applicables
            and p.page_debut <= page <= p.page_fin
        ]
        match = next((p for p in candidates if wanted in normalize(p.texte)), None)
        if match:
            g.definitions[wanted] = match
    return g


def load_terms(path: Path = TERMS) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


class KagStrategy:
    name = "kag"

    def __init__(self, corpus: Corpus, graph: Graph | None = None) -> None:
        self.corpus = corpus
        self.graph = graph or build_graph(corpus, load_terms())

    def _ranked(self, chapter: str, words: set[str]) -> list[tuple[int, tuple[str, ...]]]:
        scored = [(len(words & self.graph.titles[a]), a) for a in self.graph.articles_of[chapter]]
        order = {a: i for i, a in enumerate(self.graph.articles_of[chapter])}
        return sorted(((s, a) for s, a in scored if s), key=lambda x: (-x[0], order[x[1]]))

    def build(self, analysis: Analysis, zones: list[str]) -> Contexte:
        words = stems(analysis.question)
        g = self.graph
        passages: list[Passage] = []
        path: list[str] = []
        if zones:
            starts = zones
        elif analysis.oap:
            prefix = f"OAP {analysis.oap} "
            oaps = [name for name in g.oaps if (name + " ").startswith(prefix)]
            for name in oaps:
                passages += g.oaps[name]
                path.append(f"{name} ({len(g.oaps[name])} passages)")
            starts = []
        else:
            starts = [PART_ONE]
        seen: set[tuple[str, ...]] = set()
        for chapter in starts:
            articles = g.articles_of[chapter]
            ranked = [a for _, a in self._ranked(chapter, words)[:MAX_ARTICLES]]
            overview = [a for a in articles if a[-1].startswith("Caractère")]
            if not ranked and chapter != PART_ONE:
                # Aucun intitulé ne partage un mot : vue d'ensemble, chapitre dans l'ordre.
                ranked = articles[:MAX_ARTICLES]
                path.append(
                    f"{chapter} : aucun intitulé ne partage un mot, {len(ranked)} premiers "
                    "articles du chapitre dans l'ordre"
                )
            for article in [*overview, *ranked]:
                if article in seen:
                    continue
                seen.add(article)
                passages += g.passages_of[article]
                if article in overview or words & g.titles[article]:
                    n = len(g.passages_of[article])
                    path.append(f"{chapter} → {article[-1]} ({n} passages)")
        for article in list(seen):
            for cible, target in g.renvois.get(article, []):
                if target not in seen and words & g.titles[target]:
                    seen.add(target)
                    passages += g.passages_of[target]
                    path.append(f"{article[-1]} → renvoi {cible} › {target[-1]}")
        text = normalize(analysis.question)
        terms = [t for t in g.definitions if t in text][:MAX_DEFINITIONS]
        for term in terms:
            definition = g.definitions[term]
            if definition not in passages:
                passages.append(definition)
                path.append(f"définition « {term} » (p. {definition.page_debut})")
        if not passages:
            refusal = "KAG : le parcours du graphe n'atteint aucun passage pour cette question."
            return Contexte([], refusal=refusal, notes=[f"Parcours : {p}" for p in path])
        unique = list({p.passage_id: p for p in passages}.values())
        notes = [f"KAG : {len(unique)} passages atteints par le parcours du graphe"]
        notes += [f"Parcours : {p}" for p in path]
        return Contexte(unique, trimmable=True, notes=notes)
