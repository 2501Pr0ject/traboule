"""Index Qdrant des passages : sélection, en-tête contextuel, identifiants, recherche filtrée."""

from types import SimpleNamespace

import pytest

from traboule.contracts.passage import AliasCode, Passage
from traboule.retrieval import index as ix

BASE = {
    "source_id": "SRC-005",
    "version_piece": "Modification n°4 - Approbation 2024",
    "version_gpu": "200046977_PLUi_20260326",
    "page_debut": 1,
    "page_fin": 1,
    "extracteur": "pymupdf",
}


def passage(pid, **kw):
    fields = {"passage_id": pid, "texte": "Texte.", "doc_id": "reglement.pdf", "chemin": ["P"]}
    return Passage(**(BASE | fields | kw))


def write(folder, passages):
    folder.mkdir(parents=True)
    (folder / "passages.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in passages))


def test_excluded_resources_are_left_out_and_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(ix, "REGLEMENT_DIR", tmp_path / "reglement")
    monkeypatch.setattr(ix, "CAHIERS_DIR", tmp_path / "cahiers")
    write(tmp_path / "reglement", [passage("r1")])
    write(tmp_path / "cahiers" / "cahier_a", [passage("a1", doc_id="a.pdf")])
    write(tmp_path / "cahiers" / "cahier_b", [passage("b1", doc_id="b.pdf")] * 2)
    passages, excluded = ix.load_passages({"cahier_b": "Doublon"})
    assert [p.passage_id for p in passages] == ["r1", "a1"] and excluded == {"cahier_b": 2}
    with pytest.raises(ix.IndexBuildError, match="double"):
        ix.load_passages({})


def test_reglement_header_carries_zone_label_path_and_probable_alias():
    p = passage(
        "r1",
        zone="UCe3",
        zone_libelle="Faubourg",
        zones_applicables=["UCe3"],
        chemin=["Partie II", "Zone UCe3", "CHAPITRE 2 - MORPHOLOGIE"],
        secteurs=["UCe3p"],
        alias=[AliasCode(code_zonage="UCe3-p", code_reglement="UCe3p", statut="probable")],
    )
    assert ix.contextual_header(p, {}) == (
        "Règlement du PLU-H | Zone UCe3 (Faubourg) | Partie II > Zone UCe3 > CHAPITRE 2 - "
        "MORPHOLOGIE | Secteurs : UCe3p (correspondance de code probable : UCe3-p)"
    )


def test_common_provisions_header_lists_the_applicable_zones():
    p = passage("r2", zones_applicables=["UPr1", "UPr2"], chemin=["Dispositions communes"])
    assert ix.contextual_header(p, {}).startswith("Règlement du PLU-H | Zones UPr1, UPr2 |")


def test_cahier_header_names_the_place_or_the_shared_piece():
    cahier = {
        "doc_id": "200046977_cahier_arrondissement_SECT33_20260326.pdf",
        "secteur_pluh": "33",
        "code_commune_cog2026": "69123",
        "commune_historique": "69383",
        "oap": "OAP 3.2 Clinique",
        "chemin": ["4. OAP", "OAP 3.2 Clinique"],
    }
    names = {"69383": "Lyon 3e Arrondissement"}
    assert ix.contextual_header(passage("c1", **cahier), names) == (
        "Cahier d'arrondissement : Lyon 3e Arrondissement | 4. OAP > OAP 3.2 Clinique"
    )
    shared = passage(
        "c2",
        doc_id="lyon.pdf",
        secteurs_pluh=["31", "32"],
        code_commune_cog2026="69123",
        commune_historique="69123",
        titre_piece="Cahier communal de Lyon (identique pour les secteurs 31 à 39)",
    )
    assert ix.contextual_header(shared, names).startswith("Cahier communal de Lyon (identique")


def test_point_ids_are_stable_and_distinct():
    assert ix.point_id("abc") == ix.point_id("abc") != ix.point_id("abd")


class FakeModels:
    SparseVector = staticmethod(lambda indices, values: (indices, values))
    Filter = staticmethod(lambda must: ("filtre", must))
    FieldCondition = staticmethod(lambda key, match: (key, match))
    MatchAny = staticmethod(lambda any: tuple(any))
    Prefetch = staticmethod(lambda **kw: kw)
    FusionQuery = staticmethod(lambda fusion: fusion)
    Fusion = SimpleNamespace(RRF="rrf")


def test_sparse_vector_is_sorted_by_token_id():
    assert ix.sparse_vector(FakeModels, {"7": 0.5, "2": 0.1}) == ([2, 7], [0.1, 0.5])


def test_search_filters_both_prefetches_on_applicable_zones():
    class Model:
        def encode(self, texts, **kw):
            return {"dense_vecs": [SimpleNamespace(tolist=lambda: [0.1])],
                    "lexical_weights": [{"3": 1.0}]}  # fmt: skip

    calls = {}

    class Client:
        def query_points(self, collection, **kw):
            calls.update(kw, collection=collection)
            return SimpleNamespace(points=["p"])

    assert ix.search(Client(), Model(), FakeModels, "c", "hauteur", ["UEi1"]) == ["p"]
    expected = ("filtre", [("zones_applicables", ("UEi1",))])
    assert all(p["filter"] == expected for p in calls["prefetch"])
    assert calls["query"] == "rrf" and calls["limit"] == ix.TOP_K
    ix.search(Client(), Model(), FakeModels, "c", "hauteur", None)
    assert all(p["filter"] is None for p in calls["prefetch"])
