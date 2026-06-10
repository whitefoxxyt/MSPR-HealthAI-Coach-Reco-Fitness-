"""
Tests d'integration de PUT /api/v1/programs/{program_id}/feedback (RF-12).
Necessite Docker (testcontainers MongoDB).
"""
import time
from datetime import datetime, timezone
from unittest.mock import patch

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


PROGRAM_DOC = {
    "duration_weeks": 4,
    "scoring_strategy": "hybrid_rank_fusion",
    "tier_at_generation": "premium",
    "weeks": [],
    "created_at": datetime.now(timezone.utc),
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

    test_motor_client = AsyncIOMotorClient(mongo_test_db, tz_aware=True)
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


def _seed_program(sync_db, program_id: str, user_id: str):
    """Insere directement un programme en Mongo pour les tests."""
    sync_db["workout_programs"].insert_one({
        "program_id": program_id,
        "user_id": user_id,
        **PROGRAM_DOC,
    })


@pytest.mark.integration
class TestPutFeedback:
    def test_owner_can_record_feedback(self, client):
        c, sync_db = client
        user_id = "u-feedback-1"
        program_id = "prog-feedback-1"
        _seed_program(sync_db, program_id, user_id)

        response = c.put(
            f"/api/v1/programs/{program_id}/feedback",
            json={
                "score": 4,
                "completed": True,
                "comment": "Bon programme",
                "exercise_id": 123,
            },
            headers=_auth(user_id),
        )

        assert response.status_code == 200, response.text

        docs = list(sync_db["recommendation_history"].find({"user_id": user_id}))
        assert len(docs) == 1
        doc = docs[0]
        assert doc["program_id"] == program_id
        assert doc["feedback_score"] == 4
        assert doc["completed"] is True
        assert doc["comment"] == "Bon programme"
        assert doc["exercise_id"] == 123
        assert "created_at" in doc

    def test_other_user_cannot_record_feedback_on_someone_elses_program(self, client):
        c, sync_db = client
        owner = "u-owner-2"
        intruder = "u-intruder-2"
        program_id = "prog-foreign-2"
        _seed_program(sync_db, program_id, owner)

        response = c.put(
            f"/api/v1/programs/{program_id}/feedback",
            json={"score": 5, "completed": False},
            headers=_auth(intruder),
        )

        assert response.status_code == 403, response.text
        assert sync_db["recommendation_history"].count_documents({"program_id": program_id}) == 0

    def test_unknown_program_returns_404(self, client):
        c, sync_db = client
        user_id = "u-unknown-3"
        # No _seed_program -- program_id does not exist in DB.

        response = c.put(
            "/api/v1/programs/does-not-exist/feedback",
            json={"score": 3, "completed": True},
            headers=_auth(user_id),
        )

        assert response.status_code == 404, response.text
        assert sync_db["recommendation_history"].count_documents({"user_id": user_id}) == 0

    def test_program_level_feedback_stores_exercise_id_as_none(self, client):
        c, sync_db = client
        user_id = "u-prog-level-5"
        program_id = "prog-level-5"
        _seed_program(sync_db, program_id, user_id)

        response = c.put(
            f"/api/v1/programs/{program_id}/feedback",
            json={"score": 5, "completed": True},
            headers=_auth(user_id),
        )

        assert response.status_code == 200, response.text
        doc = sync_db["recommendation_history"].find_one({"program_id": program_id})
        assert doc is not None
        assert doc["exercise_id"] is None
        assert doc["comment"] is None

    @pytest.mark.parametrize("invalid_score", [0, 6, -1, 10])
    def test_out_of_range_score_returns_422(self, client, invalid_score):
        c, sync_db = client
        user_id = "u-validate-4"
        program_id = "prog-validate-4"
        _seed_program(sync_db, program_id, user_id)

        response = c.put(
            f"/api/v1/programs/{program_id}/feedback",
            json={"score": invalid_score, "completed": True},
            headers=_auth(user_id),
        )

        assert response.status_code == 422, response.text
        assert sync_db["recommendation_history"].count_documents({"program_id": program_id}) == 0

    def test_unauthenticated_request_returns_401_or_403(self, client):
        c, sync_db = client
        program_id = "prog-no-auth-6"
        _seed_program(sync_db, program_id, "u-some-owner")

        response = c.put(
            f"/api/v1/programs/{program_id}/feedback",
            json={"score": 3, "completed": True},
        )

        assert response.status_code in (401, 403)
        assert sync_db["recommendation_history"].count_documents({"program_id": program_id}) == 0

    def test_put_is_idempotent_upserts_on_user_program_exercise(self, client):
        c, sync_db = client
        user_id = "u-upsert-7"
        program_id = "prog-upsert-7"
        _seed_program(sync_db, program_id, user_id)

        first = c.put(
            f"/api/v1/programs/{program_id}/feedback",
            json={"score": 3, "completed": False, "comment": "premier"},
            headers=_auth(user_id),
        )
        assert first.status_code == 200, first.text
        first_created_at = first.json()["created_at"]

        second = c.put(
            f"/api/v1/programs/{program_id}/feedback",
            json={"score": 5, "completed": True, "comment": "mis a jour"},
            headers=_auth(user_id),
        )
        assert second.status_code == 200, second.text

        docs = list(sync_db["recommendation_history"].find({"user_id": user_id}))
        assert len(docs) == 1, "PUT idempotent : un seul doc par (user, program, exercise)"
        assert docs[0]["feedback_score"] == 5
        assert docs[0]["completed"] is True
        assert docs[0]["comment"] == "mis a jour"
        # created_at preserve la valeur du premier insert
        assert second.json()["created_at"] == first_created_at
