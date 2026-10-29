# Traboule

Moteur d'intelligence territoriale **local-first** sur la Métropole de Lyon : il répond à des questions sur les établissements, le zonage d'urbanisme et les règles du PLU-H, avec des réponses sourcées, ancrées dans le temps, et une abstention explicite quand les données ne suffisent pas.

**Fonctionnalité signature :** relier un fait géographique (un établissement situé dans une zone du PLU-H) à la règle écrite qui s'applique à cette zone.

> **Statut : v1, semaine 1.** Spike de faisabilité clos (GO avec réserves, voir le [rapport du spike](spikes/reports/rapport-spike.md)) ; code applicatif en cours d'écriture dans [`packages/`](packages/traboule).

## Principes

- Pas de chiffre sans source, pas de citation sans passage réel, pas de réponse forcée.
- Tout s'exécute en local (MacBook Air M2, 16 Go).
- Chaque stratégie est mesurée sur un jeu de référence versionné, évalué avec [RAGnarok-AI](https://github.com/2501Pr0ject/RAGnarok-AI).

## Documentation

| Document | Contenu |
|---|---|
| [Cadrage v1](docs/cadrage-v1.md) | Périmètre, architecture, critères de réussite, planning |
| [Registre des sources](docs/sources/registre.md) | Sources officielles, licences, limites |
| [Plan du spike](docs/spike/plan-spike.md) | Tests de faisabilité et critères GO / NO-GO |
| [Rapport du spike](spikes/reports/rapport-spike.md) | Mesures, réserves, écarts au protocole, verdict |
| [Décisions (ADR)](docs/decisions/) | Choix structurants et leurs justifications |
| [Conventions](docs/conventions.md) | Règles de données, garde-fous SQL, règles de réponse, code |
| [Jeu de référence](benchmarks/datasets/gold/guide-annotation.md) | Schéma et règles d'annotation |

## Démarrage

```bash
make setup   # uv sync --all-extras : base + extras pdf, embeddings, index + outils de dev
make test    # tests
make lint    # ruff
```

Extras : `pdf` (PyMuPDF, Docling), `embeddings` (FlagEmbedding, BGE-M3), `index` (qdrant-client). Un `uv sync` sans `--all-extras` les désinstalle. Les scripts de `spikes/` (lecture seule, pour référence) utilisent aussi `psutil`, dépendance de dev.

## Données et licences

La licence du code ([Apache 2.0](#licence)) **ne couvre pas les données**. Elles restent sous la licence de leur producteur ; toute réutilisation cite la source (producteur, jeu de données, date de mise à jour).

Sources utilisées, telles que consignées dans le [registre des sources](docs/sources/registre.md) (dates, contrôles, limites) :

| Source | Producteur | Licence consignée | Usage |
|---|---|---|---|
| Stock des établissements Sirene, 1er octobre 2026 (SRC-001a) | INSEE | Licence Ouverte 2.0 | Source primaire des établissements |
| Géolocalisation des établissements Sirene, octobre 2026 (SRC-001b) | INSEE | Licence Ouverte 2.0 | Coordonnées des établissements |
| Zonage du PLU-H (SRC-002) | Métropole de Lyon | Licence Ouverte 2.0 | Jointure spatiale |
| Catalogue des documents du PLU-H (SRC-003) | Métropole de Lyon | Licence Ouverte 2.0, pour le catalogue seulement | Inventaire des pièces |
| COG 2026, table d'appartenance, table de passage 2003–2026 (SRC-004) | INSEE | Licence Ouverte 2.0 (mentions légales insee.fr) | Référentiel géographique |
| Règlement écrit et pièces du PLU-H, document `200046977_PLUi_20260326` (SRC-005) | Métropole de Lyon, diffusion par le Géoportail de l'Urbanisme | « Licence ouverte » selon les CGU du GPU, version ambiguë | Corpus documentaire |
| Sirene de la Métropole de Lyon (SRC-007) | Métropole de Lyon, à partir de Sirene | Licence Ouverte 2.0 | Contrôle croisé |
| Communes de la Métropole de Lyon (REF-COMMUNES-ML-2024) | Métropole de Lyon | Licence Ouverte 2.0 | Contrôle croisé |

**Points ambigus**, consignés plutôt que tranchés :

- **Pièces du Géoportail de l'Urbanisme** : les CGU du GPU soumettent les données d'urbanisme à « la licence ouverte », avec un lien vers le texte Etalab de 2014 (version 1.0). La version applicable, 1.0 ou 2.0, n'est pas confirmée ([ADR-0004](docs/decisions/ADR-0004-gpu-reference-version.md), statut « proposé »).
- **COG 2026** : les mentions légales d'insee.fr indiquent la Licence Ouverte 2.0, la fiche data.gouv du COG indique la Licence Ouverte 1.0 (`fr-lo`).
- **Catalogue des documents du PLU-H** : sa licence ne couvre pas automatiquement les documents vers lesquels il pointe.

Pour les contrôles du test 2 du spike, des services en ligne ont aussi été consultés (géocodage d'adresses, cadastre, bâtiments) ; ce ne sont pas des sources de données du projet et leurs réponses ne sont ni conservées ni redistribuées : voir [Services consultés pour les contrôles du spike](docs/sources/registre.md#services-consultés-pour-les-contrôles-du-spike-données-non-conservées-ni-redistribuées).

**Ce que contient le dépôt :**

- **aucune donnée brute** : `data/` ne contient que des manifestes (`manifest.json` : URL, date, taille, empreinte sha256), qui permettent de retélécharger et d'identifier chaque fichier ;
- **aucune donnée Sirene au niveau de l'établissement** : les données Sirene ne sont jamais republiées, ni en totalité ni en extrait ; le dépôt publie seulement des agrégats ;
- la réutilisation des données Sirene reste soumise aux **obligations de l'INSEE relatives aux données personnelles** (notamment celles des entrepreneurs individuels et le respect du statut de diffusion partielle).

## Limites

- **Reproductibilité des chiffres Sirene.** Le fichier INSEE de géolocalisation des établissements n'est en ligne qu'un mois, sans archive. Une reconstruction ultérieure utilisera un fichier plus récent et donnera des chiffres différents de ceux publiés ; les manifestes (date, sha256) identifient la version utilisée.
- **Diffusion partielle.** Les établissements ayant fait opposition n'ont pas de géolocalisation publique : les comptages spatiaux sont des minorants.
- **Résultats spatiaux.** Situer un établissement dans une zone du PLU-H est une analyse de localisation, pas un constat réglementaire.

## Licence

Code sous [licence Apache 2.0](LICENSE). Copyright 2026 Abdelatif TOUATI (voir [NOTICE](NOTICE)).

Les données ne sont pas couvertes par cette licence : voir [Données et licences](#données-et-licences).
