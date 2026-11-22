"""Chaîne complète avec un modèle et une recherche simulés : routes, composantes, affichage."""

import json

from rich.console import Console

from traboule.chaine.affichage import show
from traboule.chaine.rag import RagStrategy
from traboule.chaine.repondre import Chain
from traboule.chaine.sql import load_lexicon
from traboule.contracts.passage import Passage, Renvoi
from traboule.generation.llm_config import load_llm_config
from traboule.generation.ollama import ChatResult
from traboule.routing.analyse import Analysis


def passage(i: int, zone: str = "UEi1", **extra) -> Passage:
    fields = {
        "passage_id": f"p{i}",
        "texte": f"Texte du passage {i} : la hauteur est limitée à 2 m.",
        "doc_id": "200046977_reglement_20260326.pdf",
        "source_id": "SRC-005",
        "version_piece": "Modification n°4 - Approbation 2024",
        "version_gpu": "200046977_PLUi_20260326",
        "page_debut": 620 + i,
        "page_fin": 620 + i,
        "chemin": ["Partie II", f"Zone {zone}", f"2.5 - Hauteur des constructions ({i})"],
        "extracteur": "pymupdf",
        "zone": zone,
        "zones_applicables": [zone],
    }
    return Passage(**(fields | extra))


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


class FakeLlm:
    def __init__(self):
        self.config = load_llm_config()
        self.calls = []

    def chat(self, strategy, system, user, schema=None):
        self.calls.append((strategy, system, user))
        answer = {"reponse": "2 mètres.", "passages_cites": [1], "suffisant": True}
        return ChatResult(json.dumps(answer), prompt_tokens=10, seconds=0.1)

    def close(self):
        pass


class FakeSearch:
    def __init__(self, passages):
        self.passages = passages
        self.calls = []

    def __call__(self, question, zones):
        self.calls.append(zones)
        return [p for p in self.passages if not zones or set(zones) & set(p.zones_applicables)]


def chain(con, search):
    return Chain(
        con=con,
        lexicon=load_lexicon(con),
        llm=FakeLlm(),
        counter=WordCounter(),
        factories={"rag": lambda: RagStrategy(search)},
    )


def test_rag_question_is_answered_with_verified_citations(con):
    renvoi = Renvoi(cible="Partie I, CHAPITRE 6", doc_id="d", passage_ids=["x"])
    search = FakeSearch([passage(1, renvoi_vers=[renvoi]), passage(2, zone="UEi2")])
    c = chain(con, search)
    r = c.ask("Quelle est la hauteur des clôtures en zone UEi1 ?")
    assert r.route == "RAG" and r.strategie == "rag"
    (doc,) = r.composantes
    assert doc.valeur == "2 mètres." and doc.citations[0].page == 621
    assert search.calls == [["UEi1"]]
    assert any("Renvois cités, non chargés : Partie I, CHAPITRE 6" in n for n in doc.notes)


def test_hybrid_question_has_both_components(con):
    c = chain(con, FakeSearch([passage(1)]))
    r = c.ask(
        "Combien d'établissements actifs en zone UEi1, et quelle règle de hauteur s'y applique ?"
    )
    assert r.route == "HYBRID"
    assert [x.type for x in r.composantes] == ["structuree", "documentaire"]
    assert r.composantes[0].valeur == 2
    assert "partie réglementaire" in c.llm.calls[0][2]


def test_structural_abstention_calls_neither_search_nor_model(con):
    search = FakeSearch([passage(1)])
    c = chain(con, search)
    r = c.ask("Que prévoit le règlement pour la zone UEi3 ?")
    assert r.route == "ABSTAIN" and r.composantes[0].motif == "zone_inexistante"
    assert search.calls == [] and c.llm.calls == []


def test_sql_question_does_not_load_the_strategy(con):
    c = chain(con, None)
    r = c.ask("Combien d'établissements actifs à Vénissieux ?")
    assert r.route == "SQL" and r.composantes[0].valeur == 4
    assert c._strategies == {}


def test_display_shows_route_values_and_citations(con):
    c = chain(con, FakeSearch([passage(1)]))
    console = Console(record=True, width=200)
    show(
        c.ask("Combien d'établissements actifs en zone UEi1, et quelle règle s'y applique ?"),
        console,
    )
    out = console.export_text()
    assert (
        "Route : HYBRID · stratégie RAG" in out
        and "Données (SQL)" in out
        and "Règlement (RAG)" in out
    )
    assert "Règlement du PLU-H, p. 621" in out and "Modification n°4 - Approbation 2024" in out


def test_rag_interleaves_one_search_per_chapter():
    search = FakeSearch(
        [passage(i, zone="UEi1") for i in range(1, 9)]
        + [passage(i, zone="AUs.co") for i in range(11, 19)]
    )
    ctx = RagStrategy(search).build(Analysis(question="q"), ["AUs.co", "UEi1"])
    assert search.calls == [["AUs.co"], ["UEi1"]]
    assert [p.passage_id for p in ctx.passages][:4] == ["p11", "p1", "p12", "p2"]
    assert len(ctx.passages) == 10


def test_closing_the_chain_closes_the_search_client(con):
    closed = []
    search = FakeSearch([passage(1)])
    search.close = lambda: closed.append(True)
    c = chain(con, search)
    c.ask("Quelle hauteur en zone UEi1 ?")
    c.close()
    assert closed == [True]


def test_off_topic_citation_is_blocked_in_the_chain(con):
    pleine_terre = passage(
        1,
        chemin=["Partie II", "Zone UEi1", "3.2.1 - Le coefficient de pleine terre"],
        texte="Le coefficient de pleine terre est au minimum de 25%.",
    )
    c = chain(con, FakeSearch([pleine_terre]))
    r = c.ask("Quel est le coefficient d'emprise au sol en zone UEi1 ?")
    (doc,) = r.composantes
    assert doc.abstention and doc.motif == "citation_non_verifiee"
    assert doc.texte.startswith(
        "Passage cité hors du sujet demandé : la question porte sur emprise au sol"
    )
