"""Référentiel géographique (conventions §3, règles 4 à 6), sur des tables synthétiques."""

import duckdb
import pytest

from traboule.geo.referentiel import ReferentielError, Territory, build

TERRITORY = Territory(epci="E", lyon="69123", communes_count=3, arrondissements=("69381", "69387"))


def table(con, name: str, cols: str, rows: list[tuple]) -> None:
    values = ", ".join(str(r) for r in rows)
    con.execute(f"create or replace table {name} as select * from (values {values}) t({cols})")


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    table(con, "cog", "TYPECOM, COM, LIBELLE, COMPARENT", [
        ("COM", "69123", "Lyon", ""),
        ("COM", "69149", "Oullins-Pierre-Bénite", ""),
        ("COM", "69259", "Vénissieux", ""),
        ("COM", "99999", "Vénissieux", ""),  # même libellé, autre code, hors EPCI
        ("ARM", "69381", "Lyon 1er Arrondissement", "69123"),
        ("ARM", "69387", "Lyon 7e Arrondissement", "69123"),
    ])  # fmt: skip
    table(con, "mvt", "TYPECOM_AV, COM_AV, TYPECOM_AP, COM_AP, DATE_EFF, MOD", [
        ("COM", "69152", "COM", "69149", "2024-01-01", "32"),
        ("COM", "69149", "COM", "69149", "2024-01-01", "32"),
    ])  # fmt: skip
    table(con, "appart_com", "CODGEO, EPCI", [
        ("69123", "E"), ("69149", "E"), ("69259", "E"), ("99999", "X"),
    ])  # fmt: skip
    table(
        con, "appart_arm", "CODGEO, COM, EPCI", [("69381", "69123", "E"), ("69387", "69123", "E")]
    )
    table(con, "passage_src", "CODGEO_INI, CODGEO_2026", [
        ("69123", "69123"), ("69149", "69149"), ("69152", "69149"),
        ("69259", "69259"), ("99999", "99999"),
    ])  # fmt: skip
    return con


def rows(con, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def test_build_reference_tables(con):
    result = build(con, TERRITORY)
    assert result["communes"] == 3
    assert result["arrondissements"] == 2


def test_codes_not_labels_are_join_keys(con):
    # Règle 4 : un homonyme hors EPCI n'est pas rapproché.
    build(con, TERRITORY)
    assert rows(con, "select code_commune from ref_communes_ml where libelle = 'Vénissieux'") == [
        ("69259",)
    ]


def test_arrondissements_are_not_communes(con):
    # Règle 5 : les arrondissements sont des subdivisions de Lyon, jamais additionnés aux communes.
    build(con, TERRITORY)
    assert not rows(con, "select * from ref_communes_ml where code_commune like '6938%'")
    assert rows(
        con,
        """select code_cog_2026, code_arrondissement_2026, niveau_source from passage_communes
           where code_source = '69387'""",
    ) == [("69123", "69387", "arrondissement_municipal")]


def test_historical_code_maps_to_cog_2026_with_effect_date(con):
    # Règle 6 : 69152 (Pierre-Bénite) → 69149 au 1er janvier 2024.
    historical = build(con, TERRITORY)["codes_historiques"]
    assert historical == [
        {"code_source": "69152", "code_cog_2026": "69149", "date_effet": "2024-01-01",
         "type_mouvement": "32"}
    ]  # fmt: skip


def test_ambiguous_source_code_fails(con):
    con.execute("insert into passage_src values ('69152', '69259')")
    with pytest.raises(ReferentielError, match="ambigu"):
        build(con, TERRITORY)


def test_historical_code_without_effect_date_fails(con):
    con.execute("delete from mvt where COM_AV = '69152'")
    with pytest.raises(ReferentielError, match="date d'effet"):
        build(con, TERRITORY)


def test_unexpected_commune_count_fails(con):
    with pytest.raises(ReferentielError, match="communes"):
        build(con, Territory("E", "69123", 58, ("69381", "69387")))


def test_unexpected_arrondissements_fail(con):
    with pytest.raises(ReferentielError, match="arrondissements"):
        build(con, Territory("E", "69123", 3, ("69381",)))
