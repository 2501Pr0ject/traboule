"""Test 4 du spike : BGE-M3 (dense + sparse) sur le M2, index Qdrant local, 21 requêtes.

Script jetable. Entrées figées : spikes/output/pdf/passages.jsonl (corpus du Test 3) et
spikes/queries_pilote.tsv (requêtes du porteur), vérifiés par sha256 avant tout encodage.
Quatre modes : dense, sparse, hybride (RRF), hybride filtré sur la zone attendue.
Sorties (non versionnées) : spikes/output/qdrant/, spikes/output/test4/{metrics.json,
jugements.csv, revue_requetes.html}. jugements.csv n'est jamais réécrit s'il existe.
"""

import csv
import hashlib
import html
import json
import platform
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import psutil
import typer

ROOT = Path(__file__).resolve().parents[1]
PASSAGES = ROOT / "spikes" / "output" / "pdf" / "passages.jsonl"
QUERIES = ROOT / "spikes" / "queries_pilote.tsv"
OUT = ROOT / "spikes" / "output" / "test4"
QDRANT = ROOT / "spikes" / "output" / "qdrant"
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
PASSAGES_SHA = "fda1d07b9ca9299e207877dac53110641838095862b479328c57bd1c48eaffdb"
QUERIES_SHA = "1355d77e18f317dc85dae1c0b350496d3ed6f4d2cfe703d7c0bc6856857bdb5d"
MODEL = "BAAI/bge-m3"
COLLECTION = "pilote"
BATCH_SIZE = 8
MAX_LENGTH = 8192
PREFETCH = 50
TOP_K = 10
POOL_K = 5
DOC = {"A": "A_reglement", "B": "B_oap_oullins", "C": "C_cahier_pierre_benite"}
ZONE_FILTER = {"AUEi1": ["AUs.co", "UEi1"]}  # correspondance du Test 3 (p. 731 + chapitre UEi1)
# Estimation du corpus complet (pages) : règlement entier ; cahiers 76 × fourchette observée
REGLEMENT_PAGES = 803
CAHIERS = 76
CAHIER_PAGES = (67, 150)
PILOT_PAGES = {"A_reglement": 120, "B_oap_oullins": 18, "C_cahier_pierre_benite": 67}

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


@contextmanager
def measured(name: str, steps: dict, mps=None):
    """Temps, pic RSS (échantillonné toutes les 100 ms) et mémoire MPS allouée par le pilote."""
    proc, peak, stop = psutil.Process(), [0, 0], threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            if mps is not None:
                peak[1] = max(peak[1], mps.driver_allocated_memory())
            stop.wait(0.1)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    start = time.perf_counter()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        steps[name] = {
            "seconds": round(time.perf_counter() - start, 2),
            "peak_rss_mb": round(max(peak[0], proc.memory_info().rss) / 1e6),
            "peak_mps_mb": round(peak[1] / 1e6) if mps is not None else None,
        }
        typer.echo(f"  {name} : {steps[name]}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dir_size(path: Path) -> int:
    # Sans suivre les liens symboliques (le cache Hugging Face lie snapshots et blobs)
    return (
        sum(p.lstat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())
        if path.exists()
        else 0
    )


def sparse_vector(models, weights: dict):
    items = sorted((int(k), float(v)) for k, v in weights.items())
    return models.SparseVector(indices=[i for i, _ in items], values=[v for _, v in items])


def run_query(client, models, mode: str, dense, sparse, zones: list[str] | None):
    flt = (
        models.Filter(must=[models.FieldCondition(key="zone", match=models.MatchAny(any=zones))])
        if zones
        else None
    )
    if mode == "dense":
        res = client.query_points(COLLECTION, query=dense, using="dense", limit=TOP_K)
    elif mode == "sparse":
        res = client.query_points(COLLECTION, query=sparse, using="sparse", limit=TOP_K)
    else:  # hybride, filtré ou non
        res = client.query_points(
            COLLECTION,
            prefetch=[
                models.Prefetch(query=dense, using="dense", limit=PREFETCH, filter=flt),
                models.Prefetch(query=sparse, using="sparse", limit=PREFETCH, filter=flt),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=TOP_K,
        )
    return [(p.payload["passage_id"], float(p.score)) for p in res.points]


@app.command()
def main() -> None:
    """Encodage, indexation, requêtes dans les 4 modes et pool de jugement."""
    OUT.mkdir(parents=True, exist_ok=True)
    if sha256(PASSAGES) != PASSAGES_SHA or sha256(QUERIES) != QUERIES_SHA:
        raise typer.Exit("ERREUR : corpus ou requêtes différents des versions figées (sha256)")
    passages = [json.loads(line) for line in PASSAGES.open(encoding="utf-8")]
    by_id = {p["passage_id"]: p for p in passages}
    queries = list(csv.DictReader(QUERIES.open(encoding="utf-8"), delimiter="\t"))
    typer.echo(
        f"  corpus et requêtes conformes : {len(passages)} passages, {len(queries)} requêtes"
    )

    import torch
    from FlagEmbedding import BGEM3FlagModel
    from qdrant_client import QdrantClient, models

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    mps = torch.mps if device == "mps" else None
    steps: dict = {}
    result: dict = {"started_at": datetime.now(UTC).isoformat(), "device": device, "steps": steps}

    cache_before = dir_size(HF_CACHE)
    with measured("chargement_modele (exclu)", steps, mps):
        model = BGEM3FlagModel(MODEL, use_fp16=(device == "mps"), devices=device)
    result["modele_telecharge_mo"] = round((dir_size(HF_CACHE) - cache_before) / 1e6)

    texts = [p["texte"] for p in passages]
    tokens = [len(model.tokenizer(t, add_special_tokens=False)["input_ids"]) for t in texts]
    with measured("encodage_corpus", steps, mps):
        enc = model.encode(
            texts, batch_size=BATCH_SIZE, max_length=MAX_LENGTH,
            return_dense=True, return_sparse=True, return_colbert_vecs=False,
        )  # fmt: skip
    seconds = steps["encodage_corpus"]["seconds"]
    result["encodage"] = {
        "passages": len(texts), "tokens": sum(tokens), "tokens_max": max(tokens),
        "passages_par_min": round(60 * len(texts) / seconds, 1),
        "tokens_par_s": round(sum(tokens) / seconds),
        "batch_size": BATCH_SIZE, "max_length": MAX_LENGTH, "fp16": device == "mps",
    }  # fmt: skip

    if QDRANT.exists():
        shutil.rmtree(QDRANT)  # index régénérable
    client = QdrantClient(path=str(QDRANT))
    with measured("indexation_qdrant", steps):
        client.create_collection(
            COLLECTION,
            vectors_config={
                "dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
        points = [
            models.PointStruct(
                id=i,
                vector={
                    "dense": enc["dense_vecs"][i].tolist(),
                    "sparse": sparse_vector(models, enc["lexical_weights"][i]),
                },
                payload={
                    k: p[k]
                    for k in (
                        "passage_id",
                        "doc_id",
                        "zone",
                        "chemin",
                        "page_debut",
                        "page_fin",
                        "version_piece",
                    )
                },  # fmt: skip
            )
            for i, p in enumerate(passages)
        ]
        client.upsert(COLLECTION, points=points)
    result["qdrant"] = {
        "points": client.count(COLLECTION).count,
        "taille_disque_mo": round(dir_size(QDRANT) / 1e6, 1),
    }

    with measured("encodage_requetes", steps, mps):
        qenc = model.encode(
            [q["requete"] for q in queries], batch_size=BATCH_SIZE, max_length=512,
            return_dense=True, return_sparse=True, return_colbert_vecs=False,
        )  # fmt: skip
    rankings, latencies = {}, {m: [] for m in ("dense", "sparse", "hybride", "hybride_filtre")}
    for i, q in enumerate(queries):
        dense = qenc["dense_vecs"][i].tolist()
        sparse = sparse_vector(models, qenc["lexical_weights"][i])
        zone = q["zone_attendue"]
        zones = ZONE_FILTER.get(zone, [zone]) if zone != "-" else None
        rankings[q["id"]] = {}
        for mode in latencies:
            if mode == "hybride_filtre" and not zones:
                continue
            start = time.perf_counter()
            rankings[q["id"]][mode] = run_query(
                client, models, mode, dense, sparse, zones if mode == "hybride_filtre" else None
            )
            latencies[mode].append((time.perf_counter() - start) * 1000)
    result["latence_ms"] = {
        m: {"mediane": round(sorted(v)[len(v) // 2], 1), "max": round(max(v), 1), "n": len(v)}
        for m, v in latencies.items()
    }
    result["filtre_zone"] = {q["id"]: ZONE_FILTER.get(q["zone_attendue"], [q["zone_attendue"]])
                             for q in queries if q["zone_attendue"] != "-"}  # fmt: skip
    result["sonde_q21"] = rankings.get("Q21")
    result["classements"] = rankings

    # Contrôle de cohérence (Q05 : coefficient de pleine terre en UEp)
    q05 = {pid for mode in ("dense", "sparse") for pid, _ in rankings["Q05"][mode]}
    result["controle_q05"] = any(
        by_id[pid]["zone"] == "UEp" and "pleine terre" in by_id[pid]["chemin"].lower()
        for pid in q05
    )
    typer.echo(f"  contrôle Q05 (UEp pleine terre en dense ou sparse) : {result['controle_q05']}")

    # Multivecteur : taille et temps estimés (non indexé)
    tok_page = {
        d: sum(t for t, p in zip(tokens, passages, strict=True) if p["doc_id"] == d) / n
        for d, n in PILOT_PAGES.items()
    }
    tok_cahier = (sum(tok_page[d] * PILOT_PAGES[d] for d in ("B_oap_oullins", "C_cahier_pierre_benite"))  # noqa: E501
                  / (PILOT_PAGES["B_oap_oullins"] + PILOT_PAGES["C_cahier_pierre_benite"]))  # fmt: skip  # noqa: E501
    scenarios = {
        "corpus_pilote": sum(tokens),
        "reglement_complet": tok_page["A_reglement"] * REGLEMENT_PAGES,
        "reglement_et_cahiers_bas": tok_page["A_reglement"] * REGLEMENT_PAGES
        + tok_cahier * CAHIERS * CAHIER_PAGES[0],
        "reglement_et_cahiers_haut": tok_page["A_reglement"] * REGLEMENT_PAGES
        + tok_cahier * CAHIERS * CAHIER_PAGES[1],
    }
    tps = result["encodage"]["tokens_par_s"]
    result["multivecteur"] = {
        k: {"tokens": round(v), "fp32_go": round(v * 1024 * 4 / 1e9, 2),
            "fp16_go": round(v * 1024 * 2 / 1e9, 2), "encodage_estime_min": round(v / tps / 60, 1)}
        for k, v in scenarios.items()
    }  # fmt: skip
    result["tokens_par_page"] = {d: round(v) for d, v in tok_page.items()}

    write_pool(queries, rankings, by_id)
    result["environment"] = {
        "python": platform.python_version(), "platform": platform.platform(),
        "versions": {p: version(p) for p in ("torch", "flagembedding", "transformers",
                                             "qdrant-client", "psutil")},
        "passages_sha256": PASSAGES_SHA, "requetes_sha256": QUERIES_SHA,
    }  # fmt: skip
    (OUT / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    typer.echo(f"Mesures : {OUT / 'metrics.json'}")


def write_pool(queries: list[dict], rankings: dict, by_id: dict) -> None:
    """Pool de jugement : top 10 hybride ∪ top 5 dense ∪ top 5 sparse ∪ top 5 hybride filtré."""
    rows, sections = [], []
    for q in queries:
        r = rankings[q["id"]]
        rank = {m: {pid: i + 1 for i, (pid, _) in enumerate(lst)} for m, lst in r.items()}
        pool = [pid for pid, _ in r["hybride"][:TOP_K]]
        for mode in ("dense", "sparse", "hybride_filtre"):
            pool += [pid for pid, _ in r.get(mode, [])[:POOL_K] if pid not in pool]
        items = []
        for pid in pool:
            p = by_id[pid]
            row = {
                "requete_id": q["id"], "role": q["role"], "passage_id": pid, "doc_id": p["doc_id"],
                "zone": p["zone"] or "", "chemin": p["chemin"], "pages": f"{p['page_debut']}-{p['page_fin']}",  # noqa: E501
                **{f"rang_{m}": rank.get(m, {}).get(pid, "") for m in ("hybride", "dense", "sparse", "hybride_filtre")},  # noqa: E501
                "auto_doc_attendu": DOC[q["doc_attendu"]] == p["doc_id"],
                "auto_zone_attendue": "" if q["zone_attendue"] == "-"
                else p["zone"] in ZONE_FILTER.get(q["zone_attendue"], [q["zone_attendue"]]),
                "pertinent": "", "relu_par_humain": "non", "commentaire": "",
            }  # fmt: skip
            rows.append(row)
            items.append(
                f"<tr><td>{row['rang_hybride']}</td><td>{row['rang_dense']}</td><td>{row['rang_sparse']}</td>"  # noqa: E501
                f"<td>{row['rang_hybride_filtre']}</td><td>{pid}</td><td>{row['zone']}</td>"
                f"<td>{html.escape(p['chemin'])}<br><small>p. {row['pages']}</small></td>"
                f"<td><small>{html.escape(p['texte'][:600])}</small></td>"
                f"<td>{'✓' if row['auto_doc_attendu'] else '✗'} / {row['auto_zone_attendue']}</td></tr>"  # noqa: E501
            )
        sections.append(
            f"<section><h2>{q['id']} ({q['type']}, {q['role']}) — {html.escape(q['requete'])}</h2>"
            f"<p>Attendu : doc {q['doc_attendu']}, zone {q['zone_attendue']}</p><table><tr>"
            "<th>hyb.</th><th>dense</th><th>sparse</th><th>filtré</th><th>passage</th><th>zone</th>"
            "<th>chemin</th><th>extrait</th><th>pré-indication* doc / zone</th></tr>"
            + "".join(items)
            + "</table></section>"
        )
    path = OUT / "jugements.csv"
    if path.exists():
        typer.echo(f"  {path} existe : conservé (jugement éventuel en cours)")
    else:
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (OUT / "revue_requetes.html").write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Revue Test 4</title>"
        "<style>body{font:13px system-ui;margin:12px}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:4px;vertical-align:top}section{margin-top:18px}"
        "</style></head><body><h1>Revue des requêtes — Test 4</h1><p>* Pré-indications "
        "automatiques <b>non contraignantes</b> : seul le jugement du porteur compte.</p>"
        + "".join(sections)
        + "</body></html>",
        encoding="utf-8",
    )


if __name__ == "__main__":
    app()
