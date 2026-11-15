"""Migration 0049 (Integrations tab phase 10, ruling W4) up and down on tables
that hold rows. Runs only when TEST_DATABASE_URL is set: it makes a scratch
database beside that one, migrates it to 0048, writes a tick, two fix plans
that cost something, a setup plan and a fix plan that cost nothing, and an Ask
Claude answer, upgrades, checks the two tables are gone and every cost was
copied into ``integration_agent_call``, downgrades, checks the tables are back
empty and the copies removed, and drops the scratch database."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.test_survey_migration_pg import _URL, _alembic, _one, _plain  # noqa: F401

asyncpg = pytest.importorskip("asyncpg")

SCRATCH = "cbm_integration_removal_test"
T0 = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


@pytest.fixture
async def scratch():
    admin = await asyncpg.connect(_plain(_URL))
    await admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH}")
    await admin.execute(f"CREATE DATABASE {SCRATCH}")
    url = _plain(_URL, SCRATCH)
    try:
        yield url
    finally:
        await admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        await admin.close()


async def _tables(url: str) -> set[str]:
    return {r["tablename"] for r in await _one(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


async def test_0049_keeps_the_costs_and_drops_the_tables(scratch):
    _alembic(scratch, "upgrade", "0048_integration_wizard")
    conn = await asyncpg.connect(scratch)
    try:
        await conn.execute(
            "INSERT INTO integration_checklist_tick (id, step_id, integration, ticked, created_at) "
            "VALUES ('T1', '5.18', 'zoom', true, $1)", T0)
        for pid, kind, cost in (("P1", "fix", 0.26), ("P2", "setup", 0.4), ("P3", "fix", 0.0)):
            await conn.execute(
                "INSERT INTO integration_fix_plan (id, integration, kind, status, diagnosis, steps, cost, "
                "created_by, created_at) VALUES ($1, 'zoom', $2, 'proposed', 'The host is wrong.', "
                "'[]'::jsonb, $3, 'adm', $4)", pid, kind, cost, T0)
        await conn.execute(
            "INSERT INTO integration_agent_call (id, integration, screen, status, answer, cost, created_at) "
            "VALUES ('C1', 'zoom', 'zoom-host', 'answered', 'x', 0.05, $1)", T0)
    finally:
        await conn.close()

    _alembic(scratch, "upgrade", "0049_drop_checklist_fix_plans")
    tables = await _tables(scratch)
    assert "integration_fix_plan" not in tables and "integration_checklist_tick" not in tables
    rows = {r["id"]: r for r in await _one(scratch, "SELECT * FROM integration_agent_call")}
    assert set(rows) == {"C1", "P1", "P2"}  # a plan that cost nothing is not copied
    assert rows["P1"]["status"] == "fix plan" and rows["P2"]["status"] == "setup plan"
    assert rows["P1"]["screen"] is None and rows["P1"]["asked_by"] == "adm"
    assert rows["P1"]["created_at"] == T0
    [total] = await _one(scratch, "SELECT sum(cost) AS s FROM integration_agent_call")
    assert round(total["s"], 2) == 0.71

    _alembic(scratch, "downgrade", "0048_integration_wizard")
    tables = await _tables(scratch)
    assert {"integration_fix_plan", "integration_checklist_tick"} <= tables
    assert await _one(scratch, "SELECT * FROM integration_fix_plan") == []
    assert [r["id"] for r in await _one(scratch, "SELECT id FROM integration_agent_call")] == ["C1"]
    indexes = {r["indexname"] for r in await _one(
        scratch, "SELECT indexname FROM pg_indexes WHERE tablename IN "
                 "('integration_fix_plan', 'integration_checklist_tick')")}
    assert {"ix_integration_fix_plan_latest", "ix_integration_checklist_tick_step"} <= indexes
    _alembic(scratch, "upgrade", "head")
