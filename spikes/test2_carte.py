"""Test 2 : régénère carte_controles.html à partir de controles.csv (remplacements inclus).

Script jetable. Reprend le gabarit Leaflet de test2_jointure.py ; positions lues dans les
liens GPU de la grille ; zones SRC-002 à moins de 150 m. Ni adresse, ni SIRET, ni nom.
"""

import csv
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test2_jointure import LEAFLET, MAP_TEMPLATE, ORTHO_URL, OUTPUT_DIR, ZONAGE  # noqa: E402


def link_point(link: str) -> tuple[float, float] | None:
    if not link:
        return None
    fragment = parse_qs(urlsplit(link).fragment)
    return float(fragment["lon"][0]), float(fragment["lat"][0])


def main() -> None:
    rows = list(csv.DictReader((OUTPUT_DIR / "controles.csv").open(encoding="utf-8")))
    points = []
    for r in rows:
        main_pt, stock_pt = link_point(r["lien_gpu_principal"]), link_point(r["lien_gpu_stock"])
        points.append(
            {
                "num": int(r["num"]), "echantillon": r["echantillon"],
                "zone": r["zone_principale"] or None, "zone_stock": r["zone_stock"] or None,
                "lon": main_pt[0], "lat": main_pt[1],
                "lon_stock": stock_pt[0] if stock_pt else None,
                "lat_stock": stock_pt[1] if stock_pt else None,
                "gpu": r["lien_gpu_principal"],
            }
        )  # fmt: skip
    con = duckdb.connect()
    con.load_extension("spatial")
    con.execute(
        f"create table z as select coalesce(zonage, zone) code, geom from ST_Read('{ZONAGE}')"
    )
    con.execute("create table c (g geometry)")
    for p in points:
        for lon, lat in ((p["lon"], p["lat"]), (p["lon_stock"], p["lat_stock"])):
            if lon is not None:
                con.execute(
                    """insert into c select ST_Transform(ST_Point(?, ?), 'EPSG:4326', 'EPSG:2154',
                       always_xy := true)""",
                    [lon, lat],
                )
    zones = con.execute(
        """select distinct z.code,
                  ST_AsGeoJSON(ST_Transform(z.geom, 'EPSG:2154', 'EPSG:4326', always_xy := true))
           from z, c where ST_DWithin(z.geom, c.g, 150)"""
    ).fetchall()
    features = [
        {"type": "Feature", "properties": {"code": code}, "geometry": json.loads(gj)}
        for code, gj in zones
    ]
    html = MAP_TEMPLATE.replace("__LEAFLET__", LEAFLET).replace("__ORTHO__", ORTHO_URL)
    html = html.replace(
        "__ZONES__", json.dumps({"type": "FeatureCollection", "features": features})
    )
    html = html.replace("__POINTS__", json.dumps(points))
    (OUTPUT_DIR / "carte_controles.html").write_text(html, encoding="utf-8")
    print(f"{len(points)} contrôles, {len(features)} zones → {OUTPUT_DIR / 'carte_controles.html'}")


if __name__ == "__main__":
    main()
