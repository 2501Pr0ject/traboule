# ADR-0003 — Sirene INSEE (stock + géolocalisation) comme source primaire

- **Statut :** accepté
- **Date :** 2026-10-27

## Contexte
Le jeu Sirene de la Métropole de Lyon est dérivé, ne contient que les établissements actifs géolocalisés et avait trois mois de retard au moment du contrôle. Le jeu géocodé par Etalab a été décommissionné en avril 2026.

## Décision
Source primaire : stock des établissements INSEE + fichier INSEE de géolocalisation pour études statistiques (mensuel, Lambert 93, qualité de géolocalisation, IRIS/QPV). Le jeu de la Métropole sert de contrôle croisé.

## Conséquences
- Historique disponible (établissements fermés, dates) → questions ancrées dans le temps.
- Code IRIS = pont vers les statistiques INSEE infracommunales.
- Les indicateurs de qualité permettent de filtrer ou signaler les géolocalisations douteuses.
- Coût : stock national volumineux à filtrer en streaming.
- Biais documenté : établissements à diffusion partielle sans géolocalisation publique.

## Critère de réexamen
Changement de format ou de diffusion par l'INSEE ; écarts inexpliqués au contrôle croisé.
