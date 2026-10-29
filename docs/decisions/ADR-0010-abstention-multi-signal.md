# ADR-0010 — Abstention multi-signal

- **Statut :** proposé
- **Date :** 2026-10-29

## Contexte
L'abstention est un comportement attendu et évalué (cadrage §2, conventions §6). Au test 4, la sonde Q21 (« logement de gardien », sujet absent du corpus) a un score de premier résultat de 0,526 en dense, 0,108 en sparse, 0,700 en hybride ; une requête légitime a un score dense plus bas (Q02, 0,519), une un score sparse plus bas (Q20), neuf un score hybride plus bas. **Un seuil sur le score du premier résultat ne sépare pas** la sonde des requêtes légitimes ; les scores de fusion RRF, fondés sur les rangs, ne sont pas calibrés pour cela.

## Décision
Décider l'abstention à partir de plusieurs signaux, combinés et mesurés en v1 sur les questions sans réponse du jeu de référence :
- **signaux structurels** (prioritaires, sans seuil) : zone inexistante dans le zonage indexé ; document ou pièce non ingéré ; niveau géographique non chargé ; date `as_of` hors de la version indexée ; établissement à diffusion partielle (pas de position publique) ; **confiance de zone faible** (ADR-0006) ;
- **signaux de retrieval** : score du premier résultat dense, écart entre premier et second résultats, **score du reranker** (le reranking reste en v1, ADR-0001) ;
- **vérification à la génération** : la réponse doit citer un passage qui contient l'information demandée.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Multi-signal (retenue) | Les cas structurels sont certains ; les autres se mesurent | Plus de règles à maintenir et à évaluer |
| Seuil sur le score de retrieval | Simple | Ne sépare pas Q21 des requêtes légitimes |
| Laisser le modèle décider | Aucun réglage | Non mesurable, non reproductible |

## Conséquences
- Le jeu de référence doit contenir des quasi-réponses couvrant chaque signal structurel (guide d'annotation).
- Les seuils de retrieval et du reranker sont fixés après mesure, avant l'évaluation finale.

## Critère de réexamen
Si un signal unique (par exemple le score du reranker) sépare les questions sans réponse avec une précision suffisante sur le jeu de référence.
