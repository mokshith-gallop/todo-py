import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.db_url import connect_args_for_url

# Derive SSL connect_args from the *original* env URL (before sslmode was stripped)
_raw_url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args_for_url(_raw_url),
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
