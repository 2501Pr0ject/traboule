# ADR-0001 — Périmètre de la v1 et report du laboratoire avancé en v1.1

- **Statut :** accepté
- **Date :** 2026-10-27

## Contexte
Le plan initial empilait RAG, CAG, GraphRAG, KAG, multivecteurs, quantification, TimesFM et vLLM, soit l'équivalent de huit projets. L'objectif est une v1 présentable en 4 à 6 semaines sur un MacBook Air M2 de 16 Go, pendant une recherche de mission.

Les techniques de compression (quantification, multivecteur compressé) n'apportent un gain mesurable qu'à une échelle que le corpus PLU-H n'atteindra pas.

## Décision
- **v1 :** données structurées, géographie (jointure spatiale), RAG hybride (dense, sparse, hybride, reranking), routeur SQL/RAG/HYBRID/ABSTAIN, évaluation RAGnarok-AI, benchmark public français, interface minimale.
- **v1.1 :** multivecteurs, quantification, benchmark anglais.
- **Hors périmètre :** GraphRAG, KAG, CAG, TimesFM, vLLM, Neo4j, PostgreSQL, frameworks d'agents.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Tout en v1 | Vitrine technologique large | Ne sera pas terminé ; briques artificielles sur ce domaine |
| v1 resserrée + v1.1 lab (retenue) | Livrable rapide, chaque brique justifiée | Moins de technologies visibles au départ |
| Domaine scientifique (OpenAlex) | Terrain plus naturel pour le retrieval avancé | Marché saturé, anglophone, sans légitimité métier |

## Conséquences
Le multivecteur de BGE-M3 est seulement mesuré (taille) pendant le spike, pas indexé. Toute demande d'ajout hors périmètre passe par un nouvel ADR.

## Critère de réexamen
GO de la v1 publié ; ou corpus dépassant une taille où la mémoire devient la contrainte principale.
