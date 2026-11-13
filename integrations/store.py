"""Integration test runs (prds/integrations-tab-plan.md § 7), in the
application's database (migration ``0043_integration_test_run``).

One row per integration test, manual or nightly (the nightly run comes with
phase 5): the integration, how it was started, its start and finish, its
outcome, its checks and integration facts, and who ran it. The checks and facts
are stored exactly as ``integrations.testing.run_checks`` returns them, already
scrubbed of every secret value; a vendor's response body is never stored.

Training data on the sandbox: the table is in ``RESET_TABLES``, so crm-test's
history of integration tests is one day long (plan § 5). That is expected.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB

from core.config import Settings
from core.store import metadata, shared_engine

MANUAL = "manual"
NIGHTLY = "nightly"

integration_test_run = Table(
    "integration_test_run",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("integration", String(40), nullable=False),
    Column("trigger", String(16), nullable=False),      # manual | nightly
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("outcome", String(16), nullable=False),      # ok | failed | unknown
    Column("checks", JSONB, nullable=False),
    Column("facts", JSONB, nullable=False),
    Column("run_by_id", String(32)),
    Column("run_by", String(128)),
    Index("ix_integration_test_run_latest", "integration", "started_at"),
)


def _parse(stamp: Any) -> datetime:
    return stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp))


def public(row: Any) -> dict[str, Any]:
    """A stored run, in the shape the page reads."""
    r = dict(row)
    return {
        "id": r["id"],
        "integration": r["integration"],
        "trigger": r["trigger"],
        "outcome": r["outcome"],
        "checks": r["checks"] or [],
        "facts": r["facts"] or [],
        "startedAt": r["started_at"].isoformat() if r["started_at"] else None,
        "finishedAt": r["finished_at"].isoformat() if r["finished_at"] else None,
        "durationMs": r["duration_ms"],
        "runBy": r.get("run_by") or "",
    }


class TestRunStore:
    __test__ = False  # not a pytest class

    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def record(self, result: dict[str, Any], *, trigger: str = MANUAL,
                     run_by_id: str = "", run_by: str = "") -> dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "integration": result["integration"],
            "trigger": trigger,
            "started_at": _parse(result["startedAt"]),
            "finished_at": _parse(result["finishedAt"]),
            "duration_ms": int(result.get("durationMs") or 0),
            "outcome": result["outcome"],
            "checks": result.get("checks") or [],
            "facts": result.get("facts") or [],
            "run_by_id": run_by_id or None,
            "run_by": run_by or None,
        }
        async with self._engine.begin() as conn:
            await conn.execute(integration_test_run.insert().values(**row))
        return public(row)

    async def latest(self, integration: str) -> Optional[dict[str, Any]]:
        t = integration_test_run
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(t).where(t.c.integration == integration)
                .order_by(t.c.started_at.desc()).limit(1)
            )).mappings().first()
        return public(row) if row else None

    async def latest_all(self) -> dict[str, dict[str, Any]]:
        """The last run of each integration, keyed by integration."""
        t = integration_test_run
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(t).distinct(t.c.integration)
                .order_by(t.c.integration, t.c.started_at.desc())
            )).mappings().all()
        return {r["integration"]: public(r) for r in rows}


def make_test_run_store(settings: Settings) -> Optional[TestRunStore]:
    """A store when a database is configured, else None (runs are not kept)."""
    if not settings.store_enabled:
        return None
    return TestRunStore(settings.database_url)
