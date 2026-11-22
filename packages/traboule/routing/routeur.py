"""Routeur SQL / RAG / HYBRID / ABSTAIN, déterministe (ADR-0010).

Les signaux structurels d'abstention passent avant toute recherche : zone inexistante,
zone régie par un autre document (secteur sauvegardé, PSMV non ingéré), STECAL (partie III
non ingérée), date hors des versions chargées, activité non reconnue. Chaque abstention porte
son motif et une limite écrite en clair.
"""

from dataclasses import dataclass

from traboule.contracts.question import Route
from traboule.contracts.reponse import MotifAbstention
from traboule.routing.analyse import Analysis, Lexicon

Abstention = tuple[MotifAbstention, str]


@dataclass(frozen=True)
class Decision:
    route: Route
    structured: bool
    documentary: bool
    motif: str
    structured_abstention: Abstention | None = None
    documentary_abstention: Abstention | None = None


def _neighbours(code: str, lexicon: Lexicon) -> list[str]:
    stem = code.rstrip("0123456789")
    stem = stem if stem != code else code[:-1]
    known = set(lexicon.zones) | set(lexicon.chapters)
    return sorted(c for c in known if c.startswith(stem) and c != code)[:6]


def _zone_abstention(analysis: Analysis, lexicon: Lexicon) -> Abstention | None:
    if analysis.unknown_zones:
        code = analysis.unknown_zones[0]
        near = _neighbours(code, lexicon)
        hint = f" ; codes proches : {', '.join(near)}" if near else ""
        text = f"La zone {code} n'existe pas dans le zonage{hint}."
        return MotifAbstention.ZONE_INEXISTANTE, text
    return None


def _documentary_abstention(analysis: Analysis, lexicon: Lexicon) -> Abstention | None:
    if analysis.safeguarded:
        return (
            MotifAbstention.AUTRE_DOCUMENT,
            "Le secteur sauvegardé du Vieux-Lyon est régi par le plan de sauvegarde et de mise "
            "en valeur (PSMV), document non ingéré ; le PLU-H ne s'y applique pas.",
        )
    for code in analysis.zones:
        rule = lexicon.zones.get(code)
        if rule and rule.abstention_motif == MotifAbstention.DOCUMENT_NON_INGERE:
            return (
                MotifAbstention.DOCUMENT_NON_INGERE,
                f"{code} est un STECAL régi par la partie III du règlement, non ingérée.",
            )
    if old := [d for d in analysis.dates if d.year < lexicon.reglement_year]:
        return (
            MotifAbstention.HORS_VERSION,
            f"Date {old[0]} antérieure au règlement chargé (approbation {lexicon.reglement_year}) ;"
            " les versions antérieures du PLU-H ne sont pas chargées.",
        )
    return None


def _structured_abstention(analysis: Analysis, lexicon: Lexicon) -> Abstention | None:
    stock = lexicon.stock_date
    if other := [d for d in analysis.dates if not d.matches(stock)]:
        return (
            MotifAbstention.HORS_VERSION,
            f"Date {other[0]} hors version : seul le stock Sirene du {stock.isoformat()} est "
            "chargé (historique des états non chargé).",
        )
    if analysis.unknown_activity:
        return (
            MotifAbstention.PREUVE_INSUFFISANTE,
            f"Activité « {analysis.unknown_activity} » non reconnue : préciser une section, une "
            "division ou une classe de la NAF rév. 2 (ex. « division 47 », « 52.10 »). Le "
            "système compte des établissements (SIRET), pas des entreprises.",
        )
    if analysis.measure == "share" and not (analysis.partial_diffusion or analysis.activity):
        return (
            MotifAbstention.PREUVE_INSUFFISANTE,
            "Part non reconnue : seules la part de diffusion partielle (statut P) et la part "
            "d'une activité NAF sont calculées.",
        )
    return None


def _describe(analysis: Analysis) -> str:
    parts = []
    if analysis.zones:
        parts.append("zone " + ", ".join(analysis.zones))
    if analysis.places:
        parts.append(", ".join(p.libelle for p in analysis.places))
    if analysis.activity:
        parts.append(analysis.activity.label)
    return f" ({' ; '.join(parts)})" if parts else ""


def route(analysis: Analysis, lexicon: Lexicon) -> Decision:
    structured = analysis.measure is not None
    documentary = analysis.rule or not structured
    zone_abst = _zone_abstention(analysis, lexicon)
    s_abst = (zone_abst or _structured_abstention(analysis, lexicon)) if structured else None
    d_abst = (zone_abst or _documentary_abstention(analysis, lexicon)) if documentary else None
    measure = {
        "count": "comptage demandé",
        "share": "part demandée",
        "distribution": "répartition demandée",
    }
    pieces = []
    if structured:
        pieces.append(f"{measure[analysis.measure]}{_describe(analysis)} → SQL")
    if documentary:
        pieces.append("règle écrite demandée → recherche documentaire")
    needed = [a for a, on in ((s_abst, structured), (d_abst, documentary)) if on]
    if all(a is not None for a in needed):
        r: Route = "ABSTAIN"
        pieces.append("abstention structurelle avant toute recherche")
    elif structured and documentary:
        r = "HYBRID"
    else:
        r = "SQL" if structured else "RAG"
    return Decision(r, structured, documentary, " ; ".join(pieces), s_abst, d_abst)
