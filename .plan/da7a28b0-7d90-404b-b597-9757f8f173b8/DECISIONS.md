# Locked Decisions for Story da7a28b0-7d90-404b-b597-9757f8f173b8

## Implementation Approach
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

## Validation
## Input Validation & Error Handling

### Request Body Validation (Pydantic — `ListUpdate` schema)

| Field | Rule | Error |
|-------|------|-------|
| `name` | Optional. If provided: 1–120 characters, not blank after trimming whitespace | 422 `validation_error` with field `name` |
| `position` | Optional. If provided: valid float | 422 `validation_error` with field `position` |
| Body | At least one of `name` or `position` must be present | 422 `validation_error` — "At least one of name or position must be provided" |

**Blank name detection:** The `name_not_blank` field validator strips whitespace and rejects all-whitespace strings like `"   "`. Combined with `min_length=1`, this covers both AC #3 cases (blank name and empty string). The `max_length=120` constraint covers the upper bound.

### Path Parameter Validation

| Parameter | Rule | Error |
|-----------|------|-------|
| `list_id` | Must be a valid UUID | 422 (FastAPI auto-validates via `uuid.UUID` type annotation) |

### Business Rule Validation (Service layer)

| Rule | Behavior |
|------|----------|
| List not found | 404 `resource_not_found` — "List not found" |
| List belongs to another user | 404 `resource_not_found` (AC #4 — never 403) |
| List is soft-deleted | 404 `resource_not_found` (treated as non-existent) |

### Error Response Format
All errors use the existing error envelope already wired in `app/core/errors.py`:
```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      { "field": "name", "message": "String should have at least 1 character" }
    ]
  }
}
```

### Edge Cases
- **Whitespace-only name** (e.g., `"   "`) → rejected as blank by `name_not_blank` validator
- **Name exactly 120 chars** → accepted (boundary inclusive)
- **Name 121 chars** → rejected by `max_length=120`
- **Position = 0.0** → accepted (valid float, could be used to place at the start)
- **Position = negative** → accepted (no business reason to restrict — float ordering works with negatives)
- **Both fields null/absent** → rejected by `at_least_one_field` model validator
- **Extra unknown fields** → silently ignored by Pydantic (default behavior with `CamelBase`)
- **Empty JSON body `{}`** → rejected by `at_least_one_field` validator

## API Design
## PATCH /v1/lists/{list_id}

### Endpoint
- **Method:** `PATCH`
- **Path:** `/v1/lists/{list_id}` (UUID path parameter)
- **Auth:** Bearer JWT (existing `get_current_user` dependency)
- **Success:** `200 OK` with `ListResponse` body
- **Content-Type:** `application/json`

### Request Body (camelCase on the wire)
```json
{
  "name": "Groceries",      // optional, string 1–120 chars, non-blank
  "position": 2500.0        // optional, float
}
```
At least one field must be present. Both may be sent together (AC #6 — atomic update).

### Response Body (reuses existing `ListResponse`)
```json
{
  "id": "uuid",
  "name": "Groceries",
  "position": 2500.0,
  "deletedAt": null,
  "createdAt": "2025-01-01T00:00:00Z",
  "updatedAt": "2025-07-31T12:00:00Z"
}
```

### Error Responses
| Status | Code | When |
|--------|------|------|
| 401 | `authentication_required` | Missing/invalid JWT |
| 404 | `resource_not_found` | List doesn't exist, is soft-deleted, or belongs to another user (AC #4) |
| 422 | `validation_error` | Blank name, name > 120 chars, or empty body |

### Schema: `ListUpdate`
New Pydantic model in `app/schemas/list.py`:
```python
class ListUpdate(CamelBase):
    name: str | None = Field(None, min_length=1, max_length=120)
    position: float | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Name must not be blank")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ListUpdate":
        if self.name is None and self.position is None:
            raise ValueError("At least one of name or position must be provided")
        return self
```

### Notes
- The `ListResponse` schema is identical to the one already used by `POST /v1/lists`. No new response model needed.
- Path parameter `list_id` is a UUID — FastAPI validates format automatically via type annotation.
- Follows the existing router pattern: router calls service, never builds SQLAlchemy statements directly.
