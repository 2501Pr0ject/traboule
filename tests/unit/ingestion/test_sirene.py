"""Filtrage Sirene (conventions §3, règles 5, 6, 10 ; epsg 2154), sur des Parquet synthétiques.

SIRET fictifs : aucune donnée Sirene réelle (règle 9).
"""

import duckdb
import pytest

from traboule.ingestion.sirene import SireneError, build_sirene_ml

STOCK_COLS = (
    "siret, siren, nic, etablissementSiege, statutDiffusionEtablissement, "
    "etatAdministratifEtablissement, dateCreationEtablissement, dateDebut, "
    "dateDernierTraitementEtablissement, activitePrincipaleEtablissement, "
    "nomenclatureActivitePrincipaleEtablissement, activitePrincipaleNAF25Etablissement, "
    "trancheEffectifsEtablissement, caractereEmployeurEtablissement, codeCommuneEtablissement, "
    "coordonneeLambertAbscisseEtablissement, coordonneeLambertOrdonneeEtablissement"
)


def stock_row(siret: str, commune: str, diffusion: str = "O", x: str = "842395") -> str:
    return (
        f"('{siret}', '{siret[:9]}', '{siret[9:]}', true, '{diffusion}', 'A', null, null, null, "
        f"'25.11Z', 'NAFRev2', null, null, null, '{commune}', '{x}', '6519229')"
    )


@pytest.fixture
def files(tmp_path):
    con = duckdb.connect()
    stock = tmp_path / "stock.parquet"
    geoloc = tmp_path / "geoloc.parquet"
    rows = [
        stock_row("00000000100001", "69387"),  # arrondissement de Lyon
        stock_row("00000000200001", "69152"),  # code historique de Pierre-Bénite
        stock_row("00000000300001", "69259", diffusion="P", x="[ND]"),  # P géolocalisé
        stock_row("00000000400001", "69259"),  # géolocalisé en CRS d'outre-mer
        stock_row("00000000500001", "75056"),  # hors Métropole
    ]
    con.execute(
        f"copy (select * from (values {', '.join(rows)}) t({STOCK_COLS})) "
        f"to '{stock}' (format parquet)"
    )
    con.execute(f"""copy (select * from (values
        ('00000000100001', 842395.0, 6519229.0, '11', '69387', null, 1.0, '2154'),
        ('00000000200001', 840000.0, 6512000.0, '11', '69152', null, 1.0, '2154'),
        ('00000000300001', 845000.0, 6512000.0, '11', '69259', null, 1.0, '2154'),
        ('00000000400001', 1.0, 2.0, '11', '69259', null, 1.0, '5490'),
        ('00000000500001', 650000.0, 6860000.0, '11', '75056', null, 1.0, '2154')
    ) t(siret, x, y, qualite_xy, plg_code_commune, plg_iris, distance_precision, epsg))
    to '{geoloc}' (format parquet)""")
    return stock, geoloc


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("""create table passage_communes as select * from (values
        ('69387', '69123', '69387'), ('69149', '69149', null), ('69152', '69149', null),
        ('69259', '69259', null)
    ) t(code_source, code_cog_2026, code_arrondissement_2026)""")
    return con


def build(con, files, tmp_path) -> tuple[dict, dict[str, dict]]:
    out = tmp_path / "sirene_ml.parquet"
    result = build_sirene_ml(con, *files, out)
    cur = con.execute(f"select * from read_parquet('{out}')")
    cols = [d[0] for d in cur.description]
    return result, {r[0]: dict(zip(cols, r, strict=True)) for r in cur.fetchall()}


def test_only_metropole_establishments_are_kept(con, files, tmp_path):
    _, rows = build(con, files, tmp_path)
    assert "00000000500001" not in rows
    assert len(rows) == 4


def test_arrondissement_keeps_commune_and_arrondissement(con, files, tmp_path):
    # Règle 5 : Lyon 69123 et son arrondissement, sans confusion.
    _, rows = build(con, files, tmp_path)
    r = rows["00000000100001"]
    assert (r["code_commune_cog2026"], r["code_arrondissement"]) == ("69123", "69387")


def test_historical_code_is_mapped_to_cog_2026(con, files, tmp_path):
    # Règle 6 : 69152 → 69149.
    _, rows = build(con, files, tmp_path)
    assert rows["00000000200001"]["code_commune_cog2026"] == "69149"
    assert rows["00000000200001"]["codeCommuneEtablissement"] == "69152"


def test_status_p_has_no_position_even_if_geolocated(con, files, tmp_path):
    # Règle 10 : le statut P du stock prévaut ; le fait brut reste dans geoloc_present.
    result, rows = build(con, files, tmp_path)
    r = rows["00000000300001"]
    assert r["geoloc_present"] and not r["position_publique"]
    assert r["x"] is None and r["y"] is None and r["qualite_xy"] is None
    assert r["coordonneeLambertAbscisseEtablissement"] is None
    assert result["statut_p_presents_dans_geolocalisation"] == 1


def test_non_lambert93_geolocation_is_dropped(con, files, tmp_path):
    _, rows = build(con, files, tmp_path)
    r = rows["00000000400001"]
    assert not r["geoloc_present"] and r["x"] is None


def test_public_position_count(con, files, tmp_path):
    result, _ = build(con, files, tmp_path)
    assert result["position_publique"] == 2


def test_unexpected_diffusion_status_fails_without_output(con, files, tmp_path):
    stock, geoloc = files
    duckdb.execute(
        "copy (select * replace ('X' as statutDiffusionEtablissement) "
        f"from read_parquet('{stock}')) to '{tmp_path / 'bad.parquet'}' (format parquet)"
    )
    out = tmp_path / "sirene_ml.parquet"
    with pytest.raises(SireneError, match="statut"):
        build_sirene_ml(con, tmp_path / "bad.parquet", geoloc, out)
    assert not out.exists() and not list(tmp_path.glob("*.partial"))
