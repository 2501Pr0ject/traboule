"""Jointure spatiale (règle 10, catégories, ADR-0006), sur un zonage synthétique en EPSG:2154."""

import duckdb
import pytest
from geodata import square, write_geojson, write_sirene

from traboule.geo.crs import CRSError
from traboule.geo.jointure import build, write


def row(siret, x, y, q="11", stock=None, diffusion="O", position=True, commune="69259"):
    sx, sy = (str(stock[0]), str(stock[1])) if stock else ("[ND]", "[ND]")
    return (siret, "A", diffusion, commune, None, q, x, y, sx, sy, "25.11Z", x is not None,
            position)  # fmt: skip


ROWS = [
    row("00000000000001", 50, 50, stock=(50, 50)),  # UEi2, à 50 m de UEi1 → haute
    row("00000000000002", 95, 50, stock=(95, 50)),  # à 5 m de UEi1 → faible
    row("00000000000003", 50, 50, q="21", stock=(50, 50)),  # qualité 21 → moyenne
    row("00000000000004", 50, 50),  # stock absent → moyenne
    row("00000000000005", 50, 50, stock=(150, 50)),  # stock en UEi1 → faible
    row("00000000000006", 500, 500, stock=(500, 500)),  # hors zonage
    row("00000000000007", 50, 250, stock=(50, 250)),  # secteur sauvegardé
    row("00000000000008", 10, 10, stock=(10, 10)),  # UEi2 et UCe1 → multi_zones
    # Statut P : exclu même si une position lui était attribuée par erreur (règle 10).
    row("00000000000009", 50, 50, stock=(50, 50), diffusion="P", position=True),
    row("00000000000010", None, None, position=False),  # sans coordonnées
]


@pytest.fixture
def result(spatial, zonage, tmp_path):
    sirene = write_sirene(tmp_path / "sirene_ml.parquet", ROWS)
    out = tmp_path / "etablissements_zones.parquet"
    measures = build(spatial, sirene, zonage)
    write(spatial, out)
    cur = duckdb.execute(f"select * from read_parquet('{out}')")
    cols = [d[0] for d in cur.description]
    return measures, {r[0]: dict(zip(cols, r, strict=True)) for r in cur.fetchall()}


def test_status_p_and_no_coordinates_never_enter_the_join(result):
    measures, rows = result
    assert "00000000000009" not in rows and "00000000000010" not in rows
    assert measures["points"] == 8 and {r["diffusion"] for r in rows.values()} == {"O"}


@pytest.mark.parametrize(
    "siret,zone,confiance",
    [
        ("00000000000001", "UEi2", "haute"),
        ("00000000000002", "UEi2", "faible"),
        ("00000000000003", "UEi2", "moyenne"),
        ("00000000000004", "UEi2", "moyenne"),
        ("00000000000005", "UEi2", "faible"),
    ],
)
def test_zone_and_confidence(result, siret, zone, confiance):
    r = result[1][siret]
    assert (r["categorie"], r["zone"], r["confiance"]) == ("une_zone", zone, confiance)


def test_distance_to_other_zone(result):
    rows = result[1]
    assert rows["00000000000001"]["dist_autre_zone_m"] == pytest.approx(1800**0.5)  # coin de UCe1
    assert rows["00000000000002"]["dist_autre_zone_m"] == pytest.approx(5.0)


def test_categories(result):
    rows = result[1]
    assert rows["00000000000006"]["categorie"] == "aucune_zone"
    assert rows["00000000000006"]["confiance"] is None
    assert (rows["00000000000007"]["categorie"], rows["00000000000007"]["zone"]) == (
        "secteur_sauvegarde",
        "SECTSAUV",
    )
    assert rows["00000000000008"]["categorie"] == "multi_zones"
    assert rows["00000000000008"]["zone"] is None


def test_zonage_in_wrong_crs_is_rejected(spatial, tmp_path):
    bad = write_geojson(tmp_path / "z4326.geojson", [({"zone": "U", "zonage": "U1"},
                                                     square(4, 45, 5, 46))], 4326)  # fmt: skip
    sirene = write_sirene(tmp_path / "s.parquet", ROWS[:1])
    with pytest.raises(CRSError):
        build(spatial, sirene, bad)
