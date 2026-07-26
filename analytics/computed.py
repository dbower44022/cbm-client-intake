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

import logging
from datetime import datetime, timezone

from core import attention

from . import crm
from .registry import (
    SHAPE_BREAKDOWN,
    SHAPE_ROWS,
    SHAPE_SERIES,
    SRC_COMPUTED,
    SRC_CRM,
    SRC_STORE,
    VIZ_BAR,
    VIZ_LINE,
    VIZ_TABLE,
    MetricContext,
    breakdown,
    metric,
    rows,
    series,
    unavailable,
)

log = logging.getLogger("cbm_intake.analytics")

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


# Rows shown per attention category (the panel is a work list, not an archive;
# the oldest items surface first so nothing scrolls out silently un-noted).
_ATTENTION_LIMIT = 15

# Plain-language Type cells for the open-submission states (why the row is open).
_SUBMISSION_ROW_LABELS = {
    "held_review": "Submission — awaiting approval",
    "needs_attention": "Submission — delivery failed",
    "completed": "Submission — reply owed",
}


def _submission_days(received_at) -> int | None:
    if not isinstance(received_at, datetime):
        return None
    dt = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - dt).days, 0)


@metric(
    key="attention_queue",
    name="Items awaiting processing",
    shape=SHAPE_ROWS,
    source=SRC_COMPUTED,
    default_viz=VIZ_TABLE,
    cache_mode="live",
    description=(
        "Everything currently awaiting staff processing — clients awaiting a "
        "mentor, new mentor and partner applications, funders with no manager, "
        "and open submissions — oldest first, each linked to the item."
    ),
)
async def _attention_queue(ctx: MetricContext):
    """The work-queue panel (Doug, 2026-07-26). Blends the CRM attention
    categories (:mod:`core.attention` — the same definitions the portal tile
    badges use) with the durable store's open submissions. Each source is
    best-effort (a failing one is logged and skipped); links go to the item's
    working surface — the app record page where one exists, else the CRM
    record, and the /ops deep link for submissions."""
    columns = [
        {"key": "type", "label": "Type"},
        {"key": "name", "label": "Item", "link": "record"},
        {"key": "received", "label": "Received"},
        {"key": "days", "label": "Days waiting", "align": "right"},
    ]
    out: list[dict] = []
    failures = 0

    for t in attention.CRM_TYPES:
        try:
            recs = await attention.crm_records(ctx.espo, t, limit=_ATTENTION_LIMIT)
        except Exception as exc:  # noqa: BLE001 — one failing source never blanks the panel
            log.warning("attention metric: %s source failed: %s", t.key, exc)
            failures += 1
            continue
        for r in recs:
            row = {
                "type": t.row_label,
                "name": r.get("name") or "(unnamed)",
                "received": crm.fmt_date(r.get("createdAt")),
                "days": crm.days_since(r.get("createdAt")),
            }
            if t.href_template:
                row["href"] = t.href_template.format(id=r.get("id"))
            else:
                row["entity"], row["recordId"] = t.entity, r.get("id")
            out.append(row)

    if ctx.submission_store is not None:
        try:
            subs = await ctx.submission_store.list_open_review(limit=_ATTENTION_LIMIT)
        except Exception as exc:  # noqa: BLE001
            log.warning("attention metric: submission source failed: %s", exc)
            failures += 1
            subs = []
        from forms import SPECS_BY_SLUG  # lazy: keep analytics import-light

        for s in subs:
            spec = SPECS_BY_SLUG.get(s.get("form_slug"))
            title = spec.title if spec else (s.get("form_slug") or "Submission")
            email = s.get("email")
            out.append({
                "type": _SUBMISSION_ROW_LABELS.get(s.get("status"), attention.OPS_ROW_LABEL),
                "name": f"{title} — {email}" if email else title,
                "received": (s["received_at"].strftime("%b %-d, %Y")
                             if isinstance(s.get("received_at"), datetime) else ""),
                "days": _submission_days(s.get("received_at")),
                "href": f"/ops/?submission={s.get('id')}",
            })

    if failures and not out:
        return unavailable(SHAPE_ROWS, "None of the attention sources could be read.")
    # Oldest waiting first, across every category (unknown ages last).
    out.sort(key=lambda r: (r["days"] is None, -(r["days"] or 0)))
    return rows(columns, out)


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
