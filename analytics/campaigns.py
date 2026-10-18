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
    SHAPE_SCALAR,
    SRC_COMPUTED,
    VIZ_STAT,
    VIZ_TABLE,
    MetricContext,
    PageSpec,
    PanelSpec,
    metric,
    register_page,
    rows,
    scalar,
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


@metric(
    key="prospect_funnel",
    name="The prospect funnel",
    shape=SHAPE_ROWS,
    source=SRC_COMPUTED,
    default_viz=VIZ_TABLE,
    cache_mode="live",
    description=("A count per rung, nothing counted twice: prospect records still on the ladder, "
                 "Companies typed Prospect, Contacts typed Prospect not counted under their company, "
                 "and Candidate and Client from the engagements (build plan § 6 item 1)."),
)
async def _prospect_funnel(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    from campaigns import reporting

    data = await reporting.funnel(ctx.espo)
    columns = [{"key": "band", "label": "Band"}, {"key": "rung", "label": "Rung"},
               {"key": "count", "label": "Count", "align": "right"}]
    return rows(columns, data)


# --- the campaign's own dashboard (CM-9, § 6): the COutreachCampaign scope ---------------
CAMPAIGN = "COutreachCampaign"

_CAMPAIGN_RESULTS = (
    ("campaign_candidates", "Candidates", "candidates", "Engagements carrying the campaign that have no session yet."),
    ("campaign_clients", "Clients", "clients", "Engagements carrying the campaign in active mentoring."),
    ("campaign_registered", "Registered", "registered", "Event registrations carrying the campaign."),
    ("campaign_attended", "Attended", "attended", "Event registrations carrying the campaign marked attended."),
    ("campaign_info_requests", "Information requests", "informationRequests", "Information requests carrying the campaign."),
    ("campaign_partners", "Partner profiles", "partners", "Partner profiles carrying the campaign."),
    ("campaign_funders", "Funder profiles", "funders", "Funder profiles carrying the campaign."),
)


def _org_client(ctx: MetricContext):
    """The counts are aggregates over records the Marketing Admin Role does not
    read one by one (it holds no engagement read): they run under the org-wide
    key AFTER the record view has read the campaign as the user — the Events
    tab's precedent (v0.249.2, Doug's ruling 10-11-26). Never cached."""
    s = ctx.settings
    if s is None or getattr(s, "espo_dry_run", True) or not getattr(s, "espo_api_key", ""):
        return None
    from core.espo import EspoClient
    return EspoClient(s.espo_base_url, s.espo_api_key, s.request_timeout_seconds)


def _campaign_metric(key: str, name: str, field: str, description: str):
    async def compute(ctx: MetricContext):
        if not ctx.record or ctx.record.entity != CAMPAIGN:
            return unavailable(SHAPE_SCALAR, "This metric only works on a campaign's Analytics tab.")
        client = _org_client(ctx) or ctx.espo
        try:
            from campaigns import reporting
            eq = [{"type": "equals", "attribute": "outreachCampaignId", "value": ctx.record.record_id}]
            extra = {
                "candidates": [{"type": "in", "attribute": "engagementStatus", "value": list(reporting.CANDIDATE_STATUSES)}],
                "clients": [{"type": "in", "attribute": "engagementStatus", "value": list(reporting.CLIENT_STATUSES)}],
                "attended": [{"type": "equals", "attribute": "attendanceStatus", "value": "Attended"}],
            }.get(field, [])
            entity = {"candidates": "CEngagement", "clients": "CEngagement", "registered": "CEventRegistration",
                      "attended": "CEventRegistration", "informationRequests": "CInformationRequest",
                      "partners": "CPartnerProfile", "funders": "CSponsorProfile"}[field]
            n = await reporting._count(client, entity, eq + extra)
        except Exception as exc:  # noqa: BLE001 — a panel reads unavailable, never a 500
            log.warning("campaign metric %s failed: %s", key, exc)
            return unavailable(SHAPE_SCALAR, "This count could not be read.")
        return scalar(n)

    compute.__name__ = f"_{key}"
    return metric(key=key, name=name, shape=SHAPE_SCALAR, source=SRC_COMPUTED, default_viz=VIZ_STAT,
                  applies_to=(CAMPAIGN,), cache_mode="live", description=description)(compute)


for _key, _name, _field, _desc in _CAMPAIGN_RESULTS:
    _campaign_metric(_key, _name, _field, _desc)


register_page(PageSpec(
    key="record-campaign", title="Campaign Analytics", scope=CAMPAIGN,
    subtitle="What this campaign produced, down the funnel.",
    default_range="all",
    panels=[PanelSpec(k, n, k, VIZ_STAT, width=3) for k, n, _f, _d in _CAMPAIGN_RESULTS],
))


register_page(PageSpec(
    key="campaigns",
    title="Campaigns",
    subtitle="Prospect marketing: what each campaign reached and where each door's records entered the ladder.",
    scope="system",
    default_range="all",
    panels=[
        PanelSpec("funnel", "The prospect funnel", "prospect_funnel", VIZ_TABLE, width=12),
        PanelSpec("touches", "Touches by campaign", "campaign_touches", VIZ_TABLE, width=12),
        PanelSpec("entry_rungs", "Entry rung per door", "prospect_entry_rungs", VIZ_TABLE, width=12),
    ],
))
