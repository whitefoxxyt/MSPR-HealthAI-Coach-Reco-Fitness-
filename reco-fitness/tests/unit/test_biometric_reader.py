"""Tests unitaires pour app/services/biometric_reader.py (RF-11).

Ces tests verifient le modele Pydantic `Biometric` sans toucher a la BDD.
Les tests de la requete `get_recent` vivent dans tests/integration.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.biometric_reader import Biometric


class TestBiometricModel:
    def test_accepts_all_spec_fields(self):
        bio = Biometric(
            user_id=42,
            weight_kg=72.5,
            avg_heart_rate_bpm=68,
            experience_level="intermediate",
            measured_at=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
        )

        assert bio.user_id == 42
        assert bio.weight_kg == 72.5
        assert bio.avg_heart_rate_bpm == 68
        assert bio.experience_level == "intermediate"
        assert bio.measured_at == datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)

    def test_optional_fields_default_to_none(self):
        bio = Biometric(
            user_id=1,
            measured_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )

        assert bio.weight_kg is None
        assert bio.avg_heart_rate_bpm is None
        assert bio.experience_level is None

    def test_rejects_missing_user_id(self):
        with pytest.raises(ValidationError):
            Biometric(measured_at=datetime(2026, 5, 1, tzinfo=timezone.utc))  # type: ignore[call-arg]

    def test_rejects_missing_measured_at(self):
        with pytest.raises(ValidationError):
            Biometric(user_id=1)  # type: ignore[call-arg]
