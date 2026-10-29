"""Contrats Etablissement et ZoneAssignment (conventions §3, règles 5, 7, 10 ; ADR-0006)."""

import pytest
from pydantic import ValidationError

from traboule.contracts import Etablissement, ZoneAssignment

SIRET = "00000000000018"  # fictif


def etab(**kw) -> Etablissement:
    base = {"siret": SIRET, "etat": "A", "diffusion": "O", "code_commune_cog2026": "69259"}
    return Etablissement(**(base | kw))


def test_position_publique_requires_coordinates_and_status_o():
    assert etab(x=1.0, y=2.0).position_publique
    assert not etab().position_publique


def test_status_p_has_no_public_position_even_with_coordinates():
    # Règle 10 : le statut P du stock prévaut sur les coordonnées de la géolocalisation.
    assert not etab(diffusion="P", x=1.0, y=2.0).position_publique


def test_arrondissement_only_under_lyon():
    assert etab(code_commune_cog2026="69123", code_arrondissement="69387").code_arrondissement
    with pytest.raises(ValidationError, match="69123"):
        etab(code_arrondissement="69387")


def test_lyon_commune_code_is_not_an_arrondissement():
    with pytest.raises(ValidationError):
        etab(code_commune_cog2026="69123", code_arrondissement="69123")


def test_coordinates_come_in_pairs():
    with pytest.raises(ValidationError, match="ensemble"):
        etab(x=1.0)


@pytest.mark.parametrize("field,value", [("siret", "123"), ("qualite_xy", "99"), ("etat", "X")])
def test_invalid_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        etab(**{field: value})


def test_assignment_zone_matches_category():
    ok = ZoneAssignment(siret=SIRET, categorie="une_zone", zone="UEi2", confiance="haute")
    assert ok.zone == "UEi2"
    with pytest.raises(ValidationError):
        ZoneAssignment(siret=SIRET, categorie="multi_zones", zone="UEi2", confiance=None)
    with pytest.raises(ValidationError):
        ZoneAssignment(siret=SIRET, categorie="une_zone", zone=None, confiance=None)


def test_no_confidence_without_zone():
    with pytest.raises(ValidationError, match="confiance"):
        ZoneAssignment(siret=SIRET, categorie="aucune_zone", zone=None, confiance="faible")
