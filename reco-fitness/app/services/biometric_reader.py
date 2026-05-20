"""
Lecture des biometriques recentes d'un utilisateur (RF-10, tier premium_plus).

Stub : la lecture reelle (PostgreSQL biometric_entries ou Mongo) sera branchee
dans une issue ulterieure. Pour l'instant retourne None par defaut, ce qui
fait degrader proprement le tier premium_plus vers le comportement premium.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase


@dataclass
class Biometrics:
    heart_rate_rest: int | None
    bmi: float | None
    body_fat_pct: float | None
    recorded_at: datetime


async def get_recent_biometrics(
    user_id: str,
    db: AsyncIOMotorDatabase,
) -> Biometrics | None:
    """Retourne les biometriques recentes du user, ou None si indisponible."""
    return None
