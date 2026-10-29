"""Établissement Sirene rattaché à la Métropole (conventions §3 ; ADR-0003, ADR-0006)."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

LYON = "69123"
QualiteXY = Literal["11", "12", "21", "22", "33"]


class Etablissement(BaseModel):
    """Établissement du stock SRC-001a, avec sa position SRC-001b (EPSG:2154) si elle existe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    siret: str = Field(pattern=r"^[0-9]{14}$")
    etat: Literal["A", "F"]
    diffusion: Literal["O", "P"]
    code_commune_cog2026: str = Field(pattern=r"^[0-9]{5}$")
    code_arrondissement: str | None = Field(default=None, pattern=r"^6938[1-9]$")
    naf_rev2: str | None = Field(default=None, pattern=r"^[0-9]{2}\.[0-9]{2}[A-Z]$")
    qualite_xy: QualiteXY | None = None
    x: float | None = None
    y: float | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        # Règle 5 : un arrondissement n'existe que sous la commune de Lyon.
        if self.code_arrondissement and self.code_commune_cog2026 != LYON:
            raise ValueError("code_arrondissement exige code_commune_cog2026 = 69123")
        if (self.x is None) != (self.y is None):
            raise ValueError("x et y sont présents ensemble ou absents ensemble")
        return self

    @property
    def position_publique(self) -> bool:
        """Conventions §3, règles 7 et 10 : coordonnées présentes et statut de diffusion O."""
        return self.diffusion == "O" and self.x is not None
