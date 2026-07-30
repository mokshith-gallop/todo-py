"""Tests for POST /api/v1/tasks — Create a Task.

Covers all 8 acceptance criteria (AC1–AC8).
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.task_list import TaskList
from app.models.user import User
from tests.conftest import make_auth_headers

URL = "/api/v1/tasks"


# ── AC1: valid title + listId → 201 with id, title, position, createdAt, version ──


class TestAC1_BasicCreation:
    async def test_create_returns_201_with_required_fields(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(test_list.id), "title": "Buy milk"},
            headers=headers,
        )

        assert resp.status_code == 201
        body = resp.json()

        # id is a valid UUID
        uuid.UUID(body["id"])

        assert body["title"] == "Buy milk"
        assert isinstance(body["position"], (int, float))
        assert body["createdAt"] is not None
        assert body["version"] == 1
        assert body["listId"] == str(test_list.id)


# ── AC2: optional fields (notes, dueAt, priority) persisted and returned ──


class TestAC2_OptionalFields:
    async def test_optional_fields_persisted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={
                "listId": str(test_list.id),
                "title": "Full task",
                "notes": "Remember to check expiry dates",
                "dueAt": "2025-06-01T12:00:00Z",
                "priority": "high",
            },
            headers=headers,
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["notes"] == "Remember to check expiry dates"
        assert body["priority"] == "high"
        assert body["dueAt"] is not None
        assert "2025-06-01" in body["dueAt"]


# ── AC3: defaults — priority='none', completedAt=null ──


class TestAC3_Defaults:
    async def test_defaults_when_only_required_fields(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(test_list.id), "title": "Minimal task"},
            headers=headers,
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["priority"] == "none"
        assert body["completedAt"] is None
        assert body["notes"] is None
        assert body["dueAt"] is None


# ── AC4: position — provided vs auto-assigned ──


class TestAC4_Position:
    async def test_explicit_position_honored(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={
                "listId": str(test_list.id),
                "title": "Positioned",
                "position": 500.0,
            },
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["position"] == 500.0

    async def test_auto_position_first_task(
        self,
        async_client: AsyncClient,
        test_user: User,
        db_session,
    ):
        """First task in a fresh list gets position 1000."""
        # Create a brand-new list so there are zero tasks
        fresh_list = TaskList(
            id=uuid.uuid4(),
            user_id=test_user.id,
            name="Fresh",
            position=1000.0,
        )
        db_session.add(fresh_list)
        await db_session.commit()

        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(fresh_list.id), "title": "First"},
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["position"] == 1000.0

    async def test_auto_position_subsequent_task(
        self,
        async_client: AsyncClient,
        test_user: User,
        db_session,
    ):
        """Second auto-positioned task gets position 2000."""
        fresh_list = TaskList(
            id=uuid.uuid4(),
            user_id=test_user.id,
            name="Fresh2",
            position=2000.0,
        )
        db_session.add(fresh_list)
        await db_session.commit()

        headers = make_auth_headers(test_user.id)

        r1 = await async_client.post(
            URL,
            json={"listId": str(fresh_list.id), "title": "Task 1"},
            headers=headers,
        )
        assert r1.status_code == 201
        assert r1.json()["position"] == 1000.0

        r2 = await async_client.post(
            URL,
            json={"listId": str(fresh_list.id), "title": "Task 2"},
            headers=headers,
        )
        assert r2.status_code == 201
        assert r2.json()["position"] == 2000.0


# ── AC5: list not owned → 404 (not 403) ──


class TestAC5_ListOwnership:
    async def test_other_users_list_returns_404(
        self,
        async_client: AsyncClient,
        test_user: User,
        other_list: TaskList,
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(other_list.id), "title": "Snoop"},
            headers=headers,
        )

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "resource_not_found"

    async def test_nonexistent_list_returns_404(
        self, async_client: AsyncClient, test_user: User
    ):
        headers = make_auth_headers(test_user.id)
        fake_id = str(uuid.uuid4())
        resp = await async_client.post(
            URL,
            json={"listId": fake_id, "title": "Ghost"},
            headers=headers,
        )

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "resource_not_found"

    async def test_no_existence_leak(
        self,
        async_client: AsyncClient,
        test_user: User,
        other_list: TaskList,
    ):
        """Both 'not owned' and 'doesn't exist' return identical 404 shape."""
        headers = make_auth_headers(test_user.id)

        r_owned = await async_client.post(
            URL,
            json={"listId": str(other_list.id), "title": "A"},
            headers=headers,
        )
        r_ghost = await async_client.post(
            URL,
            json={"listId": str(uuid.uuid4()), "title": "B"},
            headers=headers,
        )

        assert r_owned.status_code == r_ghost.status_code == 404
        assert (
            r_owned.json()["error"]["code"]
            == r_ghost.json()["error"]["code"]
            == "resource_not_found"
        )


# ── AC6: title validation — blank and length ──


class TestAC6_TitleValidation:
    async def test_blank_title_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(test_list.id), "title": "   "},
            headers=headers,
        )

        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        fields = [d["field"] for d in body["error"]["details"]]
        assert "title" in fields

    async def test_empty_title_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(test_list.id), "title": ""},
            headers=headers,
        )

        assert resp.status_code == 422

    async def test_title_501_chars_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(test_list.id), "title": "x" * 501},
            headers=headers,
        )

        assert resp.status_code == 422
        fields = [d["field"] for d in resp.json()["error"]["details"]]
        assert "title" in fields

    async def test_title_exactly_500_chars_accepted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={"listId": str(test_list.id), "title": "a" * 500},
            headers=headers,
        )

        assert resp.status_code == 201
        assert len(resp.json()["title"]) == 500


# ── AC7: notes length validation ──


class TestAC7_NotesValidation:
    async def test_notes_10001_chars_returns_422(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={
                "listId": str(test_list.id),
                "title": "ok",
                "notes": "n" * 10_001,
            },
            headers=headers,
        )

        assert resp.status_code == 422
        fields = [d["field"] for d in resp.json()["error"]["details"]]
        assert "notes" in fields

    async def test_notes_exactly_10000_chars_accepted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={
                "listId": str(test_list.id),
                "title": "ok",
                "notes": "n" * 10_000,
            },
            headers=headers,
        )

        assert resp.status_code == 201
        assert len(resp.json()["notes"]) == 10_000


# ── AC8: dueAt timezone-aware enforcement ──


class TestAC8_DueAtTimezone:
    async def test_naive_datetime_rejected(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={
                "listId": str(test_list.id),
                "title": "ok",
                "dueAt": "2025-03-15T10:00:00",
            },
            headers=headers,
        )

        assert resp.status_code == 422
        details = resp.json()["error"]["details"]
        fields = [d["field"] for d in details]
        assert "dueAt" in fields

    async def test_utc_datetime_accepted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={
                "listId": str(test_list.id),
                "title": "ok",
                "dueAt": "2025-03-15T10:00:00Z",
            },
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["dueAt"] is not None

    async def test_offset_aware_datetime_accepted(
        self, async_client: AsyncClient, test_user: User, test_list: TaskList
    ):
        headers = make_auth_headers(test_user.id)
        resp = await async_client.post(
            URL,
            json={
                "listId": str(test_list.id),
                "title": "ok",
                "dueAt": "2025-03-15T10:00:00+05:30",
            },
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["dueAt"] is not None
