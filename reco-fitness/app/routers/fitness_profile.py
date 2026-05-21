from typing import Annotated

from fastapi import APIRouter, Body, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_db
from app.openapi_responses import NOT_FOUND, auth_responses
from app.schemas.fitness_profile import FitnessProfileRequest, FitnessProfileResponse
from app.services import fitness_profile_service as svc
from app.services.jwt_decoder import UserIdentity

FITNESS_PROFILE_EXAMPLES = {
    "musculation_intermediaire": {
        "summary": "Renforcement intermediaire avec halteres",
        "value": {
            "health_goal_fitness": "muscle_strength",
            "experience_level": "intermediate",
            "equipment": ["dumbbell", "bench"],
            "limitations": [],
            "preferences": {"duration_min_per_session": 60, "sessions_per_week": 4},
        },
    },
    "endurance_sans_materiel": {
        "summary": "Endurance debutant au poids du corps, blessure genou",
        "value": {
            "health_goal_fitness": "endurance",
            "experience_level": "beginner",
            "equipment": [],
            "limitations": ["knee"],
            "preferences": {"duration_min_per_session": 30, "sessions_per_week": 3},
        },
    },
}

router = APIRouter(
    prefix="/fitness-profile",
    tags=["Profil"],
    responses=auth_responses(),
)

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
MongoDB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]


@router.get("/me", summary="Recuperer mon profil fitness", responses=NOT_FOUND)
async def get_my_profile(
    current_user: CurrentUser,
    db: MongoDB,
) -> FitnessProfileResponse:
    """
    Retourne le profil fitness de l'utilisateur authentifie.
    Repond 404 si aucun profil n'a encore ete configure.
    """
    return await svc.get_profile(current_user.user_id, db)


@router.put("/me", summary="Creer ou mettre a jour mon profil fitness")
async def upsert_my_profile(
    current_user: CurrentUser,
    db: MongoDB,
    payload: FitnessProfileRequest = Body(..., openapi_examples=FITNESS_PROFILE_EXAMPLES),
) -> FitnessProfileResponse:
    """
    Cree ou met a jour le profil fitness de l'utilisateur authentifie.
    Le user_id est toujours extrait du JWT, jamais du corps de la requete.
    """
    return await svc.upsert_profile(current_user.user_id, payload, db)
