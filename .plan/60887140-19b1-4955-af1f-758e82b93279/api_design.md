# API Design

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
