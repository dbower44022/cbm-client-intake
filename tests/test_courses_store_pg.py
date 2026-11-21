"""The training course store against real Postgres (prds/training-app-plan.md
§ 6). Skipped unless TEST_DATABASE_URL is set (same Postgres as
test_store_pg.py)."""

from __future__ import annotations

import os

import pytest

from core.store import make_async_engine
from courses.store import (CourseStore, training_completion, training_dismissal,
                           training_onboarding_write, training_progress)

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")
_TABLES = (training_progress, training_completion, training_dismissal, training_onboarding_write)


async def _fresh() -> CourseStore:
    engine = make_async_engine(_URL)
    async with engine.begin() as conn:
        for t in _TABLES:
            await conn.run_sync(lambda c, t=t: t.drop(c, checkfirst=True))
            await conn.run_sync(lambda c, t=t: t.create(c))
    await engine.dispose()
    return CourseStore(_URL)


async def test_progress_is_saved_replaced_and_cleared():
    store = await _fresh()
    await store.save_item("u1", "c", "1.0", "1.1")
    await store.save_item("u1", "c", "1.0", "cp-1", "first")
    await store.save_item("u1", "c", "1.1", "cp-1", "second")
    await store.save_item("u2", "c", "1.0", "1.1")
    rows = {r["item_key"]: r for r in await store.progress("u1", "c")}
    assert set(rows) == {"1.1", "cp-1"}
    assert rows["cp-1"]["answer"] == "second" and rows["cp-1"]["revision"] == "1.1"
    assert list(await store.progress_counts("u1")) == ["c"]
    await store.clear_item("u1", "c", "1.1")
    await store.clear_items("u1", "c", ["cp-1"])
    assert await store.progress("u1", "c") == []
    assert len(await store.progress("u2", "c")) == 1


async def test_a_completion_is_recorded_once_per_revision():
    store = await _fresh()
    row, created = await store.complete("u1", "Kitty", "c", "1.0", {"cp-1": {"answer": "R"}})
    assert created and row["answers"]["cp-1"]["answer"] == "R"
    again, created = await store.complete("u1", "Kitty", "c", "1.0", {})
    assert not created and again["id"] == row["id"]
    await store.complete("u1", "Kitty", "c", "2.0", {})
    assert [c["revision"] for c in await store.completions("u1")] == ["2.0", "1.0"]
