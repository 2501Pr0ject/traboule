"""Construction de la base DuckDB documentée, sur des données synthétiques."""

import csv
import json
from pathlib import Path

import duckdb
import pytest

from traboule.catalogue import TABLES
from traboule.geo.crs import CRSError
from traboule.ingestion.database import DatabaseError, Inputs, build_database

SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]


def geojson(path: Path, features: list[dict], epsg: int) -> Path:
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"}},
        "features": [{"type": "Feature", "properties": p, "geometry": g} for p, g in features],
    }))  # fmt: skip
    return path


def poly(coords) -> dict:
    return {"type": "Polygon", "coordinates": [coords]}


def parquet(path: Path, columns: list[str], values: dict[str, str]) -> None:
    select = ", ".join(f'{values.get(c, "null::varchar")} as "{c}"' for c in columns)
    duckdb.execute(f"copy (select {select}) to '{path}' (format parquet)")


def columns(name: str) -> list[str]:
    return [c.name for c in next(t for t in TABLES if t.name == name).columns]


@pytest.fixture
def inputs(tmp_path: Path) -> Inputs:
    interim = tmp_path / "interim"
    interim.mkdir()
    parquet(
        interim / "ref_communes_ml.parquet",
        columns("communes"),
        {"code_commune": "'69259'", "niveau": "'commune'"},
    )
    parquet(
        interim / "ref_arrondissements_lyon.parquet",
        columns("arrondissements"),
        {"code_arrondissement": "'69387'", "code_commune_parent": "'69123'"},
    )
    parquet(
        interim / "passage_communes.parquet",
        columns("passage_communes"),
        {"code_source": "'69152'", "code_cog_2026": "'69149'"},
    )
    parquet(
        interim / "sirene_ml.parquet",
        columns("etablissements"),
        {"siret": "'00000000000001'", "statutDiffusionEtablissement": "'P'"},
    )
    parquet(interim / "etablissements_zones.parquet", columns("etablissements_zones"),
            {"siret": "'00000000000002'", "zone": "'UEi2'"})  # fmt: skip
    zonage = geojson(tmp_path / "zonage.geojson", [(
        {"zone": "UEi", "zonage": "UEi2", "stecal": None, "plafond": None, "ces": "60",
         "ces_bande_principale": None, "ces_bande_secondaire": None, "cpt": None,
         "cpt_bande_principale": None, "cpt_bande_secondaire": None,
         "hauteur_bande_principale": None, "hauteur_bande_secondaire": None,
         "last_update": "2026-03-03"}, poly(SQUARE))], 2154)  # fmt: skip
    lon, lat = 4.83, 45.75
    small = [[lon, lat], [lon + 0.01, lat], [lon + 0.01, lat + 0.01], [lon, lat + 0.01], [lon, lat]]
    communes = geojson(
        tmp_path / "communes.geojson",
        [({"insee": "69123"}, poly(small)), ({"insee": "69259"}, poly(small))],
        4326,
    )
    arrondissements = geojson(tmp_path / "arr.geojson", [({"insee": "69387"}, poly(SQUARE))], 2154)
    zones = tmp_path / "zones_reglement.csv"
    with zones.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns("zones_reglement"), restval="")
        writer.writeheader()
        writer.writerow({"code_zone": "UEi2", "methode": "exact"})
    raw = tmp_path / "raw"
    manifest = raw / "SRC-002" / "2026-10-28" / "zonage" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"source_id": "SRC-002", "source_url": "https://exemple.test",
                                    "sha256": "a" * 64, "retrieved_at": "2026-10-28T10:00:00Z",
                                    "license": "Licence Ouverte 2.0"}))  # fmt: skip
    return Inputs(interim, zonage, communes, arrondissements, zones, raw)


def test_every_table_and_column_carries_its_comment(inputs, tmp_path):
    out = tmp_path / "base.duckdb"
    counts = build_database(out, inputs)
    con = duckdb.connect(str(out), read_only=True)
    tables = dict(
        con.execute("select table_name, comment from duckdb_tables() where not internal").fetchall()
    )
    assert set(tables) == {t.name for t in TABLES} | {"_catalogue", "_sources"}
    assert all(tables.values())
    assert (
        "statut P" in tables["etablissements"]
        and "Niveau : établissement" in tables["etablissements"]
    )
    undocumented = con.execute(
        """select table_name, column_name from duckdb_columns()
           where not internal and (comment is null or comment = '')"""
    ).fetchall()
    assert not undocumented
    assert counts["unites"] == 2 and counts["_sources"] == 1  # fmt: skip


def test_catalogue_and_sources_tables(inputs, tmp_path):
    out = tmp_path / "base.duckdb"
    build_database(out, inputs)
    con = duckdb.connect(str(out), read_only=True)
    assert con.execute("select count(*) from _catalogue").fetchone()[0] == len(TABLES)
    assert con.execute("select sources from _catalogue where nom = 'unites'").fetchone()[0] == [
        "REF-COMMUNES-ML-2024", "REF-ARRONDISSEMENTS-LYON"]  # fmt: skip
    assert con.execute("select source_id, ressource from _sources").fetchall() == [
        ("SRC-002", "2026-10-28/zonage")]  # fmt: skip


def test_lyon_is_replaced_by_its_arrondissements_in_units(inputs, tmp_path):
    out = tmp_path / "base.duckdb"
    build_database(out, inputs)
    con = duckdb.connect(str(out), read_only=True)
    assert con.execute("select code, niveau from unites order by 1").fetchall() == [
        ("69259", "commune"), ("69387", "arrondissement_municipal")]  # fmt: skip


def test_arrondissement_in_communes_fails_without_output(inputs, tmp_path):
    parquet(inputs.interim_dir / "ref_communes_ml.parquet", columns("communes"),
            {"code_commune": "'69387'"})  # fmt: skip
    out = tmp_path / "base.duckdb"
    with pytest.raises(DatabaseError, match="arrondissement"):
        build_database(out, inputs)
    assert not out.exists() and not list(tmp_path.glob("*.partial"))


def test_column_outside_catalogue_fails(inputs, tmp_path):
    duckdb.execute(
        f"copy (select '69123' as code_commune) to "
        f"'{inputs.interim_dir / 'ref_communes_ml.parquet'}' (format parquet)"
    )
    with pytest.raises(DatabaseError, match="communes"):
        build_database(tmp_path / "base.duckdb", inputs)


def test_zonage_in_wrong_crs_fails(inputs, tmp_path):
    bad = geojson(tmp_path / "z4326.geojson", [({"zone": "U", "zonage": "U1"}, poly(SQUARE))], 4326)
    with pytest.raises(CRSError):
        build_database(tmp_path / "base.duckdb", Inputs(**{**inputs.__dict__, "zonage": bad}))
    assert not (tmp_path / "base.duckdb").exists()
