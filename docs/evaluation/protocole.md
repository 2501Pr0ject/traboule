# Protocole d'évaluation et de revue humaine

**Version :** 0.1 (2026-11-01), écrite **avant tout tirage** ([ADR-0012](../decisions/ADR-0012-tirages-protocole-revue.md)).
**Statut :** validé par le porteur le 2026-11-01 (graine de l'échantillon A, limite de 10 remplacements par strate, bâtiment à cheval = confirmé, règles de l'adresse sans numéro et de l'écart de version).

Toute règle ajoutée après un premier résultat est **datée et marquée** « ajoutée après tirage », avec son effet possible sur le verdict.

## 1. Règles communes

### Tirages

- Ordre de tirage : `md5(identifiant || graine)` croissant, calculé en SQL (`md5(siret || '20261101')`). La fonction `hash()` de DuckDB n'est jamais utilisée (stabilité non garantie d'une version à l'autre).
- **Une graine par échantillon**, consignée dans ce document avant le tirage. Deux échantillons n'ont jamais la même graine.
- La population, la taille, les règles de statut, de remplacement et de fin, et le critère sont écrits ici avant le tirage.
- Le tirage porte sur une table identifiée : fichier, commande qui l'a produite, tag ou commit du code.
- **Note du 2026-11-01 (ajoutée après tirage)** : la graine `20261101` de l'échantillon A a été réutilisée par erreur pour tirer les 3 points de la preuve GPU de `UCe3-p` (`configs/preuves_gpu/UCe3-p.json`). Sans effet sur l'échantillon A : les populations sont disjointes (objets de zonage d'un côté, établissements de l'autre). Tout tirage futur a sa graine propre ; l'enregistrement d'une preuve GPU exige désormais une graine explicite (`--graine`).

### Grilles de revue

- Une grille est un fichier CSV **local** (`data/interim/controles/`, jamais versionné) dès qu'elle contient un SIRET ou une adresse. Seuls des agrégats sont publiés.
- Colonnes obligatoires :
  - `methode` : `humain`, `pré-lecture automatisée` ou `vérification automatisée`, ligne par ligne ;
  - `relu_par_humain` : `oui` / `non`, **modifiée par le porteur lui-même** dans le fichier.
- **Seules les lignes relues (`relu_par_humain = oui`) comptent** pour un critère. Une relecture déclarée sans modification du fichier ne compte pas.
- Une revue plus courte mais réellement faite vaut mieux qu'une revue longue déléguée.

## 2. Échantillon A — contrôle de l'indice de confiance de zone

**Objet :** vérifier que la zone attribuée par la jointure (`traboule.geo.jointure`) est celle du bâtiment à l'adresse déclarée, par niveau de confiance (ADR-0006).

### Population et tirage

- Table : `data/interim/etablissements_zones.parquet` produite par `uv run python -m traboule.geo.jointure` ; le tag ou le commit du code est noté dans la grille.
- Population : établissements actifs (`etat = 'A'`), catégorie `une_zone` (hors secteur sauvegardé, aucune zone et multi-zones), répartis en trois strates par `confiance` (haute, moyenne, faible).
- **Graine : `20261101`** (une seule pour l'échantillon ; les strates sont disjointes).
- Taille : **10 établissements par strate**, soit 30. Dans chaque strate, les 10 premiers rangs de l'ordre de tirage.
- L'adresse déclarée est lue dans le stock SRC-001a (champs d'adresse de l'établissement) et reste dans la grille locale.
- Commande : `uv run python -m traboule.evaluation.tirage --graine 20261101`, qui écrit la grille, les remplacements masqués et les métadonnées du tirage dans `data/interim/controles/` et refuse de réécrire une grille existante ; un test vérifie en local qu'elle redonne exactement la grille tirée.

### Méthode de vérification (humaine)

Pour chaque établissement :

1. ouvrir la visionneuse du Géoportail de l'Urbanisme (lien `https://www.geoportail-urbanisme.gouv.fr/map/#lon=…&lat=…&zoom=19`, point de la géolocalisation) ;
2. y rechercher **l'adresse déclarée** et repérer le bâtiment situé à cette adresse ; si l'adresse n'a pas de numéro de voie, repérer la voie ;
3. lire la ou les zones du PLU-H sous ce bâtiment (ou le long de cette voie) ;
4. comparer à `zone_jointure`.

La grille est remplie par le porteur (`methode = humain`). Aucun pré-remplissage automatisé des colonnes de statut pour cet échantillon : seules les colonnes de tirage (strate, rang, SIRET, adresse, lien, zone de la jointure) sont préparées automatiquement.

### Statuts

| Statut | Règle |
|---|---|
| **confirmé** | le bâtiment à l'adresse déclarée est entièrement dans `zone_jointure` ; ou il est à cheval sur plusieurs zones dont `zone_jointure` (colonne `a_cheval = oui`, rapportée à part) ; adresse sans numéro : la voie est entièrement dans `zone_jointure` |
| **infirmé** | le bâtiment est entièrement dans une autre zone ; ou il est à cheval sur plusieurs zones dont aucune n'est `zone_jointure` ; adresse sans numéro : la voie traverse une ou plusieurs zones dont aucune n'est `zone_jointure` |
| **indéterminable** | adresse sans numéro dont la voie traverse plusieurs zones dont `zone_jointure` ; adresse introuvable dans la visionneuse ; aucun bâtiment à l'adresse, ou plusieurs bâtiments sans moyen de désigner le bon |
| **écart de version** | le code de zone lu sur le GPU diffère du code du zonage SRC-002 au même endroit (contrôle croisé de version) ; **exclu du calcul du critère**, rapporté à part |

- Cause d'un statut infirmé, dans une liste fermée : `geocodage` (point de la géolocalisation sur un autre bâtiment que celui de l'adresse), `limite` (bâtiment ou point sur une limite de zone), `jointure` (défaut de la jointure elle-même).
- La méthode porte sur le bâtiment **à l'adresse déclarée** : une adresse de domiciliation dont l'activité s'exerce ailleurs est jugée sur le bâtiment de l'adresse.

### Remplacement et fin

- Un cas **indéterminable** ou en **écart de version** est **remplacé par le rang suivant de la même strate** dans l'ordre de tirage.
- **Au plus 10 remplacements par strate**, tous motifs confondus. Au-delà, la strate est déclarée « non concluante », avec le nombre de cas déterminés.
- Fin : **10 cas déterminés par strate**, relus par le porteur.

### Critère et rapport

- **Critère : « haute » confirmée sur au moins 9 cas sur 10.**
- « moyenne » et « faible » sont **rapportées sans critère** : nombres de confirmés, d'infirmés et de causes.
- Le rapport donne pour chaque strate : confirmés (dont à cheval et dont adresses sans numéro), infirmés par cause, indéterminables, écarts de version et remplacements. Aucun SIRET ni aucune adresse.
- Échec du critère : réexamen de l'ADR-0006 (seuils de distance, place de la qualité `21`) avant toute réponse qui expose la confiance « haute ».

## 3. Échantillon B — calibration du juge automatique (LLM-as-judge)

Structure seulement ; taille, population, graine et critère fixés **avant la semaine 4** (cadrage §6), par une nouvelle version de ce document.

- Sous-ensemble du jeu de référence annoté à la main par le porteur ; le juge n'est jamais considéré comme vérité.
- Mesure prévue : accord juge / humain par critère (fidélité, citations, abstention).
- **Graine propre**, consignée avant son tirage et différente de celle de l'échantillon A (`20261101`).

## 4. Jeu de référence

- Pas de tirage : chaque question est écrite ou relue par le porteur, qui seul la passe en `validated` (`validated_by`, `validated_at`) ; voir le [guide d'annotation](../../benchmarks/datasets/gold/guide-annotation.md).
- `expected_result` est la référence ; une preuve documentaire se lit par document, page, zone et chemin.

## 5. Interface avec RAGnarok-AI

À compléter en semaine 4 ([ADR-0005](../decisions/ADR-0005-evaluation-ragnarok.md)) : format d'export des prédictions, métriques de routage, d'exécution SQL et d'abstention.
