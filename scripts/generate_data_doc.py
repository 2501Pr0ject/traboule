"""Génère docs/architecture/donnees.md depuis le catalogue (`traboule.catalogue`), qui fait foi.

Usage : `uv run python scripts/generate_data_doc.py` ; `--check` échoue si le fichier
versionné diffère de la génération.
"""

import sys
from pathlib import Path

from traboule.catalogue import META_TABLES, TABLES, Table

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "donnees.md"

HEADER = """# Tables de la base DuckDB

Document généré par `scripts/generate_data_doc.py` depuis `packages/traboule/catalogue.py` ; ne
pas le modifier à la main.

La base `data/processed/traboule.duckdb` est construite par
`uv run python -m traboule.ingestion.database` et reste **locale** (elle contient des SIRET ;
`*.duckdb` est exclu de Git). Chaque table déclare son niveau géographique et son millésime
(conventions §3, règles 5 et 6) ; les mêmes descriptions figurent dans la base
(`COMMENT ON TABLE`, `COMMENT ON COLUMN`, table `_catalogue`). Les géométries sont en
EPSG:2154 ; ouvrir la base avec l'extension `spatial` chargée.
"""


def render_table(t: Table) -> str:
    lines = [f"### `{t.name}`", "", t.description, ""]
    lines += [
        f"- **Niveau géographique :** {t.niveau}",
        f"- **Millésime :** {t.millesime}",
        f"- **Sources :** {', '.join(f'`{s}`' for s in t.sources) or '—'}",
        f"- **Produite par :** `{t.produite_par}`",
    ]
    if t.avertissement:
        lines.append(f"- **Règle d'usage :** {t.avertissement}")
    lines += ["", "| Colonne | Description |", "|---|---|"]
    lines += [f"| `{c.name}` | {c.description} |" for c in t.columns]
    lines += ["", "Exemple :", "", "```sql", t.exemple_sql, "```", ""]
    return "\n".join(lines)


def render() -> str:
    """Documentation complète, sérialisée de façon stable."""
    parts = [HEADER, "## Tables de données", ""]
    parts += [render_table(t) for t in TABLES]
    parts += ["## Tables de description", ""]
    parts += [render_table(t) for t in META_TABLES]
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv[1:]:
        if not DOC_PATH.exists() or DOC_PATH.read_text(encoding="utf-8") != content:
            print(f"{DOC_PATH.name} diffère du catalogue : régénérer la documentation")
            return 1
        return 0
    DOC_PATH.write_text(content, encoding="utf-8")
    print(f"écrit : {DOC_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
