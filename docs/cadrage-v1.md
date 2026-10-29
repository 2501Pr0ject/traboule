# Traboule — Cadrage de la v1

**Version :** 0.3 (intègre les conclusions du spike, 29/10/2026)
**Statut :** validé ; spike conclu **GO avec réserves** (`spikes/reports/rapport-spike.md`)
**Objectif de livraison :** 6 à 8 semaines après le GO du spike, à temps plein, à ajuster selon la disponibilité réelle (objectif, pas promesse)
**Environnement :** MacBook Air M2, 16 Go de RAM
**Évaluation :** RAGnarok-AI

## Changements par rapport à la v0.2 (conclusions du spike)

| Point | v0.2 | v0.3 |
|---|---|---|
| Délai | 4 à 6 semaines | **6 à 8 semaines** à temps plein (charges ajoutées par le spike ≈ 2 à 3 semaines, ≈ 1 semaine économisée) |
| Corpus réglementaire | Règlement (zones) | **Partie I** (dispositions communes) + partie II + cahiers communaux (ADR-0011) |
| Extraction PDF | Décision ouverte | **PyMuPDF** pour le texte du règlement, **Docling** pour les tableaux et les cahiers (ADR-0008) |
| Passages | doc, page, zone | **En-tête contextuel** préfixé, **payload** complet (zone, secteur PLU-H, commune COG 2026 et historique, OAP, version de la pièce, pages), **filtre par zone** (ADR-0009) |
| Zone d'un établissement | Jointure point-dans-polygone | Jointure + **indice de confiance de zone exposé** (ADR-0006) ; rattachement au bâtiment en v1.1 (ADR-0007, à mesurer) |
| Abstention | Comportement attendu | **Multi-signal** : signaux structurels, signaux de retrieval dont le reranker, vérification à la génération (ADR-0010) |
| Contrôles et évaluation | — | Tirages `md5`, une graine par échantillon, protocole fixé avant tirage, revue humaine réellement faite (ADR-0012) |
| Encodeur | Décision ouverte | **BGE-M3** dense + sparse confirmé (test 4 : 30 s pour le corpus pilote, 2,3 Go sur MPS) |

## Changements de la v0.2 par rapport à la v0.1

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
4. Jointure spatiale établissements ↔ zonage PLU-H, avec taux de géolocalisation et qualité documentés ; source de coordonnées et **indice de confiance de zone exposé dans les réponses** (ADR-0006) ; correspondance code de zone → chapitre du règlement (suffixe + table des zones `AU*`).
5. Extraction et découpage du règlement du PLU-H (**partie I et partie II**, ADR-0011) et des cahiers communaux ; PyMuPDF pour le texte du règlement, Docling pour les tableaux et les cahiers (ADR-0008) ; chaque passage relié à son document, sa page, sa zone, la version de sa pièce, avec un en-tête contextuel et un payload complet (ADR-0009).
6. Qdrant : dense, sparse, hybride, hybride + reranking ; **filtre par zone** quand la zone est connue (ADR-0009).
7. Routeur `SQL | RAG | HYBRID | ABSTAIN` avec garde-fous SQL.
8. Construction de contexte contrôlée (budget, déduplication, provenance).
9. Génération locale de réponses sourcées (version de la pièce citée) et **abstention multi-signal** (ADR-0010).
10. Jeu de référence versionné (~150 questions validées manuellement ; **chemin critique**) ; tirages et revues selon l'ADR-0012.
11. Évaluation RAGnarok-AI, étendue pour le routage et l'exactitude SQL.
12. Benchmark public français de retrieval (candidats : tâches françaises de MTEB).
13. Interface web minimale : question, route choisie, réponse, sources consultables.
14. Rapport de résultats, limites et vidéo de démonstration.

### 3.2 v1.1

Multivecteurs (BGE-M3 ColBERT : 12 à 25 Go en fp32 avec les cahiers, mesuré au test 4), quantification (TurboQuant, Turbo4 — à revérifier dans la documentation Qdrant au moment de s'y mettre), benchmark anglais pour se comparer aux résultats publiés ; **rattachement de l'établissement au bâtiment ou à la parcelle** (ADR-0007, après mesure sur 1 000 établissements) ; OCR des pages graphiques ; optimisation du calcul de distance à la limite de zone.

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
| 0 (spike) | Test 0 + 4 tests de faisabilité (`docs/spike/plan-spike.md`) | **Fait** : GO avec réserves (`spikes/reports/rapport-spike.md`) |
| 1 | Structure `packages/`, contrats Pydantic ; réécriture testée du code utile des spikes (téléchargement, référentiel, jointure) ; protocole d'évaluation (ADR-0012) ; 15 questions | Socle d'ingestion, 15 questions |
| 2 | Tables DuckDB, jointure spatiale, indice de confiance (ADR-0006), correspondance des codes de zone ; 30 questions | Pipeline d'ingestion reproductible |
| 3 | Extraction partie I + partie II + cahiers (ADR-0008, ADR-0011), passages avec en-tête et payload (ADR-0009), indexation Qdrant, baselines retrieval (avec et sans filtre par zone), benchmark FR public | Benchmark retrieval initial |
| 4–5 | Routeur, garde-fous SQL, reranking, génération locale, citations avec version de la pièce, abstention multi-signal (ADR-0010), intégration RAGnarok | Système de bout en bout |
| 6–8 | Jeu de référence étendu à ~150 questions écrites et validées par le porteur (**chemin critique** : 5 à 6 jours de travail humain, à répartir dès la semaine 1), mesures, interface, rapport, vidéo | Version publique |

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

- ~~Choix des documents du règlement inclus dans le corpus pilote~~ : tranché au spike (règlement, zones économiques et AU ; OAP et cahiers d'Oullins et de Pierre-Bénite) ; corpus v1 : ADR-0011.
- ~~Extracteur PDF (PyMuPDF vs Docling)~~ : tranché, ADR-0008.
- ~~Encodeur (BGE-M3 ou alternative plus légère)~~ : BGE-M3 dense + sparse confirmé par le test 4.
- Rattachement au bâtiment ou à la parcelle : ADR-0007, proposé, à mesurer (v1.1).
- Modèle de génération local.
- Benchmark public français retenu.
- Extensions à apporter à RAGnarok-AI (routage, exactitude SQL).
- ~~Nom définitif du projet~~ : tranché, « Traboule ».
