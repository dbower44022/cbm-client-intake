"""Integration test for the real Postgres store. Skipped unless TEST_DATABASE_URL
is set (e.g. `docker compose up -d db` then
`TEST_DATABASE_URL=postgresql://cbm:cbm@localhost:5432/cbm_intake uv run pytest`).
"""

from __future__ import annotations

import os
import uuid

import pytest

from core.store import STATUS_COMPLETED, STATUS_PENDING, PostgresStore

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


async def test_capture_idempotency_and_completion():
    store = PostgresStore(_URL)
    await store.create_all()
    token = f"it-{uuid.uuid4()}"
    payload = {"first_name": "Ada", "message": "hi", "company_url": ""}

    first = await store.capture("info-request", token, payload, status=STATUS_PENDING)
    assert first.is_new is True
    assert first.status == STATUS_PENDING

    # Same (form, token) → idempotent, no second row.
    second = await store.capture("info-request", token, payload, status=STATUS_PENDING)
    assert second.is_new is False
    assert second.id == first.id

    await store.mark_completed(first.id, {"contactId": "c1"})
    third = await store.capture("info-request", token, payload, status=STATUS_PENDING)
    assert third.is_new is False
    assert third.status == STATUS_COMPLETED
    assert third.result == {"contactId": "c1"}

    await store.dispose()


async def test_ops_list_counts_and_redrive():
    store = PostgresStore(_URL)
    await store.create_all()
    token = f"ops-{uuid.uuid4()}"
    cap = await store.capture(
        "info-request", token, {"email": "ops@example.com"}, status="needs_attention"
    )

    rows = await store.list_submissions(status="needs_attention")
    mine = [r for r in rows if r["id"] == cap.id]
    assert mine and mine[0]["email"] == "ops@example.com"

    counts = await store.counts_by_status()
    assert counts.get("needs_attention", 0) >= 1

    assert await store.redrive(cap.id) is True
    detail = await store.get_submission(cap.id)
    assert detail["status"] == "pending"
    assert detail["attempt_count"] == 0

    m = await store.metrics()
    assert "counts" in m and "backlog" in m and "needsAttention" in m

    await store.dispose()
