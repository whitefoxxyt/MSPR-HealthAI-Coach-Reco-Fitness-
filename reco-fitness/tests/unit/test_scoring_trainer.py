"""Tests for the training pipeline that produces the scoring model + report."""
import json
from pathlib import Path

import joblib
import pytest
from app.services.exercise_catalog import Exercise
from app.services.scoring_trainer import train_and_persist
from app.services.training_data import build_dataset
from sklearn.ensemble import RandomForestRegressor


def _mini_catalog(n: int = 6) -> list[Exercise]:
    categories = ["cardio", "strength"]
    difficulties = ["beginner", "intermediate", "advanced"]
    equipments = [["none"], ["dumbbells"], ["barbell", "rack"]]
    muscles = [["chest"], ["quadriceps"], ["glutes"]]
    return [
        Exercise(
            id=i,
            name=f"ex-{i}",
            target_muscles=muscles[i % len(muscles)],
            equipment=equipments[i % len(equipments)],
            difficulty=difficulties[i % len(difficulties)],
            category=categories[i % len(categories)],
        )
        for i in range(1, n + 1)
    ]


@pytest.fixture()
def training_csv(tmp_path: Path) -> Path:
    df = build_dataset(_mini_catalog(6), n_profiles=40, seed=42)
    csv_path = tmp_path / "scoring_dataset.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


class TestTrainAndPersistArtifacts:
    def test_creates_model_pkl_with_expected_bundle_keys(
        self, training_csv: Path, tmp_path: Path
    ):
        model_path = tmp_path / "scoring_model.pkl"
        report_path = tmp_path / "training_report.json"

        train_and_persist(training_csv, model_path, report_path)

        assert model_path.exists()
        bundle = joblib.load(model_path)
        assert set(bundle) == {"model", "vocab", "feature_columns"}
        assert isinstance(bundle["model"], RandomForestRegressor)
        assert isinstance(bundle["feature_columns"], list)
        assert len(bundle["feature_columns"]) > 0

    def test_creates_report_json_with_val_and_test_metrics(
        self, training_csv: Path, tmp_path: Path
    ):
        model_path = tmp_path / "scoring_model.pkl"
        report_path = tmp_path / "training_report.json"

        train_and_persist(training_csv, model_path, report_path)

        report = json.loads(report_path.read_text())
        assert "val" in report and "test" in report
        for key in ("mse", "r2"):
            assert isinstance(report["val"][key], float)
        for key in ("precision", "recall", "f1"):
            assert isinstance(report["test"][key], float)


class TestSplitDeterministic:
    def test_default_run_produces_reproducible_report(
        self, training_csv: Path, tmp_path: Path
    ):
        path_a_report = tmp_path / "a.json"
        path_b_report = tmp_path / "b.json"
        train_and_persist(training_csv, tmp_path / "a.pkl", path_a_report)
        train_and_persist(training_csv, tmp_path / "b.pkl", path_b_report)
        assert path_a_report.read_text() == path_b_report.read_text()


class TestHyperparametersDefaults:
    def test_default_hyperparameters_match_issue_spec(
        self, training_csv: Path, tmp_path: Path
    ):
        model_path = tmp_path / "scoring_model.pkl"
        train_and_persist(training_csv, model_path, tmp_path / "report.json")
        bundle = joblib.load(model_path)
        model = bundle["model"]
        assert model.n_estimators == 200
        assert model.max_depth == 15
        assert model.random_state == 42


class TestEndToEndWithScoringMl:
    def test_trained_model_is_loadable_by_scoring_ml_module(
        self, training_csv: Path, tmp_path: Path, monkeypatch
    ):
        from app.schemas.fitness_profile import (
            ExperienceLevel,
            FitnessProfileRequest,
            HealthGoalFitness,
            SessionPreferences,
        )
        from app.services import scoring_ml

        model_path = tmp_path / "scoring_model.pkl"
        train_and_persist(training_csv, model_path, tmp_path / "report.json")

        monkeypatch.setattr(scoring_ml, "MODEL_PATH", model_path)
        scoring_ml.reset_model()

        catalog = _mini_catalog(6)
        score = scoring_ml.score_exercise(
            catalog[0],
            FitnessProfileRequest(
                health_goal_fitness=HealthGoalFitness.muscle_strength,
                experience_level=ExperienceLevel.intermediate,
                equipment=["barbell"],
                limitations=[],
                preferences=SessionPreferences(),
            ),
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
