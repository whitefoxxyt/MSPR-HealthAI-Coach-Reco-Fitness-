"""Router GET /api/v1/programs/me et /api/v1/feedback/me (RF-13)."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_db
from app.schemas.program_history import (
    PaginatedFeedbackResponse,
    PaginatedProgramsResponse,
)
from app.services import program_history_service as svc
from app.services.jwt_decoder import UserIdentity

router = APIRouter(tags=["Program History"])

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
MongoDB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
LimitParam = Annotated[int, Query(ge=1, le=100)]
OffsetParam = Annotated[int, Query(ge=0)]


@router.get(
    "/programs/me",
    response_model=PaginatedProgramsResponse,
    summary="Lister mes programmes d'entrainement",
)
async def list_my_programs(
    current_user: CurrentUser,
    db: MongoDB,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> PaginatedProgramsResponse:
    return await svc.list_programs(current_user.user_id, limit, offset, db)


@router.get(
    "/feedback/me",
    response_model=PaginatedFeedbackResponse,
    summary="Lister mes feedbacks envoyes",
)
async def list_my_feedback(
    current_user: CurrentUser,
    db: MongoDB,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> PaginatedFeedbackResponse:
    return await svc.list_feedback(current_user.user_id, limit, offset, db)
