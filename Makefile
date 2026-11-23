.PHONY: setup lint test validate-gold download build

# Sources lues par la construction (configs/sources.yaml).
SOURCES = SRC-001a SRC-001b SRC-002 SRC-004a SRC-004b SRC-004c SRC-005 \
          REF-COMMUNES-ML-2024 REF-ARRONDISSEMENTS-LYON
# make build FORCE=1 : transmet --force aux étapes qui l'acceptent (voir build).
FORCE_FLAG = $(if $(FORCE),--force,)

setup:            ## Installe l'environnement complet (extras pdf, embeddings, index, generation, web + dev)
	uv sync --all-extras

lint:
	uv run ruff check . && uv run ruff format --check .

test:
	uv run pytest -q

validate-gold:    ## Valide benchmarks/datasets/gold/*.jsonl contre schema.json
	uv run python scripts/validate_gold.py

download:         ## Télécharge les 9 sources dans data/raw (relançable : les ressources présentes sont gardées)
	@for source in $(SOURCES); do \
		uv run python -m traboule.ingestion.download $$source || exit 1; \
	done

# Quand les sorties existent déjà :
# - référentiel, Sirene, jointure, base : l'étape s'arrête en erreur, sauf avec FORCE=1 ;
# - correspondance zones → règlement : contrôle seul, n'écrit rien ;
# - règlement, cahiers : passages toujours réécrits ; l'extraction (Docling, tableaux) d'un
#   PDF inchangé (même sha256) est reprise du cache, sauf avec FORCE=1 ;
# - ligatures, renvois : passages toujours réécrits depuis l'extraction ;
# - index : toujours supprimé puis reconstruit.
build:            ## Construit données, base et index, dans l'ordre (s'arrête à la première erreur)
	uv run python -m traboule.geo.referentiel $(FORCE_FLAG)
	uv run python -m traboule.ingestion.sirene $(FORCE_FLAG)
	uv run python -m traboule.geo.jointure $(FORCE_FLAG)
	uv run python -m traboule.geo.zones_reglement --check
	uv run python -m traboule.ingestion.database $(FORCE_FLAG)
	uv run python -m traboule.retrieval.reglement $(FORCE_FLAG)
	uv run python -m traboule.retrieval.cahiers $(FORCE_FLAG)
	uv run python -m traboule.retrieval.ligatures
	uv run python -m traboule.retrieval.renvois
	uv run python -m traboule.retrieval.index build
