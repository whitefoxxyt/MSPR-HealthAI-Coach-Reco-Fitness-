"""
Tests d'integration pour exercise_catalog.py.
Demarre un vrai PostgreSQL via testcontainers (Docker requis).
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from testcontainers.postgres import PostgresContainer

from app.services.exercise_catalog import (
    get_all,
    get_by_id,
    invalidate_cache,
    ExerciseFilters,
)
from app.models.exercise import ExerciseORM
from app.db.session import Base


# ------------------------------------------------------------
# Fixture : PostgreSQL container partage pour toute la session
# ------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_engine():
    with PostgresContainer("postgres:16-alpine") as pg:
        engine = create_engine(pg.get_connection_url())
        Base.metadata.create_all(engine)
        yield engine
        Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def db_session_factory(pg_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)


@pytest.fixture()
def db(db_session_factory, pg_engine) -> Session:
    """Session propre par test avec rollback automatique."""
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = db_session_factory(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def reset_cache():
    invalidate_cache()
    yield
    invalidate_cache()


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _insert_exercise(db: Session, **kwargs) -> ExerciseORM:
    defaults = dict(
        name="Burpee",
        target_muscles=["full_body"],
        equipment=["none"],
        difficulty="intermediate",
        category="cardio",
        description="Un burpee complet.",
        instructions=["Debout", "Au sol", "Pompe", "Saut"],
        duration_seconds=None,
        calories_per_minute=10,
    )
    defaults.update(kwargs)
    row = ExerciseORM(**defaults)
    db.add(row)
    db.flush()
    return row


# ------------------------------------------------------------
# Tests
# ------------------------------------------------------------

class TestGetAllIntegration:
    def test_empty_table_returns_empty_list(self, db):
        result = get_all(db)
        assert result == []

    def test_returns_inserted_exercise(self, db):
        _insert_exercise(db, name="Squat")
        invalidate_cache()
        result = get_all(db)
        assert len(result) == 1
        assert result[0].name == "Squat"

    def test_returns_multiple_exercises(self, db):
        _insert_exercise(db, name="Squat")
        _insert_exercise(db, name="Lunge")
        invalidate_cache()
        result = get_all(db)
        assert len(result) == 2

    def test_second_call_does_not_hit_db(self, db, pg_engine):
        _insert_exercise(db, name="Plank")
        invalidate_cache()
        get_all(db)

        # On insere un 2e exercice apres le premier appel -- le cache ne doit pas le voir
        with sessionmaker(bind=pg_engine)() as other_session:
            _insert_exercise(other_session, name="Hidden")
            other_session.commit()

        result = get_all(db)
        names = [e.name for e in result]
        assert "Hidden" not in names

    def test_invalidate_cache_fetches_fresh_data(self, db, pg_engine):
        _insert_exercise(db, name="Plank")
        invalidate_cache()
        get_all(db)

        with sessionmaker(bind=pg_engine)() as other_session:
            _insert_exercise(other_session, name="NewExercise")
            other_session.commit()

        invalidate_cache()
        result = get_all(db)
        names = [e.name for e in result]
        assert "NewExercise" in names


class TestGetAllFiltersIntegration:
    def test_filter_by_difficulty(self, db):
        _insert_exercise(db, name="Easy", difficulty="beginner")
        _insert_exercise(db, name="Hard", difficulty="advanced")
        invalidate_cache()
        result = get_all(db, filters=ExerciseFilters(difficulty="beginner"))
        assert all(e.difficulty == "beginner" for e in result)

    def test_filter_by_target_muscle(self, db):
        _insert_exercise(db, name="Press", target_muscles=["chest", "triceps"])
        _insert_exercise(db, name="Row", target_muscles=["back", "biceps"])
        invalidate_cache()
        result = get_all(db, filters=ExerciseFilters(target_muscle="chest"))
        assert len(result) == 1
        assert result[0].name == "Press"


class TestGetByIdIntegration:
    def test_returns_correct_exercise(self, db):
        row = _insert_exercise(db, name="Deadlift")
        invalidate_cache()
        result = get_by_id(row.id, db)
        assert result is not None
        assert result.name == "Deadlift"

    def test_returns_none_for_unknown_id(self, db):
        result = get_by_id(99999, db)
        assert result is None
