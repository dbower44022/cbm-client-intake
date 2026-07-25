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
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
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


# --- definition tables (Phase B) --------------------------------------------
# The reusable metric library. Builder metrics (source='crm') store their
# entity + filters + aggregation in `definition`; panels/pages reference a
# metric by `key`, uniformly with code-registered metrics.
analytics_metric = Table(
    "analytics_metric",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("key", String(128), nullable=False, unique=True),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("source", String(16), nullable=False, server_default="crm"),
    Column("result_shape", String(16), nullable=False),
    Column("default_viz", String(16), nullable=False),
    Column("entity", String(64)),
    Column("definition", Text, nullable=False),          # JSON {filters, aggregation, time_field}
    Column("applies_to", Text, nullable=False, server_default='["system"]'),  # JSON list
    Column("context_param", String(64)),
    Column("cache_mode", String(16), nullable=False, server_default="cached"),
    Column("refresh_seconds", Integer, nullable=False, server_default="0"),
    Column("time_aware", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by", String(128)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(128)),
)

# Admin-curated pages. Panels are stored INLINE as a JSON list on the page
# (each = {title, metric_key, viz, width, visibility:[teams], config:{}}) — a
# deliberate simplification over a separate reusable-panel table; metrics are
# the reusable unit, panels are cheap to recreate.
analytics_page = Table(
    "analytics_page",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("key", String(128), nullable=False, unique=True),
    Column("scope", String(64), nullable=False, server_default="system"),
    Column("title", String(255), nullable=False),
    Column("subtitle", Text),
    Column("team_gate", Text, nullable=False, server_default="[]"),   # JSON list
    Column("portal_dashboard", Boolean, nullable=False, server_default="false"),
    Column("default_range", String(32), nullable=False, server_default="last12mo"),
    Column("panels", Text, nullable=False, server_default="[]"),      # JSON list
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by", String(128)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(128)),
)

# The definition columns that carry JSON text (decoded on read).
_METRIC_JSON = ("definition", "applies_to")
_PAGE_JSON = ("team_gate", "panels")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _decode(row: dict, json_cols) -> dict:
    out = dict(row)
    for col in json_cols:
        val = out.get(col)
        if isinstance(val, str):
            try:
                out[col] = json.loads(val)
            except (ValueError, TypeError):
                out[col] = None
    return out


def _encode_metric(values: dict) -> dict:
    out = dict(values)
    for col in _METRIC_JSON:
        if col in out and not isinstance(out[col], str):
            out[col] = json.dumps(out[col])
    return out


def _encode_page(values: dict) -> dict:
    out = dict(values)
    for col in _PAGE_JSON:
        if col in out and not isinstance(out[col], str):
            out[col] = json.dumps(out[col])
    return out


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


    # --- metric library (Phase B) -------------------------------------------
    async def create_metric(self, values: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        row = _encode_metric(values)
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", now)
        row["updated_at"] = now
        async with self._engine.begin() as conn:
            await conn.execute(analytics_metric.insert().values(**row))
        return await self.get_metric(row["id"])

    async def update_metric(self, metric_id: str, values: dict[str, Any]) -> Optional[dict[str, Any]]:
        row = _encode_metric(values)
        row["updated_at"] = _now()
        async with self._engine.begin() as conn:
            res = await conn.execute(
                analytics_metric.update().where(analytics_metric.c.id == metric_id).values(**row)
            )
            if res.rowcount == 0:
                return None
        return await self.get_metric(metric_id)

    async def get_metric(self, metric_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            r = (await conn.execute(
                select(analytics_metric).where(analytics_metric.c.id == metric_id)
            )).mappings().first()
        return _decode(dict(r), _METRIC_JSON) if r else None

    async def get_metric_by_key(self, key: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            r = (await conn.execute(
                select(analytics_metric).where(analytics_metric.c.key == key)
            )).mappings().first()
        return _decode(dict(r), _METRIC_JSON) if r else None

    async def list_metrics(self) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(analytics_metric).order_by(analytics_metric.c.name)
            )).mappings().all()
        return [_decode(dict(r), _METRIC_JSON) for r in rows]

    async def delete_metric(self, metric_id: str) -> bool:
        async with self._engine.begin() as conn:
            res = await conn.execute(
                delete(analytics_metric).where(analytics_metric.c.id == metric_id)
            )
        return res.rowcount > 0

    # --- pages (Phase B) ----------------------------------------------------
    async def create_page(self, values: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        row = _encode_page(values)
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", now)
        row["updated_at"] = now
        async with self._engine.begin() as conn:
            await conn.execute(analytics_page.insert().values(**row))
        return await self.get_page(row["id"])

    async def update_page(self, page_id: str, values: dict[str, Any]) -> Optional[dict[str, Any]]:
        row = _encode_page(values)
        row["updated_at"] = _now()
        async with self._engine.begin() as conn:
            res = await conn.execute(
                analytics_page.update().where(analytics_page.c.id == page_id).values(**row)
            )
            if res.rowcount == 0:
                return None
        return await self.get_page(page_id)

    async def get_page(self, page_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            r = (await conn.execute(
                select(analytics_page).where(analytics_page.c.id == page_id)
            )).mappings().first()
        return _decode(dict(r), _PAGE_JSON) if r else None

    async def get_page_by_key(self, key: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            r = (await conn.execute(
                select(analytics_page).where(analytics_page.c.key == key)
            )).mappings().first()
        return _decode(dict(r), _PAGE_JSON) if r else None

    async def list_pages(self) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(analytics_page).order_by(analytics_page.c.title)
            )).mappings().all()
        return [_decode(dict(r), _PAGE_JSON) for r in rows]

    async def delete_page(self, page_id: str) -> bool:
        async with self._engine.begin() as conn:
            res = await conn.execute(
                delete(analytics_page).where(analytics_page.c.id == page_id)
            )
        return res.rowcount > 0

    async def metric_key_in_use(self, key: str) -> list[str]:
        """Page keys whose inline panels reference this metric key (delete guard)."""
        pages = await self.list_pages()
        return [
            p["key"] for p in pages
            if any((pan.get("metric_key") == key) for pan in (p.get("panels") or []))
        ]


class MemoryAnalyticsStore:
    """In-memory AnalyticsStore for tests (mirrors the async interface)."""

    def __init__(self) -> None:
        # (metric_key, context_key, range_key) -> {result, computed_at, expires_at}
        self._rows: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._metrics: dict[str, dict[str, Any]] = {}   # id -> decoded metric
        self._pages: dict[str, dict[str, Any]] = {}     # id -> decoded page

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

    # --- metric library ------------------------------------------------------
    async def create_metric(self, values):
        now = _now()
        row = dict(values)
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", now)
        row["updated_at"] = now
        self._metrics[row["id"]] = row
        return dict(row)

    async def update_metric(self, metric_id, values):
        row = self._metrics.get(metric_id)
        if row is None:
            return None
        row.update(values)
        row["updated_at"] = _now()
        return dict(row)

    async def get_metric(self, metric_id):
        row = self._metrics.get(metric_id)
        return dict(row) if row else None

    async def get_metric_by_key(self, key):
        for row in self._metrics.values():
            if row.get("key") == key:
                return dict(row)
        return None

    async def list_metrics(self):
        return [dict(r) for r in sorted(self._metrics.values(), key=lambda r: r.get("name") or "")]

    async def delete_metric(self, metric_id):
        return self._metrics.pop(metric_id, None) is not None

    # --- pages ---------------------------------------------------------------
    async def create_page(self, values):
        now = _now()
        row = dict(values)
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", now)
        row["updated_at"] = now
        self._pages[row["id"]] = row
        return dict(row)

    async def update_page(self, page_id, values):
        row = self._pages.get(page_id)
        if row is None:
            return None
        row.update(values)
        row["updated_at"] = _now()
        return dict(row)

    async def get_page(self, page_id):
        row = self._pages.get(page_id)
        return dict(row) if row else None

    async def get_page_by_key(self, key):
        for row in self._pages.values():
            if row.get("key") == key:
                return dict(row)
        return None

    async def list_pages(self):
        return [dict(r) for r in sorted(self._pages.values(), key=lambda r: r.get("title") or "")]

    async def delete_page(self, page_id):
        return self._pages.pop(page_id, None) is not None

    async def metric_key_in_use(self, key):
        return [
            p["key"] for p in self._pages.values()
            if any(pan.get("metric_key") == key for pan in (p.get("panels") or []))
        ]


def make_analytics_store(settings: Settings) -> Optional[AnalyticsStore]:
    """An AnalyticsStore when a database is configured, else None (live-only)."""
    if not settings.store_enabled:
        return None
    return AnalyticsStore(settings.database_url)
