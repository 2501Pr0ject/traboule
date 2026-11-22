"""Chaîne complète : question → analyse → routeur → composantes → `Reponse` (ADR-0010, ADR-0014).

La composante structurée est écrite par le code à partir des résultats SQL ; la composante
documentaire est rédigée par le modèle à partir du contexte de la stratégie choisie, puis ses
citations sont vérifiées. Les abstentions structurelles passent avant toute recherche.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache

import duckdb

from traboule.chaine.contexte import (
    ContextStrategy,
    Corpus,
    load_corpus,
    reglement_zones,
    zones_from_distribution,
)
from traboule.chaine.sql import StructuredComponent
from traboule.contracts.reponse import Composante, Reponse
from traboule.generation.llm_config import Strategy
from traboule.generation.ollama import OllamaClient
from traboule.generation.redaction import draft
from traboule.generation.tokens import TokenCounter
from traboule.routing.analyse import Lexicon, analyse
from traboule.routing.routeur import route

STRATEGIES: tuple[Strategy, ...] = ("rag", "cag", "kag")


@dataclass
class Chain:
    con: duckdb.DuckDBPyConnection
    lexicon: Lexicon
    llm: OllamaClient
    counter: TokenCounter
    factories: dict[str, Callable[[], ContextStrategy]]
    _strategies: dict[str, ContextStrategy] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.structured = StructuredComponent(self.con, self.lexicon)

    def strategy(self, name: Strategy) -> ContextStrategy:
        if name not in self._strategies:
            if name not in self.factories:
                raise ValueError(f"stratégie non disponible : {name}")
            self._strategies[name] = self.factories[name]()
        return self._strategies[name]

    def ask(self, question: str, strategy: Strategy = "rag") -> Reponse:
        analysis = analyse(question, self.lexicon)
        decision = route(analysis, self.lexicon)
        components: list[Composante] = []
        if decision.structured:
            components += self.structured.build(analysis, decision)
        if decision.documentary:
            if decision.documentary_abstention:
                motif, text = decision.documentary_abstention
                components.append(Composante(type="documentaire", abstention=True, motif=motif,
                                             texte=text, limites=[text]))  # fmt: skip
            else:
                extra = []
                if not analysis.zones:
                    for c in components:
                        if isinstance(c.valeur, list):
                            extra = zones_from_distribution(c.valeur, question)
                zones = reglement_zones(analysis, self.lexicon, extra)
                contexte = self.strategy(strategy).build(analysis, zones)
                components.append(draft(self.llm, self.counter, strategy, question, contexte,
                                        hybrid=decision.structured))  # fmt: skip
        return Reponse(
            route=decision.route,
            composantes=components,
            question=question,
            strategie=strategy,
            motif_route=decision.motif,
        )

    def close(self) -> None:
        for s in self._strategies.values():
            if hasattr(s, "close"):
                s.close()
        self.llm.close()
        self.con.close()


def build_chain() -> Chain:
    """Chaîne sur la base locale, l'index Qdrant et le serveur Ollama de `configs/llm.yaml`."""
    from traboule.chaine.cag import CagStrategy
    from traboule.chaine.kag import KagStrategy
    from traboule.chaine.rag import QdrantSearch, RagStrategy
    from traboule.chaine.sql import connect, load_lexicon
    from traboule.generation.llm_config import load_llm_config
    from traboule.generation.tokens import HfTokenCounter

    config = load_llm_config()
    con = connect()
    counter = HfTokenCounter(config.tokenizer)

    @cache
    def corpus() -> Corpus:
        return load_corpus()

    return Chain(
        con=con,
        lexicon=load_lexicon(con),
        llm=OllamaClient(config),
        counter=counter,
        factories={
            "rag": lambda: RagStrategy(QdrantSearch()),
            "cag": lambda: CagStrategy(corpus(), counter, config.model, config.num_ctx.cag),
            "kag": lambda: KagStrategy(corpus()),
        },
    )
