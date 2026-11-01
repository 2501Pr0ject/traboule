"""Fonctions de données synthétiques pour les tests géographiques (aucune donnée Sirene réelle)."""

import json
from pathlib import Path

import duckdb

SIRENE_COLUMNS = (
    "siret varchar, etatAdministratifEtablissement varchar, statutDiffusionEtablissement varchar, "
    "code_commune_cog2026 varchar, code_arrondissement varchar, qualite_xy varchar, x float, "
    "y float, coordonneeLambertAbscisseEtablissement varchar, "
    "coordonneeLambertOrdonneeEtablissement varchar, activitePrincipaleEtablissement varchar, "
    "geoloc_present boolean, position_publique boolean"
)


def square(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
    }


def write_geojson(path: Path, features: list[tuple[dict, dict]], epsg: int) -> Path:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"}},
                "features": [
                    {"type": "Feature", "properties": props, "geometry": geom}
                    for props, geom in features
                ],
            }
        )
    )
    return path


def write_sirene(path: Path, rows: list[tuple]) -> Path:
    con = duckdb.connect()
    con.execute(f"create table s ({SIRENE_COLUMNS})")
    con.executemany(f"insert into s values ({', '.join('?' * 13)})", rows)
    con.execute(f"copy s to '{path}' (format parquet)")
    return path
