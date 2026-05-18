import pytest
import respx
import httpx
from unittest.mock import patch
from datetime import datetime, timezone

AUTH_API_URL = "http://fake-auth"
ENTITLEMENTS_URL = f"{AUTH_API_URL}/api/entitlements/me"
FAKE_JWT = "fake.jwt.token"
FAKE_USER_ID = "user-abc"


@pytest.fixture(autouse=True)
def patch_auth_url():
    """Remplace AUTH_API_URL par la valeur de test dans tous les tests."""
    with patch("app.services.entitlements_client.settings") as mock_settings:
        mock_settings.AUTH_API_URL = AUTH_API_URL
        yield mock_settings


@pytest.fixture(autouse=True)
def reset_cache():
    """Vide le cache avant chaque test pour eviter les effets de bord."""
    from app.services.entitlements_client import clear_cache
    clear_cache()
    yield
    clear_cache()


from app.services.entitlements_client import get_entitlements, Entitlements  # noqa: E402


class TestTierFree:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_free_tier(self):
        respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={"tier": "free", "expires_at": None, "features": []})
        )
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "free"
        assert result.features == []
        assert result.expires_at is None


class TestTierPremium:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_premium_tier(self):
        respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={
                "tier": "premium",
                "expires_at": "2027-01-01T00:00:00",
                "features": ["advanced_reco"],
            })
        )
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "premium"
        assert "advanced_reco" in result.features
        assert isinstance(result.expires_at, datetime)


class TestTierPremiumPlus:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_premium_plus_tier(self):
        respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={
                "tier": "premium_plus",
                "expires_at": "2027-06-01T00:00:00+00:00",
                "features": ["advanced_reco", "nutrition_ai", "custom_plans"],
            })
        )
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "premium_plus"
        assert len(result.features) == 3


class TestCache:
    @pytest.mark.asyncio
    @respx.mock
    async def test_cache_hit_does_not_call_api_twice(self):
        route = respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={"tier": "premium", "expires_at": None, "features": []})
        )
        await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert route.call_count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_cache_expired_calls_api_again(self):
        from cachetools import TTLCache
        short_cache: TTLCache = TTLCache(maxsize=10000, ttl=1)

        route = respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={"tier": "free", "expires_at": None, "features": []})
        )

        with patch("app.services.entitlements_client._cache", short_cache):
            await get_entitlements(FAKE_USER_ID, FAKE_JWT)
            # Vide manuellement le cache pour simuler l'expiration TTL
            short_cache.clear()
            await get_entitlements(FAKE_USER_ID, FAKE_JWT)

        assert route.call_count == 2


class TestDegradeTimeout:
    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_returns_free(self):
        respx.get(ENTITLEMENTS_URL).mock(side_effect=httpx.TimeoutException("timeout"))
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "free"
        assert result.features == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_does_not_raise(self):
        respx.get(ENTITLEMENTS_URL).mock(side_effect=httpx.TimeoutException("timeout"))
        try:
            await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        except Exception as exc:
            pytest.fail(f"Une exception inattendue a ete levee : {exc}")


class TestDegrademalformedResponse:
    @pytest.mark.asyncio
    @respx.mock
    async def test_missing_tier_defaults_to_free(self):
        respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={"expires_at": None, "features": []})
        )
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "free"

    @pytest.mark.asyncio
    @respx.mock
    async def test_unknown_tier_defaults_to_free(self):
        respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={"tier": "ultra_vip", "expires_at": None, "features": []})
        )
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "free"

    @pytest.mark.asyncio
    @respx.mock
    async def test_500_from_auth_returns_free(self):
        respx.get(ENTITLEMENTS_URL).mock(return_value=httpx.Response(500))
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "free"

    @pytest.mark.asyncio
    @respx.mock
    async def test_invalid_expires_at_does_not_crash(self):
        respx.get(ENTITLEMENTS_URL).mock(
            return_value=httpx.Response(200, json={
                "tier": "premium",
                "expires_at": "not-a-date",
                "features": [],
            })
        )
        result = await get_entitlements(FAKE_USER_ID, FAKE_JWT)
        assert result.tier == "premium"
        assert result.expires_at is None
