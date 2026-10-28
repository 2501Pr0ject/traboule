# Traboule — Cadrage de la v1

**Version :** 0.2 (intègre la revue du 27/10/2026)
**Statut :** validé sous réserve du spike de faisabilité
**Objectif de livraison :** 4 à 6 semaines après GO du spike (objectif, pas promesse)
**Environnement :** MacBook Air M2, 16 Go de RAM
**Évaluation :** RAGnarok-AI

## Changements par rapport à la v0.1

| Point | v0.1 | v0.2 |
|---|---|---|
| Laboratoire retrieval | Ambigu (multivecteur « conditionnel ») | v1 = dense/sparse/hybride/reranking ; multivecteur + quantification + benchmark anglais en **v1.1** (ADR-0001) |
| Géographie | Absente | **Centrale** : jointure spatiale établissement → zone PLU-H (fonctionnalité signature) |
| Source Sirene | Jeu dérivé de la Métropole | **Stock INSEE + fichier de géolocalisation INSEE** ; jeu Métropole en contrôle croisé (ADR-0003) |
| Version du PLU-H | Non traitée | **Géoportail de l'Urbanisme** comme référence de version opposable (ADR-0004) |
| Questions sans réponse | Cas faciles (prévision future) | **Quasi-réponses** : information proche mais insuffisante |
| Ancrage temporel | Implicite | Chaque question porte une date `as_of` et les versions de sources |
| Sécurité SQL | Absente | Lecture seule, liste blanche, timeout, limite de lignes |
| Démonstration | API seule | Interface web minimale + vidéo de 2 minutes |
| Semaine 1 | 30 questions + tout le reste | 15 questions en semaine 1, 30 en semaine 2 |

## 1. Vision

Permettre à un utilisateur d'interroger la Métropole de Lyon — ses établissements, son zonage d'urbanisme et les règles qui s'y appliquent — et d'obtenir des réponses vérifiables, sourcées, ancrées dans le temps, avec une abstention explicite quand les données ne suffisent pas.

**Objectif produit :** un moteur de connaissance territorial fiable, traçable, exécutable localement.
**Objectif d'ingénierie :** un système mesurable, où chaque stratégie (retrieval, routage, construction de contexte) est comparée sur un jeu de référence versionné.

## 2. Types de questions

| Type | Route attendue | Exemple (à préciser après inventaire) |
|---|---|---|
| Factuelle | `SQL` | Combien d'établissements actifs de la section NAF C sont géolocalisés dans le 7e arrondissement au `as_of` du stock ? |
| Documentaire | `RAG` | Que prévoit le règlement du PLU-H pour la hauteur des constructions en zone X ? |
| Mixte (signature) | `HYBRID` | Combien d'établissements industriels sont situés en zone d'activités économiques, et que dit le règlement de ces zones sur les extensions ? |
| Sans réponse | `ABSTAIN` | Quasi-réponses : donnée à un niveau non chargé, zone inexistante, date hors de la version, établissement à diffusion partielle |

## 3. Périmètre

### 3.1 Inclus en v1

1. Pipeline d'ingestion reproductible avec manifestes.
2. Registre des sources et versions (`docs/sources/registre.md`, `configs/sources.yaml`).
3. DuckDB + extension spatiale ; tables documentées avec niveau géographique et millésime.
4. Jointure spatiale établissements ↔ zonage PLU-H, avec taux de géolocalisation et qualité documentés.
5. Extraction et découpage du règlement du PLU-H, chaque passage relié à son document, sa page, sa zone.
6. Qdrant : dense, sparse, hybride, hybride + reranking.
7. Routeur `SQL | RAG | HYBRID | ABSTAIN` avec garde-fous SQL.
8. Construction de contexte contrôlée (budget, déduplication, provenance).
9. Génération locale de réponses sourcées et abstention.
10. Jeu de référence versionné (~150 questions validées manuellement).
11. Évaluation RAGnarok-AI, étendue pour le routage et l'exactitude SQL.
12. Benchmark public français de retrieval (candidats : tâches françaises de MTEB).
13. Interface web minimale : question, route choisie, réponse, sources consultables.
14. Rapport de résultats, limites et vidéo de démonstration.

### 3.2 v1.1

Multivecteurs (BGE-M3 ColBERT), quantification (TurboQuant, Turbo4 — à revérifier dans la documentation Qdrant au moment de s'y mettre), benchmark anglais pour se comparer aux résultats publiés.

### 3.3 Exclus

GraphRAG, KAG, CAG, TimesFM, vLLM, Neo4j, PostgreSQL, framework d'agents, fine-tuning, multi-utilisateur, déploiement cloud, indexation exhaustive des données publiques.

## 4. Architecture v1

```
Sources officielles ──► data/raw (immuable + manifestes)
                          │
                          ▼
              normalisation (Polars / DuckDB)
                │                         │
                ▼                         ▼
   DuckDB + spatial                Extraction PDF → passages
   (établissements, zonage,        (doc_id, page, zone, version)
    référentiels, correspondances)        │
                │                         ▼
                │                 Qdrant (dense / sparse / hybride)
                │                         │
                └──────► Routeur ◄────────┘
                   SQL | RAG | HYBRID | ABSTAIN
                          │
                          ▼
             Construction de contexte (provenance, budget)
                          │
                          ▼
                LLM local (Ollama) → réponse sourcée
                          │
                          ▼
           RAGnarok-AI : retrieval, génération, routage, SQL
```

### Garde-fous SQL

Connexion en lecture seule, liste blanche de vues, `SELECT`/`WITH` uniquement, timeout, limite de lignes, journalisation de chaque requête générée.

## 5. Jeu de référence

| Catégorie | Cible finale |
|---|---:|
| Factuelles | 40 |
| Documentaires | 40 |
| Mixtes | 40 |
| Sans réponse (dont ≥ 20 quasi-réponses) | 30 |
| **Total** | **150** |

Schéma et règles : `benchmarks/datasets/gold/`. Les cibles sont indicatives : mieux vaut 120 questions solides que 150 fragiles.

## 6. Évaluation

- **Retrieval :** Recall@k, MRR, NDCG@k, latence.
- **Génération :** fidélité, pertinence, complétude, exactitude des citations, affirmations non étayées, qualité de l'abstention.
- **Routage :** exactitude, matrice de confusion, précision/rappel par route.
- **SQL :** validité, **exactitude d'exécution** (le résultat, pas le texte de la requête), gestion des résultats vides.
- **LLM-as-judge :** calibré sur un sous-ensemble annoté manuellement ; jamais considéré comme vérité.

Résultats métier et benchmark public présentés séparément, sans extrapolation de l'un à l'autre.

## 7. Plan de travail

| Semaine | Contenu | Livrable |
|---|---|---|
| 0 (spike) | 3 tests de faisabilité (`docs/spike/plan-spike.md`) | Rapport de spike GO / NO-GO |
| 1 | Téléchargements figés, référentiel géographique, 15 questions | Corpus pilote, registre v0.3, 15 questions |
| 2 | Normalisation, tables DuckDB, jointure spatiale complète, tests de cohérence, 30 questions | Pipeline d'ingestion reproductible |
| 3 | Extraction du règlement, indexation Qdrant, baselines retrieval, benchmark FR public | Benchmark retrieval initial |
| 4 | Routeur, garde-fous SQL, génération locale, citations, abstention, intégration RAGnarok | Système de bout en bout |
| 5–6 | Jeu de référence étendu, mesures, interface, rapport, vidéo | Version publique |

Si l'extraction ou les données prennent plus de temps que prévu : réduire le périmètre (moins de zones, moins de documents) avant de réduire la qualité de l'évaluation.

## 8. Critères de réussite de la v1

- Sources documentées, licences vérifiées, données reconstruisibles depuis les manifestes.
- Jointure spatiale avec taux de couverture et qualité de géolocalisation publiés.
- Réponses documentaires citant document, page et version.
- Requêtes SQL contrôlables et résultats comparés aux références.
- Abstention mesurée sur les quasi-réponses.
- Stratégies de retrieval comparées, métriques reproductibles, configurations versionnées.
- Interface utilisable, rapport et limites publiés.

Aucun seuil de qualité ou de latence fixé avant les premières baselines.

## 9. Principes

1. Pas de chiffre sans source identifiable.
2. Pas de citation sans passage réel correspondant.
3. Pas de réponse forcée.
4. Pas de complexité sans justification expérimentale.
5. Pas de comparaison sans baseline reproductible.
6. Pas de score de juge considéré comme vérité.
7. Pas de service distant sans justification.
8. Pas de résultat de benchmark sans ses conditions.
9. Pas de données intégrées sans conditions de réutilisation vérifiées.
10. Pas de fonctionnalité au détriment de la livraison de la v1.

## 10. Décisions ouvertes (tranchées par le spike ou en semaine 1)

- Choix des documents du règlement inclus dans le corpus pilote.
- Extracteur PDF (PyMuPDF vs Docling).
- Encodeur (BGE-M3 ou alternative plus légère).
- Modèle de génération local.
- Benchmark public français retenu.
- Extensions à apporter à RAGnarok-AI (routage, exactitude SQL).
- ~~Nom définitif du projet~~ : tranché, « Traboule ».
