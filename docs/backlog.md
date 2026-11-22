# Backlog

Défauts constatés et travaux reportés, avec leur date de constat. Un élément sort du backlog par un commit qui le corrige ou par une décision consignée.

## Extraction du règlement (`traboule.retrieval.reglement`)

- **Titre 2.1.5 recollé** (constat du 2026-11-02) : dans les zones agricoles et naturelles, le titre « 2.1.5 - Règle applicable dans les autres STECAL (A2s1, A2s2 …) » reçoit la ligne suivante, qui commence par une minuscule (« le choix d'implantation des constructions s'effectue… ») : la règle de suite de titre (ligne courte, sans ponctuation finale, commençant par une minuscule) la prend pour la fin du titre. Le texte reste dans le chemin au lieu du passage.
- **Titre de chapitre tronqué** (constat du 2026-11-02) : une variante du titre du chapitre 1 se termine par « … ET ACTIVITE » au lieu de « … ET ACTIVITÉS ».

## Cahiers

- **Noms d'OAP non réparés** (constat du 2026-11-02) : 11 noms gardent un mot coupé par une ligature (« Christi ne », « Lavirott e », « sporti f »…), forme vue moins de 3 fois dans le vocabulaire de référence ; élargir le vocabulaire au texte réparé des cahiers demande une décision.

## Évaluation et jeu de référence (reportés le 2026-11-22)

Décision du porteur (2026-11-22) : priorité au fonctionnel (`traboule ask` en RAG, CAG et KAG léger, puis interface web minimale). Benchmarks, tirages, mesures et validations sont reportés ; seuls restent les contrôles de protection des données (aucune ligne individuelle en statut P exposée), de sécurité SQL (DuckDB en lecture seule, liste blanche) et de citation (document, page, version de la pièce). Les 15 questions de `benchmarks/datasets/gold/questions.jsonl`, toutes en `draft`, servent de **questions de démonstration** ; elles ne sont ni validées ni utilisées pour mesurer.

- **Validation du jeu de référence** : 15 questions en `draft` à valider par le porteur ; questions 16 à 30 à écrire.
- **Échantillons A et C** (ADR-0012) : relecture de la grille de confiance de zone (A) et de la lecture des cahiers (C).
- **Alias UCe3-p → UCe3p** (`configs/zones_alias.csv`, statut « probable ») : à confirmer ou non.
- **Mesures de retrieval** (dense, sparse, hybride, reranking) sur le jeu validé.
- **BSARD** et benchmark public français (tâches françaises de MTEB) : non lancés.
- **Comparaison RAGnarok-AI des stratégies** RAG, CAG et KAG léger (ADR-0005, ADR-0014), avec les coûts : temps par question, pic mémoire réel, préparation et réutilisation du cache CAG.
- **Mise à jour de `docs/cadrage-v1.md` §3.1** : y intégrer l'ADR-0014 (CAG et KAG léger), et retirer CAG et KAG des exclusions du §3.3.

## Chaîne de réponse (constats du 2026-11-22)

- **DOC-004 (zone AUEi1)** (constat du 2026-11-22) : « Quelles règles s'appliquent à une zone AUEi1 ? ». Les trois stratégies répondent par les règles de la zone U de référence (UEi1), sans rappeler le régime du chapitre AUs.co : dans l'attente de l'ouverture à l'urbanisation, seule la gestion du bâti existant est admise. RAG : passages UEi1 cités (une recherche par chapitre, AUs.co compris dans le contexte) ; CAG : chapitres AUs.co et UEi1 en entier (15,8 k tokens, 240 s), 21 passages cités, tous de UEi1 ; KAG : repli sur les premiers articles des deux chapitres. Piste : verser la règle AU → U de `zones_reglement` (citation et page) au contexte comme passage structurel, et la demander explicitement dans la consigne pour un code AU.
- **Vérification des citations** (constat du 2026-11-22) : elle contrôle que les passages cités figurent dans le contexte, pas qu'ils portent l'affirmation. En CAG, « Quel est le coefficient d'emprise au sol en zone URm1 ? » a reçu « au minimum 25 % » en citant le coefficient de pleine terre (3.2.1, p. 330), alors que le chapitre dit « L'emprise au sol des constructions n'est pas réglementée » (2.4.1 a, p. 325). Contexte de 19,5 k tokens. Piste : contrôle de recouvrement entre la réponse et les passages cités (valeurs chiffrées présentes dans le passage), abstention `CITATION_NON_VERIFIEE` sinon.
- **KAG** : rapprochement des intitulés par racine de 6 lettres, sans synonymes (« bâtiment » ne rejoint pas « construction ») ; repli sur les 6 premiers articles du chapitre pour une question générale.
- **Analyse** : lexique fermé de 7 activités (au-delà, code NAF explicite demandé) ; activité non reconnue repérée par heuristique (mots qui suivent « établissements ») ; partie réglementaire d'une question mixte isolée sur « , et ».
- **Formulation** : le minorant s'écrit sans séparateur de milliers (`Minorant.formulation`, « jusqu'à 7582 ») ; le modèle reprend parfois des numéros de passages dans son texte (renumérotés selon les citations affichées).
- **Latence** (M2, 16 Go) : 15 à 60 s par question en RAG ou KAG ; en CAG, 2 à 5 minutes pour la première question d'un chapitre, une dizaine de secondes ensuite (préfixe en cache). `ollama ps` : 6,3 Go à 16 384 tokens, 6,8 Go à 22 528, 100 % GPU.
