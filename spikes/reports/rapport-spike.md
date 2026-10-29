# Rapport de spike — 2026-10-28

## Verdict global : GO avec réserves (2026-10-29)

**Fondement : les mesures seulement.** Les quatre tests atteignent leurs critères GO, tels qu'appliqués ; aucun critère n'a été assoupli au moment de rendre un verdict, mais plusieurs règles de contrôle ont été fixées en cours de route, et la vérification humaine a été partiellement remplacée par des vérifications automatisées pour les tests 2 et 3 ; pour le test 4, chaque réussite et chaque échec reposent sur une lecture humaine (section « Écarts au protocole »). La faisabilité technique est établie sur le M2 (temps et mémoire largement dans les limites). Ce qui n'est **pas** démontré : la fiabilité de la recherche pour une question ciblant l'article d'une zone sans filtre (6/9), un mécanisme d'abstention (le score seul ne suffit pas), l'extraction de qualité des cahiers communaux, l'arbitrage entre sources de coordonnées.

| Test | Verdict |
|---|---|
| Test 0 — Préparation | Fait (registre v0.3, manifestes, immuabilité par ressource) |
| Test 1 — Référentiel et Sirene | **GO avec réserves** (voir ci-dessous) |
| Test 2 — Jointure spatiale | **GO avec réserves** (critères atteints, règles de contrôle fixées en cours de route) |
| Test 3 — PDF | **GO avec réserves** (critères atteints sur le règlement ; cahiers et choix d'extracteur à traiter) |
| Test 4 — BGE-M3 | **GO avec réserves** (16/20 ; requêtes ciblant une zone : 6/9 sans filtre) |

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

## Test 2 — Jointure spatiale : GO avec réserves

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

## Test 3 — PDF : GO avec réserves

Scripts : `spikes/test3_extraction.py` (extraction, échantillon, revue, structure, passages), `spikes/test3_tableaux.py` (tableaux du règlement), `spikes/test3_grille.py` (pré-remplissage de la grille). Sorties dans `spikes/output/pdf/` (non versionné) : `revue.html`, `grille.csv`, `passages.jsonl`, `tableaux/revue_tableaux.html`, `metrics.json`.

### Corpus pilote (pièces du document GPU `200046977_PLUi_20260326`)

| Doc | Pièce (SRC-005) | Pages PDF | Version lue dans la pièce |
|---|---|---|---|
| A — règlement, zones économiques + zones à urbaniser | `reglement_ecrit` | 581–680, 729–748 (120 p.) | « Modification n° 4 – Approbation 2024 » (pied de page) |
| B — OAP d'Oullins (8 OAP, dont l'OAP 7 « ZA de la Saulaie », vocation économique) | `cahier_communal_oullins` (SECT45) | 56–73 (18 p.) | « Mise en compatibilité n°10 – Approbation 2025 » |
| C — cahier communal de Pierre-Bénite (diagnostic, PADD, POAH, OAP, surfaces) | `cahier_communal_pierre_benite` (SECT46) | 1–67 | « Modification n°4 – Approbation 2024 » |

Les OAP ne sont pas des pièces séparées au GPU : elles forment la partie 4 de chaque cahier communal. Le cahier contient aussi le rapport de présentation communal (type couvert sans pièce supplémentaire). **Chaque pièce porte sa propre procédure**, distincte de la date de publication GPU (2026-04-23) : une citation doit donner la version de la pièce (conventions §6).

Nouvelles ressources téléchargées dans `data/raw/SRC-005/2026-10-28/<ressource>/` (immuabilité par ressource, conventions §3.1) : `cahier_communal_oullins` (30,5 Mo, sha256 `67a23086`), `cahier_communal_pierre_benite` (14,7 Mo, `63d7187f`), `plan_de_secteurs` (0,6 Mo, `e5f625cf`).

### Performances

| Étape | 1er passage (froid) | 2e passage | Pic RSS (2e) |
|---|---:|---:|---:|
| PyMuPDF A (120 p.) | 58,0 s | 11,2 s (10,7 p/s) | 387 Mo |
| PyMuPDF B (18 p.) | 10,1 s | 3,1 s | 403 Mo |
| PyMuPDF C (67 p.) | 36,8 s | 9,6 s | 505 Mo |
| Docling : import + chauffe (**exclu**) | 51,7 s | 9,9 s | 881 Mo |
| Docling A | 131,9 s | 50,8 s (2,4 p/s) | 1 318 Mo |
| Docling B | 25,8 s | 8,8 s | 726 Mo |
| Docling C | 121,8 s | 51,3 s (1,3 p/s) | 965 Mo |

Le temps PyMuPDF comprend la détection de tableaux et le comptage des tracés (le texte seul est bien plus rapide). Le premier passage cumule téléchargement des modèles Docling (**529 Mo** réels : `docling-models` 358 Mo + `docling-layout-heron` 171 Mo ; *corrigé le 2026-10-28 : la valeur de 1 590 Mo publiée d'abord comptait deux fois les fichiers liés du cache*), premiers chargements et disque froid ; les deux passages sont consignés. Mémoire : < 1,4 Go, compatible avec la machine. OCR désactivé (PDF natifs).

### Pages graphiques

Règle fixée avant le tirage : < 300 caractères extractibles **et** (≥ 50 % de la page en images **ou** > 2 000 tracés). Résultat : A 0 page, B 2, C 5, classées « graphique, hors périmètre sans OCR ». **La règle manque deux cartes de l'échantillon** (B p. 59 et p. 63 : 49,9 % et 45,3 % d'image, juste sous le seuil) : classées graphiques à l'œil dans la grille, règle non modifiée après coup ; à revoir (seuil d'image ou critère « texte majoritairement de légende »).

### Grille (10 pages par document, 2 extracteurs)

Tirage `md5(doc_id | page | graine)`, une graine par document (3101, 3102, 3103). Revue : `revue.html` (rendu PNG, texte PyMuPDF, texte Docling côte à côte). Grille issue d'un **pré-remplissage automatisé** (rendus PNG et textes), puis **relue par le porteur le 2026-10-28** : 60 lignes sur 60 déclarées conformes, sans correction. Le porteur n'ayant pas modifié les fichiers, `relu_par_humain = oui` a été reporté dans la grille par un report automatisé, sur cette déclaration ; la relecture couvre aussi `revue.html` et `tableaux/revue_tableaux.html`.

| Document | PyMuPDF : lisible et dans l'ordre | Docling : lisible et dans l'ordre | Pages graphiques |
|---|---:|---:|---:|
| A — règlement | 10/10 | 10/10 | 0 |
| B — OAP | 0/10 | 7/10 | 3 |
| C — cahier | 2/10 | 5/10 | 0 |

- **Règlement (une colonne)** : les deux extracteurs donnent un texte lisible et ordonné ; Docling écarte en-têtes et pieds de page, PyMuPDF les garde (retirés au découpage).
- **Cahiers (deux colonnes, encadrés, cartes)** : `PyMuPDF get_text(sort=True)` **entrelace les colonnes ligne à ligne** (inutilisable) ; Docling restitue l'ordre des colonnes et les titres.
- **Défaut de Docling** : sur les pages de graphiques (C p. 32, 34), **duplication massive** du texte (une même ligne jusqu'à 5 fois, étiquettes de camemberts répétées) ; puces mal décodées (« ͳ ») dans les OAP.

### Tableaux du règlement

Les chapitres du corpus (zones économiques et AU) **ne contiennent aucun tableau de règles** : les deux « tableaux » détectés par Docling sont les sommaires des pages de garde de section. Le critère a donc été évalué sur le règlement complet : PyMuPDF trouve des tableaux sur **43 pages** (partie I : stationnement, définitions ; quelques zones mixtes). Tirage de 5 pages (graine 3104 : p. 101, 103, 277, 362, 436) :
- les deux extracteurs détectent les mêmes tableaux (8 au total) ;
- **Docling** : en-têtes et cellules propres, cellules fusionnées correctement restituées (ex. p. 101, normes de stationnement par secteur ; p. 362, coefficients de pleine terre par sous-secteur URm2) ;
- **PyMuPDF** : mots collés dans les en-têtes (« Secteursde », « Coefficientdepleineterre »), colonnes fantômes (« Col1 ») sur les cellules fusionnées ; exploitable sur les tableaux simples seulement.
- Revue visuelle : `tableaux/revue_tableaux.html` (relue par le porteur, conforme).

### Structure zone → article (règlement)

Repères tirés du texte réel : en-tête courant « … PARTIE II  Zone <code> » (zone de chaque page), « CHAPITRE n - … », sections « n.n - … », sous-sections « n.n.n - … » ; seconde ligne d'un titre rattachée au titre (courte, sans ponctuation finale, en capitales ou commençant par une minuscule). Résultat sur les 120 pages, mesuré **en caractères** : **94,6 % du texte rattaché à zone > chapitre > article**, 5,3 % aux préambules de zone (caractère, rappels), 0,1 % aux pages de garde de section ; 8 zones (UEa, UEc, UEi1, UEi2, UEl, UEp, AUs.co, AU).

Défauts du premier découpage trouvés et corrigés : (1) préambule d'une zone rattaché au dernier article de la zone précédente (chemin non réinitialisé au changement de zone) ; (2) seconde ligne des titres devenue un passage à part (21 fragments du type « soumis à conditions », « publiques ou privées ») et titres tronqués. Limite restante : un titre de sous-section emporte le début de sa première phrase (« 1.2.1 - Sont autorisés, les constructions… suivants à »). L'en-tête du PDF porte la coquille « Aus.co » (normalisée en « AUs.co »).

Cahiers : découpage par la table des matières et par OAP (« OAP n Nom », numéro parfois placé après le nom par le tri spatial) ; **texte des passages pris dans Docling** (ordre des colonnes), doublons exacts d'une même page supprimés.

### Corpus figé du Test 4

`spikes/output/pdf/passages.jsonl` — **360 passages** (A 262, B 17, C 81), **90 634 tokens BGE-M3** (tokenizer seul), sha256 `fda1d07b9ca9299e207877dac53110641838095862b479328c57bd1c48eaffdb`. Passages de plus de 2 000 caractères découpés aux limites de phrase (`partie` / `parties`). Champs : `passage_id`, `doc_id`, `source_id`, `version_gpu`, `version_piece`, `page_debut`, `page_fin`, `zone`, `chemin`, `texte`, `extracteur`, `partie`, `parties`. Extracteur : PyMuPDF pour A, Docling pour B et C.

**Version au niveau du passage.** Distribution des mentions de version lues page par page : A « Modification n° 4 – Approbation 2024 » sur 120 / 120 pages ; B « Mise en compatibilité n°10 – Approbation 2025 » sur 18 / 18 ; C « Modification n°4 – Approbation 2024 » sur 66 / 67 (page de couverture sans en-tête). La version ne varie pas à l'intérieur d'une pièce ; elle est néanmoins portée par chaque passage (`version_piece`, lue sur sa page de début) pour rester juste si une pièce mêlait des versions.

**Doublons** (texte normalisé : minuscules, sans accents ni ponctuation ; quasi-doublons : `difflib` ratio > 0,9) :
- dans un même document, une même zone et un même chemin : **0** après correction des titres (les 21 fragments de titres en étaient la seule source) ; rien n'a été retiré par le dédoublonnage ;
- **entre zones** : 44 groupes de textes identiques (112 passages en surnombre) et 210 paires quasi identiques — le règlement réécrit le même article dans chaque zone (implantation, distances, renvois à la partie I). **Conservés** : chaque passage porte sa zone, et une question sur une zone doit retrouver l'article de cette zone ;
- dans une même zone : 24 paires quasi identiques — phrases de renvoi formulaires (« Les dispositions règlementaires relatives aux voies et aux accès se situent au chapitre 5 de la partie I… ») dont seul l'objet change : contenus distincts, conservés.
- Conséquence pour le Test 4 : un résultat de recherche peut renvoyer le même texte pour plusieurs zones ; regrouper ou filtrer par zone est à mesurer.

### Codes AU* et codes résiduels (question du Test 2)

Règle lue dans le règlement : zone **AUs.co** (p. PDF 731) — « Dès lors que les conditions d'ouverture à l'urbanisation sont réunies, le règlement de la zone U correspondante s'applique (par exemple dans une zone AURm2 s'appliquera le règlement de la zone URm2) » ; chapitres 2 à 5 (p. 734–737) : « les règles applicables […] sont celles prévues par le règlement de la zone "U" de référence […] indiquée […] après le sigle AU ». Zone **AU** (p. 739) : AU1 mixte, AU2 à dominante d'habitat, AU3 à dominante d'activité, ouverture différée.

| Codes | Chapitre AU | Zone U de référence (chapitre, page PDF) |
|---|---|---|
| AU1, AU2, AU3 | Zone AU (p. 739) | — (ouverture différée) |
| AUCe4a, AUCe4b | Zone AUs.co (p. 731) | UCe4 (p. 199) |
| AUEc · AUEi1 · AUEi2 · AUEl | Zone AUs.co | UEc (595) · UEi1 (611) · UEi2 (633) · UEl (655) |
| AUL · AUPr · AUSP | Zone AUs.co | UL (683) · UPr (379) · USP (713) |
| AURc2, AURc2b, AURc2c | Zone AUs.co | URc2 (249) |
| AURi1a–c · AURi2a–c | Zone AUs.co | URi1 (271) · URi2 (293) |
| AURm1, AURm1a–d · AURm2a–d | Zone AUs.co | URm1 (315) · URm2 (347) |

- **UPpa** : secteur de la zone UPp — « La zone comprend un secteur UPpa de protection forte liée à la présence de sites archéologiques majeurs » (chapitre Zone UPp, p. 697).
- **UCe3-p** : **introuvable dans le règlement écrit** (ni titre, ni texte). Non rattaché ; à instruire (pièce graphique, prescription, cahier communal ?), sans supposition.
- Bilan : 31 des 32 codes sans correspondance automatique sont rattachés avec citation ; **le critère « table manuelle de quelques dizaines de lignes » du Test 2 est confirmé** (13 lignes de correspondance AU → U, plus UPpa).

### Écart 67 / 58 (question du Test 2) : résolu, il n'y a pas d'écart

`plan_de_secteurs` (« Révision n°2 – Approbation 2019 ») numérote 67 secteurs : 58 communes du découpage à 59 sans Lyon (dont Oullins = 45 et Pierre-Bénite = 46, séparées) et les 9 arrondissements de Lyon (secteurs 31–39).

| | Secteurs 01–30, 40–67 | Secteurs 31–39 (Lyon) | Total |
|---|---:|---:|---:|
| Plan de secteurs | 58 communes | 9 arrondissements | 67 |
| Cahiers « communal » | 58 | 9 | 67 |
| Cahiers « arrondissement » | — | 9 | 9 |
| SRC-003 | 58 entrées communales | 9 arrondissements (`uid` 69381–69389) | 67 |

Les 9 cahiers « communaux » des secteurs 31–39 portent tous la page de titre « Lyon — Cahier communal » mais ont des contenus distincts (sha256 tous différents, lus en mémoire, non stockés). Le « 58 » du Test 2 ne comptait que les entrées non lyonnaises de SRC-003.

### Pour le jeu de référence

- **Oullins et Pierre-Bénite ont des cahiers communaux séparés** (SECT45, SECT46) malgré la fusion du 1er janvier 2024, avec des procédures différentes (« Mise en compatibilité n°10 – 2025 » / « Modification n°4 – 2024 ») : question piège sur la commune 69149 et sur la version citée.
- Une citation d'OAP ou de règlement doit donner la version de la pièce, pas seulement la date de publication GPU.

### Verdict Test 3 : GO avec réserves

| Critère | État |
|---|---|
| ≥ 90 % des pages du règlement lisibles et dans l'ordre | **Atteint** : 10/10 (100 %) pour PyMuPDF comme pour Docling, sur les lignes relues. |
| Structure zone → article reconstructible automatiquement | **Atteint** : 94,6 % du texte (en caractères) rattaché à zone > chapitre > article, 5,3 % aux préambules de zone ; titres reconstruits automatiquement. |
| Au moins un extracteur traite les tableaux du règlement de façon exploitable | **Atteint, hors corpus pilote** : le corpus ne contient aucun tableau de règles ; sur 5 pages à tableaux tirées dans le règlement complet, Docling restitue les 8 tableaux de façon exploitable (relu). |

**Pourquoi « avec réserves ».** Les trois critères, qui portent sur le règlement, sont atteints. Mais :
1. le critère des tableaux a été évalué **hors du corpus pilote** (5 pages tirées dans le règlement complet), le corpus prévu n'en contenant aucun : changement de périmètre consigné ;
2. **les cahiers communaux** (OAP, rapport de présentation) sont nettement moins bien extraits : PyMuPDF inutilisable sur les colonnes (0/10 et 2/10), Docling 7/10 et 5/10, avec duplications massives sur les pages de graphiques et puces mal décodées ;
3. la règle « graphique » a manqué deux cartes (seuil d'image à revoir) ;
4. `UCe3-p` reste sans rattachement au règlement ;
5. **aucun extracteur ne suffit seul** : PyMuPDF pour le règlement (rapide, une colonne), Docling pour les cahiers et les tableaux ; choix à consigner en ADR.

## Test 4 — BGE-M3 : GO avec réserves

### Protocole (fixé le 2026-10-28, avant l'encodage)

- **Corpus** : `spikes/output/pdf/passages.jsonl`, 360 passages, 90 634 tokens, sha256 `fda1d07b9ca9299e207877dac53110641838095862b479328c57bd1c48eaffdb` (vérifié avant encodage).
- **Requêtes** : `spikes/queries_pilote.tsv`, écrites par le porteur, **figées** (sha256 `1355d77e18f317dc85dae1c0b350496d3ed6f4d2cfe703d7c0bc6856857bdb5d`) : 20 requêtes du critère (types L littérale, P paraphrase, U usager) et une sonde Q21 hors critère.
- **Revue préalable des requêtes** (recherche textuelle dans le document et la zone attendus, sans classement) : l'ancienne Q11 (« logement de gardien ») n'avait **aucun** passage traitant du sujet ; remplacée par « règles de hauteur des bâtiments dans les zones d'activités » (23 passages ciblés). L'ancienne Q11 devient **Q21, sonde hors critère** : encodée et classée dans les 4 modes, scores des top 10 consignés, exclue du critère ; elle sert à caler un seuil d'abstention. Q10 (le corpus n'a que le renvoi vers la partie I) et Q14 (hauteur des clôtures traitée en UEi1 et UEi2 seulement) confirmées.
- **Modes** : dense, sparse, hybride (fusion RRF), hybride filtré sur la zone attendue (Q01–Q08, Q13 ; pour Q13, zone `AUEi1` absente des passages, filtre sur `AUs.co` ou `UEi1` d'après la correspondance du Test 3).
- **Critère GO** : hybride **sans** filtre ; une requête est réussie si au moins un passage jugé `pertinent = oui` (ligne `relu_par_humain = oui`) figure dans son top 10 ; GO si **≥ 14 / 20**. Le gain du filtre est rapporté à part, comme mesure.
- **Pool de jugement** : top 10 hybride ∪ top 5 dense ∪ top 5 sparse ∪ top 5 hybride filtré ; pré-indications automatiques (doc, zone) non contraignantes.
- **Règles de jugement particulières** :
  - **Q13** : pertinents = la règle de renvoi des zones AU indicées (p. 731, chapitre AUs.co) ou un article du chapitre UEi1 ; le passage de renvoi seul suffit pour une réussite ;
  - **Q19** : est jugé pertinent (« oui ») **tout passage sur les règles d'extension d'une zone économique, quelle qu'elle soit** : le retrieval seul ne connaît pas la zone de l'entrepôt (aucun lien commune → zone dans le règlement ; ce lien relève de la jointure spatiale) ;
  - **Q10** : le bon passage est le renvoi vers le chapitre 5 de la partie I.
- **Limite relevée (Q10, ancienne Q11)** : la v1 devra intégrer la **partie I du règlement** (dispositions communes : stationnement, définitions), absente du corpus pilote.

### Mesures

Script : `spikes/test4_bge_m3.py`. Sorties (non versionnées) : `spikes/output/qdrant/`, `spikes/output/test4/{metrics.json, jugements.csv, revue_requetes.html}`. Environnement : torch 2.14.1, FlagEmbedding 1.4.2 (avec transformers 5.21.0, chargé sans incident), qdrant-client 1.20.0 ; **device `mps`**, fp16.

| Mesure | Valeur |
|---|---:|
| Modèle BGE-M3 téléchargé | **4,59 Go** réels (`pytorch_model.bin` 2,27 Go + `model.onnx_data` 2,27 Go, la version ONNX n'étant pas utilisée) |
| Chargement du modèle (exclu des mesures) | 133 s (dont téléchargement), pic RSS 2,2 Go |
| Encodage du corpus (360 passages, 90 634 tokens, dense + sparse) | **30,0 s** — 720 passages/min, 3 022 tokens/s |
| Mémoire pendant l'encodage | RSS 224 Mo + **2,27 Go alloués sur MPS** (mémoire unifiée) ; pic du processus 2,23 Go |
| Indexation Qdrant local (vecteurs nommés `dense` 1024 cosinus + `sparse`) | 0,34 s ; 360 points ; **4,3 Mo** sur disque |
| Encodage des 21 requêtes | 0,5 s |
| Latence de recherche (médiane / max, ms) | dense 0,7 / 38 ; sparse 3,3 / 4,3 ; hybride RRF 4,4 / 7,0 ; hybride filtré 7,8 / 14,4 |

Contrôle de cohérence : Q05 ramène bien un passage UEp « coefficient de pleine terre » en dense ou en sparse.

### Multivecteur (mesuré, non indexé)

Taille = tokens × 1024 × 4 octets (fp32) ou × 2 (fp16). Tokens par page mesurés : règlement 396, OAP 402, cahier 535. Cahiers : 76 × 67 à 150 pages (fourchette observée).

| Périmètre | Tokens | fp32 | fp16 | Encodage estimé (débit mesuré) |
|---|---:|---:|---:|---:|
| Corpus pilote | 90 634 | 0,37 Go | 0,19 Go | 0,5 min |
| Règlement complet (803 p.) | ≈ 318 000 | 1,3 Go | 0,65 Go | 1,8 min |
| Règlement + 76 cahiers (bas) | ≈ 2,9 M | 11,9 Go | 5,9 Go | 16 min |
| Règlement + 76 cahiers (haut) | ≈ 6,1 M | 25,0 Go | 12,5 Go | 34 min |

Le multivecteur reste raisonnable pour le règlement seul ; avec tous les cahiers il dépasse la mémoire de la machine en fp32 et la frôle en fp16 (stockage disque ou quantification nécessaires) : cohérent avec son report en v1.1 (ADR-0001).

### Sonde Q21 (hors critère) — seuil d'abstention

Q21 (« logement de gardien », sujet absent du corpus) : score du premier résultat dense 0,526, sparse 0,108, hybride (RRF) 0,700. Parmi les 20 requêtes du critère, une a un premier score dense plus bas (Q02, 0,519), une un premier score sparse plus bas (Q20, 0,090), neuf un premier score hybride plus bas. **Un seuil simple sur le score du premier résultat ne sépare pas la sonde des requêtes légitimes** ; les scores RRF, fondés sur les rangs, ne sont pas calibrés pour cela. L'abstention devra reposer sur autre chose (ex. reranking, écart entre scores, vérification par le LLM) — à mesurer en v1.

### Jugement (porteur, 2026-10-29)

Méthode (étape 1, suffisante pour le critère) : pour chaque requête, lecture du top 10 hybride dans l'ordre jusqu'au premier passage pertinent ; lecture complète des 10 pour les requêtes en échec. **Pré-lecture automatisée, puis lecture humaine** : le porteur a vérifié les échecs (Q02, Q04, Q06, Q19) et les cas limites (Q03, Q08, Q16) dans `etape1.html`, puis, le 2026-10-29, **relu et confirmé les 17 passages pertinents retenus** (premier pertinent des 16 réussites, plus Q03 #8). Les rangs jugés « non » avant le premier pertinent des 9 autres réussites n'ont pas été relus (pré-lecture automatisée seule). Report automatisé dans `jugements.csv` (80 lignes ; colonne `methode` : `verifie_porteur` pour les 17 passages pertinents relus, `relu_par_humain = oui` ; `pre_lecture_automatisee_verifiee_porteur` pour les 44 lignes des échecs et cas limites, `relu_par_humain = oui` ; `pre_lecture_automatisee_acceptee_porteur` pour les 19 rangs « non » non relus, `relu_par_humain = non`), avec vérification de la correspondance rang → passage (une divergence de description sans effet : pour Q04, le #1 est UEc 2.2 et non le préambule de UEa). L'étape 2 (reste du pool : dense, sparse, hybride filtré) n'est pas faite ; elle est facultative.

| Requête | Type | 1er pertinent (rang hybride) | Passage |
|---|---|---|---|
| Q01 | L | 1 | UEi1 2.5.1 hauteur de façade |
| Q02 | L | **aucun** | l'article 1.1 de UEc n'est pas dans le top 10 (#1 = préambule UEc) |
| Q03 | L | 3 (et 8) | UEi2 2.4.3 règles alternatives ; 2.4.1 « limité à 60 % » au #8 |
| Q04 | L | **aucun** | l'article 2.1 de UEa n'est pas dans le top 10 |
| Q05 | L | 6 | UEp 3.2.1 « n'est pas réglementé » |
| Q06 | L | **aucun** | l'article 1.2 de UEl n'est pas dans le top 10 (#2 = préambule UEl) |
| Q07 | P | 3 | UEi1 2.2.1 retrait par rapport aux limites séparatives |
| Q08 | P | 1 | préambule AU (principe : « seule la gestion du bâti existant ») — compté oui par le porteur |
| Q09 | L | 1 | UEl 2.2 retrait ≥ 4 m |
| Q10 | L | 6 | UEl 5.2.1, renvoi au chapitre 5 de la partie I |
| Q11 | P | 1 | UEl 2.5.1 hauteur |
| Q12 | P | 1 | UEl 3.3.2 traitement paysager |
| Q13 | P | 4 | AUs.co, renvoi à la zone U de référence |
| Q14 | L | 1 | UEi1 4.5 clôtures, hauteur limitée à 2 m |
| Q15 | L | 5 | OAP 7 ZA de la Saulaie (#1 = OAP 5 La Saulaie, autre OAP) |
| Q16 | P | 3 | OAP 1 Aulagne (#2 OAP de Pierre-Bénite : non) |
| Q17 | P | 1 | PADD de Pierre-Bénite, zones d'activités |
| Q18 | L | 1 | tableau des surfaces de zonages de Pierre-Bénite |
| Q19 | U | **aucun** | seulement du diagnostic du cahier de Pierre-Bénite, aucune règle d'extension |
| Q20 | U | 1 | UEi2 1.2.1, commerce de détail sous conditions |

**Résultat : 16 / 20** (critère : ≥ 14). Par type : L 8/11, P 7/7, U 1/2. **Requêtes ciblant une zone (Q01–Q08, Q13) : 6/9** ; les trois échecs (Q02, Q04, Q06) suivent le même schéma : le **préambule de la zone** (« caractère de la zone ») remonte à la place de l'article demandé.

**Indication automatique, non jugée** (étape 2 non faite) : en mode **hybride filtré par zone**, l'article attendu de Q02 (UEc 1.1), Q04 (UEa 2.1) et Q06 (UEl 1.2) apparaît au **rang 2 ou 3** ; sans filtre, il est absent du top 10 hybride (dense : Q02 au rang 8 ; sparse : Q04 au rang 9). Le gain du filtre reste à confirmer par jugement.

### Verdict Test 4 : GO avec réserves

| Critère | Résultat |
|---|---|
| Corpus pilote indexé en < 1 h ; extrapolation au corpus complet < 4 h | **Atteint** : 30 s ; 2 à 34 min selon le périmètre (règlement seul à règlement + 76 cahiers). |
| Pic mémoire < 10 Go | **Atteint** : 2,23 Go pour le processus + 2,27 Go sur MPS. |
| Bon passage dans le top 10 pour une majorité nette (≥ 14 / 20, hybride sans filtre) | **Atteint** : 16 / 20 ; les 17 passages retenus (16 réussites) ont été relus et confirmés par le porteur le 2026-10-29 ; échecs et cas limites vérifiés par le porteur. |

Réserves :
1. **Requêtes ciblant un article d'une zone** : 6/9 sans filtre ; le préambule de zone concurrence l'article. C'est le cas d'usage central (question mixte zone → règle) : la v1 doit filtrer ou pondérer par la zone connue (la jointure spatiale fournit la zone) ; gain indiqué automatiquement, à mesurer par jugement.
2. **Abstention** : un seuil sur le score du premier résultat ne sépare pas la sonde Q21 des requêtes légitimes ; mécanisme à concevoir et mesurer.
3. **Requêtes d'usager sans zone** (Q19) : le retrieval seul ne relie pas une commune à une zone ; elles exigent la route HYBRID (SQL/spatial puis RAG).
4. Jugement limité au premier passage pertinent (suffisant pour le critère) ; la comparaison des modes (étape 2) reste à faire pour l'ADR.
5. Modèle : 4,59 Go téléchargés, dont 2,27 Go de version ONNX inutile ; en v1, limiter le téléchargement aux poids PyTorch (`snapshot_download(..., allow_patterns=…)` sur les fichiers nécessaires : poids PyTorch, configuration, tokenizer, têtes sparse et colbert), sans le dossier `onnx/`.

## Surprises et risques

- Lyon est codée par arrondissement dans Sirene (une seule exception) ; le niveau commune se reconstruit par agrégation.
- SRC-007 publie des coordonnées pour des établissements à diffusion partielle (301 actifs) que l'INSEE ne géolocalise pas publiquement : point à signaler au moment de toute comparaison ou publication.
- Les coordonnées du stock Sirene et celles du fichier de géolocalisation divergent souvent (15 % > 50 m) ; la zone change pour 5,1 % des établissements ayant les deux.
- Le zonage contient un secteur sauvegardé (31,2 ha, 0,84 % des établissements) hors règlement du PLU-H.
- Le règlement est découpé par zone mère : les sous-secteurs (a, b, c…) et les zones `AU*` exigent une correspondance explicite.

## Écarts au protocole

Pour chaque écart : ce qui était prévu, ce qui a été fait réellement, et s'il a pu changer un verdict.

| Test | Prévu | Fait réellement | A pu changer un verdict ? |
|---|---|---|---|
| 1 | Critère « tout établissement filtré rattaché au COG 2026 » | Reformulé en « perte inverse » (géolocalisé dans la Métropole, codé ailleurs) à la demande du porteur, **avant** les mesures | **Non** : fixé avant d'avoir les résultats ; plus exigeant que le critère tautologique initial. |
| 2 | Contrôle visuel humain de 10 établissements tirés au hasard (10/10) | Grille remplie par une **vérification automatisée** (BAN → cadastre → GPU), puis 4 cas revus par une **vérification automatisée par les données** (BD TOPO, tronçons de voie) avec une observation visuelle ; **vérification visuelle humaine** du porteur sur #2, #21 et #22 seulement | **Oui, en principe** : #1, #3 à #10 n'ont pas été vus par un humain ; un contrôle visuel aurait pu en déclarer un en échec. Le porteur a validé la lecture des données de #8, #9, #10. |
| 2 | Critère 10/10 sur les 10 premiers tirages | Règles de statut (limite, adresse sans numéro), de remplacement et de fin **fixées après** les premiers résultats ; 2 remplacements (rangs 11 et 12) | **Oui** : sur les 10 premiers tirages, 8 réussis et 2 indéterminables — le critère tel que formulé n'était pas atteint ; c'est la règle de fin (10 cas déterminables) qui donne 10/10. Aucun cas déterminable n'a échoué. |
| 2 | Échantillons de validation et d'arbitrage indépendants | Même graine et même hachage : recoupement #21 = #13 | **Non** : chaque échantillon reste un tirage sans biais de sa population (contrôle sur 1 000 rangs et 3 autres graines). |
| 2 | Arbitrage stock / géolocalisation sur 10 écarts > 50 m | Vérification automatisée biaisée vers le stock (coordonnées dérivées de la BAN) ; 2 cas déterminables sur 10 | **Non** pour le verdict (l'arbitrage n'entre pas dans le critère) ; la décision de source (ADR-0006) reste non éprouvée. |
| 3 | Grille de 30 pages relue par le porteur | **Pré-remplissage automatisé**, relecture déclarée par le porteur sans modification des fichiers, report automatisé de `relu_par_humain` | **Peu probable** : le critère repose sur une déclaration ; sur le règlement, les 10 pages sont lisibles et ordonnées pour les deux extracteurs, sans ambiguïté sur les rendus. |
| 3 | Tableaux du règlement évalués sur le corpus pilote | Le corpus n'en contenait aucun : évaluation sur 5 pages tirées dans le règlement complet | **Oui** : sur le corpus prévu, ce critère était non évaluable et le verdict n'aurait pas pu être GO sur ce point. |
| 3 | Découpage zone → article | Deux défauts trouvés et corrigés après le premier passage (préambules rattachés à la zone précédente, fragments de titres) | **Non** : corrections de défauts, mesure refaite sur le texte corrigé (94,6 %). |
| 4 | 20 requêtes du porteur, telles que fournies | Q11 remplacée **avant** le gel et l'encodage (aucun passage ne traitait le sujet) ; l'ancienne Q11 devient la sonde Q21, hors critère | **Non** : décidé avant tout classement. |
| 4 | Jugement humain du pool | **Pré-lecture automatisée** ; vérification humaine du porteur sur les échecs et cas limites (7 requêtes sur 20), puis, le 2026-10-29, **relecture par le porteur des 17 passages retenus** (le premier pertinent des 16 requêtes réussies, plus Q03 #8) : jugements confirmés. Les passages jugés « non » avant le premier pertinent des 9 autres réussites n'ont pas été relus (`relu_par_humain = non`) | **Non** : chaque réussite repose sur un passage relu et confirmé par un humain ; les rangs non relus ne peuvent qu'ajouter des passages pertinents, pas retirer une réussite. |
| 4 | Comparaison des modes (étape 2 du jugement) | Non faite | **Non** pour le verdict (hors critère) ; le gain du filtre par zone reste une indication automatisée. |

**Effet global.** Aucun écart n'a transformé un échec constaté en réussite. Le verdict du test 2 repose sur des règles et des vérifications qui n'étaient pas celles prévues (règles fixées après les premiers résultats, vérification humaine partielle), et celui du test 3 sur une relecture déclarée et un critère des tableaux évalué hors du corpus prévu. Pour le test 4, seuls des rangs non pertinents restent non relus, sans effet possible sur le verdict. Les verdicts restent des GO **avec réserves**, pas des GO francs.

**Recommandation pour la v1** (ADR-0012) : une revue humaine plus courte mais réellement faite, dans les fichiers de grille ; protocole, règles de statut, de remplacement et de fin fixés **avant** tout tirage ; une graine par échantillon (`md5`) ; distinction humain / automatisé ligne par ligne.

## Décisions à consigner en ADR

Rédigés le 2026-10-29 dans `docs/decisions/` ; **ADR-0006 et 0008 à 0012 acceptés**, ADR-0007 « proposé, à mesurer » : ADR-0006 (source de coordonnées et indice de confiance de zone), ADR-0007 (rattachement au bâtiment ou à la parcelle, à mesurer), ADR-0008 (extracteur PDF), ADR-0009 (représentation des passages), ADR-0010 (abstention multi-signal), ADR-0011 (partie I du règlement), ADR-0012 (tirages reproductibles et protocole de revue). Mises à jour : ADR-0002 confirmé par le test 2 ; ADR-0004 reste proposé (licence ambiguë). Détail des constats à l'origine de chaque ADR :


- Source de coordonnées pour la jointure spatiale : fichier de géolocalisation en principal, coordonnées du stock en sensibilité (décidé le 2026-10-28) — ADR à rédiger avec les mesures du Test 2.
- Statut de diffusion : le stock INSEE le plus récent prévaut ; jamais de coordonnées SRC-007 pour un établissement `P` (conventions §3.10).
- Indice de confiance de zone (règle, seuils révisés après le Test 2) et son usage dans les réponses.
- Correspondance code de zone → chapitre du règlement (règle de suffixe + table manuelle `AU*` ; les zones à urbaniser renvoient souvent aux règles d'une autre zone ou à une OAP — à confirmer au Test 3).
- **Retrieval v1** : BGE-M3 dense + sparse, fusion RRF.
  - **Cause des échecs Q02, Q04, Q06** : le nom de zone est absent du texte des passages (il n'est que dans les métadonnées), et les articles sont identiques d'une zone à l'autre ; seul le préambule nomme la zone, d'où sa remontée.
  - **Remèdes à tester ensemble en v1** : un **en-tête contextuel** préfixé au texte avant encodage (zone, libellé de zone, chapitre, article) et un **filtre de payload par zone** quand la zone est connue ; mesurer chacun et leur combinaison sur les requêtes ciblant une zone. Préambules de zone à traiter comme passages de contexte, pas de règle.
  - **Payload** : ajouter la **commune** et le **nom d'OAP** (d'après Q15 — OAP 5 « La Saulaie » devant l'OAP 7 « ZA de la Saulaie » — et Q16 — OAP de Pierre-Bénite remontée pour une question sur Oullins).
- **Abstention** : mécanisme autre qu'un seuil sur le score du premier résultat (sonde Q21 non séparable).
- **Après le GO :** rattachement établissement → parcelle cadastrale ou bâtiment (RNB) → zone, au lieu du point d'adresse (voir Test 2, distance à une autre zone) ; chiffrer la part résiduelle à position aléatoire.
- **Choix de l'extracteur pour la v1** (après relecture de la grille du Test 3) : Docling partout, ou Docling seulement pour les pages à tableaux et les cahiers (PyMuPDF pour le texte du règlement). Mesure à l'appui : sur 5 pages à tableaux du règlement (p. 101, 103, 277, 362, 436, graine 3104), les deux extracteurs détectent les mêmes 8 tableaux ; Docling restitue en-têtes et cellules fusionnées, PyMuPDF colle les mots et crée des colonnes fantômes ; coût Docling ≈ 2 s par page contre ≈ 0,1 s pour PyMuPDF, modèles 0,53 Go. À trancher aussi : nettoyage des duplications de Docling sur les pages de graphiques.
- Protocole de contrôle par échantillon : tirages futurs par `md5(siret || graine)`, une graine par échantillon, règles de statut / remplacement / fin fixées avant le tirage.

## Impact sur le planning

### Classement des décisions

| Décision | Classement | Justification (mesure) |
|---|---|---|
| Filtre de payload par zone (ADR-0009) | **v1 obligatoire** | Échecs Q02, Q04, Q06 vérifiés ; gain du filtre indiqué par une mesure automatisée (article au rang 2–3), à confirmer en v1. |
| En-tête contextuel préfixé (ADR-0009) | **v1 obligatoire** | Cause mesurée des échecs : nom de zone absent du texte, articles identiques entre zones. |
| Payload complet : zone, commune, nom d'OAP, version de la pièce, pages (ADR-0009) | **v1 obligatoire** | Q15, Q16 ; citation de la version de la pièce (conventions §6). |
| Partie I du règlement (ADR-0011) | **v1 obligatoire** | Q10 servie par un simple renvoi ; ancienne Q11 sans aucun passage. |
| Indice de confiance de zone exposé, règle révisée (ADR-0006) | **v1 obligatoire** | 20 % en confiance faible, 13 % à moins de 10 m d'une autre zone. |
| Abstention structurelle + signaux mesurés (ADR-0010) | **v1 obligatoire** | Q21 non séparable par le score ; abstention exigée par le cadrage. |
| Reranking (ADR-0001, accepté) | **v1 obligatoire** | Prévu par l'ADR-0001 ; signal d'abstention à mesurer (ADR-0010) ; non mesuré au spike. |
| Extracteur mixte PyMuPDF / Docling et nettoyage (ADR-0008) | **v1 obligatoire** | PyMuPDF inutilisable sur les cahiers ; tableaux exploitables avec Docling seulement. |
| Correspondance code de zone → chapitre (suffixe + table `AU*`) | **v1 obligatoire** | Condition de la chaîne zone → règle ; 31 codes sur 32 rattachés avec citation. |
| Protocole de tirage et de revue (ADR-0012) | **v1 obligatoire** | Écarts au protocole du spike ; reproductibilité de l'évaluation. |
| Rattachement au bâtiment / à la parcelle (ADR-0007) | **v1.1** | Critère du test 2 atteint avec le point ; mesure sur 1 000 établissements à faire ; aucune mesure n'impose la v1. |
| Optimisation du calcul de distance (411 s) | **v1.1** | Acceptable pour un traitement par lot ; sans effet sur les réponses. |
| Pages graphiques (OCR, cartes) | **v1.1** | Hors périmètre sans OCR ; règle de détection à revoir. |
| Multivecteur, quantification (ADR-0001) | **v1.1** | 12 à 25 Go en fp32 avec les cahiers : au-delà de la machine. |
| Seuil de score seul pour l'abstention | **abandonné** | Ne sépare pas la sonde Q21. |
| PyMuPDF trié (`sort=True`) pour les cahiers | **abandonné** | Colonnes entrelacées. |
| Vérification automatisée BAN comme arbitre de la source de coordonnées | **abandonné** | Biaisée : les coordonnées du stock dérivent de la BAN. |
| Tirages par `hash()` de DuckDB | **abandonné** | Stabilité entre versions non garantie ; remplacé par `md5`. |
| Dédoublonnage des articles identiques entre zones | **abandonné** | Chaque passage porte sa zone ; le supprimer empêcherait de retrouver l'article d'une zone. |

Position sur l'avis de départ du porteur : **conforme aux mesures** (filtre, en-tête, partie I, payload, indice exposé, abstention structurelle en v1 ; bâtiment en v1.1), avec trois ajouts en v1 que les mesures imposent : l'extracteur mixte et son nettoyage, la correspondance des codes de zone, le protocole de revue. Le reranker reste en v1 (ADR-0001).

### Délai

Le cadrage prévoyait 4 à 6 semaines après le GO. Charges ajoutées par le spike, estimées : partie I du règlement (2 à 3 jours, tableaux compris) ; chaîne Docling et nettoyage (2 jours) ; en-tête, payload, filtre et leur mesure (2 à 3 jours) ; indice de confiance exposé (1 jour) ; abstention structurelle et mesure des signaux (2 à 3 jours) ; correspondance des codes de zone (0,5 jour) ; revue humaine réellement faite sur le jeu de référence et les contrôles (2 à 3 jours répartis). Total ≈ 2 à 3 semaines. **Chemin critique : jeu de référence, 150 questions écrites et validées par le porteur, 5 à 6 jours de travail humain** (déjà prévu au cadrage, mais non délégable et non parallélisable avec sa propre relecture). Gain : une partie de la semaine 1 et de la semaine 2 du cadrage est déjà faite (sources figées, référentiel, jointure, extraction pilote), à réécrire proprement (≈ 1 semaine économisée).

**Estimation révisée : 6 à 8 semaines** après le GO (au lieu de 4 à 6), **à temps plein, à ajuster selon la disponibilité réelle**. Si le délai dérape, appliquer la règle du cadrage : réduire le périmètre (moins de cahiers communaux, moins de zones) avant de réduire la qualité de l'évaluation. `docs/cadrage-v1.md` est passé en v0.3 le 2026-10-29, après validation de ces classements.
