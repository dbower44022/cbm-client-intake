"""Postgres cache for computed analytics results (Analytics Phase A).

Metrics that sweep the CRM are expensive, so their results are materialized here
and refreshed on a per-metric cadence by the worker; a cache miss recomputes
live and fills the row. Keyed by ``(metric_key, context_key, range_key)``:

  * ``metric_key``  — the registered metric
  * ``context_key`` — ``"system"`` for org-wide metrics; ``"CMentorProfile:<id>"``
                      for a record-scoped metric (Phase C)
  * ``range_key``   — the time-range the result is for (``"all"`` for a
                      non-time-aware metric; ``"last30d"`` / ``"custom:…"`` etc.)

Own ``MetaData`` + engine, like :mod:`comms.store` / :mod:`docs.store`. The table
is created by Alembic migration ``0021_analytics_cache``. Inert
(``make_analytics_store`` → ``None``) without ``DATABASE_URL``, so the app runs
LIVE-ONLY (no materialization) until a database is attached — analytics still
render, just recomputed each view.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    Text,
    delete,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import make_async_engine

metadata = MetaData()

analytics_cache = Table(
    "analytics_cache",
    metadata,
    Column("metric_key", String(128), primary_key=True),
    Column("context_key", String(160), primary_key=True),
    Column("range_key", String(96), primary_key=True),
    Column("result", Text, nullable=False),  # JSON-encoded panel-result payload
    Column("computed_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Index("ix_analytics_cache_expires", "expires_at"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AnalyticsStore:
    """analytics_cache persistence (one engine, like CommsStore/DocumentStore)."""

    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def get_cached(
        self, metric_key: str, context_key: str, range_key: str
    ) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(analytics_cache).where(
                        analytics_cache.c.metric_key == metric_key,
                        analytics_cache.c.context_key == context_key,
                        analytics_cache.c.range_key == range_key,
                    )
                )
            ).mappings().first()
        if row is None:
            return None
        return {
            "result": json.loads(row["result"]),
            "computed_at": row["computed_at"],
            "expires_at": row["expires_at"],
        }

    async def put_cached(
        self,
        metric_key: str,
        context_key: str,
        range_key: str,
        *,
        result: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        now = _now()
        payload = json.dumps(result)
        stmt = (
            pg_insert(analytics_cache)
            .values(
                metric_key=metric_key,
                context_key=context_key,
                range_key=range_key,
                result=payload,
                computed_at=now,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=[
                    analytics_cache.c.metric_key,
                    analytics_cache.c.context_key,
                    analytics_cache.c.range_key,
                ],
                set_={"result": payload, "computed_at": now, "expires_at": expires_at},
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def due(self, *, now: Optional[datetime] = None) -> list[dict[str, str]]:
        """Cache keys whose ``expires_at`` has passed — refresh candidates."""
        now = now or _now()
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        analytics_cache.c.metric_key,
                        analytics_cache.c.context_key,
                        analytics_cache.c.range_key,
                    ).where(analytics_cache.c.expires_at <= now)
                )
            ).all()
        return [
            {"metricKey": r.metric_key, "contextKey": r.context_key, "rangeKey": r.range_key}
            for r in rows
        ]

    async def invalidate(
        self,
        metric_key: str,
        context_key: Optional[str] = None,
        range_key: Optional[str] = None,
    ) -> None:
        conds = [analytics_cache.c.metric_key == metric_key]
        if context_key is not None:
            conds.append(analytics_cache.c.context_key == context_key)
        if range_key is not None:
            conds.append(analytics_cache.c.range_key == range_key)
        async with self._engine.begin() as conn:
            await conn.execute(delete(analytics_cache).where(*conds))


class MemoryAnalyticsStore:
    """In-memory AnalyticsStore for tests (mirrors the async interface)."""

    def __init__(self) -> None:
        # (metric_key, context_key, range_key) -> {result, computed_at, expires_at}
        self._rows: dict[tuple[str, str, str], dict[str, Any]] = {}

    async def create_all(self) -> None:  # parity, no-op
        return None

    async def dispose(self) -> None:  # parity, no-op
        return None

    async def get_cached(self, metric_key, context_key, range_key):
        row = self._rows.get((metric_key, context_key, range_key))
        return dict(row) if row else None

    async def put_cached(self, metric_key, context_key, range_key, *, result, expires_at):
        self._rows[(metric_key, context_key, range_key)] = {
            "result": json.loads(json.dumps(result)),  # decouple from caller's dict
            "computed_at": _now(),
            "expires_at": expires_at,
        }

    async def due(self, *, now: Optional[datetime] = None):
        now = now or _now()
        return [
            {"metricKey": k[0], "contextKey": k[1], "rangeKey": k[2]}
            for k, v in self._rows.items()
            if v["expires_at"] <= now
        ]

    async def invalidate(self, metric_key, context_key=None, range_key=None):
        for key in list(self._rows):
            if key[0] != metric_key:
                continue
            if context_key is not None and key[1] != context_key:
                continue
            if range_key is not None and key[2] != range_key:
                continue
            self._rows.pop(key, None)


def make_analytics_store(settings: Settings) -> Optional[AnalyticsStore]:
    """An AnalyticsStore when a database is configured, else None (live-only)."""
    if not settings.store_enabled:
        return None
    return AnalyticsStore(settings.database_url)
