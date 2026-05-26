"""Schemas Pydantic pour POST /api/v1/recommendations (RF-10)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RecommendationRequest(BaseModel):
    """Corps de la requete. Vide pour l'instant : tout est lu depuis le profil + JWT."""

    model_config = ConfigDict(extra="ignore")


class ExerciseInProgram(BaseModel):
    id: int
    name: str
    target_muscles: list[str]
    equipment: list[str]
    difficulty: str
    category: str | None = None
    gif_url: str | None = None


class WorkoutProgramResponse(BaseModel):
    program_id: str
    user_id: str
    duration_weeks: int
    scoring_strategy: Literal["rule_based", "hybrid_rank_fusion"]
    tier_at_generation: Literal["free", "premium", "premium_plus"]
    health_goal_at_generation: str | None = None
    duration_min_per_session: int | None = None
    weeks: list[list[list[ExerciseInProgram]]]
    created_at: datetime
