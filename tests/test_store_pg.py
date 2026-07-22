"""Integration test for the real Postgres store. Skipped unless TEST_DATABASE_URL
is set (e.g. `docker compose up -d db` then
`TEST_DATABASE_URL=postgresql://cbm:cbm@localhost:5432/cbm_intake uv run pytest`).
"""

from __future__ import annotations

import os
import uuid

import pytest

from core.store import (
    STATUS_COMPLETED,
    STATUS_DISCARDED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    PostgresStore,
)

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


async def test_discard_resolves_stuck_but_not_completed():
    store = PostgresStore(_URL)
    await store.create_all()

    # A needs_attention row can be discarded (terminal) and then no longer claimed.
    stuck = await store.capture(
        "volunteer", f"disc-{uuid.uuid4()}", {"email": "stuck@example.com"},
        status="needs_attention",
    )
    assert await store.discard(stuck.id) is True
    assert (await store.get_submission(stuck.id))["status"] == STATUS_DISCARDED
    claimed = await store.claim_batch(50, lease_seconds=900)
    assert all(c.id != stuck.id for c in claimed)

    # A completed delivery must never be discarded.
    done = await store.capture(
        "volunteer", f"done-{uuid.uuid4()}", {"email": "done@example.com"},
        status=STATUS_PENDING,
    )
    await store.mark_completed(done.id, {"contactId": "c1"})
    assert await store.discard(done.id) is False
    assert (await store.get_submission(done.id))["status"] == STATUS_COMPLETED

    await store.dispose()


async def test_claim_leases_and_reclaims_stranded_processing():
    """A claimed row is leased (not re-claimable while the lease holds); once the
    lease expires it is reclaimed — the crash-recovery guarantee."""
    store = PostgresStore(_URL)
    await store.create_all()

    # Row A: claimed with a live lease must NOT be handed out again.
    held = await store.capture(
        "info-request", f"held-{uuid.uuid4()}", {"email": "held@example.com"},
        status=STATUS_PENDING,
    )
    claimed = await store.claim_batch(50, lease_seconds=900)
    assert any(c.id == held.id for c in claimed)
    again = await store.claim_batch(50, lease_seconds=900)
    assert all(c.id != held.id for c in again)
    assert (await store.get_submission(held.id))["status"] == STATUS_PROCESSING

    # Row B: claimed with a zero-length lease (its lease is immediately in the
    # past), simulating a worker that died mid-delivery — the next claim reclaims
    # it rather than leaving it stranded in "processing" forever.
    stranded = await store.capture(
        "info-request", f"stranded-{uuid.uuid4()}", {"email": "stranded@example.com"},
        status=STATUS_PENDING,
    )
    first = await store.claim_batch(50, lease_seconds=0)
    assert any(c.id == stranded.id for c in first)
    reclaimed = await store.claim_batch(50, lease_seconds=900)
    assert any(c.id == stranded.id for c in reclaimed)

    await store.dispose()


async def test_redrive_guard_and_acted_by():
    """P1-11: only needs_attention / retry / held rows can be re-driven —
    a completed row must never re-deliver — and the acting username lands
    durably in acted_by."""
    store = PostgresStore(_URL)
    await store.create_all()

    stuck = await store.capture(
        "info-request", f"guard-{uuid.uuid4()}", {"email": "g@example.com"},
        status="needs_attention",
    )
    assert await store.redrive(stuck.id, acted_by="doug.staff") is True
    row = await store.get_submission(stuck.id)
    assert row["status"] == STATUS_PENDING
    assert row["acted_by"] == "doug.staff"

    done = await store.capture(
        "info-request", f"guard-done-{uuid.uuid4()}", {"email": "d@example.com"},
        status=STATUS_PENDING,
    )
    await store.mark_completed(done.id, {"contactId": "c1"})
    assert await store.redrive(done.id, acted_by="doug.staff") is False
    assert (await store.get_submission(done.id))["status"] == STATUS_COMPLETED

    # Tidy the re-driven row so it isn't claimed by other tests' claim_batch.
    assert await store.discard(stuck.id, acted_by="doug.staff") is True
    assert (await store.get_submission(stuck.id))["acted_by"] == "doug.staff"

    await store.dispose()


async def test_heartbeat_and_stranded_metrics():
    """P1-6: the worker's heartbeat upsert + the stranded (lease-expired
    processing) count both surface in metrics()."""
    store = PostgresStore(_URL)
    await store.create_all()

    # Before any stamp the age may be None (fresh DB) or a real age (another
    # test/session stamped) — after stamping it must be a small number.
    await store.heartbeat()
    m = await store.metrics()
    assert m["workerHeartbeatAgeSeconds"] is not None
    assert m["workerHeartbeatAgeSeconds"] < 60
    # Upsert: a second stamp updates the single row, never inserts another.
    await store.heartbeat()
    m2 = await store.metrics()
    assert m2["workerHeartbeatAgeSeconds"] < 60

    # A row claimed with an already-expired lease counts as stranded.
    cap = await store.capture(
        "info-request", f"strand-metric-{uuid.uuid4()}",
        {"email": "strand@example.com"}, status=STATUS_PENDING,
    )
    claimed = await store.claim_batch(50, lease_seconds=0)
    assert any(c.id == cap.id for c in claimed)
    m3 = await store.metrics()
    assert m3["stranded"] >= 1

    # Resolve the row (leaves the shared DB tidy) — no longer processing, so
    # it stops counting as stranded.
    await store.mark_completed(cap.id, {"contactId": "c-strand"})

    await store.dispose()


async def test_metrics_windowed_latency():
    """Phase 6: recentAvgLatencySeconds averages only the newest completions,
    so a fresh regression is visible next to the lifetime average."""
    store = PostgresStore(_URL)
    await store.create_all()
    cap = await store.capture(
        "info-request", f"lat-{uuid.uuid4()}", {"email": "lat@example.com"},
        status=STATUS_PENDING,
    )
    await store.mark_completed(cap.id, {"contactId": "c-lat"})
    m = await store.metrics()
    assert m["recentAvgLatencySeconds"] is not None
    assert m["recentAvgLatencySeconds"] >= 0
    assert "avgLatencySeconds" in m
    await store.dispose()


async def test_thread_anchoring_round_trip():
    """v0.110.0: Gmail thread anchors (migration 0013) — append/dedup, the
    poller's token pre-check, cross-submission thread lookup, and the
    held_review approval path (redrive)."""
    store = PostgresStore(_URL)
    await store.create_all()
    token = f"thr-{uuid.uuid4()}"
    cap = await store.capture(
        "info-email", token,
        {"email": "thr@example.com", "gmail_thread_id": "tA"},
        status="held_review",
    )
    assert await store.add_thread_id(cap.id, "tA") is True
    assert await store.add_thread_id(cap.id, "tB") is True
    assert await store.add_thread_id(cap.id, "tA") is True  # dupe = no-op
    assert await store.add_thread_id("missing-id", "tX") is False

    row = await store.get_submission(cap.id)
    assert row["thread_ids"] == ["tA", "tB"]

    got = await store.existing_tokens("info-email", [token, "nope"])
    assert got == {token}
    assert await store.existing_tokens("info-email", []) == set()

    known = await store.known_gmail_threads(["tA", "tB", "tZ"])
    assert known == {"tA", "tB"}

    # Approval = redrive: held_review rows are re-drivable (→ pending).
    assert await store.redrive(cap.id, acted_by="tester") is True
    row2 = await store.get_submission(cap.id)
    assert row2["status"] == STATUS_PENDING
    # Tidy: park the row terminally so reruns of the suite stay clean.
    await store.discard(cap.id, acted_by="tester")
    await store.dispose()


async def test_request_status_round_trip():
    """v0.134.0: the staff request status (migration 0015) — set, read back on
    detail AND list, acted_by stamped; unknown id = False."""
    store = PostgresStore(_URL)
    await store.create_all()
    cap = await store.capture(
        "info-request", f"rs-{uuid.uuid4()}", {"email": "rs@example.com"},
        status=STATUS_COMPLETED,
    )
    row = await store.get_submission(cap.id)
    assert row["request_status"] is None  # pre-existing rows read as "New"

    assert await store.set_request_status(cap.id, "Responded", acted_by="tester") is True
    assert await store.set_request_status("missing-id", "Closed") is False

    row = await store.get_submission(cap.id)
    assert row["request_status"] == "Responded"
    assert row["acted_by"] == "tester"
    listed = [r for r in await store.list_submissions() if r["id"] == cap.id]
    assert listed and listed[0]["request_status"] == "Responded"
    await store.dispose()


async def test_discarded_rows_are_redrivable():
    """The /ops UI has offered Re-drive on discarded rows since v0.106.0; the
    store guard now actually allows it (mistaken-discard recovery)."""
    store = PostgresStore(_URL)
    await store.create_all()
    cap = await store.capture(
        "info-request", f"undo-{uuid.uuid4()}", {"email": "undo@example.com"},
        status="needs_attention",
    )
    assert await store.discard(cap.id, acted_by="tester") is True
    assert await store.redrive(cap.id, acted_by="tester") is True
    row = await store.get_submission(cap.id)
    assert row["status"] == STATUS_PENDING
    await store.discard(cap.id, acted_by="tester")
    await store.dispose()
