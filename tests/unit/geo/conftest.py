"""Fixtures des tests géographiques."""

from pathlib import Path

import duckdb
import pytest
from geodata import square, write_geojson


@pytest.fixture
def zonage(tmp_path: Path) -> Path:
    """Trois zones contiguës ou séparées, une zone qui chevauche, un secteur sauvegardé."""
    return write_geojson(
        tmp_path / "zonage.geojson",
        [
            ({"zone": "UEi", "zonage": "UEi2"}, square(0, 0, 100, 100)),
            ({"zone": "UEi", "zonage": "UEi1"}, square(100, 0, 200, 100)),
            ({"zone": "UC", "zonage": "UCe1"}, square(0, 0, 20, 20)),  # chevauche UEi2
            ({"zone": "SECTSAUV", "zonage": None}, square(0, 200, 100, 300)),
        ],
        2154,
    )


@pytest.fixture
def spatial() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.load_extension("spatial")
    return con
