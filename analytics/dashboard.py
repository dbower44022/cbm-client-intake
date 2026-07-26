"""The code-seeded System Analytics dashboard (Analytics Phase A flagship).

Five metrics spanning all four panel types, all sourced from EspoCRM:

  * Total Active Mentors            — scalar (cheap: list total, live)
  * Active Client Engagements       — scalar (cheap: list total, live)
  * New client engagements / month  — series  (sweep + month buckets, cached)
  * Engagements by status           — breakdown (sweep + group-by, cached)
  * Oldest unassigned engagements   — rows   (Submitted, oldest first, cached)

Importing this module registers the metrics and the ``system-overview`` page.
Builder metrics (Phase B) execute the same CRM primitives via
:mod:`analytics.builder`; the panel/page layer here is the shape those fill.
"""

from __future__ import annotations

from . import crm
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


# --- metrics -----------------------------------------------------------------
@metric(
    key="active_mentors",
    name="Total Active Mentors",
    shape=SHAPE_SCALAR,
    default_viz=VIZ_STAT,
    cache_mode="live",
    description="Mentors whose profile status is Active.",
    builder_definition={
        "entity": "CMentorProfile",
        "filters": [{"type": "equals", "attribute": "mentorStatus", "value": "Active"}],
        "aggregation": {"kind": "count"},
    },
)
async def _active_mentors(ctx: MetricContext):
    n = await crm.count(
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
    builder_definition={
        "entity": "CEngagement",
        "filters": [{"type": "in", "attribute": "engagementStatus",
                     "value": list(ACTIVE_ENGAGEMENT_STATUSES)}],
        "aggregation": {"kind": "count"},
    },
)
async def _active_engagements(ctx: MetricContext):
    n = await crm.count(
        ctx.espo,
        "CEngagement",
        [{"type": "in", "attribute": "engagementStatus", "value": list(ACTIVE_ENGAGEMENT_STATUSES)}],
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
    builder_definition={
        "entity": "CEngagement", "filters": [],
        "aggregation": {"kind": "bucket"}, "time_field": "createdAt",
    },
)
async def _engagements_per_month(ctx: MetricContext):
    records = await crm.sweep(
        ctx.espo, "CEngagement", "createdAt", order_by="createdAt", order="asc"
    )
    return series(crm.bucket_by_month(records, "createdAt", ctx.time_range))


@metric(
    key="engagements_by_status",
    name="Engagements by status",
    shape=SHAPE_BREAKDOWN,
    default_viz=VIZ_BAR,
    cache_mode="cached",
    refresh_seconds=3600,
    description="Current count of engagements grouped by status.",
    builder_definition={
        "entity": "CEngagement", "filters": [],
        "aggregation": {"kind": "group_by", "field": "engagementStatus"},
    },
)
async def _engagements_by_status(ctx: MetricContext):
    records = await crm.sweep(ctx.espo, "CEngagement", "engagementStatus")
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
    builder_definition={
        "entity": "CEngagement",
        "filters": [{"type": "equals", "attribute": "engagementStatus", "value": "Submitted"}],
        "aggregation": {
            "kind": "list", "orderBy": "createdAt", "order": "asc", "limit": 10,
            "select": ["name", "createdAt"],
            "columns": [{"key": "name", "label": "Engagement", "link": "record"},
                        {"key": "createdAt", "label": "Created"}],
        },
    },
)
async def _oldest_unassigned(ctx: MetricContext):
    records = await crm.sweep(
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
        out.append({
            "name": r.get("name") or "(unnamed engagement)",
            "created": crm.fmt_date(r.get("createdAt")),
            "days": crm.days_since(r.get("createdAt")),
            "entity": "CEngagement",
            "recordId": r.get("id"),
        })
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
            # The cross-app work queue (metric registered in analytics.computed;
            # seeded here out of the box — Doug's ruling 2026-07-26).
            PanelSpec("attention_queue", "Items awaiting processing", "attention_queue", VIZ_TABLE, width=6),
        ],
    )
)
