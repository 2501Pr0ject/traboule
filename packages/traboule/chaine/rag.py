"""Stratégie RAG : recherche hybride Qdrant (dense + sparse, RRF), filtrée par zone (ADR-0014).

Les questions sont encodées par BGE-M3 sur CPU, pour laisser le GPU au modèle de génération
(décision du porteur, 2026-11-22). Les renvois des passages trouvés (partie I du règlement,
OAP 0.1) sont cités par leur titre, sans être chargés.
"""

import logging
from collections.abc import Callable
from itertools import zip_longest

from traboule.chaine.contexte import renvois_notes
from traboule.contracts.passage import Passage
from traboule.generation.redaction import Contexte
from traboule.routing.analyse import Analysis

Search = Callable[[str, list[str] | None], list[Passage]]
COLLECTION = "passages_entete"
TOP_K = 10


class QdrantSearch:
    """Recherche hybride sur l'index embarqué (`retrieval.index.search`)."""

    def __init__(self, collection: str = COLLECTION) -> None:
        # Avertissement de torch.distributed sans objet sous macOS, émis à l'import.
        logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").setLevel(
            logging.ERROR
        )
        from FlagEmbedding import BGEM3FlagModel
        from qdrant_client import QdrantClient, models

        from traboule.retrieval.index import MODEL, QDRANT_DIR

        self.collection = collection
        self.models = models
        self.model = BGEM3FlagModel(MODEL, use_fp16=False, devices="cpu")
        self.client = QdrantClient(path=str(QDRANT_DIR))

    def __call__(self, question: str, zones: list[str] | None) -> list[Passage]:
        from traboule.retrieval.index import search

        points = search(self.client, self.model, self.models, self.collection, question, zones)
        return [Passage.model_validate(point.payload) for point in points]

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None  # libéré avant l'arrêt de l'interpréteur (__del__ du client)


class RagStrategy:
    name = "rag"

    def __init__(self, search: Search) -> None:
        self.search = search

    def build(self, analysis: Analysis, zones: list[str]) -> Contexte:
        if len(zones) > 1:
            # Une recherche par chapitre, entrelacées : chaque chapitre visé est représenté
            # (zone AU : chapitre AUs.co et zone U de référence ; zones d'une répartition).
            per_zone = [self.search(analysis.question, [z]) for z in zones]
            merged = [p for rank in zip_longest(*per_zone) for p in rank if p is not None]
            hits = list({p.passage_id: p for p in merged}.values())[:TOP_K]
        else:
            hits = self.search(analysis.question, zones or None)
        scope = f", filtre zones_applicables = {', '.join(zones)}" if zones else ", sans filtre"
        notes = [f"RAG : {len(hits)} passages trouvés (recherche hybride dense + sparse{scope})"]
        notes += renvois_notes(hits, {p.passage_id for p in hits})
        return Contexte(hits, trimmable=True, notes=notes)

    def close(self) -> None:
        if hasattr(self.search, "close"):
            self.search.close()
