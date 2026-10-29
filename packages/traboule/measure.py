"""Mesures d'une étape lourde : pic mémoire, durée, environnement (conventions §1, §8).

Une opération lourde = une commande = un processus : le pic mémoire du processus est donc
celui de l'étape. La mémoire MPS des embeddings se lit à part avec `torch.mps`.
"""

import json
import platform
import resource
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


def peak_rss_bytes(maxrss: int | None = None, system: str = sys.platform) -> int:
    """Pic de mémoire résidente du processus, en octets.

    `ru_maxrss` est en octets sous macOS et en kilo-octets sous Linux.
    """
    if maxrss is None:
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maxrss if system == "darwin" else maxrss * 1024


def environment(packages: tuple[str, ...] = ("duckdb", "pydantic", "polars")) -> dict[str, Any]:
    """Versions de Python, de la plateforme et des dépendances utilisées."""
    versions = {}
    for name in packages:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": versions,
    }


@contextmanager
def measured(steps: dict[str, Any], name: str) -> Iterator[None]:
    """Consigne dans `steps[name]` la durée et le pic mémoire du processus à la fin du bloc."""
    start = time.perf_counter()
    try:
        yield
    finally:
        steps[name] = {
            "seconds": round(time.perf_counter() - start, 3),
            "peak_rss_mb": round(peak_rss_bytes() / 2**20, 1),
        }


def write_metrics(path: Path, metrics: dict[str, Any], config: dict[str, Any]) -> None:
    """Écrit les mesures avec la configuration et les versions (conventions §8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": config,
        "environment": environment(),
        "metrics": metrics,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
