# Implementation Approach

## Service Layer: `update_list` in `list_service.py`

### Core Flow
1. **Fetch & authorize** — `SELECT ... WHERE id = list_id AND user_id = user_id AND deleted_at IS NULL`. If no row, raise `ResourceNotFoundError` (→ 404). This matches the existing tenant isolation pattern in `task_service.create_task`.
2. **Apply fields** — Set `name` and/or `position` on the ORM object if provided. Set `updated_at = datetime.now(timezone.utc)` explicitly (matching `create_list` pattern of setting all fields server-side rather than relying on ORM `onupdate`).
3. **Flush** — `await session.flush()` to persist changes (commit handled by `get_session` context manager).
4. **Rebalance check** — If `position` was updated, run the gap-check and rebalance logic (see below).
5. **Return** the updated `TaskList` ORM instance.

### Position Rebalancing (AC #5)

**Trigger check** — After flushing a position update, query the user's non-deleted lists ordered by position and compute the minimum gap between adjacent positions:

```python
# Fetch all positions for this user, ordered
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
```

**Rebalance** — If triggered, reassign positions as `1000, 2000, 3000, ...` preserving the existing sort order. This runs in the same transaction (same `session.flush()`):

```python
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
```

**Why 1000-step:** Consistent with `create_list` auto-position (`MAX + 1000`). Maximizes the number of midpoint insertions before the next rebalance (~20 halvings before hitting 1e-6).

### Router: PATCH handler in `lists.py`

```python
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
```

### Key Design Choices
- **No `SELECT FOR UPDATE`** on the initial fetch — PostgreSQL's default `READ COMMITTED` isolation is sufficient. The rebalance query fetches all positions after flush, so it sees the just-written value. Concurrent rebalances on the same user are unlikely (single-user to-do app) and harmless (both would produce the same 1000-step result).
- **Soft-deleted lists excluded** from both position queries and rebalancing — they don't participate in ordering.
- **No Alembic migration needed** — the `task_list` table already has all required columns (`name`, `position`). No schema changes.
- **`updated_at` set explicitly** rather than relying on SQLAlchemy's `onupdate=func.now()` — keeps the pattern consistent with `create_list` and ensures the returned object has the correct timestamp without a refresh.
