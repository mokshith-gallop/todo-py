# Implementation Approach

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
