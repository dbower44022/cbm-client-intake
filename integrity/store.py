"""Fault state for the login integrity check — plan § 4.2, step 4a.

One row per fault the check found, in the application's database (migration
``0041_login_integrity_fault``), so a deploy resends nothing and a fault the
check no longer finds closes itself. A fault found again after it closed is a
new row: its history stays, and it reads as new.

Condition 7 (a login with no mentor profile signs in, 4c) is an event, not a
standing state: its key carries the day, so it is recorded at most once per
login per day, and the next daily run closes the ones from earlier days.

Training data on the sandbox: the table is in ``RESET_TABLES``, because its
faults point at CRM records the nightly restore puts back. On crm-test every
fault therefore reads as new each morning; that is expected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, Text, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import make_async_engine, metadata

from .check import DAILY

login_integrity_fault = Table(
    "login_integrity_fault",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("fault_key", String(300), nullable=False),
    Column("condition", Integer, nullable=False),
    Column("summary", Text, nullable=False),
    Column("mentors", JSONB),
    Column("login", JSONB),
    Column("first_seen", DateTime(timezone=True), nullable=False),
    Column("last_seen", DateTime(timezone=True), nullable=False),
    Column("closed_at", DateTime(timezone=True)),
    Column("ack_by_id", String(32)),
    Column("ack_by", String(128)),
    Column("ack_at", DateTime(timezone=True)),
    Column("ack_note", Text),
    Column("notified_at", DateTime(timezone=True)),
    Index("uq_login_integrity_fault_open", "fault_key", unique=True,
          postgresql_where=text("closed_at IS NULL")),
    Index("ix_login_integrity_fault_closed", "closed_at"),
)

#: A condition-7 row older than this is closed by the next daily run.
SIGNIN_EVENT_LIFE = timedelta(hours=20)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(row: Any) -> dict[str, Any]:
    return dict(row)


class IntegrityStore:
    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def apply_run(self, found: list[dict[str, Any]],
                        now: Optional[datetime] = None) -> dict[str, Any]:
        """Bring the open faults in line with one complete run of the daily
        conditions: insert the new, refresh the known, close the gone.
        Returns ``{"new": [...], "closed": [...], "open": [...]}``."""
        now = now or _now()
        t = login_integrity_fault
        by_key = {f["key"]: f for f in found}
        new: list[dict[str, Any]] = []
        closed: list[dict[str, Any]] = []
        async with self._engine.begin() as conn:
            open_rows = (await conn.execute(
                select(t).where(t.c.closed_at.is_(None))
            )).mappings().all()
            known = {r["fault_key"]: r for r in open_rows}
            for r in open_rows:
                gone = (r["condition"] in DAILY and r["fault_key"] not in by_key) or (
                    r["condition"] not in DAILY
                    and r["first_seen"] <= now - SIGNIN_EVENT_LIFE)
                if gone:
                    await conn.execute(update(t).where(t.c.id == r["id"]).values(closed_at=now))
                    closed.append(dict(r))
            for key, f in by_key.items():
                values = {"summary": f["summary"], "mentors": f.get("mentors") or [],
                          "login": f.get("login"), "last_seen": now}
                if key in known:
                    await conn.execute(update(t).where(t.c.id == known[key]["id"]).values(**values))
                else:
                    row = {"id": str(uuid.uuid4()), "fault_key": key,
                           "condition": f["condition"], "first_seen": now, **values}
                    await conn.execute(t.insert().values(**row))
                    new.append(row)
        return {"new": new, "closed": closed, "open": await self.open_faults()}

    async def open_faults(self) -> list[dict[str, Any]]:
        t = login_integrity_fault
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(t).where(t.c.closed_at.is_(None))
                .order_by(t.c.condition, t.c.first_seen)
            )).mappings().all()
        return [_public(r) for r in rows]

    async def open_count(self, *, unacknowledged: bool = True) -> int:
        t = login_integrity_fault
        q = select(func.count()).select_from(t).where(t.c.closed_at.is_(None))
        if unacknowledged:
            q = q.where(t.c.ack_at.is_(None))
        async with self._engine.begin() as conn:
            return int((await conn.execute(q)).scalar_one())

    async def get(self, fault_id: str) -> Optional[dict[str, Any]]:
        t = login_integrity_fault
        async with self._engine.begin() as conn:
            row = (await conn.execute(select(t).where(t.c.id == fault_id))).mappings().first()
        return _public(row) if row else None

    async def acknowledge(self, fault_id: str, *, by_id: str, by: str, note: str,
                          now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
        """Mark an OPEN fault "known — being handled". None when there is no
        such open fault (closed meanwhile, or never existed)."""
        t = login_integrity_fault
        async with self._engine.begin() as conn:
            res = await conn.execute(
                update(t).where(t.c.id == fault_id, t.c.closed_at.is_(None))
                .values(ack_by_id=by_id or None, ack_by=by or None,
                        ack_at=now or _now(), ack_note=note or None)
            )
        if not res.rowcount:
            return None
        return await self.get(fault_id)

    async def record_event(self, fault: dict[str, Any],
                           now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
        """Record a condition-7 sign-in once. The row, or None when the same key
        is already open (this login was reported today)."""
        now = now or _now()
        row = {"id": str(uuid.uuid4()), "fault_key": fault["key"],
               "condition": fault["condition"], "summary": fault["summary"],
               "mentors": fault.get("mentors") or [], "login": fault.get("login"),
               "first_seen": now, "last_seen": now}
        t = login_integrity_fault
        async with self._engine.begin() as conn:
            res = await conn.execute(
                pg_insert(t).values(**row)
                .on_conflict_do_nothing(index_elements=["fault_key"],
                                        index_where=text("closed_at IS NULL"))
            )
        return row if res.rowcount else None

    async def mark_notified(self, ids: list[str], now: Optional[datetime] = None) -> None:
        if not ids:
            return
        t = login_integrity_fault
        async with self._engine.begin() as conn:
            await conn.execute(update(t).where(t.c.id.in_(ids)).values(notified_at=now or _now()))


_store: Optional[IntegrityStore] = None
_store_url: Optional[str] = None


def get_store(settings: Settings) -> Optional[IntegrityStore]:
    """One store per process (root CLAUDE.md: a store owns a connection pool;
    building one per request exhausted crm-test's database). None without a
    database."""
    global _store, _store_url
    if not settings.database_url:
        return None
    if _store is None or _store_url != settings.database_url:
        _store = IntegrityStore(settings.database_url)
        _store_url = settings.database_url
    return _store
