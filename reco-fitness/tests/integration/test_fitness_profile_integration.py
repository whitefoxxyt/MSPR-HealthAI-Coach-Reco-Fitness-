"""
Tests d'integration du fitness profile : PUT/GET sur un vrai MongoDB ephemere.
Necessite Docker (testcontainers).
"""
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

TEST_SECRET = "test_better_auth_secret_for_ci"


def _make_jwt(user_id: str, email: str = "test@example.com") -> str:
    return jwt.encode(
        {"sub": user_id, "email": email, "exp": int(time.time()) + 3600},
        TEST_SECRET,
        algorithm="HS256",
    )


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_jwt(user_id)}"}


VALID_PAYLOAD = {
    "health_goal_fitness": "fat_loss",
    "experience_level": "beginner",
    "equipment": ["dumbbells", "barbell"],
    "limitations": ["knee_injury"],
    "preferences": {"duration_min_per_session": 45, "sessions_per_week": 3},
}


@pytest.fixture(scope="module")
def mongo_test_db():
    """Container MongoDB ephemere partage pour tous les tests du module."""
    try:
        from testcontainers.mongodb import MongoDbContainer
        with MongoDbContainer("mongo:7-jammy") as mongo:
            yield mongo.get_connection_url()
    except Exception:
        pytest.skip("Docker non disponible -- tests d'integration ignores")


@pytest.fixture()
def client(mongo_test_db):
    """Client FastAPI avec MongoDB pointe vers le container de test."""
    from motor.motor_asyncio import AsyncIOMotorClient

    from app.main import app

    test_motor_client = AsyncIOMotorClient(mongo_test_db)
    test_db = test_motor_client["reco_fitness_test"]

    with (
        patch("app.dependencies.get_db", return_value=test_db),
        patch("app.services.jwt_decoder.settings") as mock_settings,
    ):
        mock_settings.BETTER_AUTH_SECRET = TEST_SECRET
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    # Nettoyage apres chaque test
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        test_db["user_fitness_profiles"].drop()
    )
    test_motor_client.close()


@pytest.mark.integration
class TestFitnessProfileCRUD:
    def test_get_profile_returns_404_when_no_profile(self, client):
        response = client.get("/api/v1/fitness-profile/me", headers=_auth("u-new"))
        assert response.status_code == 404

    def test_put_creates_profile(self, client):
        response = client.put(
            "/api/v1/fitness-profile/me",
            json=VALID_PAYLOAD,
            headers=_auth("u-create"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "u-create"
        assert data["health_goal_fitness"] == "fat_loss"
        assert data["experience_level"] == "beginner"
        assert "updated_at" in data

    def test_get_returns_profile_after_put(self, client):
        user_id = "u-get-after-put"
        client.put("/api/v1/fitness-profile/me", json=VALID_PAYLOAD, headers=_auth(user_id))
        response = client.get("/api/v1/fitness-profile/me", headers=_auth(user_id))
        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_second_put_updates_profile(self, client):
        user_id = "u-update"
        client.put("/api/v1/fitness-profile/me", json=VALID_PAYLOAD, headers=_auth(user_id))
        updated = {**VALID_PAYLOAD, "health_goal_fitness": "endurance", "experience_level": "advanced"}
        response = client.put("/api/v1/fitness-profile/me", json=updated, headers=_auth(user_id))
        assert response.status_code == 200
        data = response.json()
        assert data["health_goal_fitness"] == "endurance"
        assert data["experience_level"] == "advanced"

    def test_user_cannot_read_another_users_profile(self, client):
        user_a = "u-owner"
        user_b = "u-intruder"
        client.put("/api/v1/fitness-profile/me", json=VALID_PAYLOAD, headers=_auth(user_a))
        # user_b demande /me avec son propre JWT -- il ne voit que son propre profil
        response = client.get("/api/v1/fitness-profile/me", headers=_auth(user_b))
        assert response.status_code == 404

    def test_user_cannot_modify_another_users_profile(self, client):
        user_a = "u-target"
        user_b = "u-attacker"
        client.put("/api/v1/fitness-profile/me", json=VALID_PAYLOAD, headers=_auth(user_a))
        # user_b fait un PUT sur /me -- il ne peut modifier que le sien
        response = client.put("/api/v1/fitness-profile/me", json=VALID_PAYLOAD, headers=_auth(user_b))
        assert response.status_code == 200
        assert response.json()["user_id"] == user_b

        # Le profil de user_a est intact
        get_a = client.get("/api/v1/fitness-profile/me", headers=_auth(user_a))
        assert get_a.json()["user_id"] == user_a


@pytest.mark.integration
class TestFitnessProfileValidation:
    def test_invalid_goal_returns_422(self, client):
        bad_payload = {**VALID_PAYLOAD, "health_goal_fitness": "invalid_goal"}
        response = client.put(
            "/api/v1/fitness-profile/me",
            json=bad_payload,
            headers=_auth("u-validate"),
        )
        assert response.status_code == 422

    def test_invalid_level_returns_422(self, client):
        bad_payload = {**VALID_PAYLOAD, "experience_level": "expert"}
        response = client.put(
            "/api/v1/fitness-profile/me",
            json=bad_payload,
            headers=_auth("u-validate"),
        )
        assert response.status_code == 422

    def test_unauthenticated_request_returns_401_or_403(self, client):
        response = client.get("/api/v1/fitness-profile/me")
        assert response.status_code in (401, 403)
