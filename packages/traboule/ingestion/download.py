"""Téléchargement des sources dans data/raw/<source_id>/<AAAA-MM-JJ>/<ressource>/ avec manifeste.

Conventions §3, règles 1 à 3. Chaque ressource d'une source (configs/sources.yaml) est
téléchargée dans un dossier de travail renommé à la fin, puis passée en lecture seule
(chmod -R a-w) ; une ressource existante n'est jamais réécrite ; le dossier daté reste
inscriptible. Une URL `A_CONFIRMER` est refusée.

Contrôles :
- kind http + datagouv : sha1 et taille comparés à ceux publiés par l'API data.gouv ;
- kind wfs : nombre d'objets reçus comparé au numberMatched du serveur (resultType=hits).

Usage : `uv run python -m traboule.ingestion.download SRC-002 [--resource zonage]`.
"""

import csv
import hashlib
import json
import shutil
import stat
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import typer

from traboule.config import RAW_DIR, SOURCES_CONFIG, UNCONFIRMED_URL, load_sources
from traboule.contracts.manifest import INGESTION_VERSION, Manifest

DATAGOUV_API = "https://www.data.gouv.fr/api/1"
USER_AGENT = f"traboule-download/{INGESTION_VERSION}"
CHUNK_SIZE = 1024 * 1024
PROGRESS_EVERY = 200 * CHUNK_SIZE
TIMEOUT = httpx.Timeout(30.0, read=300.0)


class DownloadError(RuntimeError):
    """Échec bloquant d'un téléchargement ou d'un contrôle."""


def find_source(config: dict, source_id: str) -> dict:
    """Renvoie la source `source_id` de la configuration, qui doit déclarer des ressources."""
    for source in config["sources"]:
        if source["id"] == source_id:
            if not source.get("resources"):
                raise DownloadError(f"{source_id} : aucune ressource déclarée")
            return source
    raise DownloadError(f"{source_id} absent de la configuration")


def resource_urls(resource: dict) -> list[str]:
    """URLs d'une ressource ; refuse une URL non confirmée (règle 3)."""
    urls = resource["urls"] if resource["kind"] == "wfs" else [resource["url"]]
    if not urls or any(UNCONFIRMED_URL in u for u in urls):
        raise DownloadError(f"{resource['name']} : URL non confirmée ({UNCONFIRMED_URL})")
    return urls


def select_resources(source: dict, names: list[str] | None) -> list[dict]:
    """Ressources demandées (toutes par défaut) ; refuse un nom inconnu."""
    if not names:
        return source["resources"]
    known = {r["name"]: r for r in source["resources"]}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise DownloadError(f"ressource(s) inconnue(s) pour {source['id']} : {unknown}")
    return [known[n] for n in names]


def stream_to_file(client: httpx.Client, url: str, dest: Path) -> tuple[int, str, str]:
    """Télécharge url dans dest en streaming. Renvoie (taille, sha256, sha1)."""
    sha256, sha1, size, next_report = hashlib.sha256(), hashlib.sha1(), 0, PROGRESS_EVERY
    with client.stream("GET", url) as response:
        response.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in response.iter_bytes(CHUNK_SIZE):
                fh.write(chunk)
                sha256.update(chunk)
                sha1.update(chunk)
                size += len(chunk)
                if size >= next_report:
                    typer.echo(f"    … {size / 1e9:.2f} Go")
                    next_report += PROGRESS_EVERY
    return size, sha256.hexdigest(), sha1.hexdigest()


def datagouv_resource(client: httpx.Client, dataset_id: str, resource_id: str) -> dict:
    """Métadonnées publiées par data.gouv pour une ressource d'un jeu."""
    response = client.get(f"{DATAGOUV_API}/datasets/{dataset_id}/")
    response.raise_for_status()
    for resource in response.json()["resources"]:
        if resource["id"] == resource_id:
            return resource
    raise DownloadError(f"ressource {resource_id} absente du jeu {dataset_id}")


def check_datagouv(published: dict, size: int, sha1: str) -> str | None:
    """Compare taille et sha1 à data.gouv. Renvoie une note si le repli d'analyse a servi.

    Un fichier remplacé sur place garde un sha1 déclaré périmé : le repli n'est accepté
    que si l'analyse data.gouv (analysis:checksum) a vu exactement ce fichier.
    """
    checksum = published.get("checksum") or {}
    extras = published.get("extras") or {}
    note = None
    if checksum.get("type") == "sha1" and checksum.get("value") != sha1:
        if extras.get("analysis:checksum") != sha1:
            raise DownloadError(f"sha1 différent de data.gouv : {sha1} ≠ {checksum.get('value')}")
        note = (
            f"sha1 déclaré par data.gouv ({checksum.get('value')}) différent du fichier servi ; "
            "conforme au sha1 de l'analyse data.gouv (analysis:checksum), fichier "
            f"modifié le {extras.get('analysis:last-modified-at')} selon cette analyse."
        )
    expected_size = published.get("filesize")
    if expected_size and expected_size != size:
        raise DownloadError(f"taille différente de data.gouv : {size} ≠ {expected_size}")
    return note


def wfs_hits_url(url: str) -> str:
    """Même requête GetFeature, mais resultType=hits et sans format de sortie."""
    parts = urlsplit(url)
    params = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in {"outputformat", "resulttype", "count", "maxfeatures"}
    ]
    params.append(("resultType", "hits"))
    return urlunsplit(parts._replace(query=urlencode(params)))


def wfs_number_matched(client: httpx.Client, url: str) -> int:
    """numberMatched annoncé par le serveur pour la requête."""
    response = client.get(wfs_hits_url(url))
    response.raise_for_status()
    marker = 'numberMatched="'
    start = response.text.find(marker)
    if start < 0:
        raise DownloadError(f"numberMatched absent de la réponse hits : {response.text[:200]}")
    return int(response.text[start + len(marker) :].split('"', 1)[0])


def requested_srs(url: str) -> str | None:
    """CRS demandé dans la requête (paramètre srsName)."""
    return {k.lower(): v for k, v in parse_qsl(urlsplit(url).query)}.get("srsname")


def count_wfs_features(path: Path, fmt: str) -> tuple[int, str | None]:
    """Compte les objets d'une réponse WFS et lit le CRS déclaré (GeoJSON seulement)."""
    if fmt == "geojson":
        try:
            data = json.loads(path.read_bytes())
        except json.JSONDecodeError as exc:
            raise DownloadError(f"réponse non JSON ({exc})") from exc
        if "features" not in data:
            raise DownloadError(f"réponse sans « features » : {str(data)[:200]}")
        crs = ((data.get("crs") or {}).get("properties") or {}).get("name")
        return len(data["features"]), crs
    if fmt == "csv":
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = ",".join(next(reader, []))
            if "ExceptionReport" in header or "<?xml" in header:
                raise DownloadError(f"le serveur a renvoyé une exception : {header[:200]}")
            return sum(1 for _ in reader), None
    raise DownloadError(f"format WFS non géré : {fmt}")


def file_name_for(resource: dict, url: str) -> str:
    """Nom du fichier : celui de l'URL pour un fichier http, sinon <ressource>.<format>."""
    basename = Path(urlsplit(url).path).name
    if resource["kind"] == "http" and "." in basename:
        return basename
    return f"{resource['name']}.{resource['format'].split()[0]}"


def as_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _fetch_http(client: httpx.Client, resource: dict, dest_dir: Path) -> dict:
    url = resource_urls(resource)[0]
    typer.echo(f"  {resource['name']} ← {url}")
    size, sha256, sha1 = stream_to_file(client, url, dest_dir / file_name_for(resource, url))
    out = {"url": url, "size": size, "sha256": sha256, "notes": [], "published_at": None}
    if dg := resource.get("datagouv"):
        published = datagouv_resource(client, dg["dataset"], dg["resource"])
        if note := check_datagouv(published, size, sha1):
            out["notes"].append(note)
            typer.echo(f"    ATTENTION : {note}")
        typer.echo(f"    sha1 et taille vérifiés contre data.gouv ({size:,} o)")
        out["published_at"] = as_date(published.get("last_modified"))
    return out


def _fetch_wfs(client: httpx.Client, resource: dict, dest_dir: Path) -> dict:
    errors = []
    for url in resource_urls(resource):
        dest = dest_dir / file_name_for(resource, url)
        typer.echo(f"  {resource['name']} ← {url}")
        try:
            matched = wfs_number_matched(client, url)
            size, sha256, _ = stream_to_file(client, url, dest)
            count, declared_crs = count_wfs_features(dest, resource["format"])
        except (DownloadError, httpx.HTTPError) as exc:
            errors.append(f"{url} : {exc}")
            typer.echo(f"    échec, URL suivante : {exc}")
            dest.unlink(missing_ok=True)
            continue
        if count != matched:
            raise DownloadError(f"{count} objets reçus, numberMatched = {matched}")
        typer.echo(f"    {count} objets = numberMatched")
        crs = declared_crs or f"{requested_srs(url)} (demandé dans la requête)"
        return {"url": url, "size": size, "sha256": sha256, "crs": crs, "notes": []}
    raise DownloadError("toutes les URLs WFS ont échoué :\n" + "\n".join(errors))


def download_resource(
    client: httpx.Client, source: dict, resource: dict, dest_dir: Path
) -> Manifest:
    """Télécharge une ressource dans dest_dir (créé) et y écrit son manifeste."""
    fetchers = {"http": _fetch_http, "wfs": _fetch_wfs}
    if resource["kind"] not in fetchers:
        raise DownloadError(f"kind inconnu : {resource['kind']}")
    dest_dir.mkdir(parents=True)
    got = fetchers[resource["kind"]](client, resource, dest_dir)
    notes = [resource["limitations"]] if resource.get("limitations") else []
    manifest = Manifest(
        source_id=source["id"],
        source_title=resource.get("title") or source["title"],
        publisher=source["publisher"],
        source_url=got["url"],
        license=source["license"],
        retrieved_at=datetime.now(UTC),
        published_at=as_date(resource.get("published_at")) or got.get("published_at"),
        reference_date=as_date(resource.get("reference_date")),
        geographic_vintage=resource.get("geographic_vintage"),
        format=resource["format"],
        file_size_bytes=got["size"],
        sha256=got["sha256"],
        schema_version=resource.get("schema_version"),
        limitations=" ".join(notes + got["notes"]) or None,
        crs=got.get("crs") or resource.get("crs"),
    )
    (dest_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest


def make_read_only(path: Path) -> None:
    """Équivalent de chmod -R a-w."""
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    for p in [*sorted(path.rglob("*"), reverse=True), path]:
        p.chmod(p.stat().st_mode & ~write_bits)


def download_source(
    client: httpx.Client, source: dict, date_dir: Path, names: list[str] | None = None
) -> list[Manifest]:
    """Télécharge les ressources demandées dans date_dir, une par une, en lecture seule.

    Refuse avant tout téléchargement si l'une des ressources existe déjà ou si une URL
    n'est pas confirmée.
    """
    resources = select_resources(source, names)
    for resource in resources:
        resource_urls(resource)
    existing = [r["name"] for r in resources if (date_dir / r["name"]).exists()]
    if existing:
        raise DownloadError(f"ressource(s) déjà présente(s) dans {date_dir} : {existing}")
    date_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for resource in resources:
        work_dir = date_dir / f".{resource['name']}.partial"
        if work_dir.exists():
            shutil.rmtree(work_dir)  # reste d'un essai interrompu, jamais validé
        manifests.append(download_resource(client, source, resource, work_dir))
        final_dir = date_dir / resource["name"]
        work_dir.rename(final_dir)
        make_read_only(final_dir)
        typer.echo(f"    ressource en lecture seule : {final_dir}")
    return manifests


app = typer.Typer(add_completion=False)


@app.command()
def main(
    source_id: Annotated[str, typer.Argument(help="Identifiant de source, ex. SRC-002")],
    retrieved_on: Annotated[str | None, typer.Option("--date", help="Dossier daté")] = None,
    config: Annotated[Path, typer.Option(help="Fichier sources.yaml")] = SOURCES_CONFIG,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    resource: Annotated[
        list[str] | None, typer.Option("--resource", help="Ressource(s) à télécharger")
    ] = None,
) -> None:
    """Télécharge les ressources d'une source (toutes, ou celles de --resource)."""
    retrieved_on = retrieved_on or date.today().isoformat()
    try:
        source = find_source(load_sources(config), source_id)
        date_dir = raw_dir / source_id / retrieved_on
        typer.echo(f"{source_id} → {date_dir}")
        with httpx.Client(
            timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            download_source(client, source, date_dir, resource)
        typer.echo("OK")
    except (DownloadError, httpx.HTTPError) as exc:
        typer.echo(f"ERREUR {source_id} : {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    app()
