"""Stratégie CAG : chapitre entier, abstention au-delà de la fenêtre, cache explicite."""

import json

from test_repondre import WordCounter, passage

from traboule.chaine.cag import CagStrategy, cache_key
from traboule.chaine.contexte import Corpus
from traboule.contracts.passage import Renvoi
from traboule.routing.analyse import Analysis, Place


def corpus():
    renvoi = Renvoi(cible="Partie I, CHAPITRE 5", doc_id="d", passage_ids=["i1"])
    return Corpus(
        [
            passage(1, renvoi_vers=[renvoi]),
            passage(2, zone="UEi2"),
            passage(3),
            passage(
                9,
                zone=None,
                zones_applicables=None,
                chemin=["Partie I", "CHAPITRE 5"],
                passage_id="i1",
            ),
            passage(
                4,
                zone=None,
                zones_applicables=None,
                chemin=["OAP"],
                oap="OAP 2 Le Puits",
                doc_id="200046977_cahier_communal_SECT22_20260326.pdf",
                secteur_pluh="22",
                code_commune_cog2026="69259",
                commune_historique="69259",
            ),
        ]
    )


def strategy(tmp_path):
    return CagStrategy(corpus(), WordCounter(), "qwen3:8b", 20480, cache_dir=tmp_path)


def test_whole_chapter_without_part_one_and_untrimmable(tmp_path):
    ctx = strategy(tmp_path).build(Analysis(question="q"), ["UEi1"])
    assert [p.passage_id for p in ctx.passages] == ["p1", "p3"]
    assert not ctx.trimmable
    assert any("Renvois cités, non chargés : Partie I, CHAPITRE 5" in n for n in ctx.notes)


def test_cache_entry_is_prepared_then_reused(tmp_path):
    s = strategy(tmp_path)
    first = s.build(Analysis(question="q1"), ["UEi1"])
    second = s.build(Analysis(question="q2"), ["UEi1"])
    assert "préparé" in first.notes[0] and "réutilisé (2e utilisation)" in second.notes[0]
    (path,) = tmp_path.glob("*.json")
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert entry["passages"] == ["p1", "p3"] and entry["utilisations"] == 2


def test_key_changes_with_the_text_or_the_window():
    a = [passage(1), passage(3)]
    b = [passage(1), passage(3, texte="Texte modifié.")]
    assert cache_key("qwen3:8b", 20480, a) != cache_key("qwen3:8b", 20480, b)
    assert cache_key("qwen3:8b", 20480, a) != cache_key("qwen3:8b", 16384, a)
    assert cache_key("qwen3:8b", 20480, a) == cache_key("qwen3:8b", 20480, list(a))


def test_oap_by_number_and_commune(tmp_path):
    analysis = Analysis(question="q", oap="2", places=(Place("69259", "commune", "Vénissieux"),))
    ctx = strategy(tmp_path).build(analysis, [])
    assert [p.passage_id for p in ctx.passages] == ["p4"]


def test_no_zone_nor_oap_is_refused(tmp_path):
    ctx = strategy(tmp_path).build(Analysis(question="q"), [])
    assert ctx.refusal and "zone ou une OAP" in ctx.refusal
