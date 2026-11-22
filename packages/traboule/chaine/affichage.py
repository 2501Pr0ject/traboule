"""Affichage lisible d'une `Reponse` dans le terminal (rich)."""

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from traboule.contracts.reponse import Citation, Composante, Reponse
from traboule.generation.redaction import document_title

MOTIFS = {
    "zone_inexistante": "zone inexistante",
    "document_non_ingere": "document non ingéré",
    "niveau_non_charge": "niveau géographique non chargé",
    "hors_version": "hors des versions chargées",
    "diffusion_partielle": "diffusion partielle",
    "autre_document": "régi par un autre document",
    "confiance_faible": "confiance de zone faible",
    "preuve_insuffisante": "preuve insuffisante",
    "citation_non_verifiee": "citation non vérifiée",
}


def citation_line(c: Citation) -> str:
    path = " > ".join(c.chemin[-3:])
    return f"{document_title(c.doc_id)}, p. {c.page} — {path} — {c.version_piece}"


def component_panel(c: Composante, strategy: str | None) -> Panel:
    kind = "Données (SQL)" if c.type == "structuree" else f"Règlement ({(strategy or '').upper()})"
    body: list = []
    if c.abstention:
        body.append(Text(f"Abstention — {MOTIFS.get(c.motif, c.motif)}", style="bold yellow"))
        body.append(Text(c.texte or ""))
    else:
        body.append(Text(c.texte or str(c.valeur)))
    for i, cit in enumerate(c.citations, 1):
        body.append(Text(f"[{i}] {citation_line(cit)}", style="cyan"))
    for s in c.sources:
        body.append(Text(f"Source : {s.table} — {s.millesime} ({', '.join(s.sources)})", "cyan"))
    for limit in c.limites if not c.abstention else []:
        body.append(Text(f"Limite : {limit}", style="dim"))
    for note in c.notes:
        body.append(Text(f"Contexte : {note}", style="dim"))
    style = "yellow" if c.abstention else ("green" if c.type == "structuree" else "blue")
    return Panel(Group(*body), title=kind, title_align="left", border_style=style)


def show(reponse: Reponse, console: Console | None = None) -> None:
    console = console or Console()
    console.print(Text(f"Route : {reponse.route}", style="bold"), Text(f"— {reponse.motif_route}"))
    for c in reponse.composantes:
        console.print(component_panel(c, reponse.strategie))
