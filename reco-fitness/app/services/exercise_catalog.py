from dataclasses import dataclass, field
from typing import Literal

from cachetools import TTLCache
from sqlalchemy.orm import Session

from app.models.exercise import ExerciseORM

_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)
_CACHE_KEY = "all_exercises"


@dataclass
class Exercise:
    id: int
    name: str
    target_muscles: list[str]
    equipment: list[str]
    difficulty: str
    category: str | None = None
    description: str | None = None
    instructions: list[str] = field(default_factory=list)
    duration_seconds: int | None = None
    calories_per_minute: int | None = None
    gif_url: str | None = None


@dataclass
class ExerciseFilters:
    difficulty: Literal["beginner", "intermediate", "advanced"] | None = None
    target_muscle: str | None = None
    equipment: str | None = None
    category: str | None = None


def _orm_to_dataclass(row: ExerciseORM) -> Exercise:
    # difficulty, category, description, duration_seconds, calories_per_minute ne sont
    # pas exposes par MSPR-DB (table exercises issue de l'ETL ExerciseDB). On utilise
    # getattr pour rester tolerant aux mocks de tests qui peuvent les setter, et on
    # fournit des defauts neutres en production (scoring rule-based + ML tolerent).
    raw_instructions = getattr(row, "instructions", None)
    if isinstance(raw_instructions, str):
        instructions_list = [s.strip() for s in raw_instructions.split(".") if s.strip()]
    elif isinstance(raw_instructions, list):
        instructions_list = raw_instructions
    else:
        instructions_list = []
    return Exercise(
        id=row.id,
        name=row.name,
        target_muscles=row.target_muscles or [],
        equipment=row.equipment or [],
        difficulty=getattr(row, "difficulty", None) or "beginner",
        category=getattr(row, "category", None),
        description=getattr(row, "description", None),
        instructions=instructions_list,
        duration_seconds=getattr(row, "duration_seconds", None),
        calories_per_minute=getattr(row, "calories_per_minute", None),
        gif_url=row.gif_url,
    )


def _apply_filters(exercises: list[Exercise], filters: ExerciseFilters | None) -> list[Exercise]:
    if filters is None:
        return exercises
    result = exercises
    if filters.difficulty:
        result = [e for e in result if e.difficulty == filters.difficulty]
    if filters.target_muscle:
        result = [e for e in result if filters.target_muscle in e.target_muscles]
    if filters.equipment:
        result = [e for e in result if filters.equipment in e.equipment]
    if filters.category:
        result = [e for e in result if e.category == filters.category]
    return result


def get_all(db: Session, filters: ExerciseFilters | None = None) -> list[Exercise]:
    """
    Retourne tous les exercices.
    Premier appel : query PostgreSQL puis mise en cache TTL 1h.
    Appels suivants dans la fenetre TTL : retour du cache sans hit BDD.
    Jamais d ecriture sur la table exercises.
    """
    cached = _cache.get(_CACHE_KEY)
    if cached is None:
        rows = db.query(ExerciseORM).all()
        cached = [_orm_to_dataclass(row) for row in rows]
        _cache[_CACHE_KEY] = cached

    return _apply_filters(cached, filters)


def get_by_id(exercise_id: int, db: Session) -> Exercise | None:
    """
    Retourne un exercice par son identifiant.
    Utilise le cache si disponible, sinon query directe.
    """
    cached = _cache.get(_CACHE_KEY)
    if cached is not None:
        for exercise in cached:
            if exercise.id == exercise_id:
                return exercise
        return None

    row = db.query(ExerciseORM).filter(ExerciseORM.id == exercise_id).first()
    return _orm_to_dataclass(row) if row else None


def invalidate_cache() -> None:
    """Invalide manuellement le cache -- utile pour les tests et les mises a jour."""
    _cache.clear()
