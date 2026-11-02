"""Passage d'un document du PLU-H et son payload (ADR-0008, ADR-0009)."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Secteur = Annotated[str, StringConstraints(pattern=r"^(0[1-9]|[1-5][0-9]|6[0-7])$")]


class QualiteTexte(BaseModel):
    """Défauts d'extraction restant dans le texte d'un passage après réparation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Caractères « \ufffd » laissés par Docling (ligature non décodée, non remplacée).
    illisibles: int = Field(ge=0)
    # Mots coupés par une ligature codée avec une espace (« stati on »), non recollés.
    fragments: int = Field(ge=0)


class Renvoi(BaseModel):
    """Lien d'un passage vers les passages qu'il cite par renvoi (ADR-0009, ADR-0011).

    Ex. : un cahier d'arrondissement renvoie à l'OAP 0.1 du cahier communal de Lyon ; un
    article de zone renvoie à un chapitre de la partie I du règlement.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    cible: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    passage_ids: list[str] = Field(min_length=1)


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
    # Pièce identique pour plusieurs secteurs (cahier communal de Lyon, secteurs 31 à 39) :
    # un seul exemplaire indexé, avec tous ses secteurs et le titre à citer (ADR-0009).
    secteurs_pluh: list[Secteur] | None = None
    titre_piece: str | None = None
    # Cahiers : défauts restants après réparation des ligatures (traboule.retrieval.ligatures).
    qualite_texte: QualiteTexte | None = None
    renvoi_vers: list[Renvoi] | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.page_fin < self.page_debut:
            raise ValueError("page_fin antérieure à page_debut")
        if self.secteur_pluh and not (self.code_commune_cog2026 and self.commune_historique):
            raise ValueError("un passage de cahier porte sa commune COG 2026 et historique")
        if self.secteurs_pluh and self.secteur_pluh:
            raise ValueError("une pièce commune à plusieurs secteurs ne porte pas de secteur seul")
        if self.est_preambule and self.zone is None:
            raise ValueError("un préambule de zone porte sa zone")
        return self
