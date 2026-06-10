"""ensure_scoring_model : no-op si pickle present, entrainement sinon, jamais d'exception."""
from __future__ import annotations

import pytest

from app.services import scoring_bootstrap, scoring_ml
from app.services.exercise_catalog import Exercise


class _FakeSession:
    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _isolated_model(tmp_path, monkeypatch):
    """Pointe MODEL_PATH vers un fichier temporaire et reset le singleton."""
    monkeypatch.setattr(scoring_ml, "MODEL_PATH", tmp_path / "scoring_model.pkl")
    scoring_ml.reset_model()
    yield
    scoring_ml.reset_model()


def _catalog() -> list[Exercise]:
    muscles = ["quads", "lats", "pectorals", "delts"]
    return [
        Exercise(
            id=i,
            name=f"exercise {i}",
            target_muscles=[muscles[i % len(muscles)]],
            equipment=["body weight" if i % 2 else "dumbbell"],
            difficulty="beginner" if i % 2 else "intermediate",
            category="strength",
            body_parts=["upper legs"],
        )
        for i in range(1, 9)
    ]


def test_noop_quand_modele_present(monkeypatch):
    scoring_ml.MODEL_PATH.write_bytes(b"placeholder")

    def _boom(*args, **kwargs):
        raise AssertionError("SessionLocal ne doit pas etre appele quand le pickle existe")

    monkeypatch.setattr(scoring_bootstrap, "SessionLocal", _boom)
    assert scoring_bootstrap.ensure_scoring_model() is True


def test_entraine_depuis_le_catalogue(monkeypatch):
    monkeypatch.setattr(scoring_bootstrap, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(scoring_bootstrap, "get_all", lambda db: _catalog())
    assert scoring_bootstrap.ensure_scoring_model() is True
    assert scoring_ml.MODEL_PATH.exists()
    bundle = scoring_ml.get_model()
    assert set(bundle) == {"model", "vocab", "feature_columns"}


def test_catalogue_vide_sans_entrainement(monkeypatch):
    monkeypatch.setattr(scoring_bootstrap, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(scoring_bootstrap, "get_all", lambda db: [])
    assert scoring_bootstrap.ensure_scoring_model() is False
    assert not scoring_ml.MODEL_PATH.exists()


def test_pg_injoignable_ne_leve_pas(monkeypatch):
    def _boom():
        raise RuntimeError("PG down")

    monkeypatch.setattr(scoring_bootstrap, "SessionLocal", _boom)
    assert scoring_bootstrap.ensure_scoring_model() is False
