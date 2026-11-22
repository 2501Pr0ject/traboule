"""Contrat Reponse en composantes (conventions §6 ; ADR-0006, ADR-0010)."""

import pytest
from pydantic import ValidationError

from traboule.contracts import (
    Citation,
    Composante,
    Minorant,
    MotifAbstention,
    Reponse,
    VentilationConfiance,
)

CIT = Citation(
    source_id="SRC-005", doc_id="reglement.pdf", page=634, version_piece="Modification n° 4"
)


def comptage(**kw) -> Composante:
    base = {
        "type": "structuree",
        "valeur": 6,
        "comptage_spatial": True,
        "ventilation_confiance": VentilationConfiance(haute=3, moyenne=2, faible=1),
        "minorant": Minorant(n=4, perimetre="communes qui intersectent UEi2"),
    }
    return Composante(**(base | kw))


def test_mixed_answer_partially_abstained():
    # Comptage donné, affirmation réglementaire abstenue en confiance faible.
    reponse = Reponse(
        route="HYBRID",
        composantes=[
            comptage(),
            Composante(
                type="documentaire", abstention=True, motif=MotifAbstention.CONFIANCE_FAIBLE
            ),
        ],
    )
    assert reponse.composantes[1].valeur is None


def test_non_spatial_count_needs_no_lower_bound():
    # FAC-001 : comptage par code commune du stock, sans jointure spatiale.
    c = Composante(type="structuree", valeur=510)
    assert Reponse(route="SQL", composantes=[c]).composantes[0].minorant is None


def test_decimal_value_is_accepted():
    # FAC-003 : part des établissements actifs à diffusion partielle, en pourcentage.
    c = Composante(type="structuree", valeur=18.09)
    assert Reponse(route="SQL", composantes=[c]).composantes[0].valeur == 18.09


def test_abstention_may_cite_its_justification():
    # ABS-001 : la partie I (p. 17) exclut le PSMV du champ du règlement.
    c = Composante(
        type="documentaire",
        abstention=True,
        motif=MotifAbstention.AUTRE_DOCUMENT,
        citations=[CIT.model_copy(update={"page": 17})],
    )
    assert Reponse(route="ABSTAIN", composantes=[c]).composantes[0].citations


def test_abstention_has_no_value_and_a_reason():
    with pytest.raises(ValidationError, match="pas de valeur"):
        Composante(type="structuree", abstention=True, motif="hors_version", valeur=3)
    with pytest.raises(ValidationError, match="motif"):
        Composante(type="structuree", abstention=True)
    with pytest.raises(ValidationError, match="sans abstention"):
        Composante(type="structuree", valeur=3, motif="hors_version")


def test_spatial_count_requires_lower_bound_and_breakdown():
    with pytest.raises(ValidationError, match="minorant"):
        comptage(minorant=None)
    with pytest.raises(ValidationError, match="minorant"):
        comptage(ventilation_confiance=None)


def test_breakdown_totals_the_value():
    with pytest.raises(ValidationError, match="totalise"):
        comptage(valeur=7)


def test_lower_bound_wording():
    m = Minorant(n=2211, perimetre="de Vénissieux (69259)", qui="établissements actifs")
    assert m.formulation == (
        "2\u202f211 établissements actifs de Vénissieux (69259) n'ont pas de position publique "
        "et ne peuvent pas être placés : certains pourraient se trouver dans la zone."
    )
    assert "jusqu'à" not in m.formulation and "supplémentaires" not in m.formulation
    one = Minorant(n=1, perimetre="de Saint-Fons (69199)", qui="établissements actifs")
    assert one.formulation == (
        "1 établissement actif de Saint-Fons (69199) n'a pas de position publique et ne peut pas "
        "être placé : il pourrait se trouver dans la zone."
    )
    none = Minorant(n=0, perimetre="de Saint-Fons (69199)", qui="établissements fermés")
    assert none.formulation.startswith("Aucun établissement fermé de Saint-Fons (69199)")
    assert m.phrase("dans l'une de ces zones").endswith("dans l'une de ces zones.")


def test_citation_requires_piece_version():
    with pytest.raises(ValidationError):
        Citation(source_id="SRC-005", doc_id="reglement.pdf", page=634, version_piece="")
    with pytest.raises(ValidationError):
        Citation(source_id="SRC-005", doc_id="reglement.pdf", page=634)


def test_documentary_answer_cites_a_passage():
    with pytest.raises(ValidationError, match="cite"):
        Composante(type="documentaire", valeur="2 m")
    assert Composante(type="documentaire", valeur="2 m", citations=[CIT])


@pytest.mark.parametrize(
    "route,types",
    [("SQL", ["documentaire"]), ("RAG", ["structuree"]), ("HYBRID", ["structuree"])],
)
def test_route_matches_component_types(route, types):
    comps = [
        comptage() if t == "structuree" else Composante(type=t, valeur="x", citations=[CIT])
        for t in types
    ]
    with pytest.raises(ValidationError, match="route"):
        Reponse(route=route, composantes=comps)


def test_abstain_route_requires_all_components_abstained():
    with pytest.raises(ValidationError, match="ABSTAIN"):
        Reponse(route="ABSTAIN", composantes=[comptage()])


def test_structured_component_carries_its_sources_and_query():
    from traboule.contracts.reponse import SourceDonnees

    source = SourceDonnees(
        table="etablissements", millesime="stock Sirene du 2026-10-01", sources=["SRC-001a"]
    )
    c = Composante(
        type="structuree",
        valeur=510,
        texte="510 établissements actifs",
        sources=[source],
        requete="select count(*) from v_etablissements",
    )
    r = Reponse(route="SQL", composantes=[c], question="Combien ?", strategie="rag")
    assert r.composantes[0].sources[0].sources == ["SRC-001a"]
    with pytest.raises(ValidationError):
        SourceDonnees(table="etablissements", millesime="2026", sources=[])
    with pytest.raises(ValidationError):
        Reponse(route="SQL", composantes=[c], strategie="graphrag")
