"""Renvois d'un passage vers les passages d'une OAP d'une autre pièce (ADR-0009, ADR-0011)."""

import pytest

from traboule.contracts.passage import Passage
from traboule.retrieval import renvois as rv


def passage(pid, texte, doc="a.pdf", oap=None):
    return Passage(
        passage_id=pid,
        texte=texte,
        doc_id=doc,
        source_id="SRC-005",
        version_piece="Modification n°4 - Approbation 2024",
        version_gpu="200046977_PLUi_20260326",
        page_debut=1,
        page_fin=1,
        chemin=["4. OAP"],
        extracteur="docling",
        oap=oap,
    )


TARGETS = [
    passage("t1", "Site UNESCO.", "lyon.pdf", "OAP 0.1 UNESCO ET ZONE TAMPON"),
    passage("t2", "Zone tampon.", "lyon.pdf", "OAP 0.1 UNESCO ET ZONE TAMPON"),
    passage("t3", "Autre OAP.", "lyon.pdf", "OAP 0.10 Autre"),
]


def test_citing_passages_link_to_every_passage_of_the_oap():
    sources = [passage("s1", "Voir OAP 0.1 et OAP 1.1."), passage("s2", "OAP 0.10 seule.")]
    out, linked = rv.link_oap(sources, TARGETS, "0.1", "OAP 0.1 — Lyon")
    assert linked == 1 and out[1].renvoi_vers is None
    (renvoi,) = out[0].renvoi_vers
    assert (renvoi.doc_id, renvoi.passage_ids) == ("lyon.pdf", ["t1", "t2"])
    # Résolution répétée : le lien n'est pas dupliqué.
    again, _ = rv.link_oap(out, TARGETS, "0.1", "OAP 0.1 — Lyon")
    assert len(again[0].renvoi_vers) == 1


def test_missing_target_or_citation_blocks():
    with pytest.raises(rv.RenvoiError, match="dans la cible"):
        rv.link_oap([passage("s1", "OAP 0.1")], TARGETS[2:], "0.1", "c")
    with pytest.raises(rv.RenvoiError, match="ne cite"):
        rv.link_oap([passage("s1", "Rien.")], TARGETS, "0.1", "c")


def test_configured_links_point_to_the_lyon_communal_cahier():
    links = rv.load_oap_links()
    assert len(links) == 8
    assert {(n, t) for _, n, t in links} == {("0.1", "cahier_communal_sect31")}


def regl(pid, texte, chemin):
    return passage(pid, texte, "reglement.pdf").model_copy(update={"chemin": chemin})


PARTIE_I = "Partie I - Dispositions communes"
REGLEMENT = [
    regl("c5", "Normes.", [PARTIE_I, "CHAPITRE 5 - DEPLACEMENTS", "5.1 - Accès"]),
    regl("c5b", "Calcul.", [PARTIE_I, "CHAPITRE 5 - DEPLACEMENTS", "5.2 - Stationnement"]),
    regl("t1", "Toitures.", [PARTIE_I, "CHAPITRE 3 - NATURE", "3.1.6.1 - Toitures végétalisées"]),
    regl(
        "z1",
        "Les normes se situent au chapitre 5 de la partie I du règlement ; conformément au "
        "3.1.6.1 de la Partie 1. Définitions prévues dans la partie I du règlement.",
        ["Partie II Règlement des zones", "Zone UCe1", "CHAPITRE 5 - STATIONNEMENT"],
    ),
]


def test_zone_articles_link_to_partie_i_chapters_and_articles():
    out, counts = rv.link_partie_i(REGLEMENT)
    renvois = {r.cible: r.passage_ids for r in out[3].renvoi_vers}
    assert renvois == {
        "Partie I, CHAPITRE 5 - DEPLACEMENTS": ["c5", "c5b"],
        "Partie I, 3.1.6.1 - Toitures végétalisées": ["t1"],
    }
    assert all(p.renvoi_vers is None for p in out[:3]) and sum(counts.values()) == 2


def test_reference_to_a_missing_partie_i_chapter_blocks():
    zone = regl("z", "Voir le chapitre 4 de la partie I.", ["Partie II", "Zone UCe1"])
    with pytest.raises(rv.RenvoiError, match="sans passage cible"):
        rv.link_partie_i([*REGLEMENT[:3], zone])
