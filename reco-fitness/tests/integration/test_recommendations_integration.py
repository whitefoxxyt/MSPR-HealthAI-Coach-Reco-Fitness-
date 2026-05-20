"""
Tests d'integration de POST /api/v1/recommendations (RF-10).
Necessite Docker (testcontainers MongoDB).
"""
import time
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from jose import jwt

TEST_SECRET = "test_better_auth_secret_for_ci"
TEST_AUTH_URL = "https://fake-mspr-auth"
ENTITLEMENTS_URL = f"{TEST_AUTH_URL}/api/entitlements/me"


def _make_jwt(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "email": "test@example.com", "exp": int(time.time()) + 3600},
        TEST_SECRET,
        algorithm="HS256",
    )


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_jwt(user_id)}"}


PROFILE_DOC = {
    "health_goal_fitness": "fat_loss",
    "experience_level": "beginner",
    "equipment": ["dumbbells"],
    "limitations": [],
    "preferences": {"duration_min_per_session": 45, "sessions_per_week": 3},
}


def _make_fake_catalog():
    """Catalogue d'exercices retourne par l'override de exercise_catalog.get_all."""
    from app.services.exercise_catalog import Exercise

    return [
        Exercise(
            id=i,
            name=f"ex-{i}",
            category="cardio",
            difficulty="beginner",
            equipment=["none"],
            target_muscles=["abs"],
        )
        for i in range(1, 41)
    ]


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
    """Client FastAPI avec Mongo override + auth secret mock + exercise_catalog mock."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import MongoClient

    from app.db.session import get_db as get_pg_db
    from app.dependencies import get_db
    from app.main import app
    from app.services import exercise_catalog

    test_motor_client = AsyncIOMotorClient(mongo_test_db)
    test_db = test_motor_client["reco_fitness_test"]
    sync_client = MongoClient(mongo_test_db)
    sync_db = sync_client["reco_fitness_test"]

    fake_catalog = _make_fake_catalog()

    def _fake_pg_session():
        # exercise_catalog.get_all est mocke -> la session PG n'est jamais touchee.
        yield None

    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_pg_db] = _fake_pg_session

    with (
        patch("app.services.jwt_decoder.settings") as mock_jwt_settings,
        patch.object(exercise_catalog, "get_all", return_value=fake_catalog),
        patch(
            "app.services.workout_program_orchestrator.score_ml",
            lambda exercise, profile: max(0.0, 1.0 - exercise.id * 0.001),
        ),
    ):
        mock_jwt_settings.BETTER_AUTH_SECRET = TEST_SECRET
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, sync_db

    app.dependency_overrides.clear()
    sync_db["user_fitness_profiles"].drop()
    sync_db["workout_programs"].drop()
    sync_client.close()
    test_motor_client.close()


@pytest.fixture()
def mock_auth_free():
    """Mock l'endpoint MSPR-AUTH pour retourner tier=free."""
    with respx.mock(base_url=TEST_AUTH_URL, assert_all_called=False) as router:
        router.get("/api/entitlements/me").mock(
            return_value=httpx.Response(
                200,
                json={"tier": "free", "expires_at": None, "features": []},
            )
        )
        with patch("app.services.entitlements_client.settings") as mock_settings:
            mock_settings.AUTH_API_URL = TEST_AUTH_URL
            from app.services.entitlements_client import clear_cache
            clear_cache()
            yield router


def _seed_profile(sync_db, user_id: str):
    """Insere directement le profil en Mongo (sync via pymongo)."""
    sync_db["user_fitness_profiles"].insert_one({
        "user_id": user_id,
        **PROFILE_DOC,
        "updated_at": datetime.now(timezone.utc),
    })


@pytest.fixture()
def mock_auth_tier():
    """Factory : configure respx pour repondre tier=X pour MSPR-AUTH."""
    def _make(tier: str):
        router = respx.mock(base_url=TEST_AUTH_URL, assert_all_called=False)
        router.start()
        router.get("/api/entitlements/me").mock(
            return_value=httpx.Response(
                200,
                json={"tier": tier, "expires_at": None, "features": []},
            )
        )
        return router

    settings_patcher = patch("app.services.entitlements_client.settings")
    mock_settings = settings_patcher.start()
    mock_settings.AUTH_API_URL = TEST_AUTH_URL
    from app.services.entitlements_client import clear_cache
    clear_cache()

    routers: list = []
    def factory(tier: str):
        r = _make(tier)
        routers.append(r)
        return r

    yield factory

    for r in routers:
        r.stop()
    settings_patcher.stop()
    clear_cache()


@pytest.mark.integration
class TestPostRecommendationsFree:
    def test_returns_program_for_free_tier(self, client, mock_auth_free):
        c, test_db = client
        user_id = "u-free-1"
        _seed_profile(test_db, user_id)

        response = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["duration_weeks"] == 2
        assert body["scoring_strategy"] == "rule_based"
        assert body["tier_at_generation"] == "free"
        assert "program_id" in body
        assert "weeks" in body
        assert len(body["weeks"]) == 2

    def test_persists_program_in_mongodb_with_tier_and_strategy(self, client, mock_auth_free):
        c, test_db = client
        user_id = "u-persist-1"
        _seed_profile(test_db, user_id)

        response = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))
        assert response.status_code == 200

        # Verifie la presence du document avec champs attendus
        docs = list(test_db["workout_programs"].find({"user_id": user_id}))
        assert len(docs) == 1
        doc = docs[0]
        assert doc["tier_at_generation"] == "free"
        assert doc["scoring_strategy"] == "rule_based"
        assert doc["duration_weeks"] == 2
        assert doc["program_id"] == response.json()["program_id"]


@pytest.mark.integration
class TestPostRecommendationsPremium:
    def test_returns_program_for_premium_tier(self, client, mock_auth_tier):
        mock_auth_tier("premium")
        c, test_db = client
        user_id = "u-premium-1"
        _seed_profile(test_db, user_id)

        response = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tier_at_generation"] == "premium"
        assert body["scoring_strategy"] == "hybrid_rank_fusion"
        # fat_loss -> mapping premium duration_weeks=4
        assert body["duration_weeks"] == 4
        assert len(body["weeks"]) == 4

    def test_premium_plus_high_avg_heart_rate_reduces_sessions(self, client, mock_auth_tier):
        from datetime import datetime, timezone

        from app.services.biometric_reader import Biometric

        mock_auth_tier("premium_plus")
        c, test_db = client
        # user_id numerique pour que la conversion str->int dans le router fonctionne.
        user_id = "42"
        _seed_profile(test_db, user_id)

        fake_biometric = Biometric(
            user_id=42,
            avg_heart_rate_bpm=90,
            weight_kg=72.5,
            experience_level="intermediate",
            measured_at=datetime.now(timezone.utc),
        )

        with patch(
            "app.routers.recommendations.biometric_reader.get_recent",
            return_value=fake_biometric,
        ) as reader_mock:
            response = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tier_at_generation"] == "premium_plus"
        assert body["scoring_strategy"] == "hybrid_rank_fusion"
        # PROFILE_DOC.health_goal_fitness=fat_loss -> 4 seances/sem nominal
        # avg_heart_rate_bpm=90 (>80) -> -1 seance -> 3 seances/sem
        for week in body["weeks"]:
            assert len(week) == 3
        reader_mock.assert_called_once()

    def test_premium_plus_without_biometric_keeps_base_sessions(self, client, mock_auth_tier):
        mock_auth_tier("premium_plus")
        c, test_db = client
        user_id = "43"
        _seed_profile(test_db, user_id)

        # get_recent retourne None -> comportement nominal de premium.
        with patch(
            "app.routers.recommendations.biometric_reader.get_recent",
            return_value=None,
        ):
            response = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tier_at_generation"] == "premium_plus"
        # fat_loss premium duration_weeks=4, 4 seances/sem nominales
        for week in body["weeks"]:
            assert len(week) == 4


@pytest.mark.integration
class TestPostRecommendationsRateLimit:
    def test_returns_429_when_exceeding_per_minute_limit(self, client, mock_auth_free):
        """
        Le PRD impose 10/heure ET 3/minute. La limite minute se declenche en premier,
        validant la mecanique : 4eme appel rapide depuis le meme user_id -> 429.
        """
        c, test_db = client
        user_id = "u-ratelimit-1"
        _seed_profile(test_db, user_id)

        for _ in range(3):
            response = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))
            assert response.status_code == 200, response.text

        fourth = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))
        assert fourth.status_code == 429
        assert "rate limit" in fourth.text.lower() or "rate" in fourth.text.lower()

    def test_returns_429_when_exceeding_per_hour_limit(self, client, mock_auth_free):
        """11eme appel dans l'heure -> 429 (bucket minute reset pour isoler le bucket heure)."""
        c, test_db = client
        user_id = "u-ratelimit-2"
        _seed_profile(test_db, user_id)

        # Pour isoler la limite 10/heure, on retire temporairement la limite minute
        # en monkeypatchant la decoration du endpoint.
        from app.routers import recommendations as reco_router

        # Reset les compteurs en ecrasant le storage du limiter
        reco_router.limiter._storage.storage.clear() if hasattr(
            reco_router.limiter._storage, "storage"
        ) else None

        with patch.object(
            reco_router.limiter, "enabled", True
        ):
            # Patch la decoration pour ne garder que 10/hour
            for i in range(10):
                # Petit hack : attendre 21 secondes entre chaque rafale de 3 serait
                # trop lent. Au lieu, on simule la fenetre en clearant le compteur "minute".
                response = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))
                assert response.status_code == 200, f"appel {i + 1} : {response.text}"
                # Reset uniquement le bucket minute, garde le bucket heure
                storage = reco_router.limiter._storage
                if hasattr(storage, "storage"):
                    keys_to_drop = [k for k in storage.storage if "minute" in k]
                    for k in keys_to_drop:
                        del storage.storage[k]

            eleventh = c.post("/api/v1/recommendations", json={}, headers=_auth(user_id))
            assert eleventh.status_code == 429, f"11eme appel : {eleventh.text}"
