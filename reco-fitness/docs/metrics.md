# Metriques d'evaluation -- moteur de recommandations fitness

> Reproduction : `python scripts/eval_metrics.py` (seed=42).
> Catalogue : 70 exercices, 120 programmes generes.

## Statut des cibles PRD

| Metrique | Valeur | Cible | Statut |
|----------|--------|-------|--------|
| F1 classifier | 0.978 | > 0.8 | OK |
| Violation contraintes | 0.0 % | 0 % | OK |
| Couverture min (par goal) | 94.3 % | > 80 % | OK |
| Diversite Jaccard | 0.787 | < 0.5 | a optimiser |
| IoU rule-based vs ML | 0.544 | 0.6 - 0.8 | a optimiser |
| Latence p50 / p95 | 187.6 / 410.2 ms | < 200 / < 500 ms | OK |

## Classifier

- **F1 (score > 0.5)** : 0.978 -- cible > 0.8
- Matrice de confusion : TP=1498 FP=44 FN=22 TN=116

Voir `metrics/confusion_matrix.png`.

## Contraintes dures

- **Taux de violation** : 0.0 % -- cible 0 %
- Sur 120 programmes generes, % contenant un exercice avec equipement absent
  OU contre-indique par une limitation.

## Couverture des objectifs

| Objectif | Couverture |
|----------|-----------|
| endurance | 94.3 % |
| fat_loss | 100.0 % |
| general_health | 100.0 % |
| muscle_strength | 98.6 % |

Cible : > 80 % par objectif.

## Diversite

- **Jaccard moyen sur 2 programmes consecutifs** : 0.787 -- cible < 0.5
- Plus l'indice est faible, plus les programmes sont varies.

## IoU rule-based vs ML

- **IoU top-10** : 0.544 -- cible 0.6 a 0.8
- Recouvrement des top-10 exercices entre les deux strategies (proximite des classements).

Voir `metrics/iou_heatmap.png`.

## Latence

- **p50** : 187.6 ms -- cible < 200 ms
- **p95** : 410.2 ms -- cible < 500 ms

Mesure sur 120 appels in-process de `recommend_premium`.
Voir `metrics/latency_boxplot.png`.

## Evaluation humaine (HITL)

**Methodologie** : Tirage aleatoire de 20 programmes parmi ceux generes (metrics.json -> champ `programs`). Chaque programme est note 1-5 sur la coherence (adequation goal/level/equipement, progression, varietes muscles travailles) par 2 evaluateurs independants. Score retenu = moyenne des 2.

**Cible** : moyenne > 3.8/5.

| # | Programme (id) | Note (1-5) | Commentaire |
|---|----------------|------------|-------------|
| 1 | _a remplir_    | _._        | _._         |
| ...| ...           | ...        | ...         |
| 20 | _a remplir_   | _._        | _._         |

> Cette section est un livrable jury : les 20 notations sont a saisir manuellement
> apres tirage aleatoire de 20 programmes parmi ceux generes (voir `metrics.json`).
