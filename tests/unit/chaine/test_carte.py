"""Carte de la réponse : reprojection, carroyage agrégé, aucune donnée individuelle."""

import duckdb
import pytest
from base_chaine import make_database

from traboule.chaine.carte import OFFLINE, build_map, grid_layer, guard, needs_map, wgs84
from traboule.chaine.sql import StructuredComponent, connect, load_lexicon
from traboule.contracts.reponse import Composante, MotifAbstention, Reponse
from traboule.routing.analyse import analyse
from traboule.routing.routeur import route

# Six établissements dans un carreau de 200 m, deux dans un autre, un statut P géolocalisé.
CLUSTER = [(f"1000000000000{i}", 842210.0 + 10 * i, 6519230.0) for i in range(6)]
SPARSE = [("20000000000001", 842615.0, 6519640.0), ("20000000000002", 842625.0, 6519640.0)]
MASKED = ("30000000000001", 842230.0, 6519240.0)
ETABLISSEMENTS = [
    *[(s, "A", "O", "69259", None, "69259", "47.11B", True, x, y) for s, x, y in CLUSTER + SPARSE],
    (MASKED[0], "A", "P", "69259", None, "69259", "47.11B", False, MASKED[1], MASKED[2]),
]
ZONES = [(s, "A", "O", "69259", None, "UEi1", "haute") for s, _, _ in CLUSTER + SPARSE]
ZONAGE = [
    ("UEi1", (842000, 6519000, 843000, 6520000)),
    ("UEi2", (843000, 6519000, 844000, 6520000)),
]
UNITES = [("69259", "commune", (841500, 6518500, 844500, 6520500))]


@pytest.fixture
def con(tmp_path):
    path = make_database(tmp_path / "carte.duckdb", ETABLISSEMENTS, ZONES, ZONAGE, UNITES)
    con = connect(path)
    yield con
    con.close()


def answer(con, question):
    lexicon = load_lexicon(con)
    analysis = analyse(question, lexicon)
    decision = route(analysis, lexicon)
    components = StructuredComponent(con, lexicon).build(analysis, decision)
    return lexicon, analysis, Reponse(route=decision.route, composantes=components)


def test_bellecour_is_reprojected_with_x_y_order():
    con = duckdb.connect()
    con.load_extension("spatial")
    lon, lat = con.execute(
        f"select ST_X(g), ST_Y(g) from (select {wgs84('ST_Point(842395.13, 6519229.36)')} as g)"
    ).fetchone()
    assert lon == pytest.approx(4.8320, abs=1e-4) and lat == pytest.approx(45.7578, abs=1e-4)


def test_grid_shows_no_cell_under_the_threshold(con):
    _, analysis, _ = answer(con, "Combien d'établissements actifs en zone UEi1 à Vénissieux ?")
    layer, shown, hidden = grid_layer(con, analysis, ["UEi1"])
    assert [f["properties"]["n"] for f in layer.features] == [6]
    assert (shown, hidden) == (6, 2)  # le statut P n'est compté nulle part


def test_map_html_has_no_establishment_coordinates_nor_siret(con):
    lexicon, analysis, reponse = answer(
        con, "Combien d'établissements actifs en zone UEi1 à Vénissieux ?"
    )
    carte = build_map(con, lexicon, analysis, reponse, {"UEi1": "Zone activites artisanales"})
    page = carte["html"]
    points = duckdb.connect()
    points.load_extension("spatial")
    for siret, x, y in [*CLUSTER, *SPARSE, MASKED]:
        assert siret not in page
        assert str(int(x)) not in page and str(int(y)) not in page
        lon, lat = points.execute(
            f"select ST_X(g), ST_Y(g) from (select {wgs84(f'ST_Point({x}, {y})')} as g)"
        ).fetchone()
        assert f"{lon:.6f}" not in page and f"{lat:.6f}" not in page
    assert (
        "OpenStreetMap" in page
        and "Zone activites artisanales" in page
        and "Zone UEi1, p. 611" in page
    )
    assert "Confiance de zone</strong> : 8 haute, 0 moyenne, 0 faible" in page
    assert "carreaux de moins de 5 masqués (2 établissements)" in page
    assert carte["minorant"] == (
        "8 établissements sont géolocalisés dans la zone. 1 établissement actif de Vénissieux "
        "(69259) n'a pas de position publique et ne peut pas être placé : il pourrait se trouver "
        "dans la zone."
    )


def test_no_map_without_a_zone(con):
    lexicon, analysis, reponse = answer(con, "Combien d'établissements actifs à Vénissieux ?")
    assert not needs_map(reponse, analysis)
    assert build_map(con, lexicon, analysis, reponse, {}) is None
    abstained = Reponse(
        route="ABSTAIN",
        composantes=[
            Composante(type="documentaire", abstention=True, motif=MotifAbstention.ZONE_INEXISTANTE)
        ],
    )
    assert (
        build_map(con, lexicon, analyse("Que prévoit la zone UEi1 ?", lexicon), abstained, {})
        is None
    )


def test_documentary_answer_on_a_zone_draws_the_zone_without_grid(con):
    lexicon = load_lexicon(con)
    analysis = analyse("Quelle est la hauteur maximale en zone UEi1 ?", lexicon)
    reponse = Reponse(
        route="RAG",
        composantes=[
            Composante(
                type="documentaire", abstention=True, motif=MotifAbstention.PREUVE_INSUFFISANTE
            )
        ],
    )
    carte = build_map(con, lexicon, analysis, reponse, {})
    assert carte is not None and carte["minorant"] is None
    assert "Établissements par carreau" not in carte["html"]


def test_offline_guard_wraps_the_map_script():
    page = guard('<html><body><script>\nvar map_1 = L.map("map_1");\n</script></body></html>')
    assert "if (window.L) {" in page and OFFLINE in page
    assert page.index("if (window.L)") < page.index("L.map(")
