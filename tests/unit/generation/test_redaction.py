"""Client Ollama, budget de la fenêtre et vérification des citations."""

import json

import httpx
import pytest

from traboule.contracts.passage import Passage
from traboule.generation.llm_config import load_llm_config
from traboule.generation.ollama import ChatResult, OllamaClient, OllamaError
from traboule.generation.redaction import Contexte, document_title, draft, render

CONFIG = load_llm_config()


def passage(i: int, words: int = 10, **extra) -> Passage:
    fields = {
        "passage_id": f"p{i}",
        "texte": " ".join(["mot"] * words),
        "doc_id": "200046977_reglement_20260326.pdf",
        "source_id": "SRC-005",
        "version_piece": "Modification n°4 - Approbation 2024",
        "version_gpu": "200046977_PLUi_20260326",
        "page_debut": 600 + i,
        "page_fin": 600 + i,
        "chemin": ["Partie II", "Zone UEi1", f"Article {i}"],
        "extracteur": "pymupdf",
        "zone": "UEi1",
    }
    return Passage(**(fields | extra))


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


class FakeLlm:
    def __init__(self, answer: dict | str, config=CONFIG):
        self.config = config
        self.answer = answer
        self.calls = []

    def chat(self, strategy, system, user, schema=None):
        self.calls.append({"strategy": strategy, "system": system, "user": user})
        content = self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
        return ChatResult(content=content, prompt_tokens=42, seconds=1.0)


def test_ollama_client_sends_the_configured_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        body = {"message": {"content": "{}"}, "prompt_eval_count": 12, "total_duration": 2e9}
        return httpx.Response(200, json=body)

    client = OllamaClient(CONFIG, transport=httpx.MockTransport(handler))
    result = client.chat("cag", "consigne", "question", {"type": "object"})
    assert seen["model"] == "qwen3:8b" and seen["think"] is False and seen["stream"] is False
    assert seen["options"]["num_ctx"] == 20480 and seen["options"]["num_predict"] == 1024
    assert seen["messages"][0] == {"role": "system", "content": "consigne"}
    assert seen["format"] == {"type": "object"}
    assert (result.prompt_tokens, result.seconds) == (12, 2.0)


def test_ollama_errors_are_reported():
    client = OllamaClient(CONFIG, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(OllamaError, match="qwen3:8b"):
        client.chat("rag", "s", "u")


def test_verified_answer_cites_document_page_and_version():
    llm = FakeLlm({"reponse": "2 mètres.", "passages_cites": [2], "suffisant": True})
    c = draft(
        llm, WordCounter(), "rag", "Hauteur des clôtures ?", Contexte([passage(1), passage(2)])
    )
    assert not c.abstention and c.valeur == "2 mètres."
    (cit,) = c.citations
    assert (cit.doc_id, cit.page, cit.version_piece) == (
        "200046977_reglement_20260326.pdf",
        602,
        "Modification n°4 - Approbation 2024",
    )
    assert "[2] Règlement du PLU-H" in llm.calls[0]["system"]
    assert llm.calls[0]["user"] == "Hauteur des clôtures ?"


@pytest.mark.parametrize("cited", [[], [3], [0, 1]])
def test_citation_outside_the_context_is_refused(cited):
    llm = FakeLlm({"reponse": "x", "passages_cites": cited, "suffisant": True})
    c = draft(llm, WordCounter(), "rag", "q", Contexte([passage(1), passage(2)]))
    assert c.abstention and c.motif == "citation_non_verifiee"


def test_insufficient_or_unreadable_answers_abstain():
    llm = FakeLlm({"reponse": "Rien sur ce point.", "passages_cites": [], "suffisant": False})
    c = draft(llm, WordCounter(), "rag", "q", Contexte([passage(1)]))
    assert c.motif == "preuve_insuffisante" and "Rien sur ce point" in c.limites[0]
    c = draft(FakeLlm("pas du json"), WordCounter(), "rag", "q", Contexte([passage(1)]))
    assert c.motif == "citation_non_verifiee"


def test_trimmable_context_is_cut_to_the_budget():
    llm = FakeLlm({"reponse": "x", "passages_cites": [1], "suffisant": True})
    big = [passage(i, words=5000) for i in range(1, 6)]  # 5 × 5 000 mots, budget ≈ 15 000
    c = draft(llm, WordCounter(), "rag", "q", Contexte(big))
    assert not c.abstention
    assert "retirés faute de place" in " ".join(c.notes)
    assert llm.calls[0]["system"].count("Règlement du PLU-H —") == 3


def test_untrimmable_context_over_budget_abstains_without_calling_the_model():
    llm = FakeLlm({"reponse": "x", "passages_cites": [1], "suffisant": True})
    big = [passage(i, words=5000) for i in range(1, 6)]
    c = draft(llm, WordCounter(), "cag", "q", Contexte(big, trimmable=False))
    assert c.abstention and c.motif == "preuve_insuffisante" and "au-delà du budget" in c.texte
    assert llm.calls == []


def test_refusal_and_hybrid_note():
    llm = FakeLlm({"reponse": "x", "passages_cites": [1], "suffisant": True})
    c = draft(llm, WordCounter(), "cag", "q", Contexte([], refusal="Aucune zone identifiée."))
    assert c.abstention and c.texte == "Aucune zone identifiée." and llm.calls == []
    draft(llm, WordCounter(), "rag", "Combien et quelle règle ?", Contexte([passage(1)]), True)
    assert "partie réglementaire" in llm.calls[0]["user"]
    question = "Combien d'établissements en zone UEp, et le règlement y impose-t-il une règle ?"
    draft(llm, WordCounter(), "rag", question, Contexte([passage(1)]), True)
    user = llm.calls[-1]["user"]
    assert user.startswith("Le règlement y impose-t-il une règle ?") and question in user


def test_titles_of_cahiers():
    assert document_title("200046977_cahier_communal_SECT22_20260326.pdf") == (
        "Cahier communal (secteur 22)"
    )
    assert render(1, passage(1)).startswith("[1] Règlement du PLU-H — Partie II > Zone UEi1")
