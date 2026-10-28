"""Vérifie dans un dépôt jetable que .gitignore suit les manifestes et ignore les données."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("git") is None, reason="git absent")
def test_manifest_tracked_data_ignored(tmp_path):
    shutil.copy(ROOT / ".gitignore", tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    files = [
        "data/raw/SRC-002/2026-10-28/manifest.json",
        "data/raw/SRC-002/2026-10-28/zonage.geojson",
        "data/raw/SRC-007/2026-10-28/sirene.csv",
        "data/interim/sirene_ml.parquet",
    ]
    for f in files:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).touch()
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.split()

    assert "data/raw/SRC-002/2026-10-28/manifest.json" in tracked
    assert "data/raw/SRC-002/2026-10-28/zonage.geojson" not in tracked
    assert "data/raw/SRC-007/2026-10-28/sirene.csv" not in tracked
    assert "data/interim/sirene_ml.parquet" not in tracked
