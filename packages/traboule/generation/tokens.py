"""Comptage des tokens du modèle de génération, avant tout envoi (budget de la fenêtre).

Le tokenizer est celui du modèle (`tokenizer` de `configs/llm.yaml`), lu dans le cache
Hugging Face, téléchargé seulement s'il en est absent ; ses comptes sont identiques à ceux
d'Ollama (`prompt_eval_count`, contrôle consigné dans l'ADR-0014).
"""

from typing import Protocol


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class HfTokenCounter:
    def __init__(self, repo: str) -> None:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import LocalEntryNotFoundError
        from tokenizers import Tokenizer

        try:
            path = hf_hub_download(repo, "tokenizer.json", local_files_only=True)
        except LocalEntryNotFoundError:
            path = hf_hub_download(repo, "tokenizer.json")
        self._tokenizer = Tokenizer.from_file(path)

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)
