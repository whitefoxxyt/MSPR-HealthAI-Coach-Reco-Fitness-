"""Service de lecture de l'historique : programmes generes et feedbacks envoyes (RF-13)."""
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.program_history import (
    FeedbackItem,
    PaginatedFeedbackResponse,
    PaginatedProgramsResponse,
)
from app.schemas.recommendations import WorkoutProgramResponse

PROGRAMS_COLLECTION = "workout_programs"
FEEDBACK_COLLECTION = "recommendation_history"


async def list_programs(
    user_id: str,
    limit: int,
    offset: int,
    db: AsyncIOMotorDatabase,
) -> PaginatedProgramsResponse:
    """
    Retourne la page de programmes generes par l'utilisateur, tri descendant sur created_at.
    Le filtre user_id provient du JWT (jamais de l'URL).
    """
    cursor = (
        db[PROGRAMS_COLLECTION]
        .find({"user_id": user_id}, {"_id": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    total = await db[PROGRAMS_COLLECTION].count_documents({"user_id": user_id})
    return PaginatedProgramsResponse(
        items=[WorkoutProgramResponse(**d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


async def list_feedback(
    user_id: str,
    limit: int,
    offset: int,
    db: AsyncIOMotorDatabase,
) -> PaginatedFeedbackResponse:
    """
    Retourne la page de feedbacks envoyes par l'utilisateur, tri descendant sur created_at.
    Le filtre user_id provient du JWT (jamais de l'URL).
    """
    cursor = (
        db[FEEDBACK_COLLECTION]
        .find({"user_id": user_id}, {"_id": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    total = await db[FEEDBACK_COLLECTION].count_documents({"user_id": user_id})
    return PaginatedFeedbackResponse(
        items=[FeedbackItem(**d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )
