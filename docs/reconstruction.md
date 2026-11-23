# Reconstructions depuis un clone neuf

## Première reconstruction, commande par commande — 2026-11-22

Démarrage rapide complet joué dans un clone neuf (version qui exige un stock et une géolocalisation Sirene du même mois ; l'index a été construit après la correction de sa commande, sous-commande `build`, et la base après celle des millésimes, tirés des données réellement lues), sur la machine de référence : Apple M2, 16 Go. Les caches de uv (paquets Python), de Hugging Face (BGE-M3, modèles Docling, tokenizer Qwen3) et d'Ollama (`qwen3:8b`) étaient déjà présents : sur une machine neuve, le premier téléchargement des modèles (environ 14 Go) et des paquets s'ajoute aux durées ci-dessous et n'a pas été mesuré.

### Durées

| Étape | Commande | Durée |
|---|---|---:|
| Clone | `git clone …` | < 1 s |
| Installation | `make setup` | 2 s (cache uv) |
| Tests | `make test` | 17 s |
| Téléchargement, 9 sources (4,2 Go) | `uv run python -m traboule.ingestion.download <source>` | 7 min 18 s |
| — dont stock Sirene (SRC-001a) | | 3 min 40 s |
| — dont géolocalisation Sirene (SRC-001b) | | 1 min 15 s |
| — dont pièces du PLU-H, 79 ressources (SRC-005) | | 2 min 16 s |
| — dont les 6 autres sources | | 6 s |
| Référentiel | `uv run python -m traboule.geo.referentiel` | 1 s |
| Sirene | `uv run python -m traboule.ingestion.sirene` | 5 s |
| Jointure spatiale | `uv run python -m traboule.geo.jointure` | 4 min 43 s |
| Contrôle zones → règlement | `uv run python -m traboule.geo.zones_reglement --check` | 3 s |
| Base DuckDB | `uv run python -m traboule.ingestion.database` | 3 s |
| Règlement | `uv run python -m traboule.retrieval.reglement` | 2 min 32 s |
| Cahiers (76, Docling) | `uv run python -m traboule.retrieval.cahiers` | 41 min 49 s |
| Ligatures | `uv run python -m traboule.retrieval.ligatures` | 18 s |
| Renvois | `uv run python -m traboule.retrieval.renvois` | < 1 s |
| Index (2 × 7 254 passages, BGE-M3) | `uv run python -m traboule.retrieval.index build` | 47 min 35 s |
| Modèle (déjà présent) | `ollama pull qwen3:8b` | 1 s |
| Question SQL | `uv run traboule ask …` | 1 s |
| Question mixte, RAG, chargement des modèles compris | `uv run traboule ask …` | 49 s |
| **Téléchargement et construction** | | **1 h 44 min** |

Écart au protocole : la première tentative de l'index a échoué (`index` lancé sans la sous-commande `build`, telle que l'indiquait la documentation du module, depuis corrigée) ; l'étape a été relancée seule.

### Pics de mémoire

Sirene 4,4 Go ; cahiers 3,4 Go ; index 4,1 Go, plus 2,2 Go de mémoire du processeur graphique ; règlement 1,5 Go ; jointure 1,2 Go ; base 0,5 Go (mesures de `data/interim/metrics/`, champ du pic de chaque étape).

### Espace disque

Données brutes 4,2 Go ; données intermédiaires 0,1 Go ; base et index 0,3 Go ; environnement Python 1,8 Go. Caches hors du clone (mesurés sur la machine de référence) : BGE-M3 8,5 Go (dépôt Hugging Face complet, ONNX compris), `qwen3:8b` 5,2 Go.

### Mémoire à l'usage (base de référence, 2026-11-22)

`traboule ask` en RAG : pic de 2,9 Go pour le processus (BGE-M3 sur processeur) ; en CAG : 0,3 Go (BGE-M3 non chargé). Serveur Ollama (`ollama ps`) : 6,3 Go avec une fenêtre de 16 384 tokens, 6,8 Go avec 22 528 tokens, 100 % sur le processeur graphique.

### Ressources : identiques ou en écart avec la référence

| Source | Résultat |
|---|---|
| SRC-004a, SRC-004b, SRC-004c (archives INSEE) | identiques (sha256 du manifeste) |
| SRC-005 : règlement, 76 cahiers, plan de secteurs | identiques |
| SRC-001a et SRC-001b : notices | identiques |
| SRC-001a : stock Sirene | écart : stock de novembre 2026 (URL courante de data.gouv) |
| SRC-001b : géolocalisation | écart : géolocalisation de novembre 2026, publiée le 2026-11-21 |
| SRC-002 : zonage du PLU-H (WFS) | écart |
| SRC-005 : liste des pièces | écart |
| REF-COMMUNES-ML-2024, REF-ARRONDISSEMENTS-LYON (WFS) | écart |

Chaque écart a été téléchargé dans le dossier daté du 2026-11-22 avec son propre manifeste ; les dossiers de référence ont gardé leur seul manifeste. Le contrôle d'appariement Sirene a accepté la paire stock et géolocalisation de novembre 2026 ; la correspondance zones → règlement est restée à jour avec le zonage du 2026-11-22.

### Chiffres : référence et reconstruction

| Mesure | Référence (stock du 2026-10-01) | Reconstruction (stock du 2026-11-01) |
|---|---:|---:|
| Établissements de la Métropole (actifs et fermés) | 1 139 191 | 1 145 427 |
| Positions publiques rattachées au zonage | 956 708 | 959 966 |
| Actifs en zone UEi1 à Vénissieux (haute, moyenne, faible) | 1 479 (1 069, 214, 196) | 1 487 (1 075, 216, 196) |
| Minorant, UEi1 à Vénissieux | 2 211 | 2 274 |
| Actifs en zone UEp (haute, moyenne, faible) | 101 (39, 49, 13) | 101 (39, 49, 13) |
| Minorant, UEp | 7 582 | 7 722 |
| Passages indexés (règlement + cahiers) | 7 254 (1 827 + 5 427) | 7 254 (1 827 + 5 427) |

La réponse documentaire sur le coefficient de pleine terre en zone UEp est la même (mêmes passages cités, p. 674 et 675). Les réponses de la reconstruction citent le stock Sirene du 2026-11-01, la géolocalisation de novembre 2026 et le zonage du 2026-11-22 (millésimes tirés des données réellement lues, et non plus de la date de référence).

## Seconde reconstruction, par les cibles make — 2026-11-23

Même machine, clone neuf (version qui ajoute les cibles `make download` et `make build`, mise à jour avant la relance du téléchargement par la correction décrite plus bas), mêmes caches de modèles et de paquets. Commandes du démarrage rapide : `make setup`, `ollama pull qwen3:8b`, `make download`, `make build`.

### Durées

| Étape | Durée |
|---|---:|
| `make setup` (cache uv) | 1 s |
| `ollama pull qwen3:8b` (déjà présent) | 1 s |
| `make download`, première tentative : stock Sirene téléchargé, puis géolocalisation arrêtée par une coupure réseau (`The read operation timed out`) | 11 min |
| `make download`, relance (ressources déjà présentes gardées ; une coupure retentée automatiquement) | 4 min 36 s |
| `make build`, durée de calcul | 1 h 14 min |
| — dont référentiel, Sirene, contrôle zones → règlement et base | 15 s |
| — dont jointure spatiale (calcul mesuré : 288 s) | 4 min 48 s |
| — dont règlement | 2 min 38 s |
| — dont cahiers (76, Docling) | 36 min 46 s |
| — dont ligatures et renvois | 18 s |
| — dont index (2 × 7 254 passages, BGE-M3) | 28 min 51 s |
| Question SQL (`traboule ask`) | 1 s |

La coupure réseau a conduit à rendre le téléchargement relançable : une ressource déjà présente est gardée, jamais réécrite, et une lecture interrompue est retentée deux fois.

Écart au protocole : la machine s'est mise en veille de 01:17 à 01:47 pendant la jointure (journal `pmset`), ce qui porte la durée écoulée de `make build` à 1 h 42 min ; la durée de calcul ci-dessus l'exclut. Lancer la construction avec `caffeinate -i` évite cette veille.

Rien d'autre ne tournait pendant la construction, hors la suite de tests (environ 30 s, pendant les cahiers) ; le serveur web et Ollama ont été démarrés après la fin.

### Pics de mémoire

Sirene 4,8 Go ; index 4,3 Go, plus 2,2 Go de mémoire du processeur graphique ; cahiers 3,7 Go ; jointure 1,2 Go ; base 0,6 Go.

### Ressources et chiffres

Mêmes écarts que le 2026-11-22 (stock et géolocalisation Sirene de novembre 2026, zonage, liste des pièces et contours communaux téléchargés le jour même), mêmes ressources identiques à la référence. Chiffres identiques à ceux de la reconstruction du 2026-11-22 : 1 145 427 établissements, 959 966 positions publiques rattachées au zonage, 1 487 actifs en zone UEi1 à Vénissieux (1 075, 216, 196), minorant 2 274, 7 254 passages indexés (1 827 + 5 427).

### Réponse CAG, cache froid et cache chaud

Sur la base de référence, après la construction : question « Quel est le coefficient d'emprise au sol en zone URm1 ? » en CAG, 231 s à la première question (lecture du chapitre), 6 s à la suivante, même réponse bloquée (passage cité hors du sujet demandé). `ollama ps` : 6,8 Go, 100 % sur le processeur graphique, fenêtre de 22 528 tokens.
