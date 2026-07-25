"""Operational + cross-source computed metrics (Analytics Phase D).

Metrics sourced from the app's OWN data (the durable submission store) and a
currency CRM rollup — beyond what a builder metric expresses. Importing this
module registers them; they appear in the metric library and can be placed on
pages like any other metric.

Data domains proven here: ``store`` (the durable submission Postgres) and a
currency-formatted ``crm`` rollup. Deeper cross-source blends (e.g. intake →
first-session latency, email volume per mentor) need a data-model decision on
how a submission links to its engagement/sessions — a documented follow-up.
"""

from __future__ import annotations

from . import crm
from .registry import (
    SHAPE_BREAKDOWN,
    SHAPE_SERIES,
    SRC_CRM,
    SRC_STORE,
    VIZ_BAR,
    VIZ_LINE,
    MetricContext,
    breakdown,
    metric,
    series,
    unavailable,
)

# Delivery statuses excluded from the "open queue" breakdown.
_QUEUE_EXCLUDE = {"completed", "discarded"}


def _status_label(status: str) -> str:
    return (status or "").replace("_", " ").strip().capitalize() or "(none)"


@metric(
    key="submissions_per_month",
    name="Submissions received per month",
    shape=SHAPE_SERIES,
    source=SRC_STORE,
    default_viz=VIZ_LINE,
    cache_mode="cached",
    refresh_seconds=3600,
    time_aware=True,
    description="Intake submissions captured each month (the durable store).",
)
async def _submissions_per_month(ctx: MetricContext):
    store = ctx.submission_store
    if store is None:
        return unavailable(SHAPE_SERIES, "The submission store isn't configured on this deployment.")
    rows = await store.submissions_by_month()
    counts = {r["month"]: r["count"] for r in rows if r.get("month")}
    return series(crm.fill_month_series(counts, ctx.time_range))


@metric(
    key="submission_queue",
    name="Submission queue by status",
    shape=SHAPE_BREAKDOWN,
    source=SRC_STORE,
    default_viz=VIZ_BAR,
    cache_mode="cached",
    refresh_seconds=600,
    description="Open submissions grouped by delivery status (excludes completed/discarded).",
)
async def _submission_queue(ctx: MetricContext):
    store = ctx.submission_store
    if store is None:
        return unavailable(SHAPE_BREAKDOWN, "The submission store isn't configured on this deployment.")
    counts = await store.counts_by_status()
    items = [
        {"label": _status_label(s), "value": v}
        for s, v in counts.items()
        if v and s not in _QUEUE_EXCLUDE
    ]
    items.sort(key=lambda i: -i["value"])
    return breakdown(items)


@metric(
    key="contributions_received_per_month",
    name="Contributions received per month",
    shape=SHAPE_SERIES,
    source=SRC_CRM,
    default_viz=VIZ_BAR,
    cache_mode="cached",
    refresh_seconds=3600,
    time_aware=True,
    description="Sum of received contribution amounts by month.",
)
async def _contributions_per_month(ctx: MetricContext):
    recs = await crm.sweep(ctx.espo, "CContribution", "receivedDate,amount,status")
    sums: dict[str, float] = {}
    for r in recs:
        if (r.get("status") or "") != "Received":
            continue
        dt = crm.parse_crm_dt(r.get("receivedDate"))
        if dt is None:
            continue
        try:
            amt = float(r.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        key = crm.month_key(dt)
        sums[key] = sums.get(key, 0.0) + amt
    return series(crm.fill_month_series(sums, ctx.time_range), unit="$", fmt="currency")
