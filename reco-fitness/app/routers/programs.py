"""Router /api/v1/programs (RF-12)."""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_db
from app.openapi_responses import NOT_FOUND, auth_responses
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services import feedback_service
from app.services.jwt_decoder import UserIdentity

FEEDBACK_EXAMPLES = {
    "programme_complete_5_etoiles": {
        "summary": "Programme termine et bien note",
        "value": {"score": 5, "completed": True, "comment": "Tres bon programme, bien dose."},
    },
    "exercice_trop_difficile": {
        "summary": "Feedback granulaire sur un exercice",
        "value": {
            "score": 2,
            "completed": False,
            "comment": "Trop dur, douleur a l'epaule.",
            "exercise_id": 142,
        },
    },
}

router = APIRouter(
    prefix="/programs",
    tags=["Feedback"],
    responses=auth_responses(),
)

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
MongoDB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]


@router.put(
    "/{program_id}/feedback",
    response_model=FeedbackResponse,
    summary="Enregistrer un feedback utilisateur sur un programme genere",
    responses={
        **NOT_FOUND,
        403: {"description": "Le programme cible n'appartient pas a l'utilisateur authentifie."},
    },
)
async def put_feedback(
    program_id: str,
    current_user: CurrentUser,
    db: MongoDB,
    payload: FeedbackRequest = Body(..., openapi_examples=FEEDBACK_EXAMPLES),
) -> FeedbackResponse:
    """
    Enregistre une note 1-5, un flag de completion et un commentaire optionnel
    sur un programme deja genere. Idempotent : PUT successifs avec le meme
    `(program_id, exercise_id)` mettent a jour le meme document (pas de doublons).

    Le feedback est exploite a la prochaine generation via la fonction
    `novelty_and_feedback_score` (penalise les exercices mal notes).
    Repond 403 si le programme n'appartient pas a l'utilisateur authentifie.
    """
    document = await feedback_service.record_feedback(
        user_id=current_user.user_id,
        program_id=program_id,
        score=payload.score,
        completed=payload.completed,
        comment=payload.comment,
        exercise_id=payload.exercise_id,
        db=db,
    )
    return FeedbackResponse(**document)
