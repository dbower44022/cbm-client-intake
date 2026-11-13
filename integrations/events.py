"""Recent errors of each integration (prds/integrations-tab-plan.md § 6.6;
Doug's decision 11-13-26: the narrowed table), in the application's database
(migration ``0046_integration_fix_plan``).

The web process cannot read the worker's log, so the top-level error handler of
each integration's own job writes one line here, and the diagnosis agent reads
it through ``get_recent_errors``. Rules:

* only top-level handlers write — a job's whole pass failed, not one record;
* each message is scrubbed of every secret setting's value first;
* the same message for the same integration is written at most once an hour;
* rows are kept 14 days (pruned by the nightly run).

:func:`record_event` never raises: an error about an error is only logged.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Index, String, Table, delete, select

from core.store import metadata, shared_engine

log = logging.getLogger("cbm_intake.integrations.events")

KEEP_DAYS = 14
DEDUPE = timedelta(hours=1)
MESSAGE_MAX = 500

integration_event = Table(
    "integration_event",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("integration", String(40), nullable=False),
    Column("source", String(64), nullable=False),
    Column("message", String(MESSAGE_MAX), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_integration_event_recent", "integration", "created_at"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EventStore:
    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def record(self, integration: str, source: str, message: str,
                     *, now: Optional[datetime] = None) -> bool:
        """Write one line unless the same one was written within the hour."""
        now = now or _now()
        t = integration_event
        async with self._engine.begin() as conn:
            seen = (await conn.execute(
                select(t.c.id).where(t.c.integration == integration, t.c.message == message,
                                     t.c.created_at >= now - DEDUPE).limit(1)
            )).first()
            if seen:
                return False
            await conn.execute(t.insert().values(
                id=str(uuid.uuid4()), integration=integration, source=source[:64],
                message=message[:MESSAGE_MAX], created_at=now))
        return True

    async def recent(self, integration: str, *, days: int = KEEP_DAYS, limit: int = 50) -> list[dict[str, Any]]:
        t = integration_event
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(t).where(t.c.integration == integration,
                                t.c.created_at >= _now() - timedelta(days=days))
                .order_by(t.c.created_at.desc()).limit(limit)
            )).mappings().all()
        return [{"source": r["source"], "message": r["message"],
                 "at": r["created_at"].isoformat()} for r in rows]

    async def prune(self, *, days: int = KEEP_DAYS) -> int:
        t = integration_event
        async with self._engine.begin() as conn:
            res = await conn.execute(delete(t).where(t.c.created_at < _now() - timedelta(days=days)))
        return int(res.rowcount or 0)


def make_event_store(settings: Any) -> Optional[EventStore]:
    if not getattr(settings, "store_enabled", False):
        return None
    return EventStore(settings.database_url)


def clean(settings: Any, message: Any) -> str:
    """One line, scrubbed of every secret setting's value, cut to the column."""
    from integrations.testing import scrub, secret_values

    text = " ".join(str(message or "").split())
    return scrub(text, secret_values(settings))[:MESSAGE_MAX]


async def record_event(settings: Any, integration: str, source: str, message: Any) -> None:
    """Best-effort: one recent error for ``integration``. Never raises."""
    try:
        store = make_event_store(settings)
        if store is None:
            return
        await store.record(integration, source, clean(settings, message))
    except Exception as exc:  # noqa: BLE001 — an error about an error is only logged
        log.debug("integration event for %s could not be written: %s", integration, exc)
