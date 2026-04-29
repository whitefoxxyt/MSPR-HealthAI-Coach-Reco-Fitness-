from dataclasses import dataclass
from jose import jwt, JWTError, ExpiredSignatureError
from fastapi import HTTPException, status
from app.config import settings

ALGORITHM = "HS256"


@dataclass
class UserIdentity:
    user_id: str
    email: str | None


def decode(token: str) -> UserIdentity:
    """
    Valide la signature, verifie l'expiration, retourne l'identite.
    Leve HTTPException 401 si invalide ou expire.
    """
    try:
        payload = jwt.decode(
            token,
            settings.BETTER_AUTH_SECRET,
            algorithms=[ALGORITHM],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expire.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Claim 'sub' manquant dans le token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserIdentity(
        user_id=user_id,
        email=payload.get("email"),
    )
