"""Contrats de données partagés par les sous-paquets (Pydantic v2)."""

from traboule.contracts.etablissement import Etablissement
from traboule.contracts.manifest import INGESTION_VERSION, Manifest
from traboule.contracts.passage import Passage
from traboule.contracts.question import Evidence, Question
from traboule.contracts.reponse import (
    Citation,
    Composante,
    Minorant,
    MotifAbstention,
    Reponse,
    VentilationConfiance,
)
from traboule.contracts.zone import Zone, ZoneAssignment

__all__ = [
    "INGESTION_VERSION",
    "Citation",
    "Composante",
    "Etablissement",
    "Evidence",
    "Manifest",
    "Minorant",
    "MotifAbstention",
    "Passage",
    "Question",
    "Reponse",
    "VentilationConfiance",
    "Zone",
    "ZoneAssignment",
]
