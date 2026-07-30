# Validation

## Input Validation & Error Handling

### Validation Rules (Pydantic Layer)

| Field | Rule | Error |
|---|---|---|
| `listId` | Required, valid UUID | 422 — `field: "listId"` |
| `title` | Required, 1–500 chars, not blank after `strip()` | 422 — `field: "title"` with specific message for blank vs. too-long |
| `notes` | Optional, max 10,000 chars | 422 — `field: "notes"` |
| `dueAt` | Optional, must be timezone-aware (`tzinfo is not None`) | 422 — `field: "dueAt"`, message: "Datetime must include timezone info" |
| `priority` | Optional, must be one of `none`, `low`, `med`, `high`; defaults to `none` | 422 — `field: "priority"` |
| `position` | Optional, float | 422 if not a valid number |

### Pydantic Validators

**Title — blank-after-strip check:**
```python
@field_validator("title")
@classmethod
def title_not_blank(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("Title must not be blank")
    return v
```
Note: `min_length=1` catches empty strings; the validator catches whitespace-only strings. `max_length=500` catches length overflow. Together they enforce AC #6.

**dueAt — timezone-aware enforcement:**
```python
@field_validator("due_at")
@classmethod
def due_at_must_be_aware(cls, v: datetime | None) -> datetime | None:
    if v is not None and v.tzinfo is None:
        raise ValueError("Datetime must include timezone information")
    return v
```
This implements AC #8 — naive datetimes are rejected with 422, not silently normalized.

### Service-Layer Validation

| Check | Behavior |
|---|---|
| List ownership | Query `task_list WHERE id = list_id AND user_id = user_id`. No row → raise `ResourceNotFoundError("List not found")` → 404. Uses 404 (not 403) per AC #5 to prevent resource enumeration. |

### Error Response Format

All validation errors use the locked error envelope from `app/core/errors.py`:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      { "field": "title", "message": "Title must not be blank" },
      { "field": "notes", "message": "String should have at most 10000 characters" }
    ]
  }
}
```

Pydantic's `RequestValidationError` is caught by a FastAPI exception handler that transforms the native error list into the standard envelope. Multiple validation errors are returned together (not fail-fast on the first).

### Edge Cases

| Scenario | Behavior |
|---|---|
| Title is only whitespace (e.g., `"   "`) | 422 — blank-after-strip validator |
| Title is exactly 500 chars | Accepted |
| Title is 501 chars | 422 — max_length |
| Notes is exactly 10,000 chars | Accepted |
| Notes is 10,001 chars | 422 — max_length |
| `dueAt` is `"2025-03-15T10:00:00"` (no TZ) | 422 — naive datetime rejected |
| `dueAt` is `"2025-03-15T10:00:00Z"` | Accepted (UTC) |
| `dueAt` is `"2025-03-15T10:00:00+05:30"` | Accepted (offset-aware) |
| `priority` is `"urgent"` | 422 — not in enum |
| `priority` omitted | Defaults to `"none"` |
| `listId` is valid UUID but belongs to another user | 404 |
| `listId` is valid UUID but doesn't exist at all | 404 (same response — no existence leak) |
| `position` omitted | Auto-assigned: `max(position) + 1000` |
| `position` provided as negative | Accepted (no business constraint against it) |
| `completedAt` sent in request body | Ignored — not in `TaskCreate` schema, so Pydantic silently drops it |
