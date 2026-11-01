# ADR-0011 — Ingestion de la partie I du règlement (dispositions communes)

- **Statut :** accepté
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

## Amendement du 2026-11-01 : partie III du règlement (STECAL)

La nomenclature (partie I, §0.2, p. 23 et 24) renvoie les STECAL « installations ou activités spécifiques » (`A2s1`, `A2s2`… et `N2s1`, `N2s2`…) à des « règles particulières figurant dans la partie III du règlement ». Constaté le 2026-11-01 :
- le règlement écrit `200046977_reglement_20260326.pdf` ne contient que les parties I et II ;
- aucune des 617 pièces du document GPU `200046977_PLUi_20260326` (`liste_pieces.json`) ne porte un nom qui évoque une partie III ou les STECAL ;
- le zonage SRC-002 porte le numéro de chaque STECAL dans l'attribut `stecal`, objet par objet (A2s : 1 à 3 ; N2s : 1 à 7).

Décision : la **source de la partie III est à localiser** (aucune supposition). Jusque-là, une question sur un STECAL `A2s` ou `N2s` donne lieu à une **abstention**, motif `document_non_ingere` (ADR-0010), **avec le numéro du STECAL** lu dans l'attribut `stecal` de l'objet concerné ; la correspondance `configs/zones_reglement.csv` liste les numéros présents par code (`numeros_stecal`).
