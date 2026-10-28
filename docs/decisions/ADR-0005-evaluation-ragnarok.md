# ADR-0005 — RAGnarok-AI comme framework d'évaluation

- **Statut :** accepté
- **Date :** 2026-10-27

## Contexte
RAGnarok-AI (framework d'évaluation RAG local-first, publié sur GitHub/PyPI) couvre déjà les métriques de retrieval, l'évaluation locale via Ollama et le checkpointing. Il ne couvre probablement pas l'évaluation d'un routeur ni l'exactitude d'exécution SQL.

## Décision
Pas de nouveau harnais. L'évaluation passe par RAGnarok-AI ; les manques sont comblés par des **extensions dans RAGnarok-AI lui-même** :
- exactitude du routage (matrice de confusion, précision/rappel par route) ;
- exactitude d'exécution SQL (comparaison des résultats, pas du texte de la requête ; tolérance d'ordre et de types documentée) ;
- qualité de l'abstention.

## Conséquences
- Cohérence de portfolio : l'outil d'évaluation est utilisé sur un vrai système.
- Les extensions suivent le cycle de RAGnarok (tests, version, changelog), pas celui de Traboule.
- Traboule exporte ses prédictions dans un format que RAGnarok lit ; l'interface est documentée dans `docs/evaluation/`.

## Critère de réexamen
Si une extension exige de déformer l'architecture de RAGnarok, l'implémenter d'abord comme plugin externe.
