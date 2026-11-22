"""Base DuckDB réduite, au schéma de la base locale, pour la composante structurée."""

from pathlib import Path

import duckdb
import pytest

from traboule.chaine.sql import connect


def square(x0: float, y0: float, x1: float, y1: float) -> str:
    return f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0}))"


# siret, état, diffusion, commune COG 2026, arrondissement, code du stock, NAF, position publique
ETABLISSEMENTS = [
    ("00000000000001", "A", "O", "69259", None, "69259", "47.11B", True),
    ("00000000000002", "A", "O", "69259", None, "69259", "52.10B", True),
    ("00000000000003", "A", "P", "69259", None, "69259", "47.11B", False),
    ("00000000000004", "A", "O", "69259", None, "69259", "10.71C", False),  # sans coordonnées
    ("00000000000005", "F", "O", "69259", None, "69259", "47.11B", True),
    ("00000000000006", "A", "O", "69149", None, "69152", "25.62B", True),  # ancien code
    ("00000000000007", "A", "O", "69149", None, "69149", "25.62B", True),
    ("00000000000008", "A", "O", "69123", "69387", "69387", "28.11Z", True),
    ("00000000000009", "A", "P", "69123", "69387", "69387", "28.11Z", False),
]
# siret, état, diffusion, commune, arrondissement, zone, confiance (statuts P exclus)
ZONES = [
    ("00000000000001", "A", "O", "69259", None, "UEi1", "haute"),
    ("00000000000002", "A", "O", "69259", None, "UEi1", "faible"),
    ("00000000000005", "F", "O", "69259", None, "UEi1", "haute"),
    ("00000000000006", "A", "O", "69149", None, "UEi2", "moyenne"),
    ("00000000000007", "A", "O", "69149", None, "UCe3a", "haute"),
    ("00000000000008", "A", "O", "69123", "69387", "UEi2", "haute"),
]


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "traboule.duckdb"
    con = duckdb.connect(str(path))
    con.load_extension("spatial")
    con.execute("""create table etablissements (siret varchar, etatAdministratifEtablissement
        varchar, statutDiffusionEtablissement varchar, code_commune_cog2026 varchar,
        code_arrondissement varchar, codeCommuneEtablissement varchar,
        activitePrincipaleEtablissement varchar, position_publique boolean)""")
    con.executemany("insert into etablissements values (?, ?, ?, ?, ?, ?, ?, ?)", ETABLISSEMENTS)
    con.execute("""create table etablissements_zones (siret varchar, etat varchar,
        diffusion varchar, code_commune_cog2026 varchar, code_arrondissement varchar,
        zone varchar, confiance varchar)""")
    con.executemany("insert into etablissements_zones values (?, ?, ?, ?, ?, ?, ?)", ZONES)
    con.execute("create table zonage (code varchar, geom geometry)")
    con.execute("create table unites (code varchar, niveau varchar, geom geometry)")
    for code, box in [("UEi1", (0, 0, 100, 100)), ("UEi2", (100, 0, 200, 100))]:
        con.execute("insert into zonage values (?, ST_GeomFromText(?))", [code, square(*box)])
    for code, niveau, box in [
        ("69259", "commune", (0, 0, 150, 100)),  # intersecte UEi1 et UEi2
        ("69149", "commune", (150, 0, 300, 100)),  # intersecte UEi2
        ("69387", "arrondissement_municipal", (0, 100, 100, 200)),  # contact de bordure
    ]:
        con.execute(
            "insert into unites values (?, ?, ST_GeomFromText(?))", [code, niveau, square(*box)]
        )
    con.execute("create table communes (code_commune varchar, libelle varchar)")
    con.executemany(
        "insert into communes values (?, ?)",
        [("69259", "Vénissieux"), ("69149", "Oullins-Pierre-Bénite"), ("69123", "Lyon")],
    )
    con.execute("create table arrondissements (code_arrondissement varchar, libelle varchar)")
    con.execute("insert into arrondissements values ('69387', 'Lyon 7e Arrondissement')")
    con.execute("""create table zones_reglement (code_zone varchar, methode varchar,
        chapitre varchar, zone_u_reference varchar, chapitre_u varchar,
        abstention_motif varchar, version_piece varchar)""")
    version = "MODIFICATION N° 4 – APPROBATION 2024"
    con.executemany(
        "insert into zones_reglement values (?, ?, ?, ?, ?, ?, ?)",
        [
            ("UEi1", "exact", "Zone UEi1", None, None, None, version),
            ("UEi2", "exact", "Zone UEi2", None, None, None, version),
            ("UCe3a", "suffixe", "Zone UCe3", None, None, None, version),
        ],
    )
    con.execute("create table _catalogue (nom varchar, millesime varchar, sources varchar[])")
    con.executemany(
        "insert into _catalogue values (?, ?, ?)",
        [
            (
                "etablissements",
                "stock Sirene du 2026-10-01 ; géolocalisation d'octobre 2026",
                ["SRC-001a", "SRC-001b"],
            ),
            (
                "etablissements_zones",
                "stock Sirene du 2026-10-01 × zonage du 2026-10-28",
                ["SRC-001a", "SRC-002"],
            ),
            ("zonage", "zonage du 2026-10-28", ["SRC-002"]),
            ("unites", "communes 2024 ; arrondissements 2026-11-01", ["REF-COMMUNES-ML-2024"]),
        ],
    )
    con.close()
    return path


@pytest.fixture
def con(database: Path) -> duckdb.DuckDBPyConnection:
    con = connect(database)
    yield con
    con.close()
