"""Enregistrement des feedbacks utilisateur sur les programmes generes (RF-12)."""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.scoring_rule_based import Recommendation

PROGRAMS_COLLECTION = "workout_programs"
HISTORY_COLLECTION = "recommendation_history"
_HISTORY_SCORING_LIMIT = 200


async def load_history(
    user_id: str, db: AsyncIOMotorDatabase, limit: int = _HISTORY_SCORING_LIMIT
) -> list[Recommendation]:
    """
    Feedbacks exercice-level recents de l'utilisateur, convertis pour le
    scoring novelty_and_feedback_score. Les feedbacks program-level
    (exercise_id=None) sont ignores : ils ne ciblent aucun exercice.
    """
    cursor = (
        db[HISTORY_COLLECTION]
        .find({"user_id": user_id, "exercise_id": {"$ne": None}})
        .sort("created_at", -1)
        .limit(limit)
    )
    history: list[Recommendation] = []
    async for doc in cursor:
        history.append(
            Recommendation(
                exercise_id=doc["exercise_id"],
                feedback_score=doc.get("feedback_score"),
                created_at=doc["created_at"],
            )
        )
    return history


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
