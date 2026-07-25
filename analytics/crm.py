"""Shared CRM aggregation helpers for analytics metrics.

The paginated-sweep + cheap-count primitives (the ``mentor_engagement_metrics``
pattern) and date/bucket helpers, used by both the code-seeded dashboard
(:mod:`analytics.dashboard`) and the builder-metric executor
(:mod:`analytics.builder`).
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any, Optional

SWEEP_PAGE = 200
SWEEP_MAX_PAGES = 50  # 10k-row safety cap; a system entity this large ⇒ revisit


async def count(espo, entity: str, where: Optional[list[dict[str, Any]]]) -> int:
    """A cheap server-side count via the list ``total`` envelope (maxSize=1)."""
    env = await espo.list(entity, where=where, select="id", max_size=1)
    return int(env.get("total") or 0)


async def sweep(
    espo,
    entity: str,
    select: str,
    *,
    where: Optional[list[dict[str, Any]]] = None,
    order_by: Optional[str] = None,
    order: Optional[str] = None,
    max_pages: int = SWEEP_MAX_PAGES,
) -> list[dict[str, Any]]:
    """Page through an entity, aggregating in Python. Bounded by ``max_pages``."""
    out: list[dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        env = await espo.list(
            entity, where=where, select=select, max_size=SWEEP_PAGE,
            offset=offset, order_by=order_by, order=order,
        )
        batch = env.get("list") or []
        out.extend(batch)
        if len(batch) < SWEEP_PAGE:
            break
        offset += SWEEP_PAGE
    return out


# --- date helpers ------------------------------------------------------------
def parse_crm_dt(value: Optional[str]) -> Optional[datetime]:
    """EspoCRM datetimes are UTC ``YYYY-MM-DD HH:MM:SS`` (date-only for dates)."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            core = text[:19] if " " in text else text[:10]
            return datetime.strptime(core, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def month_label(year: int, month: int) -> str:
    return f"{calendar.month_abbr[month]} {year}"


def months_between(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """Inclusive (year, month) list from start's month to end's month."""
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def days_since(value: Optional[str], now: Optional[datetime] = None) -> Optional[int]:
    dt = parse_crm_dt(value)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max((now - dt).days, 0)


def fmt_date(value: Optional[str]) -> str:
    dt = parse_crm_dt(value)
    return dt.strftime("%b %-d, %Y") if dt else ""


def fill_month_series(counts: dict[str, float], time_range) -> list[dict[str, Any]]:
    """Render a month → value map as an ordered point list over the time range's
    window, filling empty months with 0. Keys are ``"YYYY-MM"``. When the range
    is unbounded (start None), the axis starts at the earliest key present.
    Months outside [axis_start, end] are naturally windowed out."""
    start = getattr(time_range, "start", None)
    end = getattr(time_range, "end", None) or datetime.now(timezone.utc)
    axis_start = start
    if axis_start is None:
        keys = sorted(k for k in counts if k)
        if not keys:
            return []
        axis_start = datetime(int(keys[0][:4]), int(keys[0][5:7]), 1, tzinfo=timezone.utc)
    points = []
    for (y, m) in months_between(axis_start, end):
        key = f"{y:04d}-{m:02d}"
        points.append({"bucket": key, "label": month_label(y, m), "value": counts.get(key, 0)})
    return points


def bucket_by_month(records: list[dict[str, Any]], field: str, time_range) -> list[dict[str, Any]]:
    """Count records per calendar month over the time range's window, filling
    empty months with 0. ``time_range`` may be None (all time)."""
    counts: dict[str, float] = {}
    for r in records:
        dt = parse_crm_dt(r.get(field))
        if dt is None:
            continue
        counts[month_key(dt)] = counts.get(month_key(dt), 0) + 1
    return fill_month_series(counts, time_range)
