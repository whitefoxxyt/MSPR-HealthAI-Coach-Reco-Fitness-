"""Router POST /api/v1/recommendations (RF-10)."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.db.session import get_db as get_pg_db
from app.dependencies import get_current_user, get_db
from app.schemas.recommendations import (
    ExerciseInProgram,
    RecommendationRequest,
    WorkoutProgramResponse,
)
from app.services import biometric_reader, exercise_catalog, fitness_profile_service
from app.services import workout_program_orchestrator as orchestrator
from app.services.entitlements_client import get_entitlements
from app.services.jwt_decoder import UserIdentity
from app.services.jwt_decoder import decode as decode_jwt


def _user_id_from_request(request: Request) -> str:
    """
    Cle de rate limiting : user_id extrait du JWT Bearer pour cloisonner les compteurs
    par utilisateur authentifie. Fallback sur l'IP si le header est absent ou invalide.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return get_remote_address(request)
    token = auth_header.split(" ", 1)[1].strip()
    try:
        return decode_jwt(token).user_id
    except Exception:
        return get_remote_address(request)


limiter = Limiter(key_func=_user_id_from_request)

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
MongoDB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
PgSession = Annotated[Session, Depends(get_pg_db)]

COLLECTION = "workout_programs"


def _exercise_to_schema(ex) -> ExerciseInProgram:
    return ExerciseInProgram(
        id=ex.id,
        name=ex.name,
        target_muscles=ex.target_muscles,
        equipment=ex.equipment,
        difficulty=ex.difficulty,
        category=ex.category,
    )


@router.post(
    "",
    response_model=WorkoutProgramResponse,
    summary="Generer un programme d'entrainement personnalise",
)
@limiter.limit("10/hour;3/minute")
async def post_recommendation(
    request: Request,
    payload: RecommendationRequest,
    current_user: CurrentUser,
    db: MongoDB,
    pg_session: PgSession,
) -> WorkoutProgramResponse:
    """
    Genere un programme personnalise selon le tier de l'utilisateur :
    - free : 2 semaines, scoring rule-based seul
    - premium : duree pleine, fusion rule-based + ML
    - premium_plus : premium + ajustement de la charge via biometriques recentes
    """
    request.state.user_id = current_user.user_id

    jwt_token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    entitlements = await get_entitlements(current_user.user_id, jwt_token)

    profile_response = await fitness_profile_service.get_profile(current_user.user_id, db)
    profile = profile_response  # FitnessProfileResponse herite des memes champs

    # Charge le catalogue via le cache exercise_catalog (lecture PG read-only).
    catalog = exercise_catalog.get_all(pg_session)

    history: list = []  # TODO RF-x : charger recommendation_history du user

    if entitlements.tier == "free":
        program = orchestrator.recommend_free(profile, history, catalog)
    elif entitlements.tier == "premium":
        program = orchestrator.recommend_premium(profile, history, catalog)
    elif entitlements.tier == "premium_plus":
        biometrics = await biometric_reader.get_recent_biometrics(current_user.user_id, db)
        program = orchestrator.recommend_premium_plus(profile, history, catalog, biometrics)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tier inconnu : {entitlements.tier}",
        )

    program_id = str(uuid4())
    now = datetime.now(timezone.utc)

    weeks_serialized = [
        [[_exercise_to_schema(ex).model_dump() for ex in session] for session in week]
        for week in program.weeks
    ]

    document = {
        "program_id": program_id,
        "user_id": current_user.user_id,
        "duration_weeks": program.duration_weeks,
        "scoring_strategy": program.scoring_strategy,
        "tier_at_generation": entitlements.tier,
        "intensity_modifier": program.intensity_modifier,
        "weeks": weeks_serialized,
        "created_at": now,
    }
    await db[COLLECTION].insert_one(document.copy())

    return WorkoutProgramResponse(**document)
