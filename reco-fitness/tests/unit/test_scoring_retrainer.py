"""Tests for the feedback-enriched retraining pipeline (RF-15)."""
from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
import pytest
from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services.exercise_catalog import Exercise
from app.services.scoring_retrainer import (
    build_feedback_rows,
    retrain_and_maybe_replace,
    should_replace_model,
)
from app.services.training_data import build_dataset, derive_vocab


def _ex(
    exercise_id: int = 1,
    target_muscles: list[str] | None = None,
    equipment: list[str] | None = None,
    difficulty: str = "beginner",
    category: str | None = "strength",
) -> Exercise:
    return Exercise(
        id=exercise_id,
        name=f"ex-{exercise_id}",
        target_muscles=target_muscles or ["quadriceps"],
        equipment=equipment or ["none"],
        difficulty=difficulty,
        category=category,
    )


def _profile(
    health_goal_fitness: HealthGoalFitness = HealthGoalFitness.fat_loss,
    experience_level: ExperienceLevel = ExperienceLevel.intermediate,
    equipment: list[str] | None = None,
    limitations: list[str] | None = None,
) -> FitnessProfileRequest:
    return FitnessProfileRequest(
        health_goal_fitness=health_goal_fitness,
        experience_level=experience_level,
        equipment=equipment or [],
        limitations=limitations or [],
        preferences=SessionPreferences(),
    )


class TestBuildFeedbackRows:
    def test_one_valid_feedback_produces_one_row_with_label_score_div_5(self):
        catalog = [_ex(1, target_muscles=["chest"], equipment=["dumbbells"])]
        vocab = derive_vocab(catalog)
        feedbacks = [
            {
                "user_id": "u1",
                "program_id": "p1",
                "exercise_id": 1,
                "feedback_score": 4,
            }
        ]

        df = build_feedback_rows(
            feedbacks=feedbacks,
            profiles_by_user={"u1": _profile()},
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df["label"].iloc[0] == 0.8

    def test_empty_feedback_list_returns_empty_dataframe(self):
        catalog = [_ex(1)]
        vocab = derive_vocab(catalog)

        df = build_feedback_rows(
            feedbacks=[],
            profiles_by_user={},
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_multiple_feedbacks_produce_one_row_each_with_correct_labels(self):
        catalog = [
            _ex(1, target_muscles=["chest"], equipment=["dumbbells"]),
            _ex(2, target_muscles=["quadriceps"], equipment=["barbell"]),
        ]
        vocab = derive_vocab(catalog)
        feedbacks = [
            {"user_id": "u1", "program_id": "p1", "exercise_id": 1, "feedback_score": 1},
            {"user_id": "u1", "program_id": "p1", "exercise_id": 2, "feedback_score": 5},
            {"user_id": "u2", "program_id": "p2", "exercise_id": 1, "feedback_score": 3},
        ]

        df = build_feedback_rows(
            feedbacks=feedbacks,
            profiles_by_user={"u1": _profile(), "u2": _profile()},
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )

        assert len(df) == 3
        assert sorted(df["label"].tolist()) == [0.2, 0.6, 1.0]

    def test_feedback_with_missing_profile_is_ignored(self):
        catalog = [_ex(1)]
        vocab = derive_vocab(catalog)
        feedbacks = [
            {
                "user_id": "ghost-user",
                "program_id": "p1",
                "exercise_id": 1,
                "feedback_score": 5,
            }
        ]

        df = build_feedback_rows(
            feedbacks=feedbacks,
            profiles_by_user={},
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )

        assert len(df) == 0

    def test_feedback_referencing_missing_exercise_is_ignored(self):
        catalog = [_ex(1)]
        vocab = derive_vocab(catalog)
        feedbacks = [
            {
                "user_id": "u1",
                "program_id": "p1",
                "exercise_id": 999,
                "feedback_score": 3,
            }
        ]

        df = build_feedback_rows(
            feedbacks=feedbacks,
            profiles_by_user={"u1": _profile()},
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )

        assert len(df) == 0

    def test_program_level_feedback_with_exercise_id_none_is_ignored(self):
        catalog = [_ex(1)]
        vocab = derive_vocab(catalog)
        feedbacks = [
            {
                "user_id": "u1",
                "program_id": "p1",
                "exercise_id": None,
                "feedback_score": 5,
            }
        ]

        df = build_feedback_rows(
            feedbacks=feedbacks,
            profiles_by_user={"u1": _profile()},
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )

        assert len(df) == 0


def _mini_catalog(n: int = 8) -> list[Exercise]:
    categories = ["cardio", "strength"]
    difficulties = ["beginner", "intermediate", "advanced"]
    equipments = [["none"], ["dumbbells"], ["barbell", "rack"]]
    muscles = [["chest"], ["quadriceps"], ["glutes"], ["lower_back"]]
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
def base_csv(tmp_path: Path) -> Path:
    df = build_dataset(_mini_catalog(8), n_profiles=40, seed=42)
    path = tmp_path / "scoring_dataset.csv"
    df.to_csv(path, index=False)
    return path


class TestRetrainAndMaybeReplace:
    def test_first_run_without_old_model_writes_pickle_and_returns_replaced_true(
        self, base_csv: Path, tmp_path: Path
    ):
        model_path = tmp_path / "scoring_model.pkl"
        report_path = tmp_path / "retrain_report.json"
        assert not model_path.exists()

        report = retrain_and_maybe_replace(
            base_csv=base_csv,
            feedback_rows=pd.DataFrame(),
            model_path=model_path,
            report_path=report_path,
        )

        assert report["replaced"] is True
        assert model_path.exists()
        bundle = joblib.load(model_path)
        assert set(bundle) == {"model", "vocab", "feature_columns"}

    def test_non_empty_feedback_rows_get_concatenated_into_training_set(
        self, base_csv: Path, tmp_path: Path
    ):
        # build_feedback_rows garantit que les colonnes restent alignees avec le vocab du base_csv.
        catalog = _mini_catalog(8)
        vocab = derive_vocab(catalog)
        feedbacks = [
            {"user_id": "u1", "program_id": "p1", "exercise_id": 1, "feedback_score": 5},
            {"user_id": "u2", "program_id": "p2", "exercise_id": 2, "feedback_score": 4},
        ]
        feedback_rows = build_feedback_rows(
            feedbacks=feedbacks,
            profiles_by_user={"u1": _profile(), "u2": _profile()},
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )

        report = retrain_and_maybe_replace(
            base_csv=base_csv,
            feedback_rows=feedback_rows,
            model_path=tmp_path / "scoring_model.pkl",
            report_path=tmp_path / "retrain_report.json",
        )

        assert report["n_feedback_used"] == 2

    def test_empty_feedback_falls_back_to_base_dataset_without_crash(
        self, base_csv: Path, tmp_path: Path
    ):
        report = retrain_and_maybe_replace(
            base_csv=base_csv,
            feedback_rows=pd.DataFrame(),
            model_path=tmp_path / "scoring_model.pkl",
            report_path=tmp_path / "retrain_report.json",
        )

        assert report["n_feedback_used"] == 0
        assert isinstance(report["new_f1"], float)

    def test_report_has_required_keys_and_persists_as_json(
        self, base_csv: Path, tmp_path: Path
    ):
        report_path = tmp_path / "retrain_report.json"
        report = retrain_and_maybe_replace(
            base_csv=base_csv,
            feedback_rows=pd.DataFrame(),
            model_path=tmp_path / "scoring_model.pkl",
            report_path=report_path,
        )

        expected = {"old_f1", "new_f1", "old_r2", "new_r2", "replaced", "n_feedback_used"}
        assert set(report) == expected
        # Persiste un JSON parsable avec les memes cles.
        import json

        on_disk = json.loads(report_path.read_text())
        assert set(on_disk) == expected

    def test_pipeline_keeps_pickle_when_replacement_policy_rejects(
        self, base_csv: Path, tmp_path: Path, monkeypatch
    ):
        from app.services import scoring_retrainer

        model_path = tmp_path / "scoring_model.pkl"
        report_path = tmp_path / "retrain_report.json"

        # 1er run : initialise le pickle.
        retrain_and_maybe_replace(base_csv, pd.DataFrame(), model_path, report_path)
        original_bytes = model_path.read_bytes()

        # 2e run : on force la decision a "ne pas remplacer".
        monkeypatch.setattr(
            scoring_retrainer, "should_replace_model", lambda old, new: False
        )
        report = retrain_and_maybe_replace(
            base_csv, pd.DataFrame(), model_path, report_path
        )

        assert report["replaced"] is False
        assert model_path.read_bytes() == original_bytes

    def test_old_model_with_mismatching_feature_columns_is_treated_as_first_run(
        self, base_csv: Path, tmp_path: Path
    ):
        # 1er run : initialise un pickle dont on va ensuite corrompre les feature_columns.
        model_path = tmp_path / "scoring_model.pkl"
        report_path = tmp_path / "retrain_report.json"
        retrain_and_maybe_replace(base_csv, pd.DataFrame(), model_path, report_path)
        bundle = joblib.load(model_path)
        bundle["feature_columns"] = ["col_inconnue_qui_ne_matche_pas"]
        joblib.dump(bundle, model_path)

        report = retrain_and_maybe_replace(
            base_csv, pd.DataFrame(), model_path, report_path
        )

        # vocab incompatible : on traite comme un premier run (old_f1/r2 = None, replaced = True).
        assert report["old_f1"] is None
        assert report["old_r2"] is None
        assert report["replaced"] is True


class TestShouldReplaceModel:
    def test_no_old_model_means_replace(self):
        assert should_replace_model(old_f1=None, new_f1=0.0) is True

    def test_strictly_better_replaces(self):
        assert should_replace_model(old_f1=0.5, new_f1=0.9) is True

    def test_equal_replaces(self):
        # Politique : >= (not just >). Egalite acceptable.
        assert should_replace_model(old_f1=0.7, new_f1=0.7) is True

    def test_strictly_worse_keeps_old(self):
        assert should_replace_model(old_f1=0.9, new_f1=0.5) is False
