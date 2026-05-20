"""ML-based exercise scoring : charge un RandomForest entraine et expose `score_exercise`."""
from __future__ import annotations

from pathlib import Path

from app.schemas.fitness_profile import FitnessProfileRequest
from app.services.exercise_catalog import Exercise
from app.services.training_data import encode_pair

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "scoring_model.pkl"

_model_bundle: dict | None = None


def reset_model() -> None:
    """Vide le singleton (utile pour les tests et apres un re-entrainement)."""
    global _model_bundle
    _model_bundle = None


def get_model() -> dict:
    """Charge lazily le bundle {model, vocab, feature_columns} depuis MODEL_PATH."""
    global _model_bundle
    if _model_bundle is not None:
        return _model_bundle
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"scoring_model.pkl introuvable a {MODEL_PATH}. "
            "Lance `python scripts/train_scoring_model.py` pour le generer."
        )
    import joblib

    _model_bundle = joblib.load(MODEL_PATH)
    return _model_bundle


def score_exercise(exercise: Exercise, profile: FitnessProfileRequest) -> float:
    """Inference : retourne le score predit par le modele RF, clamp dans [0, 1]."""
    bundle = get_model()
    row = encode_pair(exercise, profile, score=0.0, vocab=bundle["vocab"])
    features = [row[col] for col in bundle["feature_columns"]]
    prediction = float(bundle["model"].predict([features])[0])
    return max(0.0, min(1.0, prediction))
