from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services.exercise_catalog import Exercise
from app.services.scoring_rule_based import (
    Recommendation,
    equipment_match,
    goal_match,
    level_match,
    limitation_filter,
    novelty_and_feedback_score,
    score_exercise,
)


def _make_profile(
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


def _reco(
    exercise_id: int,
    days_ago: float,
    feedback_score: int | None = None,
) -> Recommendation:
    return Recommendation(
        exercise_id=exercise_id,
        feedback_score=feedback_score,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def _make_exercise(
    id: int = 1,
    name: str = "Squat",
    target_muscles: list[str] | None = None,
    equipment: list[str] | None = None,
    difficulty: str = "beginner",
    category: str | None = "legs",
) -> Exercise:
    return Exercise(
        id=id,
        name=name,
        target_muscles=target_muscles or ["quadriceps"],
        equipment=equipment or ["none"],
        difficulty=difficulty,
        category=category,
    )


class TestLimitationFilter:
    def test_no_limitations_returns_one(self):
        ex = _make_exercise(target_muscles=["quadriceps", "glutes"])
        assert limitation_filter(ex, []) == 1.0

    def test_targeted_muscle_in_limitations_returns_zero(self):
        ex = _make_exercise(target_muscles=["lower_back", "glutes"])
        assert limitation_filter(ex, ["lower_back"]) == 0.0

    def test_unrelated_limitation_returns_one(self):
        ex = _make_exercise(target_muscles=["chest"], category="upper")
        assert limitation_filter(ex, ["knee"]) == 1.0

    def test_category_in_limitations_returns_zero(self):
        ex = _make_exercise(target_muscles=["quadriceps"], category="cardio")
        assert limitation_filter(ex, ["cardio"]) == 0.0


class TestEquipmentMatch:
    def test_bodyweight_exercise_always_matches(self):
        ex = _make_exercise(equipment=["none"])
        assert equipment_match(ex, []) == 1.0

    def test_required_equipment_not_owned_returns_zero(self):
        ex = _make_exercise(equipment=["barbell"])
        assert equipment_match(ex, ["dumbbells"]) == 0.0

    def test_all_required_equipment_owned_returns_one(self):
        ex = _make_exercise(equipment=["barbell", "rack"])
        assert equipment_match(ex, ["barbell", "rack", "bench"]) == 1.0

    def test_partial_equipment_returns_ratio(self):
        ex = _make_exercise(equipment=["barbell", "rack"])
        assert equipment_match(ex, ["barbell"]) == 0.5

    def test_none_in_equipment_list_is_ignored(self):
        ex = _make_exercise(equipment=["none", "dumbbells"])
        assert equipment_match(ex, ["dumbbells"]) == 1.0


class TestLevelMatch:
    def test_exact_match_returns_one(self):
        ex = _make_exercise(difficulty="intermediate")
        assert level_match(ex, ExperienceLevel.intermediate) == 1.0

    def test_one_step_off_returns_half(self):
        ex = _make_exercise(difficulty="intermediate")
        assert level_match(ex, ExperienceLevel.beginner) == 0.5
        assert level_match(ex, ExperienceLevel.advanced) == 0.5

    def test_two_steps_off_returns_zero(self):
        ex_beginner = _make_exercise(difficulty="beginner")
        ex_advanced = _make_exercise(difficulty="advanced")
        assert level_match(ex_beginner, ExperienceLevel.advanced) == 0.0
        assert level_match(ex_advanced, ExperienceLevel.beginner) == 0.0


class TestGoalMatch:
    def test_cardio_matches_fat_loss(self):
        ex = _make_exercise(category="cardio")
        assert goal_match(ex, HealthGoalFitness.fat_loss) == 1.0

    def test_strength_matches_muscle_strength(self):
        ex = _make_exercise(category="strength")
        assert goal_match(ex, HealthGoalFitness.muscle_strength) == 1.0

    def test_score_changes_when_goal_changes(self):
        ex = _make_exercise(category="strength")
        s_strength = goal_match(ex, HealthGoalFitness.muscle_strength)
        s_endurance = goal_match(ex, HealthGoalFitness.endurance)
        assert s_strength != s_endurance
        assert s_strength == 1.0
        assert s_endurance == 0.4

    def test_unknown_category_returns_default(self):
        ex = _make_exercise(category="mobility")
        assert goal_match(ex, HealthGoalFitness.fat_loss) == 0.5

    def test_no_category_returns_default(self):
        ex = _make_exercise(category=None)
        assert goal_match(ex, HealthGoalFitness.fat_loss) == 0.5


class TestNoveltyAndFeedbackScore:
    def test_never_done_returns_one(self):
        ex = _make_exercise(id=1)
        assert novelty_and_feedback_score(ex, []) == 1.0

    def test_just_done_returns_zero(self):
        ex = _make_exercise(id=1)
        history = [_reco(exercise_id=1, days_ago=0)]
        assert novelty_and_feedback_score(ex, history) == pytest.approx(0.0, abs=1e-3)

    def test_curve_grows_with_days_since_last(self):
        ex = _make_exercise(id=1)
        score_7d = novelty_and_feedback_score(ex, [_reco(1, days_ago=7)])
        score_14d = novelty_and_feedback_score(ex, [_reco(1, days_ago=14)])
        assert score_7d == pytest.approx(1.0 - 1.0 / 2.718281828, abs=1e-3)
        assert score_14d == pytest.approx(0.865, abs=1e-3)
        assert score_14d > score_7d

    def test_only_last_occurrence_counts(self):
        ex = _make_exercise(id=1)
        history_old_then_recent = [_reco(1, days_ago=30), _reco(1, days_ago=2)]
        history_only_old = [_reco(1, days_ago=30)]
        score_mixed = novelty_and_feedback_score(ex, history_old_then_recent)
        score_old = novelty_and_feedback_score(ex, history_only_old)
        assert score_mixed < score_old
        assert score_mixed < 0.3

    def test_other_exercises_in_history_ignored(self):
        ex = _make_exercise(id=1)
        history = [_reco(99, days_ago=0)]
        assert novelty_and_feedback_score(ex, history) == 1.0

    def test_feedback_one_divides_score_by_five(self):
        ex = _make_exercise(id=1)
        score_no_fb = novelty_and_feedback_score(ex, [_reco(1, days_ago=14)])
        score_fb_1 = novelty_and_feedback_score(ex, [_reco(1, days_ago=14, feedback_score=1)])
        assert score_fb_1 == pytest.approx(score_no_fb / 5, abs=1e-6)

    def test_feedback_two_divides_score_by_two(self):
        ex = _make_exercise(id=1)
        score_no_fb = novelty_and_feedback_score(ex, [_reco(1, days_ago=14)])
        score_fb_2 = novelty_and_feedback_score(ex, [_reco(1, days_ago=14, feedback_score=2)])
        assert score_fb_2 == pytest.approx(score_no_fb / 2, abs=1e-6)

    def test_feedback_three_no_penalty(self):
        ex = _make_exercise(id=1)
        score_no_fb = novelty_and_feedback_score(ex, [_reco(1, days_ago=14)])
        score_fb_3 = novelty_and_feedback_score(ex, [_reco(1, days_ago=14, feedback_score=3)])
        assert score_fb_3 == pytest.approx(score_no_fb, abs=1e-6)


class TestScoreExercise:
    def test_returns_weighted_sum_between_zero_and_one(self):
        ex = _make_exercise(
            id=1,
            category="cardio",
            difficulty="intermediate",
            equipment=["none"],
            target_muscles=["legs"],
        )
        profile = _make_profile(
            health_goal_fitness=HealthGoalFitness.fat_loss,
            experience_level=ExperienceLevel.intermediate,
        )
        score = score_exercise(ex, profile, history=[])
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_changing_goal_changes_score(self):
        ex = _make_exercise(
            id=1,
            category="cardio",
            difficulty="intermediate",
            equipment=["none"],
            target_muscles=["legs"],
        )
        s_fat_loss = score_exercise(
            ex, _make_profile(health_goal_fitness=HealthGoalFitness.fat_loss), []
        )
        s_strength = score_exercise(
            ex, _make_profile(health_goal_fitness=HealthGoalFitness.muscle_strength), []
        )
        assert s_fat_loss != s_strength

    def test_contraindicated_exercise_lowers_score(self):
        ex = _make_exercise(target_muscles=["lower_back"])
        s_safe = score_exercise(ex, _make_profile(limitations=[]), [])
        s_blocked = score_exercise(ex, _make_profile(limitations=["lower_back"]), [])
        assert s_blocked < s_safe
