"""Test 3 : pré-remplissage de spikes/output/pdf/grille.csv (pré-remplissage automatisé, à relire).

Script jetable. Évaluation faite sur le rendu PNG des pages (planches) et la comparaison des
textes PyMuPDF / Docling. Ne modifie jamais une ligne où relu_par_humain = « oui ».
Valeurs : texte_lisible oui/non/graphique ; ordre_lecture oui/non/partiel ; titres
oui/non/sans objet ; tableaux oui/partiel/non/sans objet ; parasites description courte.
"""

import csv
from pathlib import Path

GRID = Path(__file__).resolve().parents[1] / "spikes" / "output" / "pdf" / "grille.csv"

A_TEXT = ("oui", "oui")
TWO_COLUMNS = {"pymupdf": ("oui", "non"), "docling": ("oui", "oui")}
GRAPHIC = "graphique (hors périmètre sans OCR)"

# (doc, page) -> {extracteur: (lisible, ordre, titres, tableaux, parasites, commentaire)}
EVAL: dict[tuple[str, int], dict[str, tuple[str, ...]]] = {}

for page in (584, 598, 611, 620, 645, 658, 679, 736):
    EVAL[("A_reglement", page)] = {
        "pymupdf": (*A_TEXT, "oui", "sans objet", "en-tête et pied (retirés au découpage)", ""),
        "docling": (*A_TEXT, "oui", "sans objet", "non", ""),
    }
for page in (635, 643):  # pages sans titre (suite de liste)
    EVAL[("A_reglement", page)] = {
        "pymupdf": (
            *A_TEXT,
            "sans objet",
            "sans objet",
            "en-tête et pied (retirés au découpage)",
            "",
        ),
        "docling": (*A_TEXT, "sans objet", "sans objet", "non", ""),
    }

for page in (56, 60, 62, 64, 66, 72):  # OAP en deux colonnes
    EVAL[("B_oap_oullins", page)] = {
        "pymupdf": (*TWO_COLUMNS["pymupdf"], "oui", "sans objet", "pied de page",
                    "colonnes entrelacées ligne à ligne"),
        "docling": (*TWO_COLUMNS["docling"], "oui", "sans objet", "puces mal décodées (ͳ)", ""),
    }  # fmt: skip
for page in (59, 63, 67):  # cartes
    EVAL[("B_oap_oullins", page)] = {
        e: (GRAPHIC, "sans objet", "sans objet", "sans objet", "légende morcelée",
            "carte ; règle auto : graphique seulement p. 67 (p. 59, 63 sous le seuil d'image)")
        for e in ("pymupdf", "docling")
    }  # fmt: skip
EVAL[("B_oap_oullins", 69)] = {
    "pymupdf": (
        "oui",
        "partiel",
        "oui",
        "sans objet",
        "légende de carte mêlée au texte",
        "à relire",
    ),
    "docling": ("oui", "oui", "oui", "sans objet", "légende de carte", "à relire"),
}

for page in (3, 18, 27):  # deux colonnes
    EVAL[("C_cahier_pierre_benite", page)] = {
        "pymupdf": (*TWO_COLUMNS["pymupdf"], "oui", "sans objet", "pied de page",
                    "colonnes entrelacées"),
        "docling": (*TWO_COLUMNS["docling"], "oui", "sans objet", "non", ""),
    }  # fmt: skip
for page in (32, 34):  # graphiques
    EVAL[("C_cahier_pierre_benite", page)] = {
        "pymupdf": ("oui", "non", "oui", "sans objet", "étiquettes de graphiques",
                    "colonnes et graphiques entrelacés"),
        "docling": ("oui", "partiel", "oui", "sans objet", "texte dupliqué (jusqu'à 5 fois)",
                    "duplication massive sur les graphiques"),
    }  # fmt: skip
for page in (41, 43):  # texte + notes latérales
    EVAL[("C_cahier_pierre_benite", page)] = {
        "pymupdf": ("oui", "non", "oui", "sans objet", "notes latérales mêlées", "à relire"),
        "docling": ("oui", "partiel", "oui", "sans objet", "notes latérales", "à relire"),
    }
for page in (48, 52):  # une colonne
    EVAL[("C_cahier_pierre_benite", page)] = {
        e: ("oui", "oui", "oui", "sans objet", "pied de page" if e == "pymupdf" else "non", "")
        for e in ("pymupdf", "docling")
    }
EVAL[("C_cahier_pierre_benite", 65)] = {
    e: ("quasi vide", "sans objet", "oui", "sans objet", "non",
        "page de titre de section (tableau des surfaces sur la page suivante)")
    for e in ("pymupdf", "docling")
}  # fmt: skip

FIELDS = ("texte_lisible", "ordre_lecture", "titres_zone_article", "tableaux", "parasites")


def main() -> None:
    rows = list(csv.DictReader(GRID.open(encoding="utf-8")))
    missing = []
    for row in rows:
        if row["relu_par_humain"] == "oui":
            continue
        values = EVAL.get((row["doc_id"], int(row["page_pdf"])), {}).get(row["extracteur"])
        if values is None:
            missing.append((row["doc_id"], row["page_pdf"], row["extracteur"]))
            continue
        row.update(dict(zip(FIELDS, values[:5], strict=True)))
        row["commentaire"] = ("pré-remplissage automatisé ; " + values[5]).rstrip(" ;")
    with GRID.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} lignes, {len(missing)} sans évaluation : {missing}")


if __name__ == "__main__":
    main()
