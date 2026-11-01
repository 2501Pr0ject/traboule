"""Extraction des pièces PDF (ADR-0008) : ligatures, pages graphiques, nettoyage Docling."""

import pymupdf
import pytest

from traboule.retrieval import extraction as ex


def test_ligature_glyphs_and_their_spaces_are_repaired():
    text, n = ex.repair_ligatures("résidenƟ el, aﬃ  rmer, permeƩ ant")
    assert (text, n) == ("résidentiel, affirmer, permettant", 3)


@pytest.mark.parametrize(
    "chars,share,drawings,expected",
    [(100, 0.6, 0, True), (100, 0.1, 2500, True), (100, 0.1, 10, False), (400, 0.9, 0, False)],
)
def test_graphic_rule(chars, share, drawings, expected):
    assert ex.is_graphic(chars, share, drawings) is expected


def test_clean_markdown_counts_duplicates_and_drops_markup():
    md = "## Titre\n<!-- image -->\n| a | b |\n|---|---|\nLigne\nLigne\nrésidenƟ el\n\n"
    lines, duplicates, ligatures = ex.clean_markdown(md)
    assert lines == ["Titre", "| a | b |", "Ligne", "résidentiel"]
    assert (duplicates, ligatures) == (1, 1)


def synthetic_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "PLU-H - TEST - Modification n°4 - Approbation 2024\nTexte " * 20)
    graphic = doc.new_page()
    for i in range(2100):  # plus de 2 000 tracés et presque pas de texte : page graphique
        graphic.draw_line((10, 10 + i % 700), (500, 10 + i % 700))
    doc.set_toc([[1, "1. Rapport de présentation", 1], [1, "4. Orientations d'Aménagement", 2]])
    doc.save(path)
    return path


def test_read_pages_detects_graphic_page_and_toc(tmp_path):
    toc, pages = ex.read_pages(synthetic_pdf(tmp_path / "c.pdf"))
    assert [t[1] for t in toc] == ["1. Rapport de présentation", "4. Orientations d'Aménagement"]
    assert (pages[1].graphique, pages[2].graphique) == (False, True)


class FakeDoc:
    def export_to_markdown(self, page_no):
        return f"Ligne {page_no}\nLigne {page_no}"


class FakeConverter:
    def convert(self, path):
        return type("R", (), {"document": FakeDoc()})()


def test_docling_text_is_cleaned_and_graphic_pages_skipped(tmp_path):
    path = synthetic_pdf(tmp_path / "c.pdf")
    _, pages = ex.read_pages(path)
    ex.apply_docling(pages, ex.docling_markdown(FakeConverter(), path, len(pages)))
    assert (pages[1].lignes, pages[1].doublons_retires) == (["Ligne 1"], 1)
    assert pages[2].lignes == []
