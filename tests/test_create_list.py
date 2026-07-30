"""Tests for POST /api/v1/lists — Create a Task List.

Covers all 5 acceptance criteria (AC1–AC5) plus auth.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_list import TaskList
from app.models.user import User
from tests.conftest import make_auth_headers

URL = "/api/v1/lists"


# ── AC1: valid name → 201 with id, name, position, timestamps in camelCase ──


class TestAC1_BasicCreation:
    async def test_create_returns_201_with_required_fields(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "Groceries"},
            headers=headers,
        )

        assert resp.status_code == 201
        body = resp.json()

        # id is a valid UUID
        uuid.UUID(body["id"])

        assert body["name"] == "Groceries"
        assert isinstance(body["position"], (int, float))
        assert body["createdAt"] is not None
        assert body["updatedAt"] is not None
        assert body["deletedAt"] is None

    async def test_name_exactly_120_chars_accepted(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "a" * 120},
            headers=headers,
        )

        assert resp.status_code == 201
        assert len(resp.json()["name"]) == 120

    async def test_response_uses_camel_case_keys(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "CamelCheck"},
            headers=headers,
        )

        assert resp.status_code == 201
        body = resp.json()
        # Verify camelCase keys (not snake_case)
        assert "createdAt" in body
        assert "updatedAt" in body
        assert "deletedAt" in body
        assert "created_at" not in body
        assert "updated_at" not in body
        assert "deleted_at" not in body


# ── AC2: blank or empty name → 422 ──


class TestAC2_BlankName:
    async def test_blank_name_returns_422(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "   "},
            headers=headers,
        )

        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        fields = [d["field"] for d in body["error"]["details"]]
        assert "name" in fields

    async def test_empty_name_returns_422(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": ""},
            headers=headers,
        )

        assert resp.status_code == 422

    async def test_missing_name_returns_422(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={},
            headers=headers,
        )

        assert resp.status_code == 422


# ── AC3: name exceeding 120 characters → 422 ──


class TestAC3_NameTooLong:
    async def test_name_121_chars_returns_422(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "x" * 121},
            headers=headers,
        )

        assert resp.status_code == 422
        fields = [d["field"] for d in resp.json()["error"]["details"]]
        assert "name" in fields


# ── AC4: list is owner-scoped via user_id ──


class TestAC4_OwnerScoping:
    async def test_list_scoped_to_creating_user(
        self,
        async_client: AsyncClient,
        test_user: User,
        other_user: User,
        db_session: AsyncSession,
    ):
        """A list created by test_user is not visible when querying for other_user."""
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "Private List"},
            headers=headers,
        )

        assert resp.status_code == 201
        created_id = uuid.UUID(resp.json()["id"])

        # Query the DB directly: the list should belong to test_user
        result = await db_session.execute(
            select(TaskList).where(
                TaskList.id == created_id,
                TaskList.user_id == test_user.id,
            )
        )
        assert result.scalar_one_or_none() is not None

        # Query with other_user's id — should find nothing
        result2 = await db_session.execute(
            select(TaskList).where(
                TaskList.id == created_id,
                TaskList.user_id == other_user.id,
            )
        )
        assert result2.scalar_one_or_none() is None


# ── AC5: position — explicit vs auto-assigned ──


class TestAC5_Position:
    async def test_explicit_position_honored(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "Positioned", "position": 2000.0},
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["position"] == 2000.0

    async def test_explicit_position_zero_accepted(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "Zero Pos", "position": 0.0},
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["position"] == 0.0

    async def test_auto_position_first_list(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """First auto-positioned list for a fresh user gets position 1000."""
        # Create a brand-new user with no existing lists
        fresh_user = User(
            id=uuid.uuid4(),
            email=f"fresh-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="hashed",
        )
        db_session.add(fresh_user)
        await db_session.commit()

        headers = make_auth_headers(fresh_user.id)
        resp = await async_client.post(
            URL,
            json={"name": "First List"},
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["position"] == 1000.0

    async def test_auto_position_subsequent_list(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Second auto-positioned list gets position 2000."""
        fresh_user = User(
            id=uuid.uuid4(),
            email=f"fresh2-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="hashed",
        )
        db_session.add(fresh_user)
        await db_session.commit()

        headers = make_auth_headers(fresh_user.id)

        r1 = await async_client.post(
            URL,
            json={"name": "List 1"},
            headers=headers,
        )
        assert r1.status_code == 201
        assert r1.json()["position"] == 1000.0

        r2 = await async_client.post(
            URL,
            json={"name": "List 2"},
            headers=headers,
        )
        assert r2.status_code == 201
        assert r2.json()["position"] == 2000.0


# ── Auth: missing token → 401 ──


class TestAuth:
    async def test_missing_auth_returns_401(
        self, async_client: AsyncClient
    ):
        resp = await async_client.post(
            URL,
            json={"name": "No Auth"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"]["error"]["code"] == "authentication_required"
