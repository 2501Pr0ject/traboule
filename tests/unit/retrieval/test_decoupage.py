"""Découpage en passages avec les pages réelles de chaque passage."""

import pytest

from traboule.retrieval import decoupage as de


def test_split_long_at_sentence_boundaries():
    chunks = de.split_long("Phrase une. " * 300, max_chars=500)
    assert all(len(c) <= 500 for c in chunks) and len(chunks) > 1


def test_each_chunk_carries_the_pages_of_its_own_lines():
    lines = [
        (p, f"Phrase de la page {p}, assez longue pour remplir un morceau.") for p in range(7, 27)
    ]
    chunks = de.split_block(lines, max_chars=200)
    assert len(chunks) > 1
    assert chunks[0].page_debut == 7 and chunks[-1].page_fin == 26
    assert all(c.pages <= 4 for c in chunks)
    # Les morceaux se suivent sans perte de texte.
    assert " ".join(c.texte for c in chunks) == " ".join(t for _, t in lines)


def test_short_block_keeps_its_range():
    chunks = de.split_block([(3, "Une phrase."), (4, "Une autre.")])
    assert [(c.texte, c.page_debut, c.page_fin) for c in chunks] == [
        ("Une phrase. Une autre.", 3, 4)
    ]


def test_chunks_repeating_the_whole_block_range_are_refused(monkeypatch):
    # Découpage qui ignorerait les pages : chaque morceau reprend la plage du bloc.
    monkeypatch.setattr(de, "chunk_spans", lambda text, max_chars: [(0, len(text))] * 2)
    with pytest.raises(de.DecoupageError, match="plage entière"):
        de.split_block([(1, "Première page."), (2, "Seconde page.")])


def test_long_ranges_are_reported():
    chunks = [de.Chunk("a", 1, 4), de.Chunk("b", 5, 9)]
    assert de.long_ranges(chunks, max_pages=4) == [chunks[1]]


def test_text_without_sentence_end_is_split_at_paragraphs():
    # Listes à puces sans ponctuation finale : 30 lignes de 100 caractères sur une page.
    lines = [(1, "x" * 99 + f"{i % 10}") for i in range(30)]
    chunks = de.split_block(lines, max_chars=2000, text_pages={1})
    assert len(chunks) == 2 and all(len(c.texte) <= 2000 for c in chunks)
    assert " ".join(c.texte for c in chunks) == " ".join(t for _, t in lines)
    # Sans les pages de texte, la règle n'est pas appliquée (texte d'un seul tenant).
    assert len(de.split_block(lines, max_chars=2000)) == 1


def test_many_text_pages_are_split_but_maps_are_not():
    lines = [(p, f"Paragraphe de la page {p}") for p in range(1, 6)]
    # Cinq pages de texte : redécoupé pour ne pas dépasser trois pages de texte.
    chunks = de.split_block(lines, text_pages={1, 2, 3, 4, 5})
    assert [(c.page_debut, c.page_fin) for c in chunks] == [(1, 3), (4, 5)]
    # Pages 2 à 4 : cartes et légendes (pas des pages de texte) : le passage reste entier.
    kept = de.split_block(lines, text_pages={1, 5})
    assert [(c.page_debut, c.page_fin) for c in kept] == [(1, 5)]


def test_text_pages_exclude_graphic_and_short_pages():
    from types import SimpleNamespace as P

    pages = {
        1: P(graphique=False, caracteres=400),
        2: P(graphique=False, caracteres=399),
        3: P(graphique=True, caracteres=900),
    }
    assert de.text_page_numbers(pages) == {1}
