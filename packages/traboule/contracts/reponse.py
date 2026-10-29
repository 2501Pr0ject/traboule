"""Réponse du système, structurée en composantes (conventions §6 ; ADR-0006, ADR-0010).

Une question mixte peut être en partie abstenue : le comptage est donné, l'affirmation
réglementaire est abstenue (par exemple en confiance de zone faible). Les règles s'appliquent
donc par composante.
"""

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traboule.contracts.question import Route


class MotifAbstention(StrEnum):
    """Signaux d'abstention de l'ADR-0010."""

    # Signaux structurels
    ZONE_INEXISTANTE = "zone_inexistante"
    DOCUMENT_NON_INGERE = "document_non_ingere"
    NIVEAU_NON_CHARGE = "niveau_non_charge"
    HORS_VERSION = "hors_version"
    DIFFUSION_PARTIELLE = "diffusion_partielle"
    AUTRE_DOCUMENT = "autre_document"  # ex. secteur sauvegardé, régi par le PSMV
    CONFIANCE_FAIBLE = "confiance_faible"
    # Signaux de retrieval et vérification à la génération
    PREUVE_INSUFFISANTE = "preuve_insuffisante"
    CITATION_NON_VERIFIEE = "citation_non_verifiee"


class Citation(BaseModel):
    """Passage cité : la version de la pièce est obligatoire (conventions §6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    version_piece: str = Field(min_length=1)
    version_gpu: str | None = None
    zone: str | None = None
    chemin: list[str] = Field(default_factory=list)
    passage_id: str | None = None


class VentilationConfiance(BaseModel):
    """Ventilation d'un comptage spatial par niveau de confiance de zone (ADR-0006)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    haute: int = Field(ge=0)
    moyenne: int = Field(ge=0)
    faible: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.haute + self.moyenne + self.faible


class Minorant(BaseModel):
    """Établissements de même périmètre sans position publique (conventions §3, règle 7)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    n: int = Field(ge=0)
    perimetre: str = Field(min_length=1, description="ex. « communes qui intersectent UEi2 »")

    @property
    def formulation(self) -> str:
        return f"jusqu'à {self.n} établissements supplémentaires pourraient se trouver dans la zone"


class Composante(BaseModel):
    """Partie structurée (SQL, jointure) ou documentaire (règlement) d'une réponse."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["structuree", "documentaire"]
    valeur: Any = None
    abstention: bool = False
    motif: MotifAbstention | None = None
    comptage_spatial: bool = False
    ventilation_confiance: VentilationConfiance | None = None
    minorant: Minorant | None = None
    citations: list[Citation] = Field(default_factory=list)
    limites: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.abstention:
            # Une abstention peut citer ce qui justifie son motif (ex. exclusion du PSMV).
            if self.valeur is not None:
                raise ValueError("une composante abstenue n'a pas de valeur")
            if self.motif is None:
                raise ValueError("une composante abstenue porte un motif")
            return self
        if self.motif is not None:
            raise ValueError("un motif d'abstention sans abstention")
        if self.valeur is None:
            raise ValueError("une composante non abstenue porte une valeur")
        if self.type == "documentaire" and not self.citations:
            raise ValueError("une composante documentaire cite au moins un passage")
        if self.comptage_spatial:
            if self.minorant is None or self.ventilation_confiance is None:
                raise ValueError("un comptage spatial porte un minorant et une ventilation")
            if isinstance(self.valeur, int) and self.valeur != self.ventilation_confiance.total:
                raise ValueError("la ventilation de confiance ne totalise pas la valeur")
        return self


class Reponse(BaseModel):
    """Réponse à une question : route choisie et composantes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Route
    composantes: list[Composante] = Field(min_length=1)
    question_id: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        types = {c.type for c in self.composantes}
        if self.route == "ABSTAIN" and not all(c.abstention for c in self.composantes):
            raise ValueError("route ABSTAIN : toutes les composantes sont abstenues")
        if self.route == "SQL" and types != {"structuree"}:
            raise ValueError("route SQL : composantes structurées seulement")
        if self.route == "RAG" and types != {"documentaire"}:
            raise ValueError("route RAG : composantes documentaires seulement")
        if self.route == "HYBRID" and types != {"structuree", "documentaire"}:
            raise ValueError("route HYBRID : au moins une composante de chaque type")
        return self
