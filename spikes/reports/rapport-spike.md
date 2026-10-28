# Rapport de spike — 2026-10-28

## Verdict global : à établir (session 6)

| Test | Verdict |
|---|---|
| Test 0 — Préparation | Fait (registre v0.3, manifestes) |
| Test 1 — Référentiel et Sirene | **GO avec réserves** (voir ci-dessous) |
| Test 2 — Jointure spatiale | **GO avec réserves** (critères atteints, règles de contrôle fixées en cours de route) |
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
- **Qualité de géolocalisation** (`qualite_xy`) — libellés exacts de la documentation v8 de SRC-001b, page 4, § 3.1 « La description des variables » :

  | Code | Libellé |
  |---|---|
  | 11 | Voie Sûre, Numéro trouvé |
  | 12 | Voie Sûre, Position aléatoire dans la voie |
  | 21 | Voie probable, Numéro trouvé |
  | 22 | Voie probable, Position aléatoire dans la voie |
  | 33 | Voie inconnue, Position aléatoire dans la commune |

  Distribution dans la Métropole : `11` 94,80 % ; `12` 4,28 % (médiane de `distance_precision` 604 m) ; `33` 0,45 % (6 033 m) ; `21` 0,35 % ; `22` 0,12 %. Environ 5 % des points ont une imprécision documentée de plusieurs centaines de mètres : à porter dans le Test 2.
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

## Test 2 — Jointure spatiale : en attente du contrôle manuel

Script : `spikes/test2_jointure.py`. Mesures brutes : `spikes/output/test2/metrics.json` ; liste des zones : `zones.csv` ; contrôles : `controles.csv` et `carte_controles.html` (locaux, jamais versionnés). Sortie : `data/interim/etablissements_zones.parquet`. Source de coordonnées principale : fichier de géolocalisation (SRC-001b) ; coordonnées du stock en sensibilité. **Un résultat de ce test est une analyse de localisation, jamais un constat réglementaire.**

### Performances

| Étape | Temps | Pic RSS |
|---|---:|---:|
| Chargement et contrôles du zonage (validité, chevauchements, couverture) | 13,9 s | 148 Mo |
| Jointure pilote 69387 (66 623 points) | 0,2 s | 327 Mo |
| **Jointure Métropole** (957 377 points × 4 487 polygones, `ST_Contains`) | **2,5 s** | 689 Mo |
| Jointure de sensibilité (coordonnées du stock) | 2,1 s | 694 Mo |
| Distance au polygone d'une autre zone (`ST_DWithin` 200 m) | **410,7 s** | 755 Mo |
| Correspondance avec le règlement (PyMuPDF, 803 pages) | 4,9 s | 544 Mo |

La jointure elle-même est quasi instantanée. Le calcul de distance n'utilise pas la jointure spatiale optimisée de DuckDB (boucle imbriquée) : à optimiser hors spike (limites entre zones de codes différents précalculées), sans enjeu de faisabilité.

### Zonage

- CRS déclaré **EPSG:2154** (lu par GDAL) : aucune reprojection ; 4 487 multipolygones, **tous valides** ; 92 codes PLU-H + 1 objet `SECTSAUV`.
- **Secteur sauvegardé** (`zone = 'SECTSAUV'`, `zonage` nul, 31,2 ha) : régi par son propre plan de sauvegarde et de mise en valeur, pas par le règlement du PLU-H. Traité comme une catégorie à part.
- Chevauchements : 16 paires, 49 m² au total (artefacts de numérisation, max 10,5 m²).
- Couverture : territoire des 58 communes 537,46 km², zonage 537,45 km² ; **0,16 ha du territoire non zoné, 0,03 ha de zonage hors territoire**.

### Jointure

| Catégorie | Établissements géolocalisés | % | Actifs | % des actifs |
|---|---:|---:|---:|---:|
| Exactement une zone PLU-H | 949 228 | 99,149 | 324 846 | 99,231 |
| Secteur sauvegardé (hors règlement PLU-H) | 8 076 | 0,844 | 2 495 | 0,762 |
| Plusieurs zones | 0 | 0 | 0 | 0 |
| Aucune zone | 73 | 0,008 | 24 | 0,007 |

- Pilote 69387 : 66 623 points, tous dans une zone, aucun multi-zones.
- **Aucune zone (73) :** 62 hors territoire (médiane 8 m de la zone la plus proche : établissements de bord de Métropole géolocalisés juste de l'autre côté de la limite communale) ; 11 sur une limite (< 1 m, médiane 0,35 m : `ST_Contains` exclut le bord). Tous expliqués.
- Point de contrôle : place Bellecour → `UCe1b`.

### Distance au polygone le plus proche d'un autre code de zone

Mesurée jusqu'à 200 m (au-delà : « ≥ 200 m ») sur les 957 304 établissements situés dans une zone : p10 **8,2 m**, médiane **45,9 m** ; **13,0 % à moins de 10 m**, **31,2 % à moins de 25 m**, 8,9 % à 200 m ou plus. La proximité d'une limite augmente quand la qualité baisse (`11` : 12,9 % < 10 m ; `33` : 19,0 %) et dans les petites zones (N 25,8 %, UL 31,5 %, AUR 29,6 % à moins de 10 m).

**Lecture (hypothèse métier, non vérifiée dans les données du spike) :** la proximité d'une limite est en partie structurelle. Le point géocodé est une adresse, souvent posée à l'accès du bâtiment côté rue ; les limites de zone suivent fréquemment les voies, et le côté opposé de la rue relève souvent d'une autre zone. Un point de façade se trouve donc mécaniquement près d'une limite, sans erreur de données.

**Piste pour la v1 (candidat ADR après le GO, rien n'est ajouté au spike) :** les règles d'urbanisme s'appliquent à la parcelle, pas à un point. Rattacher l'établissement à sa parcelle cadastrale, ou à son bâtiment via le Référentiel national des bâtiments (RNB), puis prendre la zone de cette parcelle serait plus juste juridiquement et plus robuste aux erreurs de géocodage. Les ~20 % d'établissements en confiance faible deviennent ainsi un problème identifié avec une solution connue. À instruire : sources (cadastre, RNB), licences, taux de rattachement adresse → parcelle / bâtiment, cas des parcelles à cheval sur deux zones.

### Sensibilité à la source de coordonnées

Sur les 800 928 établissements ayant les deux coordonnées :

| Résultat | n | % |
|---|---:|---:|
| Même zone | 760 048 | 94,90 |
| Zone différente | 40 808 | 5,10 |
| Sans zone → zone (stock) | 34 | < 0,01 |
| Zone → sans zone (stock) | 38 | < 0,01 |

156 449 établissements n'ont pas de coordonnées dans le stock (accord non vérifiable). Le changement de zone dépend fortement de la qualité de géolocalisation (`11` : 3,7 % ; `12` : 39,4 % ; `21` : 29,5 % ; `22` : 72,6 % ; `33` : 87,8 %) et de l'écart entre sources (≤ 50 m : 0,8 % ; > 50 m : 29,3 %). Par famille : UC 1,9 %, UR 5,9 %, UE 7,2 %, N 41,0 %, UL 53,8 %.

### Indice de confiance de zone

Règle fixée avant exécution (plan, étape 10 ; seuils de 10 et 25 m **à réviser** au vu de cette distribution).

| Confiance | Établissements | % | Actifs |
|---|---:|---:|---:|
| Haute | 516 618 | 53,97 | 203 117 |
| Moyenne | 253 175 | 26,45 | 63 977 |
| Faible | 187 511 | 19,59 | 60 247 |

« Moyenne » inclut les 156 449 établissements sans coordonnées dans le stock (plafonnés à « moyenne »).

**Plan de révision de l'indice (après le Test 2) :**
- une qualité « position aléatoire dans la voie » (`12`, `22`) ou « dans la commune » (`33`) donne **au mieux une confiance faible, par définition, quelle que soit la distance** : le point ne désigne aucun bâtiment (décidé le 2026-10-28). La règle actuelle produit déjà ce résultat (toute qualité ≠ `11` → faible) ; la révision l'écrit comme un principe et non comme un seuil ;
- **seule la qualité `11` peut donner « haute » ; la qualité `21` (voie probable, numéro trouvé) donne au mieux « moyenne »** (décidé le 2026-10-28 ; la règle exécutée au Test 2 classait `21` en faible) ;
- seuils de 10 m et 25 m à revoir sur la distribution observée ;
- distance mesurée depuis le point, pas depuis le bâtiment : #9 était en confiance haute alors que sa parcelle touche trois zones (piste bâtiment / RNB). Par famille, la confiance haute va de 61,3 % (UC) à 11,3 % (UL) ; les zones N et A ont plus de 50 % de confiance faible. Détail par commune dans `metrics.json`. **Lecture :** une question qui s'appuie sur la zone d'un établissement doit porter l'indice ; les comptages par zone gagnent à être présentés avec la part de confiance faible.

### Attributs réglementaires du zonage

Synthèse produite par la Métropole ; le règlement écrit fait foi (conventions §6).

| Attribut | Objets remplis (sur 4 487) | Où |
|---|---:|---|
| `plafond` | 441 | surtout UC (308 / 510) ; valeurs 7, 10, 13… |
| `hauteur_bande_principale` / `_secondaire` | 112 / 112 | UC (108), AUC (3), UR (1) |
| `stecal` | 79 | N (63), A (16) ; numéros 1 à 7 |
| `ces` | 64 | UE (25), UR (11), UP, A, N… ; 0,1 à 0,5 |
| `cpt` | 62 | surtout UR (43) |
| `ces_bande_secondaire`, `cpt_bande_principale`, `cpt_bande_secondaire` | 8, 2, 1 | UC |
| `ces_bande_principale` | 0 | — |

Ces attributs couvrent une minorité d'objets : ils peuvent filtrer ou compter, pas tenir lieu de règle.

### Codes de zone ↔ règlement écrit (SRC-005)

Le règlement (803 pages) est structuré par **zone mère**, sans les sous-secteurs : 33 chapitres « Zone … » (ex. « Zone UCe1 » couvre UCe1a et UCe1b ; titres « Zone A 1 », « Zone N 2 » avec espace). Correspondance automatique : **60 codes sur 92** (24 exacts, 36 en retirant le suffixe de sous-secteur après un chiffre). **32 codes** demandent une table manuelle : 30 codes `AU*` (zones à urbaniser, ex. `AURm1c`, `AUCe4a` ; chapitres candidats « Zone AU » et « Zone AUs.co », à confirmer au Test 3), `UCe3-p` et `UPpa`. Toutes les zones contiennent au moins un établissement.

### Contrôles (tirage)

Tirage reproductible (graine 20261028), actifs en diffusion `O` uniquement, échantillons disjoints (contrôlé). Chaque contrôle a un lien vers la visionneuse du Géoportail de l'Urbanisme (`/map/#lon=…&lat=…&zoom=19`, paramètres lus dans `gpu-client.js`, fonction `parseUrlParams`) et figure sur `carte_controles.html` (orthophoto IGN, couche `ORTHOIMAGERY.ORTHOPHOTOS` vérifiée par GetCapabilities). Ni adresse, ni SIRET, ni nom sur la carte ou dans ce rapport ; l'adresse déclarée figure seulement dans `controles.csv` (local).

- **Validation** (critère GO, 10/10 strict) : 10 tirés au hasard parmi les établissements dans une zone. Indice de confiance de l'échantillon : 6 haute, 2 moyenne, 2 faible ; 2 des 10 ont une zone différente selon la source.
- **Méthode de remplissage** (fixée avant le remplissage) : ouvrir le lien GPU, rechercher l'adresse déclarée (CSV) dans le Géoportail de l'Urbanisme.
  - `zone_attendue` : zone de la parcelle ou du bâtiment à cette adresse selon le GPU ;
  - `source_juste` : point le plus proche du bâtiment réel — `principale`, `stock`, `les_deux`, `aucune` ou `indeterminable` ;
  - `commentaire` = cause d'un écart, dans une liste fermée : `geocodage` (point sur le mauvais bâtiment), `limite` (bâtiment à cheval sur deux zones, ou point sur la limite), `version` (code GPU ≠ code data.grandlyon : contrôle croisé de version), `domiciliation` (adresse de centre d'affaires : point juste, activité ailleurs), `jointure` (vrai défaut).
  - Le critère de validation reste 10/10 : la cause notée ne change pas le verdict, elle indique quoi corriger (`version` ou `geocodage` interrogent la source, pas la jointure).
- **Arbitrage** (sans effet sur le GO) : actifs `O` avec un écart stock / géolocalisation > 50 m : **12 339** où les deux sources donnent des zones différentes, **33 020** où elles donnent la même zone. Les 10 cas sont tous tirés dans le premier groupe. Réexamen de l'ADR « source de coordonnées » si le stock est jugé juste dans au moins 7 cas.

### Contrôle automatique indépendant (décision du 2026-10-28)

**Mention : contrôle automatique, pas vérification humaine.** Sur décision du porteur, la grille a été remplie par une chaîne indépendante de la jointure (`spikes/test2_controle_auto.py`) : adresse déclarée → géocodage BAN (Géoplateforme, `data.geopf.fr/geocodage`) → parcelle cadastrale contenant le point, sinon la plus proche à moins de 20 m (API Carto, module cadastre) → zones du **GPU national** sur cette parcelle (API Carto, module GPU, `zone-urba`). Les 20 adresses (diffusion `O`) ont été envoyées à ces deux API publiques ; elles restent dans `spikes/output/test2/` (local). Détail sans adresse : `controles_auto.json`.

Statut retenu : `correct` si la zone de la parcelle est exactement la zone de la jointure ; `limite` si la parcelle est à cheval sur plusieurs zones dont celle de la jointure ; `indeterminable` si l'adresse n'a pas de numéro (point BAN de type « rue ») ou un score < 0,7 ; `ecart` sinon.

| Échantillon | correct | limite | indéterminable | écart |
|---|---:|---:|---:|---:|
| Validation (10) | **6** | 2 | 2 | **0** |
| Arbitrage (10) | 0 | 0 | 8 | 2 |

- **Validation :** 6 zones confirmées ; #9 et #10 sur des parcelles à cheval sur deux ou trois zones (dont la zone de la jointure, point principal sur la parcelle) ; #2 et #8 sans numéro dans l'adresse déclarée (géocodage au niveau de la rue, zone attendue non fiable). **Aucun cas où la zone de la jointure est démentie**, mais 10/10 n'est pas démontré.
- **Contrôle de version (gratuit) :** pour les 20 points, la zone du GPU national au point principal est **identique** au code data.grandlyon : le zonage SRC-002 est concordant avec la version opposable `200046977_PLUI_20260326` sur cet échantillon.
- **Arbitrage — limite de la méthode :** les coordonnées du stock tombent presque toujours sur la parcelle BAN (0 à 5 m) et le stock porte un `identifiantAdresseEtablissement` : elles dérivent très probablement de la BAN. Le contrôle automatique n'est donc **pas neutre entre les deux sources** et favorise mécaniquement le stock. Sur les 2 cas déterminables (#11, #18), le stock est sur la parcelle de l'adresse et la géolocalisation à 83 m et 1,8 km : cause `geocodage`. Les 8 autres ont une adresse sans numéro. **L'arbitrage ne peut pas conclure** ; la règle « réexamen de l'ADR si le stock est juste ≥ 7 / 10 » n'est pas évaluable par cette méthode.
- Ce que l'automatisme ne fait pas : reconnaître le bâtiment réel de l'activité (`domiciliation`, mauvais bâtiment). `source_juste` est remplacé par un indicateur nommé « point le plus proche de la parcelle BAN ».

### Verdict Test 2 : GO avec réserves

| Critère | Résultat |
|---|---|
| ≥ 98 % des géolocalisés dans exactement une zone, le reste expliqué | **Atteint** : 99,99 % (99,15 % zone PLU-H + 0,84 % secteur sauvegardé) ; 73 sans zone, tous expliqués ; 0 multi-zones. |
| Validation : 10/10 zones correctes avec la source principale | **Atteint selon la règle de fin** : 10 cas déterminables sur 12 tirages, **10 réussis, 0 échec** ; 2 indéterminables (adresses sans numéro, position aléatoire dans la voie) ; 2 remplacements sur 5 autorisés. Vérification par les données (BD TOPO, voies, zonage concordant avec le GPU) et confirmation visuelle du porteur sur les cas non triviaux. |
| Codes de zone reliés au règlement sans table manuelle de plus de quelques dizaines de lignes | **Atteint** : 60 / 92 automatiques, table manuelle de 32 lignes (à confirmer au Test 3 pour les `AU*`). |

**Pourquoi « avec réserves » alors que la règle de fin donne GO.** Les trois critères sont atteints, mais le critère 2 l'est au terme de règles fixées **après** la vue des premiers résultats, toutes datées et consignées ci-dessus : contrôle automatique au lieu de la vérification visuelle, règles de statut (limite, adresse sans numéro), changement de méthode (données + observation visuelle), règle de remplacement, règle de fin. Aucune n'a transformé un échec en réussite : aucun cas déterminable n'a échoué à aucune étape. Mais le 10/10 sur les 10 premiers tirages, tel que formulé avant exécution, n'a pas été obtenu (8 réussis, 2 indéterminables).

Réserves à porter :
1. Règles du critère 2 fixées en cours de contrôle (ci-dessus) ; à figer **avant** exécution pour toute reprise.
2. Rattachement des 30 codes `AU*` au règlement à confirmer au Test 3.
3. Positions aléatoires dans la voie (≈ 2,35 % des actifs diffusibles) : zone indéterminable par construction quand la voie traverse plusieurs zones ; à traiter dans l'ADR « rattachement au bâtiment / RNB ».
4. Indice de confiance à réviser (plan de révision ci-dessus) ; distance au polygone d'une autre zone à optimiser (411 s).

**Recommandations pour les tirages futurs :** `md5(siret || graine)` comme ordre de tirage (hachage documenté et stable entre versions), **une graine par échantillon** ; règles de statut, de remplacement et de fin écrites avant le premier tirage.

**Règles de statut fixées le 2026-10-28, avant la vérification humaine** (elles s'appliquent aux 10 contrôles de validation) :
1. **Bâtiment à cheval sur plusieurs zones** : le contrôle est **réussi** si la zone de la jointure fait partie de ces zones (cause `limite`).
2. **Adresse sans numéro** : le cas n'est **indéterminable** que si l'une des zones possibles est la zone de la jointure ; si aucune ne l'est, c'est un **échec**.

**Changement de méthode (2026-10-28).** Les contrôles #2, #8, #9 et #10 n'ont pas été vérifiés par une observation visuelle seule, mais par des **données indépendantes** (`spikes/test2_verif_batiments.py`) : emprise et usage des bâtiments BD TOPO (IGN, WFS Géoplateforme, couche `BDTOPO_V3:batiment`), tronçons de la voie déclarée (`BDTOPO_V3:troncon_de_route`, même nom BAN et même commune), zonage SRC-002 (concordant avec le GPU sur l'échantillon) ; plus **une observation visuelle** de l'orthophoto au point de #2. Résultats validés par le porteur :

| # | Constat | Statut |
|---|---|---|
| 2 | Point principal (qualité 22, position aléatoire dans la voie) près d'une annexe en UPp ; aucun bâtiment d'activité au point, quartier résidentiel à l'orthophoto ; les deux bâtiments d'activité à moins de 150 m du point BAN sont en N2 ; la voie déclarée (3,1 km) traverse N1, **UPp (846 m)**, N2, URi2c, UCe4a | **indéterminable** (règle 2) |
| 8 | Voie déclarée (350 m) entièrement en UCe4a ; trois points et bâtiments proches en UCe4a | **réussi** |
| 9 | Les trois points désignent le même bâtiment, à 100 % en URc1a (c'est la parcelle qui touche trois zones) | **réussi** |
| 10 | Les trois points désignent le même bâtiment, à 100 % en UCe3a | **réussi** |

**Remplacement d'un cas indéterminable — règle décidée le 2026-10-28, après la vérification ci-dessus (et non avant)** : un contrôle de validation indéterminable est remplacé par le rang suivant de la séquence de tirage (même graine). La reproductibilité est vérifiée : les rangs 1 à 10 redonnent exactement la grille (la numérotation des contrôles suit le SIRET, pas le rang). `spikes/test2_remplacement.py`.

- **Rang 11 → contrôle #21.** C'est **le même établissement que le contrôle d'arbitrage #13** : l'échantillon d'arbitrage n'excluait que les rangs 1 à 10. Zone de la jointure URm1d, stock URi2c, qualité 12, confiance faible.
- Vérification par les données : adresse **sans numéro** ; la voie déclarée (2,9 km) traverse URi2c, UEi2, **URm1d (354 m)**, UEc, AU1, URc1b… ; point principal sur une maison en URm1d, à 528 m du point BAN ; point BAN et point du stock confondus (0 m). Statut proposé : **indéterminable** (règle 2), en attente de la confirmation visuelle du porteur (#2 et #21).

**Défaut du tirage (constaté le 2026-10-28).** La validation et l'arbitrage sont tous deux ordonnés par `hash(siret || '20261028')` : même graine, même hachage. L'arbitrage retient les 10 premiers de sa population dans cet ordre ; un établissement placé tôt dans l'ordre global et présent dans les deux populations tombe donc dans les deux (rang 11 de la validation = #13 de l'arbitrage). Chaque échantillon, pris isolément, reste un tirage pseudo-aléatoire sans biais de sa population ; ce sont leurs recouvrements qui ne sont pas indépendants. **À l'avenir : une graine distincte par échantillon.**

**Règle de fin — décidée le 2026-10-28, après les deux premiers cas indéterminables (#2, #21)** : on poursuit la séquence de validation (rangs 12, 13…) jusqu'à obtenir 10 cas déterminables, avec au plus 5 remplacements, sans redéfinir la population. Si la limite est atteinte : GO avec réserves. Tout échec franc sur un cas déterminable : critère non atteint.

**Application.** Rang 12 → contrôle #22 (zone URi2c, stock URi2c, qualité 11, confiance haute) : adresse avec numéro, bâtiment au point BAN à 100 % en URi2c → **réussi**. Deux remplacements utilisés sur cinq. Pour homogénéiser la méthode, les contrôles #1, #3 à #7 (confirmés d'abord par la chaîne BAN → parcelle → GPU) ont aussi été vérifiés par les bâtiments BD TOPO.

| # | Rang | Qualité | Adresse | Bâtiment au point BAN / voie déclarée | Statut (données) |
|---|---:|---|---|---|---|
| 1 | — | 11 | avec numéro | 100 % URi2c | réussi |
| 2 | — | 22 | sans numéro | voie : N1, UPp, N2, URi2c, UCe4a | indéterminable |
| 3 | — | 11 | avec numéro | 100 % UCe3b | réussi |
| 4 | — | 11 | avec numéro | 100 % UCe1b | réussi |
| 5 | — | 11 | avec numéro | 100 % UPr1 | réussi |
| 6 | — | 11 | avec numéro | 100 % UCe3a | réussi |
| 7 | — | 11 | avec numéro | 100 % URi1a | réussi |
| 8 | — | 12 | sans numéro | voie entièrement en UCe4a | réussi |
| 9 | — | 11 | avec numéro | 100 % URc1a | réussi |
| 10 | — | 11 | avec numéro | 100 % UCe3a | réussi |
| 21 | 11 | 12 | sans numéro | voie : URi2c, UEi2, URm1d, UEc, AU1… | indéterminable |
| 22 | 12 | 11 | avec numéro | 100 % URi2c | réussi |

(Rangs 1 à 10 : numérotation des contrôles par SIRET, pas par rang.)

**Bilan :** 10 cas déterminables, **10 réussis, 0 échec** ; 2 indéterminables (#2, #21). **Vérification visuelle du porteur (2026-10-28)** : #22 vérifié visuellement, bâtiment en URi2c, conforme ; #2 et #21 conformes au constat (indéterminables).

**Résultat : cas indéterminables et positions aléatoires.** Les deux cas indéterminables ont une position aléatoire dans la voie (qualités 22 et 12) et une adresse sans numéro. Dans la population de validation (actifs diffusibles dans une zone, 324 533), les positions aléatoires (`12`, `22`, `33`) pèsent **2,35 %** (1,96 % + 0,12 % + 0,27 %) ; l'échantillon en contient 3 sur 12 (#2, #8, #21), soit 25 % — probabilité de 0,24 % (au moins 3 sur 12) sous un tirage uniforme : écart noté, sans conclusion sur sa cause. Une position aléatoire n'est pas toujours indéterminable : #8 ne l'est pas, sa voie étant dans une seule zone.

**Contrôle du tirage (2026-10-28) : hasard, pas défaut.** Deux anomalies allaient dans le même sens : 3 positions aléatoires sur 12 tirages (2,35 % attendus) et 2 tirages sur 12 dans le sous-ensemble de l'arbitrage (écart > 50 m et zones différentes, qui pèse **3,80 %** de la population de validation, et non 1,3 %). Test sur les 1 000 premiers rangs de la séquence (même population, même ordre), puis avec 3 autres graines :

| Graine | Positions aléatoires (12/22/33) | Divergents (zones différentes) | khi² répartition `qualite_xy` | Binomial positions aléatoires | Binomial divergents |
|---|---:|---:|---:|---:|---:|
| Population (324 533) | 2,35 % | 4,47 % | — | — | — |
| **20261028** (utilisée) | 2,5 % | 4,9 % | p = 0,96 | p = 0,75 | p = 0,49 |
| 1 | 3,5 % | 5,3 % | p = 0,14 | p = 0,021 | p = 0,19 |
| 42 | 1,7 % | 3,5 % | p = 0,50 | p = 0,21 | p = 0,15 |
| 20261029 | 3,1 % | 4,9 % | p = 0,19 | p = 0,12 | p = 0,49 |

- Sur 1 000 rangs, la séquence utilisée reproduit la population (p ≥ 0,49 sur tous les tests). Seul un test sur huit passe sous 0,05 (graine 1, p = 0,021), ce qui n'est pas significatif une fois corrigé pour les huit comparaisons (seuil de Bonferroni 0,006).
- Les 12 premiers rangs : P(≥ 3 positions aléatoires) = 0,24 % ; P(≥ 2 dans le sous-ensemble arbitrage) = 7,4 %. Les deux anomalies ne sont pas indépendantes : une position aléatoire produit souvent une zone différente selon la source (39 % à 88 % de changement de zone pour les qualités 12 à 33). Il s'agit essentiellement d'une seule anomalie, rare mais compatible avec le hasard sur un échantillon de 12.
- **Conclusion : hasard.** L'ordre `hash(siret || graine)` ne présente pas de biais sur la population. Le seul défaut du tirage reste le partage de la graine entre validation et arbitrage (recoupement #21 / #13), déjà consigné. L'échantillon de validation n'est pas refait. S'il y avait eu biais, il aurait favorisé les cas difficiles et donc rendu le critère plus exigeant, pas plus indulgent.
- **Pour les tirages futurs** : une graine distincte par échantillon ; et un ordre fondé sur un hachage documenté et stable (`md5(siret || graine)`) plutôt que sur `hash()` de DuckDB, dont la stabilité entre versions n'est pas garantie — condition de reproductibilité du tirage. Non appliqué aux scripts du spike, pour ne pas modifier l'échantillon existant.

**Conséquence pour l'ADR « rattachement au bâtiment / RNB » :** le rattachement à un bâtiment suppose une adresse avec numéro. Les établissements à position aléatoire (≈ 2,35 % des actifs diffusibles de la population, ≈ 5 % de tous les géolocalisés hors qualité `11`) ne seront pas résolus par le RNB : ils resteront en confiance faible, ou une réponse devra s'abstenir sur leur zone quand la voie traverse plusieurs zones. L'ADR doit chiffrer cette part résiduelle et prévoir ce traitement, pas la supposer résolue.

### Pour le jeu de référence

- **Secteur sauvegardé (`SECTSAUV`)** : candidat à une question sans réponse (`out_of_corpus` ou `near_miss_level`) : un établissement du Vieux-Lyon est dans le secteur sauvegardé, régi par son propre plan de sauvegarde, non ingéré ; la bonne réponse nomme ce plan sans appliquer le règlement du PLU-H.
- Les établissements en confiance faible font de bons cas de quasi-réponse sur « dans quelle zone se trouve… ».

## Test 3 — PDF : à faire

## Test 4 — BGE-M3 : à faire

## Surprises et risques

- Lyon est codée par arrondissement dans Sirene (une seule exception) ; le niveau commune se reconstruit par agrégation.
- SRC-007 publie des coordonnées pour des établissements à diffusion partielle (301 actifs) que l'INSEE ne géolocalise pas publiquement : point à signaler au moment de toute comparaison ou publication.
- Les coordonnées du stock Sirene et celles du fichier de géolocalisation divergent souvent (15 % > 50 m) ; la zone change pour 5,1 % des établissements ayant les deux.
- Le zonage contient un secteur sauvegardé (31,2 ha, 0,84 % des établissements) hors règlement du PLU-H.
- Le règlement est découpé par zone mère : les sous-secteurs (a, b, c…) et les zones `AU*` exigent une correspondance explicite.

## Décisions à consigner en ADR

- Source de coordonnées pour la jointure spatiale : fichier de géolocalisation en principal, coordonnées du stock en sensibilité (décidé le 2026-10-28) — ADR à rédiger avec les mesures du Test 2.
- Statut de diffusion : le stock INSEE le plus récent prévaut ; jamais de coordonnées SRC-007 pour un établissement `P` (conventions §3.10).
- Indice de confiance de zone (règle, seuils révisés après le Test 2) et son usage dans les réponses.
- Correspondance code de zone → chapitre du règlement (règle de suffixe + table manuelle `AU*` ; les zones à urbaniser renvoient souvent aux règles d'une autre zone ou à une OAP — à confirmer au Test 3).
- **Après le GO :** rattachement établissement → parcelle cadastrale ou bâtiment (RNB) → zone, au lieu du point d'adresse (voir Test 2, distance à une autre zone) ; chiffrer la part résiduelle à position aléatoire.
- Protocole de contrôle par échantillon : tirages futurs par `md5(siret || graine)`, une graine par échantillon, règles de statut / remplacement / fin fixées avant le tirage.

## Impact sur le planning

À établir en session 6.
