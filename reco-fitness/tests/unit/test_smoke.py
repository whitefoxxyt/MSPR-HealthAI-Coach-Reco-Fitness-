"""Smoke test unitaire -- verifie que les imports et fixtures de base fonctionnent."""
import time

import pytest
from jose import jwt

TEST_SECRET = "test_better_auth_secret_for_ci"


@pytest.mark.unit
def test_valid_jwt_fixture_produces_decodable_token(valid_jwt):
    token = valid_jwt(user_id="u-1", email="smoke@test.com")
    payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
    assert payload["sub"] == "u-1"
    assert payload["email"] == "smoke@test.com"
    assert payload["exp"] > int(time.time())


@pytest.mark.unit
def test_valid_jwt_fixture_default_values(valid_jwt):
    token = valid_jwt()
    payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
    assert payload["sub"] == "test-user-1"


@pytest.mark.unit
async def test_mock_auth_fixture_returns_free_tier_by_default(mock_auth):
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get("https://fake-mspr-auth/api/entitlements/me")
    assert response.status_code == 200
    assert response.json()["tier"] == "free"
