"""Stratégie CAG : chapitre de zone, ou OAP, préchargé en entier, avec cache explicite (ADR-0014).

- contexte : tous les passages du chapitre de la zone (`zones_applicables`, dispositions
  communes UPr comprises), dans l'ordre du document, **sans** les passages de la partie I :
  les renvois y sont cités par leur titre (décision du porteur, 2026-11-22) ; ou tous les
  passages d'une OAP citée par son numéro ;
- non tronquable : un contexte au-delà du budget de la fenêtre (`num_ctx` du CAG moins la réponse)
  entraîne l'abstention, sans repli silencieux sur le RAG ; sans zone ni OAP, abstention ;
- cache : la clé est l'empreinte du modèle, de la fenêtre, et des identifiants et textes des
  passages et de leur rendu ; elle change dès que la pièce, son texte ou le rendu change
  (invalidation). Le fichier
  `data/interim/cache_cag/<clé>.json` garde le contexte préparé (passages, tokens, date) et
  compte ses réutilisations. Consigne et chapitre forment un préfixe identique d'une question
  à l'autre : le serveur Ollama en garde l'état et n'évalue que la question (un seul préfixe
  à la fois par modèle chargé).
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from traboule.chaine.contexte import Corpus, renvois_notes
from traboule.config import INTERIM_DIR
from traboule.contracts.passage import Passage
from traboule.generation.redaction import Contexte, blocks, context_tokens
from traboule.generation.tokens import TokenCounter
from traboule.routing.analyse import Analysis

CACHE_DIR = INTERIM_DIR / "cache_cag"


def cache_key(model: str, window: int, passages: list[Passage]) -> str:
    """Empreinte du contexte tel qu'envoyé : modèle, fenêtre, identifiants et texte rendu."""
    content = json.dumps([model, window, [p.passage_id for p in passages], blocks(passages)])
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class CagStrategy:
    name = "cag"

    def __init__(
        self,
        corpus: Corpus,
        counter: TokenCounter,
        model: str,
        window: int,
        cache_dir: Path = CACHE_DIR,
    ) -> None:
        self.corpus = corpus
        self.counter = counter
        self.model = model
        self.window = window
        self.cache_dir = cache_dir

    def select(self, analysis: Analysis, zones: list[str]) -> tuple[str, list[Passage]]:
        if zones:
            return "chapitre " + " + ".join(zones), self.corpus.of_zones(zones)
        if analysis.oap:
            communes = {p.code for p in analysis.places}
            return f"OAP {analysis.oap}", self.corpus.of_oap(analysis.oap, communes)
        return "", []

    def _entry(self, key: str, label: str, passages: list[Passage]) -> tuple[dict, bool]:
        path = self.cache_dir / f"{key}.json"
        created = not path.exists()
        if created:
            tokens = sum(context_tokens(passages, self.counter))
            entry = {
                "cle": key,
                "contexte": label,
                "modele": self.model,
                "fenetre": self.window,
                "passages": [p.passage_id for p in passages],
                "tokens": tokens,
                "prepare_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "utilisations": 0,
            }
        else:
            entry = json.loads(path.read_text(encoding="utf-8"))
        entry["utilisations"] += 1
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
        return entry, created

    def build(self, analysis: Analysis, zones: list[str]) -> Contexte:
        label, passages = self.select(analysis, zones)
        if not label:
            refusal = "Le CAG demande une zone ou une OAP citée dans la question : aucune trouvée."
            return Contexte([], trimmable=False, refusal=refusal)
        if not passages:
            return Contexte([], trimmable=False, refusal=f"Aucun passage pour le {label}.")
        key = cache_key(self.model, self.window, passages)
        entry, created = self._entry(key, label, passages)
        state = "préparé" if created else f"réutilisé ({entry['utilisations']}e utilisation)"
        notes = [
            f"CAG : {label} en entier ({len(passages)} passages, {entry['tokens']} tokens), "
            f"sans les passages de la partie I ; cache {key} {state}"
        ]
        notes += renvois_notes(passages, {p.passage_id for p in passages})
        return Contexte(passages, trimmable=False, notes=notes)
