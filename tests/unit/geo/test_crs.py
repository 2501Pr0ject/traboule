"""Systèmes de coordonnées (conventions §4)."""

import pytest
from geodata import square, write_geojson

from traboule.geo.crs import CRSError, declared_crs, require_crs, to_lambert93


def test_bellecour_reprojection_with_always_xy(spatial):
    # Place Bellecour : (4,8320 ; 45,7578) en EPSG:4326 → environ (842 395 ; 6 519 229).
    x, y = spatial.execute(
        f"select ST_X(g), ST_Y(g) from (select {to_lambert93('ST_Point(4.8320, 45.7578)')} g)"
    ).fetchone()
    assert abs(x - 842395) < 50 and abs(y - 6519229) < 50


def test_declared_crs_is_read_not_assumed(spatial, tmp_path):
    path = write_geojson(tmp_path / "a.geojson", [({}, square(0, 0, 1, 1))], 2154)
    assert declared_crs(spatial, path) == "EPSG:2154"


def test_unexpected_crs_is_rejected(spatial, tmp_path):
    path = write_geojson(tmp_path / "b.geojson", [({}, square(4, 45, 5, 46))], 4326)
    with pytest.raises(CRSError, match="EPSG:4326"):
        require_crs(spatial, path, "EPSG:2154")
