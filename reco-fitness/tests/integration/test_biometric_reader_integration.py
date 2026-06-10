"""Tests d'integration pour app/services/biometric_reader.py (RF-11).

Demarre un PostgreSQL ephemere via testcontainers (Docker requis) et verifie
que `get_recent` lit correctement la table `biometric_entries`.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.biometric import BiometricEntryORM
from app.services.biometric_reader import Biometric, get_recent

# Dates relatives a maintenant : des dates calendaires en dur finissent par
# sortir de la fenetre de recence de get_recent (30 j) et font echouer la
# suite avec le temps.
_NOW = datetime.now(timezone.utc)


def _insert_biometric(db, **kwargs) -> BiometricEntryORM:
    defaults = {
        "user_id": 1,
        "weight_kg": 72.0,
        "avg_heart_rate_bpm": 65,
        "experience_level": "intermediate",
        "measured_at": _NOW - timedelta(days=10),
    }
    defaults.update(kwargs)
    row = BiometricEntryORM(**defaults)
    db.add(row)
    db.flush()
    return row


@pytest.mark.integration
class TestGetRecentNoRows:
    def test_returns_none_when_user_has_no_biometrics(self, db_session):
        result = get_recent(user_id=999, db=db_session)
        assert result is None


@pytest.mark.integration
class TestGetRecentReturnsMostRecent:
    def test_returns_latest_among_three_entries(self, db_session):
        user_id = 1
        latest = _NOW - timedelta(days=2)
        _insert_biometric(
            db_session,
            user_id=user_id,
            weight_kg=70.0,
            avg_heart_rate_bpm=60,
            measured_at=_NOW - timedelta(days=15),
        )
        _insert_biometric(
            db_session,
            user_id=user_id,
            weight_kg=71.0,
            avg_heart_rate_bpm=62,
            measured_at=_NOW - timedelta(days=10),
        )
        # La plus recente : on doit la retrouver
        _insert_biometric(
            db_session,
            user_id=user_id,
            weight_kg=72.5,
            avg_heart_rate_bpm=68,
            experience_level="advanced",
            measured_at=latest,
        )

        result = get_recent(user_id=user_id, db=db_session)

        assert result is not None
        assert isinstance(result, Biometric)
        assert result.user_id == user_id
        assert result.weight_kg == pytest.approx(72.5)
        assert result.avg_heart_rate_bpm == 68
        assert result.experience_level == "advanced"
        assert result.measured_at == latest

    def test_ignores_other_users(self, db_session):
        _insert_biometric(
            db_session, user_id=1, measured_at=_NOW - timedelta(days=3)
        )
        _insert_biometric(
            db_session, user_id=2, measured_at=_NOW - timedelta(days=2)
        )

        result = get_recent(user_id=1, db=db_session)

        assert result is not None
        assert result.user_id == 1


@pytest.mark.integration
class TestGetRecentDaysWindow:
    def test_excludes_entries_older_than_days_window(self, db_session):
        now = datetime.now(timezone.utc)
        # Une biometrique trop ancienne (50 jours en arriere, hors fenetre de 30j)
        _insert_biometric(
            db_session,
            user_id=1,
            measured_at=now - timedelta(days=50),
        )

        result = get_recent(user_id=1, db=db_session, days=30)

        assert result is None

    def test_returns_entry_within_days_window(self, db_session):
        now = datetime.now(timezone.utc)
        # Une recente (5 jours) et une ancienne (50 jours)
        _insert_biometric(
            db_session,
            user_id=1,
            weight_kg=80.0,
            measured_at=now - timedelta(days=50),
        )
        _insert_biometric(
            db_session,
            user_id=1,
            weight_kg=78.0,
            measured_at=now - timedelta(days=5),
        )

        result = get_recent(user_id=1, db=db_session, days=30)

        assert result is not None
        assert result.weight_kg == pytest.approx(78.0)
