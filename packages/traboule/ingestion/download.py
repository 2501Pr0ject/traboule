"""Téléchargement des sources dans data/raw/<source_id>/<AAAA-MM-JJ>/<ressource>/ avec manifeste.

Conventions §3, règles 1 à 3. Chaque ressource d'une source (configs/sources.yaml) est
téléchargée dans un dossier de travail renommé à la fin, puis passée en lecture seule
(chmod -R a-w) ; une ressource dont les données existent n'est jamais réécrite ; le dossier
daté reste inscriptible. Une URL `A_CONFIRMER` est refusée.

Dossier qui ne contient que son manifeste (manifeste versionné, données absentes, cas d'un
clone neuf) : l'immuabilité protège les données, pas le manifeste ; le téléchargement est
autorisé. Si la ressource est encore disponible à l'identique (même sha256 que le manifeste),
ses données rejoignent le dossier de référence, manifeste inchangé. Sinon, elle est
téléchargée dans le dossier daté du jour avec son propre manifeste, et l'écart est signalé.
Date par défaut : la date de référence de la ressource (`retrieved_on`), sinon le jour.

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
from traboule.ingestion.raw import MANIFEST, data_files

DATAGOUV_API = "https://www.data.gouv.fr/api/1"
USER_AGENT = f"traboule-download/{INGESTION_VERSION}"
CHUNK_SIZE = 1024 * 1024
PROGRESS_EVERY = 200 * CHUNK_SIZE
TIMEOUT = httpx.Timeout(30.0, read=300.0)
RETRIES = 3  # essais d'un téléchargement interrompu par le réseau


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
    """Télécharge url dans dest en streaming, avec RETRIES essais en cas de coupure réseau.

    Renvoie (taille, sha256, sha1) ; chaque essai repart du début du fichier.
    """
    for attempt in range(1, RETRIES + 1):
        try:
            return _stream(client, url, dest)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            if attempt == RETRIES:
                raise
            typer.echo(f"    coupure réseau ({exc}) : nouvel essai {attempt + 1}/{RETRIES}")
    raise AssertionError("inatteignable")


def _stream(client: httpx.Client, url: str, dest: Path) -> tuple[int, str, str]:
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


def _pinned_is_reference(client: httpx.Client, url: str, reference: Manifest) -> bool:
    """L'URL figée sert-elle encore un fichier de la taille du manifeste de référence ?"""
    try:
        head = client.head(url)
    except httpx.HTTPError:
        return False
    length = head.headers.get("content-length")
    return head.is_success and (length is None or int(length) == reference.file_size_bytes)


def _fetch_http(
    client: httpx.Client, resource: dict, dest_dir: Path, reference: Manifest | None = None
) -> dict:
    url = resource_urls(resource)[0]
    dest = dest_dir / file_name_for(resource, url)
    out = {"url": url, "notes": [], "published_at": None}
    dg = resource.get("datagouv")
    if reference and _pinned_is_reference(client, url, reference):
        # La taille ne sert qu'à décider d'essayer l'URL figée : seul le sha256 complet décide.
        typer.echo(f"  {resource['name']} ← {url}")
        size, sha256, _ = stream_to_file(client, url, dest)
        if sha256 == reference.sha256:
            typer.echo("    identique au manifeste de référence (sha256)")
            return out | {"size": size, "sha256": sha256}
        if not dg:
            typer.echo("    même taille, sha256 différent du manifeste de référence")
            return out | {"size": size, "sha256": sha256}
        dest.unlink()  # version figée périmée : la version courante vient de data.gouv
    published = None
    if dg:
        # Ressource mise à jour à la source : version courante publiée par data.gouv.
        published = datagouv_resource(client, dg["dataset"], dg["resource"])
        url = published.get("url") or url
        dest = dest_dir / file_name_for(resource, url)
    typer.echo(f"  {resource['name']} ← {url}")
    size, sha256, sha1 = stream_to_file(client, url, dest)
    out |= {"url": url, "size": size, "sha256": sha256}
    if published is not None:
        if note := check_datagouv(published, size, sha1):
            out["notes"].append(note)
            typer.echo(f"    ATTENTION : {note}")
        typer.echo(f"    sha1 et taille vérifiés contre data.gouv ({size:,} o)")
        out["published_at"] = as_date(published.get("last_modified"))
    return out


def _fetch_wfs(
    client: httpx.Client, resource: dict, dest_dir: Path, reference: Manifest | None = None
) -> dict:
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


def fetch_resource(
    client: httpx.Client, resource: dict, dest_dir: Path, reference: Manifest | None = None
) -> dict:
    """Télécharge les données d'une ressource dans dest_dir (créé), sans manifeste."""
    fetchers = {"http": _fetch_http, "wfs": _fetch_wfs}
    if resource["kind"] not in fetchers:
        raise DownloadError(f"kind inconnu : {resource['kind']}")
    dest_dir.mkdir(parents=True)
    return fetchers[resource["kind"]](client, resource, dest_dir, reference)


def write_manifest(
    source: dict, resource: dict, got: dict, dest_dir: Path, new_version: str = ""
) -> Manifest:
    """Manifeste d'une ressource téléchargée. `new_version` : écart avec la référence.

    Une nouvelle version ne reprend ni le titre, ni les dates de la version de référence
    décrites dans sources.yaml.
    """
    notes = [resource["limitations"]] if resource.get("limitations") else []
    if new_version:
        notes.append(new_version)
    manifest = Manifest(
        source_id=source["id"],
        source_title=source["title"] if new_version else resource.get("title") or source["title"],
        publisher=source["publisher"],
        source_url=got["url"],
        license=source["license"],
        retrieved_at=datetime.now(UTC),
        published_at=(None if new_version else as_date(resource.get("published_at")))
        or got.get("published_at"),
        reference_date=None if new_version else as_date(resource.get("reference_date")),
        geographic_vintage=resource.get("geographic_vintage"),
        format=resource["format"],
        file_size_bytes=got["size"],
        sha256=got["sha256"],
        schema_version=resource.get("schema_version"),
        limitations=" ".join(notes + got["notes"]) or None,
        crs=got.get("crs") or resource.get("crs"),
    )
    (dest_dir / MANIFEST).write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest


def download_resource(
    client: httpx.Client, source: dict, resource: dict, dest_dir: Path
) -> Manifest:
    """Télécharge une ressource dans dest_dir (créé) et y écrit son manifeste."""
    got = fetch_resource(client, resource, dest_dir)
    return write_manifest(source, resource, got, dest_dir)


def make_read_only(path: Path) -> None:
    """Équivalent de chmod -R a-w."""
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    for p in [*sorted(path.rglob("*"), reverse=True), path]:
        p.chmod(p.stat().st_mode & ~write_bits)


def reference_manifest(folder: Path) -> Manifest | None:
    """Manifeste d'un dossier qui ne contient que lui (données absentes), sinon None."""
    if folder.is_dir() and not data_files(folder) and (folder / MANIFEST).exists():
        return Manifest.model_validate_json((folder / MANIFEST).read_text(encoding="utf-8"))
    return None


def download_source(
    client: httpx.Client,
    source: dict,
    date_dir: Path,
    names: list[str] | None = None,
    today: str | None = None,
) -> list[tuple[Manifest, Path, str]]:
    """Télécharge les ressources demandées dans date_dir, une par une, en lecture seule.

    Refuse avant tout téléchargement si une URL n'est pas confirmée. Une ressource dont les
    données existent n'est jamais réécrite : elle est ignorée, et la commande peut être
    relancée après une interruption. Renvoie (manifeste, dossier, statut) par ressource ;
    statut : « téléchargée », « identique à la référence », « écart » (nouveau dossier) ou
    « déjà présente ».
    """
    today = today or date.today().isoformat()
    resources = select_resources(source, names)
    for resource in resources:
        resource_urls(resource)
    # Dossier sans données ni manifeste : état incohérent, à examiner avant tout téléchargement.
    broken = [
        r["name"]
        for r in resources
        if (date_dir / r["name"]).exists()
        and not data_files(date_dir / r["name"])
        and reference_manifest(date_dir / r["name"]) is None
    ]
    if broken:
        raise DownloadError(f"dossier(s) sans données ni manifeste dans {date_dir} : {broken}")
    date_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for resource in resources:
        name = resource["name"]
        target = date_dir / name
        if data_files(target):
            # Données déjà présentes : jamais réécrites ; la commande peut être relancée.
            typer.echo(f"  {name} : déjà présente dans {target}, non réécrite")
            manifest = Manifest.model_validate_json((target / MANIFEST).read_text(encoding="utf-8"))
            results.append((manifest, target, "déjà présente"))
            continue
        reference = reference_manifest(target)
        done = date_dir.parent / today / name
        if reference is not None and data_files(done):
            typer.echo(f"  {name} : écart déjà téléchargé dans {done}")
            manifest = Manifest.model_validate_json((done / MANIFEST).read_text(encoding="utf-8"))
            results.append((manifest, done, "écart"))
            continue
        work_dir = date_dir / f".{name}.partial"
        if work_dir.exists():
            shutil.rmtree(work_dir)  # reste d'un essai interrompu, jamais validé
        got = fetch_resource(client, resource, work_dir, reference)
        if reference is None:
            manifest = write_manifest(source, resource, got, work_dir)
            work_dir.rename(target)
            final, status = target, "téléchargée"
        elif got["sha256"] == reference.sha256:
            for path in data_files(work_dir):
                path.rename(target / path.name)
            shutil.rmtree(work_dir)
            manifest, final, status = reference, target, "identique à la référence"
        else:
            final = date_dir.parent / today / name
            if final.exists() or today == date_dir.name:
                shutil.rmtree(work_dir)
                raise DownloadError(f"{name} : écart avec la référence, et {final} existe déjà")
            note = (
                f"Version différente de la référence du {date_dir.name} (sha256 "
                f"{reference.sha256[:8]} → {got['sha256'][:8]}) : ressource modifiée à la source."
            )
            manifest = write_manifest(source, resource, got, work_dir, new_version=note)
            final.parent.mkdir(parents=True, exist_ok=True)
            work_dir.rename(final)
            status = "écart"
            typer.echo(f"    ÉCART : {note} Téléchargée dans {final}")
        make_read_only(final)
        typer.echo(f"    ressource en lecture seule : {final}")
        results.append((manifest, final, status))
    return results


app = typer.Typer(add_completion=False)


@app.command()
def main(
    source_id: Annotated[str, typer.Argument(help="Identifiant de source, ex. SRC-002")],
    retrieved_on: Annotated[
        str | None,
        typer.Option("--date", help="Dossier daté (défaut : date de référence, sinon le jour)"),
    ] = None,
    config: Annotated[Path, typer.Option(help="Fichier sources.yaml")] = SOURCES_CONFIG,
    raw_dir: Annotated[Path, typer.Option(help="Racine des données brutes")] = RAW_DIR,
    resource: Annotated[
        list[str] | None, typer.Option("--resource", help="Ressource(s) à télécharger")
    ] = None,
) -> None:
    """Télécharge les ressources d'une source (toutes, ou celles de --resource)."""
    today = date.today().isoformat()
    try:
        source = find_source(load_sources(config), source_id)
        groups: dict[str, list[str]] = {}
        for r in select_resources(source, resource):
            day = retrieved_on or r.get("retrieved_on") or source.get("retrieved_on") or today
            groups.setdefault(day, []).append(r["name"])
        results = []
        with httpx.Client(
            timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            for day, names in groups.items():
                typer.echo(f"{source_id} → {raw_dir / source_id / day}")
                results += download_source(client, source, raw_dir / source_id / day, names, today)
        gaps = [final for _, final, status in results if status == "écart"]
        typer.echo(f"OK ({len(results)} ressource(s), {len(gaps)} écart(s) avec la référence)")
        for final in gaps:
            typer.echo(f"  écart : {final.relative_to(raw_dir)}")
    except (DownloadError, httpx.HTTPError) as exc:
        typer.echo(f"ERREUR {source_id} : {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    app()
