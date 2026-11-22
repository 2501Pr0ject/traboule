"""Interface web minimale (FastAPI) : une question, une stratégie, la réponse sourcée et sa route.

Usage : `traboule serve` puis http://127.0.0.1:8000. Le serveur garde la chaîne chargée (base,
index, modèles) et traite une question à la fois : un seul modèle de génération local, un
seul client de l'index embarqué.
"""

import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from traboule.chaine.repondre import Chain
from traboule.generation.ollama import OllamaError
from traboule.generation.redaction import document_title

DEMO_QUESTIONS = [
    "Combien d'établissements actifs sont situés en zone UEi1 à Vénissieux ?",
    "Quelle est la hauteur maximale des clôtures sur limite séparative en zone UEi1 ?",
    "Combien d'établissements d'entreposage (52.10, NAF rév. 2) sont situés en zone UEi2, et "
    "le règlement permet-il l'extension de leurs bâtiments ?",
    "Quelle part des établissements actifs de la Métropole de Lyon fait l'objet d'une diffusion "
    "partielle ?",
    "Que prévoit le règlement pour la zone UEi3 ?",
]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    strategie: Literal["rag", "cag", "kag"] = "rag"


def create_app(chain_factory: Callable[[], Chain]) -> FastAPI:
    lock = threading.Lock()
    state: dict[str, Chain] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if "chain" in state:
            state["chain"].close()

    app = FastAPI(title="Traboule", docs_url=None, redoc_url=None, lifespan=lifespan)

    def chain() -> Chain:
        if "chain" not in state:
            state["chain"] = chain_factory()
        return state["chain"]

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return files("traboule.chaine").joinpath("static/index.html").read_text(encoding="utf-8")

    @app.get("/api/exemples")
    def examples() -> list[str]:
        return DEMO_QUESTIONS

    @app.post("/api/ask")
    def ask(request: AskRequest) -> dict:
        with lock:
            try:
                reponse = chain().ask(request.question, request.strategie)
            except OllamaError as error:
                raise HTTPException(503, f"Génération impossible : {error}") from error
            carte = chain().map_for(request.question, reponse)
        data = reponse.model_dump(mode="json")
        data["carte"] = carte
        for component in data["composantes"]:
            for citation in component["citations"]:
                citation["titre"] = document_title(citation["doc_id"])
        return data

    return app
