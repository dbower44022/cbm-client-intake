"""Feedback surveys in Analytics (phases 8 and 9, ruling BE30; decision 8,
approved by Doug 11-20-26): the recommendation score by mentor, by event and
over time, built from Survey Response records.

* **The Feedback page** (system): viewed by the Analytics Admin, Mentor
  Administration and Marketing Admin teams. The by-mentor table is visible
  to the Mentor Administration and Analytics Admin teams only; the by-event
  table to the Marketing Admin and Analytics Admin teams only. System metrics
  compute under the org-wide key (the gates are the boundary) and are cached
  hourly, as the other system sweeps are.
* **The mentor's record tab** in Mentor Administration (staff only) gains the
  mentor's net promoter score with the average, and their score by month.
  Record metrics run as the staff member, never cached.
* **Mentors see no figures**: no feedback panel is on any page a mentor can
  open. Every by-mentor and by-event row shows its response count, so a
  figure resting on one response is not misread.

The **net promoter score** is the percentage of 9s and 10s minus the
percentage of 0s to 6s, from −100 to +100. A CRM without the Survey Response
record type reads as an unavailable panel, never a 500.
"""

from __future__ import annotations

from typing import Any, Optional

from . import crm
from .registry import (
    SWITCHED_METRICS,
    SHAPE_ROWS,
    SHAPE_SCALAR,
    SHAPE_SERIES,
    SRC_COMPUTED,
    VIZ_LINE,
    VIZ_STAT,
    VIZ_TABLE,
    MetricContext,
    PageSpec,
    PanelSpec,
    metric,
    register_page,
    rows,
    scalar,
    series,
    unavailable,
)

ENTITY = "CSurveyResponse"
MENTOR = "CMentorProfile"
SURVEYS = (("mentoring-feedback", "Mentoring feedback"), ("event-feedback", "Event feedback"),
           ("evaluation-feedback", "Evaluation feedback"))
SELECT = ("id,surveyKey,recommendScore,submittedAt,mentorProfileId,mentorProfileName,"
          "eventId,eventName,needsFollowUp,followUpDone,contactName,engagementName")

ANALYTICS_TEAM = "Analytics Admin Team"
MENTOR_ADMIN_TEAM = "Mentor Administration Team"
MARKETING_TEAM = "Marketing Admin Team"


def nps(scores: list[int]) -> Optional[int]:
    """The net promoter score of these scores; None when there are none."""
    if not scores:
        return None
    pro = sum(1 for s in scores if s >= 9)
    det = sum(1 for s in scores if s <= 6)
    return round(100 * (pro - det) / len(scores))


def average(scores: list[int]) -> Optional[float]:
    return round(sum(scores) / len(scores), 1) if scores else None


def _scores(recs: list[dict[str, Any]]) -> list[int]:
    return [r["recommendScore"] for r in recs if isinstance(r.get("recommendScore"), int)
            and not isinstance(r.get("recommendScore"), bool)]


def _range_where(ctx: MetricContext) -> list[dict[str, Any]]:
    tr = ctx.time_range
    where: list[dict[str, Any]] = []
    if tr is not None and tr.start is not None:
        where.append({"type": "after", "attribute": "submittedAt",
                      "value": tr.start.strftime("%Y-%m-%d %H:%M:%S")})
    if tr is not None and tr.end is not None:
        where.append({"type": "before", "attribute": "submittedAt",
                      "value": tr.end.strftime("%Y-%m-%d %H:%M:%S")})
    return where


async def _ready(ctx: MetricContext) -> str:
    if ctx.espo is None:
        return "This deployment has no CRM credential for system metrics."
    try:
        meta = await ctx.espo.metadata(f"entityDefs.{ENTITY}.fields")
    except Exception:  # noqa: BLE001
        meta = None
    if not (isinstance(meta, dict) and meta):
        return "The CRM does not have the Survey Response record type yet."
    return ""


async def _responses(ctx: MetricContext, where: Optional[list[dict[str, Any]]] = None,
                     *, ranged: bool = True) -> list[dict[str, Any]]:
    clauses = list(where or []) + (_range_where(ctx) if ranged else [])
    return await crm.sweep(ctx.espo, ENTITY, SELECT, where=clauses)


def _monthly_average(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Average score per month, months with responses only (a month with
    none is a gap, not a zero)."""
    by: dict[str, list[int]] = {}
    for r in recs:
        dt = crm.parse_crm_dt(r.get("submittedAt"))
        s = r.get("recommendScore")
        if dt is None or not isinstance(s, int) or isinstance(s, bool):
            continue
        by.setdefault(crm.month_key(dt), []).append(s)
    points = []
    for key in sorted(by):
        y, m = int(key[:4]), int(key[5:7])
        points.append({"bucket": key, "label": crm.month_label(y, m),
                       "value": average(by[key])})
    return points


def _fmt_nps(value: Optional[int]) -> Any:
    return "—" if value is None else (f"+{value}" if value > 0 else str(value))


# --- the system page ---------------------------------------------------------

@metric(key="feedback_responses", name="Feedback responses received", shape=SHAPE_SCALAR,
        source=SRC_COMPUTED, default_viz=VIZ_STAT, cache_mode="cached", time_aware=True,
        description="Feedback survey responses received in the range, every kind.")
async def _feedback_responses(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SCALAR, reason)
    return scalar(len(await _responses(ctx)), unit="responses")


@metric(key="feedback_nps", name="Net promoter score", shape=SHAPE_SCALAR,
        source=SRC_COMPUTED, default_viz=VIZ_STAT, cache_mode="cached", time_aware=True,
        description=("The percentage of 9s and 10s minus the percentage of 0s to 6s, every "
                     "kind of feedback survey, with the average score beside it."))
async def _feedback_nps(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SCALAR, reason)
    scores = _scores(await _responses(ctx))
    avg = average(scores)
    return scalar(nps(scores), unit=(f"average {avg} out of 10, {len(scores)} scores"
                                     if avg is not None else "no scores yet"))


def _by_month_metric(survey_key: str, title: str) -> None:
    key = "feedback_by_month_" + survey_key.split("-")[0]

    @metric(key=key, name=f"{title}: average score by month", shape=SHAPE_SERIES,
            source=SRC_COMPUTED, default_viz=VIZ_LINE, cache_mode="cached", time_aware=True,
            description=f"The average recommendation score of {title.lower()} each month.")
    async def _compute(ctx: MetricContext):
        reason = await _ready(ctx)
        if reason:
            return unavailable(SHAPE_SERIES, reason)
        recs = await _responses(ctx, [{"type": "equals", "attribute": "surveyKey",
                                       "value": survey_key}])
        return series(_monthly_average(recs), unit="out of 10")


for _key, _title in SURVEYS:
    _by_month_metric(_key, _title)


def _group_rows(recs: list[dict[str, Any]], id_field: str, name_field: str
                ) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for r in recs:
        gid = r.get(id_field)
        if not gid:
            continue
        g = groups.setdefault(gid, {"name": r.get(name_field) or "", "recs": []})
        g["recs"].append(r)
    out = []
    for gid, g in groups.items():
        scores = _scores(g["recs"])
        out.append({"id": gid, "name": g["name"], "responses": len(g["recs"]),
                    "average": average(scores), "nps": nps(scores),
                    "low": sum(1 for s in scores if s <= 6), "recs": g["recs"]})
    out.sort(key=lambda r: (-(r["responses"]), r["name"].lower()))
    return out


@metric(key="feedback_by_mentor", name="Feedback by mentor", shape=SHAPE_ROWS,
        source=SRC_COMPUTED, default_viz=VIZ_TABLE, cache_mode="cached", time_aware=True,
        description=("Mentoring and evaluation feedback by the engagement's mentor when it "
                     "was sent: responses, average, net promoter score and low scores."))
async def _feedback_by_mentor(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    recs = await _responses(ctx, [{"type": "in", "attribute": "surveyKey",
                                   "value": ["mentoring-feedback", "evaluation-feedback"]}])
    columns = [{"key": "name", "label": "Mentor", "link": True},
               {"key": "responses", "label": "Responses", "align": "right"},
               {"key": "average", "label": "Average", "align": "right"},
               {"key": "nps", "label": "Net promoter score", "align": "right"},
               {"key": "low", "label": "Low scores", "align": "right"}]
    return rows(columns, [{"name": g["name"] or "(no name)", "responses": g["responses"],
                           "average": "—" if g["average"] is None else g["average"],
                           "nps": _fmt_nps(g["nps"]), "low": g["low"],
                           "recordId": g["id"], "entity": MENTOR}
                          for g in _group_rows(recs, "mentorProfileId", "mentorProfileName")])


@metric(key="feedback_by_event", name="Feedback by event", shape=SHAPE_ROWS,
        source=SRC_COMPUTED, default_viz=VIZ_TABLE, cache_mode="cached", time_aware=True,
        description="Event feedback by event: responses, average and net promoter score.")
async def _feedback_by_event(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    recs = await _responses(ctx, [{"type": "equals", "attribute": "surveyKey",
                                   "value": "event-feedback"}])
    columns = [{"key": "name", "label": "Event", "link": True},
               {"key": "received", "label": "First response"},
               {"key": "responses", "label": "Responses", "align": "right"},
               {"key": "average", "label": "Average", "align": "right"},
               {"key": "nps", "label": "Net promoter score", "align": "right"}]
    out = []
    for g in _group_rows(recs, "eventId", "eventName"):
        first = min((r.get("submittedAt") or "" for r in g["recs"]), default="")
        out.append({"name": g["name"] or "(no name)", "received": crm.fmt_date(first) or "—",
                    "responses": g["responses"],
                    "average": "—" if g["average"] is None else g["average"],
                    "nps": _fmt_nps(g["nps"]), "recordId": g["id"], "entity": "CEvent"})
    return rows(columns, out)


@metric(key="feedback_open_follow_ups", name="Open follow-ups", shape=SHAPE_ROWS,
        source=SRC_COMPUTED, default_viz=VIZ_TABLE, cache_mode="live",
        description="Responses flagged for follow-up and not yet marked done, oldest first.")
async def _feedback_open_follow_ups(ctx: MetricContext):
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_ROWS, reason)
    recs = await crm.sweep(ctx.espo, ENTITY, SELECT, where=[
        {"type": "isTrue", "attribute": "needsFollowUp"},
        {"type": "isFalse", "attribute": "followUpDone"},
    ], order_by="submittedAt", order="asc")
    names = dict(SURVEYS)
    columns = [{"key": "received", "label": "Received"},
               {"key": "survey", "label": "Survey"},
               {"key": "score", "label": "Score", "align": "right"},
               {"key": "about", "label": "About"},
               {"key": "from", "label": "From"}]
    return rows(columns, [{
        "received": crm.fmt_date(r.get("submittedAt")) or "—",
        "survey": names.get(r.get("surveyKey") or "", r.get("surveyKey") or ""),
        "score": "—" if r.get("recommendScore") is None else r["recommendScore"],
        "about": r.get("eventName") or r.get("engagementName") or "—",
        "from": r.get("contactName") or "—",
        "recordId": r.get("id"), "entity": ENTITY,
    } for r in recs])


register_page(PageSpec(
    key="feedback",
    title="Feedback",
    subtitle=("Feedback surveys: how likely people are to recommend us, by mentor, by event "
              "and over time."),
    scope="system",
    switch="feedback_surveys",
    team_gate=(ANALYTICS_TEAM, MENTOR_ADMIN_TEAM, MARKETING_TEAM),
    default_range="last12mo",
    panels=[
        PanelSpec("responses", "Responses received", "feedback_responses", VIZ_STAT, width=4),
        PanelSpec("nps", "Net promoter score", "feedback_nps", VIZ_STAT, width=8),
        PanelSpec("mentoring_month", "Mentoring feedback: average by month",
                  "feedback_by_month_mentoring", VIZ_LINE, width=4),
        PanelSpec("event_month", "Event feedback: average by month",
                  "feedback_by_month_event", VIZ_LINE, width=4),
        PanelSpec("evaluation_month", "Evaluation feedback: average by month",
                  "feedback_by_month_evaluation", VIZ_LINE, width=4),
        PanelSpec("by_mentor", "By mentor", "feedback_by_mentor", VIZ_TABLE, width=6,
                  visibility=(MENTOR_ADMIN_TEAM, ANALYTICS_TEAM)),
        PanelSpec("by_event", "By event", "feedback_by_event", VIZ_TABLE, width=6,
                  visibility=(MARKETING_TEAM, ANALYTICS_TEAM)),
        PanelSpec("open", "Open follow-ups", "feedback_open_follow_ups", VIZ_TABLE, width=12),
    ],
))


# --- the mentor's record tab (Mentor Administration, staff only) --------------

def _rid(ctx: MetricContext) -> Optional[str]:
    return ctx.record.value if ctx.record else None


@metric(key="mentor_feedback_nps", name="Mentor's net promoter score", shape=SHAPE_SCALAR,
        default_viz=VIZ_STAT, cache_mode="live", time_aware=True, applies_to=(MENTOR,),
        description=("This mentor's net promoter score from mentoring and evaluation "
                     "feedback, with the average and the number of scores."))
async def _mentor_feedback_nps(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return unavailable(SHAPE_SCALAR, "No record selected.")
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SCALAR, reason)
    scores = _scores(await _responses(ctx, [
        {"type": "equals", "attribute": "mentorProfileId", "value": rid}]))
    avg = average(scores)
    return scalar(nps(scores), unit=(f"average {avg} out of 10, {len(scores)} scores"
                                     if avg is not None else "no scores yet"))


@metric(key="mentor_feedback_by_month", name="Mentor's average score by month",
        shape=SHAPE_SERIES, default_viz=VIZ_LINE, cache_mode="live", time_aware=True,
        applies_to=(MENTOR,),
        description="This mentor's average recommendation score each month.")
async def _mentor_feedback_by_month(ctx: MetricContext):
    rid = _rid(ctx)
    if not rid:
        return unavailable(SHAPE_SERIES, "No record selected.")
    reason = await _ready(ctx)
    if reason:
        return unavailable(SHAPE_SERIES, reason)
    recs = await _responses(ctx, [{"type": "equals", "attribute": "mentorProfileId",
                                   "value": rid}])
    return series(_monthly_average(recs), unit="out of 10")


def add_mentor_panels() -> None:
    """Put the two feedback panels on the built-in mentor dashboard. A chapter
    that customised its mentor dashboard keeps its own version."""
    from .registry import get_page

    page = get_page("record-mentor")
    if page is None or any(p.key == "feedback_nps" for p in page.panels):
        return
    page.panels.append(PanelSpec("feedback_nps", "Recommendation score (feedback)",
                                 "mentor_feedback_nps", VIZ_STAT, width=4))
    page.panels.append(PanelSpec("feedback_month", "Average feedback score by month",
                                 "mentor_feedback_by_month", VIZ_LINE, width=8))


add_mentor_panels()
# Every feedback metric exists only while FEEDBACK_SURVEYS is on: off, the
# library, the Feedback page and the mentor tab look exactly as before.
for _k in ("feedback_responses", "feedback_nps", "feedback_by_month_mentoring",
           "feedback_by_month_event", "feedback_by_month_evaluation", "feedback_by_mentor",
           "feedback_by_event", "feedback_open_follow_ups", "mentor_feedback_nps",
           "mentor_feedback_by_month"):
    SWITCHED_METRICS[_k] = "feedback_surveys"
