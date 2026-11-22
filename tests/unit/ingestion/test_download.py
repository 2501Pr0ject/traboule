"""Téléchargement avec manifeste et immuabilité par ressource (conventions §3, règles 1 à 3).

Sans réseau : le serveur est simulé par httpx.MockTransport.
"""

import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest

from traboule.contracts import Manifest
from traboule.ingestion import download as dl

PAYLOAD = b"%PDF-1.7 contenu de test"
SHA1 = hashlib.sha1(PAYLOAD).hexdigest()


def http_resource(name: str, **kw) -> dict:
    url = kw.pop("url", f"https://exemple.test/{name}.pdf")
    return {"name": name, "title": f"{name}.pdf", "kind": "http", "url": url, "format": "pdf"} | kw


def make_source(*resources: dict) -> dict:
    return {
        "id": "SRC-TEST",
        "title": "Source de test",
        "publisher": "Test",
        "license": "Licence Ouverte 2.0",
        "resources": list(resources),
    }


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def serve_payload(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=PAYLOAD)


def serve_with_datagouv(published: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.data.gouv.fr":
            return httpx.Response(200, json={"resources": [{"id": "r1"} | published]})
        return httpx.Response(200, content=PAYLOAD)

    return handler


def is_writable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o222)


@pytest.fixture(autouse=True)
def _restore_permissions(tmp_path: Path):
    """Rend les dossiers de test supprimables à la fin."""
    yield
    for root, dirs, files in os.walk(tmp_path):
        for name in dirs + files:
            os.chmod(os.path.join(root, name), 0o755)


@pytest.fixture
def date_dir(tmp_path: Path) -> Path:
    """Dossier daté contenant déjà une ressource « ancienne », en lecture seule."""
    d = tmp_path / "SRC-TEST" / "2026-10-28"
    with client_for(serve_payload) as client:
        dl.download_source(client, make_source(http_resource("ancienne")), d)
    return d


def test_new_resource_in_existing_date_dir_succeeds(date_dir: Path) -> None:
    source = make_source(http_resource("ancienne"), http_resource("nouvelle"))
    with client_for(serve_payload) as client:
        dl.download_source(client, source, date_dir, ["nouvelle"])
    new = date_dir / "nouvelle"
    manifest = Manifest(**json.loads((new / "manifest.json").read_text()))
    assert manifest.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert (new / "nouvelle.pdf").read_bytes() == PAYLOAD
    assert not any(is_writable(p) for p in [new, *new.rglob("*")])
    assert is_writable(date_dir)
    assert not list(date_dir.glob(".*.partial"))


def test_rewriting_existing_resource_fails(date_dir: Path) -> None:
    old = date_dir / "ancienne"
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in old.iterdir()}
    with (
        client_for(serve_payload) as client,
        pytest.raises(dl.DownloadError, match="déjà présente"),
    ):
        dl.download_source(client, make_source(http_resource("ancienne")), date_dir)
    after = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in old.iterdir()}
    assert after == before
    assert not is_writable(old)


def test_unknown_resource_is_rejected(date_dir: Path) -> None:
    with client_for(serve_payload) as client, pytest.raises(dl.DownloadError, match="inconnue"):
        dl.download_source(client, make_source(http_resource("ancienne")), date_dir, ["absente"])


def test_unconfirmed_url_is_refused_before_any_request(tmp_path: Path) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return serve_payload(request)

    source = make_source(http_resource("ok"), http_resource("douteuse", url="A_CONFIRMER"))
    with client_for(handler) as client, pytest.raises(dl.DownloadError, match="A_CONFIRMER"):
        dl.download_source(client, source, tmp_path / "d")
    assert not calls


def test_datagouv_sha1_and_size_are_checked(tmp_path: Path) -> None:
    resource = http_resource("f", datagouv={"dataset": "ds", "resource": "r1"})
    ok = {"checksum": {"type": "sha1", "value": SHA1}, "filesize": len(PAYLOAD)}
    with client_for(serve_with_datagouv(ok)) as client:
        dl.download_source(client, make_source(resource), tmp_path / "ok")

    bad = {"checksum": {"type": "sha1", "value": "0" * 40}, "filesize": len(PAYLOAD)}
    with (
        client_for(serve_with_datagouv(bad)) as client,
        pytest.raises(dl.DownloadError, match="sha1"),
    ):
        dl.download_source(client, make_source(resource), tmp_path / "bad")
    assert not (tmp_path / "bad" / "f").exists()  # aucune ressource validée


def test_datagouv_size_mismatch_fails() -> None:
    published = {"checksum": {"type": "sha1", "value": SHA1}, "filesize": 1}
    with pytest.raises(dl.DownloadError, match="taille"):
        dl.check_datagouv(published, len(PAYLOAD), SHA1)


def test_datagouv_analysis_checksum_fallback_is_noted() -> None:
    published = {
        "checksum": {"type": "sha1", "value": "0" * 40},
        "extras": {"analysis:checksum": SHA1, "analysis:last-modified-at": "2026-10-01"},
    }
    assert "analysis:checksum" in dl.check_datagouv(published, len(PAYLOAD), SHA1)


def wfs_handler(features: int, matched: int):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("resultType") == "hits":
            return httpx.Response(200, text=f'<wfs:FeatureCollection numberMatched="{matched}"/>')
        body = {
            "type": "FeatureCollection",
            "crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::2154"}},
            "features": [{"type": "Feature"}] * features,
        }
        return httpx.Response(200, json=body)

    return handler


WFS = {
    "name": "zonage",
    "kind": "wfs",
    "format": "geojson",
    "urls": ["https://exemple.test/ows?SERVICE=WFS&typename=z&outputFormat=application/json"],
}


def test_wfs_count_matches_number_matched(tmp_path: Path) -> None:
    with client_for(wfs_handler(3, 3)) as client:
        ((manifest, _, status),) = dl.download_source(client, make_source(WFS), tmp_path / "d")
    assert status == "téléchargée"
    assert manifest.crs == "urn:ogc:def:crs:EPSG::2154"
    with client_for(wfs_handler(2, 3)) as client, pytest.raises(dl.DownloadError, match="3"):
        dl.download_source(client, make_source(WFS), tmp_path / "e")


def test_wfs_hits_url_drops_output_format() -> None:
    url = dl.wfs_hits_url(WFS["urls"][0] + "&count=10")
    assert "resultType=hits" in url and "outputFormat" not in url and "count" not in url


def clone_like(date_dir: Path, name: str = "ancienne") -> Path:
    """Dossier de ressource réduit à son manifeste, comme dans un clone neuf."""
    folder = date_dir / name
    os.chmod(folder, 0o755)
    for path in folder.iterdir():
        os.chmod(path, 0o644)
        if path.name != "manifest.json":
            path.unlink()
    return folder


def test_manifest_only_folder_is_restored_when_identical(date_dir: Path) -> None:
    folder = clone_like(date_dir)
    manifest_before = (folder / "manifest.json").read_text()
    with client_for(serve_payload) as client:
        ((_, final, status),) = dl.download_source(
            client, make_source(http_resource("ancienne")), date_dir, today="2026-11-22"
        )
    assert (final, status) == (folder, "identique à la référence")
    assert (folder / "ancienne.pdf").read_bytes() == PAYLOAD
    assert (folder / "manifest.json").read_text() == manifest_before  # manifeste versionné intact
    assert not is_writable(folder)
    assert not (date_dir.parent / "2026-11-22").exists()


def test_changed_resource_goes_to_a_new_dated_folder(date_dir: Path) -> None:
    folder = clone_like(date_dir)

    def changed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"version suivante")

    with client_for(changed) as client:
        ((manifest, final, status),) = dl.download_source(
            client, make_source(http_resource("ancienne")), date_dir, today="2026-11-22"
        )
    assert status == "écart" and final == date_dir.parent / "2026-11-22" / "ancienne"
    assert (final / "ancienne.pdf").read_bytes() == b"version suivante"
    assert "Version différente de la référence du 2026-10-28" in manifest.limitations
    assert manifest.published_at is None and manifest.reference_date is None
    assert [p.name for p in folder.iterdir()] == ["manifest.json"]  # référence intacte
    with client_for(changed) as client:  # relance le même jour : rien à refaire
        ((_, again, status),) = dl.download_source(
            client, make_source(http_resource("ancienne")), date_dir, today="2026-11-22"
        )
    assert (again, status) == (final, "écart")


def test_updated_datagouv_resource_uses_the_current_url(date_dir: Path) -> None:
    clone_like(date_dir)
    new = b"stock du mois suivant"
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "www.data.gouv.fr":
            current = {"id": "r1", "url": "https://exemple.test/courant.pdf",
                       "checksum": {"type": "sha1", "value": hashlib.sha1(new).hexdigest()},
                       "filesize": len(new), "last_modified": "2026-11-01T08:00:00"}  # fmt: skip
            return httpx.Response(200, json={"resources": [current]})
        if request.url.path == "/ancienne.pdf":
            return httpx.Response(404)  # fichier de référence retiré par le producteur
        return httpx.Response(200, content=new)

    resource = http_resource("ancienne", datagouv={"dataset": "d1", "resource": "r1"})
    with client_for(handler) as client:
        ((manifest, final, status),) = dl.download_source(
            client, make_source(resource), date_dir, today="2026-11-22"
        )
    assert status == "écart" and manifest.source_url == "https://exemple.test/courant.pdf"
    assert str(manifest.published_at) == "2026-11-01"
    assert (final / "courant.pdf").read_bytes() == new


def test_same_size_but_different_content_goes_to_a_new_dated_folder(date_dir: Path) -> None:
    folder = clone_like(date_dir)
    same_size = bytes(reversed(PAYLOAD))
    assert len(same_size) == len(PAYLOAD) and same_size != PAYLOAD
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, content=same_size)  # HEAD : même content-length

    with client_for(handler) as client:
        ((manifest, final, status),) = dl.download_source(
            client, make_source(http_resource("ancienne")), date_dir, today="2026-11-22"
        )
    assert status == "écart" and final == date_dir.parent / "2026-11-22" / "ancienne"
    assert manifest.sha256 == hashlib.sha256(same_size).hexdigest()
    assert [p.name for p in folder.iterdir()] == ["manifest.json"]
    assert calls.count("GET") == 1  # un seul téléchargement
