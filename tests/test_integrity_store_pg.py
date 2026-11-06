"""The login integrity fault store against a real Postgres (plan § 4.2): one
open row per key, a gone fault closes, a returning fault is a new row, an
acknowledgement survives the next run, and a sign-in event is recorded once a
day. Runs only when TEST_DATABASE_URL is set (same Postgres as
test_store_pg.py), migrated to head."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")

T0 = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def _f(key: str, cond: int = 1, summary: str = "s") -> dict:
    return {"key": key, "condition": cond, "summary": summary,
            "mentors": [{"id": "M", "name": "M"}], "login": None}


@pytest.fixture
async def store():
    from integrity.store import IntegrityStore

    s = IntegrityStore(_URL)
    async with s._engine.begin() as conn:
        await conn.execute(text("delete from login_integrity_fault"))
    yield s
    await s.dispose()


async def test_new_known_closed_and_returning(store):
    r = await store.apply_run([_f("1:a"), _f("4:b", 4)], now=T0)
    assert len(r["new"]) == 2 and not r["closed"] and len(r["open"]) == 2

    r = await store.apply_run([_f("1:a", summary="changed")], now=T0 + timedelta(days=1))
    assert not r["new"] and [c["fault_key"] for c in r["closed"]] == ["4:b"]
    assert [o["summary"] for o in r["open"]] == ["changed"]
    assert r["open"][0]["first_seen"] == T0

    r = await store.apply_run([_f("1:a"), _f("4:b", 4)], now=T0 + timedelta(days=2))
    assert [n["fault_key"] for n in r["new"]] == ["4:b"]  # back again: a new row
    async with store._engine.begin() as conn:
        n = (await conn.execute(text(
            "select count(*) from login_integrity_fault where fault_key='4:b'"))).scalar_one()
    assert n == 2


async def test_an_acknowledgement_survives_the_next_run(store):
    r = await store.apply_run([_f("1:a")], now=T0)
    fid = r["new"][0]["id"]
    assert await store.open_count() == 1
    got = await store.acknowledge(fid, by_id="u1", by="Sue Staff", note="Repair booked")
    assert got["ack_by"] == "Sue Staff" and got["ack_note"] == "Repair booked"
    assert await store.open_count() == 0
    assert await store.open_count(unacknowledged=False) == 1
    r = await store.apply_run([_f("1:a")], now=T0 + timedelta(days=1))
    assert r["open"][0]["ack_by"] == "Sue Staff"
    await store.apply_run([], now=T0 + timedelta(days=2))
    assert await store.acknowledge(fid, by_id="u1", by="x", note="") is None  # closed


async def test_a_signin_event_is_once_a_day_and_closes_next_run(store):
    ev = _f("7:u1:2026-11-06", 7)
    assert await store.record_event(ev, now=T0) is not None
    assert await store.record_event(ev, now=T0 + timedelta(hours=1)) is None
    r = await store.apply_run([], now=T0 + timedelta(hours=2))
    assert [o["fault_key"] for o in r["open"]] == ["7:u1:2026-11-06"]  # still today's
    r = await store.apply_run([], now=T0 + timedelta(days=1))
    assert r["open"] == [] and r["closed"][0]["condition"] == 7


async def test_mark_notified(store):
    r = await store.apply_run([_f("1:a")], now=T0)
    await store.mark_notified([r["new"][0]["id"]], now=T0)
    assert (await store.get(r["new"][0]["id"]))["notified_at"] == T0
