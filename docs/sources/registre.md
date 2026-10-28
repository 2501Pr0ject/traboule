# Registre des sources

**Version :** 0.2
**Date de contrôle :** 27 octobre 2026
**Périmètre :** Métropole de Lyon (58 communes au 1er janvier 2024, EPCI 200046977)
**Version machine :** `configs/sources.yaml`

## Changements depuis la v0.1

- SRC-001 : passage au **stock Sirene INSEE + fichier de géolocalisation INSEE** (source primaire). Le jeu Sirene de la Métropole devient SRC-007 (contrôle croisé).
- SRC-004 : ajout de la **table de correspondance 59 → 58 communes** (regroupement Oullins + Pierre-Bénite au 1er janvier 2024).
- Nouvelle SRC-005 : **Géoportail de l'Urbanisme** comme référence de version opposable du PLU-H.
- BPE renumérotée SRC-006, toujours optionnelle.
- Le jeu Sirene géocodé par Etalab est **exclu** : décommissionné en avril 2026 au profit de celui de l'INSEE.

## Ordre de priorité

1. SRC-001 — Sirene INSEE (stock + géolocalisation)
2. SRC-002 — Zonage du PLU-H
3. SRC-004 — COG 2026 + appartenance + table de passage
4. SRC-005 — Géoportail de l'Urbanisme (version opposable, règlement écrit)
5. SRC-003 — Catalogue des documents du PLU-H
6. SRC-007 — Sirene Métropole (contrôle croisé)
7. SRC-006 — BPE (seulement si un cas d'usage la justifie)

---

## SRC-001 — Sirene INSEE : stock des établissements + géolocalisation

- **Producteur :** INSEE (alimente directement data.gouv.fr).
- **Ressources :**
  - Stock des établissements (`StockEtablissement`) — préférer la version Parquet si publiée, sinon CSV.
  - Fichier « Géolocalisation des établissements du répertoire Sirene pour les études statistiques » (data.gouv, id `61d5e2d372a52d9f9411ff88`), publié en fin de mois : SIRET, X/Y Lambert 93, code commune, variables de qualité de géolocalisation, IRIS, QPV, ZUS, QVA.
- **Licence :** à consigner depuis la fiche (Licence Ouverte attendue) + obligations légales Sirene sur les données personnelles.
- **Utilisation :** établissements actifs **et fermés** (historique, dates de création/fermeture), NAF, jointure spatiale, pont IRIS vers les statistiques INSEE infracommunales.
- **Volume :** stock national de plusieurs Go → filtrage en streaming avec DuckDB sur les codes commune de la Métropole, écriture en Parquet.

**Contrôles :**
1. Champs : `siret`, `codeCommuneEtablissement`, `activitePrincipaleEtablissement`, `etatAdministratifEtablissement`, `dateCreationEtablissement`, `statutDiffusionEtablissement`, coordonnées (noms exacts à confirmer sur la documentation des variables).
2. Niveau géographique du code commune pour Lyon : commune 69123 ou arrondissements 69381–69389 ?
3. Millésime géographique des codes commune et IRIS du fichier de géolocalisation.
4. Part des établissements actifs sans géolocalisation, ventilée par statut de diffusion.
5. Distribution des indicateurs de qualité de géolocalisation.
6. Cohérence stock ↔ fichier de géolocalisation (taux de jointure sur SIRET).

**Limites connues :**
- Environ 11 % des établissements font l'objet d'une opposition à la diffusion ; leur adresse précise et leur géolocalisation sont masquées. Comptages spatiaux structurellement sous-estimés, surtout pour les entrepreneurs individuels.
- Une coordonnée d'établissement est une adresse, pas l'emprise réelle de l'activité.

## SRC-002 — Zonage du PLU-H

- **Producteur :** Métropole de Lyon. **Portail :** data.gouv.fr / data.grandlyon.com.
- **Licence annoncée :** Licence Ouverte 2.0.
- **Formats :** Shapefile, GeoJSON (~14,8 Mo), CSV. **Fiche mise à jour :** 13 octobre 2026.
- **Utilisation :** jointure spatiale, attributs de zone, lien vers les règles écrites.

**Contrôles :**
1. CRS déclaré (EPSG:4326 ou 2154 ?) et cohérence avec les coordonnées Sirene.
2. Validité des géométries (`ST_IsValid`), chevauchements, trous.
3. Champ du code de zone et correspondance avec les intitulés du règlement écrit.
4. Version du PLU-H représentée (procédure de modification / mise à jour) et comparaison avec le GPU (SRC-005).
5. Couverture : la somme des zones couvre-t-elle tout le territoire des 58 communes ?

**Limite connue :** le zonage ne suffit pas à déterminer toutes les règles applicables (prescriptions surfaciques/linéaires, servitudes, OAP).

## SRC-003 — Catalogue des documents du PLU-H

- **Producteur :** Métropole de Lyon. **Licence du jeu d'accès :** Licence Ouverte 2.0.
- **Formats :** Shapefile, GeoJSON (~1,2 Mo), CSV. **Fiche mise à jour :** 26 octobre 2026.
- **Utilisation :** découverte des documents par commune.

**Contrôles :**
1. Tester les liens ; catégoriser les documents (règlement, OAP, rapport de présentation, plans).
2. Conditions de réutilisation **des documents cibles** (la licence du catalogue ne les couvre pas automatiquement).
3. Référence au découpage à **59 communes** (Oullins et Pierre-Bénite séparés) : à vérifier.

**Limite connue :** c'est un catalogue, pas le corpus.

## SRC-004 — Référentiel géographique INSEE

- **COG 2026** (communes, arrondissements municipaux) — millésime au 1er janvier 2026.
- **Table d'appartenance géographique des communes** (pour filtrer sur l'EPCI 200046977 plutôt que coder la liste en dur).
- **Table de passage entre millésimes** (pour la correspondance 59 → 58 communes).
- **Licence :** à consigner depuis la page INSEE.

**Contrôles :**
1. 58 communes pour l'EPCI 200046977 au COG 2026 ; Lyon (69123) + 9 arrondissements (69381–69389) dans une table distincte.
2. Code et date d'effet de la commune issue du regroupement Oullins + Pierre-Bénite (à lire dans le COG, ne pas supposer).
3. Table de correspondance `code_2023 → code_2026` documentée et testée.

**Règle de modélisation :** les arrondissements sont des subdivisions de Lyon, jamais des communes supplémentaires.

## SRC-005 — Géoportail de l'Urbanisme (GPU)

- **Producteur :** État (IGN / ministère), alimenté par la Métropole au standard CNIG.
- **Pourquoi :** depuis le 1er janvier 2023, la publication sur le GPU conditionne le caractère exécutoire d'un document d'urbanisme. C'est la référence de la **version opposable**.
- **Utilisation :** identifier la version du PLU-H en vigueur, récupérer le règlement écrit et le zonage au standard CNIG, contrôler la cohérence avec SRC-002.
- **Accès :** téléchargement du document sur le portail ou API Carto (module GPU) — à confirmer.
- **Licence :** à consigner.

**Contrôles :**
1. Identifiant et date de la version publiée du PLU-H de la Métropole.
2. Concordance des codes de zone entre GPU et data.grandlyon.
3. Disponibilité du règlement écrit (PDF) et de sa structure par zone.

**Contexte :** le PLU-H est en vigueur depuis juin 2019 et fait l'objet de procédures successives (modifications, mises à jour — par exemple mise à jour n° 9 arrêtée en décembre 2024). Chaque question du jeu de référence porte la version utilisée.

## SRC-006 — Base permanente des équipements (optionnelle)

Candidate uniquement si un cas d'usage la justifie. Contrôles : licence, millésime géographique, niveaux disponibles, valeur ajoutée mesurable.

## SRC-007 — Sirene de la Métropole de Lyon (contrôle croisé)

- **Producteur :** Métropole de Lyon à partir de Sirene. **Licence :** Licence Ouverte 2.0. **CSV ~94,7 Mo**, mise à jour observée au 4 août 2026.
- **Limites :** ne contient que les établissements **actifs** géolocalisés ; retard de mise à jour ; géocodage propre à la Métropole.
- **Utilisation :** comparer les comptages et les coordonnées avec SRC-001 ; documenter les écarts. Pas source de vérité.

---

## Manifeste obligatoire par ressource

Les champs sont définis par le modèle Pydantic `Manifest` (`spikes/download.py` pendant le spike, déplacé dans `packages/` après le GO), qui fait foi.

Les fichiers sources ne sont jamais remplacés silencieusement : une nouvelle version = un nouveau dossier daté.

## Critères de validation d'une source

Accessible et téléchargeable · provenance vérifiable · conditions de réutilisation documentées · schéma compris · champs nécessaires présents · limites consignées · traitement reproductible · version identifiée.
