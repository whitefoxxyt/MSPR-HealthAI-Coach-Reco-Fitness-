"""
Lecture des biometriques recentes d'un utilisateur (RF-11, tier premium_plus).

Lit la table PostgreSQL `biometric_entries` en read-only pour fournir a
l'orchestrateur les biometriques recentes d'un utilisateur. Si aucune donnee
n'est disponible, retourne `None` -- le tier premium_plus se replie alors
sur le comportement premium nominal.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.biometric import BiometricEntryORM


class Biometric(BaseModel):
    """Biometrique recente d'un utilisateur (snapshot lu depuis biometric_entries)."""

    user_id: int
    weight_kg: float | None = None
    avg_heart_rate_bpm: int | None = None
    experience_level: str | None = None
    measured_at: datetime


def get_recent(user_id: int, db: Session, days: int = 30) -> Biometric | None:
    """Retourne la biometrique la plus recente du user dans la fenetre `days`, ou None."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    row = (
        db.query(BiometricEntryORM)
        .filter(
            BiometricEntryORM.user_id == user_id,
            BiometricEntryORM.measured_at >= cutoff,
        )
        .order_by(BiometricEntryORM.measured_at.desc())
        .first()
    )
    if row is None:
        return None
    return Biometric(
        user_id=row.user_id,
        weight_kg=row.weight_kg,
        avg_heart_rate_bpm=row.avg_heart_rate_bpm,
        experience_level=row.experience_level,
        measured_at=row.measured_at,
    )
