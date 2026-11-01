"""Tirage de l'échantillon C (protocole d'évaluation, §2 bis)."""

import hashlib

import pytest

from traboule.evaluation import ordre_lecture as ol

CANDIDATES = {"cahier_b": list(range(1, 40)), "cahier_a": list(range(1, 30))}


def test_same_seed_same_order_md5_by_resource_page_seed():
    rows = ol.draw_pages(CANDIDATES, "20261104")
    assert rows == ol.draw_pages(CANDIDATES, "20261104")
    a = [r["page"] for r in rows if r["ressource"] == "cahier_a"]
    key = lambda p: hashlib.md5(f"cahier_a|{p}|20261104".encode()).hexdigest()  # noqa: E731
    assert a == sorted(CANDIDATES["cahier_a"], key=key)[:10]
    assert ol.draw_pages(CANDIDATES, "1") != rows


def test_seed_required_and_short_document_refused():
    with pytest.raises(ol.RevueError, match="graine"):
        ol.draw_pages(CANDIDATES, "")
    with pytest.raises(ol.RevueError, match="moins de"):
        ol.draw_pages({"court": [1, 2, 3]}, "20261104")


def test_grid_has_empty_review_columns_and_is_never_rewritten(tmp_path):
    path = tmp_path / "g.csv"
    ol.write_grid(path, [{"ressource": "cahier_a", "rang": 1, "page": 4}])
    assert path.read_text().splitlines()[1] == "cahier_a,1,4,,,,"
    with pytest.raises(ol.RevueError, match="existe déjà"):
        ol.write_grid(path, [])
