import os

from pydantic_settings import BaseSettings


def _build_database_url() -> str:
    """Build database URL from DATABASE_URL env var or APP_DB_* parts."""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        # Ensure asyncpg driver
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    # Fallback for local dev
    return "postgresql+asyncpg://app:app@localhost:5432/app"


class Settings(BaseSettings):
    DATABASE_URL: str = _build_database_url()
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Ensure asyncpg driver on the final resolved value
if settings.DATABASE_URL.startswith("postgresql://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
