"""Structure et passages des cahiers (ADR-0008, ADR-0009), sur des pages synthétiques."""

import pytest

from traboule.retrieval import cahiers as ca
from traboule.retrieval.extraction import Page

V = "PLU-H - TEST - Modification n°4 - Approbation 2024"


def page(n, raw, lines, graphique=False):
    return Page(n, f"{n}\n{V}\n{raw}", 500, 0.0, 0, graphique, lignes=[V, *lines])


TOC = [
    (1, "1. Rapport de présentation", 1),
    (2, "Diagnostic", 1),
    (1, "4. Orientations d'Aménagement et de Programmation (OAP)", 3),
    (1, "5. Annexe", 6),
]


@pytest.fixture
def pages():
    return {
        1: page(1, "Texte", ["Diagnostic de la commune."]),
        2: page(2, "Texte", ["Suite du diagnostic."]),
        3: page(3, "OAP \n0.1\nOAP \n1\nIlot Médiathèque", ["Orientation de l'îlot."]),
        4: page(4, "OAP \n2.1 Les Girondins", ["Programme de l'îlot 2.1."]),
        5: page(5, "Plan", [], graphique=True),
        6: page(6, "Texte", ["Annexe."]),
    }


def test_oap_part_even_with_altered_title():
    assert ca.oap_part(TOC, 6) == range(3, 6)
    altered = [(1, "4. Orientations d'Aménagement et de4. Orientation d'Aménagem", 3)]
    assert ca.oap_part(altered, 6) == range(3, 7)


def test_oap_titles_name_on_next_or_same_line_and_reference_excluded(pages):
    assert ca.oap_titles(pages, range(3, 6)) == {
        3: "OAP 1 Ilot Médiathèque",
        4: "OAP 2.1 Les Girondins",
    }


def test_dashed_oap_number(pages):
    pages[4].texte_pymupdf = "OAP\n11 -1 Peyssilieu"
    assert ca.oap_titles(pages, range(4, 5)) == {4: "OAP 11-1 Peyssilieu"}


def test_toc_paths():
    paths = ca.chemins(TOC, 6)
    assert paths[1] == ["1. Rapport de présentation", "Diagnostic"]
    assert paths[3] == ["4. Orientations d'Aménagement et de Programmation (OAP)"]


def test_passages_carry_path_oap_commune_and_drop_running_lines(pages):
    commune = {"secteur_pluh": "65", "code_commune_cog2026": "69259", "commune_historique": "69259"}
    passages, quality = ca.build_passages("c.pdf", TOC, pages, commune)
    assert quality["version_piece"] == "Modification n°4 - Approbation 2024"
    assert all(V not in p.texte for p in passages) and quality["en_tetes_retires"] == 6
    oap = [p for p in passages if p.oap]
    assert [p.oap for p in oap] == ["OAP 1 Ilot Médiathèque", "OAP 2.1 Les Girondins"]
    assert oap[0].chemin[-1] == "OAP 1 Ilot Médiathèque" and oap[0].secteur_pluh == "65"
    first = passages[0]
    assert (first.page_debut, first.page_fin, first.extracteur) == (1, 2, "docling")


def test_passage_id_is_stable():
    a = ca.passage_id("c.pdf", 3, ["4. OAP", "OAP 1 X"], 1)
    assert a == ca.passage_id("c.pdf", 3, ["4. OAP", "OAP 1 X"], 1) and len(a) == 16
    assert a != ca.passage_id("c.pdf", 3, ["4. OAP", "OAP 1 X"], 2)


def test_split_long_at_sentence_boundaries():
    chunks = ca.split_long("Phrase une. " * 300, max_chars=500)
    assert all(len(c) <= 500 for c in chunks) and len(chunks) > 1


@pytest.mark.parametrize(
    "file_name,expected",
    [("x_cahier_arrondissement_SECT37_2026.pdf", ("37", "69123", "69387")),
     ("x_cahier_communal_SECT46_2026.pdf", ("46", "69149", "69152"))],
)  # fmt: skip
def test_commune_codes_follow_cog_2026(file_name, expected):
    c = ca.commune_of(
        file_name, {"37": "69387", "46": "69152"}, {"69387": "69123", "69152": "69149"}
    )
    assert (c["secteur_pluh"], c["code_commune_cog2026"], c["commune_historique"]) == expected


def test_unknown_sector_is_refused():
    with pytest.raises(ca.CahierError, match="secteur"):
        ca.commune_of("x_SECT99_.pdf", {"37": "69387"}, {})


def test_split_ligature_fragments_are_counted_not_repaired():
    assert ca.SPLIT_LIGATURE.findall("la créati on de la parti e nord") == ["créati on", "parti e"]
