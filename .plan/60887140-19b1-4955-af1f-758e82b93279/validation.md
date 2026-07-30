# Validation

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
