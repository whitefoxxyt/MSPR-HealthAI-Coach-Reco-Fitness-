"""Router /api/v1/programs (RF-12)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_db
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services import feedback_service
from app.services.jwt_decoder import UserIdentity

router = APIRouter(prefix="/programs", tags=["Programs"])

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
MongoDB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]


@router.put(
    "/{program_id}/feedback",
    response_model=FeedbackResponse,
    summary="Enregistrer un feedback utilisateur sur un programme genere",
)
async def put_feedback(
    program_id: str,
    payload: FeedbackRequest,
    current_user: CurrentUser,
    db: MongoDB,
) -> FeedbackResponse:
    """Enregistre une note 1-5 + completion + commentaire optionnel sur un programme."""
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
