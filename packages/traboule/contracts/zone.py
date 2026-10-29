"""Zones du PLU-H et rattachement d'un établissement à une zone (ADR-0006)."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Confiance = Literal["haute", "moyenne", "faible"]
Categorie = Literal["une_zone", "aucune_zone", "multi_zones", "secteur_sauvegarde"]


class Zone(BaseModel):
    """Zone du zonage SRC-002 ; `SECTSAUV` est le secteur sauvegardé (PSMV, non ingéré)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    famille: str
    kind: Literal["plu", "secteur_sauvegarde"]
    libelle: str | None = None


class ZoneAssignment(BaseModel):
    """Résultat de la jointure spatiale pour un établissement à position publique."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    siret: str = Field(pattern=r"^[0-9]{14}$")
    categorie: Categorie
    zone: str | None
    zone_stock: str | None = None
    ecart_sources_m: float | None = Field(default=None, ge=0)
    dist_autre_zone_m: float | None = Field(default=None, ge=0)
    confiance: Confiance | None

    @model_validator(mode="after")
    def _check(self) -> Self:
        has_zone = self.categorie in ("une_zone", "secteur_sauvegarde")
        if has_zone != (self.zone is not None):
            raise ValueError(f"categorie {self.categorie} incompatible avec zone={self.zone!r}")
        if self.zone is None and self.confiance is not None:
            raise ValueError("pas d'indice de confiance sans zone")
        return self
