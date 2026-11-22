"""Contrôles d'une réponse documentaire : sujet des passages cités et valeurs chiffrées."""

import pytest
from test_redaction import passage

from traboule.generation.verification import canonical, numbers, on_topic, unsupported_values
from traboule.routing.analyse import normalize
from traboule.routing.sujets import BY_NAME, detect

URM1 = ["Partie II Règlement des zones", "2.1 LES ZONES MIXTES", "Zone URm1"]
PLEINE_TERRE = passage(
    1,
    chemin=[
        *URM1,
        "CHAPITRE 3 - NATURE EN VILLE",
        "3.2 - Le traitement des espaces libres : aspects quantitatifs",
        "3.2.1 - Le coefficient de pleine terre",
    ],
    texte="Le coefficient de pleine terre* est au minimum de 25%.",
)
EMPRISE = passage(
    2,
    chemin=[
        *URM1,
        "CHAPITRE 2 - MORPHOLOGIE ET IMPLANTATION DES CONSTRUCTIONS",
        "2.4 - Emprise au sol des constructions",
        "2.4.1 - Règle générale",
    ],
    texte="a. L'emprise au sol* des constructions n'est pas réglementée.",
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("au minimum de 25%.", [("25", True)]),
        (
            "2 mètres, 4,5 m et 1 500 m² ; 0,50",
            [("2", True), ("4.5", True), ("1500", True), ("0.5", False)],
        ),
        ("10 000 m2 et 60 %", [("10000", True), ("60", True)]),
        ("le 1er rang, la 2e bande [3]", []),
        ("zone UEi1, article 2.4.1", [("2.4.1", False)]),
    ],
)
def test_numbers_are_normalized(text, expected):
    assert numbers(text) == expected


def test_canonical_forms():
    assert (
        canonical("4,00") == "4" and canonical("4.50") == "4.5" and canonical("10 000") == "10000"
    )
    assert canonical("2.4.1") == "2.4.1"


def test_topics_of_the_demo_questions():
    assert detect(normalize("Quel est le coefficient d'emprise au sol en zone URm1 ?")) == (
        "emprise au sol",
    )
    assert "pleine terre" in detect(
        normalize("Le règlement y impose-t-il un coefficient de pleine terre ?")
    )
    assert set(detect(normalize("Hauteur maximale des clôtures sur limite séparative ?"))) == {
        "hauteur",
        "limites séparatives",
        "clôtures",
    }
    assert detect(normalize("Que prévoit l'OAP 3 ?")) == ()


def test_urm1_answer_citing_full_earth_for_ground_coverage_is_off_topic():
    topics = [BY_NAME["emprise au sol"]]
    assert not on_topic(topics, [PLEINE_TERRE])
    assert on_topic(topics, [PLEINE_TERRE, EMPRISE])
    assert on_topic([], [PLEINE_TERRE])


def test_cahier_passage_is_matched_on_its_text():
    oap = passage(
        3,
        doc_id="200046977_cahier_communal_SECT22_20260326.pdf",
        chemin=["OAP", "OAP 3 Le Mas"],
        texte="La hauteur des constructions est R+2.",
    )
    assert on_topic([BY_NAME["hauteur"]], [oap])


def test_values_must_be_found_in_the_cited_passages():
    assert unsupported_values("Au minimum 25 %.", "Emprise ?", [PLEINE_TERRE]) == []
    assert unsupported_values("Au minimum 30 % et 12 m.", "Emprise ?", [PLEINE_TERRE]) == [
        "30",
        "12",
    ]
    # Repris de la question sans unité : exempté ; avec une unité : à prouver.
    assert (
        unsupported_values(
            "Section C (NAF rév. 2) : 25 %.", "section C, NAF rév. 2 ?", [PLEINE_TERRE]
        )
        == []
    )
    assert unsupported_values("Oui, 12 m.", "La hauteur est-elle de 12 m ?", [PLEINE_TERRE]) == [
        "12"
    ]


def test_value_with_unit_is_proved_by_the_text_only():
    article = passage(
        4,
        chemin=["Partie II", "Zone UEi1", "2.4 - Emprise au sol des constructions"],
        texte="L'emprise au sol des constructions n'est pas réglementée.",
    )
    # « 2,4 m » n'est pas validé par le chemin « 2.4 - Emprise au sol ».
    assert unsupported_values("Un recul de 2,4 m.", "Emprise ?", [article]) == ["2.4"]
    # Sans unité, un numéro d'article est retrouvé dans le chemin.
    assert unsupported_values("Voir l'article 2.4.", "Emprise ?", [article]) == []
    # Une unité dans la réponse exige le texte, même si la question cite le nombre sans unité.
    assert unsupported_values("Une hauteur de 2 m.", "Article 2 ?", [article]) == ["2"]
