"""Réparation des ligatures par vocabulaire du corpus (décision du porteur, 2026-11-01)."""

from collections import Counter

from traboule.retrieval.ligatures import repair, repair_unreadable, vocabulary

VOCAB = vocabulary(
    ["la partie nord, une partie sud, la partie haute."] * 1
    + ["création, création, création ; articulation articulation articulation"]
    + ["en tête du cortège ; le petit enfant ; parti politique"] * 5
)


def test_split_word_is_joined_when_intact_form_is_frequent():
    text, repairs = repair("la créati on de la Parti e nord", VOCAB)
    assert text == "la création de la Partie nord"
    assert repairs == Counter({("créati on", "création"): 1, ("Parti e", "Partie"): 1})


def test_three_fragments():
    text, _ = repair("une arti culati on", VOCAB)
    assert text == "une articulation"


def test_real_neighbouring_words_are_never_merged():
    for phrase in ["la partie nord", "en tête du cortège", "le petit enfant", "parti politique"]:
        assert repair(phrase, VOCAB) == (phrase, Counter())


def test_rare_form_is_not_joined():
    rare = vocabulary(["création création"])  # 2 occurrences < 3
    assert repair("la créati on", rare)[0] == "la créati on"


def test_only_fragments_ending_with_a_ligature_are_joined():
    vocab = vocabulary(["bonjour bonjour bonjour"])
    assert repair("bon jour", vocab)[0] == "bon jour"


def test_capitalised_continuation_is_not_joined():
    vocab = vocabulary(["bâtis bâtis bâtis"])
    assert repair("front bâti S", vocab)[0] == "front bâti S"
    assert repair("Bâti s", vocab)[0] == "Bâtis"


def test_punctuation_and_double_spaces_block_joining():
    assert repair("créati, on", VOCAB)[0] == "créati, on"
    assert repair("créati  on", VOCAB)[0] == "créati  on"


# Caractère illisible « � » (décision du porteur, 2026-11-02).
ILLISIBLE = vocabulary(["orientations orientations orientations ; bâti bâti bâti"])


def test_unreadable_replaced_when_one_ligature_fits_and_pymupdf_agrees():
    text, repairs = repair_unreadable("les Orienta� ons", ILLISIBLE, {"orientations"})
    assert text == "les Orientations"
    assert repairs == Counter({("Orienta� ons", "Orientations"): 1})
    # Mot suivant réel : seul le début est complété.
    assert repair_unreadable("bâ� côté", ILLISIBLE, {"bâti"})[0] == "bâti côté"


def test_unreadable_kept_when_two_ligatures_fit():
    vocab = vocabulary(["effet effet effet ; efiet efiet efiet"])  # « ff » et « fi »
    assert repair_unreadable("e� et", vocab, {"effet", "efiet"}) == ("e� et", Counter())


def test_unreadable_kept_when_form_is_absent_from_pymupdf():
    assert repair_unreadable("les Orienta� ons", ILLISIBLE, {"les"}) == (
        "les Orienta� ons",
        Counter(),
    )


def test_unreadable_kept_when_no_ligature_fits():
    assert repair_unreadable("x� y", ILLISIBLE, {"xti"})[0] == "x� y"
