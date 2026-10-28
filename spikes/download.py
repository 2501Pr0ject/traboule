"""Téléchargement des sources dans data/raw/<source_id>/<AAAA-MM-JJ>/ avec manifeste.

Script jetable du spike. Chaque ressource d'une source (configs/sources.yaml) est
écrite dans son sous-dossier <resource.name>/ avec un manifest.json validé par
`Manifest`. Immuabilité par ressource : chaque ressource est téléchargée dans un
dossier de travail renommé à la fin, puis passée en lecture seule (chmod -R a-w) ;
une ressource existante n'est jamais réécrite. Le dossier daté reste inscriptible
pour accueillir de nouvelles ressources (option --resource).

Contrôles :
- kind http + datagouv : sha1 et taille comparés à ceux publiés par l'API data.gouv ;
- kind wfs : nombre d'objets reçus comparé au numberMatched du serveur (resultType=hits).

Le modèle `Manifest` sera déplacé dans packages/ après le GO.
"""

import csv
import hashlib
import json
import shutil
import stat
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import typer
import yaml
from pydantic import BaseModel, ConfigDict, Field

INGESTION_VERSION = "0.1.0"

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "sources.yaml"
RAW_DIR = ROOT / "data" / "raw"
DATAGOUV_API = "https://www.data.gouv.fr/api/1"
USER_AGENT = f"traboule-download/{INGESTION_VERSION}"
CHUNK_SIZE = 1024 * 1024
PROGRESS_EVERY = 200 * CHUNK_SIZE
TIMEOUT = httpx.Timeout(30.0, read=300.0)


class Manifest(BaseModel):
    """Manifeste d'une ressource téléchargée : fait foi pour la liste des champs."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_title: str
    publisher: str
    source_url: str
    license: str
    retrieved_at: datetime
    published_at: date | None
    reference_date: date | None
    geographic_vintage: str | None
    format: str
    file_size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str | None = None
    ingestion_version: str = INGESTION_VERSION
    limitations: str | None
    crs: str | None = None


class DownloadError(RuntimeError):
    pass


app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


def load_source(source_id: str, config_path: Path) -> dict:
    config = yaml.safe_load(config_path.read_text())
    for source in config["sources"]:
        if source["id"] == source_id:
            if not source.get("resources"):
                raise DownloadError(f"{source_id} : aucune ressource déclarée")
            return source
    raise DownloadError(f"{source_id} absent de {config_path}")


def stream_to_file(client: httpx.Client, url: str, dest: Path) -> tuple[int, str, str, str]:
    """Télécharge url dans dest en streaming. Renvoie (taille, sha256, sha1, content-type)."""
    sha256, sha1, size, next_report = hashlib.sha256(), hashlib.sha1(), 0, PROGRESS_EVERY
    with client.stream("GET", url) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        with dest.open("wb") as fh:
            for chunk in response.iter_bytes(CHUNK_SIZE):
                fh.write(chunk)
                sha256.update(chunk)
                sha1.update(chunk)
                size += len(chunk)
                if size >= next_report:
                    typer.echo(f"    … {size / 1e9:.2f} Go")
                    next_report += PROGRESS_EVERY
    return size, sha256.hexdigest(), sha1.hexdigest(), content_type


def datagouv_resource(client: httpx.Client, dataset_id: str, resource_id: str) -> dict:
    response = client.get(f"{DATAGOUV_API}/datasets/{dataset_id}/")
    response.raise_for_status()
    for resource in response.json()["resources"]:
        if resource["id"] == resource_id:
            return resource
    raise DownloadError(f"ressource {resource_id} absente du jeu {dataset_id}")


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
    response = client.get(wfs_hits_url(url))
    response.raise_for_status()
    marker = 'numberMatched="'
    start = response.text.find(marker)
    if start < 0:
        raise DownloadError(f"numberMatched absent de la réponse hits : {response.text[:200]}")
    return int(response.text[start + len(marker) :].split('"', 1)[0])


def requested_srs(url: str) -> str | None:
    params = {k.lower(): v for k, v in parse_qsl(urlsplit(url).query)}
    return params.get("srsname")


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
    basename = Path(urlsplit(url).path).name
    if resource["kind"] == "http" and "." in basename:
        return basename
    extension = resource["format"].split()[0]
    return f"{resource['name']}.{extension}"


def as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def download_resource(
    client: httpx.Client, source: dict, resource: dict, dest_dir: Path
) -> Manifest:
    dest_dir.mkdir(parents=True)
    published_at = as_date(resource.get("published_at"))
    crs = resource.get("crs")
    notes = [resource["limitations"]] if resource.get("limitations") else []

    if resource["kind"] == "http":
        url = resource["url"]
        dest = dest_dir / file_name_for(resource, url)
        typer.echo(f"  {resource['name']} ← {url}")
        size, sha256, sha1, _ = stream_to_file(client, url, dest)
        if dg := resource.get("datagouv"):
            published = datagouv_resource(client, dg["dataset"], dg["resource"])
            checksum = published.get("checksum") or {}
            expected_sha1, expected_size = checksum.get("value"), published.get("filesize")
            extras = published.get("extras") or {}
            if checksum.get("type") == "sha1" and expected_sha1 != sha1:
                # Fichier remplacé sur place : le sha1 déclaré au dépôt n'est plus à jour.
                # Repli accepté seulement si l'analyse data.gouv a vu exactement ce fichier.
                if extras.get("analysis:checksum") != sha1:
                    raise DownloadError(f"sha1 différent de data.gouv : {sha1} ≠ {expected_sha1}")
                notes.append(
                    f"sha1 déclaré par data.gouv ({expected_sha1}) différent du fichier servi ; "
                    "conforme au sha1 de l'analyse data.gouv (analysis:checksum), fichier "
                    f"modifié le {extras.get('analysis:last-modified-at')} selon cette analyse."
                )
                typer.echo(f"    ATTENTION : {notes[-1]}")
            if expected_size and expected_size != size:
                raise DownloadError(f"taille différente de data.gouv : {size} ≠ {expected_size}")
            typer.echo(f"    sha1 et taille vérifiés contre data.gouv ({size:,} o)")
            published_at = published_at or as_date(published.get("last_modified"))

    elif resource["kind"] == "wfs":
        errors = []
        for url in resource["urls"]:
            dest = dest_dir / file_name_for(resource, url)
            typer.echo(f"  {resource['name']} ← {url}")
            try:
                matched = wfs_number_matched(client, url)
                size, sha256, _, _ = stream_to_file(client, url, dest)
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
            break
        else:
            raise DownloadError("toutes les URLs WFS ont échoué :\n" + "\n".join(errors))
    else:
        raise DownloadError(f"kind inconnu : {resource['kind']}")

    manifest = Manifest(
        source_id=source["id"],
        source_title=resource.get("title") or source["title"],
        publisher=source["publisher"],
        source_url=url,
        license=source["license"],
        retrieved_at=datetime.now(UTC),
        published_at=published_at,
        reference_date=as_date(resource.get("reference_date")),
        geographic_vintage=resource.get("geographic_vintage"),
        format=resource["format"],
        file_size_bytes=size,
        sha256=sha256,
        schema_version=resource.get("schema_version"),
        limitations=" ".join(notes) or None,
        crs=crs,
    )
    (dest_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest


def make_read_only(path: Path) -> None:
    """Équivalent de chmod -R a-w."""
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    for p in sorted(path.rglob("*"), reverse=True) + [path]:
        p.chmod(p.stat().st_mode & ~write_bits)


def select_resources(source: dict, names: list[str] | None) -> list[dict]:
    if not names:
        return source["resources"]
    known = {r["name"]: r for r in source["resources"]}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise DownloadError(f"ressource(s) inconnue(s) pour {source['id']} : {unknown}")
    return [known[n] for n in names]


def download_source(
    client: httpx.Client, source: dict, date_dir: Path, names: list[str] | None = None
) -> list[Manifest]:
    """Télécharge les ressources demandées dans date_dir, une par une, en lecture seule.

    Refuse avant tout téléchargement si l'une des ressources existe déjà.
    """
    resources = select_resources(source, names)
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


@app.command()
def main(
    source_id: Annotated[str, typer.Argument(help="Identifiant de source, ex. SRC-002")],
    retrieved_on: Annotated[str | None, typer.Option("--date", help="Dossier daté")] = None,
    config: Annotated[Path, typer.Option(help="Fichier sources.yaml")] = CONFIG_PATH,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    resource: Annotated[
        list[str] | None, typer.Option("--resource", help="Ressource(s) à télécharger")
    ] = None,
) -> None:
    """Télécharge les ressources d'une source (toutes, ou celles de --resource)."""
    retrieved_on = retrieved_on or date.today().isoformat()
    try:
        source = load_source(source_id, config)
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
