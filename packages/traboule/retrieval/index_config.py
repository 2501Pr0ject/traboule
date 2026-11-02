"""Configuration de l'index des passages (`configs/index.yaml`).

- exclusions : ressources exclues, chacune avec son motif et sa décision ;
- pièces identiques : un exemplaire de référence indexé, les autres exclus comme doublons ;
  chaque exemplaire garde son sha256 et un texte identique à la référence (contrôle bloquant).
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from traboule.config import INDEX_CONFIG


class IndexConfigError(ValueError):
    """Configuration de l'index invalide, ou pièce qui ne la respecte plus."""


@dataclass(frozen=True)
class PieceIdentique:
    reference: str
    titre: str
    secteurs: tuple[str, ...]
    code_commune_cog2026: str
    exemplaires: dict[str, str]  # ressource → sha256

    @property
    def doublons(self) -> list[str]:
        return [r for r in self.exemplaires if r != self.reference]


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_identical(path: Path = INDEX_CONFIG) -> list[PieceIdentique]:
    """Groupes de pièces identiques ; un groupe incomplet est refusé."""
    groups = []
    for entry in _read(path).get("pieces_identiques") or []:
        keys = ("reference", "titre", "secteurs", "code_commune_cog2026", "decision")
        exemplaires = entry.get("exemplaires") or {}
        if not all(entry.get(k) for k in keys) or entry.get("reference") not in exemplaires:
            raise IndexConfigError(f"groupe de pièces identiques incomplet : {entry}")
        groups.append(
            PieceIdentique(
                entry["reference"],
                entry["titre"],
                tuple(entry["secteurs"]),
                entry["code_commune_cog2026"],
                dict(exemplaires),
            )
        )
    return groups


def load_exclusions(path: Path = INDEX_CONFIG) -> dict[str, str]:
    """Ressources exclues de l'indexation → motif ; une exclusion sans motif est refusée.

    Les doublons des pièces identiques sont exclus, avec leur référence pour motif.
    """
    exclusions = {}
    for entry in _read(path).get("exclusions") or []:
        if not entry.get("ressource") or not entry.get("motif") or not entry.get("decision"):
            raise IndexConfigError(f"exclusion incomplète : {entry}")
        exclusions[entry["ressource"]] = entry["motif"]
    for group in load_identical(path):
        for resource in group.doublons:
            exclusions[resource] = f"Doublon de {group.reference} ({group.titre})"
    return exclusions


def is_indexed(resource: str, exclusions: dict[str, str]) -> bool:
    return resource not in exclusions


def check_identical(group: PieceIdentique, sha256: dict[str, str], texts: dict[str, str]) -> None:
    """Contrôle bloquant : chaque exemplaire a le sha256 consigné et le texte de la référence."""
    for resource, expected in group.exemplaires.items():
        if sha256.get(resource) != expected:
            raise IndexConfigError(f"{resource} : sha256 différent de celui consigné")
        if texts.get(resource) != texts.get(group.reference):
            raise IndexConfigError(f"{resource} : texte différent de {group.reference}")
