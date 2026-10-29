"""Mesure du pic mémoire et écriture des métriques (conventions §1, §8)."""

import json

from traboule.measure import measured, peak_rss_bytes, write_metrics


def test_maxrss_is_bytes_on_macos_and_kilobytes_on_linux():
    assert peak_rss_bytes(maxrss=2048, system="darwin") == 2048
    assert peak_rss_bytes(maxrss=2048, system="linux") == 2048 * 1024


def test_current_process_peak_is_plausible():
    # Un interpréteur Python avec pytest occupe plus de 10 Mo et moins de 16 Go.
    assert 10 * 2**20 < peak_rss_bytes() < 16 * 2**30


def test_measured_records_duration_and_peak():
    steps: dict = {}
    with measured(steps, "etape"):
        pass
    assert set(steps["etape"]) == {"seconds", "peak_rss_mb"}
    assert steps["etape"]["peak_rss_mb"] > 0


def test_metrics_file_carries_config_and_versions(tmp_path):
    path = tmp_path / "out" / "metrics.json"
    write_metrics(path, {"lignes": 3}, {"seuil": 10})
    data = json.loads(path.read_text())
    assert data["config"] == {"seuil": 10}
    assert data["metrics"] == {"lignes": 3}
    assert "duckdb" in data["environment"]["packages"]
