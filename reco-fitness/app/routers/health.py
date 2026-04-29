from datetime import datetime, timezone
import httpx
from fastapi import APIRouter
from app.db.postgres import check_postgres
from app.db.mongo import check_mongo
from app.config import settings


router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check", response_description="Statut des services")
async def health_check():
    """
    Verifie la disponibilite de PostgreSQL, MongoDB et du service MSPR-AUTH.
    Retourne un statut global ainsi que le detail de chaque dependance.
    """
    postgres_ok = check_postgres()
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
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.AUTH_API_URL}/health")
            return response.status_code == 200
    except Exception:
        return False
