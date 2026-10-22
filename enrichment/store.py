"""The AI research runs' own tables (build plan phase 2 § 3; migration
``alembic/versions/0033_enrichment_run.py``). Working state, so it lives in
the application database; the findings themselves are CRM records.

A run is QUEUED when a person starts it, RUNNING while the worker takes its
items two at a time, and DONE (or FAILED) when no item is left. An item is
``queued`` until the worker claims it (``running``), then ``done`` or
``failed`` with what it cost. A worker that restarts mid-item finds it
``running`` and older than the lease, and takes it again: the engine never
writes a finding twice (it checks for the same finding first), so a retry
costs money but does not duplicate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Table, Text, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB

from core.config import Settings
from core.store import make_async_engine, metadata

RUN_QUEUED, RUN_RUNNING, RUN_DONE, RUN_FAILED = "queued", "running", "done", "failed"
ITEM_QUEUED, ITEM_RUNNING, ITEM_DONE, ITEM_FAILED = "queued", "running", "done", "failed"
#: An item left ``running`` this long is taken again (a worker died mid-call).
LEASE = timedelta(minutes=20)

enrichment_run = Table(
    "enrichment_run", metadata,
    Column("id", String(36), primary_key=True),
    Column("tier", String(32), nullable=False),
    Column("target_type", String(16), nullable=False),
    Column("total", Integer, nullable=False),
    Column("estimate", Float, nullable=False),
    Column("status", String(16), nullable=False),
    Column("model", String(64)),
    Column("started_by", String(128)),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("note", Text),
    Index("ix_enrichment_run_status", "status"),
)

enrichment_run_item = Table(
    "enrichment_run_item", metadata,
    Column("run_id", String(36), primary_key=True),
    Column("target_id", String(64), primary_key=True),
    Column("position", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("cost", Float, nullable=False, server_default="0"),
    Column("findings", Integer, nullable=False, server_default="0"),
    Column("detail", JSONB),
    Column("error", Text),
    Column("finished_at", DateTime(timezone=True)),
    Index("ix_enrichment_run_item_finished", "finished_at"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def month_start(now: Optional[datetime] = None) -> datetime:
    now = now or _now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class EnrichmentStore:
    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def create_run(self, *, tier: str, target_type: str, target_ids: list[str],
                         estimate: float, model: str, started_by: str) -> dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "tier": tier, "target_type": target_type,
               "total": len(target_ids), "estimate": float(estimate), "status": RUN_QUEUED,
               "model": model, "started_by": started_by, "started_at": _now(),
               "finished_at": None, "note": None}
        async with self._engine.begin() as conn:
            await conn.execute(enrichment_run.insert().values(**row))
            if target_ids:
                await conn.execute(enrichment_run_item.insert(), [
                    {"run_id": row["id"], "target_id": tid, "position": i, "status": ITEM_QUEUED,
                     "cost": 0.0, "findings": 0, "detail": None, "error": None, "finished_at": None}
                    for i, tid in enumerate(target_ids)])
        return row

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            run = (await conn.execute(select(enrichment_run).where(enrichment_run.c.id == run_id))).mappings().first()
            if not run:
                return None
            counts = (await conn.execute(
                select(enrichment_run_item.c.status, func.count(), func.coalesce(func.sum(enrichment_run_item.c.cost), 0.0),
                       func.coalesce(func.sum(enrichment_run_item.c.findings), 0))
                .where(enrichment_run_item.c.run_id == run_id)
                .group_by(enrichment_run_item.c.status))).all()
        out = dict(run)
        out["items"] = {s: int(n) for s, n, _, _ in counts}
        out["cost"] = float(sum(c for _, _, c, _ in counts))
        out["findings"] = int(sum(f for _, _, _, f in counts))
        return out

    async def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(enrichment_run).order_by(enrichment_run.c.started_at.desc())
                                       .limit(limit))).mappings().all()
        return [dict(r) for r in rows]

    async def month_spend(self, now: Optional[datetime] = None) -> float:
        """What the month's finished items cost, in dollars."""
        async with self._engine.begin() as conn:
            total = (await conn.execute(
                select(func.coalesce(func.sum(enrichment_run_item.c.cost), 0.0))
                .where(enrichment_run_item.c.finished_at >= month_start(now)))).scalar()
        return float(total or 0.0)

    async def queued_items(self) -> int:
        """Items started but not finished — reserved against the budget."""
        async with self._engine.begin() as conn:
            n = (await conn.execute(
                select(func.count()).select_from(enrichment_run_item)
                .where(enrichment_run_item.c.status.in_([ITEM_QUEUED, ITEM_RUNNING])))).scalar()
        return int(n or 0)

    async def average_item_cost(self, last: int = 50) -> Optional[float]:
        """The average cost of the last ``last`` finished items, or None."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(enrichment_run_item.c.cost)
                .where(enrichment_run_item.c.status == ITEM_DONE)
                .order_by(enrichment_run_item.c.finished_at.desc()).limit(last))).scalars().all()
        return (sum(rows) / len(rows)) if rows else None

    async def claim(self, limit: int, now: Optional[datetime] = None) -> list[dict[str, Any]]:
        """Take up to ``limit`` items to research: queued ones, or running ones
        whose lease ran out. Oldest run first, then list order."""
        now = now or _now()
        stale = now - LEASE
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(enrichment_run_item, enrichment_run.c.target_type, enrichment_run.c.model)
                .join(enrichment_run, enrichment_run.c.id == enrichment_run_item.c.run_id)
                .where(or_(enrichment_run_item.c.status == ITEM_QUEUED,
                           and_(enrichment_run_item.c.status == ITEM_RUNNING,
                                enrichment_run_item.c.finished_at < stale)))
                .order_by(enrichment_run.c.started_at, enrichment_run_item.c.position)
                .limit(limit).with_for_update(skip_locked=True, of=enrichment_run_item))).mappings().all()
            for r in rows:
                # finished_at doubles as the lease stamp while running.
                await conn.execute(update(enrichment_run_item).where(and_(
                    enrichment_run_item.c.run_id == r["run_id"], enrichment_run_item.c.target_id == r["target_id"]))
                    .values(status=ITEM_RUNNING, finished_at=now))
                await conn.execute(update(enrichment_run).where(and_(
                    enrichment_run.c.id == r["run_id"], enrichment_run.c.status == RUN_QUEUED))
                    .values(status=RUN_RUNNING))
        return [dict(r) for r in rows]

    async def finish_item(self, run_id: str, target_id: str, *, ok: bool, cost: float,
                          findings: int, detail: Optional[dict[str, Any]], error: Optional[str]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(enrichment_run_item).where(and_(
                enrichment_run_item.c.run_id == run_id, enrichment_run_item.c.target_id == target_id))
                .values(status=ITEM_DONE if ok else ITEM_FAILED, cost=float(cost), findings=int(findings),
                        detail=detail, error=(error or None), finished_at=_now()))
            left = (await conn.execute(select(func.count()).select_from(enrichment_run_item).where(and_(
                enrichment_run_item.c.run_id == run_id,
                enrichment_run_item.c.status.in_([ITEM_QUEUED, ITEM_RUNNING]))))).scalar()
            if not left:
                await conn.execute(update(enrichment_run).where(enrichment_run.c.id == run_id)
                                   .values(status=RUN_DONE, finished_at=_now()))

    async def target_pending(self, target_id: str) -> int:
        """How many of this record's research items are still queued or running."""
        async with self._engine.begin() as conn:
            n = (await conn.execute(select(func.count()).select_from(enrichment_run_item).where(and_(
                enrichment_run_item.c.target_id == target_id,
                enrichment_run_item.c.status.in_([ITEM_QUEUED, ITEM_RUNNING]))))).scalar()
        return int(n or 0)

    async def target_last(self, target_id: str) -> Optional[dict[str, Any]]:
        """The most recent finished research of this record."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(select(enrichment_run_item).where(and_(
                enrichment_run_item.c.target_id == target_id,
                enrichment_run_item.c.status.in_([ITEM_DONE, ITEM_FAILED])))
                .order_by(enrichment_run_item.c.finished_at.desc()).limit(1))).mappings().first()
        return dict(row) if row else None

    async def items(self, run_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(enrichment_run_item).where(enrichment_run_item.c.run_id == run_id)
                                       .order_by(enrichment_run_item.c.position))).mappings().all()
        return [dict(r) for r in rows]


def make_enrichment_store(settings: Settings) -> Optional[EnrichmentStore]:
    if not settings.store_enabled:
        return None
    return EnrichmentStore(settings.database_url)
