"""Fixtures de la chaîne : base DuckDB réduite (voir base_chaine.py)."""

from pathlib import Path

import duckdb
import pytest
from base_chaine import make_database

from traboule.chaine.sql import connect


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return make_database(tmp_path / "traboule.duckdb")


@pytest.fixture
def con(database: Path) -> duckdb.DuckDBPyConnection:
    con = connect(database)
    yield con
    con.close()
