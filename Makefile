.PHONY: setup lint test validate-gold

setup:            ## Installe l'environnement complet (extras pdf, embeddings, index + dev)
	uv sync --all-extras

lint:
	uv run ruff check . && uv run ruff format --check .

test:
	uv run pytest -q

validate-gold:    ## Valide benchmarks/datasets/gold/*.jsonl contre schema.json
	uv run python scripts/validate_gold.py
