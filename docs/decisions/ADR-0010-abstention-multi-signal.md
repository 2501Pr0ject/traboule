# ADR-0010 — Abstention multi-signal

- **Statut :** accepté
- **Date :** 2026-10-29

## Contexte
L'abstention est un comportement attendu et évalué (cadrage §2, conventions §6). Au test 4, la sonde Q21 (« logement de gardien », sujet absent du corpus) a un score de premier résultat de 0,526 en dense, 0,108 en sparse, 0,700 en hybride ; une requête légitime a un score dense plus bas (Q02, 0,519), une un score sparse plus bas (Q20), neuf un score hybride plus bas. **Un seuil sur le score du premier résultat ne sépare pas** la sonde des requêtes légitimes ; les scores de fusion RRF, fondés sur les rangs, ne sont pas calibrés pour cela.

## Décision
Décider l'abstention à partir de plusieurs signaux, combinés et mesurés en v1 sur les questions sans réponse du jeu de référence :
- **signaux structurels** (prioritaires, sans seuil) : zone inexistante dans le zonage indexé ; document ou pièce non ingéré ; niveau géographique non chargé ; date `as_of` hors de la version indexée ; établissement à diffusion partielle (pas de position publique) ; **zone régie par un autre document** (secteur sauvegardé `SECTSAUV`, plan de sauvegarde et de mise en valeur non ingéré) ; **confiance de zone faible** (ADR-0006), selon la règle ci-dessous ;
- **signaux de retrieval** : score du premier résultat dense, écart entre premier et second résultats, **score du reranker** (le reranking reste en v1, ADR-0001) ;
- **vérification à la génération** : la réponse doit citer un passage qui contient l'information demandée.

**Confiance de zone faible** : elle déclenche l'abstention **uniquement pour une affirmation réglementaire sur un établissement donné** (« quelle règle s'applique à tel établissement »). Pour un **agrégat** (comptage, répartition par zone), le système répond avec la **ventilation par niveau de confiance** (haute, moyenne, faible) et la mention que le comptage est un **minorant** (établissements à diffusion partielle sans position publique).

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

## Amendement du 2026-11-22 : contrôle du sujet et des valeurs des passages cités

Décision du porteur (2026-11-22), après le constat d'une réponse fausse sur une citation réelle : en CAG, « Quel est le coefficient d'emprise au sol en zone URm1 ? » a reçu « au minimum 25 % » en citant l'article 3.2.1 « Le coefficient de pleine terre » (p. 330), alors que l'article 2.4.1 dit « L'emprise au sol des constructions n'est pas réglementée » (p. 325). Le passage cité existait et contenait « 25 % » : la vérification des citations (passage présent dans le contexte) ne suffisait pas.

La **vérification à la génération** comprend désormais deux contrôles, chacun avec son motif :
- **`sujet_hors_question`** (« passage cité hors du sujet demandé ») : quand la question porte sur un sujet d'une table fermée (`traboule.routing.sujets` : emprise au sol, pleine terre, hauteur, implantation par rapport aux voies, limites séparatives, stationnement, clôtures, destinations, extension), au moins un passage cité doit porter sur ce sujet d'après son chemin (intitulés d'articles du règlement, ex. « 2.4 - Emprise au sol des constructions ») ; pour un passage sans intitulé d'article (cahier, OAP), son texte en tient lieu. Une question à plusieurs sujets est satisfaite dès qu'un passage cité porte sur l'un d'eux.
- **`valeur_non_retrouvee`** (« valeur non retrouvée dans les passages cités ») : chaque nombre de la réponse doit figurer dans un passage cité, après normalisation (espaces insécables, virgule décimale, zéros décimaux). Un nombre **suivi d'une unité** (m, %, m², niveaux…) doit figurer dans le **texte** d'un passage cité ; un nombre **sans unité** peut aussi figurer dans son chemin (numéro d'article) ou dans la version de la pièce. Sont exemptés les marqueurs de citation, les ordinaux, et les nombres sans unité repris de la question (ex. « NAF rév. 2 »).

`citation_non_verifiee` reste le motif d'une citation absente, illisible ou hors du contexte fourni. Le contrôle des valeurs ne prouve pas qu'un nombre est attribué au bon objet : c'est le rôle du contrôle du sujet.
