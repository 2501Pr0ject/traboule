# ADR-0012 — Tirages reproductibles et protocole de revue humaine

- **Statut :** proposé
- **Date :** 2026-10-29

## Contexte
Le spike a révélé plusieurs faiblesses de protocole (`spikes/reports/rapport-spike.md`, section « Écarts au protocole ») :
- au test 2, la validation et l'arbitrage étaient ordonnés par `hash(siret || '20261028')`, **même graine** : les deux échantillons se recoupaient (contrôle #21 = #13) ; chaque échantillon restait sans biais (contrôle sur 1 000 rangs et 3 autres graines) ;
- `hash()` de DuckDB n'a pas de stabilité garantie d'une version à l'autre : le tirage pourrait ne pas se reproduire ;
- des règles de statut, de remplacement et de fin ont été fixées **après** les premiers résultats ;
- la vérification humaine prévue a été remplacée ou assistée par des vérifications automatisées (tests 2, 3, 4), et une partie de la relecture a été déclarée sans modification des fichiers.

## Décision
- **Tirages** : ordre `md5(identifiant || graine)`, **une graine par échantillon**, graines consignées avant le tirage.
- **Protocole écrit avant tout tirage** : taille de l'échantillon, règles de statut (dont cas limites et cas indéterminables), règle de remplacement, règle de fin, critère.
- **Revue humaine plus courte mais réellement faite** : un nombre de cas que le porteur peut effectivement relire ; la relecture se fait dans le fichier de grille (colonne `relu_par_humain` modifiée par l'humain lui-même) ; seules les lignes relues comptent.
- **Distinction explicite** entre vérification humaine, pré-lecture automatisée et vérification automatisée, ligne par ligne (`methode`).

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Protocole écrit + md5 + une graine par échantillon (retenue) | Reproductible, indépendant, vérifiable | Discipline à tenir |
| Tirages ad hoc | Rapide | Recoupements, dépendance de version, règles a posteriori |

## Conséquences
- Les outils d'évaluation (RAGnarok-AI) et le jeu de référence suivent ce protocole.
- Toute règle ajoutée après un premier résultat est datée et marquée comme telle, et son effet possible sur le verdict est dit.

## Critère de réexamen
Si un outil de tirage ou de revue intégré à RAGnarok-AI couvre ces exigences.
