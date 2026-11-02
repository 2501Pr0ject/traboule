# ADR-0009 — Représentation des passages : en-tête contextuel, payload, filtre par zone

- **Statut :** accepté
- **Date :** 2026-10-29

## Contexte
Test 4 (`spikes/reports/rapport-spike.md`) : 16/20 requêtes réussies en hybride sans filtre, mais **6/9 seulement pour les requêtes qui ciblent l'article d'une zone**. Les trois échecs (Q02, Q04, Q06) ont la même cause : **le nom de zone est absent du texte des passages** (il n'est que dans les métadonnées) et **les articles sont identiques d'une zone à l'autre** (44 groupes de textes identiques entre zones) ; seul le préambule de zone nomme la zone, d'où sa remontée à la place de l'article. Indication automatisée, non jugée : en hybride filtré par zone, l'article attendu remonte au rang 2 ou 3 pour ces trois requêtes.

Autres constats : Q15 (l'OAP 5 « La Saulaie » devant l'OAP 7 « ZA de la Saulaie ») et Q16 (une OAP de Pierre-Bénite remontée pour une question sur Oullins) appellent la commune et le nom d'OAP en métadonnées ; chaque pièce porte sa propre version, qu'une citation doit donner (conventions §6).

## Décision
- **En-tête contextuel préfixé au texte avant encodage** (pas au texte cité) : zone, libellé de zone, chapitre, article ; pour les cahiers : commune, partie, nom d'OAP.
- **Payload** de chaque passage : `doc_id`, `source_id`, `zone`, libellé de zone, nom d'OAP, `version_piece`, `version_gpu`, `page_debut`, `page_fin`, `chemin`, extracteur ; pour les cahiers communaux, établis sur le découpage à 59 communes : **secteur PLU-H** (01–67), **code commune COG 2026** et **commune historique** (ex. secteur 46 : 69152 Pierre-Bénite, rattaché à 69149 Oullins-Pierre-Bénite au COG 2026).
- **Filtre de payload par zone** quand la zone est connue (question ou jointure spatiale) ; sans zone connue, recherche non filtrée.
- **Préambules de zone** : signalés comme tels dans le payload, mais **conservés dans la recherche** (Q08 a été réussie grâce au préambule de la zone AU).
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

## Amendement du 2026-11-01 : secteurs de zone

Le règlement est organisé par zone mère : un secteur (ex. `UCe1a`, `URm1c`, `A2sj`) n'a pas de chapitre propre. La correspondance code de zone → chapitre (`configs/zones_reglement.csv`, généré par `traboule.geo.zones_reglement`) distingue le **secteur** (code complet) de la **zone mère** et du chapitre, et indique si le code de secteur est cité dans le texte du chapitre applicable (`dispositions_secteur`, avec les pages).

- Une réponse sur un secteur **cite le chapitre de la zone mère** et **vérifie les dispositions propres au secteur** aux pages indiquées ; si le secteur n'est pas cité dans le chapitre (`dispositions_secteur = non`), la réponse le dit.
- Le **code de secteur figure dans l'en-tête contextuel** des passages concernés, en plus de la zone mère.
- **Correspondance de code par alias** (`configs/zones_alias.csv`, table fermée, colonne `alias_statut` de la correspondance) : une disposition propre au secteur du règlement citée pour un objet du code de zonage correspondant (ex. disposition de `UCe3p` pour un objet `UCe3-p`) est signalée « correspondance de code probable » tant que le statut n'est pas « confirmé ». Seul le porteur passe un alias en « confirmé ». Aucun code n'est rapproché hors de cette table.

## Amendement du 2026-11-02 : qualité du texte et version des passages de cahiers

Constat sur les 76 cahiers extraits : des ligatures restent mal décodées après réparation (`traboule.retrieval.ligatures`) : caractères « � » laissés par Docling et mots coupés par une espace (« stati on »). Un même cahier peut aussi porter plusieurs procédures dans ses en-têtes (ex. SECT09 : une page en « Modification n°3 » dans une pièce en « Modification n°4 »).

- **Payload des passages de cahiers** : champ `qualite_texte` (`illisibles` : caractères « � » restants ; `fragments` : mots coupés restants), calculé après réparation. Il permet de mesurer et, si besoin, de filtrer ou signaler les passages dégradés ; il ne modifie pas le texte cité.
- **`version_piece`** : lue dans l'en-tête de chaque page (page précédente la plus proche si la page n'en porte pas). Un passage est **coupé à chaque changement de version** : il ne couvre jamais des pages de versions différentes et porte une seule version, celle de ses pages.
- **Exclusions de l'index** : `configs/index.yaml` liste les ressources exclues, chacune avec son motif et sa décision (ex. `cahier_communal_sect64`, pièce mal identifiée).
