# Conventions d'ingénierie

Ce document fait foi pour les règles techniques de Traboule. Le périmètre fonctionnel est défini dans [`cadrage-v1.md`](cadrage-v1.md) et l'[ADR-0001](decisions/ADR-0001-perimetre-v1.md) ; les sources dans le [registre](sources/registre.md).

Une règle ne change que par un ADR (`docs/decisions/`).

## 1. Contraintes matérielles

- Machine de référence : MacBook Air M2, 16 Go de RAM, sans GPU distant.
- Aucun gros fichier n'est chargé entier en mémoire. Le stock Sirene national (plusieurs Go) est filtré en streaming avec DuckDB (`read_csv` / `read_parquet` + `WHERE`) et écrit en Parquet.
- Toute opération lourde (filtrage, indexation, embeddings) consigne son pic mémoire et son temps. Méthode :
  - **une opération lourde = une commande = un processus**, pour que le pic mémoire du processus soit celui de l'étape ;
  - pic mémoire lu par `resource.getrusage` via une fonction unique, `traboule.measure.peak_rss_bytes`, qui convertit `ru_maxrss` selon la plateforme (octets sous macOS, kilo-octets sous Linux) ;
  - la mémoire MPS des embeddings se lit à part avec `torch.mps` (`current_allocated_memory`, `driver_allocated_memory`) ;
  - les mesures sont écrites dans un fichier avec la configuration et les versions (§8).
- Accélération : `mps` si PyTorch le voit, sinon CPU. Le device utilisé est toujours consigné.

## 2. Stack

| Rôle | Choix |
|---|---|
| Langage, environnement | Python 3.12, **uv** (`uv add`, `uv run`) ; ni pip direct, ni conda |
| Données structurées | DuckDB + extension `spatial`, Polars, PyArrow, Parquet |
| Contrats de données | Pydantic v2 |
| Réseau, configuration, CLI | httpx, PyYAML, Typer |
| PDF | PyMuPDF pour le texte du règlement ; Docling pour les cahiers communaux et les pages à tableaux (ADR-0008) |
| Embeddings | BGE-M3 (candidat, validé par le spike) |
| Index vectoriel | Qdrant : mode local embarqué (`QdrantClient(path=...)`) pour le spike, serveur Docker pour les benchmarks |
| Génération | Ollama, modèle local 7–8B quantifié, choisi après mesure ; aucune API LLM distante dans le code applicatif |
| Qualité | pytest, ruff |

## 3. Règles de données

1. **Données brutes immuables, par ressource.** Chaque ressource est stockée dans `data/raw/<source_id>/<AAAA-MM-JJ>/<ressource>/` avec son manifeste ; une fois le manifeste écrit, le script de téléchargement passe ce dossier de ressource en lecture seule (`chmod -R a-w`), et une ressource existante n'est jamais modifiée ni réécrite. Le dossier daté reste inscriptible pour accueillir de nouvelles ressources ; une nouvelle version d'une ressource va dans un nouveau dossier daté. Rendre une ressource de nouveau inscriptible est une action manuelle et délibérée. Toute transformation écrit dans `data/interim/` ou `data/processed/`.
2. **Un manifeste par téléchargement** (`manifest.json` à côté du fichier). Ses champs sont définis par le modèle Pydantic `Manifest` (`traboule.contracts.manifest`, utilisé par `traboule.ingestion`), qui fait foi.
3. **Aucune URL inventée.** Les URLs de ressources se résolvent via l'API data.gouv.fr (`https://www.data.gouv.fr/api/1/datasets/<id-ou-slug>/`) ou la page officielle de l'INSEE. Une URL non confirmée reste `A_CONFIRMER` dans `configs/sources.yaml`.
4. **Codes officiels comme clés de jointure**, jamais des noms : code commune INSEE, SIRET, code IRIS, code de zone.
5. **Lyon et ses arrondissements.** La commune 69123 et ses 9 arrondissements municipaux (69381–69389) ne sont jamais additionnés ni confondus. Chaque table déclare son niveau géographique.
6. **Millésimes géographiques.** La Métropole compte 58 communes depuis le 1er janvier 2024 (regroupement Oullins + Pierre-Bénite) ; le PLU-H a été conçu sur 59 communes. Chaque table porte son millésime COG ; le passage entre millésimes se fait par une table de correspondance documentée et testée.
7. **Comptages spatiaux : minorant chiffré.** Un établissement est **sans position publique** s'il n'a pas de coordonnées **ou** s'il est en statut `P` (règle 10). Un comptage spatial n'est jamais présenté comme exhaustif : il donne le nombre d'établissements de même périmètre (activité, état) sans position publique. Pour un comptage dans une zone, ce nombre porte sur les **communes qui intersectent la zone** (intersection de plus de 100 m², pour écarter les contacts de bordure) et se formule « jusqu'à N établissements supplémentaires pourraient se trouver dans la zone ».
8. **Gros fichiers hors Git.** `data/` est ignoré ; seuls les manifestes et de petits échantillons de test sont versionnés (jamais extraits de Sirene, voir règle 9).
9. **Les données Sirene brutes ne sont jamais republiées**, ni en totalité ni en extrait au niveau établissement : obligations liées aux données personnelles (entrepreneurs individuels) et oppositions à la diffusion survenues après l'instantané téléchargé. Le dépôt publie les scripts, les manifestes et des agrégats.
10. **Le statut de diffusion du stock INSEE le plus récent prévaut.** Un établissement en statut `P` dans le stock SRC-001a le plus récent n'a **aucune position** dans Traboule, quelle que soit la source : ni les coordonnées du fichier de géolocalisation SRC-001b (qui en porte pour certains établissements en statut `P`, voir le registre), ni celles de SRC-007. Il est exclu des tables de jointure spatiale (`etablissements_zones`) et de toute jointure spatiale ; il compte parmi les établissements sans position publique (règle 7).

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
- Une citation donne la **version de la pièce** citée (procédure lue dans la pièce, ex. « Modification n°4, approbation 2024 » pour un cahier communal), pas seulement la version de publication du document au GPU.
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

- Code et identifiants en anglais ; documentation, ADR et description des messages de commit en français (§9).
- Fonctions typées ; Pydantic pour les contrats de données ; pas de logique dans les notebooks.
- Un script = une responsabilité ; options par Typer ; chemins via `pathlib`.
- Toute métrique est écrite dans un fichier (JSON ou CSV) avec la configuration et les versions des dépendances.
- Pendant le spike, le code reste dans `spikes/` (jetable) ; `packages/` n'accueille que du code réécrit et testé après le GO.

## 9. Git

- Messages au format **Conventional Commits** : `type(portée): description`.
  - **Type et portée en anglais** : types `feat`, `fix`, `docs`, `test`, `refactor`, `chore` ; portée = sous-paquet ou domaine (`ingestion`, `geo`, `contracts`, `gold`, `spike`, `adr`, `conventions`…), facultative.
  - **Description en français**, nominale et factuelle (ce que contient le commit), sans consigne : `feat(geo): jointure spatiale avec exclusion des statuts P`, `fix(ingestion): filtre epsg de la géolocalisation`.
  - **Titre de 72 caractères au plus** ; les précisions vont dans le corps, séparé du titre par une ligne vide.
- Commits petits et atomiques.
- Jalons marqués par des tags annotés (`spike-test1` … `spike-synthese`, `cadrage-v0.3`) ; un document cite un tag, jamais une empreinte de commit.
- Pas de push sans décision explicite.
