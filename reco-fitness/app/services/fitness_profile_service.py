from datetime import datetime, timezone

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.fitness_profile import FitnessProfileRequest, FitnessProfileResponse

COLLECTION = "user_fitness_profiles"


async def get_profile(user_id: str, db: AsyncIOMotorDatabase) -> FitnessProfileResponse:
    """
    Retourne le profil fitness de l'utilisateur.
    Leve 404 si aucun profil n'a encore ete configure.
    """
    doc = await db[COLLECTION].find_one({"user_id": user_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil fitness introuvable pour cet utilisateur.",
        )
    return FitnessProfileResponse(**doc)


async def upsert_profile(
    user_id: str,
    payload: FitnessProfileRequest,
    db: AsyncIOMotorDatabase,
) -> FitnessProfileResponse:
    """
    Cree ou met a jour le profil fitness de l'utilisateur.
    Le user_id est toujours extrait du JWT, jamais du corps de la requete.
    """
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "health_goal_fitness": payload.health_goal_fitness.value,
        "experience_level": payload.experience_level.value,
        "equipment": payload.equipment,
        "limitations": payload.limitations,
        "preferences": payload.preferences.model_dump(),
        "updated_at": now,
    }
    await db[COLLECTION].update_one(
        {"user_id": user_id},
        {"$set": doc},
        upsert=True,
    )
    return FitnessProfileResponse(**doc)
