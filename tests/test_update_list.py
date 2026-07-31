"""Tests for PATCH /api/v1/lists/{list_id} — Update a Task List.

Covers all 6 acceptance criteria (AC1–AC6) plus auth.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_list import TaskList
from app.models.user import User
from tests.conftest import make_auth_headers


def _url(list_id: uuid.UUID | str) -> str:
    return f"/api/v1/lists/{list_id}"


# ── AC1: PATCH with new name → 200, name updated, camelCase response ────────


class TestAC1_UpdateName:
    async def test_update_name_returns_200(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "Groceries"},
            headers=headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Groceries"
        assert body["id"] == str(test_list.id)

    async def test_update_name_changes_updated_at(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        original_updated = test_list.updated_at

        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "Renamed"},
            headers=headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        # updated_at should differ from the original
        assert body["updatedAt"] != str(original_updated)

    async def test_response_uses_camel_case_keys(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "CamelCheck"},
            headers=headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "createdAt" in body
        assert "updatedAt" in body
        assert "deletedAt" in body
        assert "created_at" not in body
        assert "updated_at" not in body
        assert "deleted_at" not in body

    async def test_name_exactly_120_chars_accepted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "a" * 120},
            headers=headers,
        )

        assert resp.status_code == 200
        assert len(resp.json()["name"]) == 120

    async def test_position_unchanged_after_name_only_update(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "Only Name"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["position"] == test_list.position


# ── AC2: PATCH with new position → 200, position updated ────────────────────


class TestAC2_UpdatePosition:
    async def test_update_position_returns_200(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"position": 2500.0},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["position"] == 2500.0

    async def test_position_zero_accepted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"position": 0.0},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["position"] == 0.0

    async def test_negative_position_accepted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"position": -500.0},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["position"] == -500.0

    async def test_name_unchanged_after_position_only_update(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"position": 9999.0},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == test_list.name


# ── AC3: Validation errors → 422 ────────────────────────────────────────────


class TestAC3_ValidationErrors:
    async def test_blank_name_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "   "},
            headers=headers,
        )

        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        fields = [d["field"] for d in body["error"]["details"]]
        assert "name" in fields

    async def test_empty_name_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": ""},
            headers=headers,
        )

        assert resp.status_code == 422

    async def test_name_121_chars_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "x" * 121},
            headers=headers,
        )

        assert resp.status_code == 422
        fields = [d["field"] for d in resp.json()["error"]["details"]]
        assert "name" in fields

    async def test_empty_body_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={},
            headers=headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    async def test_invalid_uuid_returns_422(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            "/api/v1/lists/not-a-uuid",
            json={"name": "Valid Name"},
            headers=headers,
        )

        assert resp.status_code == 422


# ── AC4: Not-owned / non-existent list → 404 (never 403) ────────────────────


class TestAC4_OwnershipAndNotFound:
    async def test_other_users_list_returns_404(
        self,
        async_client: AsyncClient,
        test_user: User,
        other_list: TaskList,
    ):
        """Patching another user's list returns 404, never 403."""
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(other_list.id),
            json={"name": "Hijacked"},
            headers=headers,
        )

        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "resource_not_found"

    async def test_nonexistent_list_returns_404(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        fake_id = uuid.uuid4()
        resp = await async_client.patch(
            _url(fake_id),
            json={"name": "Ghost"},
            headers=headers,
        )

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "resource_not_found"

    async def test_soft_deleted_list_returns_404(
        self,
        async_client: AsyncClient,
        test_user: User,
        db_session: AsyncSession,
    ):
        """A soft-deleted list is treated as non-existent."""
        from datetime import datetime, timezone

        tl = TaskList(
            id=uuid.uuid4(),
            user_id=test_user.id,
            name="Deleted List",
            position=5000.0,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(tl)
        await db_session.commit()

        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(tl.id),
            json={"name": "Revive"},
            headers=headers,
        )

        assert resp.status_code == 404

    async def test_no_existence_leak(
        self,
        async_client: AsyncClient,
        test_user: User,
        other_list: TaskList,
    ):
        """404 for other-user's list is indistinguishable from non-existent."""
        headers = make_auth_headers(test_user.id)

        # Other user's list
        resp_other = await async_client.patch(
            _url(other_list.id),
            json={"name": "Hijack"},
            headers=headers,
        )
        # Genuinely non-existent list
        resp_ghost = await async_client.patch(
            _url(uuid.uuid4()),
            json={"name": "Ghost"},
            headers=headers,
        )

        # Both should return identical error shape
        assert resp_other.status_code == resp_ghost.status_code == 404
        assert (
            resp_other.json()["error"]["code"]
            == resp_ghost.json()["error"]["code"]
            == "resource_not_found"
        )


# ── AC5: Position rebalancing when gap < 1e-6 ───────────────────────────────


class TestAC5_PositionRebalancing:
    async def test_rebalance_triggered_when_gap_below_threshold(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """When adjacent positions fall within 1e-6, all positions rebalance
        to 1000-step integers preserving sort order."""
        # Create a fresh user with lists at very close positions
        user = User(
            id=uuid.uuid4(),
            email=f"rebal-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="hashed",
        )
        db_session.add(user)
        await db_session.flush()

        list_a = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="List A",
            position=1000.0,
        )
        list_b = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="List B",
            position=2000.0,
        )
        list_c = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="List C",
            position=3000.0,
        )
        db_session.add_all([list_a, list_b, list_c])
        await db_session.commit()

        headers = make_auth_headers(user.id)

        # Move list_c to be within 1e-6 of list_a (gap = 0.0000001)
        new_position = 1000.0 + 0.0000001
        resp = await async_client.patch(
            _url(list_c.id),
            json={"position": new_position},
            headers=headers,
        )

        assert resp.status_code == 200

        # After rebalancing, positions should be 1000, 2000, 3000
        # (integer-spaced preserving sort order)
        stmt = (
            select(TaskList.id, TaskList.position)
            .where(TaskList.user_id == user.id, TaskList.deleted_at.is_(None))
            .order_by(TaskList.position)
        )
        rows = (await db_session.execute(stmt)).all()

        positions = [r.position for r in rows]
        assert positions == [1000.0, 2000.0, 3000.0]

    async def test_no_rebalance_when_gap_is_sufficient(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """When gaps between positions are large, no rebalancing occurs."""
        user = User(
            id=uuid.uuid4(),
            email=f"norebal-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="hashed",
        )
        db_session.add(user)
        await db_session.flush()

        list_a = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="List A",
            position=1000.0,
        )
        list_b = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="List B",
            position=2000.0,
        )
        db_session.add_all([list_a, list_b])
        await db_session.commit()

        headers = make_auth_headers(user.id)

        # Move list_b to 1500 — large gap, no rebalancing needed
        resp = await async_client.patch(
            _url(list_b.id),
            json={"position": 1500.0},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["position"] == 1500.0

        # Positions should remain as-is (no rebalancing)
        stmt = (
            select(TaskList.position)
            .where(TaskList.user_id == user.id, TaskList.deleted_at.is_(None))
            .order_by(TaskList.position)
        )
        rows = (await db_session.execute(stmt)).all()
        positions = [r.position for r in rows]
        assert positions == [1000.0, 1500.0]

    async def test_rebalance_preserves_sort_order(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """After rebalancing, the relative order of lists is preserved."""
        user = User(
            id=uuid.uuid4(),
            email=f"order-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="hashed",
        )
        db_session.add(user)
        await db_session.flush()

        list_x = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="X-First",
            position=100.0,
        )
        list_y = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Y-Second",
            position=200.0,
        )
        list_z = TaskList(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Z-Third",
            position=300.0,
        )
        db_session.add_all([list_x, list_y, list_z])
        await db_session.commit()

        headers = make_auth_headers(user.id)

        # Move Z right next to X (gap < 1e-6)
        resp = await async_client.patch(
            _url(list_z.id),
            json={"position": 100.0 + 1e-8},
            headers=headers,
        )
        assert resp.status_code == 200

        # After rebalance, order should be X, Z, Y (by position)
        stmt = (
            select(TaskList.name, TaskList.position)
            .where(TaskList.user_id == user.id, TaskList.deleted_at.is_(None))
            .order_by(TaskList.position)
        )
        rows = (await db_session.execute(stmt)).all()
        names = [r.name for r in rows]
        assert names == ["X-First", "Z-Third", "Y-Second"]
        positions = [r.position for r in rows]
        assert positions == [1000.0, 2000.0, 3000.0]


# ── AC6: Both name and position updated atomically ──────────────────────────


class TestAC6_AtomicUpdate:
    async def test_both_name_and_position_updated(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "Both Updated", "position": 7777.0},
            headers=headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Both Updated"
        assert body["position"] == 7777.0

    async def test_atomic_update_single_request(
        self,
        async_client: AsyncClient,
        test_user: User,
        test_list: TaskList,
        db_session: AsyncSession,
    ):
        """Both fields persist to DB from one request."""
        list_id = test_list.id  # capture before any session ops
        headers = make_auth_headers(test_user.id)
        resp = await async_client.patch(
            _url(list_id),
            json={"name": "Atomic", "position": 4242.0},
            headers=headers,
        )

        assert resp.status_code == 200

        # Expire cached ORM state so the next query hits the DB
        db_session.expire_all()

        # Verify in DB
        result = await db_session.execute(
            select(TaskList).where(TaskList.id == list_id)
        )
        db_list = result.scalar_one()
        assert db_list.name == "Atomic"
        assert db_list.position == 4242.0


# ── Auth: missing token → 401 ───────────────────────────────────────────────


class TestAuth:
    async def test_missing_auth_returns_401(
        self, async_client: AsyncClient, test_list: TaskList
    ):
        resp = await async_client.patch(
            _url(test_list.id),
            json={"name": "No Auth"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"]["error"]["code"] == "authentication_required"
