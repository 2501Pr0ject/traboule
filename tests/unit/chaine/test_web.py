"""Interface web minimale : page, exemples, réponse sourcée et erreurs du modèle."""

import pytest

pytest.importorskip("fastapi")
# Imports après le saut : fastapi vient de l'extra « web » (E402 attendu).
from fastapi.testclient import TestClient  # noqa: E402
from test_repondre import FakeSearch, chain, passage  # noqa: E402

from traboule.chaine.web import create_app  # noqa: E402
from traboule.generation.ollama import OllamaError  # noqa: E402


def test_page_and_examples(con):
    with TestClient(create_app(lambda: chain(con, FakeSearch([passage(1)])))) as client:
        page = client.get("/")
        assert page.status_code == 200 and "<title>Traboule</title>" in page.text
        assert any("UEi1" in q for q in client.get("/api/exemples").json())


def test_answer_with_route_strategy_and_citation_titles(con):
    with TestClient(create_app(lambda: chain(con, FakeSearch([passage(1)])))) as client:
        question = "Combien d'établissements actifs en zone UEi1, et quelle règle s'y applique ?"
        r = client.post("/api/ask", json={"question": question, "strategie": "rag"})
        assert r.status_code == 200
        data = r.json()
        assert data["route"] == "HYBRID" and data["strategie"] == "rag"
        (cit,) = data["composantes"][1]["citations"]
        assert cit["titre"] == "Règlement du PLU-H" and cit["page"] == 621
        assert cit["version_piece"] == "Modification n°4 - Approbation 2024"


def test_invalid_request_and_model_error(con):
    c = chain(con, FakeSearch([passage(1)]))

    def broken(*args, **kwargs):
        raise OllamaError("serveur arrêté")

    c.llm.chat = broken
    with TestClient(create_app(lambda: c)) as client:
        assert (
            client.post("/api/ask", json={"question": "x", "strategie": "rag"}).status_code == 422
        )
        bad = client.post("/api/ask", json={"question": "Quelle règle ?", "strategie": "graphrag"})
        assert bad.status_code == 422
        r = client.post("/api/ask", json={"question": "Quelle hauteur en zone UEi1 ?"})
        assert r.status_code == 503 and "serveur arrêté" in r.json()["detail"]


def test_map_only_when_the_answer_concerns_a_zone(con):
    with TestClient(create_app(lambda: chain(con, FakeSearch([passage(1)])))) as client:
        commune = client.post(
            "/api/ask", json={"question": "Combien d'établissements actifs à Vénissieux ?"}
        ).json()
        assert commune["route"] == "SQL" and commune["carte"] is None
        zone = client.post(
            "/api/ask",
            json={"question": "Combien d'établissements actifs en zone UEi1 à Vénissieux ?"},
        ).json()
        assert zone["carte"]["html"].startswith("<!DOCTYPE html>")
        assert "sont géolocalisés dans la zone" in zone["carte"]["minorant"]
        assert "certains pourraient se trouver dans la zone" in zone["carte"]["minorant"]
        assert "00000000000001" not in zone["carte"]["html"]
