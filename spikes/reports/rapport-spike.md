# Rapport de spike — 2026-10-28

## Verdict global : à établir (session 6)

| Test | Verdict |
|---|---|
| Test 0 — Préparation | Fait (registre v0.3, manifestes) |
| Test 1 — Référentiel et Sirene | **GO avec réserves** (voir ci-dessous) |
| Test 2 — Jointure spatiale | à faire |
| Test 3 — PDF | à faire |
| Test 4 — BGE-M3 | à faire |

## Environnement

| | |
|---|---|
| Machine | MacBook Air, Apple M2, 16 Go de RAM |
| OS | macOS 26.5 (arm64) |
| Python | 3.12.9 (uv 0.13.6) |
| Données | DuckDB 2.0.0 (+ spatial, excel), Polars 2.1.0, PyArrow 26.0.0, psutil 7.2.2 |
| Spike | PyMuPDF 2.0, Docling 2.143.1, FlagEmbedding 1.4.2, qdrant-client 1.20.0, torch 2.14.1 (mps disponible), transformers 5.21.0 |

## Sources téléchargées (2026-10-28)

| source_id | fichier | date | sha256 (8 car.) | taille |
|---|---|---|---|---:|
| SRC-001a | `stock-stocketablissement-parquet.parquet` | stock du 2026-10-01 | `fb02cfad` | 2,22 Go |
| SRC-001b | `geoloc-…-parquet.parquet` | octobre 2026 (publié 2026-10-21) | `db5d9ca4` | 814 Mo |
| SRC-002 | `zonage.geojson` (EPSG:2154) | WFS, 2026-10-28 | `5da8a4a7` | 20,8 Mo |
| SRC-003 | `catalogue.geojson` | WFS, 2026-10-28 | `bba60c97` | 1,3 Mo |
| SRC-004a | `cog_ensemble_2026_csv.zip` | COG 2026 | `5c037e29` | 1,96 Mo |
| SRC-004b | `table-appartenance-geo-communes-2026.zip` | 2026-03-19 | `9e26e89a` | 2,05 Mo |
| SRC-004c | `table_passage_geo2003_geo2026.zip` | 2026-03-19 | `0b2d502c` | 0,71 Mo |
| SRC-005 | `200046977_reglement_20260326.pdf` | version GPU 2026-03-26 | `2aee20bf` | 11,1 Mo |
| SRC-007 | `sirene_metropole.csv` | `datemaj` max 2026-07-31 | `6667d68f` | 100,6 Mo |
| REF-COMMUNES-ML-2024 | `communes.geojson` | WFS, 2026-10-28 | `151a86dd` | 1,25 Mo |

Détail et licences : `docs/sources/registre.md` (v0.3).

---

## Test 1 — Référentiel et Sirene : GO avec réserves

Script : `spikes/test1_referentiel.py`. Mesures brutes : `spikes/output/test1/metrics.json` (non versionné ; contient versions et sha256 des sources). Aucune donnée au niveau établissement dans ce rapport.

### Performances

| Étape | Temps | Pic RSS |
|---|---:|---:|
| Extraction des archives INSEE | 0,04 s | 88 Mo |
| Référentiels (communes, arrondissements, passage) | 1,0 s | 135 Mo |
| Filtrage du stock + jointure géolocalisation → `sirene_ml.parquet` | 16,2 s | 2 246 Mo |
| Mesures | 4,5 s | 1 179 Mo |
| Contrôle croisé SRC-007 | 0,8 s | 600 Mo |
| **Total** | **24 s** | **2,25 Go** |

DuckDB en streaming (`memory_limit = 6GB`), jamais de chargement complet du stock.

### Référentiel géographique

- **58 communes** dans l'EPCI 200046977 au COG 2026 (onglet `COM` de la table d'appartenance), identiques aux 58 codes `insee` de REF-COMMUNES-ML-2024. Lyon = 69123.
- **9 arrondissements municipaux** (`TYPECOM = 'ARM'`, `COMPARENT = 69123`), concordants avec l'onglet `ARM` (EPCI et commune parente).
- **Passage des codes historiques** (table 2003 → 2026) : un seul code de la Métropole a changé depuis 2003 : **69152 (Pierre-Bénite) → 69149 (Oullins-Pierre-Bénite)**, date d'effet **2024-01-01**, mouvement 32 (création de commune nouvelle), lus dans `v_mvt_commune_2026`. Aucun code ambigu. Table finale : 68 lignes (58 communes + 69152 + 9 arrondissements).
- Sorties : `data/interim/ref_communes_ml.parquet`, `ref_arrondissements_lyon.parquet`, `passage_communes.parquet`.

### Rattachement Sirene

`sirene_ml.parquet` : **1 139 191 établissements** (399 667 actifs, 739 524 fermés), tous rattachés à une commune du COG 2026, aucun SIRET en double.

**Niveau géographique de Lyon dans le stock :** les établissements sont codés **par arrondissement** (564 784). **1 seul** est codé 69123 (actif, dernier traitement en 2025) : il compte dans Lyon commune mais dans aucun arrondissement. Conséquence de modélisation : **total Lyon commune = somme des arrondissements + 1**. Les deux niveaux sont publiés dans des tables séparées et ne s'additionnent jamais.

**Code historique 69152 :** 18 établissements, rattachés à 69149 par la table de passage.

| Code | État | Année du dernier traitement | n |
|---|---|---|---:|
| 69123 | actif | 2025 | 1 |
| 69152 | actif | 2025 | 13 |
| 69152 | actif | 2026 | 2 |
| 69152 | fermé | 2024 | 2 |
| 69152 | fermé | 2026 | 1 |

15 établissements **actifs** portent encore l'ancien code de Pierre-Bénite près de trois ans après le regroupement : le stock n'est pas recodé rétroactivement.

**Établissements par arrondissement** (le détail par commune est dans `metrics.json`) :

| Arrondissement | Actifs | Fermés | Total |
|---|---:|---:|---:|
| 69381 | 14 964 | 33 952 | 48 916 |
| 69382 | 21 250 | 44 800 | 66 050 |
| 69383 | 39 011 | 78 558 | 117 569 |
| 69384 | 11 197 | 21 452 | 32 649 |
| 69385 | 11 669 | 22 648 | 34 317 |
| 69386 | 27 704 | 55 710 | 83 414 |
| 69387 | 29 311 | 53 375 | 82 686 |
| 69388 | 18 952 | 32 524 | 51 476 |
| 69389 | 16 645 | 31 062 | 47 707 |
| *Lyon commune (69123)* | *190 704* | *374 081* | *564 785* |

### Géolocalisation

Jointure sur SIRET avec le fichier de géolocalisation filtré `epsg = '2154'` (0 ligne hors 2154 dans le périmètre).

| État | Diffusion | Établissements | Géolocalisés | % |
|---|---|---:|---:|---:|
| actif | O | 327 378 | 327 052 | 99,90 |
| actif | P | 72 289 | 313 | 0,43 |
| fermé | O | 630 387 | 629 656 | 99,88 |
| fermé | P | 109 137 | 356 | 0,33 |

- **Actifs sans coordonnées :** 0,10 % des diffusibles (326) ; **99,57 % des établissements à diffusion partielle** (71 976). Les actifs à diffusion partielle représentent **18,1 %** des actifs de la Métropole : tout comptage spatial d'actifs est un minorant d'au moins cet ordre.
- **Qualité de géolocalisation** (`qualite_xy`, libellés dans la documentation v8) : `11` 94,80 % ; `12` 4,28 % (médiane de `distance_precision` 604 m) ; `33` 0,45 % (6 033 m) ; `21` 0,35 % ; `22` 0,12 %. Environ 5 % des points ont une imprécision documentée de plusieurs centaines de mètres : à porter dans le Test 2.
- **Codes 2024 de la géolocalisation vs COG 2026 :** un seul code hors référentiel, **69133 (Millery, hors Métropole)**, pour 2 établissements que le stock code 69260 (Saint-Genis-Laval). 24 désaccords au total entre `plg_code_commune` et le code du stock, dont 12 dus à l'ancien code 69152, 2 à Millery, 1 à la ligne 69123, le reste entre communes ou arrondissements voisins.

### Perte inexpliquée — critère reformulé

Le filtre porte sur le code commune du stock : « tout établissement filtré est rattaché à une commune du COG 2026 » est donc vrai par construction (100 %). La perte réelle se mesure dans l'autre sens : **établissements géolocalisés dans la Métropole mais codés hors Métropole dans le stock**.

- **1 établissement actif** : géolocalisé en 69149, codé 28293 (Eure-et-Loir) dans le stock. Incohérence d'adresse entre stock et géolocalisation ; non expliquée au-delà.
- **2 SIRET** géolocalisés dans la Métropole sont absents du stock du 2026-10-01 (sur 69 au niveau national, voir registre).

### Dates de création

Comptées, non filtrées :
- postérieures au stock (2026-10-01) de moins d'un an : **279** (anticipation probable) ;
- postérieures de plus d'un an ou antérieures à 1900 : **0** dans la Métropole (les dates aberrantes constatées au niveau national, jusqu'en 5015, sont hors périmètre) ;
- **nulles : 77 827**, toutes des établissements fermés (anciens établissements sans date de création renseignée). Toute question « créé avant / après » doit en tenir compte.

### Coordonnées du stock vs fichier de géolocalisation

| Couverture | Établissements |
|---|---:|
| Coordonnées dans les deux | 800 928 |
| Géolocalisation seule | 156 449 (142 109 fermés, 13 671 actifs) |
| Stock seul | 990 |
| Aucune | 180 824 |

Les coordonnées du stock valent `[ND]` (non diffusé) pour 181 426 établissements.

Écart entre les deux coordonnées (mètres, établissements présents dans les deux) : médiane **0,28 m**, p90 **82 m**, p99 **582 m**, max 11,1 km ; **15,2 % à plus de 50 m**. Même en qualité `11` (la meilleure), 12,4 % des écarts dépassent 50 m (p90 61 m). Les deux sources ne relèvent pas du même géocodage. **Risque pour le Test 2 :** la zone PLU-H d'un établissement peut dépendre de la source de coordonnées. Choix proposé : fichier de géolocalisation (source primaire, ADR-0003, qualité documentée), avec un comptage des établissements dont la zone change selon la source.

### Contrôle croisé SRC-007 (Sirene Métropole)

SRC-007 : 329 197 établissements, `datemaj` max **2026-07-31** (la date de mise à jour de la fiche data.gouv, 2026-08-04, n'est pas la date des données). Il contient 2 établissements codés 69133 (Millery, hors Métropole).

**Coordonnées :** sur les 320 719 SIRET communs, écart médian 0,14 m, p99 0,47 m. **SRC-007 reprend les coordonnées du fichier INSEE** (différence de précision seulement) : le registre parlait à tort d'un géocodage propre à la Métropole.

**Comptages par commune / arrondissement** (SRC-001 actifs géolocalisés − SRC-007, rapporté à SRC-007) : de **-1,87 %** (69142, -21 sur 1 121) à **+1,03 %** (69233, +3 sur 291) ; en volume, Villeurbanne -340 sur 31 877 (-1,07 %), Lyon 7e -178 sur 22 458. Les 11 établissements actifs encore codés 69152 n'ont pas d'équivalent dans SRC-007. Détail dans `metrics.json`.

**Recouvrement des SIRET** (actifs géolocalisés SRC-001 vs SRC-007) : 320 719 communs ; 8 478 dans SRC-007 seul ; 6 646 dans SRC-001 seul.

| Écart | n | Explication |
|---|---:|---|
| SRC-007 seul : fermés dans le stock, fermeture datée après le 2026-08-04 | 1 810 | date |
| SRC-007 seul : fermés, fermeture datée avant mais **traitée** par l'INSEE après le 2026-08-04 | 2 500 | date (enregistrement rétroactif) |
| SRC-007 seul : fermés, traités avant le 2026-08-04 ; dans tous les cas, la `datemaj` de la ligne SRC-007 est antérieure au traitement INSEE de la fermeture (vérifié sur 3 572 / 3 572 avec un filtre sur la date de traitement) | 3 570 | retard de mise à jour de SRC-007 |
| SRC-007 seul : actifs diffusibles sans géolocalisation INSEE | 296 | géocodage (la Métropole géolocalise ce que l'INSEE ne publie pas) |
| SRC-007 seul : actifs **à diffusion partielle** | 301 | périmètre — SRC-007 publie des coordonnées d'établissements à diffusion partielle |
| SRC-007 seul : SIRET absent du stock de la Métropole (code 69386) | 1 | **non expliqué** |
| SRC-001 seul : créés ou rouverts après le 2026-08-04 | 3 670 | date |
| SRC-001 seul : antérieurs mais traités après le 2026-08-04 | 2 602 | date (rétroactif) |
| SRC-001 seul : diffusibles traités entre le 2026-07-31 (dernière `datemaj` SRC-007) et le 2026-08-04 | 160 | date |
| SRC-001 seul : diffusibles traités avant le 2026-07-31 | 6 | **non expliqué** |
| SRC-001 seul : à diffusion partielle, géolocalisés par l'INSEE, absents de SRC-007 | 222 | **non expliqué** (périmètre de SRC-007 à éclaircir) |

Les lignes SRC-001 seul proviennent de requêtes séparées (filtres de dates différents) : leurs effectifs ne s'additionnent pas exactement à 6 646. Résidu non expliqué : **au plus 229 établissements** (0,07 % des actifs géolocalisés).

### Points de vigilance (session 2)

- **SRC-003 (67 objets) :** 9 arrondissements + 58 entrées communales = les 57 communes 2026 hors Lyon **+ Pierre-Bénite (69152) séparée d'Oullins-Pierre-Bénite (69149)**. Le catalogue suit donc le découpage à 59 communes du PLU-H (Lyon remplacée par ses arrondissements). Expliqué.
- **Cahiers GPU (76) :** 9 « cahier_arrondissement » + 67 « cahier_communal », nommés par secteur (`SECTnn`), sans code commune. Les 9 arrondissements concordent ; **67 cahiers communaux contre 58 entrées communales de SRC-003 : écart de 9 non expliqué** à partir des noms de fichiers. À trancher en ouvrant les cahiers (Test 3), pas par supposition.
- **Procédure postérieure à la version GPU :** l'API Carto ne renvoie qu'un document pour la partition `DU_200046977` (`200046977_PLUi_20260326`, horodatage 2026-04-23). Dans SRC-002, `last_update` max = 2026-03-03 (antérieur à l'approbation du 2026-03-26) et `last_update_fme` max = 2026-04-23 (date de chargement, identique à la publication GPU) ; SRC-003 : 2026-04-23. Aucun indice de procédure postérieure, **sans preuve d'absence** : le GPU ne publie que la version en vigueur et les procédures en cours (arrêtées, non approuvées) n'y figurent pas. Limite consignée.

### Limites

- **Périmètre 2026 appliqué à tout l'historique.** Le filtre retient les établissements dont la commune est dans la Métropole au COG 2026, quelle que soit leur date. Une question dont l'`as_of` est antérieur à l'entrée d'une commune dans l'intercommunalité porte sur un autre périmètre. Non corrigé, documenté seulement. Ces communes n'ont pas changé de code depuis 2003 : rien dans les données INSEE utilisées ne signale leur date d'adhésion.

  | Commune | Adhésion | Source |
  |---|---|---|
  | Lissieu | 2011 | [Communes de la Métropole de Lyon (2014-2023)](https://www.data.gouv.fr/datasets/communes-de-la-metropole-de-lyon-2014-2023), Métropole de Lyon, data.gouv |
  | Quincieux | juin 2014 | même source |
  | Givors | **à sourcer** | même source, phrase ambiguë (voir ci-dessous) |
  | Grigny | **à sourcer** | même source, phrase ambiguë (voir ci-dessous) |

  Texte de la fiche : « Aux 55 communes d'origine, se sont ajoutées Givors, Grigny-sur-Rhône et Lissieu en 2011, et Quincieux en juin 2014. » La phrase est **ambiguë** : « en 2011 » peut porter sur les trois communes ou seulement sur Lissieu. Ce n'est pas une contradiction avec d'autres sources, et la date n'est plus nécessaire : **décision du 2026-10-28, `as_of` ≥ 2015-01-01** (création de la Métropole ; 59 communes de 2015 à 2023, 58 depuis 2024 ; guide d'annotation règle 7, conventions §7). Toutes les adhésions sont antérieures à cette borne.
- **Diffusion partielle :** 18,1 % des actifs sans coordonnées publiques ; comptages spatiaux minorants.
- **Deux géocodages divergents** (stock vs fichier de géolocalisation) : voir ci-dessus.
- **Reproductibilité :** le fichier de géolocalisation n'est pas archivé par l'INSEE (registre).

### Verdict Test 1 : GO avec réserves

| Critère (plan, reformulé pour le 2e) | Résultat |
|---|---|
| 58 communes + 9 arrondissements correctement modélisés, sans double comptage | **Atteint.** Tables séparées ; la ligne 69123 sans arrondissement est identifiée (Lyon = Σ arrondissements + 1). |
| Aucune perte inexpliquée : établissements géolocalisés dans la Métropole mais codés ailleurs dans le stock | **Atteint avec réserve.** 1 établissement actif (+ 2 SIRET absents du stock), listés, non expliqués. |
| Écarts avec SRC-007 expliqués (date, périmètre, géocodage), pas seulement constatés | **Atteint avec réserve.** 98,5 % des 15 124 écarts de SIRET expliqués et quantifiés ; résidu de 229 établissements non expliqué (0,07 % des actifs géolocalisés). |

Réserves à porter :
1. Résidu SRC-007 de 229 établissements (dont 222 à diffusion partielle) : à éclaircir auprès du producteur ou à documenter comme limite.
2. Divergence stock / géolocalisation (15 % > 50 m). **Décidé :** le fichier de géolocalisation est la source principale ; les coordonnées du stock servent à l'analyse de sensibilité du Test 2 (changements de zone, indice de confiance).
3. Écart cahiers GPU (67) / SRC-003 (58 entrées communales) : à trancher au Test 3.

---

## Test 2 — Jointure spatiale : à faire

## Test 3 — PDF : à faire

## Test 4 — BGE-M3 : à faire

## Surprises et risques

- Lyon est codée par arrondissement dans Sirene (une seule exception) ; le niveau commune se reconstruit par agrégation.
- SRC-007 publie des coordonnées pour des établissements à diffusion partielle (301 actifs) que l'INSEE ne géolocalise pas publiquement : point à signaler au moment de toute comparaison ou publication.
- Les coordonnées du stock Sirene et celles du fichier de géolocalisation divergent souvent (15 % > 50 m).

## Décisions à consigner en ADR

- Source de coordonnées pour la jointure spatiale : fichier de géolocalisation en principal, coordonnées du stock en sensibilité (décidé le 2026-10-28) — ADR à rédiger avec les mesures du Test 2.
- Statut de diffusion : le stock INSEE le plus récent prévaut ; jamais de coordonnées SRC-007 pour un établissement `P` (conventions §3.10).

## Impact sur le planning

À établir en session 6.
