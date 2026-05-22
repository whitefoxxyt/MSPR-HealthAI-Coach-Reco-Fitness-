from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.mongo import check_mongo
from app.db.session import engine

router = APIRouter(tags=["Sante"])


def _check_postgres() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health", summary="Health check du service")
async def health_check():
    """
    Verifie la disponibilite des trois dependances : PostgreSQL (catalogue),
    MongoDB (profils + programmes), MSPR-AUTH (entitlements).

    Toujours 200 (jamais 503) pour ne pas casser les orchestrateurs : le champ
    `status` vaut `ok` si tout repond, `degraded` si au moins une dependance est
    injoignable. Cible des sondes liveness/readiness Kubernetes.
    """
    postgres_ok = _check_postgres()
    mongo_ok = await check_mongo()
    auth_ok = await _check_auth()
    all_ok = postgres_ok and mongo_ok and auth_ok
    return {
        "status": "ok" if all_ok else "degraded",
        "postgres": "ok" if postgres_ok else "unreachable",
        "mongo": "ok" if mongo_ok else "unreachable",
        "auth": "ok" if auth_ok else "unreachable",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _check_auth() -> bool:
    # MSPR-AUTH (better-auth) expose /api/auth/ok comme sonde de disponibilite,
    # pas /health. Cf. issue de healthcheck Reco-Fitness post-integration MSPR2.
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.AUTH_API_URL}/api/auth/ok")
            return response.status_code == 200
    except Exception:
        return False
