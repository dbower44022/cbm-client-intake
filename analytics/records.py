"""Starter dashboards for the record views (Analytics Phase E).

One seeded page per record type, so an Analytics tab shows real numbers the day
it is switched on rather than "nobody has set this up yet". Doug's ruling
(2026-07-27): **one dashboard per record type**, placement is per dashboard —
see ``prds/analytics-app-plan.md`` §17.

Pages seeded here (scope = the record's CRM entity):

  * ``record-mentor``      CMentorProfile  — their clients + session activity
  * ``record-engagement``  CEngagement     — session history + contact recency
  * ``record-partner``     CPartnerProfile — referrals + partner meetings
  * ``record-funder``      CSponsorProfile — the contribution ledger, summarised
  * ``record-contact``     Contact         — meetings attended + email threads
  * ``record-client``      CClientProfile  — this business's engagement history
  * ``record-company``     Account         — the company's people and activity

Like every built-in, these are **defaults**: an analytics admin can edit them
(materialising an editable copy), delete them, or reset them (v0.168/0.171).

Record metrics never run under the org-wide API key and are never cached — the
engine computes them AS THE VIEWING USER (``service.resolve_metric`` skips the
cache whenever ``ctx.record`` is set), so EspoCRM's ACL bounds every number and
one viewer's scope can never be served to another. They are cheap because they
are bounded to one record's related set.

Every attribute filtered on below was verified live against crm-test
(2026-07-28): ``CSession.engagementId`` / ``partnerSessionId`` /
``sponsorProfileId``, ``CEngagement.mentorProfileId`` / ``referringPartnerId`` /
``lastContactDate`` / ``engagementClientId`` / ``clientOrganizationId``,
``CContribution.sponsorProfileId`` / ``status`` / ``amount``,
``Contact.accountId``, and the two ``linkedWith`` reads used for a Contact.
The engagement→client / engagement→company links are also read live by
``sessions/config.py`` and ``scripts/repair_duplicate_intake.py``.
"""

from __future__ import annotations

from typing import Any, Optional

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
    unavailable,
)

MENTOR = "CMentorProfile"
ENGAGEMENT = "CEngagement"
PARTNER = "CPartnerProfile"
FUNDER = "CSponsorProfile"
CONTACT = "Contact"
CLIENT = "CClientProfile"
ACCOUNT = "Account"

# Engagement statuses that count as a live client relationship (the set the
# session tools treat as active).
ACTIVE_ENGAGEMENT_STATUSES = ("Active", "Assigned", "Pending Acceptance", "On-Hold")
# A session that actually happened. Scheduled/Cancelled/No Show are not history.
COMPLETED = "Completed"
# Only Received money counts toward a funder's totals (funder-contributions
# plan, Doug 2026-07-20 — the same rule the Contributions tab applies).
RECEIVED = "Received"


def _rid(ctx: MetricContext) -> Optional[str]:
    return ctx.record.record_id if ctx.record else None


def _eq(attribute: str, value: str) -> dict[str, Any]:
    return {"type": "equals", "attribute": attribute, "value": value}


def _no_record(shape: str):
    """A record metric placed on a system page has nothing to scope to."""
    return unavailable(shape, "This metric only works on a record's Analytics tab.")


async def _sessions_for(ctx: MetricContext, fk: str, select: str, **kw) -> list[dict]:
    return await crm.sweep(ctx.espo, "CSession", select, where=[_eq(fk, _rid(ctx))], **kw)


def _session_rows(records: list[dict], *, limit: int = 10) -> Any:
    """The recent-meetings table, shared by every domain's starter page."""
    records = sorted(
        records, key=lambda r: str(r.get("dateStart") or ""), reverse=True
    )[:limit]
    columns = [
        {"key": "date", "label": "Date"},
        {"key": "name", "label": "Session", "link": "record"},
        {"key": "status", "label": "Status"},
    ]
    out = []
    for r in records:
        out.append({
            "date": crm.fmt_date(r.get("dateStart")),
            "name": r.get("name") or "(untitled session)",
            "status": r.get("status") or "",
            "entity": "CSession",
            "recordId": r.get("id"),
        })
    return rows(columns, out)


def _months(records: list[dict], field: str, ctx: MetricContext) -> Any:
    return series(crm.bucket_by_month(records, field, ctx.time_range))


# --- Mentor -------------------------------------------------------------------
@metric(
    key="mentor_active_clients",
    name="Active clients",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(MENTOR,),
    description="Client engagements assigned to this mentor that are still active.",
)
async def _mentor_active_clients(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    n = await crm.count(ctx.espo, ENGAGEMENT, [
        _eq("mentorProfileId", rid),
        {"type": "in", "attribute": "engagementStatus", "value": list(ACTIVE_ENGAGEMENT_STATUSES)},
    ])
    return scalar(n, unit="clients")


@metric(
    key="mentor_engagements_by_status",
    name="Client engagements by status",
    shape=SHAPE_BREAKDOWN, default_viz=VIZ_BAR, cache_mode="live",
    applies_to=(MENTOR,),
    description="Every engagement this mentor has held, grouped by status.",
)
async def _mentor_engagements_by_status(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_BREAKDOWN)
    recs = await crm.sweep(ctx.espo, ENGAGEMENT, "engagementStatus",
                           where=[_eq("mentorProfileId", rid)])
    counts: dict[str, int] = {}
    for r in recs:
        label = r.get("engagementStatus") or "(none)"
        counts[label] = counts.get(label, 0) + 1
    return breakdown([
        {"label": k, "value": v}
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ])


@metric(
    key="mentor_sessions_per_month",
    name="Sessions per month",
    shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
    applies_to=(MENTOR,),
    description="Completed sessions across this mentor's engagements, by month.",
)
async def _mentor_sessions_per_month(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SERIES)
    engagements = await crm.sweep(ctx.espo, ENGAGEMENT, "id",
                                  where=[_eq("mentorProfileId", rid)])
    ids = [e["id"] for e in engagements if e.get("id")]
    if not ids:
        return series(crm.bucket_by_month([], "dateStart", ctx.time_range))
    recs = await crm.sweep(ctx.espo, "CSession", "dateStart,status", where=[
        {"type": "in", "attribute": "engagementId", "value": ids},
        _eq("status", COMPLETED),
    ])
    return _months(recs, "dateStart", ctx)


@metric(
    key="mentor_client_list",
    name="Clients",
    shape=SHAPE_ROWS, default_viz=VIZ_TABLE, cache_mode="live",
    applies_to=(MENTOR,),
    description="This mentor's engagements, most recently contacted first.",
)
async def _mentor_client_list(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_ROWS)
    recs = await crm.sweep(ctx.espo, ENGAGEMENT, "name,engagementStatus,lastContactDate",
                           where=[_eq("mentorProfileId", rid)])
    recs = sorted(recs, key=lambda r: str(r.get("lastContactDate") or ""), reverse=True)[:10]
    columns = [
        {"key": "name", "label": "Engagement", "link": "record"},
        {"key": "status", "label": "Status"},
        {"key": "contact", "label": "Last contact"},
    ]
    return rows(columns, [{
        "name": r.get("name") or "(unnamed engagement)",
        "status": r.get("engagementStatus") or "",
        "contact": crm.fmt_date(r.get("lastContactDate")) or "—",
        "entity": ENGAGEMENT,
        "recordId": r.get("id"),
    } for r in recs])


# --- Engagement ---------------------------------------------------------------
@metric(
    key="engagement_sessions_completed",
    name="Sessions completed",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(ENGAGEMENT,),
    description="Meetings recorded against this engagement with status Completed.",
)
async def _engagement_sessions_completed(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    n = await crm.count(ctx.espo, "CSession", [_eq("engagementId", rid), _eq("status", COMPLETED)])
    return scalar(n, unit="sessions")


@metric(
    key="engagement_days_since_contact",
    name="Days since last contact",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(ENGAGEMENT,),
    description="How long since this client was last contacted (auto-maintained).",
)
async def _engagement_days_since_contact(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    rec = await ctx.espo.get(ENGAGEMENT, rid, select="id,lastContactDate")
    days = crm.days_since((rec or {}).get("lastContactDate"))
    if days is None:
        return unavailable(SHAPE_SCALAR, "No contact has been recorded yet.")
    return scalar(days, unit="days")


@metric(
    key="engagement_sessions_per_month",
    name="Sessions per month",
    shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
    applies_to=(ENGAGEMENT,),
    description="Completed sessions on this engagement, by month.",
)
async def _engagement_sessions_per_month(ctx: MetricContext):
    if not _rid(ctx):
        return _no_record(SHAPE_SERIES)
    recs = await _sessions_for(ctx, "engagementId", "dateStart,status")
    recs = [r for r in recs if r.get("status") == COMPLETED]
    return _months(recs, "dateStart", ctx)


@metric(
    key="engagement_recent_sessions",
    name="Recent sessions",
    shape=SHAPE_ROWS, default_viz=VIZ_TABLE, cache_mode="live",
    applies_to=(ENGAGEMENT,),
    description="The latest meetings on this engagement, newest first.",
)
async def _engagement_recent_sessions(ctx: MetricContext):
    if not _rid(ctx):
        return _no_record(SHAPE_ROWS)
    return _session_rows(await _sessions_for(ctx, "engagementId", "name,dateStart,status"))


# --- Partner ------------------------------------------------------------------
@metric(
    key="partner_referred_clients",
    name="Clients referred",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(PARTNER,),
    description="Client engagements naming this partner as the referring partner.",
)
async def _partner_referred_clients(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    return scalar(await crm.count(ctx.espo, ENGAGEMENT, [_eq("referringPartnerId", rid)]),
                  unit="clients")


@metric(
    key="partner_sessions_completed",
    name="Meetings held",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(PARTNER,),
    description="Completed partner meetings recorded against this partner.",
)
async def _partner_sessions_completed(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    n = await crm.count(ctx.espo, "CSession",
                        [_eq("partnerSessionId", rid), _eq("status", COMPLETED)])
    return scalar(n, unit="meetings")


@metric(
    key="partner_referrals_per_month",
    name="Referrals per month",
    shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
    applies_to=(PARTNER,),
    description="Client engagements referred by this partner, by month created.",
)
async def _partner_referrals_per_month(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SERIES)
    recs = await crm.sweep(ctx.espo, ENGAGEMENT, "createdAt",
                           where=[_eq("referringPartnerId", rid)],
                           order_by="createdAt", order="asc")
    return _months(recs, "createdAt", ctx)


@metric(
    key="partner_recent_sessions",
    name="Recent meetings",
    shape=SHAPE_ROWS, default_viz=VIZ_TABLE, cache_mode="live",
    applies_to=(PARTNER,),
    description="The latest meetings with this partner, newest first.",
)
async def _partner_recent_sessions(ctx: MetricContext):
    if not _rid(ctx):
        return _no_record(SHAPE_ROWS)
    return _session_rows(await _sessions_for(ctx, "partnerSessionId", "name,dateStart,status"))


# --- Funder -------------------------------------------------------------------
async def _contributions(ctx: MetricContext, select: str) -> list[dict]:
    return await crm.sweep(ctx.espo, "CContribution", select,
                           where=[_eq("sponsorProfileId", _rid(ctx))])


def _amount(r: dict) -> float:
    try:
        return float(r.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


@metric(
    key="funder_total_received",
    name="Total received",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(FUNDER,),
    description="Sum of this funder's contributions with status Received.",
)
async def _funder_total_received(ctx: MetricContext):
    if not _rid(ctx):
        return _no_record(SHAPE_SCALAR)
    recs = await _contributions(ctx, "amount,status")
    total = sum(_amount(r) for r in recs if r.get("status") == RECEIVED)
    return scalar(round(total, 2), fmt="currency")


@metric(
    key="funder_pipeline",
    name="Pledged & committed",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(FUNDER,),
    description="Money promised but not yet received (Pledged + Committed).",
)
async def _funder_pipeline(ctx: MetricContext):
    if not _rid(ctx):
        return _no_record(SHAPE_SCALAR)
    recs = await _contributions(ctx, "amount,status")
    total = sum(_amount(r) for r in recs if r.get("status") in ("Pledged", "Committed"))
    return scalar(round(total, 2), fmt="currency")


@metric(
    key="funder_received_per_month",
    name="Received per month",
    shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
    applies_to=(FUNDER,),
    description="Contribution money received from this funder each month.",
)
async def _funder_received_per_month(ctx: MetricContext):
    if not _rid(ctx):
        return _no_record(SHAPE_SERIES)
    recs = await _contributions(ctx, "amount,status,receivedDate")
    totals: dict[str, float] = {}
    for r in recs:
        if r.get("status") != RECEIVED:
            continue
        dt = crm.parse_crm_dt(r.get("receivedDate"))
        if dt is None:
            continue
        key = crm.month_key(dt)
        totals[key] = totals.get(key, 0) + _amount(r)
    return series(crm.fill_month_series(totals, ctx.time_range), fmt="currency")


@metric(
    key="funder_recent_contributions",
    name="Recent contributions",
    shape=SHAPE_ROWS, default_viz=VIZ_TABLE, cache_mode="live",
    applies_to=(FUNDER,),
    description="This funder's latest contributions, newest first.",
)
async def _funder_recent_contributions(ctx: MetricContext):
    if not _rid(ctx):
        return _no_record(SHAPE_ROWS)
    recs = await _contributions(
        ctx, "name,amount,status,contributionType,receivedDate,expectedPaymentDate,commitmentDate"
    )

    def effective(r: dict) -> str:
        # The funder ledger's effective-date rule (funder-contributions plan).
        for f in ("receivedDate", "expectedPaymentDate", "commitmentDate"):
            if r.get(f):
                return str(r[f])
        return ""

    recs = sorted(recs, key=effective, reverse=True)[:10]
    columns = [
        {"key": "date", "label": "Date"},
        {"key": "name", "label": "Contribution", "link": "record"},
        {"key": "type", "label": "Type"},
        {"key": "status", "label": "Status"},
        {"key": "amount", "label": "Amount", "align": "right"},
    ]
    return rows(columns, [{
        "date": crm.fmt_date(effective(r)) or "—",
        "name": r.get("name") or "(untitled)",
        "type": r.get("contributionType") or "",
        "status": r.get("status") or "",
        "amount": _amount(r),
        "entity": "CContribution",
        "recordId": r.get("id"),
    } for r in recs])


# --- Contact ------------------------------------------------------------------
def _linked(attribute: str, rid: str) -> dict[str, Any]:
    return {"type": "linkedWith", "attribute": attribute, "value": [rid]}


@metric(
    key="contact_sessions_attended",
    name="Meetings attended",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(CONTACT,),
    description="Completed sessions this contact was an attendee of.",
)
async def _contact_sessions_attended(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    n = await crm.count(ctx.espo, "CSession",
                        [_linked("sessionAttendees", rid), _eq("status", COMPLETED)])
    return scalar(n, unit="meetings")


@metric(
    key="contact_email_threads",
    name="Email conversations",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(CONTACT,),
    description="Email threads this contact is part of.",
)
async def _contact_email_threads(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    return scalar(await crm.count(ctx.espo, "CConversation", [_linked("contacts", rid)]),
                  unit="conversations")


@metric(
    key="contact_sessions_per_month",
    name="Meetings per month",
    shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
    applies_to=(CONTACT,),
    description="Completed sessions this contact attended, by month.",
)
async def _contact_sessions_per_month(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SERIES)
    recs = await crm.sweep(ctx.espo, "CSession", "dateStart,status",
                           where=[_linked("sessionAttendees", rid), _eq("status", COMPLETED)])
    return _months(recs, "dateStart", ctx)


@metric(
    key="contact_recent_sessions",
    name="Recent meetings",
    shape=SHAPE_ROWS, default_viz=VIZ_TABLE, cache_mode="live",
    applies_to=(CONTACT,),
    description="The latest meetings this contact attended, newest first.",
)
async def _contact_recent_sessions(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_ROWS)
    recs = await crm.sweep(ctx.espo, "CSession", "name,dateStart,status",
                           where=[_linked("sessionAttendees", rid)])
    return _session_rows(recs)


# --- Client -------------------------------------------------------------------
@metric(
    key="client_engagements_total",
    name="Total engagements",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(CLIENT,),
    description="Every engagement this client business has ever had.",
)
async def _client_engagements_total(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    n = await crm.count(ctx.espo, ENGAGEMENT, [_eq("engagementClientId", rid)])
    return scalar(n, unit="engagements")


@metric(
    key="client_engagements_active",
    name="Currently active",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(CLIENT,),
    description="Live mentoring relationships for this client business right now.",
)
async def _client_engagements_active(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    n = await crm.count(ctx.espo, ENGAGEMENT, [
        _eq("engagementClientId", rid),
        {"type": "in", "attribute": "engagementStatus", "value": list(ACTIVE_ENGAGEMENT_STATUSES)},
    ])
    return scalar(n, unit="engagements")


@metric(
    key="client_sessions_per_month",
    name="Sessions per month",
    shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
    applies_to=(CLIENT,),
    description="Completed sessions across all this client's engagements, by month.",
)
async def _client_sessions_per_month(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SERIES)
    engagements = await crm.sweep(ctx.espo, ENGAGEMENT, "id",
                                  where=[_eq("engagementClientId", rid)])
    ids = [e["id"] for e in engagements if e.get("id")]
    if not ids:
        return series(crm.bucket_by_month([], "dateStart", ctx.time_range))
    recs = await crm.sweep(ctx.espo, "CSession", "dateStart,status", where=[
        {"type": "in", "attribute": "engagementId", "value": ids},
        _eq("status", COMPLETED),
    ])
    return _months(recs, "dateStart", ctx)


@metric(
    key="client_engagements_list",
    name="Engagements",
    shape=SHAPE_ROWS, default_viz=VIZ_TABLE, cache_mode="live",
    applies_to=(CLIENT,),
    description="This client's engagements, most recently contacted first.",
)
async def _client_engagements_list(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_ROWS)
    recs = await crm.sweep(ctx.espo, ENGAGEMENT, "name,engagementStatus,lastContactDate",
                           where=[_eq("engagementClientId", rid)])
    recs = sorted(recs, key=lambda r: str(r.get("lastContactDate") or ""), reverse=True)[:10]
    columns = [
        {"key": "name", "label": "Engagement", "link": "record"},
        {"key": "status", "label": "Status"},
        {"key": "contact", "label": "Last contact"},
    ]
    return rows(columns, [{
        "name": r.get("name") or "(unnamed engagement)",
        "status": r.get("engagementStatus") or "",
        "contact": crm.fmt_date(r.get("lastContactDate")) or "—",
        "entity": ENGAGEMENT,
        "recordId": r.get("id"),
    } for r in recs])


# --- Company (Account) --------------------------------------------------------
@metric(
    key="company_contacts_count",
    name="Contacts at this company",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(ACCOUNT,),
    description="People whose Account is this company.",
)
async def _company_contacts_count(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    return scalar(await crm.count(ctx.espo, CONTACT, [_eq("accountId", rid)]),
                  unit="contacts")


@metric(
    key="company_engagements_count",
    name="Engagements as client",
    shape=SHAPE_SCALAR, default_viz=VIZ_STAT, cache_mode="live",
    applies_to=(ACCOUNT,),
    description="Engagements this company has been the client on.",
)
async def _company_engagements_count(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SCALAR)
    return scalar(await crm.count(ctx.espo, ENGAGEMENT, [_eq("clientOrganizationId", rid)]),
                  unit="engagements")


@metric(
    key="company_activity_per_month",
    name="Activity over time",
    shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
    applies_to=(ACCOUNT,),
    description="Completed sessions across this company's engagements, by month.",
)
async def _company_activity_per_month(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_SERIES)
    engagements = await crm.sweep(ctx.espo, ENGAGEMENT, "id",
                                  where=[_eq("clientOrganizationId", rid)])
    ids = [e["id"] for e in engagements if e.get("id")]
    if not ids:
        return series(crm.bucket_by_month([], "dateStart", ctx.time_range))
    recs = await crm.sweep(ctx.espo, "CSession", "dateStart,status", where=[
        {"type": "in", "attribute": "engagementId", "value": ids},
        _eq("status", COMPLETED),
    ])
    return _months(recs, "dateStart", ctx)


@metric(
    key="company_contacts_list",
    name="Contacts",
    shape=SHAPE_ROWS, default_viz=VIZ_TABLE, cache_mode="live",
    applies_to=(ACCOUNT,),
    description="People at this company, newest first.",
)
async def _company_contacts_list(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return _no_record(SHAPE_ROWS)
    recs = await crm.sweep(ctx.espo, CONTACT, "name,title,createdAt",
                           where=[_eq("accountId", rid)])
    recs = sorted(recs, key=lambda r: str(r.get("createdAt") or ""), reverse=True)[:10]
    columns = [
        {"key": "name", "label": "Contact", "link": "record"},
        {"key": "title", "label": "Title"},
        {"key": "added", "label": "Added"},
    ]
    return rows(columns, [{
        "name": r.get("name") or "(unnamed contact)",
        "title": r.get("title") or "",
        "added": crm.fmt_date(r.get("createdAt")) or "—",
        "entity": CONTACT,
        "recordId": r.get("id"),
    } for r in recs])


# --- the seeded record pages --------------------------------------------------
# One page per record type (Doug 2026-07-27) — the record endpoint takes the
# page whose scope matches, so exactly one keeps the tab unambiguous.
register_page(PageSpec(
    key="record-mentor", title="Mentor Analytics", scope=MENTOR,
    subtitle="This mentor's client load and session activity.",
    default_range="last12mo",
    panels=[
        PanelSpec("active_clients", "Active clients", "mentor_active_clients", VIZ_STAT, width=3),
        PanelSpec("by_status", "Client engagements by status", "mentor_engagements_by_status", VIZ_BAR, width=9),
        PanelSpec("sessions_month", "Sessions per month", "mentor_sessions_per_month", VIZ_LINE, width=6),
        PanelSpec("clients", "Clients", "mentor_client_list", VIZ_TABLE, width=6),
    ],
))

register_page(PageSpec(
    key="record-engagement", title="Engagement Analytics", scope=ENGAGEMENT,
    subtitle="Session history and contact recency for this client.",
    default_range="last12mo",
    panels=[
        PanelSpec("sessions_done", "Sessions completed", "engagement_sessions_completed", VIZ_STAT, width=3),
        PanelSpec("since_contact", "Days since last contact", "engagement_days_since_contact", VIZ_STAT, width=3),
        PanelSpec("sessions_month", "Sessions per month", "engagement_sessions_per_month", VIZ_LINE, width=6),
        PanelSpec("recent", "Recent sessions", "engagement_recent_sessions", VIZ_TABLE, width=12),
    ],
))

register_page(PageSpec(
    key="record-partner", title="Partner Analytics", scope=PARTNER,
    subtitle="What this partnership has produced.",
    default_range="last12mo",
    panels=[
        PanelSpec("referred", "Clients referred", "partner_referred_clients", VIZ_STAT, width=3),
        PanelSpec("meetings", "Meetings held", "partner_sessions_completed", VIZ_STAT, width=3),
        PanelSpec("referrals_month", "Referrals per month", "partner_referrals_per_month", VIZ_LINE, width=6),
        PanelSpec("recent", "Recent meetings", "partner_recent_sessions", VIZ_TABLE, width=12),
    ],
))

register_page(PageSpec(
    key="record-funder", title="Funder Analytics", scope=FUNDER,
    subtitle="The contribution ledger, summarised.",
    default_range="last12mo",
    panels=[
        PanelSpec("received", "Total received", "funder_total_received", VIZ_STAT, width=3),
        PanelSpec("pipeline", "Pledged & committed", "funder_pipeline", VIZ_STAT, width=3),
        PanelSpec("received_month", "Received per month", "funder_received_per_month", VIZ_LINE, width=6),
        PanelSpec("recent", "Recent contributions", "funder_recent_contributions", VIZ_TABLE, width=12),
    ],
))

register_page(PageSpec(
    key="record-contact", title="Contact Analytics", scope=CONTACT,
    subtitle="This person's meetings and email activity with CBM.",
    default_range="last12mo",
    panels=[
        PanelSpec("meetings", "Meetings attended", "contact_sessions_attended", VIZ_STAT, width=3),
        PanelSpec("threads", "Email conversations", "contact_email_threads", VIZ_STAT, width=3),
        PanelSpec("meetings_month", "Meetings per month", "contact_sessions_per_month", VIZ_LINE, width=6),
        PanelSpec("recent", "Recent meetings", "contact_recent_sessions", VIZ_TABLE, width=12),
    ],
))

register_page(PageSpec(
    key="record-client", title="Client Analytics", scope=CLIENT,
    subtitle="This business's engagement history with CBM.",
    default_range="last12mo",
    panels=[
        PanelSpec("total", "Total engagements", "client_engagements_total", VIZ_STAT, width=3),
        PanelSpec("active", "Currently active", "client_engagements_active", VIZ_STAT, width=3),
        PanelSpec("sessions_month", "Sessions per month", "client_sessions_per_month", VIZ_LINE, width=6),
        PanelSpec("engagements", "Engagements", "client_engagements_list", VIZ_TABLE, width=12),
    ],
))

register_page(PageSpec(
    key="record-company", title="Company Analytics", scope=ACCOUNT,
    subtitle="The company's people and activity with CBM.",
    default_range="last12mo",
    panels=[
        PanelSpec("contacts", "Contacts at this company", "company_contacts_count", VIZ_STAT, width=3),
        PanelSpec("engagements", "Engagements as client", "company_engagements_count", VIZ_STAT, width=3),
        PanelSpec("activity_month", "Activity over time", "company_activity_per_month", VIZ_LINE, width=6),
        PanelSpec("contacts_list", "Contacts", "company_contacts_list", VIZ_TABLE, width=12),
    ],
))
