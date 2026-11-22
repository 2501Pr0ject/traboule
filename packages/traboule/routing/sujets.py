"""Sujets réglementaires d'une question : table fermée sujet → intitulés d'articles (ADR-0010).

Un sujet est repéré dans la question (texte normalisé) ; une réponse documentaire sur ce sujet
doit citer au moins un passage dont le chemin (intitulés du règlement) porte sur lui. Les
intitulés viennent du règlement écrit : 2.1 « Implantation des constructions par rapport aux
voies et aux emprises publiques ou privées », 2.2 « … par rapport aux limites séparatives »,
2.4 « Emprise au sol des constructions », 2.5 « Hauteur des constructions », 3.2.1 « Le
coefficient de pleine terre », 4.5 « Traitement des clôtures », chapitre 5 « Déplacements et
stationnement ». Un sujet absent de la table n'est pas contrôlé.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    name: str
    question: re.Pattern  # sur la question normalisée (`analyse.normalize`)
    titles: re.Pattern  # sur les intitulés normalisés du chemin d'un passage


def _topic(name: str, question: str, titles: str) -> Topic:
    return Topic(name, re.compile(question), re.compile(titles))


TOPICS: tuple[Topic, ...] = (
    _topic("emprise au sol", r"\bemprise au sol\b|\bces\b", r"\bemprise au sol\b"),
    _topic("pleine terre", r"\bpleine terre\b|\bcpt\b", r"\bpleine terre\b"),
    _topic(
        "hauteur",
        r"\bhauteurs?\b|\bgabarits?\b|\bvetc\b|\bnombre de niveaux\b",
        r"\bhauteur|\bgabarit|\bvolume enveloppe\b|\bvetc\b|\bcouronnement\b",
    ),
    _topic(
        "implantation par rapport aux voies",
        r"\bpar rapport aux voies\b|\balignement\b|\bemprises? publiques?\b",
        r"\bpar rapport aux voies\b|\bemprises? publiques\b",
    ),
    _topic("limites séparatives", r"\blimites? separatives?\b", r"\blimites? separatives?\b"),
    _topic("stationnement", r"\bstationnement\b|\bparkings?\b", r"\bstationnement\b"),
    _topic("clôtures", r"\bclotures?\b", r"\bclotures?\b"),
    _topic(
        "destinations",
        r"\badmis\w*|\badmet\b|\bautoris\w*|\binterdi\w*|\bdestinations?\b",
        r"\bdestinations?\b|\binterdit|\bautorise|\bsoumis\w* a conditions\b",
    ),
    _topic(
        "extension",
        r"\bextensions?\b",
        r"\bextension\b|\bdestinations?\b|\bregles? alternatives?\b",
    ),
)
BY_NAME = {t.name: t for t in TOPICS}


def detect(normalized_question: str) -> tuple[str, ...]:
    """Sujets de la table repérés dans la question normalisée."""
    return tuple(t.name for t in TOPICS if t.question.search(normalized_question))
