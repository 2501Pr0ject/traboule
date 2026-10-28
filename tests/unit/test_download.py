"""Immuabilité par ressource dans spikes/download.py (sans réseau)."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("download", ROOT / "spikes" / "download.py")
download = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download)

PAYLOAD = b"%PDF-1.7 contenu de test"


def make_source(*names: str) -> dict:
    return {
        "id": "SRC-TEST",
        "title": "Source de test",
        "publisher": "Test",
        "license": "Licence Ouverte 2.0",
        "resources": [
            {
                "name": name,
                "title": f"{name}.pdf",
                "kind": "http",
                "url": f"https://exemple.test/{name}.pdf",
                "format": "pdf",
            }
            for name in names
        ],
    }


def mock_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=PAYLOAD))
    )


def is_writable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o222)


@pytest.fixture
def date_dir(tmp_path: Path) -> Path:
    """Dossier daté contenant déjà une ressource « ancienne », en lecture seule."""
    d = tmp_path / "SRC-TEST" / "2026-10-28"
    with mock_client() as client:
        download.download_source(client, make_source("ancienne"), d)
    return d


def test_new_resource_in_existing_date_dir_succeeds(date_dir: Path) -> None:
    with mock_client() as client:
        download.download_source(
            client, make_source("ancienne", "nouvelle"), date_dir, ["nouvelle"]
        )
    new = date_dir / "nouvelle"
    manifest = download.Manifest(**json.loads((new / "manifest.json").read_text()))
    assert manifest.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert (new / "nouvelle.pdf").read_bytes() == PAYLOAD
    assert not any(is_writable(p) for p in [new, *new.rglob("*")])
    assert is_writable(date_dir)
    assert not list(date_dir.glob(".*.partial"))


def test_rewriting_existing_resource_fails(date_dir: Path) -> None:
    old = date_dir / "ancienne"
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in old.iterdir()}
    with mock_client() as client, pytest.raises(download.DownloadError, match="déjà présente"):
        download.download_source(client, make_source("ancienne"), date_dir, ["ancienne"])
    after = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in old.iterdir()}
    assert after == before
    assert not is_writable(old)


def test_unknown_resource_is_rejected(date_dir: Path) -> None:
    with mock_client() as client, pytest.raises(download.DownloadError, match="inconnue"):
        download.download_source(client, make_source("ancienne"), date_dir, ["absente"])


@pytest.fixture(autouse=True)
def _restore_permissions(tmp_path: Path):
    """Rend les dossiers de test supprimables à la fin."""
    yield
    for root, dirs, files in os.walk(tmp_path):
        for name in dirs + files:
            os.chmod(os.path.join(root, name), 0o755)
