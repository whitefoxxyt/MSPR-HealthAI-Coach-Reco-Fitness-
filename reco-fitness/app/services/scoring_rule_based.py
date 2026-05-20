import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.data.scoring_weights import SCORING_WEIGHTS
from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
)
from app.services.exercise_catalog import Exercise


@dataclass
class Recommendation:
    exercise_id: int
    feedback_score: int | None
    created_at: datetime


GOAL_CATEGORY_AFFINITY: dict[str, dict[str, float]] = {
    "fat_loss": {"cardio": 1.0, "strength": 0.5, "flexibility": 0.3},
    "muscle_strength": {"strength": 1.0, "cardio": 0.3, "flexibility": 0.4},
    "endurance": {"cardio": 1.0, "strength": 0.4, "flexibility": 0.4},
    "general_health": {"cardio": 0.8, "strength": 0.8, "flexibility": 0.7},
}
_DEFAULT_AFFINITY = 0.5


def goal_match(exercise: Exercise, health_goal: HealthGoalFitness) -> float:
    affinity = GOAL_CATEGORY_AFFINITY.get(health_goal.value, {})
    if exercise.category is None:
        return _DEFAULT_AFFINITY
    return affinity.get(exercise.category, _DEFAULT_AFFINITY)


def equipment_match(exercise: Exercise, user_equipment: list[str]) -> float:
    required = [e for e in exercise.equipment if e != "none"]
    if not required:
        return 1.0
    owned = set(user_equipment)
    matched = sum(1 for item in required if item in owned)
    return matched / len(required)


_LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


def level_match(exercise: Exercise, experience_level: ExperienceLevel) -> float:
    ex_idx = _LEVEL_ORDER.get(exercise.difficulty, 0)
    user_idx = _LEVEL_ORDER[experience_level.value]
    gap = abs(ex_idx - user_idx)
    if gap == 0:
        return 1.0
    if gap == 1:
        return 0.5
    return 0.0


_NOVELTY_TAU_DAYS = 7.0


def novelty_and_feedback_score(exercise: Exercise, history: list[Recommendation]) -> float:
    last = _last_occurrence(exercise, history)
    if last is None:
        return 1.0
    days = _days_since(last.created_at)
    novelty = 1.0 - math.exp(-days / _NOVELTY_TAU_DAYS)
    return novelty * _feedback_multiplier(last.feedback_score)


def _feedback_multiplier(feedback_score: int | None) -> float:
    if feedback_score is None:
        return 1.0
    if feedback_score <= 1:
        return 1.0 / 5.0
    if feedback_score <= 2:
        return 1.0 / 2.0
    return 1.0


def _last_occurrence(exercise: Exercise, history: list[Recommendation]) -> Recommendation | None:
    occurrences = [r for r in history if r.exercise_id == exercise.id]
    if not occurrences:
        return None
    return max(occurrences, key=lambda r: r.created_at)


def _days_since(when: datetime) -> float:
    now = datetime.now(timezone.utc)
    delta = now - when
    return delta.total_seconds() / 86400.0


def limitation_filter(exercise: Exercise, limitations: list[str]) -> float:
    blocked = set(limitations)
    if blocked & set(exercise.target_muscles):
        return 0.0
    if exercise.category and exercise.category in blocked:
        return 0.0
    return 1.0


def score_exercise(
    exercise: Exercise,
    profile: FitnessProfileRequest,
    history: list[Recommendation],
) -> float:
    weights = SCORING_WEIGHTS[profile.health_goal_fitness.value]
    return (
        weights["goal"] * goal_match(exercise, profile.health_goal_fitness)
        + weights["level"] * level_match(exercise, profile.experience_level)
        + weights["equipment"] * equipment_match(exercise, profile.equipment)
        + weights["novelty"] * novelty_and_feedback_score(exercise, history)
        + weights["limit"] * limitation_filter(exercise, profile.limitations)
    )
