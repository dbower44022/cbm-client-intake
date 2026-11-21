"""What the Ambassador Program keeps in the application database (PRD § 4.1).

``ambassador_report`` holds one row per report a mentor submitted, written
BEFORE any CRM call, so a report is safe the moment the mentor sees "saved".
The row carries who submitted it (taken from the sign-in, never from the
browser), what they submitted, and the delivery's progress: the delivery
runs through ``core/resumable.ResumableClient``, so a retry finishes a
half-done chain without duplicating anything.

Statuses: ``pending`` (to deliver), ``delivered``, ``failed`` (retries
exhausted; logged and listed by the worker). ``lease_until`` keeps the web's
own first try and the worker from delivering one row at the same time.

Training data on the sandbox (``core/sandbox_reset.RESET_TABLES``). One store
per process; it borrows the shared pool. In tests the in-memory twin is
``tests/ambassador_fakes.MemoryReportStore``.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import (Column, DateTime, Integer, String, Table, Text, UniqueConstraint, and_,
                        or_, select, update)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import metadata, shared_engine

PENDING, DELIVERED, FAILED = "pending", "delivered", "failed"
#: Backoff between delivery attempts, then the row is left failed.
BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30),
           timedelta(hours=2), timedelta(hours=6))

ambassador_report = Table(
    "ambassador_report",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("reference", String(16), nullable=False),
    Column("submission_token", String(64), nullable=False),
    Column("user_id", String(32), nullable=False),
    Column("user_name", String(255), nullable=False, server_default=""),
    Column("mentor_profile_id", String(32), nullable=False),
    Column("payload", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("lease_until", DateTime(timezone=True)),
    Column("progress", Text, nullable=False, server_default="{}"),
    Column("activity_id", String(32)),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("submission_token", name="uq_ambassador_report_token"),
    UniqueConstraint("reference", name="uq_ambassador_report_reference"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_reference() -> str:
    """A short reference staff can read aloud: AMB- and eight letters/digits."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "AMB-" + "".join(secrets.choice(alphabet) for _ in range(8))


def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    for key in ("payload", "progress"):
        try:
            d[key] = json.loads(d.get(key) or "{}")
        except ValueError:
            d[key] = {}
    return d


def next_after(attempts: int, now: datetime) -> Optional[datetime]:
    """When the next attempt is due after ``attempts`` failures; None when the
    backoff is used up and the row is left failed."""
    if attempts > len(BACKOFF):
        return None
    return now + BACKOFF[max(0, attempts - 1)]


class ReportStore:
    """Postgres store."""

    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def capture(self, *, token: str, user_id: str, user_name: str,
                      mentor_profile_id: str, payload: dict[str, Any],
                      lease_seconds: int, now: Optional[datetime] = None
                      ) -> tuple[dict[str, Any], bool]:
        """Write the report; ``(row, created)``. A repeated submission token
        returns the first row and False, so a double press is one report.
        The new row is leased to the caller for ``lease_seconds``."""
        now = now or _now()
        row = {"id": str(uuid.uuid4()), "reference": new_reference(), "submission_token": token,
               "user_id": user_id, "user_name": user_name or "",
               "mentor_profile_id": mentor_profile_id, "payload": json.dumps(payload),
               "status": PENDING, "attempts": 0, "next_attempt_at": now,
               "lease_until": now + timedelta(seconds=lease_seconds), "progress": "{}",
               "created_at": now, "updated_at": now}
        async with self._engine.begin() as conn:
            got = (await conn.execute(
                pg_insert(ambassador_report).values(**row)
                .on_conflict_do_nothing(constraint="uq_ambassador_report_token")
                .returning(ambassador_report))).mappings().first()
            if got is not None:
                return _row(got), True
            old = (await conn.execute(select(ambassador_report).where(
                ambassador_report.c.submission_token == token))).mappings().first()
        return _row(old), False

    async def get(self, report_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            got = (await conn.execute(select(ambassador_report).where(
                ambassador_report.c.id == report_id))).mappings().first()
        return _row(got) if got else None

    async def claim_due(self, limit: int, lease_seconds: int,
                        now: Optional[datetime] = None) -> list[dict[str, Any]]:
        """Pending rows due an attempt and not leased, leased to this caller."""
        now = now or _now()
        async with self._engine.begin() as conn:
            ids = [r[0] for r in (await conn.execute(
                select(ambassador_report.c.id).where(and_(
                    ambassador_report.c.status == PENDING,
                    ambassador_report.c.next_attempt_at <= now,
                    or_(ambassador_report.c.lease_until.is_(None),
                        ambassador_report.c.lease_until < now)))
                .order_by(ambassador_report.c.created_at).limit(limit)
                .with_for_update(skip_locked=True))).all()]
            if not ids:
                return []
            rows = (await conn.execute(
                update(ambassador_report).where(ambassador_report.c.id.in_(ids))
                .values(lease_until=now + timedelta(seconds=lease_seconds), updated_at=now)
                .returning(ambassador_report))).mappings().all()
        return [_row(r) for r in rows]

    async def save_progress(self, report_id: str, progress: dict[str, Any]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(ambassador_report)
                               .where(ambassador_report.c.id == report_id)
                               .values(progress=json.dumps(progress), updated_at=_now()))

    async def delivered(self, report_id: str, activity_id: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(ambassador_report)
                               .where(ambassador_report.c.id == report_id)
                               .values(status=DELIVERED, activity_id=activity_id,
                                       lease_until=None, last_error=None, updated_at=_now()))

    async def failed_attempt(self, report_id: str, error: str,
                             now: Optional[datetime] = None) -> str:
        """Record a failed attempt; returns the new status."""
        now = now or _now()
        row = await self.get(report_id)
        attempts = int((row or {}).get("attempts") or 0) + 1
        due = next_after(attempts, now)
        status = PENDING if due is not None else FAILED
        async with self._engine.begin() as conn:
            await conn.execute(update(ambassador_report)
                               .where(ambassador_report.c.id == report_id)
                               .values(status=status, attempts=attempts,
                                       next_attempt_at=due or now, lease_until=None,
                                       last_error=(error or "")[:1000], updated_at=now))
        return status

    async def undelivered_for(self, user_id: str) -> list[dict[str, Any]]:
        """The mentor's reports not in the CRM yet, newest first: My activity
        shows them as "Saving" so a report never seems lost."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(ambassador_report).where(and_(
                ambassador_report.c.user_id == user_id,
                ambassador_report.c.status != DELIVERED))
                .order_by(ambassador_report.c.created_at.desc()).limit(50))).mappings().all()
        return [_row(r) for r in rows]


_stores: dict[str, ReportStore] = {}


def report_store(settings: Settings) -> Optional[ReportStore]:
    """One store per process when a database is configured, else None."""
    if not settings.store_enabled:
        return None
    store = _stores.get(settings.database_url)
    if store is None:
        store = _stores[settings.database_url] = ReportStore(settings.database_url)
    return store
