"""The integration test run store against a real Postgres (plan § 7): a run is
recorded, the latest run of each integration is read back, and no secret value
reaches the table. Runs only when TEST_DATABASE_URL is set, migrated to head."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from sqlalchemy import text

from core.config import Settings
from integrations.checks import zoom

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")

SECRET = "zoom-secret-value-987"


@pytest.fixture
async def store():
    from integrations.store import TestRunStore

    s = TestRunStore(_URL)
    async with s._engine.begin() as conn:
        await conn.execute(text("delete from integration_test_run"))
    yield s
    await s.dispose()


def _result(integration, outcome, started):
    return {"integration": integration, "outcome": outcome,
            "checks": [{"key": "a", "label": "A", "outcome": outcome, "detail": "d"}],
            "facts": [{"label": "F", "value": "v"}],
            "startedAt": started, "finishedAt": started, "durationMs": 5}


async def test_record_and_read_the_latest(store):
    await store.record(_result("zoom", "failed", "2026-11-13T06:00:00+00:00"), run_by="adm")
    await store.record(_result("zoom", "ok", "2026-11-13T07:00:00+00:00"), run_by="adm")
    await store.record(_result("espocrm", "unknown", "2026-11-13T05:00:00+00:00"),
                       trigger="nightly")
    latest = await store.latest("zoom")
    assert latest["outcome"] == "ok" and latest["runBy"] == "adm"
    assert latest["checks"][0]["key"] == "a" and latest["facts"] == [{"label": "F", "value": "v"}]
    every = await store.latest_all()
    assert set(every) == {"zoom", "espocrm"}
    assert every["zoom"]["outcome"] == "ok"
    assert every["espocrm"]["trigger"] == "nightly"
    assert await store.latest("google_workspace") is None


async def test_no_secret_reaches_the_table(store):
    from core.zoom import ZoomError

    class Leaky:
        scopes = ""

        async def _access_token(self, force=False):
            raise ZoomError(f"HTTP 400 bad client {SECRET}", status_code=400)

    settings = Settings(zoom_account_id="a", zoom_client_id="b",
                        zoom_client_secret=SECRET, zoom_host_email="h@x.org")
    result = await zoom.run(settings, zoom.Deps(client=lambda s: Leaky()))
    await store.record(result)
    async with store._engine.begin() as conn:
        rows = (await conn.execute(text(
            "select checks::text, facts::text from integration_test_run"))).all()
    assert rows and SECRET not in json.dumps([list(r) for r in rows])
