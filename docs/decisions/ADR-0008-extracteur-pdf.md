# ADR-0008 — Extracteur PDF : PyMuPDF pour le règlement, Docling pour les tableaux et les cahiers

- **Statut :** accepté
- **Date :** 2026-10-29

## Contexte
Test 3 (`spikes/reports/rapport-spike.md`) :
- **règlement écrit** (une colonne) : texte lisible et dans l'ordre sur 10/10 pages avec PyMuPDF comme avec Docling ; PyMuPDF 10,7 pages/s, Docling 2,4 pages/s ;
- **cahiers communaux** (colonnes, encadrés, cartes) : `PyMuPDF get_text(sort=True)` entrelace les colonnes ligne à ligne (0/10 et 2/10 pages correctes) ; Docling restitue l'ordre (7/10 et 5/10) mais **duplique massivement le texte** sur les pages de graphiques et décode mal certaines puces ;
- **tableaux du règlement** (5 pages tirées sur les 43 qui en contiennent) : mêmes 8 tableaux détectés ; Docling restitue en-têtes et cellules fusionnées, PyMuPDF colle les mots et crée des colonnes fantômes ;
- modèles Docling : 0,53 Go ; mémoire < 1,4 Go ; OCR inutile (PDF natifs).

## Décision
- **PyMuPDF** pour le texte du règlement écrit (repérage des titres zone / chapitre / article sur son texte).
- **Docling** pour les cahiers communaux (dont les OAP) et pour toute page où PyMuPDF détecte un tableau.
- **Combinaison dans un même document** : la structure (zone, chapitre, article) reste celle tirée de PyMuPDF ; seul le contenu des tableaux est remplacé par la sortie Docling ; chaque passage indique son extracteur.
- Nettoyage systématique des sorties Docling : suppression des lignes dupliquées à l'identique sur une même page, normalisation des puces.
- Pages graphiques (plans, cartes) : hors périmètre sans OCR ; règle de détection à revoir (deux cartes manquées au seuil de 50 % d'image).

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Mixte (retenue) | Meilleur résultat mesuré par type de page ; règlement rapide | Deux chaînes à maintenir |
| Docling partout | Une seule chaîne ; ordre et tableaux corrects | Plus lent (règlement ≈ 6 min, cahiers ≈ 1 à 2,5 h estimés) ; duplications à nettoyer |
| PyMuPDF partout | Rapide | Inutilisable sur les cahiers ; tableaux complexes dégradés |

## Conséquences
- Chaque passage porte son extracteur dans ses métadonnées.
- Le corpus du test 4 suit déjà cette règle (PyMuPDF pour le règlement, Docling pour les cahiers).

## Critère de réexamen
Si le nettoyage des sorties Docling ne suffit pas sur un échantillon de cahiers relu par un humain, ou si une version de PyMuPDF restitue l'ordre des colonnes.
