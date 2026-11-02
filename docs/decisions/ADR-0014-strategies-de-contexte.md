# ADR-0014 — RAG, CAG et KAG léger : trois stratégies de contexte comparables en v1

- **Statut :** accepté (décision du porteur, 2026-11-02)
- **Date :** 2026-11-02
- **Amende :** ADR-0001 (CAG et KAG y étaient hors périmètre)

## Contexte
L'ADR-0001 réservait la v1 au RAG hybride et plaçait CAG et KAG hors périmètre, pour éviter d'empiler des briques artificielles. Les données de la v1 ont depuis une structure explicite qui rend ces deux approches peu coûteuses et mesurables sur ce domaine :
- le règlement est découpé par partie, zone, chapitre et article ; les renvois vers la partie I sont résolus (`renvoi_vers`) ; les secteurs, alias, AU → U de référence et zones applicables sont dans le payload et dans `configs/zones_reglement.csv` ; l'index des termes définis est une table ;
- un chapitre de zone tient dans la fenêtre d'un modèle local (mesures ci-dessous).

Le porteur a décidé (2026-11-02) de construire d'abord une chaîne complète, et d'y comparer trois façons de constituer le contexte d'une réponse.

## Décision
CAG et un KAG léger entrent en v1, **comme stratégies de contexte comparables au RAG**. Les trois partagent l'analyse de la question, le routeur, la composante SQL, le générateur, la vérification des citations et les abstentions structurelles (ADR-0010) ; seule la construction du contexte diffère. Chacune rend un objet `Reponse`.
- **RAG** : recherche hybride Qdrant (dense et sparse, fusion RRF), filtrée par `zones_applicables` quand la zone est connue (question ou jointure spatiale) ; renvois `renvoi_vers` ajoutés au contexte dans la limite du budget.
- **CAG** : contexte préchargé par chapitre de zone et par OAP, avec un **cache explicite et mesuré** :
  - préparation : préchargement du préfixe (consigne et chapitre) ;
  - réutilisation : préfixe identique, seule la question est évaluée ;
  - invalidation : la clé (pièce, zone ou OAP, version de la pièce, sha256 du texte) change quand la pièce change.
  Le CAG ne s'applique que si le contexte tient dans la fenêtre du modèle ; sinon, ou sans zone ni OAP identifiée, il s'abstient (`PREUVE_INSUFFISANTE`, limite écrite en clair), sans repli silencieux sur le RAG. La taille de chaque contexte est mesurée et consignée, en tokens du LLM.
- **KAG léger** : graphe construit sur la **structure explicite** des données : établissement → zone (jointure spatiale) → chapitre → article ; renvois vers la partie I ; AU → U de référence ; secteur → zone mère ; OAP → commune ; terme défini → définition. Un parcours **déterministe** depuis les entités de la question mène aux passages, dont le texte forme le contexte. Ce n'est **ni une implémentation d'OpenSPG** ni du GraphRAG : aucun graphe n'est extrait du texte par un modèle.

## Mesures de taille des contextes (2026-11-02)
Tokens du modèle de génération (`qwen3:8b`), comptés avec le tokenizer Qwen3 ; le compte est identique à celui d'Ollama (`prompt_eval_count`) sur deux textes de contrôle (506 et 4 099 tokens). Contexte d'une zone : passages dont `zones_applicables` contient la zone (dispositions communes UPr comprises) ; contexte d'une OAP : ses passages dans les pièces indexées (doublons exclus). « Avec renvois » : plus les passages cités par `renvoi_vers` (chapitres ou articles de la partie I pour les zones ; OAP 0.1 du cahier communal de Lyon pour les OAP d'arrondissement).

| Contexte | n | min | médiane | p75 | p90 | max | ≤ 20 000 | ≤ 18 000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chapitre de zone, sans renvois | 33 | 1 802 | 12 339 | 15 217 | 16 761 | 18 035 | 33 (100 %) | 32 (97 %) |
| Chapitre de zone, avec renvois | 33 | 14 488 | 26 031 | 28 943 | 31 503 | 33 545 | 11 (33 %) | 6 (18 %) |
| OAP, sans renvois | 323 | 56 | 957 | 1 576 | 2 304 | 37 521 | 322 (99,7 %) | 322 (99,7 %) |
| OAP, avec renvois | 323 | 56 | 959 | 1 610 | 2 496 | 39 888 | 315 (97,5 %) | 315 (97,5 %) |

- Le seul contexte d'OAP au-delà de 20 k est l'OAP 0.1 (site UNESCO, 37,5 k) ; les 7 OAP d'arrondissement qui y renvoient dépassent 38 k avec ce renvoi.
- Avec renvois, 22 chapitres de zone sur 33 dépassent 20 k (les renvois portent surtout sur les chapitres 5 et 6 de la partie I, cités par presque toutes les zones).
- Préremplissage mesuré sur la machine de référence : environ 110 tokens/s (4 099 tokens en 36,7 s) ; la préparation d'un chapitre de 18 k tokens prend donc plusieurs minutes, ce que le cache doit amortir.

**Fenêtre du CAG** : 20 480 tokens. Le contexte est le chapitre de zone (ou l'OAP) **sans** les passages de la partie I ; les renvois y figurent par leur titre seulement. L'OAP 0.1 et les renvois vers elle dépassent la fenêtre : abstention du CAG avec la limite en clair.

## Options considérées
| Option | Pour | Contre |
|---|---|---|
| Trois stratégies comparables, même chaîne (retenue) | Comparaison à composants égaux ; exploite la structure déjà extraite | Trois constructions de contexte à maintenir |
| RAG seul (ADR-0001) | Plus simple | Ne dit pas si la structure explicite ou le préchargement font mieux sur ce domaine |
| GraphRAG ou KAG complet (OpenSPG) | Approches de référence | Graphe extrait par un modèle, coûteux et non vérifiable ; hors de proportion avec le corpus |

## Conséquences
- Le cache CAG dépend du serveur de modèle : Ollama ne garde qu'un préfixe par modèle chargé (cache effectif de taille 1). Un cache persistant (sauvegarde des états de `llama-server`) est noté au backlog, non retenu pour la première chaîne.
- Le KAG ne crée aucun nœud individuel d'établissement : l'arête établissement → zone reste la table `etablissements_zones`, interrogée en agrégats seulement.
- La comparaison des trois stratégies passe par RAGnarok-AI (ADR-0005) quand les questions du jeu de référence seront validées ; la première chaîne ne mesure pas la qualité.
- À mettre à jour après acceptation : périmètre du cadrage (§3.1) et consignes locales de travail.

## Critère de réexamen
Si, sur le jeu de référence validé, une stratégie est dominée par une autre sur toutes les métriques (qualité, abstention, coût), elle est retirée de la v1.
