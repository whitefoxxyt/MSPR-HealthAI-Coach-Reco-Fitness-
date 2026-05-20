# MSPR-HealthAI-Coach-Reco-Fitness

Micro-service de recommandations fitness, partie de la plateforme HealthAI Coach (MSPR2).

## Stack

- **FastAPI** : API REST
- **MongoDB** : stockage des profils et programmes fitness
- **PostgreSQL** : catalogue d'exercices (lecture seule, via MSPR-DB)

## Algorithme de scoring

```python
score = (
    w_goal      * goal_match(exercise, user.goal)
  + w_level     * level_match(exercise, user.experience)
  + w_equipment * equipment_match(exercise, user.gear)
  + w_novelty   * novelty_score(exercise, user.history)
  + w_limit     * limitation_filter(exercise, user.injuries)
)
```

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /recommendations` | Génère un programme personnalisé |
| `GET /programs/{user_id}` | Historique programmes + progression |
| `PUT /programs/{program_id}/feedback` | Retour utilisateur (adaptation) |
| `GET /health` | Healthcheck |

## Dataset d'entraînement ML

Le scoring rule-based sert d'**oracle** pour générer un dataset synthétique destiné à entraîner un modèle ML (issue RF-9).

```bash
# Génère data/training/scoring_dataset.csv (5000+ lignes)
python scripts/generate_training_data.py

# Avec paramètres custom
python scripts/generate_training_data.py --n-profiles 25 --seed 42 \
    --out data/training/scoring_dataset.csv
```

Le dossier `data/training/` est **gitignore** : le dataset est regénérable à tout moment depuis le catalogue PostgreSQL. Format CSV avec :

- une colonne `exercise_id`
- des features one-hot/multi-hot dérivées du catalogue (`ex_muscle_*`, `ex_equipment_*`, `ex_difficulty_*`, `ex_category_*`)
- des features one-hot/multi-hot du profil (`profile_goal_*`, `profile_level_*`, `profile_equipment_*`, `profile_limit_*`)
- une colonne `label` (score float ∈ [0, 1]) calculée via `scoring_rule_based.score_exercise`

Distribution équilibrée : 25 % par objectif fitness × ~33 % par niveau d'expérience, sous-ensembles d'équipement/limitations tirés aléatoirement depuis le vocab du catalogue. Reproductible via `--seed`.

## Démarrage

```bash
# À venir
```
