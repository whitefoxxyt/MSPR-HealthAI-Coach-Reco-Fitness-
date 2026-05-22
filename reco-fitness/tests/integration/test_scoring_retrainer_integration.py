"""Integration tests for Mongo loaders used by the retrain pipeline (RF-15)."""
from __future__ import annotations

import pytest
from app.schemas.fitness_profile import (
    ExperienceLevel,
    HealthGoalFitness,
)
from app.services.scoring_retrainer import (
    load_feedbacks_from_mongo,
    load_profiles_from_mongo,
)


@pytest.mark.integration
class TestLoadFeedbacksFromMongo:
    def test_returns_only_feedbacks_with_non_null_exercise_id(self, mongo_db):
        mongo_db["recommendation_history"].insert_many(
            [
                {
                    "user_id": "u1",
                    "program_id": "p1",
                    "exercise_id": 10,
                    "feedback_score": 4,
                },
                {
                    "user_id": "u1",
                    "program_id": "p1",
                    "exercise_id": None,
                    "feedback_score": 5,
                },
                {
                    "user_id": "u2",
                    "program_id": "p2",
                    "exercise_id": 11,
                    "feedback_score": 2,
                },
            ]
        )

        feedbacks = load_feedbacks_from_mongo(mongo_db)

        assert len(feedbacks) == 2
        assert {fb["exercise_id"] for fb in feedbacks} == {10, 11}

    def test_returns_empty_list_when_collection_empty(self, mongo_db):
        feedbacks = load_feedbacks_from_mongo(mongo_db)
        assert feedbacks == []


@pytest.mark.integration
class TestLoadProfilesFromMongo:
    def test_returns_dict_keyed_by_user_id_for_requested_ids(self, mongo_db):
        mongo_db["user_fitness_profiles"].insert_many(
            [
                {
                    "user_id": "u1",
                    "health_goal_fitness": "fat_loss",
                    "experience_level": "beginner",
                    "equipment": ["dumbbells"],
                    "limitations": [],
                    "preferences": {},
                },
                {
                    "user_id": "u2",
                    "health_goal_fitness": "muscle_strength",
                    "experience_level": "advanced",
                    "equipment": [],
                    "limitations": ["lower_back"],
                    "preferences": {},
                },
            ]
        )

        profiles = load_profiles_from_mongo(mongo_db, user_ids=["u1", "u2"])

        assert set(profiles) == {"u1", "u2"}
        assert profiles["u1"].health_goal_fitness == HealthGoalFitness.fat_loss
        assert profiles["u2"].experience_level == ExperienceLevel.advanced
        assert profiles["u2"].limitations == ["lower_back"]

    def test_returns_only_requested_profiles(self, mongo_db):
        mongo_db["user_fitness_profiles"].insert_many(
            [
                {
                    "user_id": "u1",
                    "health_goal_fitness": "fat_loss",
                    "experience_level": "beginner",
                    "equipment": [],
                    "limitations": [],
                    "preferences": {},
                },
                {
                    "user_id": "u2",
                    "health_goal_fitness": "endurance",
                    "experience_level": "intermediate",
                    "equipment": [],
                    "limitations": [],
                    "preferences": {},
                },
            ]
        )

        profiles = load_profiles_from_mongo(mongo_db, user_ids=["u1"])

        assert set(profiles) == {"u1"}

    def test_empty_user_ids_returns_empty_dict(self, mongo_db):
        profiles = load_profiles_from_mongo(mongo_db, user_ids=[])
        assert profiles == {}
