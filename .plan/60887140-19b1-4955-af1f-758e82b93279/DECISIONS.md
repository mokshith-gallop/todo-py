# Locked Decisions for Story 60887140-19b1-4955-af1f-758e82b93279

## Implementation Approach
## Follow the existing Task pattern: Schema → Service → Router

This story mirrors the already-implemented "Create Task" feature. Every new file follows the same conventions verbatim.

### New Files

| File | Purpose |
|---|---|
| `app/schemas/list.py` | `ListCreate` and `ListResponse` Pydantic models extending `CamelBase` |
| `app/services/list_service.py` | `create_list(session, user_id, data)` — business logic |
| `app/api/v1/lists.py` | `POST /lists` router with DI for session + current_user |

### Modified Files

| File | Change |
|---|---|
| `app/api/v1/__init__.py` | Import and include `lists_router` on `v1_router` |

### No New Migration
The `task_list` table already exists in `0001_initial_schema.py` with all required columns (`id`, `user_id`, `name`, `position`, `deleted_at`, `created_at`, `updated_at`). No schema changes needed.

### Service Layer — `list_service.create_list()`
Follows the `task_service.create_task()` pattern exactly:
1. **Position resolution:** If `position` is provided, use it. Otherwise, compute `MAX(position) + 1000` across the user's non-deleted lists (default to `1000.0` for first list).
2. **Set `user_id` server-side** from the JWT — never from the request body (tenant isolation per AC4).
3. **Generate all fields in Python** (`uuid4()`, `datetime.now(UTC)`) so the ORM object is fully populated without needing `session.refresh()`.
4. **`session.add()` + `session.flush()`** — commit is handled by the `get_session` context manager.

### Router Layer — `app/api/v1/lists.py`
- Single `POST ""` handler, status code 201
- `Depends(get_current_user)` for auth, `Depends(get_session)` for DB
- Calls `list_service.create_list()`, returns `ListResponse.model_validate(result)`

### Testing
- Unit tests in `tests/test_create_list.py` covering:
  - Successful creation with explicit position
  - Successful creation with auto-assigned position
  - 422 for blank name / empty string / whitespace-only
  - 422 for name > 120 characters
  - 401 for missing auth token
  - Tenant isolation: list is scoped to the creating user
- Reuses existing test fixtures (`test_user`, `async_client`, `db_session`) from `conftest.py`

## Validation
## Validation Rules

### Name Field
| Rule | Implementation | Layer |
|---|---|---|
| Required | `Field(min_length=1)` on `ListCreate.name` | Pydantic |
| Max 120 chars | `Field(max_length=120)` on `ListCreate.name` | Pydantic + DB `String(120)` |
| Not blank after trim | `@field_validator("name")` checks `v.strip()` is non-empty, raises `ValueError("Name must not be blank")` | Pydantic |

This mirrors the existing `TaskCreate.title_not_blank` validator pattern:
```python
@field_validator("name")
@classmethod
def name_not_blank(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("Name must not be blank")
    return v
```

### Position Field
| Rule | Implementation |
|---|---|
| Optional | `position: float | None = None` — defaults to `None` |
| Auto-assigned when omitted | Service computes `MAX(position) + 1000` across user's non-deleted lists; defaults to `1000.0` for user's first list |
| No range constraint | Any valid float is accepted (matches task pattern) |

### Auth
| Scenario | Response |
|---|---|
| No `Authorization` header | 401 `{"error": {"code": "authentication_required", ...}}` |
| Invalid/expired JWT | 401 (same shape) |

### Error Envelope
All 422 responses use the existing `validation_error_handler` which produces:
```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [{"field": "name", "message": "..."}]
  }
}
```
Field names in the `details` array are auto-converted to camelCase by the handler (e.g. `listId` not `list_id`).

### Edge Cases
- **Whitespace-only name** (e.g. `"   "`) → 422 via `name_not_blank` validator
- **Empty string** (`""`) → 422 via `min_length=1`
- **Exactly 120 chars** → accepted
- **121 chars** → 422 via `max_length=120`
- **Position omitted** → auto-assigned by service
- **Position explicitly provided as `0.0`** → accepted (valid float)

## API Design
## POST /v1/lists

### Request
**Auth:** Bearer JWT (401 if missing/invalid)

**Body (JSON):**
```json
{
  "name": "Groceries",       // required, string, 1–120 chars, not blank after trim
  "position": 2000.0         // optional float, auto-assigned if omitted
}
```

### Success Response — 201 Created
```json
{
  "id": "a1b2c3d4-...",
  "name": "Groceries",
  "position": 2000.0,
  "deletedAt": null,
  "createdAt": "2025-01-15T10:30:00Z",
  "updatedAt": "2025-01-15T10:30:00Z"
}
```
All field names in **camelCase** (via `CamelBase` alias generator), matching the existing `TaskResponse` pattern.

### Error Response — 422 Validation Error
Uses the existing `validation_error_handler` in `app/core/errors.py`:
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

### Endpoint Registration
- Router mounted at `prefix="/lists"` with `tags=["lists"]`
- Added to `v1_router` in `app/api/v1/__init__.py` → accessible at `/api/v1/lists`
