import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ResourceNotFoundError
from app.models.task import Task
from app.models.task_list import TaskList
from app.schemas.task import TaskCreate


async def create_task(
    session: AsyncSession, user_id: uuid.UUID, data: TaskCreate
) -> Task:
    # 1. Verify list ownership — 404 (not 403) to prevent resource enumeration
    ownership_query = select(TaskList).where(
        TaskList.id == data.list_id,
        TaskList.user_id == user_id,
    )
    result = await session.execute(ownership_query)
    if result.scalar_one_or_none() is None:
        raise ResourceNotFoundError("List not found")

    # 2. Resolve position
    if data.position is not None:
        resolved_position = data.position
    else:
        # Use FOR UPDATE on PostgreSQL to prevent race conditions;
        # fall back gracefully on SQLite (which doesn't support it).
        dialect = session.bind.dialect.name if session.bind else ""
        max_pos_query = select(
            func.coalesce(func.max(Task.position), 0) + 1000
        ).where(
            Task.list_id == data.list_id,
            Task.deleted_at.is_(None),
        )
        if dialect == "postgresql":
            max_pos_query = max_pos_query.with_for_update()
        pos_result = await session.execute(max_pos_query)
        resolved_position = pos_result.scalar_one()

    # 3. Create task — user_id set server-side, never from request body.
    #    Set all fields explicitly so the ORM object is fully populated
    #    without needing session.refresh() (which requires RETURNING support).
    now = datetime.now(timezone.utc)
    task = Task(
        id=uuid.uuid4(),
        list_id=data.list_id,
        user_id=user_id,
        title=data.title,
        notes=data.notes,
        priority=data.priority.value,
        position=resolved_position,
        due_at=data.due_at,
        completed_at=None,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(task)

    # 4. Flush to persist to DB (commit handled by get_session context manager)
    await session.flush()
    return task
