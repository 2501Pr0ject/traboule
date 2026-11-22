"""Dossiers datés des données brutes : référence de sources.yaml, puis dossier le plus récent."""

import pytest
import yaml

from traboule.ingestion.raw import RawDataError, reference_date, resource_dir, resource_file

CONFIG = {
    "sources": [
        {
            "id": "SRC-X",
            "retrieved_on": "2026-10-28",
            "resources": [{"name": "zonage"}, {"name": "plan", "retrieved_on": "2026-11-01"}],
        }
    ]
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return path


def put(raw, date, resource, data=True):
    folder = raw / "SRC-X" / date / resource
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{}")
    if data:
        (folder / f"{resource}.geojson").write_text("{}")
    return folder


def test_reference_date_of_source_or_resource(config):
    assert reference_date("SRC-X", "zonage", config) == "2026-10-28"
    assert reference_date("SRC-X", "plan", config) == "2026-11-01"
    assert reference_date("SRC-Y", "zonage", config) is None


def test_reference_folder_is_read_when_it_has_data(tmp_path, config):
    raw = tmp_path / "raw"
    ref = put(raw, "2026-10-28", "zonage")
    put(raw, "2026-11-22", "zonage")
    assert resource_dir("SRC-X", "zonage", raw_dir=raw, config=config) == ref
    assert resource_file("SRC-X", "zonage", raw_dir=raw, config=config).name == "zonage.geojson"


def test_newest_folder_with_data_when_the_reference_has_only_its_manifest(tmp_path, config):
    raw = tmp_path / "raw"
    put(raw, "2026-10-28", "zonage", data=False)  # clone neuf : manifeste versionné seul
    put(raw, "2026-11-20", "zonage")
    newest = put(raw, "2026-11-22", "zonage")
    assert resource_dir("SRC-X", "zonage", raw_dir=raw, config=config) == newest


def test_explicit_date_and_missing_data(tmp_path, config):
    raw = tmp_path / "raw"
    put(raw, "2026-10-28", "zonage", data=False)
    older = put(raw, "2026-11-20", "zonage")
    assert resource_dir("SRC-X", "zonage", "2026-11-20", raw, config) == older
    with pytest.raises(RawDataError, match="données absentes"):
        resource_dir("SRC-X", "zonage", "2026-10-28", raw, config)
    with pytest.raises(RawDataError, match="manifeste seul"):
        resource_dir("SRC-X", "plan", raw_dir=raw, config=config)
