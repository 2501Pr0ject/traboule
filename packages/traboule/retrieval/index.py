"""Index Qdrant embarqué des passages (ADR-0009, ADR-0013) : deux collections, BGE-M3.

- passages indexés : règlement (parties I et II) et cahiers, hors exclusions de
  `configs/index.yaml` (pièce mal identifiée, doublons des pièces identiques) ;
- `passages_entete` : texte précédé de l'en-tête contextuel (zone, libellé, chemin, secteurs et
  alias ; pour les cahiers : pièce, commune, OAP) ; `passages_brut` : texte seul. L'en-tête ne
  sert qu'à l'encodage : le payload garde le texte cité ;
- BGE-M3 dense (1024, cosinus) et sparse, fp16 sur MPS sinon CPU ; index de payload déclarés
  sur `zones_applicables`, `doc_id` et `code_commune_cog2026` (sans effet en mode embarqué :
  le filtre y parcourt les points, ce qui suffit à cette taille ; utiles avec un serveur) ;
- mesures : durée de chaque étape, pic mémoire du processus, mémoire MPS, taille de l'index.

Usage : `uv run python -m traboule.retrieval.index` ; recherche de démonstration :
`uv run python -m traboule.retrieval.index demo "hauteur des constructions" --zone UCe3`.
"""

import shutil
import sys
import time
import uuid
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from traboule.config import INTERIM_DIR, PROCESSED_DIR
from traboule.contracts.passage import Passage
from traboule.geo.zones_reglement import REGLEMENT
from traboule.measure import peak_rss_bytes, write_metrics
from traboule.retrieval.cahiers import OUT_DIR as CAHIERS_DIR
from traboule.retrieval.index_config import load_exclusions
from traboule.retrieval.reglement import OUT_DIR as REGLEMENT_DIR

QDRANT_DIR = PROCESSED_DIR / "qdrant"
DATABASE = PROCESSED_DIR / "traboule.duckdb"
MODEL = "BAAI/bge-m3"
BATCH_SIZE = 8
MAX_LENGTH = 8192
COLLECTIONS = {"passages_entete": True, "passages_brut": False}
PAYLOAD_INDEXES = ("zones_applicables", "doc_id", "code_commune_cog2026")
PREFETCH = 50
REGLEMENT_DOC = Path(REGLEMENT).name
TOP_K = 10


class IndexBuildError(RuntimeError):
    """Contrôle bloquant de la construction de l'index."""


def load_passages(exclusions: dict[str, str]) -> tuple[list[Passage], dict[str, int]]:
    """Passages du règlement et des cahiers indexés ; ressources exclues comptées."""
    passages = [
        Passage.model_validate_json(line)
        for line in (REGLEMENT_DIR / "passages.jsonl").open(encoding="utf-8")
    ]
    excluded = {}
    for folder in sorted(CAHIERS_DIR.iterdir()):
        path = folder / "passages.jsonl"
        if not path.exists():
            continue
        rows = [Passage.model_validate_json(line) for line in path.open(encoding="utf-8")]
        if folder.name in exclusions:
            excluded[folder.name] = len(rows)
        else:
            passages += rows
    ids = [p.passage_id for p in passages]
    if len(set(ids)) != len(ids):
        raise IndexBuildError("identifiants de passage en double")
    return passages, excluded


def place_names(database: Path = DATABASE) -> dict[str, str]:
    """Code commune ou arrondissement → libellé (base DuckDB, lecture seule)."""
    import duckdb

    con = duckdb.connect(str(database), read_only=True)
    try:
        rows = con.execute(
            "select code_commune, libelle from communes "
            "union all select code_arrondissement, libelle from arrondissements"
        ).fetchall()
    finally:
        con.close()
    return dict(rows)


def contextual_header(p: Passage, names: dict[str, str]) -> str:
    """En-tête contextuel d'un passage (ADR-0009), préfixé au texte pour l'encodage seulement."""
    parts = []
    if p.secteur_pluh or p.secteurs_pluh:
        kind = "Cahier d'arrondissement" if "arrondissement" in p.doc_id else "Cahier communal"
        place = names.get(p.commune_historique or "") or names.get(p.code_commune_cog2026 or "")
        parts.append(p.titre_piece or f"{kind} : {place}")
    else:
        parts.append("Règlement du PLU-H")
    if p.zone:
        parts.append(f"Zone {p.zone}" + (f" ({p.zone_libelle})" if p.zone_libelle else ""))
    elif p.zones_applicables:
        parts.append("Zones " + ", ".join(p.zones_applicables))
    parts.append(" > ".join(p.chemin))
    if p.secteurs:
        sectors = []
        for code in p.secteurs:
            alias = [a for a in p.alias or [] if a.code_reglement == code]
            note = "".join(
                f" (correspondance de code probable : {a.code_zonage})"
                if a.statut == "probable"
                else f" (code du zonage : {a.code_zonage})"
                for a in alias
            )
            sectors.append(code + note)
        parts.append("Secteurs : " + ", ".join(sectors))
    return " | ".join(parts)


def point_id(passage_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"traboule/{passage_id}"))


def sparse_vector(models, weights: dict):
    items = sorted((int(k), float(v)) for k, v in weights.items())
    return models.SparseVector(indices=[i for i, _ in items], values=[v for _, v in items])


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def load_model():
    import torch
    from FlagEmbedding import BGEM3FlagModel

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    return BGEM3FlagModel(MODEL, use_fp16=(device == "mps"), devices=device), device


def mps_memory_mb() -> float | None:
    import torch

    if not torch.backends.mps.is_available():
        return None
    return round(torch.mps.driver_allocated_memory() / 2**20)


app = typer.Typer(add_completion=False)


@app.command()
def build() -> None:
    """Encode les passages et construit les deux collections (index régénéré en entier)."""
    from qdrant_client import QdrantClient, models

    steps: dict[str, float] = {}
    t = time.perf_counter()
    exclusions = load_exclusions()
    passages, excluded = load_passages(exclusions)
    names = place_names()
    texts = {
        "passages_entete": [f"{contextual_header(p, names)}\n{p.texte}" for p in passages],
        "passages_brut": [p.texte for p in passages],
    }
    steps["lecture"] = time.perf_counter() - t
    t = time.perf_counter()
    model, device = load_model()
    steps["chargement_modele"] = time.perf_counter() - t
    if QDRANT_DIR.exists():
        shutil.rmtree(QDRANT_DIR)  # index régénérable
    client = QdrantClient(path=str(QDRANT_DIR))
    collections, mps_peak = {}, 0
    for name, with_header in COLLECTIONS.items():
        tokens = sum(
            len(model.tokenizer(x, add_special_tokens=False)["input_ids"]) for x in texts[name]
        )
        t = time.perf_counter()
        enc = model.encode(
            texts[name],
            batch_size=BATCH_SIZE,
            max_length=MAX_LENGTH,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        seconds = time.perf_counter() - t
        mps_peak = max(mps_peak, mps_memory_mb() or 0)
        t = time.perf_counter()
        dense = models.VectorParams(size=1024, distance=models.Distance.COSINE)
        client.create_collection(
            name,
            vectors_config={"dense": dense},
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
        for field in PAYLOAD_INDEXES:
            client.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)
        for start in range(0, len(passages), 256):
            client.upsert(name, points=[
                models.PointStruct(
                    id=point_id(p.passage_id),
                    vector={"dense": enc["dense_vecs"][i].tolist(),
                            "sparse": sparse_vector(models, enc["lexical_weights"][i])},
                    payload=p.model_dump(mode="json"),
                )
                for i, p in enumerate(passages[start : start + 256], start=start)
            ])  # fmt: skip
        count = client.count(name).count
        if count != len(passages):
            raise IndexBuildError(f"{name} : {count} points pour {len(passages)} passages")
        collections[name] = {
            "en_tete": with_header,
            "points": count,
            "tokens": tokens,
            "secondes_encodage": round(seconds, 1),
            "tokens_par_s": round(tokens / seconds),
            "secondes_indexation": round(time.perf_counter() - t, 1),
        }
        typer.echo(f"{name} : {count} points, encodage {seconds / 60:.1f} min")
    client.close()
    write_metrics(
        INTERIM_DIR / "metrics" / "index.json",
        {
            "passages": len(passages),
            "passages_reglement": sum(p.doc_id == REGLEMENT_DOC for p in passages),
            "ressources_exclues": excluded,
            "collections": collections,
            "secondes": {k: round(v, 1) for k, v in steps.items()},
            "device": device,
            "pic_rss_mo": round(peak_rss_bytes() / 2**20),
            "mps_alloue_mo": mps_peak or None,
            "taille_index_mo": round(dir_size(QDRANT_DIR) / 1e6, 1),
        },
        {"modele": MODEL, "batch_size": BATCH_SIZE, "max_length": MAX_LENGTH,
         "exclusions": sorted(exclusions),
         "versions": {k: version(k) for k in ("FlagEmbedding", "qdrant-client", "torch")}},
    )  # fmt: skip


def search(client, model, models, collection: str, query: str, zones: list[str] | None):
    """Recherche hybride (dense + sparse, fusion RRF), filtrée par `zones_applicables`."""
    enc = model.encode([query], max_length=512, return_dense=True, return_sparse=True,
                       return_colbert_vecs=False)  # fmt: skip
    dense, sparse = enc["dense_vecs"][0].tolist(), sparse_vector(models, enc["lexical_weights"][0])
    flt = (
        models.Filter(must=[models.FieldCondition(key="zones_applicables",
                                                  match=models.MatchAny(any=zones))])
        if zones else None
    )  # fmt: skip
    return client.query_points(
        collection,
        prefetch=[
            models.Prefetch(query=dense, using="dense", limit=PREFETCH, filter=flt),
            models.Prefetch(query=sparse, using="sparse", limit=PREFETCH, filter=flt),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=TOP_K,
    ).points


@app.command()
def demo(
    query: str,
    zone: Annotated[list[str] | None, typer.Option(help="Filtre sur zones_applicables")] = None,
    collection: str = "passages_entete",
) -> None:
    """Requête de démonstration : passages et payload (aucune mesure)."""
    from qdrant_client import QdrantClient, models

    model, _ = load_model()
    client = QdrantClient(path=str(QDRANT_DIR))
    for point in search(client, model, models, collection, query, zone):
        p = point.payload
        typer.echo(f"{point.score:.3f}  {p['doc_id']} p.{p['page_debut']}-{p['page_fin']} "
                   f"zones={p['zones_applicables']}  {' > '.join(p['chemin'])[-110:]}")  # fmt: skip
    client.close()


if __name__ == "__main__":
    try:
        app()
    except IndexBuildError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        sys.exit(1)
