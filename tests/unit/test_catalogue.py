"""Catalogue des tables (conventions §3, règles 5 et 6) et documentation générée."""

import importlib.util
from pathlib import Path

import duckdb
import pytest

from traboule.catalogue import META_TABLES, STATUT_P, TABLES, table

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("doc", ROOT / "scripts" / "generate_data_doc.py")
doc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doc)
DATABASE = ROOT / "data" / "processed" / "traboule.duckdb"


@pytest.mark.parametrize("entry", TABLES, ids=lambda t: t.name)
def test_every_table_declares_level_vintage_and_sources(entry):
    assert entry.description and entry.niveau and entry.millesime and entry.sources
    assert entry.produite_par.startswith("uv run python -m traboule.")
    assert entry.exemple_sql.lower().startswith("select")


@pytest.mark.parametrize("entry", TABLES + META_TABLES, ids=lambda t: t.name)
def test_every_column_is_documented_once(entry):
    names = [c.name for c in entry.columns]
    assert len(names) == len(set(names))
    assert all(c.description for c in entry.columns)


def test_etablissements_carries_the_status_p_rule():
    assert table("etablissements").avertissement == STATUT_P
    assert "statut P" in STATUT_P and "liste blanche" in STATUT_P


def test_versioned_documentation_matches_catalogue():
    assert doc.DOC_PATH.read_text(encoding="utf-8") == doc.render()


@pytest.mark.skipif(not DATABASE.exists(), reason="base locale absente")
@pytest.mark.parametrize("entry", TABLES + META_TABLES, ids=lambda t: t.name)
def test_examples_run_on_the_local_database(entry):
    con = duckdb.connect(str(DATABASE), read_only=True)
    con.load_extension("spatial")
    con.execute(entry.exemple_sql).fetchall()
