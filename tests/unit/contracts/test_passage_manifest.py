"""Contrats Passage (ADR-0009) et Manifest (conventions §3, règle 2)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from traboule.contracts import Manifest, Passage

PASSAGE = {
    "passage_id": "p1",
    "texte": "Le coefficient d'emprise au sol est fixé à 60 %.",
    "doc_id": "reglement.pdf",
    "source_id": "SRC-005",
    "version_piece": "Modification n° 4 – Approbation 2024",
    "version_gpu": "200046977_PLUi_20260326",
    "page_debut": 640,
    "page_fin": 640,
    "chemin": ["UEi2", "CHAPITRE 2", "2.4.1"],
    "extracteur": "pymupdf",
    "zone": "UEi2",
}


def test_passage_payload_is_valid():
    assert Passage(**PASSAGE).zone == "UEi2"


def test_page_range_is_ordered():
    with pytest.raises(ValidationError, match="page_fin"):
        Passage(**(PASSAGE | {"page_debut": 641}))


def test_cahier_passage_carries_both_communes():
    # Secteur 46 : Pierre-Bénite (69152), rattachée à Oullins-Pierre-Bénite (69149).
    cahier = PASSAGE | {"zone": None, "secteur_pluh": "46", "extracteur": "docling"}
    with pytest.raises(ValidationError, match="commune"):
        Passage(**cahier)
    p = Passage(**(cahier | {"code_commune_cog2026": "69149", "commune_historique": "69152"}))
    assert p.commune_historique == "69152"


@pytest.mark.parametrize("secteur", ["00", "68", "7"])
def test_sector_outside_01_67_is_rejected(secteur):
    with pytest.raises(ValidationError):
        Passage(**(PASSAGE | {"secteur_pluh": secteur}))


def test_preamble_carries_its_zone():
    with pytest.raises(ValidationError, match="préambule"):
        Passage(**(PASSAGE | {"zone": None, "est_preambule": True}))


MANIFEST = {
    "source_id": "SRC-TEST",
    "source_title": "Test",
    "publisher": "Test",
    "source_url": "https://exemple.test/a.pdf",
    "license": "Licence Ouverte 2.0",
    "retrieved_at": datetime(2026, 10, 29, tzinfo=UTC),
    "published_at": None,
    "reference_date": None,
    "geographic_vintage": None,
    "format": "pdf",
    "file_size_bytes": 3,
    "sha256": "a" * 64,
    "limitations": None,
}


def test_manifest_rejects_unknown_field_and_bad_hash():
    assert Manifest(**MANIFEST).ingestion_version
    with pytest.raises(ValidationError):
        Manifest(**(MANIFEST | {"inconnu": 1}))
    with pytest.raises(ValidationError):
        Manifest(**(MANIFEST | {"sha256": "abc"}))


def test_existing_manifests_still_validate():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    manifests = sorted((root / "data" / "raw").glob("*/*/*/manifest.json"))
    if not manifests:
        pytest.skip("aucune donnée brute locale")
    for path in manifests:
        Manifest.model_validate_json(path.read_text())
