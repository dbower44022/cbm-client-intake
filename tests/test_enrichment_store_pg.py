"""The AI research run store against real Postgres (build plan phase 2 § 3).
Skipped unless TEST_DATABASE_URL is set (same Postgres as test_store_pg.py)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from core.store import make_async_engine
from enrichment.store import EnrichmentStore, enrichment_run, enrichment_run_item

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


async def _fresh() -> EnrichmentStore:
    engine = make_async_engine(_URL)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: enrichment_run_item.drop(c, checkfirst=True))
        await conn.run_sync(lambda c: enrichment_run.drop(c, checkfirst=True))
        await conn.run_sync(lambda c: enrichment_run.create(c))
        await conn.run_sync(lambda c: enrichment_run_item.create(c))
    await engine.dispose()
    return EnrichmentStore(_URL)


async def test_a_run_is_claimed_finished_and_spent():
    store = await _fresh()
    try:
        run = await store.create_run(tier="AI research", target_type="lead", target_ids=["a1", "a2", "a3"],
                                     estimate=0.6, model="claude-opus-5-5", started_by="Mark")
        assert await store.queued_items() == 3
        first = await store.claim(2)
        assert [i["target_id"] for i in first] == ["a1", "a2"] and first[0]["target_type"] == "lead"
        assert await store.target_pending("a1") == 1
        await store.finish_item(run["id"], "a1", ok=True, cost=0.21, findings=3, detail={"x": 1}, error=None)
        await store.finish_item(run["id"], "a2", ok=False, cost=0.05, findings=0, detail=None, error="declined")
        second = await store.claim(2)
        assert [i["target_id"] for i in second] == ["a3"]
        await store.finish_item(run["id"], "a3", ok=True, cost=0.19, findings=1, detail=None, error=None)
        got = await store.get_run(run["id"])
        assert got["status"] == "done" and got["items"] == {"done": 2, "failed": 1}
        assert got["cost"] == pytest.approx(0.45) and got["findings"] == 4
        assert await store.month_spend() == pytest.approx(0.45)
        assert await store.average_item_cost() == pytest.approx(0.20)
        assert (await store.target_last("a2"))["error"] == "declined"
        assert await store.claim(5) == []
    finally:
        await store.dispose()


async def test_a_stranded_item_is_taken_again_after_the_lease():
    store = await _fresh()
    try:
        await store.create_run(tier="AI research", target_type="company", target_ids=["c1"],
                               estimate=0.2, model="m", started_by="Cara")
        assert len(await store.claim(1)) == 1
        assert await store.claim(1) == []                     # still leased
        later = datetime.now(timezone.utc) + timedelta(minutes=30)
        again = await store.claim(1, now=later)
        assert [i["target_id"] for i in again] == ["c1"]
    finally:
        await store.dispose()
