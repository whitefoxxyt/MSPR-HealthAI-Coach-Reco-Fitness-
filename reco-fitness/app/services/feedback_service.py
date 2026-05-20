"""Enregistrement des feedbacks utilisateur sur les programmes generes (RF-12)."""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

PROGRAMS_COLLECTION = "workout_programs"
HISTORY_COLLECTION = "recommendation_history"


async def record_feedback(
    user_id: str,
    program_id: str,
    score: int,
    completed: bool,
    comment: str | None,
    exercise_id: int | None,
    db: AsyncIOMotorDatabase,
) -> dict:
    """Insere un feedback dans recommendation_history et retourne le document insere."""
    program = await db[PROGRAMS_COLLECTION].find_one(
        {"program_id": program_id}, {"user_id": 1}
    )
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Programme {program_id} introuvable.",
        )
    if program["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce programme n'appartient pas a cet utilisateur.",
        )

    document = {
        "user_id": user_id,
        "program_id": program_id,
        "feedback_score": score,
        "completed": completed,
        "comment": comment,
        "exercise_id": exercise_id,
        "created_at": datetime.now(timezone.utc),
    }
    await db[HISTORY_COLLECTION].insert_one(document)
    return document
