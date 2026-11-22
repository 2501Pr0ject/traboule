"""Corpus des passages et interface commune des stratégies de contexte (ADR-0014).

Les trois stratégies (RAG, CAG, KAG léger) partagent l'analyse, le routeur, la composante
structurée, le générateur et la vérification des citations : seule la construction du
contexte change.
"""

from dataclasses import dataclass, field
from typing import Protocol

from traboule.contracts.passage import Passage
from traboule.generation.llm_config import Strategy
from traboule.generation.redaction import Contexte
from traboule.routing.analyse import Analysis, Lexicon, normalize


class ContextStrategy(Protocol):
    name: Strategy

    def build(self, analysis: Analysis, zones: list[str]) -> Contexte:
        """Contexte de la composante documentaire ; `zones` : chapitres du règlement visés."""
        ...


@dataclass
class Corpus:
    """Passages indexés (règlement et cahiers), dans l'ordre des documents."""

    passages: list[Passage]
    by_id: dict[str, Passage] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {p.passage_id: p for p in self.passages}

    def of_zones(self, zones: list[str]) -> list[Passage]:
        """Passages du règlement qui s'appliquent à l'une des zones (dispositions communes UPr)."""
        wanted = set(zones)
        return [p for p in self.passages if wanted & set(p.zones_applicables or [])]

    def of_oap(self, number: str, communes: set[str]) -> list[Passage]:
        """Passages d'une OAP par son numéro, dans les cahiers des communes citées (sinon tous)."""
        prefix = f"OAP {number} "
        found = [p for p in self.passages if p.oap and (p.oap + " ").startswith(prefix)]
        if communes:
            local = [p for p in found if communes & {p.code_commune_cog2026, p.commune_historique}]
            found = local or found
        return found


def load_corpus() -> Corpus:
    from traboule.retrieval.index import load_passages
    from traboule.retrieval.index_config import load_exclusions

    passages, _ = load_passages(load_exclusions())
    return Corpus(passages)


def renvois_notes(passages: list[Passage], loaded: set[str]) -> list[str]:
    """Renvois des passages vers des passages absents du contexte, cités par leur titre."""
    targets = []
    for p in passages:
        for r in p.renvoi_vers or []:
            if not set(r.passage_ids) <= loaded:
                targets.append(r.cible)
    targets = list(dict.fromkeys(targets))
    return [f"Renvois cités, non chargés : {' ; '.join(targets)}"] if targets else []


def reglement_zones(analysis: Analysis, lexicon: Lexicon, extra: list[str] = ()) -> list[str]:
    """Chapitres du règlement visés : zones citées, ou zones issues de la composante structurée."""
    chapters = []
    for code in [*analysis.zones, *extra]:
        chapters += lexicon.chapters_of(code)
    return list(dict.fromkeys(chapters))


def zones_from_distribution(value: list[dict], question: str, top: int = 3) -> list[str]:
    """Zones d'une répartition à documenter : zones économiques si la question les vise."""
    zones = [row["zone"] for row in value]
    if "economique" in normalize(question):
        return [z for z in zones if z.startswith("UE")]
    return zones[:top]
