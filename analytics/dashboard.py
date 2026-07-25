"""The code-seeded System Analytics dashboard (Analytics Phase A flagship).

Five metrics spanning all four panel types, all sourced from EspoCRM:

  * Total Active Mentors            — scalar (cheap: list total, live)
  * Active Client Engagements       — scalar (cheap: list total, live)
  * New client engagements / month  — series  (sweep + month buckets, cached)
  * Engagements by status           — breakdown (sweep + group-by, cached)
  * Oldest unassigned engagements   — rows   (Submitted, oldest first, cached)

Importing this module registers the metrics and the ``system-overview`` page.
Phase B adds the in-app builder + DB-backed metrics; the panel/page layer here
is the same shape those will populate.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any, Optional

from .registry import (
    SHAPE_BREAKDOWN,
    SHAPE_ROWS,
    SHAPE_SCALAR,
    SHAPE_SERIES,
    VIZ_BAR,
    VIZ_LINE,
    VIZ_STAT,
    VIZ_TABLE,
    MetricContext,
    PageSpec,
    PanelSpec,
    breakdown,
    metric,
    register_page,
    rows,
    scalar,
    series,
)

# Engagement statuses considered "active" for the org-wide count. Kept local so
# the metric doesn't couple to the comms/assignments status sets (a power user
# can refine this in the Phase B builder).
ACTIVE_ENGAGEMENT_STATUSES = ("Active", "Assigned", "Pending Acceptance", "On-Hold")

_SWEEP_PAGE = 200
_SWEEP_MAX_PAGES = 50  # 10k-row safety cap; a system entity this large ⇒ revisit


# --- CRM helpers -------------------------------------------------------------
async def _count(espo, entity: str, where: Optional[list[dict[str, Any]]]) -> int:
    """A cheap server-side count via the list ``total`` envelope (maxSize=1)."""
    env = await espo.list(entity, where=where, select="id", max_size=1)
    return int(env.get("total") or 0)


async def _sweep(
    espo,
    entity: str,
    select: str,
    *,
    where: Optional[list[dict[str, Any]]] = None,
    order_by: Optional[str] = None,
    order: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Page through an entity, aggregating in Python (the mentor-metrics pattern).
    Bounded by ``_SWEEP_MAX_PAGES``; these metrics are cached, so the sweep runs
    on the worker cadence, not per view."""
    out: list[dict[str, Any]] = []
    offset = 0
    for _ in range(_SWEEP_MAX_PAGES):
        env = await espo.list(
            entity,
            where=where,
            select=select,
            max_size=_SWEEP_PAGE,
            offset=offset,
            order_by=order_by,
            order=order,
        )
        batch = env.get("list") or []
        out.extend(batch)
        if len(batch) < _SWEEP_PAGE:
            break
        offset += _SWEEP_PAGE
    return out


# --- date helpers ------------------------------------------------------------
def _parse_crm_dt(value: Optional[str]) -> Optional[datetime]:
    """EspoCRM datetimes are UTC ``YYYY-MM-DD HH:MM:SS`` (date-only for dates)."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if " " in text else text[:10], fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    return None


def _month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _month_label(year: int, month: int) -> str:
    return f"{calendar.month_abbr[month]} {year}"


def _months_between(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """Inclusive list of (year, month) from start's month to end's month."""
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _days_since(value: Optional[str], now: Optional[datetime] = None) -> Optional[int]:
    dt = _parse_crm_dt(value)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max((now - dt).days, 0)


def _fmt_date(value: Optional[str]) -> str:
    dt = _parse_crm_dt(value)
    return dt.strftime("%b %-d, %Y") if dt else ""


# --- metrics -----------------------------------------------------------------
@metric(
    key="active_mentors",
    name="Total Active Mentors",
    shape=SHAPE_SCALAR,
    default_viz=VIZ_STAT,
    cache_mode="live",
    description="Mentors whose profile status is Active.",
)
async def _active_mentors(ctx: MetricContext):
    n = await _count(
        ctx.espo,
        "CMentorProfile",
        [{"type": "equals", "attribute": "mentorStatus", "value": "Active"}],
    )
    return scalar(n, unit="mentors")


@metric(
    key="active_engagements",
    name="Active Client Engagements",
    shape=SHAPE_SCALAR,
    default_viz=VIZ_STAT,
    cache_mode="live",
    description="Client engagements in an active status.",
)
async def _active_engagements(ctx: MetricContext):
    n = await _count(
        ctx.espo,
        "CEngagement",
        [
            {
                "type": "in",
                "attribute": "engagementStatus",
                "value": list(ACTIVE_ENGAGEMENT_STATUSES),
            }
        ],
    )
    return scalar(n, unit="engagements")


@metric(
    key="engagements_per_month",
    name="New client engagements per month",
    shape=SHAPE_SERIES,
    default_viz=VIZ_LINE,
    cache_mode="cached",
    refresh_seconds=3600,
    time_aware=True,
    description="Count of engagements created each month, over the selected range.",
)
async def _engagements_per_month(ctx: MetricContext):
    records = await _sweep(
        ctx.espo, "CEngagement", "createdAt", order_by="createdAt", order="asc"
    )
    tr = ctx.time_range
    start = tr.start if tr else None
    end = (tr.end if tr and tr.end else datetime.now(timezone.utc))

    counts: dict[str, int] = {}
    earliest: Optional[datetime] = None
    for r in records:
        dt = _parse_crm_dt(r.get("createdAt"))
        if dt is None:
            continue
        if start and dt < start:
            continue
        if dt > end:
            continue
        counts[_month_key(dt)] = counts.get(_month_key(dt), 0) + 1
        if earliest is None or dt < earliest:
            earliest = dt

    axis_start = start or earliest
    if axis_start is None:
        return series([])
    points = []
    for (y, m) in _months_between(axis_start, end):
        key = f"{y:04d}-{m:02d}"
        points.append(
            {"bucket": key, "label": _month_label(y, m), "value": counts.get(key, 0)}
        )
    return series(points)


@metric(
    key="engagements_by_status",
    name="Engagements by status",
    shape=SHAPE_BREAKDOWN,
    default_viz=VIZ_BAR,
    cache_mode="cached",
    refresh_seconds=3600,
    description="Current count of engagements grouped by status.",
)
async def _engagements_by_status(ctx: MetricContext):
    records = await _sweep(ctx.espo, "CEngagement", "engagementStatus")
    counts: dict[str, int] = {}
    for r in records:
        label = r.get("engagementStatus") or "(none)"
        counts[label] = counts.get(label, 0) + 1
    items = [
        {"label": k, "value": v}
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return breakdown(items)


@metric(
    key="oldest_unassigned_engagements",
    name="Oldest unassigned engagements",
    shape=SHAPE_ROWS,
    default_viz=VIZ_TABLE,
    cache_mode="cached",
    refresh_seconds=1800,
    description="Submitted engagements awaiting a mentor, oldest first.",
)
async def _oldest_unassigned(ctx: MetricContext):
    records = await _sweep(
        ctx.espo,
        "CEngagement",
        "name,createdAt,engagementStatus",
        where=[{"type": "equals", "attribute": "engagementStatus", "value": "Submitted"}],
        order_by="createdAt",
        order="asc",
    )
    records = records[:10]
    columns = [
        {"key": "name", "label": "Engagement", "link": "record"},
        {"key": "created", "label": "Created"},
        {"key": "days", "label": "Days waiting", "align": "right"},
    ]
    out = []
    for r in records:
        out.append(
            {
                "name": r.get("name") or "(unnamed engagement)",
                "created": _fmt_date(r.get("createdAt")),
                "days": _days_since(r.get("createdAt")),
                "entity": "CEngagement",
                "recordId": r.get("id"),
            }
        )
    return rows(columns, out)


# --- the seeded system page --------------------------------------------------
register_page(
    PageSpec(
        key="system-overview",
        title="System Analytics",
        subtitle="Organization-wide activity across mentors, clients, and engagements.",
        scope="system",
        portal_dashboard=True,
        default_range="last12mo",
        panels=[
            PanelSpec("active_mentors", "Total Active Mentors", "active_mentors", VIZ_STAT, width=3),
            PanelSpec("active_engagements", "Active Client Engagements", "active_engagements", VIZ_STAT, width=3),
            PanelSpec("engagements_per_month", "New client engagements per month", "engagements_per_month", VIZ_LINE, width=6),
            PanelSpec("engagements_by_status", "Engagements by status", "engagements_by_status", VIZ_BAR, width=6),
            PanelSpec("oldest_unassigned", "Oldest unassigned engagements", "oldest_unassigned_engagements", VIZ_TABLE, width=6),
        ],
    )
)
