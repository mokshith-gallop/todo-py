import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.database import get_session
from app.main import create_app
from app.models import Base, User, TaskList


def _register_sqlite_functions(dbapi_conn, connection_record):
    """Register PostgreSQL-compatible functions so SQLite can create tables."""
    dbapi_conn.create_function(
        "gen_random_uuid", 0, lambda: str(uuid.uuid4())
    )
    dbapi_conn.create_function(
        "char_length", 1, lambda s: len(s) if s else 0
    )


def make_auth_headers(user_id: uuid.UUID, email: str = "t@t.com") -> dict:
    """Return an Authorization header dict with a valid Bearer JWT."""
    token = jwt.encode(
        {"sub": str(user_id), "email": email},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Engine / session scoped to the entire test session (single in-memory DB)
# ---------------------------------------------------------------------------

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
event.listen(_engine.sync_engine, "connect", _register_sqlite_functions)
_test_session_factory = async_sessionmaker(
    _engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session", autouse=True)
async def _create_tables():
    """Create all tables once for the test session."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await _engine.dispose()


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _test_session_factory() as session:
        yield session


@pytest.fixture()
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the FastAPI app with the test DB."""

    async def _override_get_session():
        async with _test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture()
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture()
async def test_list(db_session: AsyncSession, test_user: User) -> TaskList:
    tl = TaskList(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test List",
        position=1000.0,
    )
    db_session.add(tl)
    await db_session.commit()
    return tl


@pytest.fixture()
async def other_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"other-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture()
async def other_list(
    db_session: AsyncSession, other_user: User
) -> TaskList:
    tl = TaskList(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="Other List",
        position=1000.0,
    )
    db_session.add(tl)
    await db_session.commit()
    return tl
