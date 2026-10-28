"""Valide les fichiers JSONL du jeu de référence contre schema.json et détecte les doublons.

- questions.example.jsonl : structure seulement (pas de contrôle des formats ni des valeurs).
- autres fichiers : formats contrôlés (dates…), doublons détectés, et pour toute question
  `validated` : validated_by et validated_at obligatoires, aucun gabarit restant.
"""

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

GOLD_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "datasets" / "gold"
EXAMPLE_FILE = "questions.example.jsonl"
PLACEHOLDERS = ("A_RENSEIGNER", "A_ECRIRE", "AAAA")


def load_validators(schema: dict) -> tuple[Draft202012Validator, Draft202012Validator]:
    """Renvoie (validateur de structure, validateur avec contrôle des formats)."""
    structural = Draft202012Validator(schema)
    strict = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    return structural, strict


def find_placeholders(value: Any, path: str = "") -> list[str]:
    """Liste les chemins de l'objet dont une valeur (ou une clé) contient un gabarit."""
    found: list[str] = []
    if isinstance(value, str):
        if any(p in value for p in PLACEHOLDERS):
            found.append(path or "<racine>")
    elif isinstance(value, dict):
        for key, sub in value.items():
            sub_path = f"{path}.{key}" if path else str(key)
            if any(p in str(key) for p in PLACEHOLDERS):
                found.append(sub_path)
            found.extend(find_placeholders(sub, sub_path))
    elif isinstance(value, list):
        for i, sub in enumerate(value):
            found.extend(find_placeholders(sub, f"{path}[{i}]"))
    return found


def check_validated(item: dict) -> list[str]:
    """Règles propres aux questions au statut `validated`."""
    if item.get("status") != "validated":
        return []
    errors = [
        f"{field} obligatoire pour une question validée"
        for field in ("validated_by", "validated_at")
        if not item.get(field)
    ]
    errors.extend(f"gabarit non renseigné : {p}" for p in find_placeholders(item))
    return errors


def check_item(item: dict, validator: Draft202012Validator, *, example: bool) -> list[str]:
    errors = [err.message for err in validator.iter_errors(item)]
    if not example:
        errors.extend(check_validated(item))
    return errors


def validate_dir(gold_dir: Path) -> int:
    """Valide tous les *.jsonl de gold_dir, affiche les erreurs et renvoie leur nombre."""
    structural, strict = load_validators(json.loads((gold_dir / "schema.json").read_text()))
    errors, seen_ids, seen_questions = 0, set(), set()
    files = sorted(gold_dir.glob("*.jsonl"))
    for path in files:
        example = path.name == EXAMPLE_FILE
        validator = structural if example else strict
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            for message in check_item(item, validator, example=example):
                print(f"{path.name}:{lineno} {item.get('id')} — {message}")
                errors += 1
            if not example:
                qid, q = item.get("id"), item.get("question", "").strip().lower()
                if qid in seen_ids:
                    print(f"{path.name}:{lineno} id en double : {qid}")
                    errors += 1
                if q in seen_questions:
                    print(f"{path.name}:{lineno} question en double : {qid}")
                    errors += 1
                seen_ids.add(qid)
                seen_questions.add(q)
    print(f"{len(files)} fichier(s), {errors} erreur(s)")
    return errors


def main() -> int:
    return 1 if validate_dir(GOLD_DIR) else 0


if __name__ == "__main__":
    sys.exit(main())
