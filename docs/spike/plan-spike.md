# Spike de faisabilité — plan et critères GO / NO-GO

**Durée cible :** 2 à 3 jours de travail effectif. Au-delà, arrêter et rédiger le rapport avec ce qui est connu.
**Code :** scripts jetables dans `spikes/`, jamais dans `packages/`.
**Sortie :** `spikes/reports/rapport-spike.md` (modèle en bas de page).

Chaque test a un critère mesurable **fixé avant** de l'exécuter. Ne pas assouplir un critère après coup sans le consigner.

---

## Test 0 — Préparation (≈ 1 h)

- Résoudre les URLs `A_CONFIRMER` de `configs/sources.yaml` pour SRC-001a, SRC-001b, SRC-002, SRC-004a/b/c via l'API data.gouv.fr ou la page INSEE.
- Résoudre l'URL de SRC-003 (catalogue des documents du PLU-H) et le télécharger complètement.
- Télécharger dans `data/raw/<source_id>/<AAAA-MM-JJ>/` avec manifeste (modèle `Manifest` de `spikes/download.py`), puis passer le dossier en lecture seule.
- **SRC-005 (GPU) : investigation seulement**, sans téléchargement en masse. Consigner dans le registre : mode d'accès (téléchargement, API Carto module GPU…), licence, identifiant et date de la version opposable du PLU-H.
- **Sortie :** registre mis à jour (v0.3), manifestes présents, fiche SRC-005 renseignée.

## Test 1 — Référentiel géographique et rattachement Sirene

**Question :** peut-on rattacher les établissements de la Métropole au bon niveau géographique sans perte inexpliquée ?

Étapes :
1. Depuis l'appartenance géographique COG 2026, extraire les communes de l'EPCI 200046977. Attendu : 58.
2. Construire `ref_arrondissements` (69381–69389, parent 69123).
3. Construire la correspondance 59 → 58 (regroupement Oullins + Pierre-Bénite) depuis la table de passage. Lire le code et la date d'effet dans les données, ne pas les supposer.
4. Filtrer le stock Sirene en streaming (DuckDB) sur ces codes ; écrire `data/interim/sirene_ml.parquet`.
5. Joindre le fichier de géolocalisation sur SIRET.
6. Mesurer :
   - nb d'établissements (actifs / fermés) par commune et par arrondissement ;
   - niveau géographique effectivement utilisé par Sirene pour Lyon (commune ou arrondissement) ;
   - taux de jointure stock ↔ géolocalisation ;
   - part des actifs **sans** coordonnées, ventilée par `statutDiffusionEtablissement` ;
   - distribution de la qualité de géolocalisation.
7. Contrôle croisé : comparer les actifs géolocalisés avec SRC-007 (jeu Métropole) par commune.

**GO si :**
- 58 communes + 9 arrondissements correctement modélisés, sans double comptage ;
- tout établissement filtré est rattaché à une commune du COG 2026 (ou à une correspondance documentée) ;
- les écarts avec SRC-007 sont expliqués (date, périmètre, géocodage), pas seulement constatés.

**Si échec :** limiter les analyses au niveau géographique fiable et documenter.

## Test 2 — Jointure spatiale établissements ↔ zonage PLU-H

**Question :** la fonctionnalité signature est-elle techniquement fiable ?

Étapes :
1. Charger le zonage dans DuckDB spatial ; lire le CRS déclaré.
2. Valider les géométries (`ST_IsValid`), mesurer chevauchements et zones vides.
3. Reprojeter dans un CRS commun (EPSG:2154) avec `always_xy := true`.
4. Sur **un seul arrondissement de Lyon d'abord** (ex. 69387), puis toute la Métropole : `ST_Contains(zone, point)`.
5. Mesurer : % d'établissements géolocalisés sans zone, % dans plusieurs zones, temps de calcul, pic mémoire.
6. Vérifier manuellement 10 établissements tirés au hasard (zone attendue vs zone trouvée, sur une carte).
7. Lister les codes de zone et vérifier qu'ils correspondent à des chapitres du règlement écrit.

**GO si :**
- ≥ 98 % des établissements géolocalisés tombent dans exactement une zone (le reste expliqué : bord, voirie, hors territoire) ;
- 10/10 contrôles manuels cohérents ;
- les codes de zone se relient au règlement sans table de correspondance manuelle de plus de quelques dizaines de lignes.

## Test 3 — Extraction des PDF du PLU-H

**Question :** le règlement est-il exploitable sans correction manuelle page par page ?

Corpus de test : **3 documents** — un extrait du règlement écrit (zones économiques), une OAP, un extrait du rapport de présentation.

Étapes :
1. Extraire avec PyMuPDF puis avec Docling.
2. Pour chaque document, sur 10 pages échantillonnées, noter :
   - texte lisible (oui/non), ordre de lecture correct (oui/non) ;
   - titres d'articles et de zones récupérés (oui/non) ;
   - tableaux exploitables (oui/partiel/non) ;
   - en-têtes/pieds de page parasites.
3. Mesurer temps d'extraction et pic mémoire. Le premier import de Docling dans un environnement neuf est lent (59 s mesurées le 2026-10-28, contre 4 s ensuite, docling 2.143.1) : faire un import de chauffe, consigner le temps d'import à part et ne chronométrer que l'extraction.

**GO si :**
- ≥ 90 % des pages du règlement avec texte lisible et ordre correct ;
- la structure zone → article est reconstructible automatiquement ;
- au moins un extracteur traite les tableaux du règlement de façon exploitable.

**Si échec :** réduire le corpus aux zones les plus propres, ou passer au règlement publié sur le GPU s'il est plus structuré.

## Test 4 — BGE-M3 sur le M2

**Question :** l'encodeur tient-il dans les contraintes matérielles ?

Corpus pilote **fixé à l'avance** : les passages issus du test 3 (consigner leur nombre et leur taille totale en tokens).

Étapes :
1. Charger BGE-M3 (dense + sparse ; multivecteur seulement mesuré pour la taille, pas indexé).
2. Encoder le corpus pilote ; mesurer débit (passages/min), pic mémoire, device (`mps` / CPU).
3. Indexer dense + sparse dans Qdrant local ; mesurer taille disque et latence de recherche sur 20 requêtes françaises écrites à la main.
4. Estimer la taille de stockage multivecteur (tokens × 1024 × 4 octets) pour le corpus complet prévu.

**GO si :**
- le corpus pilote s'indexe en < 1 h et l'extrapolation au corpus complet reste < 4 h ;
- pic mémoire compatible avec un usage normal de la machine (< 10 Go) ;
- sur les 20 requêtes, le bon passage apparaît dans le top-10 pour une majorité nette (mesure qualitative, pas un benchmark).

**Si échec :** essayer un encodeur plus léger (multilingual-e5-base ou équivalent) et le consigner dans un ADR.

---

## Modèle de rapport (`spikes/reports/rapport-spike.md`)

```markdown
# Rapport de spike — AAAA-MM-JJ

## Verdict global : GO / GO avec réserves / NO-GO

## Environnement
Machine, OS, Python, versions DuckDB / PyMuPDF / Docling / FlagEmbedding / qdrant-client, device.

## Sources téléchargées
| source_id | fichier | date | sha256 (8 car.) | taille |

## Test 1 — Référentiel et Sirene : GO / NO-GO
Mesures, écarts, décisions.

## Test 2 — Jointure spatiale : GO / NO-GO
Mesures, contrôles manuels, décisions.

## Test 3 — PDF : GO / NO-GO
Grille d'évaluation, extracteur retenu.

## Test 4 — BGE-M3 : GO / NO-GO
Débit, mémoire, taille, latence.

## Surprises et risques
## Décisions à consigner en ADR
## Impact sur le planning
```
