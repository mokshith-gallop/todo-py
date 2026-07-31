# API Design

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
