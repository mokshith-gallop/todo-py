# Implementation Approach

## Layered Implementation — Router → Service → ORM

### Files to Create/Modify

| File | Action | Purpose |
|---|---|---|
| `app/models/task.py` | **Create** | SQLAlchemy ORM model for `task` table |
| `app/schemas/task.py` | **Create** | `TaskCreate` request + `TaskResponse` response Pydantic models |
| `app/schemas/enums.py` | **Create** | `Priority` string enum (`none`, `low`, `med`, `high`) |
| `app/services/task_service.py` | **Create** | `create_task()` business logic |
| `app/api/v1/tasks.py` | **Create** | POST `/v1/tasks` router |
| `app/api/v1/__init__.py` | **Modify** | Register tasks router under `/v1/tasks` prefix |
| `alembic/versions/xxx_create_task_table.py` | **Create** | Migration: task table, constraints, indexes |

### Service Layer Logic (`task_service.create_task`)

1. **Verify list ownership**: Query `task_list` filtered by `id = list_id AND user_id = user_id`. If no row, raise 404 (not 403 — prevents resource enumeration per the security decision).
2. **Resolve position**:
   - If `position` is provided → use it directly
   - If omitted → `SELECT COALESCE(MAX(position), 0) + 1000 FROM task WHERE list_id = :list_id AND deleted_at IS NULL`
3. **Create task**: Insert a new `Task` row with `user_id` explicitly set from `current_user.id` (never from request body).
4. **Commit and return**: The session commits on success via the dependency's context manager; the service returns the ORM instance, which the router serializes via `TaskResponse`.

### Key Design Choices

- **`user_id` on the task is set server-side**, derived from the JWT — never accepted from the request body. This, combined with the composite FK `(list_id, user_id) → task_list(id, user_id)`, makes cross-tenant task creation impossible at the database level.
- **Position query uses `FOR UPDATE` row-level locking** on the max-position query to prevent race conditions when two concurrent requests create tasks in the same list. This is a lightweight lock scoped to the list.
- **The service receives `user_id: UUID` as a plain parameter** (not the request object or a scoped global) — per the architecture constraint.
- **The ORM model uses `lazy="raise"` on all relationships** — no lazy loading in async context. If task-list details are needed in future endpoints, use explicit `selectinload`.

### ORM Model Pattern
```python
class Task(Base):
    __tablename__ = "task"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_list.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(4), nullable=False, server_default="none")
    position: Mapped[float] = mapped_column(Float, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
```

### Dependency Chain
This story depends on prior stories having established:
- `User` model and `user` table (Registration story)
- `TaskList` model and `task_list` table (Create a Task List story)
- `get_current_user` dependency (Login story)
- `get_session` dependency and DB engine (app bootstrap)
- Shared `CamelBase` Pydantic model with `alias_generator`
- Error envelope handler (`app/core/errors.py`)
