"""Schemas Pydantic pour PUT /api/v1/programs/{program_id}/feedback (RF-12)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackRequest(BaseModel):
    """Feedback utilisateur sur un programme genere."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5, description="Note de 1 (mauvais) a 5 (excellent).")
    completed: bool
    comment: str | None = Field(default=None, max_length=2000)
    exercise_id: int | None = Field(
        default=None,
        description="Optionnel : feedback granulaire sur un exercice du programme.",
    )


class FeedbackResponse(BaseModel):
    user_id: str
    program_id: str
    feedback_score: int
    completed: bool
    comment: str | None
    exercise_id: int | None
    created_at: datetime
