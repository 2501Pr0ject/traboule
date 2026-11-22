"""Stratégie KAG léger : graphe de la structure et parcours déterministe."""

from test_repondre import passage

from traboule.chaine.contexte import Corpus
from traboule.chaine.kag import KagStrategy, article_key, build_graph, stems
from traboule.contracts.passage import Renvoi
from traboule.routing.analyse import Analysis

ZONE = ["Partie II", "2.3 LES ZONES", "Zone UEi1"]
PART_ONE = ["Partie I - Dispositions communes", "CHAPITRE 4 - QUALITÉ URBAINE"]


def corpus():
    renvoi = Renvoi(cible="Partie I, CHAPITRE 4", doc_id="d", passage_ids=["i1", "i2"])
    return Corpus(
        [
            passage(
                1, chemin=[*ZONE, "CHAPITRE 2 - MORPHOLOGIE", "2.5 - Hauteur des constructions"]
            ),
            passage(
                2,
                chemin=[*ZONE, "CHAPITRE 4 - QUALITÉ", "4.5 - Traitement des clôtures"],
                renvoi_vers=[renvoi],
            ),
            passage(
                3,
                chemin=[
                    *ZONE,
                    "CHAPITRE 4 - QUALITÉ",
                    "4.5 - Traitement des clôtures",
                    "Clôtures sur limite séparative",
                ],
            ),
            passage(4, chemin=[*ZONE, "CHAPITRE 3 - NATURE EN VILLE", "3.2 - Espaces libres"]),
            passage(
                5,
                zone=None,
                zones_applicables=None,
                passage_id="i1",
                chemin=[*PART_ONE, "4.4 - Les clôtures"],
                page_debut=90,
                page_fin=90,
                texte="Clôture : toute construction qui sert à enclore un terrain.",
            ),
            passage(
                6,
                zone=None,
                zones_applicables=None,
                passage_id="i2",
                chemin=[*PART_ONE, "4.1 - Insertion du projet"],
                page_debut=91,
                page_fin=91,
                texte="Espace libre : surface du terrain non occupée par les constructions.",
            ),
            passage(
                7,
                zone=None,
                zones_applicables=None,
                chemin=["OAP"],
                oap="OAP 3 Le Mas",
                doc_id="200046977_cahier_communal_SECT22_20260326.pdf",
                secteur_pluh="22",
                code_commune_cog2026="69259",
                commune_historique="69259",
            ),
        ]
    )


TERMS = [{"terme": "Clôture", "page_pdf": "90"}, {"terme": "Espace libre", "page_pdf": "91"}]


def test_article_keys_and_stems():
    assert article_key([*ZONE, "CHAPITRE 2", "2.5 - Hauteur", "a. Règle"]) == (
        *ZONE,
        "CHAPITRE 2",
        "2.5 - Hauteur",
    )
    assert article_key([*PART_ONE, "4.4 - Les clôtures", "détail"]) == (
        *PART_ONE,
        "4.4 - Les clôtures",
    )
    assert stems("Hauteur maximale des clôtures") == {"hauteu", "clotur"}


def test_traversal_follows_titles_renvois_and_definitions():
    kag = KagStrategy(corpus(), build_graph(corpus(), TERMS))
    ctx = kag.build(Analysis(question="Hauteur des clôtures sur limite séparative ?"), ["UEi1"])
    ids = [p.passage_id for p in ctx.passages]
    # 4.5 (2 mots en commun) avant 2.5 (1 mot) ; renvoi vers 4.4 de la partie I, pas vers 4.1.
    assert ids[:3] == ["p2", "p3", "p1"] and "i1" in ids and "i2" not in ids and "p4" not in ids
    path = " ".join(ctx.notes)
    assert "UEi1 → 4.5 - Traitement des clôtures" in path
    assert "renvoi Partie I, CHAPITRE 4 › 4.4 - Les clôtures" in path
    assert ctx.trimmable


def test_definition_of_a_term_cited_in_the_question():
    kag = KagStrategy(corpus(), build_graph(corpus(), TERMS))
    assert kag.graph.definitions["cloture"].passage_id == "i1"
    ctx = kag.build(Analysis(question="Une clôture est-elle admise en espace libre ?"), ["UEi1"])
    ids = [p.passage_id for p in ctx.passages]
    assert "p4" in ids and "i1" in ids and "i2" in ids
    assert any("définition « espace libre » (p. 91)" in n for n in ctx.notes)


def test_oap_and_refusal():
    kag = KagStrategy(corpus(), build_graph(corpus(), TERMS))
    ctx = kag.build(Analysis(question="Que prévoit l'OAP 3 ?", oap="3"), [])
    assert [p.passage_id for p in ctx.passages] == ["p7"]
    ctx = kag.build(Analysis(question="Stationnement des vélos ?"), [])
    assert ctx.refusal and "aucun passage" in ctx.refusal


def test_general_question_walks_the_chapter_in_order():
    kag = KagStrategy(corpus(), build_graph(corpus(), TERMS))
    ctx = kag.build(Analysis(question="Quelles règles s'appliquent ?"), ["UEi1"])
    assert [p.passage_id for p in ctx.passages] == ["p1", "p2", "p3", "p4"]
    assert any("premiers articles du chapitre dans l'ordre" in n for n in ctx.notes)
