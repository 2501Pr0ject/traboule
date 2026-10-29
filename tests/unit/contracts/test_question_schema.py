"""Le modèle Question fait foi : schema.json en est généré (scripts/generate_gold_schema.py)."""

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from traboule.contracts import Question

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "benchmarks" / "datasets" / "gold"
_spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_gold_schema.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def lines(name: str) -> list[dict]:
    return [json.loads(x) for x in (GOLD / name).read_text().splitlines() if x.strip()]


def test_versioned_schema_matches_model():
    assert (GOLD / "schema.json").read_text(encoding="utf-8") == gen.render()


def test_drafts_validate_with_model():
    for item in lines("questions.jsonl"):
        Question.model_validate(item)


def test_example_validates_structurally():
    # L'exemple contient des gabarits (AAAA-MM-JJ) : structure seulement, comme validate_gold.
    validator = Draft202012Validator(json.loads((GOLD / "schema.json").read_text()))
    for item in lines("questions.example.jsonl"):
        assert not list(validator.iter_errors(item))


@pytest.mark.parametrize(
    "change",
    [{"id": "XYZ-001"}, {"category": "autre"}, {"question": "court"}, {"champ_inconnu": 1}],
)
def test_model_and_schema_reject_the_same_items(change):
    item = lines("questions.jsonl")[0] | change
    strict = Draft202012Validator(
        json.loads((GOLD / "schema.json").read_text()),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    assert list(strict.iter_errors(item))
    with pytest.raises(ValidationError):
        Question.model_validate(item)
