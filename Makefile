.PHONY: setup spike-setup lint test validate-gold

setup:            ## Installe l'environnement de base
	uv sync

spike-setup:      ## Ajoute les dépendances du spike (PDF, embeddings, Qdrant)
	uv sync --extra spike

lint:
	uv run ruff check . && uv run ruff format --check .

test:
	uv run pytest -q

validate-gold:    ## Valide benchmarks/datasets/gold/*.jsonl contre schema.json
	uv run python scripts/validate_gold.py
