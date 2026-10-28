import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "benchmarks" / "datasets" / "gold" / "schema.json"

_spec = importlib.util.spec_from_file_location(
    "validate_gold", ROOT / "scripts" / "validate_gold.py"
)
validate_gold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_gold)


@pytest.fixture(scope="module")
def validators():
    return validate_gold.load_validators(json.loads(SCHEMA_PATH.read_text()))


def make_item(**overrides) -> dict:
    item = {
        "id": "FAC-001",
        "dataset_version": "0.1.0",
        "category": "factual",
        "expected_route": "SQL",
        "question": "Combien d'établissements actifs dans la commune 69259 ?",
        "as_of": "2026-10-01",
        "source_versions": {"SRC-001a": "2026-10-01"},
        "expected_sql": "SELECT count(*) FROM sirene_ml",
        "evidence": [{"source_id": "SRC-001a"}],
        "status": "draft",
        "validated_by": None,
        "validated_at": None,
    }
    item.update(overrides)
    return item


def validated(**overrides) -> dict:
    defaults = {"status": "validated", "validated_by": "relecteur", "validated_at": "2026-10-28"}
    return make_item(**(defaults | overrides))


def errors(item, validators, *, example=False):
    structural, strict = validators
    return validate_gold.check_item(item, structural if example else strict, example=example)


# Contrôle des formats


def test_valid_date_passes(validators):
    assert errors(make_item(), validators) == []


def test_invalid_date_fails(validators):
    assert errors(make_item(as_of="2026-13-45"), validators)


# Fichier d'exemple : structure seulement


def test_example_ignores_formats_and_values(validators):
    item = make_item(
        as_of="AAAA-MM-JJ", status="validated", source_versions={"SRC-001a": "A_RENSEIGNER"}
    )
    assert errors(item, validators, example=True) == []


def test_example_still_checks_structure(validators):
    item = make_item()
    del item["question"]
    assert errors(item, validators, example=True)


# Questions validées : validated_by et validated_at


def test_validated_with_reviewer_and_date_passes(validators):
    assert errors(validated(), validators) == []


@pytest.mark.parametrize("field", ["validated_by", "validated_at"])
def test_validated_without_reviewer_or_date_fails(validators, field):
    msgs = errors(validated(**{field: None}), validators)
    assert any(field in m for m in msgs)


# Questions validées : aucun gabarit


def test_draft_with_placeholders_passes(validators):
    item = make_item(
        source_versions={"SRC-001a": "A_RENSEIGNER"}, expected_sql="A_ECRIRE_ET_RELIRE"
    )
    assert errors(item, validators) == []


@pytest.mark.parametrize(
    "overrides, path",
    [
        ({"source_versions": {"SRC-001a": "A_RENSEIGNER"}}, "source_versions.SRC-001a"),
        ({"expected_sql": "A_ECRIRE_ET_RELIRE"}, "expected_sql"),
        ({"evidence": [{"source_id": "SRC-005", "doc_id": "A_RENSEIGNER"}]}, "evidence[0].doc_id"),
        ({"notes": "date AAAA à compléter"}, "notes"),
    ],
)
def test_validated_with_placeholder_fails(validators, overrides, path):
    msgs = errors(validated(**overrides), validators)
    assert any(path in m for m in msgs)


# Doublons et fichiers réels


def _write_gold(tmp_path: Path, items: list[dict]) -> Path:
    (tmp_path / "schema.json").write_text(SCHEMA_PATH.read_text())
    (tmp_path / "questions.jsonl").write_text("\n".join(json.dumps(i) for i in items))
    return tmp_path


def test_unique_questions_pass(tmp_path):
    other = make_item(
        id="FAC-002", question="Combien d'établissements fermés dans la commune 69259 ?"
    )
    assert validate_gold.validate_dir(_write_gold(tmp_path, [make_item(), other])) == 0


def test_duplicate_id_fails(tmp_path):
    other = make_item(question="Une autre question bien distincte ?")
    assert validate_gold.validate_dir(_write_gold(tmp_path, [make_item(), other])) == 1


def test_duplicate_question_fails(tmp_path):
    assert (
        validate_gold.validate_dir(_write_gold(tmp_path, [make_item(), make_item(id="FAC-002")]))
        == 1
    )


def test_repository_gold_dir_is_valid():
    assert validate_gold.validate_dir(validate_gold.GOLD_DIR) == 0
