"""Integration test for the System Settings override store. Skipped unless
TEST_DATABASE_URL is set (same Postgres as test_store_pg.py).

The in-memory tests in ``test_system_settings.py`` cover the rules; this covers
the round trip — upsert in place, history append, clear, and the refresh that
installs overrides into the live configuration.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from core.config import get_settings
from core.settings_store import (
    SettingsError,
    SettingsStore,
    overdue_reviews,
    refresh_into_config,
)

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _fresh_store() -> SettingsStore:
    store = SettingsStore(_URL)
    await store.create_all()
    for key in list((await store.load()).keys()):
        await store.clear(key, actor="test", reason="cleanup")
    return store


async def test_override_round_trip_and_history():
    store = await _fresh_store()
    try:
        await store.set("worker_batch_size", "25", actor="ada", reason="throughput")
        rows = await store.load()
        assert rows["worker_batch_size"].value == "25"
        assert rows["worker_batch_size"].updated_by == "ada"

        # Upsert in place — one row, not two.
        await store.set("worker_batch_size", "30", actor="ada", reason="more")
        rows = await store.load()
        assert len(rows) == 1 and rows["worker_batch_size"].value == "30"

        history = await store.history("worker_batch_size")
        assert [h["newValue"] for h in history] == ["30", "25"]
        assert history[0]["oldValue"] == "25"

        assert await store.clear("worker_batch_size", actor="ada", reason="done")
        assert await store.load() == {}
        assert (await store.history("worker_batch_size"))[0]["action"] == "clear"
        # Clearing something that isn't overridden is a no-op, not an error.
        assert await store.clear("worker_batch_size", actor="ada") is False
    finally:
        await store.dispose()


async def test_refresh_installs_overrides_into_live_config():
    store = await _fresh_store()
    try:
        assert get_settings().worker_batch_size == 10
        await store.set("worker_batch_size", "44", actor="ada")
        await refresh_into_config(store, get_settings())
        assert get_settings().worker_batch_size == 44
    finally:
        await store.clear("worker_batch_size", actor="test")
        await store.dispose()


async def test_scoped_override_does_not_change_global_config():
    store = await _fresh_store()
    try:
        await store.set(
            "gcal_events", "true", actor="ada", scope_teams=["Mentor Team"]
        )
        await refresh_into_config(store, get_settings())
        # Scoped => evaluated per user, never installed process-wide.
        assert get_settings().gcal_events is False
    finally:
        await store.clear("gcal_events", actor="test")
        await store.dispose()


async def test_denylisted_key_is_refused_by_the_store():
    store = await _fresh_store()
    try:
        with pytest.raises(SettingsError):
            await store.set("espo_api_key", "nope", actor="ada")
        assert await store.load() == {}
    finally:
        await store.dispose()


async def test_overdue_temporary_overrides():
    store = await _fresh_store()
    try:
        past = datetime.now(timezone.utc) - timedelta(days=2)
        future = datetime.now(timezone.utc) + timedelta(days=7)
        await store.set("gmail_resync", "true", actor="ada", temporary=True, review_at=past)
        await store.set("worker_batch_size", "12", actor="ada", temporary=True,
                        review_at=future)
        overdue = await overdue_reviews(store)
        assert [o.key for o in overdue] == ["gmail_resync"]
    finally:
        for key in ("gmail_resync", "worker_batch_size"):
            await store.clear(key, actor="test")
        await store.dispose()
