"""
Tests unitaires du fitness profile service.
MongoDB est mocke -- pas besoin de Docker.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    FitnessProfileResponse,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services import fitness_profile_service as svc


def _make_payload(**kwargs) -> FitnessProfileRequest:
    defaults = {
        "health_goal_fitness": HealthGoalFitness.fat_loss,
        "experience_level": ExperienceLevel.beginner,
        "equipment": ["dumbbells"],
        "limitations": [],
        "preferences": SessionPreferences(duration_min_per_session=45, sessions_per_week=3),
    }
    defaults.update(kwargs)
    return FitnessProfileRequest(**defaults)


def _mock_db(find_result=None):
    col = AsyncMock()
    col.find_one = AsyncMock(return_value=find_result)
    col.update_one = AsyncMock()
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    return db, col


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_returns_profile_when_found(self):
        doc = {
            "user_id": "u-1",
            "health_goal_fitness": "fat_loss",
            "experience_level": "beginner",
            "equipment": ["dumbbells"],
            "limitations": [],
            "preferences": {"duration_min_per_session": 45, "sessions_per_week": 3},
            "updated_at": datetime.now(timezone.utc),
        }
        db, _ = _mock_db(find_result=doc)
        result = await svc.get_profile("u-1", db)
        assert isinstance(result, FitnessProfileResponse)
        assert result.user_id == "u-1"
        assert result.health_goal_fitness == HealthGoalFitness.fat_loss

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        db, _ = _mock_db(find_result=None)
        with pytest.raises(HTTPException) as exc:
            await svc.get_profile("unknown", db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_queries_by_user_id(self):
        db, col = _mock_db(find_result=None)
        try:
            await svc.get_profile("u-42", db)
        except HTTPException:
            pass
        col.find_one.assert_called_once()
        call_filter = col.find_one.call_args[0][0]
        assert call_filter["user_id"] == "u-42"


class TestUpsertProfile:
    @pytest.mark.asyncio
    async def test_creates_profile_and_returns_response(self):
        db, col = _mock_db()
        payload = _make_payload()
        result = await svc.upsert_profile("u-1", payload, db)
        assert isinstance(result, FitnessProfileResponse)
        assert result.user_id == "u-1"
        assert result.health_goal_fitness == HealthGoalFitness.fat_loss
        col.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_uses_user_id_as_filter(self):
        db, col = _mock_db()
        await svc.upsert_profile("u-99", _make_payload(), db)
        filter_arg = col.update_one.call_args[0][0]
        assert filter_arg == {"user_id": "u-99"}

    @pytest.mark.asyncio
    async def test_upsert_sets_updated_at(self):
        db, _ = _mock_db()
        result = await svc.upsert_profile("u-1", _make_payload(), db)
        assert isinstance(result.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_upsert_stores_enum_values_as_strings(self):
        db, col = _mock_db()
        await svc.upsert_profile("u-1", _make_payload(), db)
        set_doc = col.update_one.call_args[0][1]["$set"]
        assert set_doc["health_goal_fitness"] == "fat_loss"
        assert set_doc["experience_level"] == "beginner"


class TestScoringWeights:
    def test_all_goals_present(self):
        from app.data.scoring_weights import SCORING_WEIGHTS
        expected = {"fat_loss", "muscle_strength", "endurance", "general_health"}
        assert set(SCORING_WEIGHTS.keys()) == expected

    def test_weights_sum_to_one_per_goal(self):
        from app.data.scoring_weights import SCORING_WEIGHTS
        for goal, weights in SCORING_WEIGHTS.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 1e-9, f"Poids de '{goal}' somme a {total}, attendu 1.0"

    def test_all_dimensions_present_per_goal(self):
        from app.data.scoring_weights import SCORING_WEIGHTS
        expected_dims = {"goal", "level", "equipment", "novelty", "limit"}
        for goal, weights in SCORING_WEIGHTS.items():
            assert set(weights.keys()) == expected_dims, f"Dimensions manquantes pour '{goal}'"
