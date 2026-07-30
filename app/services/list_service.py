import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_list import TaskList
from app.schemas.list import ListCreate


async def create_list(
    session: AsyncSession, user_id: uuid.UUID, data: ListCreate
) -> TaskList:
    # 1. Resolve position
    if data.position is not None:
        resolved_position = data.position
    else:
        # Compute next position as MAX(position) + 1000 across the user's
        # non-deleted lists.
        # No FOR UPDATE — PostgreSQL forbids it with aggregate functions,
        # and the transaction's snapshot isolation already gives a
        # consistent read for this append-only position assignment.
        max_pos_query = select(
            func.coalesce(func.max(TaskList.position), 0) + 1000
        ).where(
            TaskList.user_id == user_id,
            TaskList.deleted_at.is_(None),
        )
        pos_result = await session.execute(max_pos_query)
        resolved_position = pos_result.scalar_one()

    # 2. Create list — user_id set server-side, never from request body.
    #    Set all fields explicitly so the ORM object is fully populated
    #    without needing session.refresh() (which requires RETURNING support).
    now = datetime.now(timezone.utc)
    task_list = TaskList(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data.name,
        position=resolved_position,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(task_list)

    # 3. Flush to persist to DB (commit handled by get_session context manager)
    await session.flush()
    return task_list
