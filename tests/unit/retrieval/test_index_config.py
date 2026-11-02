"""Exclusions de l'index (configs/index.yaml)."""

import pytest

from traboule.retrieval.index_config import (
    IndexConfigError,
    PieceIdentique,
    check_identical,
    is_indexed,
    load_exclusions,
    load_identical,
)


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


def test_lyon_communal_cahier_has_one_reference_and_eight_duplicates():
    (group,) = load_identical()
    assert group.reference == "cahier_communal_sect31"
    assert group.secteurs == tuple(str(n) for n in range(31, 40))
    assert len(group.doublons) == 8
    assert all(len(sha) == 64 for sha in group.exemplaires.values())
    exclusions = load_exclusions()
    assert is_indexed("cahier_communal_sect31", exclusions)
    assert all(not is_indexed(r, exclusions) for r in group.doublons)
    assert "Doublon de cahier_communal_sect31" in exclusions["cahier_communal_sect37"]


GROUP = PieceIdentique("a", "Pièce A", ("31", "32"), "69123", {"a": "1" * 64, "b": "2" * 64})


def test_identical_pieces_pass_the_check():
    check_identical(GROUP, {"a": "1" * 64, "b": "2" * 64}, {"a": "texte", "b": "texte"})


def test_a_diverging_copy_blocks():
    with pytest.raises(IndexConfigError, match="texte différent"):
        check_identical(GROUP, {"a": "1" * 64, "b": "2" * 64}, {"a": "texte", "b": "autre"})
    with pytest.raises(IndexConfigError, match="sha256"):
        check_identical(GROUP, {"a": "1" * 64, "b": "3" * 64}, {"a": "texte", "b": "texte"})


def test_incomplete_group_is_refused(tmp_path):
    path = tmp_path / "index.yaml"
    path.write_text(
        "pieces_identiques:\n  - reference: a\n    titre: A\n    exemplaires: {b: x}\n",
        encoding="utf-8",
    )
    with pytest.raises(IndexConfigError, match="incomplet"):
        load_identical(path)
