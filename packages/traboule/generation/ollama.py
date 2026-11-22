"""Client de l'API locale d'Ollama (`/api/chat`), paramétré par `configs/llm.yaml`."""

from dataclasses import dataclass
from typing import Any

import httpx

from traboule.generation.llm_config import LlmConfig, Strategy

TIMEOUT_S = 900.0  # préremplissage d'un chapitre de 18 k tokens : plusieurs minutes


class OllamaError(RuntimeError):
    """Serveur Ollama injoignable ou réponse inattendue."""


@dataclass(frozen=True)
class ChatResult:
    content: str
    # Tokens du prompt évalués par le modèle : un préfixe gardé en cache n'y figure pas.
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    seconds: float | None = None


class OllamaClient:
    def __init__(
        self, config: LlmConfig, transport: httpx.BaseTransport | None = None, timeout=TIMEOUT_S
    ) -> None:
        self.config = config
        self._http = httpx.Client(base_url=config.url, transport=transport, timeout=timeout)

    def chat(
        self, strategy: Strategy, system: str, user: str, schema: dict[str, Any] | None = None
    ) -> ChatResult:
        payload = {
            **self.config.ollama_request(strategy),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
        }
        if schema is not None:
            payload["format"] = schema
        try:
            response = self._http.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise OllamaError(
                f"Ollama ({self.config.url}, {self.config.model}) : {error}"
            ) from error
        total = data.get("total_duration")
        return ChatResult(
            content=content,
            prompt_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            seconds=round(total / 1e9, 1) if total else None,
        )

    def close(self) -> None:
        self._http.close()
