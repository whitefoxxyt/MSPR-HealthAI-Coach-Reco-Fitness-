from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.services.jwt_decoder import UserIdentity, decode

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
