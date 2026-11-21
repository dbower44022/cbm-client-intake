"""The Ambassador Program in Analytics (prds/Ambassador Program/
ambassador-program-prd.md § 6; decision AM7).

A system page for the Analytics Admin Team and the program team: active
ambassadors, activities by type, open follow-ups, contacts awaiting review,
referrals made and applied by kind, and ambassador contacts with existing
partners, funders and clients. One submission is one reported activity.
Mentors see no figures. System metrics compute under the org-wide key and
sweeps are cached, as the other system pages are. A CRM without the
Ambassador Activity record type reads as an unavailable panel, never a 500.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from core.session_kinds import AMBASSADOR_SESSION_TYPE

from . import crm
from .registry import (
    SHAPE_BREAKDOWN,
    SHAPE_ROWS,
    SHAPE_SCALAR,
    SHAPE_SERIES,
    SRC_COMPUTED,
    SWITCHED_METRICS,
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

ENTITY = "CAmbassadorActivity"
SELECT = ("id,activityDate,activityType,mentorProfileId,personKind,referralOutcome,"
          "followUpRequested,followUpDone,matchStatus,reviewOutcome")
ANALYTICS_TEAM = "Analytics Admin Team"
#: The program team's default (AMBASSADOR_REVIEW_TEAMS).
PROGRAM_TEAM = "Marketing Admin Team"
REFERRED = "Referred someone"
KINDS = (("Potential client", "Clients"), ("Potential partner", "Partners"),
         ("Potential funder", "Funders"))


def _range_where(ctx: MetricContext, field: str = "activityDate") -> list[dict[str, Any]]:
    """The range as CRM filters, both ends included.

    The CRM's "after" and "before" are strict, and on a date field they
    compare whole days: "before 2026-11-21" leaves out everything dated
    the 21st, which is how every report logged today read as zero on the
    Association (11-21-26). A date field is therefore bounded by the day
    before the start and the day after the end; a date-and-time field by
    the exact instants."""
    tr = ctx.time_range
    where: list[dict[str, Any]] = []
    if tr is None:
        return where
    is_date = field == "activityDate"
    if tr.start is not None:
        value = ((tr.start - timedelta(days=1)).strftime("%Y-%m-%d") if is_date
                 else tr.start.strftime("%Y-%m-%d %H:%M:%S"))
        where.append({"type": "after", "attribute": field, "value": value})
    if tr.end is not None:
        value = ((tr.end + timedelta(days=1)).strftime("%Y-%m-%d") if is_date
                 else tr.end.strftime("%Y-%m-%d %H:%M:%S"))
        where.append({"type": "before", "attribute": field, "value": value})
    return where


async def _ready(ctx: MetricContext) -> str:
    if ctx.espo is None:
        return "This deployment has no CRM credential for system metrics."
    try:
        meta = await ctx.espo.metadata(f"entityDefs.{ENTITY}.fields")
    except Exception:  # noqa: BLE001
        meta = None
    if not (isinstance(meta, dict) and meta):
        return "The CRM does not have the Ambassador Activity record type yet."
    return ""


async def _activities(ctx: MetricContext, where: Optional[list[dict[str, Any]]] = None,
                      *, ranged: bool = True) -> list[dict[str, Any]]:
    clauses = list(where or []) + (_range_where(ctx) if ranged else [])
    return await crm.sweep(ctx.espo, ENTITY, SELECT, where=clauses)


def active_by_month(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distinct ambassadors per month, months with activity only."""
    by: dict[str, set[str]] = {}
    for r in recs:
        dt = crm.parse_crm_dt(r.get("activityDate"))
        if dt is None or not r.get("mentorProfileId"):
            continue
        by.setdefault(crm.month_key(dt), set()).add(r["mentorProfileId"])
    return [{"bucket": k, "label": crm.month_label(int(k[:4]), int(k[5:7])), "value": len(by[k])}
            for k in sorted(by)]


def referral_rows(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for kind, label in KINDS:
        made = [r for r in recs if r.get("activityType") == REFERRED and r.get("personKind") == kind]
        applied = [r for r in made if r.get("referralOutcome") == "Applied"]
        out.append({"kind": label, "made": len(made), "applied": len(applied)})
    return out


@metric(key="ambassador_active", name="Active ambassadors", shape=SHAPE_SCALAR,
        source=SRC_COMPUTED, default_viz=VIZ_STAT, cache_mode="cached", time_aware=True,
        description="Members who logged at least one ambassador activity in the range.")
async def _ambassador_active(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SCALAR, reason)
    recs = await _activities(ctx)
    return scalar(len({r.get("mentorProfileId") for r in recs if r.get("mentorProfileId")}),
                  unit="ambassadors")


@metric(key="ambassador_active_by_month", name="Active ambassadors by month", shape=SHAPE_SERIES,
        source=SRC_COMPUTED, default_viz=VIZ_LINE, cache_mode="cached", time_aware=True,
        description="Members who logged at least one ambassador activity, per month.")
async def _ambassador_active_by_month(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SERIES, reason)
    return series(active_by_month(await _activities(ctx)), unit="ambassadors")


@metric(key="ambassador_activities", name="Ambassador activities", shape=SHAPE_SCALAR,
        source=SRC_COMPUTED, default_viz=VIZ_STAT, cache_mode="cached", time_aware=True,
        description="Ambassador activities reported in the range; one report is one activity.")
async def _ambassador_activities(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SCALAR, reason)
    return scalar(len(await _activities(ctx)), unit="activities")


@metric(key="ambassador_by_type", name="Ambassador activities by type", shape=SHAPE_BREAKDOWN,
        source=SRC_COMPUTED, default_viz=VIZ_BAR, cache_mode="cached", time_aware=True,
        description="Ambassador activities reported in the range, by activity.")
async def _ambassador_by_type(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_BREAKDOWN, reason)
    counts: dict[str, int] = {}
    for r in await _activities(ctx):
        counts[r.get("activityType") or "—"] = counts.get(r.get("activityType") or "—", 0) + 1
    return breakdown([{"label": k, "value": v} for k, v in
                      sorted(counts.items(), key=lambda kv: -kv[1])])


@metric(key="ambassador_open_follow_ups", name="Open ambassador follow-ups", shape=SHAPE_SCALAR,
        source=SRC_COMPUTED, default_viz=VIZ_STAT, cache_mode="live",
        description="Follow-up requests not yet marked done, whenever they were made.")
async def _ambassador_open_follow_ups(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SCALAR, reason)
    return scalar(await crm.count(ctx.espo, ENTITY, [
        {"type": "isTrue", "attribute": "followUpRequested"},
        {"type": "isFalse", "attribute": "followUpDone"}]), unit="open")


@metric(key="ambassador_to_review", name="Ambassador contacts awaiting review", shape=SHAPE_SCALAR,
        source=SRC_COMPUTED, default_viz=VIZ_STAT, cache_mode="live",
        description="Contacts the system could not place, not yet reviewed.")
async def _ambassador_to_review(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SCALAR, reason)
    recs = await _activities(ctx, [{"type": "in", "attribute": "matchStatus",
                                    "value": ["Not matched", "More than one match"]}], ranged=False)
    return scalar(len([r for r in recs if not r.get("reviewOutcome")]), unit="contacts")


@metric(key="ambassador_referrals", name="Ambassador referrals", shape=SHAPE_ROWS,
        source=SRC_COMPUTED, default_viz=VIZ_TABLE, cache_mode="cached", time_aware=True,
        description="Referrals made in the range and how many have applied, by kind.")
async def _ambassador_referrals(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    recs = await _activities(ctx, [{"type": "equals", "attribute": "activityType", "value": REFERRED}])
    return rows([{"key": "kind", "label": "Referred"},
                 {"key": "made", "label": "Referrals made", "align": "right"},
                 {"key": "applied", "label": "Applied", "align": "right"}], referral_rows(recs))


@metric(key="ambassador_contacts", name="Ambassador contacts with known records", shape=SHAPE_ROWS,
        source=SRC_COMPUTED, default_viz=VIZ_TABLE, cache_mode="cached", time_aware=True,
        description="Ambassador contact sessions recorded on partners, funders and clients.")
async def _ambassador_contacts(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    sessions = await crm.sweep(ctx.espo, "CSession", "id,engagementId,partnerSessionId,sponsorProfileId",
                               where=[{"type": "equals", "attribute": "sessionType",
                                       "value": AMBASSADOR_SESSION_TYPE}]
                               + _range_where(ctx, "dateStart"))
    counts = {"Partners": 0, "Funders": 0, "Clients": 0}
    for s in sessions:
        if s.get("partnerSessionId"):
            counts["Partners"] += 1
        elif s.get("sponsorProfileId"):
            counts["Funders"] += 1
        elif s.get("engagementId"):
            counts["Clients"] += 1
    return rows([{"key": "with", "label": "Recorded on"},
                 {"key": "count", "label": "Contacts", "align": "right"}],
                [{"with": k, "count": v} for k, v in counts.items()])


register_page(PageSpec(
    key="ambassador",
    title="Ambassador Program",
    subtitle="What members report doing to spread the word, and the referrals that applied.",
    scope="system",
    switch="ambassador_program",
    team_gate=(ANALYTICS_TEAM, PROGRAM_TEAM),
    default_range="last12mo",
    panels=[
        PanelSpec("active", "Active ambassadors", "ambassador_active", VIZ_STAT, width=3),
        PanelSpec("activities", "Activities reported", "ambassador_activities", VIZ_STAT, width=3),
        PanelSpec("open", "Open follow-ups", "ambassador_open_follow_ups", VIZ_STAT, width=3),
        PanelSpec("review", "Contacts awaiting review", "ambassador_to_review", VIZ_STAT, width=3),
        PanelSpec("active_month", "Active ambassadors by month", "ambassador_active_by_month",
                  VIZ_LINE, width=6),
        PanelSpec("by_type", "Activities by type", "ambassador_by_type", VIZ_BAR, width=6),
        PanelSpec("referrals", "Referrals made and applied", "ambassador_referrals", VIZ_TABLE,
                  width=6),
        PanelSpec("contacts", "Contacts with known records", "ambassador_contacts", VIZ_TABLE,
                  width=6),
    ],
))

for _k in ("ambassador_active", "ambassador_active_by_month", "ambassador_activities",
           "ambassador_by_type", "ambassador_open_follow_ups", "ambassador_to_review",
           "ambassador_referrals", "ambassador_contacts"):
    SWITCHED_METRICS[_k] = "ambassador_program"
