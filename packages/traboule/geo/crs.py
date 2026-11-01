"""Systèmes de coordonnées (conventions §4) : Lambert 93 = EPSG:2154, CRS de travail.

Le CRS déclaré d'un fichier est lu, jamais supposé ; toute reprojection passe
`always_xy := true` explicitement (DuckDB 2.0 refuse sinon, ADR-0002).
"""

from pathlib import Path

import duckdb

LAMBERT93 = "EPSG:2154"


class CRSError(RuntimeError):
    """CRS déclaré absent ou différent de celui attendu."""


def to_lambert93(expr: str, source: str = "EPSG:4326") -> str:
    """Expression SQL qui reprojette `expr` de `source` vers EPSG:2154."""
    return f"ST_Transform({expr}, '{source}', '{LAMBERT93}', always_xy := true)"


def declared_crs(con: duckdb.DuckDBPyConnection, path: Path) -> str | None:
    """CRS déclaré par un fichier vectoriel, sous la forme « EPSG:<code> »."""
    code = con.execute(
        f"select layers[1].geometry_fields[1].crs.auth_code from ST_Read_Meta('{path}')"
    ).fetchone()[0]
    return f"EPSG:{code}" if code else None


def require_crs(con: duckdb.DuckDBPyConnection, path: Path, expected: str) -> None:
    """Échoue si le CRS déclaré de `path` n'est pas `expected`."""
    found = declared_crs(con, path)
    if found != expected:
        raise CRSError(f"{path.name} : CRS déclaré {found}, attendu {expected}")
