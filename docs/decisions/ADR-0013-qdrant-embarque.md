# ADR-0013 — Qdrant en mode embarqué pour la v1

- **Statut :** accepté (décision du porteur, 2026-11-01)
- **Date :** 2026-11-01

## Contexte
Les conventions (§2) prévoyaient Qdrant en mode local embarqué pour le spike et un serveur Docker pour les benchmarks. Le spike (test 4) a montré que le mode embarqué suffit au corpus : 360 passages indexés, recherche hybride RRF et filtre de payload par zone. Le corpus complet de la v1 (règlement et 76 cahiers, 6 800 pages environ) reste de l'ordre de quelques dizaines de milliers de passages. Le démon Docker ne tourne pas sur la machine de référence, et un serveur ajoute un service à opérer sans changer les résultats de retrieval.

## Décision
Qdrant en **mode local embarqué** (`QdrantClient(path=...)`) pour toute la v1 : index, recherche et mesures de retrieval. Le serveur Docker ne sert qu'aux **mesures de latence en conditions de service**. Le code ne dépend que du client : seule l'URL de connexion change.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Embarqué pour la v1, serveur pour la latence (retenue) | Aucun service à opérer ; résultats de retrieval identiques | Latence de l'embarqué non représentative d'un service |
| Serveur Docker pour tous les benchmarks | Conditions proches d'un service | Démon à faire tourner ; aucun gain sur les métriques de pertinence |

## Conséquences
- `data/processed/qdrant/` (local, exclu de Git) contient l'index.
- Les latences publiées précisent le mode de mesure ; seules celles du serveur valent pour des conditions de service.

## Critère de réexamen
Corpus ou concurrence qui dépassent ce que le mode embarqué supporte ; mesure de latence de service demandée.
