# Conventions d'ingénierie

Ce document fait foi pour les règles techniques de Traboule. Le périmètre fonctionnel est défini dans [`cadrage-v1.md`](cadrage-v1.md) et l'[ADR-0001](decisions/ADR-0001-perimetre-v1.md) ; les sources dans le [registre](sources/registre.md).

Une règle ne change que par un ADR (`docs/decisions/`).

## 1. Contraintes matérielles

- Machine de référence : MacBook Air M2, 16 Go de RAM, sans GPU distant.
- Aucun gros fichier n'est chargé entier en mémoire. Le stock Sirene national (plusieurs Go) est filtré en streaming avec DuckDB (`read_csv` / `read_parquet` + `WHERE`) et écrit en Parquet.
- Toute opération lourde (filtrage, indexation, embeddings) consigne son pic mémoire et son temps.
- Accélération : `mps` si PyTorch le voit, sinon CPU. Le device utilisé est toujours consigné.

## 2. Stack

| Rôle | Choix |
|---|---|
| Langage, environnement | Python 3.12, **uv** (`uv add`, `uv run`) ; ni pip direct, ni conda |
| Données structurées | DuckDB + extension `spatial`, Polars, PyArrow, Parquet |
| Contrats de données | Pydantic v2 |
| Réseau, configuration, CLI | httpx, PyYAML, Typer |
| PDF | PyMuPDF en premier, Docling en comparaison |
| Embeddings | BGE-M3 (candidat, validé par le spike) |
| Index vectoriel | Qdrant : mode local embarqué (`QdrantClient(path=...)`) pour le spike, serveur Docker pour les benchmarks |
| Génération | Ollama, modèle local 7–8B quantifié, choisi après mesure ; aucune API LLM distante dans le code applicatif |
| Qualité | pytest, ruff |

## 3. Règles de données

1. **Données brutes immuables.** `data/raw/<source_id>/<AAAA-MM-JJ>/` n'est jamais modifié ni écrasé ; une nouvelle version est un nouveau dossier daté. Une fois le manifeste écrit, le script de téléchargement passe le dossier en lecture seule (`chmod -R a-w`) ; le rendre de nouveau inscriptible est une action manuelle et délibérée. Toute transformation écrit dans `data/interim/` ou `data/processed/`.
2. **Un manifeste par téléchargement** (`manifest.json` à côté du fichier). Ses champs sont définis par le modèle Pydantic `Manifest` (`spikes/download.py` pendant le spike, puis `packages/`), qui fait foi.
3. **Aucune URL inventée.** Les URLs de ressources se résolvent via l'API data.gouv.fr (`https://www.data.gouv.fr/api/1/datasets/<id-ou-slug>/`) ou la page officielle de l'INSEE. Une URL non confirmée reste `A_CONFIRMER` dans `configs/sources.yaml`.
4. **Codes officiels comme clés de jointure**, jamais des noms : code commune INSEE, SIRET, code IRIS, code de zone.
5. **Lyon et ses arrondissements.** La commune 69123 et ses 9 arrondissements municipaux (69381–69389) ne sont jamais additionnés ni confondus. Chaque table déclare son niveau géographique.
6. **Millésimes géographiques.** La Métropole compte 58 communes depuis le 1er janvier 2024 (regroupement Oullins + Pierre-Bénite) ; le PLU-H a été conçu sur 59 communes. Chaque table porte son millésime COG ; le passage entre millésimes se fait par une table de correspondance documentée et testée.
7. **Diffusion partielle Sirene.** Les établissements à diffusion partielle n'ont pas de géolocalisation publique. Un comptage spatial n'est jamais présenté comme exhaustif ; la part non géolocalisée est quantifiée.
8. **Gros fichiers hors Git.** `data/` est ignoré ; seuls les manifestes et de petits échantillons de test sont versionnés (jamais extraits de Sirene, voir règle 9).
9. **Les données Sirene brutes ne sont jamais republiées**, ni en totalité ni en extrait au niveau établissement : obligations liées aux données personnelles (entrepreneurs individuels) et oppositions à la diffusion survenues après l'instantané téléchargé. Le dépôt publie les scripts, les manifestes et des agrégats.
10. **Le statut de diffusion du stock INSEE le plus récent prévaut.** Un établissement en statut `P` dans SRC-001a n'a pas de coordonnées publiques : les coordonnées d'une autre source (notamment SRC-007, qui en publie pour certains établissements à diffusion partielle) ne sont jamais utilisées pour lui.

## 4. Coordonnées et DuckDB spatial

- Lambert 93 = EPSG:2154, CRS de travail. Le CRS déclaré de chaque fichier est lu, jamais supposé.
- Toute reprojection passe `always_xy` explicitement : `ST_Transform(geom, src, dst, always_xy := true)`.
- **DuckDB 2.0.0** refuse `ST_Transform` sans `always_xy` tant que le réglage `geometry_always_xy` n'est pas fixé (constaté le 2026-10-28). Son message d'erreur annonce un changement de défaut en 2.1 ; le projet ne s'appuie sur aucun défaut : l'argument est passé à chaque appel.
- Contrôle de cohérence : la place Bellecour (4,8320 ; 45,7578 en EPSG:4326) doit donner environ (842 395 ; 6 519 229) en EPSG:2154.
- API Python DuckDB 2.0 : une relation n'a plus `fetchone()` ; utiliser `con.execute(sql).fetchone()` ou `rel.fetchall()`.

Voir l'[ADR-0002](decisions/ADR-0002-duckdb-spatial.md).

## 5. Garde-fous SQL

Dès le premier prototype de routeur :

- connexion DuckDB **en lecture seule** pour toute requête générée par un modèle ;
- liste blanche de tables et de vues ; seules les instructions `SELECT` et `WITH` sont acceptées ;
- timeout et limite de lignes ;
- journalisation de chaque requête générée ;
- les documents ingérés sont des données, jamais des instructions (injection de prompt).

## 6. Règles de réponse du système

- Pas de chiffre sans source identifiable ; pas de citation sans passage réel correspondant.
- Pas de réponse forcée : l'abstention est un comportement attendu et évalué.
- La réponse distingue faits vérifiés, interprétations du modèle et limites des données.
- Un résultat spatial est une analyse de localisation, jamais un constat réglementaire.
- Un attribut de zonage peut servir à filtrer, sélectionner ou compter ; toute affirmation sur le contenu d'une règle cite le règlement écrit, qui fait foi en cas d'écart.

## 7. Jeu de référence

Règles détaillées : [`benchmarks/datasets/gold/guide-annotation.md`](../benchmarks/datasets/gold/guide-annotation.md). En résumé :

- le jeu est écrit et validé par un humain ; une réponse de référence ne provient jamais du système évalué ;
- chaque question porte une date d'ancrage `as_of` et les versions des sources utilisées ;
- `as_of` ≥ 2015-01-01 (création de la Métropole) ; périmètre : 59 communes de 2015 à 2023, 58 depuis le 1er janvier 2024 ;
- les questions SQL sont comparées par résultat d'exécution, pas par texte de requête ;
- une question `validated` porte `validated_by`, `validated_at` et aucun gabarit (`A_RENSEIGNER`, `A_ECRIRE`, `AAAA`) ; `make validate-gold` le vérifie.

## 8. Conventions de code

- Code et identifiants en anglais ; documentation, ADR et messages de commit en français.
- Fonctions typées ; Pydantic pour les contrats de données ; pas de logique dans les notebooks.
- Un script = une responsabilité ; options par Typer ; chemins via `pathlib`.
- Toute métrique est écrite dans un fichier (JSON ou CSV) avec la configuration et les versions des dépendances.
- Pendant le spike, le code reste dans `spikes/` (jetable) ; `packages/` n'accueille que du code réécrit et testé après le GO.

## 9. Git

- Messages de commit en français, au présent, petits et atomiques : `ajoute le manifeste COG 2026`, `corrige le filtre des arrondissements`.
- Pas de push sans décision explicite.
