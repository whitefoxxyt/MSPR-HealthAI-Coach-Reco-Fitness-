"""
Matrice de ponderation pour le moteur de scoring base sur les regles.
4 objectifs fitness x 5 dimensions de scoring.
La somme des poids doit etre egale a 1.0 pour chaque objectif.
"""

SCORING_WEIGHTS: dict[str, dict[str, float]] = {
    "fat_loss": {
        "goal": 0.35,
        "level": 0.20,
        "equipment": 0.15,
        "novelty": 0.20,
        "limit": 0.10,
    },
    "muscle_strength": {
        "goal": 0.40,
        "level": 0.25,
        "equipment": 0.10,
        "novelty": 0.15,
        "limit": 0.10,
    },
    "endurance": {
        "goal": 0.30,
        "level": 0.15,
        "equipment": 0.10,
        "novelty": 0.30,
        "limit": 0.15,
    },
    "general_health": {
        "goal": 0.25,
        "level": 0.20,
        "equipment": 0.15,
        "novelty": 0.25,
        "limit": 0.15,
    },
}
