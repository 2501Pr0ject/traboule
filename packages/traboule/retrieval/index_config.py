"""Configuration de l'index des passages : ressources exclues et motif (`configs/index.yaml`)."""

from pathlib import Path

import yaml

from traboule.config import INDEX_CONFIG


class IndexConfigError(ValueError):
    """Configuration de l'index invalide."""


def load_exclusions(path: Path = INDEX_CONFIG) -> dict[str, str]:
    """Ressources exclues de l'indexation → motif ; une exclusion sans motif est refusée."""
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    exclusions = {}
    for entry in config.get("exclusions") or []:
        if not entry.get("ressource") or not entry.get("motif") or not entry.get("decision"):
            raise IndexConfigError(f"exclusion incomplète : {entry}")
        exclusions[entry["ressource"]] = entry["motif"]
    return exclusions


def is_indexed(resource: str, exclusions: dict[str, str]) -> bool:
    return resource not in exclusions
