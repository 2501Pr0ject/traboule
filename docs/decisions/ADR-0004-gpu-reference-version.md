# ADR-0004 — Géoportail de l'Urbanisme comme référence de version du PLU-H

- **Statut :** proposé (accès et licence à confirmer)
- **Date :** 2026-10-27

## Contexte
Le PLU-H est en vigueur depuis juin 2019 et évolue par procédures successives. Une réponse réglementaire sans version identifiée n'a pas de valeur. Depuis le 1er janvier 2023, la publication sur le Géoportail de l'Urbanisme conditionne le caractère exécutoire d'un document d'urbanisme.

## Décision
Le GPU sert de référence pour identifier la version opposable du PLU-H et contrôler la concordance avec le zonage diffusé sur data.grandlyon. Chaque passage indexé et chaque question du jeu de référence porte cette version.

## Conséquences
- Nouvelle question de référence possible : concordance open data / version opposable.
- Si le règlement GPU est mieux structuré que les PDF de la Métropole, il peut devenir la source du corpus RAG.

## Critère de réexamen
Accès GPU impraticable ou licence incompatible.
