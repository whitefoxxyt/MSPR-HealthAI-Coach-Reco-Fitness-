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

## Démarrage

```bash
# À venir
```
