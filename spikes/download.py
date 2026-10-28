"""Téléchargement des sources dans data/raw/<source_id>/<AAAA-MM-JJ>/ avec manifeste.

Script jetable du spike. Pour l'instant, seul le modèle `Manifest` est défini ; le
téléchargement (streaming, sha256, refus d'écraser, passage en lecture seule) est
écrit en session 1. Le modèle sera déplacé dans packages/ après le GO.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

INGESTION_VERSION = "0.1.0"


class Manifest(BaseModel):
    """Manifeste d'une ressource téléchargée : fait foi pour la liste des champs."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_title: str
    publisher: str
    source_url: str
    license: str
    retrieved_at: datetime
    published_at: date | None
    reference_date: date | None
    geographic_vintage: str | None
    format: str
    file_size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str | None = None
    ingestion_version: str = INGESTION_VERSION
    limitations: str | None
