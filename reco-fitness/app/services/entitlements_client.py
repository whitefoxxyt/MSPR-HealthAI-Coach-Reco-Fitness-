from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
import httpx
from cachetools import TTLCache
from app.config import settings

_cache: TTLCache = TTLCache(maxsize=10000, ttl=60)

ENTITLEMENTS_PATH = "/api/entitlements/me"
TIMEOUT_SECONDS = 3.0
DEFAULT_TIER: Literal["free", "premium", "premium_plus"] = "free"


@dataclass
class Entitlements:
    tier: Literal["free", "premium", "premium_plus"]
    expires_at: datetime | None
    features: list[str] = field(default_factory=list)


def _default_entitlements() -> Entitlements:
    """Retourne les droits minimaux utilises en mode degrade."""
    return Entitlements(tier=DEFAULT_TIER, expires_at=None, features=[])


def _parse_entitlements(data: dict) -> Entitlements:
    """Parse la reponse JSON de MSPR-AUTH en Entitlements."""
    tier = data.get("tier", DEFAULT_TIER)
    if tier not in ("free", "premium", "premium_plus"):
        tier = DEFAULT_TIER

    raw_expires = data.get("expires_at")
    expires_at: datetime | None = None
    if isinstance(raw_expires, str):
        try:
            expires_at = datetime.fromisoformat(raw_expires)
        except ValueError:
            expires_at = None

    features: list[str] = data.get("features") or []
    if not isinstance(features, list):
        features = []

    return Entitlements(tier=tier, expires_at=expires_at, features=features)


async def get_entitlements(user_id: str, jwt: str) -> Entitlements:
    """
    Retourne les droits de l'utilisateur en appelant MSPR-AUTH.
    Resultat mis en cache TTL 60s par user_id.
    En cas de timeout ou d'erreur, retourne tier='free' sans lever d'exception.
    """
    cached = _cache.get(user_id)
    if cached is not None:
        return cached

    url = f"{settings.AUTH_API_URL}{ENTITLEMENTS_PATH}"
    headers = {"Authorization": f"Bearer {jwt}"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            entitlements = _parse_entitlements(data)
    except Exception:
        return _default_entitlements()

    _cache[user_id] = entitlements
    return entitlements


def clear_cache() -> None:
    """Vide le cache -- utile pour les tests."""
    _cache.clear()
