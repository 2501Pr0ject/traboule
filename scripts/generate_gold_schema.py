"""Génère benchmarks/datasets/gold/schema.json depuis le modèle `Question`, qui fait foi.

Usage : `uv run python scripts/generate_gold_schema.py` ; `--check` échoue si le fichier
versionné diffère de la génération.
"""

import json
import sys
from pathlib import Path

from traboule.contracts.question import Question

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "datasets" / "gold" / "schema.json"
)
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def render() -> str:
    """Schéma JSON du modèle `Question`, sérialisé de façon stable."""
    schema = {"$schema": DIALECT, **Question.model_json_schema()}
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv[1:]:
        if SCHEMA_PATH.read_text(encoding="utf-8") != content:
            print(f"{SCHEMA_PATH.name} diffère du modèle Question : régénérer le schéma")
            return 1
        return 0
    SCHEMA_PATH.write_text(content, encoding="utf-8")
    print(f"écrit : {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
