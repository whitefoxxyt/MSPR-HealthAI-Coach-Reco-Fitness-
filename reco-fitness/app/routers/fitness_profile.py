from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.dependencies import get_current_user, get_db
from app.services.jwt_decoder import UserIdentity
from app.services import fitness_profile_service as svc
from app.schemas.fitness_profile import FitnessProfileRequest, FitnessProfileResponse

router = APIRouter(prefix="/fitness-profile", tags=["Fitness Profile"])


@router.get(
    "/me",
    response_model=FitnessProfileResponse,
    summary="Recuperer mon profil fitness",
)
async def get_my_profile(
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> FitnessProfileResponse:
    """
    Retourne le profil fitness de l'utilisateur authentifie.
    Repond 404 si aucun profil n'a encore ete configure.
    """
    return await svc.get_profile(current_user.user_id, db)


@router.put(
    "/me",
    response_model=FitnessProfileResponse,
    summary="Creer ou mettre a jour mon profil fitness",
)
async def upsert_my_profile(
    payload: FitnessProfileRequest,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> FitnessProfileResponse:
    """
    Cree ou met a jour le profil fitness de l'utilisateur authentifie.
    Le user_id est toujours extrait du JWT, jamais du corps de la requete.
    """
    return await svc.upsert_profile(current_user.user_id, payload, db)
