# ADR-0009 — Représentation des passages : en-tête contextuel, payload, filtre par zone

- **Statut :** proposé
- **Date :** 2026-10-29

## Contexte
Test 4 (`spikes/reports/rapport-spike.md`) : 16/20 requêtes réussies en hybride sans filtre, mais **6/9 seulement pour les requêtes qui ciblent l'article d'une zone**. Les trois échecs (Q02, Q04, Q06) ont la même cause : **le nom de zone est absent du texte des passages** (il n'est que dans les métadonnées) et **les articles sont identiques d'une zone à l'autre** (44 groupes de textes identiques entre zones) ; seul le préambule de zone nomme la zone, d'où sa remontée à la place de l'article. Indication automatisée, non jugée : en hybride filtré par zone, l'article attendu remonte au rang 2 ou 3 pour ces trois requêtes.

Autres constats : Q15 (l'OAP 5 « La Saulaie » devant l'OAP 7 « ZA de la Saulaie ») et Q16 (une OAP de Pierre-Bénite remontée pour une question sur Oullins) appellent la commune et le nom d'OAP en métadonnées ; chaque pièce porte sa propre version, qu'une citation doit donner (conventions §6).

## Décision
- **En-tête contextuel préfixé au texte avant encodage** (pas au texte cité) : zone, libellé de zone, chapitre, article ; pour les cahiers : commune, partie, nom d'OAP.
- **Payload** de chaque passage : `doc_id`, `source_id`, `zone`, libellé de zone, `commune` (cahiers, OAP), nom d'OAP, `version_piece`, `version_gpu`, `page_debut`, `page_fin`, `chemin`, extracteur.
- **Filtre de payload par zone** quand la zone est connue (question ou jointure spatiale) ; sans zone connue, recherche non filtrée.
- **Préambules de zone** : passages de contexte, pas de règle (signalés comme tels dans le payload).
- Articles identiques d'une zone à l'autre : conservés, un passage par zone.
- L'en-tête et le filtre sont **mesurés séparément puis ensemble** sur les requêtes ciblant une zone.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| En-tête + payload + filtre (retenue) | Corrige la cause mesurée ; le filtre exploite la jointure spatiale | Encodage à refaire si l'en-tête change |
| Filtre seul | Simple ; gain indiqué au test 4 | Inutile sans zone connue |
| Fusion des articles identiques (une entrée, plusieurs zones) | Moins de doublons | Complique la citation par zone ; non mesuré |

## Conséquences
- Le jeu de référence doit contenir des questions ciblant une zone avec et sans zone explicite.
- Le routeur HYBRID transmet la zone issue de la jointure spatiale au retrieval.

## Critère de réexamen
Si l'en-tête dégrade les requêtes sans zone, ou si le filtre seul suffit à porter les requêtes ciblant une zone au niveau des autres.
