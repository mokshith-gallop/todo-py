# API Design

## POST /v1/tasks — Create a Task

### Endpoint
`POST /v1/tasks`

### Authentication
Bearer JWT required (`get_current_user` dependency). Returns 401 if missing/invalid.

### Request Body (camelCase wire format)
```json
{
  "listId": "uuid (required)",
  "title": "string (required, 1–500 chars)",
  "notes": "string (optional, max 10,000 chars)",
  "dueAt": "datetime with timezone (optional, ISO 8601)",
  "priority": "string (optional, one of: none, low, med, high)",
  "position": "number (optional, float)"
}
```

### Pydantic Request Schema (`TaskCreate`)
- `list_id: UUID` — required
- `title: str` — `Field(min_length=1, max_length=500)`, with a validator that rejects blank-after-strip
- `notes: str | None = None` — `Field(max_length=10_000)`
- `due_at: datetime | None = None` — must have `tzinfo` set (validator rejects naive datetimes)
- `priority: Priority = Priority.NONE` — `Priority` is a `str` enum: `none`, `low`, `med`, `high`
- `position: float | None = None` — when omitted, service auto-assigns

All fields use `alias_generator=to_camel` from the shared `CamelBase` model, bridging snake_case Python ↔ camelCase JSON.

### Response — 201 Created (`TaskResponse`)
```json
{
  "id": "uuid",
  "listId": "uuid",
  "title": "string",
  "notes": "string | null",
  "dueAt": "datetime | null",
  "priority": "none | low | med | high",
  "position": 1000.0,
  "completedAt": null,
  "deletedAt": null,
  "createdAt": "datetime",
  "updatedAt": "datetime",
  "version": 1
}
```

### Error Responses

| Status | Condition | Error Code |
|---|---|---|
| 401 | Missing/invalid JWT | `authentication_required` |
| 404 | `listId` not owned by user (or doesn't exist) | `resource_not_found` |
| 422 | Validation failure (title, notes, dueAt, priority) | `validation_error` |

All errors use the locked error envelope: `{ "error": { "code": "...", "message": "...", "details": [...] } }`

### Error Envelope Examples

**422 — blank title:**
```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      { "field": "title", "message": "Title must not be blank" }
    ]
  }
}
```

**404 — list not owned:**
```json
{
  "error": {
    "code": "resource_not_found",
    "message": "List not found"
  }
}
```

### Router Implementation Pattern
```python
@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
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
    return task
```

The router delegates entirely to the service — no SQLAlchemy in the router, per the locked architecture.
