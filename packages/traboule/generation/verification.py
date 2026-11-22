"""Contrôles d'une réponse documentaire contre ses passages cités (ADR-0010).

- **Cohérence du sujet** : quand la question porte sur un sujet de la table fermée
  (`routing.sujets`), au moins un passage cité doit porter sur l'un de ses sujets d'après son
  chemin (intitulés du règlement) ; pour un passage sans intitulé d'article (cahier, OAP), le
  texte du passage en tient lieu.
- **Valeurs chiffrées** : chaque nombre de la réponse doit figurer dans au moins un passage
  cité, après normalisation des espaces (insécables compris), de la virgule décimale et des
  zéros décimaux. Un nombre suivi d'une unité de mesure (m, %, m², niveaux…) doit figurer dans
  le **texte** d'un passage cité ; un nombre sans unité peut aussi figurer dans son chemin
  (numéro d'article) ou dans la version de la pièce. Sont exemptés : les marqueurs de
  citation (`[1]`), les ordinaux (`1er`, `2e`) et les nombres repris de la question sans unité
  de mesure (ex. « NAF rév. 2 », « division 47 ») ; un nombre de la question suivi d'une unité
  (« 12 m ») reste à prouver par les passages.
"""

import re
from collections.abc import Sequence

from traboule.contracts.passage import Passage
from traboule.routing.analyse import normalize
from traboule.routing.sujets import Topic

SPACES = "\u00a0\u202f\u2009 "
NUMBER = re.compile(
    r"(?<![\w\[.,])(?:"
    r"(?P<ordinal>\d+)(?=(?:er|re|ère|e|ème|eme)\b)"
    rf"|(?P<value>\d{{1,3}}(?:[{SPACES}]\d{{3}})+(?![\d.,])|\d+(?:[.,]\d+)*(?!\d))"
    r")(?!\])"
)
UNIT = re.compile(
    rf"[{SPACES}]*(?:%|pour ?cent|m²|m2|m\b|mètres?|metres?|cm\b|km\b|ha\b|hectares?|"
    r"niveaux?|étages?|etages?)",
    re.IGNORECASE,
)


def canonical(number: str) -> str:
    """`10 000` → `10000` ; `0,50` → `0.5` ; `4,00` → `4` ; `2.4.1` inchangé."""
    n = re.sub(rf"[{SPACES}]", "", number).replace(",", ".")
    if n.count(".") == 1:
        n = n.rstrip("0").rstrip(".")
    return n


def numbers(text: str) -> list[tuple[str, bool]]:
    """Nombres d'un texte (forme canonique), chacun avec « suivi d'une unité de mesure »."""
    return [
        (canonical(m.group("value")), bool(UNIT.match(text, m.end())))
        for m in NUMBER.finditer(text)
        if m.group("value")
    ]


def unsupported_values(answer: str, question: str, cited: Sequence[Passage]) -> list[str]:
    """Nombres de la réponse absents des passages cités (exemptions : voir le module)."""
    exempt = {n for n, unit in numbers(question) if not unit}
    in_text = {n for p in cited for n, _ in numbers(p.texte)}
    in_meta = {n for p in cited for t in (" ".join(p.chemin), p.version_piece)
               for n, _ in numbers(t)}  # fmt: skip
    missing = [
        n
        for n, unit in numbers(answer)
        if n not in in_text and (unit or (n not in in_meta and n not in exempt))
    ]
    return list(dict.fromkeys(missing))


def on_topic(topics: Sequence[Topic], cited: Sequence[Passage]) -> bool:
    """Vrai si aucun sujet n'est demandé, ou si un passage cité porte sur l'un d'eux."""
    if not topics:
        return True
    for p in cited:
        is_rule = "reglement" in p.doc_id
        where = normalize(" ".join(p.chemin) if is_rule else " ".join([*p.chemin, p.texte]))
        if any(t.titles.search(where) for t in topics):
            return True
    return False
