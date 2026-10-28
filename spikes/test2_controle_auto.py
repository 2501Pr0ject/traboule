"""Test 2 : contrôle automatique indépendant des 20 établissements tirés (validation, arbitrage).

Script jetable. Remplace la vérification humaine sur décision du 2026-10-28, avec la
mention « automatique » dans le rapport. Chaîne indépendante de la jointure :
adresse déclarée → géocodage BAN (Géoplateforme) → parcelle cadastrale (API Carto
cadastre) → zones du GPU sur la parcelle (API Carto GPU, zone-urba).
Les adresses ne quittent pas spikes/output/test2/ (local, jamais versionné) ; le résumé
JSON n'en contient aucune.
"""

import csv
import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import duckdb
import httpx
import typer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "spikes" / "output" / "test2"
CONTROLS = OUTPUT_DIR / "controles.csv"
GEOCODE = "https://data.geopf.fr/geocodage/search"
PARCELLE = "https://apicarto.ign.fr/api/cadastre/parcelle"
ZONE_URBA = "https://apicarto.ign.fr/api/gpu/zone-urba"
FALLBACK_RADIUS_M = 20
MIN_SCORE = 0.7

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


def point_from_link(link: str) -> tuple[float, float] | None:
    """Lit lon / lat dans un lien de la visionneuse GPU (#lon=…&lat=…&zoom=…)."""
    if not link:
        return None
    params = parse_qs(urlsplit(link).fragment)
    return float(params["lon"][0]), float(params["lat"][0])


def geojson_point(lon: float, lat: float) -> str:
    return json.dumps({"type": "Point", "coordinates": [lon, lat]})


def geocode(client: httpx.Client, row: dict) -> dict | None:
    query = f"{row['adresse_voie']} {row['code_postal']} {row['commune']}"
    resp = client.get(
        GEOCODE, params={"q": query, "postcode": row["code_postal"], "limit": 1, "index": "address"}
    )
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None
    f = features[0]
    lon, lat = f["geometry"]["coordinates"]
    return {
        "lon": lon,
        "lat": lat,
        "score": f["properties"]["score"],
        "type": f["properties"]["type"],
    }


def parcel_at(client: httpx.Client, con, lon: float, lat: float) -> tuple[dict | None, str]:
    """Parcelle contenant le point, sinon la plus proche dans un rayon de 20 m."""
    resp = client.get(PARCELLE, params={"geom": geojson_point(lon, lat)})
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if features:
        return features[0], "contient le point"
    box = con.execute(
        f"""select ST_AsGeoJSON(ST_Transform(ST_Buffer(ST_Transform(ST_Point({lon}, {lat}),
               'EPSG:4326', 'EPSG:2154', always_xy := true), {FALLBACK_RADIUS_M}),
               'EPSG:2154', 'EPSG:4326', always_xy := true))"""
    ).fetchone()[0]
    resp = client.get(PARCELLE, params={"geom": box})
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None, f"aucune parcelle à moins de {FALLBACK_RADIUS_M} m"
    best = min(features, key=lambda f: distance_m(con, f["geometry"], lon, lat))
    return best, f"plus proche à {distance_m(con, best['geometry'], lon, lat):.1f} m"


def distance_m(con, geometry: dict, lon: float, lat: float) -> float:
    """Distance en mètres (Lambert 93) entre une géométrie GeoJSON WGS84 et un point."""
    return con.execute(
        """select ST_Distance(
               ST_Transform(ST_GeomFromGeoJSON(?), 'EPSG:4326', 'EPSG:2154', always_xy := true),
               ST_Transform(ST_Point(?, ?), 'EPSG:4326', 'EPSG:2154', always_xy := true))""",
        [json.dumps(geometry), lon, lat],
    ).fetchone()[0]


def zones_on(client: httpx.Client, geometry: dict) -> list[str]:
    resp = client.get(ZONE_URBA, params={"geom": json.dumps(geometry)})
    resp.raise_for_status()
    return sorted({f["properties"]["libelle"] for f in resp.json().get("features", [])})


def assess(con, client: httpx.Client, row: dict) -> dict:
    main = point_from_link(row["lien_gpu_principal"])
    stock = point_from_link(row["lien_gpu_stock"])
    out = {"num": row["num"], "echantillon": row["echantillon"]}
    ban = geocode(client, row)
    if ban is None:
        return out | {"statut": "indeterminable", "cause_auto": "adresse non géocodée"}
    out |= {"ban_score": round(ban["score"], 3), "ban_type": ban["type"]}
    parcel, how = parcel_at(client, con, ban["lon"], ban["lat"])
    out["parcelle"] = how
    zones_parcel = zones_on(client, parcel["geometry"]) if parcel else []
    zones_ban_point = zones_on(client, json.loads(geojson_point(ban["lon"], ban["lat"])))
    zones_gpu_main = zones_on(client, json.loads(geojson_point(*main)))
    out |= {
        "zones_parcelle_gpu": zones_parcel,
        "zone_point_ban_gpu": zones_ban_point,
        "zone_point_principal_gpu": zones_gpu_main,
        "zone_principale_grandlyon": row["zone_principale"],
        "zone_stock_grandlyon": row["zone_stock"],
    }
    if parcel:
        out["dist_principal_parcelle_m"] = round(distance_m(con, parcel["geometry"], *main), 1)
        if stock:
            out["dist_stock_parcelle_m"] = round(distance_m(con, parcel["geometry"], *stock), 1)
    expected = zones_parcel or zones_ban_point
    out["zone_attendue"] = "|".join(expected)

    # Statut de la zone principale, et cause d'un écart (liste fermée de la méthode)
    if ban["score"] < MIN_SCORE or ban["type"] != "housenumber":
        out |= {"statut": "indeterminable", "cause_auto": "adresse imprécise (BAN)"}
    elif expected == [row["zone_principale"]]:
        out |= {"statut": "correct", "cause_auto": ""}
    elif row["zone_principale"] in expected:
        out |= {"statut": "limite", "cause_auto": "limite"}
    elif zones_gpu_main and zones_gpu_main != [row["zone_principale"]]:
        out |= {"statut": "ecart", "cause_auto": "version"}
    else:
        out |= {"statut": "ecart", "cause_auto": "geocodage"}

    # Indicateur de proximité (pas un jugement sur le bâtiment réel)
    d_main, d_stock = out.get("dist_principal_parcelle_m"), out.get("dist_stock_parcelle_m")
    if d_main is None:
        out["plus_proche_parcelle"] = "indeterminable"
    elif d_stock is None:
        out["plus_proche_parcelle"] = "principale (stock absent)"
    elif abs(d_main - d_stock) < 1:
        out["plus_proche_parcelle"] = "les_deux"
    else:
        out["plus_proche_parcelle"] = "principale" if d_main < d_stock else "stock"
    return out


@app.command()
def main() -> None:
    """Remplit la grille de contrôle par la chaîne automatique BAN → cadastre → GPU."""
    rows = list(csv.DictReader(CONTROLS.open(encoding="utf-8")))
    backup = OUTPUT_DIR / "controles.vide.csv"
    if not backup.exists():
        shutil.copy(CONTROLS, backup)
    con = duckdb.connect()
    con.load_extension("spatial")
    results = []
    with httpx.Client(timeout=60) as client:
        for row in rows:
            res = assess(con, client, row)
            results.append(res)
            row["zone_attendue"] = res.get("zone_attendue", "")
            row["source_juste"] = f"auto:{res.get('plus_proche_parcelle', 'indeterminable')}"
            row["commentaire"] = f"auto:{res['statut']}" + (
                f" ({res['cause_auto']})" if res.get("cause_auto") else ""
            )
            typer.echo(
                f"  #{res['num']:>2} {res['echantillon']:<10} {row['zone_principale']:<7} "
                f"attendue={res.get('zone_attendue', '')!s:<12} {res['statut']:<14} "
                f"{res.get('cause_auto', '')}"
            )
    with CONTROLS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUTPUT_DIR / "controles_auto.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    )
    typer.echo(f"Grille : {CONTROLS} ; détail sans adresse : controles_auto.json")


if __name__ == "__main__":
    app()
