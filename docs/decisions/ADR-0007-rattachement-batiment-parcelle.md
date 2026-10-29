# ADR-0007 — Rattachement de l'établissement au bâtiment ou à la parcelle

- **Statut :** proposé, à mesurer
- **Date :** 2026-10-29

## Contexte
Les règles d'urbanisme s'appliquent à la parcelle, pas à un point d'adresse. Au test 2, 31,2 % des établissements sont à moins de 25 m d'une autre zone, en partie parce que le point est posé côté rue (hypothèse métier, non vérifiée à grande échelle).

Ce qui a été observé, sur un petit nombre de cas seulement :
- contrôles #9 et #10 : la parcelle de l'adresse touche deux ou trois zones, mais le bâtiment désigné par les trois points (BAN, géolocalisation, stock) est entièrement dans la zone de la jointure ;
- la BD TOPO (couche `BDTOPO_V3:batiment`, WFS Géoplateforme) fournit l'emprise et l'usage des bâtiments et s'interroge sans difficulté ;
- **la mesure prévue sur 1 000 établissements n'a pas été faite.**

Limite connue : les établissements à position aléatoire dans la voie (qualités `12`, `22`, `33`, ≈ 2,35 % des actifs diffusibles) n'ont pas de numéro rattachable à un bâtiment ; le rattachement ne les résout pas.

## Décision
Proposition, **classée v1.1** : rattacher chaque établissement au bâtiment (BD TOPO, ou RNB) qui contient son point ou en est le plus proche, puis à la parcelle, et prendre la zone de l'emprise ; remplacer la distance depuis le point par une distance depuis le bâtiment dans l'indice de confiance (ADR-0006).

Aucune mesure du spike n'impose ce rattachement en v1 : le critère du test 2 (≥ 98 % dans exactement une zone) est atteint avec le point (99,99 %), et l'indice de confiance exposé (ADR-0006) rend visibles les cas fragiles en attendant.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Point d'adresse + indice de confiance (v1) | Déjà mesuré ; rapide (jointure en 2,5 s) | Confiance surestimée près des limites |
| Bâtiment BD TOPO (v1.1, proposée) | Emprise réelle, usage du bâtiment | Choix du bâtiment ambigu en tissu dense ; à mesurer |
| RNB (référentiel national des bâtiments) | Identifiant pivot adresse ↔ bâtiment | Couverture et licence à vérifier |
| Parcelle cadastrale | Unité juridique de la règle | Parcelles à cheval sur plusieurs zones |

## Conséquences
- Mesure à faire avant adoption : sur 1 000 établissements actifs diffusibles tirés au hasard (graine dédiée, ADR-0012), part rattachée à un bâtiment à moins de 30 m, part dont le bâtiment est entièrement dans une zone, part dont la zone du bâtiment diffère de celle du point, temps de traitement, licences de la BD TOPO et du RNB.
- Les positions aléatoires restent traitées par l'indice (faible) et l'abstention (ADR-0010).

## Critère de réexamen
Si la mesure montre qu'une part significative des zones change entre point et bâtiment (au-delà de la part en confiance faible), avancer en v1.
