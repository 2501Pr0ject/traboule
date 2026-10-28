"""Test 2 : vérification par les bâtiments des contrôles de validation non confirmés.

Script jetable. Pour chaque contrôle demandé : bâtiments BD TOPO (IGN, WFS Géoplateforme)
autour du point d'adresse BAN et des deux points (principal, stock), usage et zone(s) de
chaque bâtiment (part de surface par zone, zonage SRC-002 dont la concordance avec le GPU
a été constatée), zones présentes à proximité. Vérification par les données, pas visuelle.
N'affiche ni adresse ni SIRET.
"""

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

import duckdb
import httpx
import typer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "spikes" / "output" / "test2"
ZONAGE = ROOT / "data/raw/SRC-002/2026-10-28/zonage/zonage.geojson"
GEOCODE = "https://data.geopf.fr/geocodage/search"
WFS = "https://data.geopf.fr/wfs/ows"
RADIUS_M = 300

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


def point_from_link(link: str) -> tuple[float, float] | None:
    if not link:
        return None
    params = parse_qs(urlsplit(link).fragment)
    return float(params["lon"][0]), float(params["lat"][0])


def buildings_around(client: httpx.Client, lon: float, lat: float, radius_m: float) -> list[dict]:
    dlat, dlon = radius_m / 111_000, radius_m / 78_000  # ordre de grandeur à 45,7° N
    bbox = f"{lat - dlat},{lon - dlon},{lat + dlat},{lon + dlon},urn:ogc:def:crs:EPSG::4326"
    resp = client.get(
        WFS,
        params={
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": "BDTOPO_V3:batiment", "OUTPUTFORMAT": "application/json",
            "SRSNAME": "EPSG:4326", "BBOX": bbox, "COUNT": 5000,
        },
    )  # fmt: skip
    resp.raise_for_status()
    return resp.json()["features"]


def load(con, buildings: list[dict], points: dict[str, tuple[float, float]]) -> None:
    con.execute(
        "create or replace table b (id varchar, usage1 varchar, usage2 varchar, g geometry)"
    )
    for f in buildings:
        con.execute(
            """insert into b select ?, ?, ?, ST_Transform(ST_Force2D(ST_GeomFromGeoJSON(?)),
               'EPSG:4326', 'EPSG:2154', always_xy := true)""",
            [
                f["properties"]["cleabs"],
                f["properties"].get("usage_1"),
                f["properties"].get("usage_2"),
                json.dumps(f["geometry"]),
            ],
        )
    con.execute("create or replace table pts (nom varchar, g geometry)")
    for name, (lon, lat) in points.items():
        con.execute(
            """insert into pts select ?, ST_Transform(ST_Point(?, ?), 'EPSG:4326', 'EPSG:2154',
               always_xy := true)""",
            [name, lon, lat],
        )


def normalize(name: str | None) -> list[str]:
    ascii_name = unicodedata.normalize("NFD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9 ]", " ", ascii_name.upper()).split()


def street_zones(con, client: httpx.Client, feat: dict) -> dict:
    """Zones traversées par la voie déclarée (tronçons BD TOPO de même nom BAN et commune)."""
    lon, lat = feat["geometry"]["coordinates"]
    street = normalize(feat["properties"].get("street") or feat["properties"]["name"])
    city = feat["properties"]["citycode"]
    d = 0.012  # ~1,3 km en latitude
    resp = client.get(
        WFS,
        params={
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": "BDTOPO_V3:troncon_de_route", "OUTPUTFORMAT": "application/json",
            "SRSNAME": "EPSG:4326", "COUNT": 5000,
            "BBOX": f"{lat - d},{lon - d * 1.4},{lat + d},{lon + d * 1.4},"
                    "urn:ogc:def:crs:EPSG::4326",
        },
    )  # fmt: skip
    resp.raise_for_status()
    segments = [
        f
        for f in resp.json()["features"]
        if any(normalize(f["properties"].get(k)) == street
               for k in ("nom_voie_ban_gauche", "nom_voie_ban_droite"))
        and city in (f["properties"].get("insee_commune_gauche"),
                     f["properties"].get("insee_commune_droite"))
    ]  # fmt: skip
    con.execute("create or replace table s (g geometry)")
    for f in segments:
        con.execute(
            """insert into s select ST_Transform(ST_Force2D(ST_GeomFromGeoJSON(?)),
               'EPSG:4326', 'EPSG:2154', always_xy := true)""",
            [json.dumps(f["geometry"])],
        )
    return {
        "troncons": len(segments),
        "longueur_m": con.execute("select round(sum(ST_Length(g))) from s").fetchone()[0],
        "zones_traversees_m": rows(
            con,
            """select z.code, round(sum(ST_Length(ST_Intersection(s.g, z.geom)))) longueur_m
               from s join z on ST_Intersects(s.g, z.geom) group by 1 order by 2 desc""",
        ),
    }


def proposed_status(out: dict) -> str:
    """Statut selon les règles du 2026-10-28 (rapport, Test 2).

    Adresse avec numéro : réussi si la zone de la jointure est l'une des zones du bâtiment
    au point BAN (règle 1 : bâtiment à cheval → réussi), échec sinon.
    Adresse sans numéro : réussi si la voie déclarée ne traverse que la zone de la jointure ;
    indéterminable si elle la traverse parmi d'autres (règle 2) ; échec sinon.
    """
    zone = out["zone_jointure"]
    if out["ban_type"] == "housenumber":
        ban_ids = {b["id"] for b in out["batiment_sous_ou_pres_du_point"] if b["nom"] == "ban"}
        zones = {
            z.split(" ")[0]
            for b in out["zones_de_ces_batiments"]
            if b["id"] in ban_ids
            for z in b["zones"]
        }
        if not zones:
            return "indeterminable (aucun bâtiment à moins de 30 m du point BAN)"
        return "reussi" if zone in zones else "echec"
    crossed = {z["code"] for z in out.get("voie_declaree", {}).get("zones_traversees_m", [])}
    if crossed == {zone}:
        return "reussi (voie entièrement dans la zone)"
    return "indeterminable (règle 2)" if zone in crossed else "echec (règle 2)"


def rows(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def building_zones(con, where: str) -> list[dict]:
    """Part de surface de chaque bâtiment par zone."""
    return rows(
        con,
        f"""with sel as (select * from b where {where})
            select sel.id, sel.usage1, sel.usage2, round(ST_Area(sel.g)) aire_m2,
                   list(z.code || ' ' || round(100 * ST_Area(ST_Intersection(sel.g, z.geom))
                        / ST_Area(sel.g)) || ' %'
                        order by ST_Area(ST_Intersection(sel.g, z.geom)) desc) zones
            from sel join z on ST_Intersects(sel.g, z.geom)
            group by all order by aire_m2 desc""",
    )


def verify(con, client: httpx.Client, row: dict) -> dict:
    main = point_from_link(row["lien_gpu_principal"])
    stock = point_from_link(row["lien_gpu_stock"])
    query = f"{row['adresse_voie']} {row['code_postal']} {row['commune']}"
    ban = client.get(GEOCODE, params={"q": query, "postcode": row["code_postal"], "limit": 1})
    ban.raise_for_status()
    feat = ban.json()["features"][0]
    ban_pt = tuple(feat["geometry"]["coordinates"])
    points = {"ban": ban_pt, "principal": main} | ({"stock": stock} if stock else {})
    buildings = {}
    for lon, lat in points.values():
        for f in buildings_around(client, lon, lat, RADIUS_M):
            buildings[f["properties"]["cleabs"]] = f
    load(con, list(buildings.values()), points)
    out: dict = {
        "num": row["num"],
        "zone_jointure": row["zone_principale"],
        "ban_type": feat["properties"]["type"],
    }
    out["distances_entre_points_m"] = rows(
        con,
        """select a.nom || '-' || b.nom paire, round(ST_Distance(a.g, b.g)) m
           from pts a, pts b where a.nom < b.nom""",
    )
    out["zone_sous_chaque_point"] = rows(
        con,
        """select p.nom, list(z.code) zones
           from pts p left join z on ST_Contains(z.geom, p.g) group by 1""",
    )
    # Bâtiment sous chaque point, sinon le plus proche (≤ 30 m)
    out["batiment_sous_ou_pres_du_point"] = rows(
        con,
        """select p.nom, b.id, b.usage1, b.usage2, round(ST_Distance(p.g, b.g), 1) dist_m
           from pts p, b
           where ST_Distance(p.g, b.g) = (select min(ST_Distance(p.g, b2.g)) from b b2)
             and ST_Distance(p.g, b.g) <= 30""",
    )
    ids = ",".join(f"'{r['id']}'" for r in out["batiment_sous_ou_pres_du_point"]) or "''"
    out["zones_de_ces_batiments"] = building_zones(con, f"id in ({ids})")
    # Bâtiments d'activité (usage non uniquement résidentiel) dans 150 m du point BAN
    out["batiments_activite_150m_ban"] = building_zones(
        con,
        """coalesce(usage1, '') not in ('Résidentiel', 'Annexe', 'Indifférencié', '')
           and ST_DWithin(g, (select g from pts where nom = 'ban'), 150)""",
    )
    if feat["properties"]["type"] != "housenumber":
        out["voie_declaree"] = street_zones(con, client, feat)
    out["statut_propose"] = proposed_status(out)
    out["zones_a_moins_de_150m"] = {
        nom: rows(
            con,
            f"""select z.code, round(min(ST_Distance(z.geom, p.g))) dist_m from z, pts p
                where p.nom = '{nom}' and ST_DWithin(z.geom, p.g, 150) group by 1 order by 2""",
        )
        for nom in points
    }
    return out


@app.command()
def main(nums: Annotated[list[str], typer.Argument(help="Numéros de contrôle")]) -> None:
    """Vérifie les contrôles donnés par les bâtiments BD TOPO et le zonage."""
    con = duckdb.connect()
    con.load_extension("spatial")
    con.execute(
        f"""create table z as select coalesce(zonage, zone) code, geom
            from ST_Read('{ZONAGE}')"""
    )
    by_num = {r["num"]: r for r in csv.DictReader((OUTPUT_DIR / "controles.csv").open())}
    results = []
    with httpx.Client(timeout=90) as client:
        for num in nums:
            results.append(verify(con, client, by_num[num]))
    out = OUTPUT_DIR / "verif_batiments.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n")
    typer.echo(json.dumps(results, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    app()
