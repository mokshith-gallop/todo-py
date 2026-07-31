import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ResourceNotFoundError
from app.models.task_list import TaskList
from app.schemas.list import ListCreate, ListUpdate


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


async def update_list(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
    data: ListUpdate,
) -> TaskList:
    # 1. Fetch & authorize — 404 for missing, soft-deleted, or other-user lists
    #    (never 403, to avoid leaking existence).
    stmt = select(TaskList).where(
        TaskList.id == list_id,
        TaskList.user_id == user_id,
        TaskList.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    task_list = result.scalar_one_or_none()
    if task_list is None:
        raise ResourceNotFoundError("List not found")

    # 2. Apply provided fields
    if data.name is not None:
        task_list.name = data.name
    if data.position is not None:
        task_list.position = data.position
    task_list.updated_at = datetime.now(timezone.utc)

    # 3. Flush to persist changes
    await session.flush()

    # 4. Rebalance check — only when position was updated
    if data.position is not None:
        await _rebalance_positions_if_needed(session, user_id, task_list)

    return task_list


async def _rebalance_positions_if_needed(
    session: AsyncSession,
    user_id: uuid.UUID,
    task_list: TaskList,
) -> None:
    """Check for adjacent position gaps below 1e-6 and rebalance if needed.

    Reassigns all positions as 1000, 2000, 3000, … preserving the current
    sort order.  Runs in the same transaction (same session).
    """
    # Fetch all non-deleted list positions for this user, ordered
    stmt = (
        select(TaskList.id, TaskList.position)
        .where(TaskList.user_id == user_id, TaskList.deleted_at.is_(None))
        .order_by(TaskList.position)
    )
    rows = (await session.execute(stmt)).all()

    # Check if any adjacent gap < 1e-6
    needs_rebalance = False
    for i in range(1, len(rows)):
        if rows[i].position - rows[i - 1].position < 1e-6:
            needs_rebalance = True
            break

    if needs_rebalance:
        for idx, row in enumerate(rows):
            await session.execute(
                update(TaskList)
                .where(TaskList.id == row.id)
                .values(position=(idx + 1) * 1000)
            )
        await session.flush()
        # Refresh the target list to reflect its potentially new position
        await session.refresh(task_list)
