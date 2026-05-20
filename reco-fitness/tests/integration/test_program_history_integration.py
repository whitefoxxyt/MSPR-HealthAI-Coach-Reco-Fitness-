"""
Tests d'integration de GET /api/v1/programs/me et GET /api/v1/feedback/me (RF-13).
Necessite Docker (testcontainers MongoDB).
"""
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt

TEST_SECRET = "test_better_auth_secret_for_ci"


def _make_jwt(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "email": "test@example.com", "exp": int(time.time()) + 3600},
        TEST_SECRET,
        algorithm="HS256",
    )


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_jwt(user_id)}"}


def _make_program_doc(user_id: str, created_at: datetime | None = None) -> dict:
    return {
        "program_id": str(uuid4()),
        "user_id": user_id,
        "duration_weeks": 2,
        "scoring_strategy": "rule_based",
        "tier_at_generation": "free",
        "intensity_modifier": 1.0,
        "weeks": [],
        "created_at": created_at or datetime.now(timezone.utc),
    }


def _make_feedback_doc(user_id: str, created_at: datetime | None = None) -> dict:
    return {
        "program_id": str(uuid4()),
        "user_id": user_id,
        "feedback_score": 4,
        "created_at": created_at or datetime.now(timezone.utc),
    }


@pytest.fixture(scope="module")
def mongo_test_db():
    try:
        from testcontainers.mongodb import MongoDbContainer
        with MongoDbContainer("mongo:7-jammy") as mongo:
            yield mongo.get_connection_url()
    except Exception:
        pytest.skip("Docker non disponible -- tests d'integration ignores")


@pytest.fixture()
def client(mongo_test_db):
    """Client FastAPI avec Mongo override + JWT secret mock."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import MongoClient

    from app.dependencies import get_db
    from app.main import app

    test_motor_client = AsyncIOMotorClient(mongo_test_db)
    test_db = test_motor_client["reco_fitness_test"]
    sync_client = MongoClient(mongo_test_db)
    sync_db = sync_client["reco_fitness_test"]

    app.dependency_overrides[get_db] = lambda: test_db

    with patch("app.services.jwt_decoder.settings") as mock_jwt_settings:
        mock_jwt_settings.BETTER_AUTH_SECRET = TEST_SECRET
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, sync_db

    app.dependency_overrides.clear()
    sync_db["workout_programs"].drop()
    sync_db["recommendation_history"].drop()
    sync_client.close()
    test_motor_client.close()


@pytest.mark.integration
class TestGetProgramsMe:
    def test_returns_only_users_own_programs(self, client):
        c, sync_db = client
        user_a = "u-programs-A"
        user_b = "u-programs-B"
        sync_db["workout_programs"].insert_many(
            [_make_program_doc(user_a) for _ in range(5)]
            + [_make_program_doc(user_b) for _ in range(3)]
        )

        response = c.get("/api/v1/programs/me", headers=_auth(user_a))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5
        assert all(item["user_id"] == user_a for item in body["items"])


@pytest.mark.integration
class TestGetFeedbackMe:
    def test_returns_only_users_own_feedback(self, client):
        c, sync_db = client
        user_a = "u-feedback-A"
        user_b = "u-feedback-B"
        sync_db["recommendation_history"].insert_many(
            [_make_feedback_doc(user_a) for _ in range(5)]
            + [_make_feedback_doc(user_b) for _ in range(3)]
        )

        response = c.get("/api/v1/feedback/me", headers=_auth(user_a))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5
        assert all(item["user_id"] == user_a for item in body["items"])


@pytest.mark.integration
class TestSort:
    def test_programs_sorted_by_created_at_desc(self, client):
        c, sync_db = client
        user_id = "u-sort-programs"
        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        # Insertion volontairement dans le desordre par rapport au tri attendu.
        sync_db["workout_programs"].insert_many(
            [
                _make_program_doc(user_id, created_at=base + timedelta(days=1)),
                _make_program_doc(user_id, created_at=base + timedelta(days=3)),
                _make_program_doc(user_id, created_at=base + timedelta(days=2)),
            ]
        )

        response = c.get("/api/v1/programs/me", headers=_auth(user_id))

        assert response.status_code == 200, response.text
        items = response.json()["items"]
        timestamps = [item["created_at"] for item in items]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_feedback_sorted_by_created_at_desc(self, client):
        c, sync_db = client
        user_id = "u-sort-feedback"
        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        sync_db["recommendation_history"].insert_many(
            [
                _make_feedback_doc(user_id, created_at=base + timedelta(days=1)),
                _make_feedback_doc(user_id, created_at=base + timedelta(days=3)),
                _make_feedback_doc(user_id, created_at=base + timedelta(days=2)),
            ]
        )

        response = c.get("/api/v1/feedback/me", headers=_auth(user_id))

        assert response.status_code == 200, response.text
        items = response.json()["items"]
        timestamps = [item["created_at"] for item in items]
        assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.integration
class TestPaginationShape:
    def test_programs_pagination_returns_correct_window(self, client):
        c, sync_db = client
        user_id = "u-paginate"
        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        # 7 documents, espaces d'un jour, du plus ancien au plus recent.
        sync_db["workout_programs"].insert_many(
            [
                _make_program_doc(user_id, created_at=base + timedelta(days=i))
                for i in range(7)
            ]
        )

        response = c.get(
            "/api/v1/programs/me",
            headers=_auth(user_id),
            params={"limit": 3, "offset": 2},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 7
        assert body["limit"] == 3
        assert body["offset"] == 2
        assert len(body["items"]) == 3


@pytest.mark.integration
class TestPaginationDefaults:
    def test_default_limit_is_20_and_caps_items(self, client):
        c, sync_db = client
        user_id = "u-default-limit"
        # 25 documents -- doit etre tronque a 20 par defaut.
        sync_db["workout_programs"].insert_many(
            [_make_program_doc(user_id) for _ in range(25)]
        )

        response = c.get("/api/v1/programs/me", headers=_auth(user_id))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert body["total"] == 25
        assert len(body["items"]) == 20


@pytest.mark.integration
class TestPaginationValidation:
    @pytest.mark.parametrize(
        "path", ["/api/v1/programs/me", "/api/v1/feedback/me"]
    )
    @pytest.mark.parametrize(
        "params",
        [
            {"limit": -1},
            {"limit": 0},
            {"limit": 101},
            {"offset": -1},
        ],
    )
    def test_invalid_pagination_returns_422(self, client, path, params):
        c, _ = client
        response = c.get(path, headers=_auth("u-validate"), params=params)
        assert response.status_code == 422, response.text
