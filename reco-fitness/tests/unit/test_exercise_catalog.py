from unittest.mock import MagicMock, patch

import pytest

from app.models.exercise import ExerciseORM
from app.services.exercise_catalog import (
    Exercise,
    ExerciseFilters,
    get_all,
    get_by_id,
    invalidate_cache,
)


def _make_orm(
    id: int = 1,
    name: str = "Squat",
    target_muscles: list | None = None,
    equipment: list | None = None,
    difficulty: str = "beginner",
    category: str | None = "legs",
    description: str | None = None,
    instructions: list | None = None,
    duration_seconds: int | None = None,
    calories_per_minute: int | None = None,
) -> ExerciseORM:
    row = ExerciseORM()
    row.id = id
    row.name = name
    row.target_muscles = target_muscles or ["quadriceps"]
    row.equipment = equipment or ["none"]
    row.difficulty = difficulty
    row.category = category
    row.description = description
    row.instructions = instructions or []
    row.duration_seconds = duration_seconds
    row.calories_per_minute = calories_per_minute
    return row


def _mock_db(rows: list) -> MagicMock:
    db = MagicMock()
    db.query.return_value.all.return_value = rows
    db.query.return_value.filter.return_value.first.return_value = rows[0] if rows else None
    return db


@pytest.fixture(autouse=True)
def reset_cache():
    invalidate_cache()
    yield
    invalidate_cache()


class TestGetAll:
    def test_returns_list_of_exercises(self):
        db = _mock_db([_make_orm(id=1), _make_orm(id=2, name="Lunge")])
        result = get_all(db)
        assert len(result) == 2
        assert all(isinstance(e, Exercise) for e in result)

    def test_empty_table_returns_empty_list(self):
        db = _mock_db([])
        result = get_all(db)
        assert result == []

    def test_maps_fields_correctly(self):
        row = _make_orm(
            id=42, name="Deadlift",
            target_muscles=["hamstrings", "glutes"],
            equipment=["barbell"], difficulty="advanced", category="back",
        )
        db = _mock_db([row])
        ex = get_all(db)[0]
        assert ex.id == 42
        assert ex.name == "Deadlift"
        assert "hamstrings" in ex.target_muscles
        assert ex.difficulty == "advanced"

    def test_none_array_fields_default_to_empty_list(self):
        row = _make_orm()
        row.target_muscles = None
        row.equipment = None
        row.instructions = None
        db = _mock_db([row])
        ex = get_all(db)[0]
        assert ex.target_muscles == []
        assert ex.equipment == []
        assert ex.instructions == []


class TestCache:
    def test_second_call_does_not_hit_db(self):
        db = _mock_db([_make_orm()])
        get_all(db)
        get_all(db)
        assert db.query.call_count == 1

    def test_invalidate_cache_forces_new_query(self):
        db = _mock_db([_make_orm()])
        get_all(db)
        invalidate_cache()
        get_all(db)
        assert db.query.call_count == 2

    def test_cache_expiry_via_short_ttl(self):
        from cachetools import TTLCache
        short_cache = TTLCache(maxsize=1, ttl=1)
        db = _mock_db([_make_orm()])
        with patch("app.services.exercise_catalog._cache", short_cache):
            get_all(db)
            short_cache.clear()
            get_all(db)
        assert db.query.call_count == 2


class TestFilters:
    def _rows(self):
        return [
            _make_orm(id=1, difficulty="beginner", target_muscles=["chest"], equipment=["none"], category="upper"),
            _make_orm(id=2, difficulty="advanced", target_muscles=["back"], equipment=["barbell"], category="upper"),
            _make_orm(id=3, difficulty="beginner", target_muscles=["legs"], equipment=["none"], category="lower"),
        ]

    def test_filter_by_difficulty(self):
        result = get_all(_mock_db(self._rows()), filters=ExerciseFilters(difficulty="beginner"))
        assert len(result) == 2
        assert all(e.difficulty == "beginner" for e in result)

    def test_filter_by_target_muscle(self):
        result = get_all(_mock_db(self._rows()), filters=ExerciseFilters(target_muscle="back"))
        assert len(result) == 1 and result[0].id == 2

    def test_filter_by_equipment(self):
        result = get_all(_mock_db(self._rows()), filters=ExerciseFilters(equipment="barbell"))
        assert len(result) == 1

    def test_filter_by_category(self):
        result = get_all(_mock_db(self._rows()), filters=ExerciseFilters(category="lower"))
        assert len(result) == 1 and result[0].id == 3

    def test_no_filter_returns_all(self):
        assert len(get_all(_mock_db(self._rows()))) == 3


class TestGetById:
    def test_returns_exercise_from_cache(self):
        db = _mock_db([_make_orm(id=5, name="Pull-up")])
        get_all(db)
        result = get_by_id(5, db)
        assert result is not None and result.name == "Pull-up"

    def test_returns_none_when_not_found(self):
        db = _mock_db([_make_orm(id=1)])
        get_all(db)
        assert get_by_id(999, db) is None

    def test_uses_cache_avoids_extra_query(self):
        db = _mock_db([_make_orm(id=1)])
        get_all(db)
        count_before = db.query.call_count
        get_by_id(1, db)
        assert db.query.call_count == count_before

    def test_queries_db_directly_when_cache_empty(self):
        db = _mock_db([_make_orm(id=7, name="Bench Press")])
        result = get_by_id(7, db)
        assert result is not None and result.name == "Bench Press"
        db.query.assert_called()
