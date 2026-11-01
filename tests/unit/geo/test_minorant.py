"""Minorant d'un comptage par zone (conventions §3, règle 7)."""

import pytest
from geodata import square, write_geojson, write_sirene

from traboule.geo.jointure import load_zonage
from traboule.geo.minorant import (
    load_units,
    units_intersecting,
    without_public_position,
    zone_lower_bound,
)


def wkt(x0, y0, x1, y1) -> str:
    return f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0}))"


@pytest.fixture
def con(spatial, zonage):
    load_zonage(spatial, zonage)  # UEi2 = carré (0, 0)–(100, 100)
    spatial.execute("create table unites (code varchar, niveau varchar, geom geometry)")
    for code, box in [
        ("69001", (0, 0, 100, 100)),  # contient UEi2
        ("69002", (100, 0, 200, 100)),  # contact de bordure seulement (0 m²)
        ("69003", (99.5, 0, 150, 100)),  # bande de 0,5 m × 100 m = 50 m² : écartée
        ("69004", (98, 0, 150, 100)),  # bande de 2 m × 100 m = 200 m² : retenue
    ]:
        spatial.execute(
            "insert into unites values (?, 'commune', ST_GeomFromText(?))", [code, wkt(*box)]
        )
    return spatial


def test_border_contacts_and_slivers_are_excluded(con):
    assert units_intersecting(con, "UEi2") == ["69001", "69004"]


def sirene_row(siret, commune, diffusion="O", geoloc=True, etat="A", naf="47.11B", arr=None):
    position = geoloc and diffusion == "O"
    return (siret, etat, diffusion, commune, arr, None, None, None, None, None, naf, geoloc,
            position)  # fmt: skip


@pytest.fixture
def sirene(tmp_path):
    return write_sirene(
        tmp_path / "sirene_ml.parquet",
        [
            sirene_row("00000000000001", "69001", diffusion="P"),  # P géolocalisé : compte
            sirene_row("00000000000002", "69001", geoloc=False),  # sans coordonnées : compte
            sirene_row("00000000000003", "69001"),  # position publique : ne compte pas
            sirene_row("00000000000004", "69001", diffusion="P", etat="F"),  # fermé
            sirene_row("00000000000005", "69004", diffusion="P", naf="25.11Z"),  # autre activité
            sirene_row("00000000000006", "69002", diffusion="P"),  # commune écartée
            sirene_row("00000000000007", "69123", diffusion="P", arr="69387"),  # Lyon 7e
            sirene_row("00000000000008", "69123", diffusion="P", arr="69381"),  # Lyon 1er
        ],
    )


def test_without_public_position_means_status_p_or_no_coordinates(con, sirene):
    assert without_public_position(con, sirene, ["69001", "69004"]) == 3
    activity = "substr(activitePrincipaleEtablissement, 1, 2) = '47'"
    assert without_public_position(con, sirene, ["69001", "69004"], activity) == 2


def test_lyon_counts_by_arrondissement_or_by_commune(con, sirene):
    # Règle 5 : arrondissement et commune ne sont jamais confondus.
    assert without_public_position(con, sirene, ["69387"]) == 1
    assert without_public_position(con, sirene, ["69123"]) == 2


def test_zone_lower_bound_wording(con, sirene):
    m = zone_lower_bound(con, sirene, "UEi2")
    assert (m.n, m.perimetre) == (3, "2 unités géographiques qui intersectent UEi2")
    assert m.formulation.startswith("jusqu'à 3 établissements supplémentaires")


def test_load_units_replaces_lyon_by_its_arrondissements(spatial, tmp_path):
    lon, lat = 4.83, 45.75  # carrés minuscules autour de Lyon, en EPSG:4326
    communes = write_geojson(
        tmp_path / "communes.geojson",
        [
            ({"insee": "69123"}, square(lon, lat, lon + 0.01, lat + 0.01)),
            ({"insee": "69259"}, square(lon + 0.02, lat, lon + 0.03, lat + 0.01)),
        ],
        4326,
    )
    arrondissements = write_geojson(
        tmp_path / "arr.geojson",
        [({"insee": "69387"}, square(842000, 6518000, 843000, 6519000))],
        2154,
    )
    assert load_units(spatial, communes) == 2
    assert load_units(spatial, communes, arrondissements) == 2
    rows = spatial.execute("select code, niveau from unites order by 1").fetchall()
    assert rows == [("69259", "commune"), ("69387", "arrondissement_municipal")]
