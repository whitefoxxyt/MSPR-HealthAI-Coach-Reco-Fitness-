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
    """Upsert le feedback sur (user_id, program_id, exercise_id) et retourne le document final."""
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

    # PUT idempotent : un feedback par (user_id, program_id, exercise_id).
    # exercise_id=None designe le feedback program-level, distinct des feedbacks par exercice.
    feedback_key = {
        "user_id": user_id,
        "program_id": program_id,
        "exercise_id": exercise_id,
    }
    now = datetime.now(timezone.utc)
    await db[HISTORY_COLLECTION].update_one(
        feedback_key,
        {
            "$set": {
                "feedback_score": score,
                "completed": completed,
                "comment": comment,
            },
            "$setOnInsert": {**feedback_key, "created_at": now},
        },
        upsert=True,
    )
    return await db[HISTORY_COLLECTION].find_one(feedback_key, {"_id": 0})
