# Guide d'annotation du jeu de référence

Le jeu de référence est le livrable le plus important du projet : il conditionne toute mesure. Il est **écrit et validé par un humain**.

## Règles

1. **Une question = une date d'ancrage (`as_of`) + les versions de sources utilisées.** Sans ancrage, pas de réponse stable.
2. **La réponse de référence ne vient jamais du système évalué.** Pour les questions SQL, la valeur attendue vient d'une requête écrite ou relue par l'humain, exécutée sur les données figées.
3. **Comparer par résultat, pas par texte de requête.** `expected_sql` sert à reproduire `expected_result`, pas à être comparé mot à mot.
4. **Chaque preuve documentaire pointe un passage réel** (doc, page, zone, version).
5. **Statut `draft` par défaut.** Passage en `validated` uniquement après relecture humaine, avec date.
6. Fichiers : `questions.jsonl` (une question par ligne), versionné dans Git. Le champ `dataset_version` suit un versionnement sémantique.
7. **`as_of` ≥ 2015-01-01** (création de la Métropole de Lyon). Périmètre de référence : **59 communes de 2015 à 2023**, **58 communes depuis le 1er janvier 2024** (regroupement Oullins + Pierre-Bénite). Une question antérieure à 2015 est hors périmètre : la rédiger, au besoin, comme une question sans réponse (`out_of_version`).

## Répartition cible

| Catégorie | Route | Cible |
|---|---|---:|
| `factual` | `SQL` | 40 |
| `documentary` | `RAG` | 40 |
| `mixed` | `HYBRID` | 40 |
| `unanswerable` | `ABSTAIN` | 30 |

Les cibles sont indicatives. 120 questions solides valent mieux que 150 fragiles.

## Questions mixtes : le cœur du projet

Une vraie question mixte exige **les deux** : un fait obtenu par SQL/spatial **et** un passage réglementaire, reliés par une clé (code de zone, commune).

- Bon : « Combien d'établissements de la section NAF C sont dans des zones d'activités de Vénissieux, et que dit le règlement de ces zones sur l'emprise au sol ? »
- Mauvais : « Combien d'établissements à Vénissieux, et que dit le PLU-H en général ? » (deux questions juxtaposées).

## Questions sans réponse : privilégier les quasi-réponses

Les questions trivialement hors sujet (« quel temps fera-t-il ? ») ne testent rien. Viser des cas où **une information proche existe mais ne suffit pas** :

| Sous-type | Exemple de construction |
|---|---|
| `near_miss_level` | Donnée demandée à un niveau géographique non chargé (îlot, parcelle) alors que l'IRIS existe |
| `nonexistent_entity` | Code de zone plausible mais inexistant dans le zonage |
| `out_of_version` | Règle d'une version du PLU-H non indexée, ou date antérieure au stock |
| `masked_by_diffusion` | Localisation précise d'un établissement à diffusion partielle |
| `out_of_corpus` | Document existant dans le catalogue mais non ingéré |
| `future_value` | Valeur future sans méthode validée (garder peu de ces cas) |

Pour chacune, renseigner `abstention_reason` : ce qui manque **et** ce qui existe de proche. Une bonne réponse du système nomme l'information proche sans l'utiliser comme réponse.

## Pièges à intégrer volontairement

- Lyon (69123) vs arrondissements (69381–69389).
- Oullins + Pierre-Bénite : données d'avant et d'après le 1er janvier 2024.
- Établissement actif vs fermé à la date `as_of`.
- Unité légale (SIREN) vs établissement (SIRET).
- Siège vs établissement secondaire.

## Rythme

- Semaine 1 : 15 questions (≈ 4 par catégorie).
- Semaine 2 : 30 questions.
- Semaines 5–6 : extension vers la cible.

## Reproductibilité des valeurs de référence

- **`expected_result` est la référence**, pas la requête : il a été calculé sur les données figées décrites par `source_versions` (date et sha256). Une reconstruction ultérieure peut donner une autre valeur, notamment parce que le fichier INSEE de géolocalisation n'est pas archivé ; on compare alors au `expected_result` consigné.
- **Une preuve documentaire se lit par document, page, zone et chemin** (`doc_id`, `page`, `zone_code`, `note`), pas par `passage_id` : les identifiants de passage dépendent d'un découpage et changent quand le corpus est ré-ingéré.
- Toute question d'activité indique sa nomenclature dans son texte (« NAF rév. 2 »).

## Pistes de questions

- **Quasi-réponse sur la nomenclature NAF** : le stock Sirene porte un code NAF rév. 2 et un code NAF 2025, qui divergent souvent (ex. division 47 en zone UEi2 : 857 en rév. 2, 1 148 en NAF 2025). Une question qui ne précise pas la nomenclature appelle une réponse qui signale l'ambiguïté et donne la nomenclature utilisée.

## Ce qui peut être automatisé

Tout outil automatisé peut : proposer des brouillons (`status: draft`), calculer une valeur attendue par une requête que l'humain relit, valider le format contre `schema.json` (`make validate-gold`), détecter les doublons.

Seul un humain passe une question en `validated`, avec `validated_by` et `validated_at`. Aucun outil n'invente une valeur, une page ou un code de zone.
