from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.jwt_decoder import decode, UserIdentity
from app.db.mongo import get_mongo_db
from motor.motor_asyncio import AsyncIOMotorDatabase

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UserIdentity:
    """
    Dependency FastAPI : extrait et valide le JWT Bearer.
    Retourne l'identite de l'utilisateur ou leve 401.
    """
    return decode(credentials.credentials)


def get_db() -> AsyncIOMotorDatabase:
    """Dependency FastAPI : fournit la base MongoDB."""
    return get_mongo_db()
