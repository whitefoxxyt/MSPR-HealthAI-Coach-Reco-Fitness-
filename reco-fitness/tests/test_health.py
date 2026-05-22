from unittest.mock import AsyncMock, patch

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_200():
    with (
        patch("app.routers.health._check_postgres", return_value=True),
        patch("app.routers.health.check_mongo", new_callable=AsyncMock, return_value=True),
        patch("app.routers.health._check_auth", new_callable=AsyncMock, return_value=True),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] == "ok"
    assert body["mongo"] == "ok"
    assert body["auth"] == "ok"
    assert "timestamp" in body


def test_health_degraded_when_db_down():
    with (
        patch("app.routers.health._check_postgres", return_value=False),
        patch("app.routers.health.check_mongo", new_callable=AsyncMock, return_value=True),
        patch("app.routers.health._check_auth", new_callable=AsyncMock, return_value=True),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["postgres"] == "unreachable"
