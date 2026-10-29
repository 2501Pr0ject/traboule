"""Chemins du projet, configuration des sources et seuils fixés par les ADR."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
INTERIM_DIR = ROOT / "data" / "interim"
SOURCES_CONFIG = ROOT / "configs" / "sources.yaml"

# Indice de confiance de zone (ADR-0006) : seuils provisoires de distance au polygone
# d'une autre zone, et rayon au-delà duquel la distance est notée « ≥ rayon ».
NEAR_LIMIT_M = 10.0
FAR_LIMIT_M = 25.0
SEARCH_RADIUS_M = 200.0

# Minorant d'un comptage par zone (conventions §3, règle 7) : surface d'intersection
# commune ∩ zone au-delà de laquelle la commune est retenue (écarte les contacts de bordure).
MIN_INTERSECTION_M2 = 100.0

# Placeholder d'URL non confirmée (conventions §3, règle 3).
UNCONFIRMED_URL = "A_CONFIRMER"


def load_sources(path: Path = SOURCES_CONFIG) -> dict:
    """Lit configs/sources.yaml."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))
