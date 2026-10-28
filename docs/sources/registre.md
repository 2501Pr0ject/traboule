# Registre des sources

**Version :** 0.3
**Date de contrôle :** 28 octobre 2026
**Périmètre :** Métropole de Lyon (58 communes au 1er janvier 2024, EPCI 200046977)
**Version machine :** `configs/sources.yaml`

## Changements depuis la v0.2

- URLs de toutes les ressources v1 résolues (API data.gouv.fr, pages INSEE, API Carto GPU) ; plus aucun `A_CONFIRMER` sur le périmètre v1.
- Premiers téléchargements figés le 2026-10-28 (`data/raw/<source_id>/2026-10-28/`), manifestes validés par le modèle `Manifest` (`spikes/download.py`), dossiers en lecture seule.
- Licences et dates constatées consignées, avec les divergences entre sources (voir SRC-004, SRC-005).
- SRC-005 : version opposable du PLU-H identifiée sur le GPU (approbation du 2026-03-26) ; règlement écrit téléchargé.
- Appariement stock Sirene ↔ géolocalisation établi sur les données (même état du répertoire, 1er octobre 2026).

## Ordre de priorité

1. SRC-001 — Sirene INSEE (stock + géolocalisation)
2. SRC-002 — Zonage du PLU-H
3. SRC-004 — COG 2026 + appartenance + table de passage
4. SRC-005 — Géoportail de l'Urbanisme (version opposable, règlement écrit)
5. SRC-003 — Catalogue des documents du PLU-H
6. SRC-007 — Sirene Métropole (contrôle croisé)
7. SRC-006 — BPE (seulement si un cas d'usage la justifie)

## Téléchargements du 2026-10-28

| source_id | fichier | taille (octets) | sha256 (8 car.) | CRS |
|---|---|---:|---|---|
| SRC-001a | `stock-stocketablissement-parquet.parquet` | 2 220 887 978 | `fb02cfad` | — |
| SRC-001a | `stocketablissement-311-description-fichier-29-01-2026.pdf` | 127 863 | `8f087087` | — |
| SRC-001b | `geoloc-geolocalisationetablissement-sirene-pour-etudes-statistiques-parquet.parquet` | 814 389 380 | `db5d9ca4` | EPSG:2154 (X, Y) + WGS84 (lat, lon) |
| SRC-001b | `documentation-geolocalisationetablissements-sirene-pouretudesstatistiques-v8.pdf` | 189 985 | `541bec41` | — |
| SRC-002 | `zonage.geojson` | 20 776 239 | `5da8a4a7` | EPSG:2154 (déclaré par le serveur) |
| SRC-003 | `catalogue.geojson` | 1 304 308 | `bba60c97` | EPSG:4326 (déclaré par le serveur) |
| SRC-004a | `cog_ensemble_2026_csv.zip` | 1 961 824 | `5c037e29` | — |
| SRC-004b | `table-appartenance-geo-communes-2026.zip` | 2 047 330 | `9e26e89a` | — |
| SRC-004c | `table_passage_geo2003_geo2026.zip` | 710 298 | `0b2d502c` | — |
| SRC-005 | `200046977_reglement_20260326.pdf` | 11 059 057 | `2aee20bf` | — |
| SRC-005 | `liste_pieces.json` | 153 306 | `762a7f0d` | — |
| SRC-007 | `sirene_metropole.csv` | 100 569 272 | `6667d68f` | EPSG:4326 (demandé dans la requête) |
| REF-COMMUNES-ML-2024 | `communes.geojson` | 1 251 747 | `151a86dd` | EPSG:4326 (déclaré par le serveur) |

Contrôles appliqués au téléchargement : sha1 et taille comparés à data.gouv pour les fichiers Sirene ; nombre d'objets reçus égal au `numberMatched` du serveur pour les ressources WFS (limite serveur : 1 000 000 d'objets par requête).

---

## SRC-001 — Sirene INSEE : stock des établissements + géolocalisation

- **Producteur :** INSEE (alimente directement data.gouv.fr).
- **Ressources retenues (format Parquet) :**
  - SRC-001a — `StockEtablissement` du **1er octobre 2026** ([fiche data.gouv](https://www.data.gouv.fr/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret), jeu `5b7ffc618b4c4169d30727e0`), 44 282 364 lignes, 54 colonnes, dessin de fichier 3.11.
  - SRC-001b — « Géolocalisation des établissements du répertoire Sirene pour les études statistiques », **octobre 2026**, publié le 2026-10-21 ([fiche data.gouv](https://www.data.gouv.fr/datasets/geolocalisation-des-etablissements-du-repertoire-sirene-pour-les-etudes-statistiques), jeu `61d5e2d372a52d9f9411ff88`), 38 016 211 lignes, 19 colonnes, documentation v8.
- **Licence constatée :** Licence Ouverte 2.0 (`lov2` sur data.gouv ; mentions légales insee.fr). Obligations légales Sirene sur les données personnelles maintenues.
- **Utilisation :** établissements actifs **et fermés**, NAF, jointure spatiale, pont IRIS vers les statistiques INSEE infracommunales.

**Appariement stock ↔ géolocalisation (constaté le 2026-10-28).** La documentation v8 ne précise pas sur quel stock la géolocalisation est calculée : elle indique seulement que les établissements sont géolocalisés « à l'adresse indiquée dans la base Sirene disponible mensuellement » et que le fichier est « publié en fin de mois ». Seule une paire est en ligne (stock du 2026-10-01, géolocalisation d'octobre 2026). Mesure sur les données :
- 69 SIRET de la géolocalisation sur 38 016 211 sont absents du stock du 1er octobre ;
- parmi les établissements diffusibles (`O`) et actifs (`A`), 98,5 % de ceux créés en septembre 2026 et 97 % de ceux dont le dernier traitement date de la semaine du 28 septembre sont géolocalisés.

**Conclusion (inférence, pas une information du producteur) :** la géolocalisation d'octobre 2026 correspond au même état du répertoire que le stock du 1er octobre 2026. La paire retenue est donc SRC-001a 2026-10-01 + SRC-001b octobre 2026.

**Constaté sur les fichiers :**
- Noms des champs du stock : `siret`, `codeCommuneEtablissement`, `activitePrincipaleEtablissement`, `activitePrincipaleNAF25Etablissement`, `etatAdministratifEtablissement`, `dateCreationEtablissement`, `statutDiffusionEtablissement`, `coordonneeLambertAbscisseEtablissement`, `coordonneeLambertOrdonneeEtablissement` (texte), etc.
- Champs de la géolocalisation : `siret`, `x`, `y`, `qualite_xy`, `epsg`, `plg_code_commune`, `plg_iris`, `plg_qp24`, `plg_qp15`, `plg_zus`, `plg_qva`, `distance_precision`, `qualite_*`, `y_latitude`, `x_longitude`.
- **`x`, `y`, `y_latitude`, `x_longitude` sont en `FLOAT` 32 bits** : précision d'environ 0,5 m sur Y en Lambert 93.
- Colonne `epsg` par ligne : 2154 (36 947 800 lignes) et des CRS d'outre-mer (5490, 2975, 2972). Filtrer sur `epsg = '2154'` avant toute jointure spatiale.
- `plg_code_commune` et `plg_iris` sont en **géographie au 1er janvier 2024** (documentation v8), pas en COG 2026.
- Statut de diffusion dans le stock : `O` 38 508 105, `P` 5 774 259 (13 %).
- Dates de création aberrantes dans le stock (jusqu'en 5015) : à filtrer et à quantifier au Test 1.
- Aucun doublon de SIRET dans la géolocalisation.
- **Le fichier de géolocalisation ne reste en ligne qu'un mois, sans archive** (documentation v8) : la copie de `data/raw/` est la seule trace.
- Les deux PDF de documentation ont été remplacés sur place le 2026-07-02 sans mise à jour du sha1 déclaré sur data.gouv ; le fichier téléchargé correspond au sha1 de l'analyse data.gouv (`analysis:checksum`). Consigné dans leurs manifestes.

**Contrôles restant à faire (Test 1) :**
1. Niveau géographique du code commune pour Lyon : commune 69123 ou arrondissements 69381–69389 ?
2. Millésime des codes commune du stock.
3. Part des établissements actifs sans géolocalisation, ventilée par statut de diffusion.
4. Distribution des indicateurs de qualité de géolocalisation.
5. Taux de jointure stock ↔ géolocalisation sur la Métropole.
6. Comparaison des coordonnées du stock et de la géolocalisation (couverture, écart en mètres).

**Limites connues :**
- Les établissements à diffusion partielle n'ont ni adresse précise ni géolocalisation publique. Comptages spatiaux structurellement sous-estimés, surtout pour les entrepreneurs individuels.
- Une coordonnée d'établissement est une adresse, pas l'emprise réelle de l'activité.

## SRC-002 — Zonage du PLU-H

- **Producteur :** Métropole de Lyon. **Fiche :** [data.gouv](https://www.data.gouv.fr/datasets/zone-du-plu-h-de-la-metropole-de-lyon) (jeu `5e3aecb18b4c413b98daa42c`, mise à jour 2026-10-28).
- **Accès :** WFS GeoServer data.grandlyon.com, couche `metropole-de-lyon:plu_h_opposable.pluzone`. Les ressources publiées sont des requêtes générées à la volée : leurs dates de « modification » sur data.gouv sont des métadonnées, pas la version des données.
- **Téléchargé :** GeoJSON avec `SRSNAME=EPSG:2154` (accepté par le serveur ; CRS déclaré `urn:ogc:def:crs:EPSG::2154`, ordre X/Y vérifié), 4 487 objets, 20,8 Mo.
- **Licence constatée :** Licence Ouverte 2.0 (`lov2`).
- **Attributs :** `zone`, `zonage`, `stecal`, `plafond`, `ces`, `ces_bande_principale`, `ces_bande_secondaire`, `cpt`, `cpt_bande_principale`, `cpt_bande_secondaire`, `hauteur_bande_principale`, `hauteur_bande_secondaire`, `last_update`, `last_update_fme`, `gid`. Certaines règles chiffrées sont portées directement par les objets.
- **Statut des attributs chiffrés :** `ces*`, `cpt*`, `hauteur_*` et `plafond` sont une **synthèse** produite par la Métropole. **Le règlement écrit (SRC-005) fait foi en cas d'écart.** Un attribut peut servir à filtrer, sélectionner ou compter ; toute affirmation sur le contenu d'une règle cite le règlement écrit (SRC-005).

**Contrôles :**
1. ~~CRS déclaré~~ : EPSG:2154 obtenu directement. Cohérence avec les coordonnées Sirene à vérifier au Test 2.
2. Validité des géométries (`ST_IsValid`), chevauchements, trous.
3. Champ du code de zone et correspondance avec les intitulés du règlement écrit.
4. Version représentée et concordance avec la version GPU du 2026-03-26 (SRC-005).
5. Couverture : la somme des zones couvre-t-elle tout le territoire des 58 communes ?

**Limite connue :** le zonage ne suffit pas à déterminer toutes les règles applicables (prescriptions surfaciques/linéaires, servitudes, OAP).

## SRC-003 — Catalogue des documents du PLU-H

- **Producteur :** Métropole de Lyon. **Fiche :** [data.gouv](https://www.data.gouv.fr/datasets/acces-direct-aux-documents-constitutifs-du-dossier-plu-h-par-commune-via-le-site-internet-du-plu-h-de-la-metropole-de-lyon) (jeu `5e3aec728b4c4137ce5aa0bf`).
- **Téléchargé :** WFS `plu_h_opposable.pludocumentcommune`, GeoJSON EPSG:4326, **67 objets** (téléchargement complet).
- **Licence constatée :** Licence Ouverte 2.0 (`lov2`) pour le catalogue uniquement.

**Contrôles :**
1. Tester les liens ; catégoriser les documents (règlement, OAP, rapport de présentation, plans).
2. Conditions de réutilisation **des documents cibles** (la licence du catalogue ne les couvre pas automatiquement).
3. Découpage : 67 objets = 58 communes + 9 arrondissements ? Ou 59 communes (Oullins et Pierre-Bénite séparés) + autre chose ? À vérifier ; à rapprocher des 76 cahiers communaux du GPU.

**Limite connue :** c'est un catalogue, pas le corpus.

## SRC-004 — Référentiel géographique INSEE

| | Ressource | Page | Publication | Format |
|---|---|---|---|---|
| SRC-004a | `cog_ensemble_2026_csv.zip` (15 CSV, dont `v_commune_2026`, `v_mvt_commune_2026`) | [COG 2026](https://www.insee.fr/fr/information/8740222) | non affichée ; fichiers datés du 2026-02-13 | CSV |
| SRC-004b | `table-appartenance-geo-communes-2026.zip` (onglets `COM`, `ARM`, `Zones_supra_communales`) | [appartenance](https://www.insee.fr/fr/information/7671844) | 2026-03-19 | xlsx |
| SRC-004c | `table_passage_geo2003_geo2026.zip` (onglets « Table de passage », « Liste des fusions »…) | [tables de passage](https://www.insee.fr/fr/information/7671867) | 2026-03-19 | xlsx |

- **Licence constatée :** Licence Ouverte 2.0 selon les [mentions légales insee.fr](https://www.insee.fr/fr/information/2008466) (« sauf mention contraire »). **Divergence :** la fiche data.gouv du COG (jeu `58c984b088ee386cdb1261f3`) indique `fr-lo` (Licence Ouverte 1.0). Les deux sont consignées.
- **Lecture :** les classeurs xlsx ont leur en-tête de données en ligne 6 ; l'extension `excel` de DuckDB les lit (`read_xlsx(..., sheet=..., range='A6:...')`).
- **Aperçu (non contractuel, à refaire au Test 1) :** l'onglet `COM` de la table d'appartenance compte 58 communes avec `EPCI = 200046977`.

**Contrôles :**
1. 58 communes pour l'EPCI 200046977 au COG 2026 ; Lyon (69123) + 9 arrondissements (69381–69389) dans une table distincte.
2. Code et date d'effet de la commune issue du regroupement Oullins + Pierre-Bénite (à lire dans `v_mvt_commune_2026` et la liste des fusions, ne pas supposer).
3. Table de correspondance `code_2023 → code_2026` documentée et testée.

**Règle de modélisation :** les arrondissements sont des subdivisions de Lyon, jamais des communes supplémentaires.

## SRC-005 — Géoportail de l'Urbanisme (GPU)

- **Producteur :** Métropole de Lyon ; diffusion par le Géoportail de l'Urbanisme (IGN / ministère).
- **Pourquoi :** depuis le 1er janvier 2023, la publication sur le GPU conditionne le caractère exécutoire d'un document d'urbanisme. C'est la référence de la **version opposable**.
- **Accès constaté :** [API Carto, module GPU](https://www.data.gouv.fr/dataservices/api-carto-module-geoportail-de-lurbanisme-gpu) (`https://apicarto.ign.fr/api/gpu`, spécification OpenAPI `https://apicarto.ign.fr/api/doc/gpu.yml`) pour retrouver le document couvrant un point ; API du site GPU (`/api/document/<id>/details`, `/files/<nom>`) pour les pièces écrites. Aucun compte nécessaire.
- **Version opposable (constatée le 2026-10-28) :**

| Champ | Valeur |
|---|---|
| Titre | Plan Local d'Urbanisme intercommunal (PLUi) GRAND LYON LA METROPOLE |
| Partition | `DU_200046977` |
| Nom du document | `200046977_PLUi_20260326` |
| Identifiant GPU | `4f3ddc27a9611b4bc94fa161443b8e86` |
| Statut | `APPROVED` / `EN_VIGUEUR` |
| Date d'approbation | 2026-03-26 (lue dans le nom du document, convention CNIG) |
| Publication GPU | 2026-04-23 |
| Projection | EPSG:2154 |
| Pièces écrites | 617 PDF, dont `200046977_reglement_20260326.pdf` (règlement écrit, un seul fichier), 76 cahiers communaux, 4 parties du rapport de présentation, PADD |
| Archive complète | 3,1 Go — **non téléchargée** |

- **Téléchargé :** le règlement écrit (11,1 Mo) et la liste JSON des 617 pièces.
- **Licence constatée :** les [CGU du GPU](https://www.geoportail-urbanisme.gouv.fr/cgu/) soumettent les données d'urbanisme à « la licence ouverte », avec un lien vers le texte Etalab de 2014 (version 1). **Version applicable ambiguë** (1.0 ou 2.0) ; le contenu propre du site relève d'un régime distinct.

**Contrôles :**
1. ~~Identifiant et date de la version publiée~~ : faits (ci-dessus).
2. Concordance des codes de zone entre GPU et data.grandlyon (SRC-002).
3. Structure par zone du règlement écrit (Test 3) ; le PDF GPU peut devenir la source du corpus RAG (ADR-0004).
4. Aucune procédure (modification, mise à jour) postérieure au 2026-03-26 ne doit exister sans être publiée : à vérifier avant de figer le corpus.

## SRC-006 — Base permanente des équipements (optionnelle)

Candidate uniquement si un cas d'usage la justifie. Contrôles : licence, millésime géographique, niveaux disponibles, valeur ajoutée mesurable.

## SRC-007 — Sirene de la Métropole de Lyon (contrôle croisé)

- **Producteur :** Métropole de Lyon à partir de Sirene. **Fiche :** [data.gouv](https://www.data.gouv.fr/datasets/base-sirene-de-la-metropole-de-lyon) (jeu `62dfe1518bcb48c2eb805b6d`), mise à jour observée au 2026-08-04.
- **Téléchargé :** WFS `insee.sirene`, CSV EPSG:4326, **329 197 objets**, 100,6 Mo. Colonnes : `siret`, `siren`, `denomination`, `datecreation`, `adresse`, `commune`, `insee`, `siege`, `enseigne`, `trancheeffectifs`, `activitenaf`, `employeur`, `datemaj`, `the_geom`…
- **Licence constatée :** Licence Ouverte 2.0 (`lov2`).
- **Limites :** établissements **actifs** géolocalisés uniquement ; retard de mise à jour ; géocodage propre à la Métropole.
- **Utilisation :** comparer les comptages et les coordonnées avec SRC-001 ; documenter les écarts. Pas source de vérité.

## REF-COMMUNES-ML-2024 — Communes de la Métropole (contrôle croisé)

- **Producteur :** Métropole de Lyon. **Fiche :** [data.gouv](https://www.data.gouv.fr/datasets/communes-de-la-metropole-de-lyon-a-partir-de-2024) (jeu `65cfe9aa969c7ab093a48414`).
- **Téléchargé :** WFS `adr_voie_lieu.adrcomgl_2024`, GeoJSON EPSG:4326, **58 objets**.
- **Licence constatée :** Licence Ouverte 2.0 (`lov2`).

---

## Manifeste obligatoire par ressource

Les champs sont définis par le modèle Pydantic `Manifest` (`spikes/download.py` pendant le spike, déplacé dans `packages/` après le GO), qui fait foi.

Les fichiers sources ne sont jamais remplacés silencieusement : une nouvelle version = un nouveau dossier daté.

## Critères de validation d'une source

Accessible et téléchargeable · provenance vérifiable · conditions de réutilisation documentées · schéma compris · champs nécessaires présents · limites consignées · traitement reproductible · version identifiée.
