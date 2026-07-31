# Validation

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
