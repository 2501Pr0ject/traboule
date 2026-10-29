"""Manifeste d'une ressource téléchargée (conventions §3, règle 2)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

INGESTION_VERSION = "0.2.0"


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
    crs: str | None = None
