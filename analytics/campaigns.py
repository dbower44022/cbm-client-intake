"""Prospect marketing's two Analytics reads (build plan § 6 items 2 and 3) and
the built-in *Campaigns* page that carries them.

Every number comes from ``campaigns/reporting.py``, so the campaign record page,
the Responses tab and this page agree. System metrics, so they compute under the
org-wide API key (the team gate and the panel visibility are the boundary), and
they run live — a cached copy would disagree with the grids for the length of
its life. A CRM without the prospect entities reads as an unavailable panel,
never a 500.
"""

from __future__ import annotations

import logging

from .registry import (
    SHAPE_ROWS,
    SRC_COMPUTED,
    VIZ_TABLE,
    MetricContext,
    PageSpec,
    PanelSpec,
    metric,
    register_page,
    rows,
    unavailable,
)

log = logging.getLogger("cbm_intake.analytics.campaigns")


async def _ready(ctx: MetricContext) -> str:
    """'' when the metric can compute, else the reason."""
    if ctx.espo is None:
        return "This deployment has no CRM credential for system metrics."
    from campaigns import service

    avail = await service.availability(ctx.espo)
    return "" if avail["available"] else avail["reason"]


@metric(
    key="campaign_touches",
    name="Touches by campaign",
    shape=SHAPE_ROWS,
    source=SRC_COMPUTED,
    default_viz=VIZ_TABLE,
    cache_mode="live",
    description=("Per campaign that selects an audience: planned, sent, delivered, returned, "
                 "scanned, the call outcomes, responded and converted, and the rung each "
                 "target was on when its touch went out (build plan § 6 item 2)."),
)
async def _campaign_touches(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    from campaigns import reporting
    from campaigns.store import make_campaign_store

    store = make_campaign_store(ctx.settings)
    try:
        data = await reporting.touches_by_campaign(ctx.espo, store)
    finally:
        if store is not None:
            await store.dispose()
    columns = [
        {"key": "name", "label": "Campaign"},
        {"key": "kind", "label": "Kind"},
        {"key": "status", "label": "Status"},
        {"key": "planned", "label": "Planned", "align": "right"},
        {"key": "sent", "label": "Sent", "align": "right"},
        {"key": "delivered", "label": "Delivered", "align": "right"},
        {"key": "returned", "label": "Returned", "align": "right"},
        {"key": "scanned", "label": "Scanned", "align": "right"},
        {"key": "called", "label": "Called", "align": "right"},
        {"key": "interested", "label": "Interested", "align": "right"},
        {"key": "declined", "label": "Declined", "align": "right"},
        {"key": "responded", "label": "Responded", "align": "right"},
        {"key": "converted", "label": "Converted", "align": "right"},
        {"key": "stages", "label": "Rung at touch"},
    ]
    dash = "—"
    out = [{
        "name": r["name"], "kind": r["kind"] or dash, "status": r["status"] or dash,
        "planned": r["planned"], "sent": r["sent"], "delivered": r["delivered"],
        "returned": r["returned"], "scanned": r["scanned"], "called": r["done"],
        "interested": r["Interested"], "declined": r["Declined"],
        "responded": dash if r["responded"] is None else r["responded"],
        "converted": dash if r["converted"] is None else r["converted"],
        "stages": reporting.stage_text(r["stageAtTouch"]),
    } for r in data]
    return rows(columns, out)


@metric(
    key="prospect_entry_rungs",
    name="Entry rung per door",
    shape=SHAPE_ROWS,
    source=SRC_COMPUTED,
    default_viz=VIZ_TABLE,
    cache_mode="live",
    description=("How many records each door brought in, by the rung they entered at, so a "
                 "door entering half-way down is never read as converting better "
                 "(build plan § 6 item 3)."),
)
async def _prospect_entry_rungs(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    from campaigns import config as cfg
    from campaigns import reporting

    data = await reporting.entry_rung_by_door(ctx.espo)
    columns = [{"key": "door", "label": "Door"}]
    columns += [{"key": s, "label": s, "align": "right"} for s in cfg.STAGES]
    columns.append({"key": "total", "label": "Total", "align": "right"})
    out = [{k: ("—" if v is None else v) for k, v in r.items()} for r in data]
    return rows(columns, out)


register_page(PageSpec(
    key="campaigns",
    title="Campaigns",
    subtitle="Prospect marketing: what each campaign reached and where each door's records entered the ladder.",
    scope="system",
    default_range="all",
    panels=[
        PanelSpec("touches", "Touches by campaign", "campaign_touches", VIZ_TABLE, width=12),
        PanelSpec("entry_rungs", "Entry rung per door", "prospect_entry_rungs", VIZ_TABLE, width=12),
    ],
))
