"""Renvois entre pièces : lien `renvoi_vers` d'un passage vers les passages qu'il cite.

Mécanisme commun (ADR-0009, ADR-0011) : renvois d'un cahier d'arrondissement à une OAP
définie dans une autre pièce (OAP 0.1 du cahier communal de Lyon), et, à venir, renvois des
articles de zone à un chapitre de la partie I du règlement.

Renvois d'OAP : `configs/oap_exceptions.yaml`, entrées avec `cible`. Chaque passage de la
ressource qui cite l'OAP (« OAP 0.1 ») reçoit un lien vers tous les passages de cette OAP dans
la pièce cible. Contrôles bloquants : la cible a des passages pour cette OAP, et la ressource a
au moins un passage qui la cite.

Renvois à la partie I : résolus à l'extraction du règlement (`link_partie_i`), vers tous les
passages du chapitre ou de l'article cité ; contrôle bloquant si la cible n'a aucun passage.

Usage : `uv run python -m traboule.retrieval.renvois` (après `traboule.retrieval.ligatures`).
"""

import re
import sys
from collections import Counter
from pathlib import Path

import typer
import yaml

from traboule.config import INTERIM_DIR, OAP_EXCEPTIONS
from traboule.contracts.passage import Passage, Renvoi
from traboule.measure import write_metrics
from traboule.retrieval.cahiers import OUT_DIR
from traboule.retrieval.index_config import load_identical


class RenvoiError(RuntimeError):
    """Contrôle bloquant de la résolution des renvois."""


def load_oap_links(path: Path = OAP_EXCEPTIONS) -> list[tuple[str, str, str]]:
    """(ressource, numéro d'OAP, ressource cible) pour les exceptions qui ont une cible."""
    entries = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("exceptions") or []
    return [(e["ressource"], str(e["oap"]), e["cible"]) for e in entries if e.get("cible")]


def cites_oap(text: str, numero: str) -> bool:
    return re.search(rf"\bOAP\s*{re.escape(numero)}(?![.\d])", text) is not None


def link_oap(
    sources: list[Passage], targets: list[Passage], numero: str, cible: str
) -> tuple[list[Passage], int]:
    """Ajoute le renvoi vers l'OAP `numero` des `targets` aux passages qui la citent."""
    ids = [p.passage_id for p in targets if p.oap and p.oap.split()[1] == numero]
    if not ids:
        raise RenvoiError(f"aucun passage de l'OAP {numero} dans la cible ({cible})")
    renvoi = Renvoi(cible=cible, doc_id=targets[0].doc_id, passage_ids=ids)
    out, linked = [], 0
    for p in sources:
        if cites_oap(p.texte, numero):
            kept = [r for r in p.renvoi_vers or [] if r.cible != cible]
            p = p.model_copy(update={"renvoi_vers": [*kept, renvoi]})
            linked += 1
        out.append(p)
    if not linked:
        raise RenvoiError(f"aucun passage ne cite l'OAP {numero}")
    return out, linked


# Renvois des articles de zone à la partie I (ADR-0011) : « au chapitre 5 de la partie I »,
# « dans la partie I du règlement (chapitre 5) », « au 3.1.6.1 de la Partie 1 ». Un renvoi à
# la partie I entière (« définitions prévues dans la partie I ») n'est pas lié.
PARTIE_I = r"partie\s+(?:I|1)\b(?![IV])"
CHAPTER_REF = re.compile(
    rf"chapitre\s+(\d)\s+de\s+la\s+{PARTIE_I}"
    rf"|{PARTIE_I}\s+du\s+(?:présent\s+)?règlement\s*\(chapitre\s+(\d)\)",
    re.I,
)
ARTICLE_REF = re.compile(rf"\b(\d+(?:\.\d+)+)\s+de\s+la\s+{PARTIE_I}", re.I)


def partie_i_targets(passages: list[Passage], ref: str, kind: str) -> tuple[str, list[str]]:
    """Cible (titre) et passages de la partie I pour un chapitre ou un article."""
    ids, title = [], None
    for p in passages:
        if not p.chemin[0].startswith("Partie I "):
            continue
        for part in p.chemin[1:]:
            match = (
                re.match(rf"CHAPITRE {ref} - ", part)
                if kind == "chapitre"
                else re.match(rf"{re.escape(ref)}(\.\d+)* - ", part)
            )
            if match:
                title = title or (
                    part if kind == "chapitre" else f"{ref} - {part.split(' - ', 1)[1]}"
                )
                ids.append(p.passage_id)
                break
    if not ids:
        raise RenvoiError(f"renvoi à la partie I ({kind} {ref}) sans passage cible")
    return f"Partie I, {title}", ids


def link_partie_i(passages: list[Passage]) -> tuple[list[Passage], Counter]:
    """Ajoute à chaque passage hors partie I ses renvois à un chapitre ou article de la partie I."""
    cache: dict[tuple[str, str], tuple[str, list[str]]] = {}
    out, counts = [], Counter()
    for p in passages:
        refs = []
        if not p.chemin[0].startswith("Partie I "):
            refs += [("chapitre", a or b) for a, b in CHAPTER_REF.findall(p.texte)]
            refs += [("article", n) for n in ARTICLE_REF.findall(p.texte)]
        renvois = []
        for kind, ref in dict.fromkeys(refs):
            if (kind, ref) not in cache:
                cache[(kind, ref)] = partie_i_targets(passages, ref, kind)
            cible, ids = cache[(kind, ref)]
            renvois.append(Renvoi(cible=cible, doc_id=p.doc_id, passage_ids=ids))
            counts[cible] += 1
        out.append(p.model_copy(update={"renvoi_vers": renvois}) if renvois else p)
    return out, counts


def read_passages(resource: str) -> list[Passage]:
    path = OUT_DIR / resource / "passages.jsonl"
    return [Passage.model_validate_json(line) for line in path.open(encoding="utf-8")]


app = typer.Typer(add_completion=False)


@app.command()
def main() -> None:
    """Résout les renvois d'OAP et réécrit les passages des ressources qui renvoient."""
    titles = {g.reference: g.titre for g in load_identical()}
    results = {}
    try:
        for resource, numero, target in load_oap_links():
            targets = read_passages(target)
            cible = f"OAP {numero} — {titles.get(target, targets[0].doc_id)}"
            passages, linked = link_oap(read_passages(resource), targets, numero, cible)
            (OUT_DIR / resource / "passages.jsonl").write_text(
                "".join(p.model_dump_json() + "\n" for p in passages), encoding="utf-8"
            )
            target_ids = next(p for p in passages if p.renvoi_vers).renvoi_vers[-1].passage_ids
            results[resource] = {"oap": numero, "cible": target, "passages_liens": linked,
                                 "passages_cibles": len(target_ids)}  # fmt: skip
    except RenvoiError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
    write_metrics(INTERIM_DIR / "metrics" / "renvois.json", results, {"source": "oap_exceptions"})
    for resource, r in results.items():
        typer.echo(f"{resource} : {r['passages_liens']} passages → OAP {r['oap']} "
                   f"({r['passages_cibles']} passages de {r['cible']})")  # fmt: skip


if __name__ == "__main__":
    app()
