"""Dossiers datés des données brutes (conventions §3, règle 1).

Chaque ressource vit dans `data/raw/<source_id>/<AAAA-MM-JJ>/<ressource>/`. La date de
référence d'une ressource (`retrieved_on` de la ressource, sinon de sa source, dans
`configs/sources.yaml`) désigne la version qui a construit les chiffres publiés ; son
manifeste est versionné.

Dossier lu par la construction, dans cet ordre :
1. la date passée explicitement (option `--date` des commandes) ;
2. la date de référence, si ce dossier contient les données (pas seulement le manifeste) ;
3. sinon le dossier daté le plus récent qui contient les données : c'est le cas d'une
   reconstruction neuve, quand la ressource a changé à la source et a été téléchargée dans
   un nouveau dossier daté (`traboule.ingestion.download`).
"""

from pathlib import Path

from traboule.config import RAW_DIR, SOURCES_CONFIG, load_sources

MANIFEST = "manifest.json"
DATE_HELP = (
    "Dossier daté des données brutes (défaut : date de référence de sources.yaml si ses données "
    "sont présentes, sinon le dossier le plus récent)"
)


class RawDataError(FileNotFoundError):
    """Ressource brute absente : à télécharger avec traboule.ingestion.download."""


def data_files(folder: Path) -> list[Path]:
    """Fichiers de données d'un dossier de ressource (tout sauf le manifeste)."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.name != MANIFEST)


def reference_date(source_id: str, resource: str, config: Path = SOURCES_CONFIG) -> str | None:
    """Date de référence d'une ressource dans sources.yaml (ressource, sinon source)."""
    for source in load_sources(config)["sources"]:
        if source["id"] != source_id:
            continue
        for r in source.get("resources") or []:
            if r["name"] == resource:
                return r.get("retrieved_on") or source.get("retrieved_on")
        return source.get("retrieved_on")
    return None


def resource_dir(
    source_id: str,
    resource: str,
    date: str | None = None,
    raw_dir: Path = RAW_DIR,
    config: Path = SOURCES_CONFIG,
) -> Path:
    """Dossier daté d'une ressource à lire pour la construction (voir l'ordre du module)."""
    base = raw_dir / source_id
    if date:
        folder = base / date / resource
        if not data_files(folder):
            raise RawDataError(f"{source_id}/{date}/{resource} : données absentes")
        return folder
    ref = reference_date(source_id, resource, config)
    if ref and data_files(base / ref / resource):
        return base / ref / resource
    dated = sorted((p for p in base.glob(f"*/{resource}") if data_files(p)), reverse=True)
    if dated:
        return dated[0]
    hint = f" (référence : {ref}, manifeste seul)" if ref else ""
    raise RawDataError(
        f"{source_id}/{resource} : aucune donnée téléchargée{hint} ; lancer "
        f"`uv run python -m traboule.ingestion.download {source_id}`"
    )


def resource_file(
    source_id: str,
    resource: str,
    date: str | None = None,
    raw_dir: Path = RAW_DIR,
    pattern: str = "*",
    config: Path = SOURCES_CONFIG,
) -> Path:
    """Fichier de données d'une ressource (un seul attendu pour le motif)."""
    folder = resource_dir(source_id, resource, date, raw_dir, config)
    files = [p for p in data_files(folder) if p.match(pattern)]
    if len(files) != 1:
        raise RawDataError(f"{folder} : {len(files)} fichier(s) « {pattern} », un seul attendu")
    return files[0]


def used(path: Path, raw_dir: Path = RAW_DIR) -> str:
    """Chemin relatif d'une donnée brute utilisée, pour les mesures (source/date/ressource)."""
    try:
        return str(path.relative_to(raw_dir))
    except ValueError:
        return str(path)
