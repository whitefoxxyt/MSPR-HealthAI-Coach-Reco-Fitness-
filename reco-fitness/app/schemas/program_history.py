"""Schemas Pydantic pour GET /api/v1/programs/me et /feedback/me (RF-13)."""
from datetime import datetime

from pydantic import BaseModel

from app.schemas.recommendations import WorkoutProgramResponse


class FeedbackItem(BaseModel):
    program_id: str
    user_id: str
    feedback_score: int
    created_at: datetime


class PaginatedProgramsResponse(BaseModel):
    items: list[WorkoutProgramResponse]
    total: int
    limit: int
    offset: int


class PaginatedFeedbackResponse(BaseModel):
    items: list[FeedbackItem]
    total: int
    limit: int
    offset: int
