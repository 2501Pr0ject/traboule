"""Passage d'un document du PLU-H et son payload (ADR-0008, ADR-0009)."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Passage(BaseModel):
    """Passage indexé.

    L'en-tête contextuel est construit à l'encodage, jamais stocké dans `texte`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: str = Field(min_length=1)
    texte: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    version_piece: str = Field(min_length=1)
    version_gpu: str = Field(min_length=1)
    page_debut: int = Field(ge=1)
    page_fin: int = Field(ge=1)
    chemin: list[str] = Field(min_length=1)
    extracteur: Literal["pymupdf", "docling"]
    zone: str | None = None
    zone_libelle: str | None = None
    est_preambule: bool = False
    oap: str | None = None
    # Cahiers communaux, établis sur le découpage à 59 communes (ADR-0009).
    secteur_pluh: str | None = Field(default=None, pattern=r"^(0[1-9]|[1-5][0-9]|6[0-7])$")
    code_commune_cog2026: str | None = Field(default=None, pattern=r"^[0-9]{5}$")
    commune_historique: str | None = Field(default=None, pattern=r"^[0-9]{5}$")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.page_fin < self.page_debut:
            raise ValueError("page_fin antérieure à page_debut")
        if self.secteur_pluh and not (self.code_commune_cog2026 and self.commune_historique):
            raise ValueError("un passage de cahier porte sa commune COG 2026 et historique")
        if self.est_preambule and self.zone is None:
            raise ValueError("un préambule de zone porte sa zone")
        return self
