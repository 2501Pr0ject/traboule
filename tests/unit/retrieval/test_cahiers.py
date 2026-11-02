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


def test_version_read_on_passage_start_page(pages):
    pages[1].texte_pymupdf = "MODIFICATION N°4\nApprobation - 2024\nCOMMUNE"  # couverture
    pages[
        4
    ].texte_pymupdf = "PLU-H - TEST - Modification n°3 - Approbation 2022\nOAP\n2.1 Les Girondins"
    pages[6].texte_pymupdf = "Annexe sans en-tête"
    commune = {"secteur_pluh": "65", "code_commune_cog2026": "69259", "commune_historique": "69259"}
    passages, quality = ca.build_passages("c.pdf", TOC, pages, commune)
    by_page = {p.page_debut: p.version_piece for p in passages}
    assert quality["version_piece"] == by_page[1] == "Modification n°4 - Approbation 2024"
    assert by_page[4] == "Modification n°3 - Approbation 2022"
    # Page 6 sans en-tête : version de la page 5.
    assert by_page[6] == "Modification n°4 - Approbation 2024"
    assert quality["passages_version_hors_couverture"] == 1
    assert quality["passages_version_par_repli"] == 1


def test_passage_is_cut_at_a_version_boundary(pages):
    # Pages 1 et 2 : même chemin ; la page 2 porte une autre version.
    pages[2].texte_pymupdf = "PLU-H - TEST - Modification n°3 - Approbation 2022\nTexte"
    commune = {"secteur_pluh": "65", "code_commune_cog2026": "69259", "commune_historique": "69259"}
    passages, quality = ca.build_passages("c.pdf", TOC, pages, commune)
    first = [p for p in passages if p.chemin == passages[0].chemin]
    assert [(p.page_debut, p.page_fin, p.version_piece) for p in first] == [
        (1, 1, "Modification n°4 - Approbation 2024"),
        (2, 2, "Modification n°3 - Approbation 2022"),
    ]
    assert quality["coupures_de_version"] == 1


def test_cover_without_version_is_refused(pages):
    pages[1].texte_pymupdf = "Couverture"
    with pytest.raises(ca.CahierError, match="couverture"):
        ca.page_versions(pages)


def test_canonical_version():
    assert ca.canonical_version("Mise en compatibilité N°6 - Approbation 2025") == (
        "Mise en compatibilité n°6 - Approbation 2025"
    )
    assert ca.canonical_version("MODIFICATION N° 4 – Approbation 2024") == (
        "Modification n°4 - Approbation 2024"
    )


def test_passage_id_is_stable():
    a = ca.passage_id("c.pdf", 3, ["4. OAP", "OAP 1 X"], 1)
    assert a == ca.passage_id("c.pdf", 3, ["4. OAP", "OAP 1 X"], 1) and len(a) == 16
    assert a != ca.passage_id("c.pdf", 3, ["4. OAP", "OAP 1 X"], 2)


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


SOMMAIRE = (
    "Sommaire\n1.\tRapport de présentation.......................1\n"
    "\tI Habitat..........................17\n"
    "4.\tOrientations d'Aménagement et de Programmation (OAP)...........3\n"
    "5.\tRapport de présentation.......... 6\n"
)


def test_printed_sommaire_replaces_missing_bookmarks(pages):
    pages[2].texte_pymupdf = SOMMAIRE
    toc, source, _ = ca.structure_toc([], pages)
    assert source == "sommaire imprimé"
    assert toc == [
        (1, "1. Rapport de présentation", 1),
        (1, "4. Orientations d'Aménagement et de Programmation (OAP)", 3),
        (1, "5. Rapport de présentation", 6),
    ]
    assert ca.oap_part(toc, 6) == range(3, 6)
    assert ca.structure_toc(TOC, pages) == (TOC, "signets", [])


def test_oap_part_is_the_union_of_bookmarks_and_printed_sommaire():
    # Signets décalés de deux pages (fin de la partie 4 à la page 3 au lieu de 5).
    shifted = [(1, "4. Orientations d'Aménagement et de Programmation (OAP)", 1), (1, "5. A", 4)]
    printed = [(1, "4. Orientations d'Aménagement et de Programmation (OAP)", 3), (1, "5. A", 6)]
    assert ca.oap_part(shifted, 6, printed) == range(1, 6)


def test_only_the_first_oap_title_of_a_page_counts(pages):
    pages[
        4
    ].texte_pymupdf = (
        "OAP \n5.1 Génovéfains - Lyon 5\nTexte\nOAP \n5.1\nOAP \n0.1\nSite UNESCO (renvoi)"
    )
    assert ca.oap_titles(pages, range(4, 5)) == {4: "OAP 5.1 Génovéfains - Lyon 5"}


def test_unnumbered_oap_title_is_read_on_the_first_line(pages):
    pages[3].texte_pymupdf = (
        "56\nPLU-H - TEST\n4.\t\nOrientations d'Aménagement et de \nProgrammation (OAP)\n"
        "Centre bourg \nEncadrer la restructuration.\nPrincipes d'aménagement\nOAP \n1\n"
    )
    pages[4].texte_pymupdf = "OAP \n3\nGriset\nEncadrer."
    assert ca.oap_titles(pages, range(3, 5)) == {3: "OAP 1 Centre bourg", 4: "OAP 3 Griset"}


def test_cited_oap_must_be_detected_or_excepted():
    exceptions = {("cahier_a", "0.1"): "Définie dans le cahier communal de Lyon"}
    assert ca.check_oaps("cahier_a", ["0.1"], exceptions) == {
        "0.1": "Définie dans le cahier communal de Lyon"
    }
    with pytest.raises(ca.CahierError, match="sans exception"):
        ca.check_oaps("cahier_a", ["0.1", "2"], exceptions)


def test_oap_exceptions_carry_reason_and_decision(tmp_path):
    exceptions = ca.load_oap_exceptions()
    assert exceptions and all(exceptions.values())
    assert ("cahier_arrondissement_sect36", "0.1") in exceptions
    path = tmp_path / "oap.yaml"
    path.write_text("exceptions:\n  - ressource: a\n    oap: '1'\n", encoding="utf-8")
    with pytest.raises(ca.CahierError, match="incomplète"):
        ca.load_oap_exceptions(path)


def test_shared_piece_payload_names_lyon_not_an_arrondissement():
    from traboule.retrieval.index_config import load_identical

    (group,) = load_identical()
    payload = ca.shared_payload(group)
    assert payload["titre_piece"] == "Cahier communal de Lyon (identique pour les secteurs 31 à 39)"
    assert payload["commune_historique"] == "69123" and "secteur_pluh" not in payload


def test_shifted_part_bookmark_is_corrected_by_the_printed_sommaire(pages):
    pages[2].texte_pymupdf = SOMMAIRE
    pages[3].texte_pymupdf = "4. Orientations d'Aménagement et de Programmation (OAP)"
    pages[1].texte_pymupdf = "3. Programme d'Orientations et d'Actions pour l'Habitat"
    shifted = [(1, "4. Orientations d'Aménagement et de Programmation (OAP)", 1)]
    toc, _, corrections = ca.structure_toc(shifted, pages)
    assert toc == [(1, "4. Orientations d'Aménagement et de Programmation (OAP)", 3)]
    assert corrections == ["4. Orientations d'Aménagement et de Programmation (OAP) : page 1 → 3"]


def test_referral_to_another_piece_is_not_an_oap(pages):
    # Arrondissement 36 : la partie 4 ne contient qu'un renvoi au cahier communal de Lyon.
    pages[3].texte_pymupdf = "OAP \n0.1\nSite UNESCO (se référer au cahier communal - LYON)"
    # Arrondissement 36 : nom avant le numéro, numéro seul en fin de page.
    pages[
        4
    ].texte_pymupdf = (
        "Programmation (OAP)\nSite UNESCO (se référer au cahier communal)\nOAP \n0.1\n"
    )
    assert ca.oap_titles(pages, range(3, 5)) == {}
