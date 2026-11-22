"""Configuration du modèle de génération (`configs/llm.yaml`, ADR-0014).

Les champs reprennent les noms de l'API d'Ollama. Toute clé inconnue est refusée : une faute
de frappe dans une option serait ignorée par Ollama et casserait la reproductibilité.
"""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError

from traboule.config import LLM_CONFIG

Strategy = Literal["rag", "cag", "kag"]


class LlmConfigError(ValueError):
    """Configuration du modèle de génération invalide."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Options(_Strict):
    temperature: float = Field(ge=0)
    seed: int
    num_predict: PositiveInt


class ContextWindows(_Strict):
    rag: PositiveInt
    cag: PositiveInt
    kag: PositiveInt


class LlmConfig(_Strict):
    url: str = Field(pattern=r"^https?://")
    model: str = Field(min_length=1)
    tokenizer: str = Field(min_length=1)
    think: bool
    keep_alive: str = Field(min_length=1)
    options: Options
    num_ctx: ContextWindows

    def input_budget(self, strategy: Strategy) -> int:
        """Tokens disponibles pour le prompt : fenêtre moins le plafond de la réponse."""
        return getattr(self.num_ctx, strategy) - self.options.num_predict

    def ollama_request(self, strategy: Strategy) -> dict[str, Any]:
        """Champs communs d'une requête Ollama pour une stratégie (sans messages ni prompt)."""
        return {
            "model": self.model,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "options": {**self.options.model_dump(), "num_ctx": getattr(self.num_ctx, strategy)},
        }


def load_llm_config(path: Path = LLM_CONFIG) -> LlmConfig:
    """Lit et valide configs/llm.yaml."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return LlmConfig.model_validate(data)
    except ValidationError as error:
        raise LlmConfigError(f"{path} : {error}") from error
