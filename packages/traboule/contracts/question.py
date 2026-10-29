"""Question du jeu de référence : fait foi ; schema.json en est généré.

Les règles propres au jeu de référence (as_of, statut validated, gabarits, doublons) restent
dans scripts/validate_gold.py.
Régénérer le schéma : `uv run python scripts/generate_gold_schema.py`.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Route = Literal["SQL", "RAG", "HYBRID", "ABSTAIN"]


class Evidence(BaseModel):
    """Preuve : se lit par document, page, zone et chemin, pas par identifiant de passage."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    doc_id: str | None = None
    page: int | None = None
    passage_id: str | None = None
    zone_code: str | None = None
    note: str | None = None


class Question(BaseModel):
    """Question du jeu de référence (benchmarks/datasets/gold)."""

    model_config = ConfigDict(extra="forbid", title="Traboule gold question")

    id: str = Field(pattern=r"^(FAC|DOC|MIX|ABS)-[0-9]{3}$")
    dataset_version: str
    category: Literal["factual", "documentary", "mixed", "unanswerable"]
    subtype: str | None = Field(
        default=None,
        description=(
            "Pour unanswerable : near_miss_level, nonexistent_entity, out_of_version, "
            "masked_by_diffusion, out_of_corpus, future_value. Pour les autres : libre "
            "(count, filter, spatial, rule_lookup...)."
        ),
    )
    expected_route: Route
    question: str = Field(min_length=10)
    as_of: date = Field(description="Date d'ancrage de la question")
    source_versions: dict[str, str] = Field(
        description=(
            "source_id -> version ou date du fichier utilisé (ex. SRC-001a: 2026-10-01, "
            "SRC-005: identifiant de version GPU)"
        )
    )
    expected_answer: str | None = None
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description=(
            "Critères vérifiables : valeur exacte, tolérance, éléments obligatoires, "
            "abstention attendue"
        ),
    )
    expected_sql: str | None = Field(
        default=None, description="Requête de référence relue par l'humain"
    )
    expected_result: Any = Field(
        default=None,
        description=(
            "Résultat d'exécution de la requête de référence (comparaison par résultat, "
            "pas par texte) ; c'est la référence, la requête n'en est que la trace"
        ),
    )
    evidence: list[Evidence] = Field(default_factory=list)
    abstention_reason: str | None = Field(
        default=None,
        description=(
            "Pour unanswerable : pourquoi aucune réponse fiable n'est possible, et quelle "
            "information proche existe"
        ),
    )
    difficulty: Literal["easy", "medium", "hard"] | None = None
    status: Literal["draft", "validated", "rejected"]
    validated_by: str | None = None
    validated_at: date | None = None
    notes: str | None = None
