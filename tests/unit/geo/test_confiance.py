"""Indice de confiance de zone (ADR-0006) : une branche par cas, Python et SQL concordants."""

import duckdb
import pytest

from traboule.geo.confiance import confiance, confiance_sql

# (qualite_xy, dist_autre_zone_m, stock_present, zone_stock, attendu) pour zone = "UEi2"
CASES = [
    ("11", 30.0, True, "UEi2", "haute"),  # qualité 11, ≥ 25 m, même zone
    ("11", None, True, "UEi2", "haute"),  # aucune autre zone dans le rayon
    ("11", 25.0, True, "UEi2", "haute"),  # seuil de 25 m inclus
    ("11", 24.9, True, "UEi2", "moyenne"),  # entre 10 et 25 m
    ("11", 10.0, True, "UEi2", "moyenne"),  # seuil de 10 m : pas faible
    ("11", 9.9, True, "UEi2", "faible"),  # < 10 m
    ("21", 30.0, True, "UEi2", "moyenne"),  # qualité 21 : moyenne au mieux
    ("11", 30.0, False, None, "moyenne"),  # stock absent : moyenne au mieux
    ("21", 30.0, False, None, "moyenne"),
    ("12", 30.0, True, "UEi2", "faible"),  # position aléatoire dans la voie
    ("22", 30.0, True, "UEi2", "faible"),
    ("33", 30.0, True, "UEi2", "faible"),  # position aléatoire dans la commune
    (None, 30.0, True, "UEi2", "faible"),  # qualité inconnue
    ("11", 30.0, True, "UEi1", "faible"),  # zones différentes selon la source
    ("11", 30.0, True, None, "faible"),  # point du stock hors zone ou multi-zones
    ("21", 5.0, False, None, "faible"),  # la condition faible prime
]


@pytest.mark.parametrize("q,d,stock,zone_stock,expected", CASES)
def test_python_rule(q, d, stock, zone_stock, expected):
    got = confiance(
        zone="UEi2", qualite_xy=q, dist_autre_zone_m=d, stock_present=stock, zone_stock=zone_stock
    )
    assert got == expected


def test_no_zone_has_no_confidence():
    assert (
        confiance(
            zone=None, qualite_xy="11", dist_autre_zone_m=30.0, stock_present=True, zone_stock=None
        )
        is None
    )


def test_sql_matches_python_on_every_case():
    con = duckdb.connect()
    rows = [("UEi2", *c[:4]) for c in CASES] + [(None, "11", 30.0, True, None)]
    con.execute(
        "create table t (zone varchar, qualite_xy varchar, dist_autre_zone_m double, "
        "stock_present boolean, zone_stock varchar)"
    )
    con.executemany("insert into t values (?, ?, ?, ?, ?)", rows)
    got = con.execute(f"select {confiance_sql()} from t").fetchall()
    expected = [
        confiance(zone=z, qualite_xy=q, dist_autre_zone_m=d, stock_present=s, zone_stock=zs)
        for z, q, d, s, zs in rows
    ]
    assert [g[0] for g in got] == expected
