"""Commande `traboule` : `traboule ask "question" --strategie rag|cag|kag [--json]`."""

import os
import sys
from enum import StrEnum
from typing import Annotated

import typer

app = typer.Typer(add_completion=False, help="Questions sur la Métropole de Lyon (Traboule).")


class StrategyName(StrEnum):
    rag = "rag"
    cag = "cag"
    kag = "kag"


@app.callback()
def main() -> None:
    """Traboule : établissements, zonage du PLU-H et règlement écrit, réponses sourcées."""


@app.command()
def ask(
    question: str,
    strategie: Annotated[StrategyName, typer.Option(help="Construction du contexte")] = "rag",
    as_json: Annotated[bool, typer.Option("--json", help="Objet Reponse brut")] = False,
) -> None:
    """Répond à une question : route, valeurs, citations, abstention et motif."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from traboule.chaine.affichage import show
    from traboule.chaine.repondre import build_chain
    from traboule.generation.ollama import OllamaError

    chain = build_chain()
    try:
        reponse = chain.ask(question, strategie.value)
    except OllamaError as error:
        typer.echo(f"Génération impossible : {error}", err=True)
        sys.exit(1)
    finally:
        chain.close()
    if as_json:
        typer.echo(reponse.model_dump_json(indent=2))
    else:
        show(reponse)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Adresse d'écoute (locale par défaut)")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port")] = 8000,
) -> None:
    """Interface web minimale : une question, une stratégie, la réponse sourcée et sa route."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import uvicorn

    from traboule.chaine.repondre import build_chain
    from traboule.chaine.web import create_app

    typer.echo(f"Traboule : http://{host}:{port}")
    uvicorn.run(create_app(build_chain), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
