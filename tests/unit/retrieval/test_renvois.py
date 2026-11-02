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
