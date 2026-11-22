"""Analyse déterministe d'une question, sans modèle (ADR-0010, ADR-0014).

Repérages : codes de zone du zonage et chapitres du règlement, communes et arrondissements
(COG 2026), activité NAF rév. 2 (section, division, groupe, classe, sous-classe, ou terme d'un
lexique fermé), mesure demandée (comptage, part, répartition), besoin réglementaire, dates,
secteur sauvegardé, numéro d'OAP. Une activité citée mais non reconnue est signalée : le
routeur s'abstient plutôt que de compter sans filtre.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from traboule.routing.sujets import detect

Measure = Literal["count", "share", "distribution"]
Niveau = Literal["commune", "arrondissement_municipal"]
NafLevel = Literal["section", "division", "groupe", "classe", "sous_classe"]

# Sections de la NAF rév. 2 : première et dernière division, libellé (nomenclature INSEE).
NAF_SECTIONS: dict[str, tuple[int, int, str]] = {
    "A": (1, 3, "agriculture, sylviculture et pêche"),
    "B": (5, 9, "industries extractives"),
    "C": (10, 33, "industrie manufacturière"),
    "D": (35, 35, "production et distribution d'électricité, de gaz, de vapeur et d'air"),
    "E": (36, 39, "eau, assainissement, gestion des déchets et dépollution"),
    "F": (41, 43, "construction"),
    "G": (45, 47, "commerce ; réparation d'automobiles et de motocycles"),
    "H": (49, 53, "transports et entreposage"),
    "I": (55, 56, "hébergement et restauration"),
    "J": (58, 63, "information et communication"),
    "K": (64, 66, "activités financières et d'assurance"),
    "L": (68, 68, "activités immobilières"),
    "M": (69, 75, "activités spécialisées, scientifiques et techniques"),
    "N": (77, 82, "activités de services administratifs et de soutien"),
    "O": (84, 84, "administration publique"),
    "P": (85, 85, "enseignement"),
    "Q": (86, 88, "santé humaine et action sociale"),
    "R": (90, 93, "arts, spectacles et activités récréatives"),
    "S": (94, 96, "autres activités de services"),
    "T": (97, 98, "activités des ménages en tant qu'employeurs"),
    "U": (99, 99, "activités extra-territoriales"),
}

# Lexique fermé : terme (normalisé) → code NAF rév. 2. Un terme absent n'est jamais deviné.
ACTIVITY_TERMS: dict[str, tuple[NafLevel, str, str]] = {
    "industrie": ("section", "C", "industrie manufacturière"),
    "industries": ("section", "C", "industrie manufacturière"),
    "industriel": ("section", "C", "industrie manufacturière"),
    "industriels": ("section", "C", "industrie manufacturière"),
    "commerce de detail": ("division", "47", "commerce de détail"),
    "commerces de detail": ("division", "47", "commerce de détail"),
    "commerce de gros": ("division", "46", "commerce de gros"),
    "commerces de gros": ("division", "46", "commerce de gros"),
    "entreposage": ("classe", "52.10", "entreposage et stockage"),
    "restaurant": ("classe", "56.10", "restaurants et services de restauration mobile"),
    "restaurants": ("classe", "56.10", "restaurants et services de restauration mobile"),
    "hotel": ("classe", "55.10", "hôtels et hébergement similaire"),
    "hotels": ("classe", "55.10", "hôtels et hébergement similaire"),
    "pharmacie": ("sous_classe", "47.73Z", "commerce de détail de produits pharmaceutiques"),
    "pharmacies": ("sous_classe", "47.73Z", "commerce de détail de produits pharmaceutiques"),
}

MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}  # fmt: skip

RULE_WORDS = re.compile(
    r"\b(regles?|reglement\w*|prevoi\w*|prevu\w*|conditions?|admis\w*|admet\w*|autoris\w*|"
    r"interdi\w*|hauteurs?|emprise|coefficients?|pleine terre|clotures?|recul\w*|"
    r"implantation\w*|stationnement\w*|extensions?|destinations?|s appliqu\w*|impos\w*|"
    r"permet\w*|toitures?|plu h|oap|amenagement\w*|constructib\w*|gabarits?|"
    r"espaces? libres?|que dit|dispositions?)\b"
)
SHARE = re.compile(r"\b(quelle part|quel pourcentage|quelle proportion|pourcentage|proportion)\b")
DISTRIBUTION = re.compile(r"\b(repartissent|repartition|reparti\w*|par zone|ventil\w*)\b")
COUNT = re.compile(r"\b(combien|nombre|denombre\w*|compte t on)\b")
PARTIAL = re.compile(r"\b(diffusion partielle|statut p|non diffusibles?)\b")
CLOSED = re.compile(r"\b(fermes?|cesses?|radies?)\b")
SAFEGUARDED = re.compile(r"\b(vieux lyon|secteur sauvegarde|psmv|sectsauv)\b")
NOT_A_PLACE = re.compile(r"\b(metropole de lyon|grand lyon|vieux lyon)\b")
ARRONDISSEMENT = re.compile(
    r"\b(?:([1-9])\s*(?:er|e|eme|ieme)?\s+arrondissement(?:\s+de\s+lyon)?|"
    r"lyon\s+([1-9])\s*(?:er|e|eme)?(?:\s+arrondissement)?)\b"
)
OAP_NUMBER = re.compile(r"\boap\s+(\d+(?:\.\d+)?)\b")
DATE = re.compile(r"\b(?:(1er|\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+)?((?:19|20)\d{2})\b")
TOKEN = re.compile(r"(?<![\w.-])([A-Z][A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)?)(?![\w-])")
PLAUSIBLE_ZONE = re.compile(r"^(?:AU|U|A|N)[A-Z]{0,2}[a-z]{0,3}\d+[a-z]?$")
STECAL_NUMBER = re.compile(r"^([A-Z]+\d+s)\d+$")
NAF_SECTION = re.compile(r"\bsection\s+([A-U])\b")
NAF_DIVISION = re.compile(r"\bdivision\s+(\d{2})\b")
NAF_GROUP = re.compile(r"\bgroupe\s+(\d{2}\.\d)\b")
NAF_CLASS = re.compile(r"(?<![\d,.])(\d{2}\.\d{2})([A-Z])?(?![\d.])")
COUNTED = re.compile(r"\bcombien\s+(?:de|d)\s+(\w+)")
AFTER_ESTABLISHMENTS = re.compile(r"\betablissements?\s+((?:\w+\s+){0,3})")
NEUTRAL_FOLLOWERS = {
    "actifs", "actif", "fermes", "ferme", "situes", "recenses", "implantes", "presents",
    "sont", "en", "dans", "a", "au", "aux", "relevant", "qui", "sur", "y", "compte",
    "comptait", "inscrits", "enregistres", "localises", "geolocalises", "et", "ont", "se",
}  # fmt: skip
ARTICLES = {"la", "le", "les", "l"}
STOPPING_FOLLOWERS = {
    "sont", "est", "etait", "etaient", "fait", "font", "representent", "en", "dans", "a", "au",
    "aux", "qui", "relevant", "ont", "se", "y", "pour", "par", "selon", "entre",
}  # fmt: skip
STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du", "d", "elle", "en", "est",
    "et", "il", "la", "le", "les", "l", "leur", "leurs", "ou", "par", "pas", "pour", "qu",
    "que", "quel", "quelle", "quelles", "quels", "qui", "sa", "se", "son", "sont", "sur",
    "un", "une", "y", "zone", "zones", "t", "s", "n", "plu", "h", "regle", "regles",
    "reglement", "prevoit", "quoi", "comment", "combien", "peut", "on", "ne",
}  # fmt: skip


def normalize(text: str) -> str:
    """Minuscules, sans accents ; apostrophes, tirets et ponctuation remplacés par des espaces."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.]+", " ", text)).strip()


@dataclass(frozen=True)
class Place:
    code: str
    niveau: Niveau
    libelle: str


@dataclass(frozen=True)
class ZoneRule:
    """Rattachement d'un code du zonage au règlement (`configs/zones_reglement.csv`)."""

    code: str
    methode: str
    chapitre: str | None  # sans « Zone » : `UEi1`, `AUs.co`
    zone_u_reference: str | None = None
    chapitre_u: str | None = None
    abstention_motif: str | None = None


@dataclass(frozen=True)
class DateMention:
    """Date citée : année seule, mois et année, ou date complète."""

    year: int
    month: int | None = None
    day: int | None = None

    def matches(self, d: date) -> bool:
        """Vrai si la mention désigne `d` (au niveau de précision de la mention)."""
        return (
            self.year == d.year
            and self.month in (None, d.month)
            and (self.day is None or (self.month == d.month and self.day == d.day))
        )

    def __str__(self) -> str:
        return "-".join(str(x).zfill(2) for x in (self.year, self.month, self.day) if x)


@dataclass(frozen=True)
class Activity:
    niveau: NafLevel
    code: str
    libelle: str | None = None

    @property
    def label(self) -> str:
        name = {"sous_classe": "sous-classe"}.get(self.niveau, self.niveau)
        suffix = f" ({self.libelle})" if self.libelle else ""
        return f"{name} {self.code}{suffix} de la NAF rév. 2"


@dataclass(frozen=True)
class Lexicon:
    """Entités connues : zonage, chapitres du règlement, lieux, dates des versions chargées."""

    zones: dict[str, ZoneRule]
    chapters: frozenset[str]
    places: dict[str, Place]  # nom normalisé → lieu
    stock_date: date
    reglement_year: int

    def chapters_of(self, code: str) -> list[str]:
        """Chapitres du règlement qui régissent un code (zone AU : chapitre AUs.co et zone U)."""
        if code in self.chapters and code not in self.zones:
            return [code]
        rule = self.zones.get(code)
        if rule is None or rule.chapitre is None:
            return []
        return [c for c in (rule.chapitre, rule.chapitre_u) if c]

    def zonage_codes(self, code: str) -> list[str]:
        """Codes du zonage couverts par un code cité : ceux de son chapitre, ou lui-même."""
        if code in self.chapters:
            codes = [c for c, r in self.zones.items() if r.chapitre == code and not r.chapitre_u]
            if codes:
                return sorted(codes)
        return [code] if code in self.zones else []


def build_lexicon(
    zone_rows: Iterable[dict], places: Iterable[Place], stock_date: date, reglement_year: int
) -> Lexicon:
    """Lexique à partir des lignes de `zones_reglement` et des lieux (communes, arrondissements)."""

    def chapter(title: str | None) -> str | None:
        return title.removeprefix("Zone ").strip() if title else None

    zones, chapters = {}, set()
    for r in zone_rows:
        rule = ZoneRule(
            code=r["code_zone"],
            methode=r["methode"],
            chapitre=chapter(r.get("chapitre")),
            zone_u_reference=r.get("zone_u_reference"),
            chapitre_u=chapter(r.get("chapitre_u")),
            abstention_motif=r.get("abstention_motif"),
        )
        zones[rule.code] = rule
        chapters.update(c for c in (rule.chapitre, rule.chapitre_u) if c)
    return Lexicon(
        zones=zones,
        chapters=frozenset(chapters),
        places={normalize(p.libelle): p for p in places},
        stock_date=stock_date,
        reglement_year=reglement_year,
    )


@dataclass(frozen=True)
class Analysis:
    question: str
    zones: tuple[str, ...] = ()
    unknown_zones: tuple[str, ...] = ()
    places: tuple[Place, ...] = ()
    activity: Activity | None = None
    unknown_activity: str | None = None
    measure: Measure | None = None
    partial_diffusion: bool = False
    etat: Literal["A", "F"] = "A"
    rule: bool = False
    dates: tuple[DateMention, ...] = ()
    safeguarded: bool = False
    oap: str | None = None
    keywords: tuple[str, ...] = field(default=())
    topics: tuple[str, ...] = ()  # sujets réglementaires de la table fermée (`routing.sujets`)


def _zones(question: str, lexicon: Lexicon) -> tuple[list[str], list[str]]:
    known, unknown = [], []
    for token in TOKEN.findall(question):
        if m := STECAL_NUMBER.match(token):
            token = m.group(1) if m.group(1) in lexicon.zones else token
        if token in lexicon.zones or token in lexicon.chapters:
            known.append(token)
        elif PLAUSIBLE_ZONE.match(token):
            unknown.append(token)
    return list(dict.fromkeys(known)), list(dict.fromkeys(unknown))


def _places(text: str, lexicon: Lexicon) -> list[Place]:
    taken = [m.span() for m in NOT_A_PLACE.finditer(text)]

    def free(span: tuple[int, int]) -> bool:
        return all(span[1] <= a or span[0] >= b for a, b in taken)

    found: list[tuple[int, Place]] = []
    by_code = {p.code: p for p in lexicon.places.values()}
    for m in ARRONDISSEMENT.finditer(text):
        code = f"6938{m.group(1) or m.group(2)}"
        if code in by_code and free(m.span()):
            taken.append(m.span())
            found.append((m.start(), by_code[code]))
    for name in sorted(lexicon.places, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(name)}\b", text):
            if free(m.span()):
                taken.append(m.span())
                found.append((m.start(), lexicon.places[name]))
    places = [p for _, p in sorted(found, key=lambda x: x[0])]
    if any(p.niveau == "arrondissement_municipal" for p in places):
        places = [p for p in places if p.code != "69123"]  # règle 5 : jamais additionnés
    return list(dict.fromkeys(places))


def _activity(question: str, text: str) -> Activity | None:
    if m := NAF_CLASS.search(question):
        if m.group(2):
            return Activity("sous_classe", m.group(1) + m.group(2))
        return Activity("classe", m.group(1))
    if m := NAF_GROUP.search(question):
        return Activity("groupe", m.group(1))
    if m := NAF_DIVISION.search(text):
        return Activity("division", m.group(1))
    if m := NAF_SECTION.search(question):
        letter = m.group(1)
        return Activity("section", letter, NAF_SECTIONS[letter][2])
    for term in sorted(ACTIVITY_TERMS, key=len, reverse=True):
        if re.search(rf"\b{term}\b", text):
            level, code, label = ACTIVITY_TERMS[term]
            return Activity(level, code, label)
    return None


def _unknown_activity(text: str, places: dict[str, Place]) -> str | None:
    """Activité citée non reconnue (« combien de boulangeries », « établissements de santé »)."""
    if (m := COUNTED.search(text)) and not m.group(1).startswith("etablissement"):
        return m.group(1)
    first_words = {name.split()[0] for name in places}
    for m in AFTER_ESTABLISHMENTS.finditer(text):
        words = m.group(1).split()
        for i, word in enumerate(words):
            if word in {"de", "d", "du", "des"}:
                following = words[i + 1] if i + 1 < len(words) else ""
                if following and following not in ARTICLES and following not in first_words:
                    return following
                break
            if word in ARTICLES or word in STOPPING_FOLLOWERS:
                break
            if word not in NEUTRAL_FOLLOWERS:
                return word
    return None


def _dates(text: str) -> list[DateMention]:
    found = []
    for m in DATE.finditer(text):
        if text[max(0, m.start() - 4) : m.start()].strip().endswith("naf"):
            continue  # « NAF 2025 » : nomenclature, pas une date
        day = None if m.group(1) is None else (1 if m.group(1) == "1er" else int(m.group(1)))
        month = MONTHS[m.group(2)] if m.group(2) else None
        found.append(DateMention(int(m.group(3)), month, day))
    return found


def analyse(question: str, lexicon: Lexicon) -> Analysis:
    text = normalize(question)
    zones, unknown = _zones(question, lexicon)
    places = _places(text, lexicon)
    activity = _activity(question, text)
    measure: Measure | None = None
    if DISTRIBUTION.search(text):
        measure = "distribution"
    elif SHARE.search(text):
        measure = "share"
    elif COUNT.search(text):
        measure = "count"
    unknown_activity = (
        _unknown_activity(text, lexicon.places) if measure and activity is None else None
    )
    keywords = tuple(dict.fromkeys(w for w in text.split() if len(w) > 2 and w not in STOPWORDS))
    oap = m.group(1) if (m := OAP_NUMBER.search(text)) else None
    return Analysis(
        question=question,
        zones=tuple(zones),
        unknown_zones=tuple(unknown),
        places=tuple(places),
        activity=activity,
        unknown_activity=unknown_activity,
        measure=measure,
        partial_diffusion=bool(PARTIAL.search(text)),
        etat="F" if CLOSED.search(text) else "A",
        rule=bool(RULE_WORDS.search(text)),
        dates=tuple(_dates(text)),
        safeguarded=bool(SAFEGUARDED.search(text)) or "SECTSAUV" in zones,
        oap=oap,
        keywords=keywords,
        topics=detect(text),
    )
