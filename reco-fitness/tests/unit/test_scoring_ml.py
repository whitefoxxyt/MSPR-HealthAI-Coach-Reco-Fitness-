"""Tests for ML scoring module."""
from pathlib import Path

import joblib
import pytest
from sklearn.ensemble import RandomForestRegressor

from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services import scoring_ml
from app.services.exercise_catalog import Exercise
from app.services.training_data import build_dataset, derive_vocab


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the lazy-loaded singleton between tests."""
    scoring_ml.reset_model()
    yield
    scoring_ml.reset_model()


def _mini_catalog() -> list[Exercise]:
    return [
        Exercise(
            id=1,
            name="squat",
            target_muscles=["quadriceps", "glutes"],
            equipment=["barbell"],
            difficulty="intermediate",
            category="strength",
        ),
        Exercise(
            id=2,
            name="run",
            target_muscles=["calves"],
            equipment=["none"],
            difficulty="beginner",
            category="cardio",
        ),
        Exercise(
            id=3,
            name="bench",
            target_muscles=["chest"],
            equipment=["barbell", "rack"],
            difficulty="advanced",
            category="strength",
        ),
    ]


def _profile(
    goal: HealthGoalFitness = HealthGoalFitness.muscle_strength,
    level: ExperienceLevel = ExperienceLevel.intermediate,
) -> FitnessProfileRequest:
    return FitnessProfileRequest(
        health_goal_fitness=goal,
        experience_level=level,
        equipment=["barbell"],
        limitations=[],
        preferences=SessionPreferences(),
    )


@pytest.fixture()
def trained_model_path(tmp_path: Path, monkeypatch) -> Path:
    """Trains a tiny model, persists the bundle, points MODEL_PATH at it."""
    catalog = _mini_catalog()
    vocab = derive_vocab(catalog)
    df = build_dataset(catalog, n_profiles=8, seed=42)
    feature_columns = [c for c in df.columns if c not in ("label", "exercise_id")]
    X = df[feature_columns].to_numpy()
    y = df["label"].to_numpy()
    model = RandomForestRegressor(n_estimators=20, max_depth=5, random_state=42)
    model.fit(X, y)

    path = tmp_path / "scoring_model.pkl"
    joblib.dump(
        {"model": model, "vocab": vocab, "feature_columns": feature_columns},
        path,
    )
    monkeypatch.setattr(scoring_ml, "MODEL_PATH", path)
    return path


class TestMissingModelFailsFast:
    def test_missing_pkl_raises_explicit_filenotfound(self, tmp_path: Path, monkeypatch):
        missing = tmp_path / "nope" / "scoring_model.pkl"
        monkeypatch.setattr(scoring_ml, "MODEL_PATH", missing)

        with pytest.raises(FileNotFoundError, match="scoring_model.pkl"):
            scoring_ml.get_model()


class TestInferenceReturnsFloatInUnitInterval:
    def test_score_exercise_returns_float_between_zero_and_one(self, trained_model_path):
        catalog = _mini_catalog()
        score = scoring_ml.score_exercise(catalog[0], _profile())
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


class TestEncodingConsistentWithTraining:
    def test_inference_uses_bundled_feature_columns_in_order(self, trained_model_path):
        """Le modele doit etre interroge avec exactement les colonnes du training,
        dans le meme ordre. Si on retire ou reorganise une feature, l'inference doit casser."""
        import joblib

        bundle = joblib.load(trained_model_path)
        # corrompt l'ordre : on inverse la liste des feature_columns
        bundle["feature_columns"] = list(reversed(bundle["feature_columns"]))
        joblib.dump(bundle, trained_model_path)
        scoring_ml.reset_model()

        catalog = _mini_catalog()
        scrambled = scoring_ml.score_exercise(catalog[0], _profile())

        # On retablit l'ordre original
        bundle["feature_columns"] = list(reversed(bundle["feature_columns"]))
        joblib.dump(bundle, trained_model_path)
        scoring_ml.reset_model()

        correct = scoring_ml.score_exercise(catalog[0], _profile())
        # Avec un ordre different la prediction differe (sauf coincidence numerique improbable).
        assert scrambled != correct

    def test_inference_features_match_encode_pair_output(self, trained_model_path):
        """Les features extraites pour l'inference doivent etre identiques a celles
        produites par encode_pair (au label/exercise_id pres)."""
        import joblib

        from app.services.training_data import encode_pair

        bundle = joblib.load(trained_model_path)
        catalog = _mini_catalog()
        profile = _profile()
        row = encode_pair(catalog[0], profile, score=0.0, vocab=bundle["vocab"])
        for col in bundle["feature_columns"]:
            assert col in row, f"colonne {col} manquante dans encode_pair output"


class TestSingletonLazyLoading:
    def test_get_model_loads_from_disk_only_once(self, trained_model_path, monkeypatch):
        load_calls = []
        import joblib

        real_load = joblib.load

        def counting_load(path, *args, **kwargs):
            load_calls.append(path)
            return real_load(path, *args, **kwargs)

        monkeypatch.setattr("joblib.load", counting_load)

        scoring_ml.get_model()
        scoring_ml.get_model()
        scoring_ml.get_model()

        assert len(load_calls) == 1
