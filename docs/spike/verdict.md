# Verdict du spike de faisabilité

Le spike (étude de faisabilité, octobre 2026) s'est conclu par un verdict **« GO avec réserves »** (2026-10-29). Le détail des mesures, des réserves et des écarts au protocole est dans le [rapport du spike](../../spikes/reports/rapport-spike.md) ; le protocole est dans le [plan du spike](plan-spike.md).

| Test | Verdict |
|---|---|
| Test 1 — Référentiel et Sirene | GO avec réserves |
| Test 2 — Jointure spatiale | GO avec réserves |
| Test 3 — Extraction des PDF | GO avec réserves |
| Test 4 — Recherche avec BGE-M3 | GO avec réserves : le bon passage pour 16 questions sur 20, mais pour 6 sur 9 seulement parmi celles qui visent l'article d'une zone, sans filtre |

Ce que le spike n'a pas démontré, selon son rapport : la fiabilité de la recherche pour une question visant l'article d'une zone sans filtre, un mécanisme d'abstention (le score seul ne suffit pas), l'extraction de qualité des cahiers communaux, l'arbitrage entre sources de coordonnées. La v1 y répond par le filtre par zone (ADR-0009), l'abstention multi-signal (ADR-0010), l'extracteur Docling pour les cahiers (ADR-0008) et l'indice de confiance de zone (ADR-0006).
