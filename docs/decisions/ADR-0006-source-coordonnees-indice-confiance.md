# ADR-0006 — Source de coordonnées et indice de confiance de zone

- **Statut :** proposé
- **Date :** 2026-10-29

## Contexte
Le spike (`spikes/reports/rapport-spike.md`, tests 1 et 2) a montré que deux sources de coordonnées existent pour un établissement : le fichier INSEE de géolocalisation (SRC-001b) et les coordonnées du stock Sirene (SRC-001a), probablement issues de la BAN. Sur les 800 928 établissements qui ont les deux, l'écart médian est de 0,28 m mais **15,2 % dépassent 50 m**, et **la zone PLU-H change pour 5,1 %** d'entre eux (3,7 % en qualité `11`, 39,4 % en `12`, 87,8 % en `33`).

Le point géocodé est une adresse, souvent placée côté rue, alors que les limites de zone suivent fréquemment les voies : **13,0 %** des établissements sont à moins de 10 m d'un polygone d'une autre zone, **31,2 %** à moins de 25 m. L'indice de confiance calculé au test 2 donnait 54 % haute, 26 % moyenne, 20 % faible. Le cas de contrôle #9 (confiance « haute » alors que la parcelle touche trois zones) montre que la distance mesurée depuis le point **surestime** la confiance.

Libellés de `qualite_xy` (documentation v8, p. 4) : `11` voie sûre, numéro trouvé ; `12` voie sûre, position aléatoire dans la voie ; `21` voie probable, numéro trouvé ; `22` voie probable, position aléatoire ; `33` voie inconnue, position aléatoire dans la commune.

## Décision
- **Source principale** : fichier INSEE de géolocalisation (SRC-001b), filtré sur `epsg = '2154'`. Les coordonnées du stock servent à l'analyse de sensibilité (accord des sources).
- **Indice de confiance de zone**, calculé pour chaque établissement et **exposé dans les réponses** :
  - **haute** : qualité `11` seulement, distance au polygone d'une autre zone ≥ 25 m, même zone avec les deux sources ;
  - **moyenne au mieux** : qualité `21` ; ou coordonnées du stock absentes (accord non vérifiable) ;
  - **faible par définition** : qualités `12`, `22`, `33` (position aléatoire), distance < 10 m, ou zones différentes selon la source ;
  - moyenne sinon.
- Les seuils de 10 m et 25 m restent provisoires ; la distance depuis le point sera remplacée par une distance depuis le bâtiment si l'ADR-0007 est adopté.
- Un établissement en statut de diffusion `P` n'a pas de coordonnées publiques ; aucune autre source n'en fournit (conventions §3.10).

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Géolocalisation INSEE + indice (retenue) | Source primaire documentée (ADR-0003), qualité par établissement, incertitude rendue visible | L'indice repose sur un point, pas sur le bâtiment |
| Coordonnées du stock | Proches de la BAN | Absentes pour 156 449 établissements géolocalisés par l'INSEE ; pas d'indicateur de qualité |
| Zone sans indice | Simple | Masque les 20 % de cas fragiles ; contraire au principe « pas de réponse forcée » |

## Conséquences
- Chaque réponse fondée sur la zone d'un établissement porte l'indice ; un comptage par zone donne la part en confiance faible.
- L'arbitrage entre sources n'a pas pu être tranché au spike : la vérification automatisée (BAN → cadastre → GPU) favorise mécaniquement le stock, dont les coordonnées dérivent de la BAN.

## Critère de réexamen
Arbitrage humain sur au moins 10 écarts de plus de 50 m : si les coordonnées du stock sont jugées justes dans au moins 7 cas, réexaminer la source principale. Adoption de l'ADR-0007.
