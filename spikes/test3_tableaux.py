"""Test 3 : tableaux du règlement écrit (critère « au moins un extracteur traite les tableaux »).

Script jetable. Les chapitres du corpus pilote (zones économiques et AU) ne contiennent pas
de tableau de règles : on repère les pages à tableaux sur tout le règlement avec PyMuPDF
(find_tables), on en tire 5 de façon reproductible (md5, graine dédiée), puis on compare
PyMuPDF et Docling sur ces pages. Sorties dans spikes/output/pdf/tableaux/ (non versionné).
"""

import hashlib
import html
import json
import time
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF = next((ROOT / "data/raw/SRC-005/2026-10-28/reglement_ecrit").glob("*.pdf"))
OUT = ROOT / "spikes" / "output" / "pdf" / "tableaux"
SEED = 3104
SAMPLE = 5


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(PDF)
    start = time.perf_counter()
    found = {}
    for i, page in enumerate(doc, start=1):
        tables = page.find_tables().tables
        real = [t for t in tables if t.row_count >= 3 and t.col_count >= 2]
        if real:
            found[i] = [{"lignes": t.row_count, "colonnes": t.col_count} for t in real]
    scan_s = round(time.perf_counter() - start, 1)
    key = lambda p: hashlib.md5(f"tableaux|{p}|{SEED}".encode()).hexdigest()  # noqa: E731
    sample = sorted(sorted(found, key=key)[:SAMPLE])

    sub = pymupdf.open()
    for p in sample:
        sub.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
    sub_path = OUT / "pages_tableaux.pdf"
    sub.save(sub_path)

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    start = time.perf_counter()
    result = converter.convert(sub_path).document
    docling_s = round(time.perf_counter() - start, 1)

    sections, rows = [], []
    for i, p in enumerate(sample, start=1):
        page = doc[p - 1]
        page.get_pixmap(dpi=90).save(OUT / f"p{p}.png")
        mu_tables = [t.to_markdown() for t in page.find_tables().tables]
        dl_tables = [
            item.export_to_markdown(result)
            for item, _ in result.iterate_items(page_no=i)
            if type(item).__name__ == "TableItem"
        ]
        rows.append({"page": p, "pymupdf": len(mu_tables), "docling": len(dl_tables)})
        sections.append(
            f"<section><h2>Règlement p. {p}</h2><div class='row'><img src='p{p}.png'>"
            f"<div><h3>PyMuPDF ({len(mu_tables)})</h3><pre>{html.escape(chr(10).join(mu_tables))}</pre></div>"  # noqa: E501
            f"<div><h3>Docling ({len(dl_tables)})</h3><pre>{html.escape(chr(10).join(dl_tables))}</pre></div>"  # noqa: E501
            "</div></section>"
        )
    (OUT / "revue_tableaux.html").write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Tableaux</title><style>"
        "body{font:13px system-ui;margin:12px}.row{display:grid;grid-template-columns:40% 30% 30%;"
        "gap:8px}img{width:100%;border:1px solid #ccc}pre{white-space:pre-wrap;font-size:11px;"
        "background:#f6f6f6;padding:6px}</style></head><body><h1>Tableaux du règlement</h1>"
        + "".join(sections)
        + "</body></html>",
        encoding="utf-8",
    )
    metrics = {
        "pages_avec_tableau_pymupdf": sorted(found),
        "nombre_pages": len(found),
        "balayage_pymupdf_s": scan_s,
        "graine": SEED,
        "echantillon": sample,
        "docling_s": docling_s,
        "par_page": rows,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in metrics.items() if k != "pages_avec_tableau_pymupdf"},
            ensure_ascii=False,
        )
    )
    print("pages avec tableau :", metrics["pages_avec_tableau_pymupdf"])


if __name__ == "__main__":
    main()
