# ADR-0011 — Ingestion de la partie I du règlement (dispositions communes)

- **Statut :** proposé
- **Date :** 2026-10-29

## Contexte
Le corpus pilote du spike ne contenait que des chapitres de zones (partie II). Or les règles de zone renvoient à la partie I : « les normes de stationnement… se situent au chapitre 5 de la partie I » (Q10 ne pouvait être servie que par ce renvoi), et les termes en italique marqués d'un astérisque sont définis dans la partie I. L'ancienne requête Q11 (« logement de gardien ») n'avait aucun passage traitant le sujet dans le corpus. Le règlement complet contient des tableaux sur 43 pages, dont plusieurs en partie I (stationnement, p. 100 à 104).

D'après la table des matières du règlement (SRC-005), la partie I couvre les p. 5 à 116 : chapitre préliminaire, chapitres 1 à 6 (destinations, morphologie, nature en ville, qualité urbaine, déplacements et stationnement, équipements et réseaux) et index.

## Décision
Ingérer la partie I en v1, avec la même structure de passages que la partie II (ADR-0009) et Docling pour ses pages à tableaux (ADR-0008) ; relier les renvois « partie I, chapitre n » des articles de zone aux passages correspondants.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Partie I en v1 (retenue) | Les réponses de zone renvoient à elle ; définitions nécessaires | ≈ 112 pages de plus, tableaux |
| Partie II seule | Corpus plus petit | Réponses incomplètes ou réduites à un renvoi |

## Conséquences
- Volume ajouté estimé à ≈ 44 000 tokens (396 tokens par page mesurés sur le règlement), encodage de l'ordre de la minute.
- Le jeu de référence peut contenir des questions sur les dispositions communes et les définitions.

## Critère de réexamen
Aucun prévu : condition de complétude des réponses réglementaires.
