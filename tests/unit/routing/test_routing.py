"""Analyse déterministe et routeur sur les questions de démonstration."""

import pytest

from traboule.routing.analyse import Activity, DateMention, analyse, normalize
from traboule.routing.routeur import route

DEMO = {
    "FAC-001": "Combien d'établissements actifs relevant de la section C (NAF rév. 2) sont "
    "recensés dans le 7e arrondissement de Lyon ?",
    "FAC-002": "Combien d'établissements actifs compte la commune d'Oullins-Pierre-Bénite ?",
    "FAC-003": "Quelle part des établissements actifs de la Métropole de Lyon fait l'objet "
    "d'une diffusion partielle ?",
    "FAC-004": "Combien d'établissements actifs sont situés en zone UEi1 à Vénissieux ?",
    "DOC-001": "Quelle est la hauteur maximale des clôtures sur limite séparative en zone UEi1 ?",
    "DOC-002": "Quel est le coefficient d'emprise au sol en zone UEi2 ?",
    "DOC-004": "Quelles règles s'appliquent à une zone AUEi1 ?",
    "MIX-001": "Combien d'établissements actifs de commerce de détail (division 47, NAF rév. 2) "
    "sont situés en zone UEi2, et à quelles conditions le règlement y admet-il ce commerce ?",
    "MIX-002": "Comment se répartissent les établissements industriels actifs (section C, NAF "
    "rév. 2) d'Oullins-Pierre-Bénite entre les zones du PLU-H, et quelle est la règle "
    "d'emprise au sol des zones économiques concernées ?",
    "MIX-004": "Combien d'établissements d'entreposage (52.10, NAF rév. 2) sont situés en zone "
    "UEi2, et le règlement permet-il l'extension de leurs bâtiments ?",
    "ABS-001": "Que prévoit le PLU-H pour la hauteur des constructions dans le Vieux-Lyon "
    "(secteur sauvegardé) ?",
    "ABS-002": "Que prévoit le règlement pour la zone UEi3 ?",
    "ABS-003": "Combien d'établissements actifs comptait la Métropole de Lyon au 1er janvier "
    "2012 ?",
}


@pytest.mark.parametrize(
    ("qid", "expected"),
    [
        ("FAC-001", "SQL"),
        ("FAC-002", "SQL"),
        ("FAC-003", "SQL"),
        ("FAC-004", "SQL"),
        ("DOC-001", "RAG"),
        ("DOC-002", "RAG"),
        ("DOC-004", "RAG"),
        ("MIX-001", "HYBRID"),
        ("MIX-002", "HYBRID"),
        ("MIX-004", "HYBRID"),
        ("ABS-001", "ABSTAIN"),
        ("ABS-002", "ABSTAIN"),
        ("ABS-003", "ABSTAIN"),
    ],
)
def test_demo_questions_are_routed(lexicon, qid, expected):
    assert route(analyse(DEMO[qid], lexicon), lexicon).route == expected


def test_arrondissement_is_not_the_commune_of_lyon(lexicon):
    a = analyse(DEMO["FAC-001"], lexicon)
    assert [p.code for p in a.places] == ["69387"]
    assert a.activity == Activity("section", "C", "industrie manufacturière")
    assert a.measure == "count" and a.unknown_activity is None


def test_metropole_de_lyon_is_not_the_commune(lexicon):
    a = analyse(DEMO["FAC-003"], lexicon)
    assert a.places == () and a.measure == "share" and a.partial_diffusion


def test_compound_commune_and_zone(lexicon):
    a = analyse(DEMO["FAC-004"], lexicon)
    assert a.zones == ("UEi1",) and [p.code for p in a.places] == ["69259"]
    assert [p.code for p in analyse(DEMO["FAC-002"], lexicon).places] == ["69149"]
    assert [p.code for p in analyse("Combien à Sainte-Foy-lès-Lyon ?", lexicon).places] == ["69202"]


def test_naf_codes_are_read(lexicon):
    assert analyse(DEMO["MIX-001"], lexicon).activity == Activity("division", "47")
    assert analyse(DEMO["MIX-004"], lexicon).activity == Activity("classe", "52.10")
    a = analyse(DEMO["MIX-002"], lexicon)
    assert a.activity.code == "C" and a.measure == "distribution" and a.rule
    assert analyse("Combien de pharmacies à Lyon ?", lexicon).activity.code == "47.73Z"


@pytest.mark.parametrize(
    "question",
    [
        "Combien de boulangeries à Villeurbanne ?",
        "Combien d'établissements de santé à Villeurbanne ?",
        "Combien d'entreprises à Lyon ?",
        "Combien d'établissements agricoles à Villeurbanne ?",
    ],
)
def test_unknown_activity_abstains_instead_of_counting_everything(lexicon, question):
    a = analyse(question, lexicon)
    assert a.unknown_activity
    d = route(a, lexicon)
    assert d.route == "ABSTAIN" and d.structured_abstention[0] == "preuve_insuffisante"


def test_zone_abstentions(lexicon):
    d = route(analyse(DEMO["ABS-002"], lexicon), lexicon)
    assert d.documentary_abstention[0] == "zone_inexistante"
    assert "UEi1" in d.documentary_abstention[1] and "UEi2" in d.documentary_abstention[1]
    d = route(analyse(DEMO["ABS-001"], lexicon), lexicon)
    assert d.documentary_abstention[0] == "autre_document"
    d = route(analyse("Que prévoit le règlement en zone A2s1 ?", lexicon), lexicon)
    assert d.route == "ABSTAIN" and d.documentary_abstention[0] == "document_non_ingere"


def test_dates_outside_loaded_versions(lexicon):
    a = analyse(DEMO["ABS-003"], lexicon)
    assert a.dates == (DateMention(2012, 1, 1),)
    assert route(a, lexicon).structured_abstention[0] == "hors_version"
    current = analyse("Combien d'établissements actifs à Lyon au 1er octobre 2026 ?", lexicon)
    assert route(current, lexicon).route == "SQL"
    assert analyse("Combien en NAF 2025 à Lyon ?", lexicon).dates == ()


def test_count_in_safeguarded_sector_is_answered_but_its_rules_are_not(lexicon):
    d = route(
        analyse(
            "Combien d'établissements actifs dans le Vieux-Lyon, et quelles règles "
            "s'y appliquent ?",
            lexicon,
        ),
        lexicon,
    )
    assert d.route == "HYBRID"
    assert d.structured_abstention is None and d.documentary_abstention[0] == "autre_document"


def test_zone_codes_map_to_chapters_and_zonage_codes(lexicon):
    assert lexicon.chapters_of("AUEi1") == ["AUs.co", "UEi1"]
    assert lexicon.chapters_of("UCe3-p") == ["UCe3"]
    assert lexicon.chapters_of("UCe3") == ["UCe3"]
    assert lexicon.zonage_codes("UCe3") == ["UCe3-p", "UCe3a"]
    assert lexicon.zonage_codes("UPr3") == ["UPr3", "UPr3c"]
    assert lexicon.zonage_codes("UEi1") == ["UEi1"]
    assert lexicon.zonage_codes("AUEi1") == ["AUEi1"]


def test_normalize():
    assert normalize("Oullins-Pierre-Bénite, l'Étoile") == "oullins pierre benite l etoile"


@pytest.mark.parametrize(
    "question",
    [
        "Quelle part des établissements actifs est en diffusion partielle ?",
        "Combien d'établissements actifs font l'objet d'une diffusion partielle à Lyon ?",
        "Combien d'établissements fermés à Villeurbanne ?",
    ],
)
def test_verbs_after_establishments_are_not_activities(lexicon, question):
    assert analyse(question, lexicon).unknown_activity is None
