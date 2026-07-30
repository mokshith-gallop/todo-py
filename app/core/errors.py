from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ResourceNotFoundError(Exception):
    """Raised when a requested resource does not exist or the user lacks access."""

    def __init__(self, message: str = "Resource not found") -> None:
        self.message = message
        super().__init__(self.message)


async def resource_not_found_handler(
    request: Request, exc: ResourceNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "resource_not_found",
                "message": exc.message,
            }
        },
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = []
    for err in exc.errors():
        # Extract the field name from loc — skip 'body' prefix
        loc = err.get("loc", ())
        field_parts = [str(part) for part in loc if part != "body"]
        field = ".".join(field_parts) if field_parts else "unknown"
        # Convert snake_case field to camelCase for the wire format
        parts = field.split("_")
        camel_field = parts[0] + "".join(p.capitalize() for p in parts[1:])
        details.append(
            {
                "field": camel_field,
                "message": err.get("msg", "Validation error"),
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": details,
            }
        },
    )
