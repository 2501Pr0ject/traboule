# Traboule

Moteur d'intelligence territoriale **local-first** sur la Métropole de Lyon : il répond à des questions sur les établissements, le zonage d'urbanisme et les règles du PLU-H, avec des réponses sourcées, ancrées dans le temps, et une abstention explicite quand les données ne suffisent pas.

**Fonctionnalité signature :** relier un fait géographique (un établissement situé dans une zone du PLU-H) à la règle écrite qui s'applique à cette zone.

> **Statut : phase 0 — spike de faisabilité.** Aucun code applicatif pour l'instant.

## Principes

- Pas de chiffre sans source, pas de citation sans passage réel, pas de réponse forcée.
- Tout s'exécute en local (MacBook Air M2, 16 Go).
- Chaque stratégie est mesurée sur un jeu de référence versionné, évalué avec [RAGnarok-AI](https://github.com/2501Pr0ject).

## Documentation

| Document | Contenu |
|---|---|
| [Cadrage v1](docs/cadrage-v1.md) | Périmètre, architecture, critères de réussite, planning |
| [Registre des sources](docs/sources/registre.md) | Sources officielles, licences, limites |
| [Plan du spike](docs/spike/plan-spike.md) | Tests de faisabilité et critères GO / NO-GO |
| [Décisions (ADR)](docs/decisions/) | Choix structurants et leurs justifications |
| [Conventions](docs/conventions.md) | Règles de données, garde-fous SQL, règles de réponse, code |
| [Jeu de référence](benchmarks/datasets/gold/guide-annotation.md) | Schéma et règles d'annotation |

## Démarrage

```bash
uv sync                 # environnement de base
uv sync --extra spike   # dépendances du spike
```

## Sources de données

Données publiques sous Licence Ouverte (Sirene / INSEE, Métropole de Lyon, Géoportail de l'Urbanisme). Les fichiers ne sont pas versionnés : les scripts et les manifestes permettent de les retélécharger. Les données Sirene brutes ne sont jamais republiées ; le dépôt ne publie que des agrégats. Voir le [registre](docs/sources/registre.md).

## Limites

- **Reproductibilité des chiffres Sirene.** Le fichier INSEE de géolocalisation des établissements n'est en ligne qu'un mois, sans archive. Une reconstruction ultérieure utilisera un fichier plus récent et donnera des chiffres différents de ceux publiés ; les manifestes (date, sha256) identifient la version utilisée.
- **Diffusion partielle.** Les établissements ayant fait opposition n'ont pas de géolocalisation publique : les comptages spatiaux sont des minorants.
- **Résultats spatiaux.** Situer un établissement dans une zone du PLU-H est une analyse de localisation, pas un constat réglementaire.
