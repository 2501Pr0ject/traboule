"""Structure, tableaux et passages du règlement (ADR-0008, ADR-0009, ADR-0011)."""

import pytest

from traboule.contracts.passage import AliasCode
from traboule.retrieval import reglement as rg

TOC = [
    (1, "SOMMAIRE GENERAL", 1),
    (1, "Partie I - Dispositions communes", 2),
    (2, "SOMMAIRE DE LA PARTIE I", 3),
    (2, "CHAPITRE 5 - DEPLACEMENTS", 4),
    (1, "Partie II Règlement des zones", 6),
    (2, "2.1 LES ZONES MIXTES", 7),
    (3, "Zone UCe1", 8),
    (2, "2.2 ZONES PROJET", 10),
    (3, "Dispositions communes", 10),
    (3, "Zone UPr1", 11),
]
V = "Modification n°4 - Approbation 2024"


def test_navigation_pages_are_sommaires_index_and_covers():
    # 1 sommaire ; 2 garde de la partie I ; 3 sommaire de la partie I ; 6 garde de la partie II ;
    # 7 garde du groupe 2.1.
    assert rg.navigation_pages(TOC, 12) == {1, 2, 3, 6, 7}


def test_toc_context_gives_part_group_and_zone():
    ctx = rg.toc_context(TOC, 12)
    assert ctx[4] == {"partie": "Partie I - Dispositions communes", "groupe": None, "entree": None}
    assert ctx[9] == {
        "partie": "Partie II Règlement des zones",
        "groupe": "2.1 LES ZONES MIXTES",
        "entree": "Zone UCe1",
    }


def test_running_lines_are_removed_but_the_zone_title_is_kept():
    lines = [
        "METROPOLE DE LYON – PLU-H – REGLEMENT – PARTIE II",
        "Zone UCe1",
        "PLU-H – MODIFICATION N° 4 – APPROBATION 2024",
        "119",
        "Zone UCe1",
        "Centre ancien imbriqué",
    ]
    assert rg.clean_page(lines, "Zone UCe1") == ["Zone UCe1", "Centre ancien imbriqué"]


def blocs(pages):
    ctx = rg.toc_context(TOC, 12)
    return rg.structure(pages, ctx, {n: V for n in pages})


def test_zone_label_preamble_chapters_and_nested_articles():
    pages = {
        8: [
            "Zone UCe1",
            "Centre ancien",
            "imbriqué",
            "CARACTÈRE DE LA ZONE",
            "Tissu urbain dense.",
            "CHAPITRE 1 - DESTINATION DES CONSTRUCTIONS, USAGE ET",
            "AFFECTATION DES SOLS",
            "1.1 - Les destinations interdites",
            "1.1.1 - Destinations interdites",
            "a. Néant",
            "1.2 - Les destinations soumises",
            "à conditions",
            "Texte de 1.2.",
        ]
    }
    pre, art, art2 = blocs(pages)
    assert pre.est_preambule and pre.chemin[-1] == "Caractère de la zone"
    assert pre.zone == "UCe1" and pre.zone_libelle == "Centre ancien imbriqué"
    assert art.chemin[-3:] == [
        "CHAPITRE 1 - DESTINATION DES CONSTRUCTIONS, USAGE ET AFFECTATION DES SOLS",
        "1.1 - Les destinations interdites",
        "1.1.1 - Destinations interdites",
    ]
    # « a. Néant » est un élément de liste, pas la suite du titre.
    assert art.lignes == [(8, "a. Néant")]
    assert art2.chemin[-1] == "1.2 - Les destinations soumises à conditions"
    assert art2.zone_libelle == "Centre ancien imbriqué" and not art2.est_preambule


def test_cut_reference_and_other_chapter_numbers_are_not_articles():
    pages = {
        4: [
            "CHAPITRE 5 - DEPLACEMENTS",
            "5.2 - Stationnement",
            "Voir le paragraphe",
            "5.2.3 - ci-après.",
            "3.1 - Numéro d'un autre chapitre",
        ]
    }
    (bloc,) = blocs(pages)
    assert bloc.chemin[-1] == "5.2 - Stationnement"
    assert [t for _, t in bloc.lignes][1:] == [
        "5.2.3 - ci-après.",
        "3.1 - Numéro d'un autre chapitre",
    ]


def test_zone_without_character_line_has_no_label():
    pages = {11: ["Zone UPr1", "Zone qui assure la gestion", "du quartier.", "Rappels :", "Texte."]}
    (bloc,) = blocs(pages)
    assert bloc.zone == "UPr1" and bloc.zone_libelle is None and bloc.est_preambule
    assert bloc.lignes[0] == (11, "Zone qui assure la gestion")


def test_common_upr_provisions_have_no_zone():
    (bloc,) = blocs({10: ["1.1. Articulations des règles", "Texte commun."]})
    assert bloc.zone is None and bloc.chemin[-2:] == [
        "Dispositions communes",
        "1.1 - Articulations des règles",
    ]


LINES = [
    (10.0, 20.0, "Texte avant"),
    (50.0, 60.0, "Cellule A Cellule B"),
    (90.0, 95.0, "Texte après"),
]


def test_table_lines_are_replaced_by_docling_cells_in_place():
    docling = {"tableaux": [{"haut": 48.0, "lignes": ["Cellule A | Cellule B"]}], "page": ""}
    lines, from_docling, mode = rg.merge_tables(LINES, [(45.0, 65.0)], docling)
    assert lines == ["Texte avant", "Cellule A | Cellule B", "Texte après"]
    assert from_docling == {"Cellule A | Cellule B"} and mode == "tableaux"


def test_table_count_mismatch_reads_the_whole_page_with_docling():
    docling = {"tableaux": [], "page": "Texte avant\n| A | B |\nTexte après"}
    _, _, mode = rg.merge_tables(LINES, [(45.0, 65.0)], docling)
    assert mode == "page_docling"


def test_cells_dropped_by_docling_keep_the_pymupdf_text():
    docling = {"tableaux": [{"haut": 48.0, "lignes": ["Cellule A"]}], "page": ""}
    lines, from_docling, mode = rg.merge_tables(LINES, [(45.0, 65.0)], docling)
    assert mode == "pymupdf" and not from_docling and "Cellule A Cellule B" in lines


def test_table_rows_drop_separators_and_repeated_merged_cells():
    md = "| Zone | Zone | Norme |\n|---|---|---|\n| UCe1 | UCe1 | 1 place |"
    assert rg.table_rows(md) == ["Zone | Norme", "UCe1 | 1 place"]


def test_page_version_falls_back_to_previous_page():
    texts = {1: "PLU-H – MODIFICATION N° 4 – APPROBATION 2024", 2: "sans en-tête"}
    assert rg.page_versions(texts) == {1: V, 2: V}
    with pytest.raises(rg.ReglementError):
        rg.page_versions({1: "sans version"})


def test_sector_and_alias_payload():
    sectors = {"UCe3": ["UCe3a", "UCe3p"]}
    alias = {"UCe3p": [AliasCode(code_zonage="UCe3-p", code_reglement="UCe3p", statut="probable")]}
    payload = rg.sector_payload("En secteur UCe3p, la hauteur…", "UCe3", sectors, alias)
    assert payload["secteurs"] == ["UCe3p"] and payload["alias"][0].code_zonage == "UCe3-p"
    # Mot entier : « UCe3a1 » n'est pas le secteur UCe3a.
    assert rg.sector_payload("UCe3a1", "UCe3", sectors, alias) == {"secteurs": None, "alias": None}


def test_common_upr_provisions_apply_to_every_zone_of_the_group():
    pages = {10: ["Texte commun."], 11: ["Zone UPr1", "Texte."]}
    common, upr1 = blocs(pages)
    rg.apply_common_zones([common, upr1], rg.group_zones(TOC))
    assert common.zones_applicables == ["UPr1"] and upr1.zones_applicables == ["UPr1"]


NOMENCLATURE = {
    20: "0.2 - Nomenclature des zones et des secteurs de zones\nZones « projet »\nUPr1\n"
    "Zone qui assure la gestion du quartier de la Part-Dieu et de la Cité\n"
    "Internationale.\nCaractère multifonctionnel.\nUPr2\nZone de type « centralité ».\n",
    21: "0.3 - Règles applicables\n",
}


def test_missing_zone_label_comes_from_the_nomenclature_with_its_page():
    labels = rg.nomenclature_labels(NOMENCLATURE, ["UPr1", "UPr2"])
    assert labels["UPr1"] == (
        "Zone qui assure la gestion du quartier de la Part-Dieu et de la Cité Internationale.",
        20,
    )
    with pytest.raises(rg.ReglementError, match="nomenclature"):
        rg.nomenclature_labels(NOMENCLATURE, ["UPr9"])


def test_index_of_defined_terms_maps_printed_to_pdf_pages():
    texts = {
        114: "METROPOLE DE LYON – PLU-H – REGLEMENT – PARTIE I\n112\nINDEX\nA\n"
        "Accès du terrain ........ 91\nAires de mise en valeur de l’architecture et\n"
        "du patrimoine (AVAP) ......... 24\nOrientations d’aménagement et de programmation 24\n",
    }
    printed = {26: 24, 93: 91, 114: 112}
    assert rg.index_terms(texts, [114], printed) == [
        {"terme": "Accès du terrain", "page_imprimee": 91, "page_pdf": 93},
        {"terme": "Aires de mise en valeur de l’architecture et du patrimoine (AVAP)",
         "page_imprimee": 24, "page_pdf": 26},
        {"terme": "Orientations d’aménagement et de programmation", "page_imprimee": 24,
         "page_pdf": 26},
    ]  # fmt: skip
    assert rg.printed_numbers({8: "METROPOLE DE LYON\nPLU-H\n6\nTexte 12"}) == {8: 6}
    assert rg.index_term_pages(
        [(2, "CHAPITRE 6", 107), (2, "INDEX ", 114), (1, "Partie II", 117)], 803
    ) == [114, 115, 116]
