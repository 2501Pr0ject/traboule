# ADR-0002 — DuckDB + extension spatiale comme stockage structuré

- **Statut :** accepté (confirmé par le test 2 du spike, 2026-10-29 : jointure de 957 377 points sur 4 487 polygones en 2,5 s, pic 689 Mo, 99,99 % dans exactement une zone ; voir `spikes/reports/rapport-spike.md`)
- **Date :** 2026-10-27

## Contexte
Le projet a besoin de requêtes analytiques sur Sirene filtré, de référentiels géographiques et d'une jointure point-dans-polygone avec le zonage PLU-H, en local, sans serveur.

## Décision
DuckDB avec l'extension `spatial`, données en Parquet. Pas de PostgreSQL/PostGIS en v1.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| DuckDB + spatial (retenue) | Embarqué, rapide sur Parquet, filtrage en streaming de gros CSV, SQL standard pour le routeur | Extension spatiale moins mature que PostGIS ; piège d'ordre des axes |
| PostgreSQL + PostGIS | Référence SIG, très mature | Serveur à opérer, plus lourd sur le M2, sans bénéfice en v1 |
| GeoPandas seul | Simple pour explorer | Pas de couche SQL pour le routeur, mémoire |

## Conséquences
- Toujours `ST_Transform(..., always_xy := true)` pour les sources en EPSG:4326.
- **DuckDB 2.0** (constaté le 2026-10-28 avec duckdb 2.0.0 et l'extension spatial) :
  - `ST_Transform` sans `always_xy` est **refusé** tant que `geometry_always_xy` n'est pas fixé. Le projet passe `always_xy := true` à chaque appel ; `SET geometry_always_xy = true` est toléré sur une connexion dédiée, mais l'appel explicite reste la règle.
  - Le message d'erreur de duckdb 2.0.0 (extension spatial `a3dbcd1781`) annonce : « In DuckDB v2.1, 'geometry_always_xy = true' will become the default. » C'est une annonce, non vérifiée : l'appel explicite ne dépend pas de ce défaut.
  - Contrôle : la place Bellecour (4,8320 ; 45,7578) donne environ (842 395 ; 6 519 229) en Lambert 93 avec `always_xy := true`, et une valeur aberrante avec `false`.
  - API Python : une relation n'a plus `fetchone()`. Utiliser `con.execute(sql).fetchone()` ou `rel.fetchall()`.
- Le routeur génère du SQL DuckDB ; connexion en lecture seule pour les requêtes générées.

## Critère de réexamen
Jointure spatiale trop lente ou imprécise au test 2 ; besoin de requêtes concurrentes.
