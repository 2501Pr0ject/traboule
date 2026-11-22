"""Lexique réduit pour les tests de l'analyse et du routeur."""

from datetime import date

import pytest

from traboule.routing.analyse import Place, build_lexicon

ZONE_ROWS = [
    {"code_zone": "UEi1", "methode": "exact", "chapitre": "Zone UEi1"},
    {"code_zone": "UEi2", "methode": "exact", "chapitre": "Zone UEi2"},
    {"code_zone": "UEp", "methode": "exact", "chapitre": "Zone UEp"},
    {"code_zone": "UCe3a", "methode": "suffixe", "chapitre": "Zone UCe3"},
    {"code_zone": "UCe3-p", "methode": "libelong_gpu", "chapitre": "Zone UCe3"},
    {"code_zone": "UPr3", "methode": "exact", "chapitre": "Zone UPr3"},
    {"code_zone": "UPr3c", "methode": "suffixe", "chapitre": "Zone UPr3"},
    {
        "code_zone": "AUEi1",
        "methode": "au_reference",
        "chapitre": "Zone AUs.co",
        "zone_u_reference": "UEi1",
        "chapitre_u": "Zone UEi1",
    },
    {"code_zone": "A2s", "methode": "stecal", "abstention_motif": "document_non_ingere"},
    {"code_zone": "SECTSAUV", "methode": "autre_document", "abstention_motif": "autre_document"},
]
PLACES = [
    Place("69123", "commune", "Lyon"),
    Place("69259", "commune", "Vénissieux"),
    Place("69149", "commune", "Oullins-Pierre-Bénite"),
    Place("69199", "commune", "Saint-Fons"),
    Place("69202", "commune", "Sainte-Foy-lès-Lyon"),
    Place("69266", "commune", "Villeurbanne"),
    Place("69387", "arrondissement_municipal", "Lyon 7e Arrondissement"),
    Place("69381", "arrondissement_municipal", "Lyon 1er Arrondissement"),
]


@pytest.fixture
def lexicon():
    return build_lexicon(ZONE_ROWS, PLACES, date(2026, 10, 1), 2024)
