from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.v1 import v1_router
from app.core.errors import (
    ResourceNotFoundError,
    resource_not_found_handler,
    validation_error_handler,
)


def create_app() -> FastAPI:
    application = FastAPI(title="Todo API", version="0.1.0")

    # Exception handlers
    application.add_exception_handler(
        ResourceNotFoundError, resource_not_found_handler  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        RequestValidationError, validation_error_handler  # type: ignore[arg-type]
    )

    # Health check
    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Mount versioned API under /api prefix
    application.include_router(v1_router, prefix="/api")

    return application


app = create_app()
