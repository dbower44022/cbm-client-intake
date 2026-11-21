"""The feedback sweep: the four automatic moments (ruling BE30; decision 6,
approved by Doug 11-20-26 with the session count as a setting).

The worker runs ``run_sweep`` every ``FEEDBACK_SWEEP_SECONDS``. It reads the
CRM, so a change made in the CRM directly is caught too. Each moment has its
own switch, default off:

1. **An engagement closes** (``FEEDBACK_ON_CLOSE``): its status is Completed,
   Inactive or Abandoned, it has at least one Completed session, and it
   closed (``closeDate``, else its last change) in the look-back. The quiet
   period does not apply (BE33).
2. **The session milestone** (``FEEDBACK_ON_SESSIONS``): the engagement's
   ``FEEDBACK_SESSION_COUNT``-th Completed session (default 3) is more than a
   day old and inside the look-back. Once per engagement.
3. **An event ends** (``FEEDBACK_ON_EVENT``): a Public event, not Cancelled,
   that ended between 24 hours and 14 days ago; each registration marked
   Attended gets one survey, so an attendee marked late is still caught.
4. **A report is released** (``FEEDBACK_ON_EVALUATION``): one survey per
   evaluation round, three days after the round's first release.

**How far back**: only a moment from the last ``FEEDBACK_LOOKBACK_DAYS``
(default 7) sends, so switching a moment on never surveys everyone from
before. Every moment is claimed in ``feedback_send`` first: never twice.
When an engagement's closing and its session milestone land in the same
pass, only the closing survey goes; the milestone is recorded as skipped.

The sweep also retries follow-up alerts that failed. It never raises.
"""

from __future__ import annotations
from core.session_kinds import where_mentoring

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from core.espo import EspoError

from . import config as cfg
from .sending import (CREATED_BY_SWEEP, Sender, contact_recipient, engagement_recipient,
                      mentor_first_name, send, utcnow)
from .store import SKIPPED

log = logging.getLogger("cbm_intake.feedback")

PAGE = 200


def crm_stamp(at: datetime) -> str:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_crm(value: Any) -> Optional[datetime]:
    """An EspoCRM datetime (always UTC, no offset) or date."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ").removesuffix("Z")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


async def _all(client: Any, entity: str, where: list[dict[str, Any]], select: str,
               order_by: str = "") -> list[dict[str, Any]]:
    """Every matching record, a page of 200 at a time (a larger page is a 403)."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        kw: dict[str, Any] = {"where": where, "select": select, "max_size": PAGE,
                              "offset": offset}
        if order_by:
            kw["order_by"] = order_by
        page = await client.list(entity, **kw)
        batch = page.get("list", [])
        rows += batch
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def _lookback(settings: Any, now: datetime) -> datetime:
    days = max(1, int(getattr(settings, "feedback_lookback_days", 7) or 7))
    return now - timedelta(days=days)


def _engagement_context(eng: dict[str, Any]) -> dict[str, Any]:
    return {"mentorFirst": mentor_first_name(eng),
            "company": eng.get("clientOrganizationName") or ""}


def _engagement_data(eng_id: str, eng: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"engagement_id": eng_id, "mentor_profile_id": eng.get("mentorProfileId") or "",
            **extra}


class Sweep:
    """One pass. Holds what the four moments share."""

    def __init__(self, settings: Any, client: Any, store: Any, survey_store: Any,
                 surveys: dict[str, Any], *, sender: Optional[Sender] = None,
                 now: Optional[datetime] = None) -> None:
        self.settings, self.client, self.store = settings, client, store
        self.survey_store, self.surveys, self.sender = survey_store, surveys, sender
        self.now = now or utcnow()
        self.since = _lookback(settings, self.now)
        self.closed_now: set[str] = set()
        self.counts: dict[str, int] = {}

    def _count(self, outcome: str) -> None:
        word = outcome.split(":", 1)[0]
        self.counts[word] = self.counts.get(word, 0) + 1

    async def _send_engagement(self, eng_id: str, *, key: str, survey_key: str, moment: str,
                               quiet: bool, extra: Optional[dict[str, Any]] = None) -> str:
        eng, who = await engagement_recipient(self.client, eng_id, self.settings)
        outcome = await send(
            self.settings, store=self.store, survey_store=self.survey_store,
            surveys=self.surveys, send_key=key, survey_key=survey_key, moment=moment,
            entity_type=cfg.ENGAGEMENT, record_id=eng_id, who=who,
            data=_engagement_data(eng_id, eng, **(extra or {})),
            display_name=eng.get("clientOrganizationName") or eng.get("name") or "",
            context=_engagement_context(eng), quiet=quiet, created_by=CREATED_BY_SWEEP,
            sender=self.sender, now=self.now)
        self._count(outcome)
        return outcome

    # --- 1. an engagement closes ----------------------------------------------

    async def closed(self) -> None:
        rows = await _all(self.client, cfg.ENGAGEMENT, [
            {"type": "in", "attribute": "engagementStatus", "value": list(cfg.CLOSED_STATUSES)},
            {"type": "after", "attribute": "modifiedAt", "value": crm_stamp(self.since)},
        ], "id,engagementStatus,closeDate,modifiedAt")
        for row in rows:
            closed_on = parse_crm(row.get("closeDate")) or parse_crm(row.get("modifiedAt"))
            if closed_on is None or closed_on.date() < self.since.date():
                continue
            done = await self.client.list(cfg.SESSION, where=[
                {"type": "equals", "attribute": "engagementId", "value": row["id"]},
                {"type": "equals", "attribute": "status", "value": cfg.SESSION_COMPLETED},
                where_mentoring(),
            ], select="id", max_size=1)
            if not (done.get("total") or done.get("list")):
                continue
            outcome = await self._send_engagement(
                row["id"], key=f"closed:{row['id']}", survey_key=cfg.SURVEY_MENTORING,
                moment=cfg.MOMENT_CLOSED, quiet=False)
            if outcome in ("sent", "already"):
                self.closed_now.add(row["id"])

    # --- 2. the session milestone ---------------------------------------------

    async def sessions(self) -> None:
        count = max(1, int(getattr(self.settings, "feedback_session_count", 3) or 3))
        latest = self.now - timedelta(hours=cfg.SESSION_WAIT_HOURS)
        earliest = self.since - timedelta(hours=cfg.SESSION_WAIT_HOURS)
        recent = await _all(self.client, cfg.SESSION, [
            {"type": "equals", "attribute": "status", "value": cfg.SESSION_COMPLETED},
                where_mentoring(),
            {"type": "after", "attribute": "dateStart", "value": crm_stamp(earliest)},
            {"type": "before", "attribute": "dateStart", "value": crm_stamp(latest)},
        ], "id,engagementId,dateStart")
        for eng_id in sorted({r.get("engagementId") for r in recent if r.get("engagementId")}):
            done = await _all(self.client, cfg.SESSION, [
                {"type": "equals", "attribute": "engagementId", "value": eng_id},
                {"type": "equals", "attribute": "status", "value": cfg.SESSION_COMPLETED},
                where_mentoring(),
            ], "id,dateStart", order_by="dateStart")
            starts = sorted(d for d in (parse_crm(r.get("dateStart")) for r in done) if d)
            if len(starts) < count:
                continue
            milestone = starts[count - 1]
            if not (earliest <= milestone <= latest):
                continue
            key = f"sessions:{eng_id}"
            if eng_id in self.closed_now:
                if await self.store.claim(key, moment=cfg.MOMENT_SESSIONS,
                                          survey_key=cfg.SURVEY_MENTORING,
                                          entity_type=cfg.ENGAGEMENT, record_id=eng_id,
                                          email="", created_by=CREATED_BY_SWEEP, now=self.now):
                    await self.store.finish(key, SKIPPED, reason="the closing survey went instead",
                                            now=self.now)
                    self._count("skipped")
                continue
            await self._send_engagement(eng_id, key=key, survey_key=cfg.SURVEY_MENTORING,
                                        moment=cfg.MOMENT_SESSIONS, quiet=True)

    # --- 3. an event ends -----------------------------------------------------

    async def events(self) -> None:
        from events.visibility import effective_audience

        latest = self.now - timedelta(hours=cfg.EVENT_WAIT_HOURS)
        earliest = self.now - timedelta(days=cfg.EVENT_WINDOW_DAYS)
        rows = await _all(self.client, cfg.EVENT, [
            {"type": "after", "attribute": "dateEnd", "value": crm_stamp(earliest)},
            {"type": "before", "attribute": "dateEnd", "value": crm_stamp(latest)},
        ], "id,name,status,dateStart,dateEnd,audience,publishToWebsite")
        tz = ZoneInfo(getattr(self.settings, "sms_timezone", "") or "America/New_York")
        for ev in rows:
            if (ev.get("status") or "") == cfg.EVENT_CANCELLED:
                continue
            if effective_audience(ev) != "Public":
                continue
            regs = await _all(self.client, cfg.REGISTRATION, [
                {"type": "equals", "attribute": "eventId", "value": ev["id"]},
                {"type": "equals", "attribute": "attendanceStatus", "value": cfg.REG_ATTENDED},
            ], "id,email,firstName,lastName,contactId")
            start = parse_crm(ev.get("dateStart"))
            context = {"eventName": ev.get("name") or "",
                       "eventDate": start.astimezone(tz) if start else None}
            for reg in regs:
                who = await contact_recipient(self.client, reg.get("contactId") or "")
                if (reg.get("email") or "").strip():
                    who["email"] = reg["email"].strip()
                who["firstName"] = who.get("firstName") or reg.get("firstName") or ""
                who["name"] = who.get("name") or " ".join(
                    p for p in (reg.get("firstName"), reg.get("lastName")) if p)
                outcome = await send(
                    self.settings, store=self.store, survey_store=self.survey_store,
                    surveys=self.surveys, send_key=f"event:{ev['id']}:{reg['id']}",
                    survey_key=cfg.SURVEY_EVENT, moment=cfg.MOMENT_EVENT,
                    entity_type=cfg.EVENT, record_id=ev["id"], who=who,
                    data={"event_id": ev["id"]}, display_name=ev.get("name") or "",
                    context=context, quiet=True, created_by=CREATED_BY_SWEEP,
                    sender=self.sender, now=self.now)
                self._count(outcome)

    # --- 4. a report is released ----------------------------------------------

    async def evaluations(self) -> None:
        wait = timedelta(days=cfg.EVALUATION_WAIT_DAYS)
        latest = self.now - wait
        earliest = self.since - wait
        rows = await _all(self.client, cfg.EVALUATION, [
            {"type": "equals", "attribute": "status", "value": cfg.RELEASED_STATUS},
            {"type": "after", "attribute": "releasedAt", "value": crm_stamp(earliest)},
        ], "id,engagementId,evaluationRound,releasedAt")
        rounds = sorted({(r.get("engagementId"), int(r.get("evaluationRound") or 1))
                         for r in rows if r.get("engagementId")})
        for eng_id, round_no in rounds:
            released = await _all(self.client, cfg.EVALUATION, [
                {"type": "equals", "attribute": "engagementId", "value": eng_id},
                {"type": "equals", "attribute": "evaluationRound", "value": round_no},
                {"type": "equals", "attribute": "status", "value": cfg.RELEASED_STATUS},
            ], "id,releasedAt")
            dated = sorted((parse_crm(r.get("releasedAt")), r["id"]) for r in released
                           if parse_crm(r.get("releasedAt")))
            if not dated:
                continue
            first_at, first_id = dated[0]
            if not (earliest <= first_at <= latest):
                continue
            await self._send_engagement(
                eng_id, key=f"evaluation:{eng_id}:{round_no}",
                survey_key=cfg.SURVEY_EVALUATION, moment=cfg.MOMENT_EVALUATION, quiet=True,
                extra={"business_evaluation_id": first_id, "round": round_no})

    # --- failed alerts ----------------------------------------------------------

    async def retry_alerts(self) -> None:
        from .alerts import alert_once
        from .service import answers_of

        for rid in await self.store.failed_alerts(self.now):
            try:
                r = await self.client.get(cfg.ENTITY, rid, select=(
                    "id,name,surveyKey,recommendScore,eventId,eventName,engagementId,"
                    "engagementName,mentorProfileId,contactName,answers,needsFollowUp"))
            except EspoError as exc:
                log.warning("feedback alert retry: response %s not read: %s", rid, exc)
                continue
            reasons = cfg.follow_up_reasons(answers_of(r.get("answers") or ""))
            outcome = await alert_once(
                self.settings, self.client, self.store, r,
                about=r.get("eventName") or r.get("engagementName") or "",
                who=r.get("contactName") or "", reasons=reasons or ["it was flagged"],
                sender=self.sender)
            self._count(f"alert-{outcome}")


MOMENT_SWITCHES = (
    ("feedback_on_close", "closed"),
    ("feedback_on_sessions", "sessions"),
    ("feedback_on_event", "events"),
    ("feedback_on_evaluation", "evaluations"),
)


async def run_sweep(settings: Any, client: Any, store: Any, survey_store: Any,
                    surveys: dict[str, Any], *, sender: Optional[Sender] = None,
                    now: Optional[datetime] = None) -> dict[str, int]:
    """One pass of every moment switched on, closing first. Returns the counts
    by outcome (for the log and the tests). Never raises."""
    if not cfg.enabled(settings) or store is None or survey_store is None or not surveys:
        return {}
    sweep = Sweep(settings, client, store, survey_store, surveys, sender=sender, now=now)
    for switch, step in MOMENT_SWITCHES:
        if not getattr(settings, switch, False):
            continue
        try:
            await getattr(sweep, step)()
        except Exception as exc:  # noqa: BLE001 — one moment never stops the others
            log.warning("feedback sweep: %s failed: %s", step, exc)
            sweep._count("error")
    try:
        await sweep.retry_alerts()
    except Exception as exc:  # noqa: BLE001
        log.warning("feedback sweep: alert retry failed: %s", exc)
    if sweep.counts:
        log.info("feedback sweep: %s", ", ".join(f"{k}={v}" for k, v in sorted(sweep.counts.items())))
    return sweep.counts
