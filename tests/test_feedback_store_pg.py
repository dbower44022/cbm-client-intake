"""The feedback store against a real Postgres (migration 0052): a moment
claimed once, a failure retried up to three times, the quiet-period lookup by
address, the alert claimed once. Runs only when TEST_DATABASE_URL is set,
migrated to head. Also checks the migration and the store declare the same
columns, which needs no database."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from feedback.store import FAILED, SENT, feedback_alert, feedback_send

_URL = os.environ.get("TEST_DATABASE_URL")
_MIGRATION = Path(__file__).resolve().parents[1] / "alembic/versions/0052_feedback_send.py"
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _columns(table: str) -> set[str]:
    src = _MIGRATION.read_text(encoding="utf-8").split("def downgrade", 1)[0]
    block = src.split(f'"{table}",', 1)[1].split("op.create_", 1)[0]
    return set(re.findall(r'sa\.Column\("(\w+)"', block))


def test_the_migration_and_the_store_declare_the_same_columns():
    assert _columns("feedback_send") == {c.name for c in feedback_send.columns}
    assert _columns("feedback_alert") == {c.name for c in feedback_alert.columns}


def test_the_revision_id_fits_alembic_version():
    src = _MIGRATION.read_text(encoding="utf-8")
    rev = re.search(r'^revision = "([^"]+)"', src, re.M).group(1)
    assert len(rev) <= 32 and rev == _MIGRATION.stem


needs_pg = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


@pytest.fixture
async def store():
    from feedback.store import FeedbackStore

    s = FeedbackStore(_URL)
    async with s._engine.begin() as conn:
        await conn.execute(text("delete from feedback_send"))
        await conn.execute(text("delete from feedback_alert"))
    yield s


def _claim(store, key, *, email="dana@example.com", now=T0):
    return store.claim(key, moment="Session Milestone", survey_key="mentoring-feedback",
                       entity_type="CEngagement", record_id="E1", email=email, now=now)


@needs_pg
async def test_a_moment_is_claimed_once(store):
    assert await _claim(store, "sessions:E1") is True
    assert await _claim(store, "sessions:E1") is False
    await store.finish("sessions:E1", SENT, link_id="L1", now=T0)
    row = await store.get("sessions:E1")
    assert row["outcome"] == SENT and row["link_id"] == "L1"


@needs_pg
async def test_a_failure_is_retried_three_times_in_all(store):
    assert await _claim(store, "k") is True
    for _ in range(2):
        await store.finish("k", FAILED, reason="no")
        assert await _claim(store, "k") is True
    await store.finish("k", FAILED, reason="no")
    assert await _claim(store, "k") is False


@needs_pg
async def test_the_quiet_period_reads_by_address(store):
    await _claim(store, "a", email=" Dana@Example.com ")
    await store.finish("a", SENT, now=T0)
    assert await store.recently_sent("dana@example.com", T0 - timedelta(days=30)) is True
    assert await store.recently_sent("dana@example.com", T0 + timedelta(minutes=1)) is False
    assert await store.recently_sent("someone@example.com", T0 - timedelta(days=30)) is False


@needs_pg
async def test_an_alert_is_claimed_once_and_a_failed_one_again(store):
    assert await store.claim_alert("R1") is True
    assert await store.claim_alert("R1") is False
    await store.finish_alert("R1", FAILED, "no")
    assert await store.failed_alerts() == ["R1"]
    assert await store.claim_alert("R1") is True
