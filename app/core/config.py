import os

from pydantic_settings import BaseSettings

from app.core.db_url import normalise_url


def _resolve_database_url() -> str:
    """Resolve DATABASE_URL from the environment, normalised for asyncpg."""
    raw = os.environ.get("DATABASE_URL", "")
    if raw:
        return normalise_url(raw)
    # Fallback for local dev
    return "postgresql+asyncpg://app:app@localhost:5432/app"


class Settings(BaseSettings):
    DATABASE_URL: str = _resolve_database_url()
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Re-normalise in case pydantic-settings resolved DATABASE_URL from .env
settings.DATABASE_URL = normalise_url(settings.DATABASE_URL)
