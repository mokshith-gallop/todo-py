from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.schemas.task import TaskCreate, TaskResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=TaskResponse
)
async def create_task(
    body: TaskCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    task = await task_service.create_task(
        session=session,
        user_id=current_user.id,
        data=body,
    )
    return TaskResponse.model_validate(task)
