import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.schemas.list import ListCreate, ListResponse, ListUpdate
from app.services import list_service

router = APIRouter(prefix="/lists", tags=["lists"])


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=ListResponse
)
async def create_list(
    body: ListCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ListResponse:
    task_list = await list_service.create_list(
        session=session,
        user_id=current_user.id,
        data=body,
    )
    return ListResponse.model_validate(task_list)


@router.patch("/{list_id}", response_model=ListResponse)
async def update_list(
    list_id: uuid.UUID,
    body: ListUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ListResponse:
    task_list = await list_service.update_list(
        session=session,
        user_id=current_user.id,
        list_id=list_id,
        data=body,
    )
    return ListResponse.model_validate(task_list)
