"""Tirage de l'échantillon A (protocole d'évaluation, §2 ; ADR-0012).

Données synthétiques à SIRET fictifs ; la reproduction de la grille réelle se compare en
local seulement, aux fichiers de data/interim/controles/, sans aucun SIRET dans ce test.
"""

import csv
import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from traboule.config import INTERIM_DIR, RAW_DIR
from traboule.evaluation import tirage


@pytest.fixture
def zones(tmp_path: Path) -> Path:
    rows = []
    for i, strate in enumerate(tirage.STRATA):
        for k in range(25):
            rows.append((f"{i}{k:013d}", "A", "une_zone", strate))
    rows += [
        ("9" + "0" * 13, "F", "une_zone", "haute"),
        ("9" + "1" * 13, "A", "multi_zones", "haute"),
    ]
    path = tmp_path / "zones.parquet"
    con = duckdb.connect()
    con.execute(
        "create table t (siret varchar, etat varchar, categorie varchar, confiance varchar)"
    )
    con.executemany("insert into t values (?, ?, ?, ?)", rows)
    con.execute(f"copy (select *, 'UEi2' as zone from t) to '{path}' (format parquet)")
    return path


def sirets(rows: list[dict]) -> list[str]:
    return [r["siret"] for r in rows]


def test_same_seed_gives_same_order_and_another_seed_another(zones):
    con = duckdb.connect()
    first, again = tirage.draw(con, zones, "20261101"), tirage.draw(con, zones, "20261101")
    assert sirets(first) == sirets(again)
    assert sirets(tirage.draw(con, zones, "42")) != sirets(first)


def test_order_is_md5_of_siret_and_seed(zones):
    rows = tirage.draw(duckdb.connect(), zones, "20261101")
    for strate in tirage.STRATA:
        drawn = [r["siret"] for r in rows if r["strate"] == strate]
        population = [f"{tirage.STRATA.index(strate)}{k:013d}" for k in range(25)]
        expected = sorted(
            population, key=lambda s: hashlib.md5((s + "20261101").encode()).hexdigest()
        )
        assert drawn == expected[: tirage.PER_STRATUM + tirage.REPLACEMENTS]
        assert [r["rang"] for r in rows if r["strate"] == strate] == list(range(1, 21))


def test_population_excludes_closed_and_multi_zone(zones):
    drawn = sirets(tirage.draw(duckdb.connect(), zones, "20261101"))
    assert not any(s.startswith("9") for s in drawn)
    assert len(drawn) == 3 * (tirage.PER_STRATUM + tirage.REPLACEMENTS)


def test_seed_is_mandatory(zones):
    with pytest.raises(tirage.TirageError, match="graine"):
        tirage.draw(duckdb.connect(), zones, "")


def test_incomplete_stratum_is_refused(zones):
    with pytest.raises(tirage.TirageError, match="strate"):
        tirage.draw(duckdb.connect(), zones, "20261101", ranks=26)


def test_grid_has_empty_review_columns_and_is_never_rewritten(tmp_path):
    row = {"rang": 1, "strate": "haute", "siret": "0" * 14, "adresse_declaree": "1 RUE X",
           "zone_jointure": "UEi2", "lien_gpu": "https://exemple.test"}  # fmt: skip
    path = tmp_path / "grille.csv"
    tirage.write_grid(path, [row])
    (line,) = list(csv.DictReader(path.open(encoding="utf-8")))
    assert all(line[c] == "" for c in tirage.REVIEW_COLUMNS)
    with pytest.raises(tirage.TirageError, match="existe déjà"):
        tirage.write_grid(path, [row])


LOCAL = INTERIM_DIR / "controles"
ZONES = INTERIM_DIR / "etablissements_zones.parquet"
STOCK = RAW_DIR / tirage.STOCK


def local_draw_available() -> bool:
    needed = [LOCAL / tirage.GRID, LOCAL / tirage.MASKED, LOCAL / tirage.META, ZONES, STOCK]
    if not all(p.exists() for p in needed):
        return False
    meta = json.loads((LOCAL / tirage.META).read_text())
    return meta["table_sha256"] == hashlib.sha256(ZONES.read_bytes()).hexdigest()


@pytest.mark.skipif(not local_draw_available(), reason="grille locale absente ou table modifiée")
def test_module_reproduces_the_local_grid_exactly(tmp_path):
    seed = json.loads((LOCAL / tirage.META).read_text())["graine"]
    tirage.run(tmp_path, seed, ZONES, INTERIM_DIR / "sirene_ml.parquet", STOCK)
    for name in (tirage.GRID, tirage.MASKED):
        assert (tmp_path / name).read_bytes() == (LOCAL / name).read_bytes(), name
