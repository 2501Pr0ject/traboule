"""Exclusions de l'index (configs/index.yaml)."""

import pytest

from traboule.retrieval.index_config import IndexConfigError, is_indexed, load_exclusions


def test_sect64_is_excluded_with_its_reason():
    exclusions = load_exclusions()
    assert "Éléments bâtis patrimoniaux" in exclusions["cahier_communal_sect64"]
    assert not is_indexed("cahier_communal_sect64", exclusions)
    assert is_indexed("cahier_communal_sect65", exclusions)


def test_exclusion_without_reason_is_refused(tmp_path):
    path = tmp_path / "index.yaml"
    path.write_text("exclusions:\n  - ressource: cahier_communal_sect01\n", encoding="utf-8")
    with pytest.raises(IndexConfigError, match="incomplète"):
        load_exclusions(path)
