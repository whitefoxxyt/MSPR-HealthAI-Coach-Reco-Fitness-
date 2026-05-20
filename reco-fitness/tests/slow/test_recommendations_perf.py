"""Test de perf simple (slow) : p50 < 500ms sur recommend_premium (cas le plus lourd)."""
import statistics
import time

import pytest

from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services import workout_program_orchestrator as orchestrator
from app.services.exercise_catalog import Exercise


@pytest.mark.slow
def test_recommend_premium_p50_under_500ms(monkeypatch):
    """20 generations consecutives : la mediane doit etre < 500ms."""
    monkeypatch.setattr(
        "app.services.workout_program_orchestrator.score_ml",
        lambda exercise, profile: max(0.0, 1.0 - exercise.id * 0.001),
    )

    catalog = [
        Exercise(
            id=i,
            name=f"ex-{i}",
            category="strength",
            difficulty="intermediate",
            equipment=["dumbbells"],
            target_muscles=["chest"],
        )
        for i in range(1, 500)
    ]
    profile = FitnessProfileRequest(
        health_goal_fitness=HealthGoalFitness.muscle_strength,
        experience_level=ExperienceLevel.intermediate,
        equipment=["dumbbells"],
        limitations=[],
        preferences=SessionPreferences(),
    )

    durations_ms: list[float] = []
    for _ in range(20):
        start = time.perf_counter()
        orchestrator.recommend_premium(profile, history=[], catalog=catalog)
        durations_ms.append((time.perf_counter() - start) * 1000)

    p50 = statistics.median(durations_ms)
    assert p50 < 500.0, f"p50={p50:.1f}ms (cible < 500ms), durations={durations_ms}"
