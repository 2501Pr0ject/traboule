"""Composante structurée : garde-fous SQL et gabarits (conventions §3, §5)."""

from datetime import date

import duckdb
import pytest

from traboule.chaine.sql import (
    DATABASE,
    SqlGuardError,
    StructuredComponent,
    check_query,
    connect,
    load_lexicon,
    query,
)
from traboule.routing.analyse import analyse
from traboule.routing.routeur import route


@pytest.mark.parametrize(
    "sql",
    [
        "select count(*) from etablissements",  # table hors liste blanche
        "select siret from v_etablissements_zones",  # colonne interdite
        "select count(*) from read_parquet('data/interim/sirene_ml.parquet')",
        "select 1; select 2",
        "insert into v_communes values ('1', 'x')",
        "with e as (select * from etablissements) select count(*) from e",
    ],
)
def test_guard_refuses(con, sql):
    with pytest.raises(SqlGuardError):
        check_query(con, sql)


def test_guard_accepts_whitelisted_views_and_ctes(con):
    sql = "with a as (select zone from v_etablissements_zones) select count(*) as n from a"
    assert query(con, sql) == [{"n": 6}]


def test_connection_is_read_only_without_file_access(con):
    with pytest.raises(duckdb.Error):
        con.execute("create table t (x int)")
    with pytest.raises(duckdb.PermissionException):
        con.execute("select * from read_csv('/etc/hosts')")


@pytest.fixture
def lexicon(con):
    return load_lexicon(con)


def build(con, lexicon, question):
    analysis = analyse(question, lexicon)
    return StructuredComponent(con, lexicon).build(analysis, route(analysis, lexicon))


def test_lexicon_reads_versions_from_the_base(lexicon):
    assert lexicon.stock_date == date(2026, 10, 1) and lexicon.reglement_year == 2024
    assert lexicon.zonage_codes("UCe3") == ["UCe3a"]


def test_count_by_commune_reports_former_codes(con, lexicon):
    (c,) = build(con, lexicon, "Combien d'établissements actifs à Oullins-Pierre-Bénite ?")
    assert c.valeur == 2
    assert "Dont 1 sous le code 69152" in c.texte
    assert c.sources[0].sources == ["SRC-001a", "SRC-001b"] and "v_etablissements" in c.requete


def test_arrondissement_is_counted_alone(con, lexicon):
    (c,) = build(con, lexicon, "Combien d'établissements actifs dans le 7e arrondissement ?")
    assert c.valeur == 2 and "7e arrondissement de Lyon (69387)" in c.texte


def test_share_of_partial_diffusion(con, lexicon):
    (c,) = build(con, lexicon, "Quelle part des établissements actifs est en diffusion partielle ?")
    assert c.valeur == 25.0  # 2 statuts P sur 8 actifs
    assert "2 sur 8" in c.texte


def test_zone_count_with_breakdown_and_lower_bound_by_commune(con, lexicon):
    (c,) = build(con, lexicon, "Combien d'établissements actifs en zone UEi1 à Vénissieux ?")
    assert c.valeur == 2 and c.comptage_spatial
    assert (c.ventilation_confiance.haute, c.ventilation_confiance.faible) == (1, 1)
    assert c.minorant.n == 2  # un statut P et un établissement sans coordonnées
    assert "Analyse de localisation" in c.limites[0]


def test_zone_lower_bound_by_intersecting_units(con, lexicon):
    (c,) = build(con, lexicon, "Combien d'établissements actifs en zone UEi2 ?")
    assert c.valeur == 2
    # Vénissieux et Oullins-Pierre-Bénite intersectent UEi2 ; le 7e ne la touche pas.
    assert c.minorant.n == 2 and "2 communes ou arrondissements" in c.minorant.perimetre


def test_activity_filter(con, lexicon):
    (c,) = build(con, lexicon, "Combien d'établissements d'entreposage (52.10) en zone UEi1 ?")
    assert c.valeur == 1


def test_distribution_by_zone(con, lexicon):
    (c,) = build(
        con,
        lexicon,
        "Comment se répartissent les établissements actifs de "
        "Oullins-Pierre-Bénite entre les zones ?",
    )
    assert c.valeur == [
        {"zone": "UCe3a", "n": 1, "faible": 0},
        {"zone": "UEi2", "n": 1, "faible": 0},
    ]
    assert c.ventilation_confiance.total == 2 and c.minorant.n == 0


def test_abstention_is_carried_without_query(con, lexicon):
    (c,) = build(con, lexicon, "Combien d'établissements actifs à Lyon au 1er janvier 2012 ?")
    assert c.abstention and c.motif == "hors_version" and c.requete is None


def test_no_result_exposes_an_individual_row(con, lexicon):
    questions = [
        "Combien d'établissements actifs à Vénissieux ?",
        "Combien d'établissements actifs en zone UEi1 à Vénissieux ?",
        "Comment se répartissent les établissements actifs de Vénissieux entre les zones ?",
    ]
    for question in questions:
        for c in build(con, lexicon, question):
            assert "siret" not in c.requete.lower()
            assert "00000000000003" not in str(c.model_dump())


@pytest.mark.skipif(not DATABASE.exists(), reason="base locale absente")
def test_demo_values_on_the_local_base():
    con = connect()
    lexicon = load_lexicon(con)
    (c,) = build(
        con,
        lexicon,
        "Combien d'établissements actifs relevant de la section C (NAF "
        "rév. 2) sont recensés dans le 7e arrondissement de Lyon ?",
    )
    assert c.valeur == 510
    (c,) = build(
        con, lexicon, "Combien d'établissements actifs sont situés en zone UEi1 à Vénissieux ?"
    )
    assert (c.valeur, c.minorant.n) == (1479, 2211)
    con.close()
