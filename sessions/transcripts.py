"""Worker retrieval job: meeting transcripts -> ``CSession``.

Plans: ``prds/meet-transcript-integration.md`` §4 (Google Meet) and
``prds/fathom-transcript-integration.md`` (Fathom note taker). Runs on its
own worker timer (``MEET_TRANSCRIPTS_POLL_SECONDS``, monitoring-check
pattern) under the **API-key client** (comms-sync precedent — the
CustomAppAPIRole needs CSession read + edit). For every recent past session
with a meeting link and no transcript yet, it walks an **ordered provider
list** — Fathom first when enabled (one team-key listing sweep per cycle,
matched by normalized join URL + start window), then Google Meet
(impersonating the meeting organizer's ``CMentorProfile.cbmEmail``) — and
writes the first ready result back: speaker-attributed HTML into
``sessionTranscription``, the permanent link (Google Doc or Fathom share
URL) into ``transcriptDocUrl``, and — Fathom only — the AI summary into
``sessionAiSummary`` plus the action items into an EMPTY ``nextSteps``
(never over human content; a non-empty ``nextSteps`` diverts them into the
summary field). All CRM fields feature-detected.

Best-effort throughout: no Google/Fathom/CRM failure ever crashes a worker
cycle, and a per-session failure never blocks the rest of the batch. No
retry state is stored — a session simply stays a candidate until it gains a
transcript or its ``dateStart`` falls out of the ``TRANSCRIPT_GIVE_UP_DAYS``
window (meeting never happened, or transcription was off).

Provider seam: :class:`TranscriptSource` — :class:`FathomTranscriptSource`
and :class:`MeetTranscriptSource`; source order IS the precedence ruling.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from assignments.service import assigned_user_id
from core import fathom
from core.fathom import FathomClient, FathomError, normalize_meeting_url
from core.gmeet import (
    MeetClient,
    format_transcript_html,
    meeting_code,
    participant_names,
)
from sessions.config import (
    AI_SUMMARY_FIELD,
    DOMAINS,
    MENTOR_PROFILE,
    SESSION,
    TRANSCRIPT_DOC_URL_FIELD,
    TRANSCRIPT_FIELD,
)

log = logging.getLogger("cbm_intake.sessions.transcripts")

_PAGE = 200

# A wysiwyg column is finite: clamp a marathon transcript rather than 400 the
# whole write. The cut lands on a paragraph boundary and says where the rest is.
TRANSCRIPT_MAX_CHARS = 200_000
_TRUNCATION_NOTE = (
    "<p><em>Transcript truncated — the full transcript is in the linked "
    "Google Doc.</em></p>"
)

# How far around the session's scheduled start a conference may have started
# and still count as THIS session's meeting (disambiguates reused/recurring
# meeting codes; generous because real meetings run early, late, or next-day).
_MATCH_WINDOW = timedelta(hours=36)


@dataclass
class SourceResult:
    """What a provider found for one session."""

    status: str  # "ready" | "not_ready" | "skip"
    html: str = ""
    doc_url: str = ""
    reason: str = ""
    summary_html: str = ""        # Fathom AI summary (already sanitized HTML)
    action_items_html: str = ""   # Fathom task list (already sanitized HTML)


class TranscriptSource:
    """Provider seam: given (session, organizer mailbox), find its transcript."""

    # Whether fetch() needs the organizer's CBM mailbox (DWD impersonation).
    needs_mailbox = True
    # A candidate-query narrowing hint: sessions whose link contains this
    # substring. None = the source can serve any meeting link, so the CRM
    # query must not pre-filter by host.
    link_contains: Optional[str] = None

    def matches(self, link: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    async def fetch(
        self, session: dict[str, Any], mailbox: str
    ) -> SourceResult:  # pragma: no cover - interface
        raise NotImplementedError


class MeetTranscriptSource(TranscriptSource):
    """Google Meet REST v2, impersonating the organizer (DWD)."""

    link_contains = "meet.google.com"

    def __init__(self, sa_info: dict[str, Any], timeout: int = 20) -> None:
        self._sa_info = sa_info
        self._timeout = timeout

    def matches(self, link: str) -> bool:
        return meeting_code(link) is not None

    async def fetch(self, session: dict[str, Any], mailbox: str) -> SourceResult:
        code = meeting_code(session.get("videoMeetingLink"))
        if not code:
            return SourceResult("skip", reason="no Meet meeting code in the link")
        start = _parse_stamp(session.get("dateStart"))
        if start is None:
            return SourceResult("skip", reason="unusable dateStart")
        meet = MeetClient(self._sa_info, mailbox, self._timeout)
        records = await meet.list_conference_records(
            code, start - _MATCH_WINDOW, start + _MATCH_WINDOW
        )
        if not records:
            return SourceResult("not_ready", reason="no conference record yet")
        for record in records:  # newest first
            transcript = await _pick_transcript(meet, record.get("name") or "")
            if transcript is None:
                continue
            entries = await meet.list_transcript_entries(transcript["name"])
            if not entries:
                continue
            names = participant_names(
                await meet.list_participants(record["name"])
            )
            html_text = format_transcript_html(entries, names)
            if not html_text:
                continue  # entries with no speech — treat as no transcript
            docs = transcript.get("docsDestination") or {}
            return SourceResult(
                "ready", html=html_text, doc_url=docs.get("exportUri") or ""
            )
        return SourceResult(
            "not_ready", reason="conference found, transcript not ready"
        )


async def _pick_transcript(
    meet: MeetClient, record_name: str
) -> Optional[dict[str, Any]]:
    """The conference's first finished transcript (a STARTED one isn't done)."""
    if not record_name:
        return None
    for t in await meet.list_transcripts(record_name):
        if t.get("name") and t.get("state") in ("ENDED", "FILE_GENERATED"):
            return t
    return None


class FathomTranscriptSource(TranscriptSource):
    """Fathom external API, authenticated by the single CBM team key.

    One ``GET /meetings`` sweep per cycle (lazy, cached on the instance — a
    fresh source is built each cycle), indexed by the normalized join URL;
    every candidate session resolves against the in-memory index, so only a
    matched session costs a per-recording transcript call. A listing failure
    marks the whole cycle ``not_ready`` for this source (the Meet fallback
    still runs) rather than erroring per session.
    """

    needs_mailbox = False
    link_contains = None  # Fathom records Meet, Zoom, and Teams meetings

    def __init__(
        self, client: FathomClient, *, now: datetime, give_up_days: int = 14
    ) -> None:
        self._client = client
        # Cover a meeting held up to a match-window before the oldest
        # still-candidate session's start.
        self._created_after = now - timedelta(days=give_up_days) - _MATCH_WINDOW
        self._index: Optional[dict[str, list[dict[str, Any]]]] = None
        self._listing_failed = False

    def matches(self, link: str) -> bool:
        return normalize_meeting_url(link) is not None

    async def _ensure_index(self) -> None:
        if self._index is not None:
            return
        try:
            meetings = await self._client.list_meetings(self._created_after)
        except FathomError as exc:
            log.warning("fathom listing failed (source idle this cycle): %s", exc)
            self._index = {}
            self._listing_failed = True
            return
        index: dict[str, list[dict[str, Any]]] = {}
        for meeting in meetings:
            key = normalize_meeting_url(meeting.get("meeting_url"))
            if key:
                index.setdefault(key, []).append(meeting)
        self._index = index

    async def fetch(self, session: dict[str, Any], mailbox: str) -> SourceResult:
        key = normalize_meeting_url(session.get("videoMeetingLink"))
        if not key:
            return SourceResult("skip", reason="unrecognized meeting link")
        start = _parse_stamp(session.get("dateStart"))
        if start is None:
            return SourceResult("skip", reason="unusable dateStart")
        await self._ensure_index()
        if self._listing_failed:
            return SourceResult("not_ready", reason="Fathom unavailable this cycle")
        meeting = _closest_meeting(
            (self._index or {}).get(key, []), start
        )
        if meeting is None:
            return SourceResult("not_ready", reason="no Fathom recording yet")
        recorded_by = ((meeting.get("recorded_by") or {}).get("email") or "").lower()
        if mailbox and recorded_by and recorded_by != mailbox:
            # Soft check only — a co-mentor or the client may have run Fathom.
            log.info(
                "fathom match for session %s recorded by %s (organizer %s)",
                session.get("id"), recorded_by, mailbox,
            )
        entries = meeting.get("transcript")
        if not isinstance(entries, list):
            recording_id = meeting.get("recording_id") or meeting.get("id")
            if recording_id is None:
                return SourceResult("not_ready", reason="meeting has no recording id")
            entries = await self._client.get_transcript(recording_id)
        html_text = fathom.format_transcript_html(entries or [])
        if not html_text:
            return SourceResult("not_ready", reason="transcript not ready")
        return SourceResult(
            "ready",
            html=html_text,
            doc_url=meeting.get("share_url") or meeting.get("url") or "",
            summary_html=fathom.summary_html(_summary_markdown(meeting)),
            action_items_html=fathom.action_items_html(meeting.get("action_items")),
        )


def _summary_markdown(meeting: dict[str, Any]) -> str:
    """The meeting's summary markdown, whatever shape the API returned."""
    raw = meeting.get("summary")
    if isinstance(raw, dict):
        return (
            raw.get("markdown_formatted") or raw.get("markdown")
            or raw.get("text") or ""
        )
    return str(raw or "")


def _closest_meeting(
    meetings: list[dict[str, Any]], session_start: datetime
) -> Optional[dict[str, Any]]:
    """The meeting starting closest to the session inside the match window
    (disambiguates reused meeting links, mirroring the Meet source)."""
    best: Optional[dict[str, Any]] = None
    best_gap: Optional[timedelta] = None
    for meeting in meetings:
        start = _parse_iso(
            meeting.get("recording_start_time") or meeting.get("scheduled_start_time")
        )
        if start is None:
            continue
        gap = abs(start - session_start)
        if gap > _MATCH_WINDOW:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = meeting, gap
    return best


def _parse_iso(stamp: Any) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


# --- the worker cycle ---------------------------------------------------------


async def run_transcript_cycle(
    settings: Any,
    espo: Any,
    *,
    sources: Optional[list[TranscriptSource]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """One retrieval pass. Returns a summary dict (logged by the caller too).

    ``sources`` is a test-injection seam; by default the list is built from
    config, in precedence order (Doug's ruling): Fathom first when enabled,
    then the Meet source from the shared Google service account (Email-Setup
    config first, env fallback — the same resolution the gcal hook uses).
    """
    fathom_on = getattr(settings, "fathom_transcripts", False)
    meet_on = getattr(settings, "meet_transcripts", False)
    if not (fathom_on or meet_on):
        return {"skipped": "disabled"}
    fields = await espo.metadata(f"entityDefs.{SESSION}.fields")
    if TRANSCRIPT_FIELD not in fields:
        log.info("transcript retrieval waiting: the CRM has no %s field yet",
                 TRANSCRIPT_FIELD)
        return {"skipped": f"no {TRANSCRIPT_FIELD} field"}
    has_doc_url = TRANSCRIPT_DOC_URL_FIELD in fields
    has_ai_summary = AI_SUMMARY_FIELD in fields

    now = now or datetime.now(timezone.utc)
    if sources is None:
        sources = []
        if fathom_on:
            api_key = getattr(settings, "fathom_api_key", "")
            if api_key:
                sources.append(FathomTranscriptSource(
                    FathomClient(
                        api_key,
                        base_url=getattr(
                            settings, "fathom_base_url", fathom.DEFAULT_BASE_URL
                        ) or fathom.DEFAULT_BASE_URL,
                        timeout=getattr(settings, "request_timeout_seconds", 20),
                    ),
                    now=now,
                    give_up_days=getattr(settings, "transcript_give_up_days", 14),
                ))
            else:
                log.warning("transcript retrieval: FATHOM_TRANSCRIPTS is on "
                            "but no FATHOM_API_KEY is set")
        if meet_on:
            from comms.service import get_service_account  # shared, process-cached

            sa_info = await get_service_account(settings)
            if sa_info is not None:
                sources.append(MeetTranscriptSource(
                    sa_info, getattr(settings, "request_timeout_seconds", 20)
                ))
            else:
                log.warning(
                    "transcript retrieval: no Google service account configured")
        if not sources:
            return {"skipped": "no sources"}

    candidates = await _candidate_sessions(
        settings, espo, now,
        any_link=any(s.link_contains is None for s in sources),
    )
    summary = {"candidates": len(candidates), "stored": 0, "pending": 0, "skipped": 0}
    mailboxes: Optional[dict[str, str]] = None  # user id -> cbmEmail, lazy
    for session in candidates:
        try:
            link = session.get("videoMeetingLink") or ""
            stored = pending = False
            for source in sources:
                if not source.matches(link):
                    continue
                mailbox = ""
                if source.needs_mailbox:
                    if mailboxes is None:
                        mailboxes = await _mentor_mailboxes(espo)
                    mailbox = await _organizer_mailbox(espo, session, mailboxes) or ""
                    if not mailbox:
                        log.info(
                            "transcript skip %s (%s): no resolvable organizer "
                            "mailbox", session.get("id"), type(source).__name__,
                        )
                        continue
                try:
                    result = await source.fetch(session, mailbox)
                except Exception as exc:  # noqa: BLE001 — fall through to the next source
                    log.warning("transcript source %s failed for session %s: %s",
                                type(source).__name__, session.get("id"), exc)
                    continue
                if result.status == "ready":
                    await _write_back(
                        espo, session, result, has_doc_url, has_ai_summary
                    )
                    stored = True
                    break
                if result.status == "not_ready":
                    pending = True
            if stored:
                summary["stored"] += 1
            elif pending:
                summary["pending"] += 1
            else:
                summary["skipped"] += 1
        except Exception as exc:  # noqa: BLE001 — one session never sinks the batch
            log.warning("transcript retrieval failed for session %s: %s",
                        session.get("id"), exc)
            summary["skipped"] += 1
    if summary["stored"]:
        log.info("transcript cycle: %s", summary)
    return summary


def _parse_stamp(stamp: Any) -> Optional[datetime]:
    """CRM ``"YYYY-MM-DD HH:MM:SS"`` (UTC) -> aware datetime."""
    try:
        return datetime.strptime(str(stamp).strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None


def _fmt_stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def _candidate_sessions(
    settings: Any, espo: Any, now: datetime, *, any_link: bool = False
) -> list[dict[str, Any]]:
    """Past meeting-linked sessions still awaiting a transcript, inside the
    give-up window. Status is deliberately NOT required to be Completed —
    mentors don't reliably flip it. ``any_link`` widens the link filter from
    Meet-only to any non-empty link (a Fathom-capable cycle serves Zoom/Teams
    links too); per-link routing stays in Python via ``matches()``.
    ``nextSteps`` rides the select for the action-items routing rule."""
    give_up_days = getattr(settings, "transcript_give_up_days", 14)
    cutoff = now - timedelta(days=give_up_days)
    parent_fks = [cfg.session_parent_fk for cfg in DOMAINS.values()]
    select = ",".join(
        ["id", "name", "dateStart", "videoMeetingLink", "nextSteps",
         "assignedUserId", "assignedUsersIds", *parent_fks]
    )
    link_clause: dict[str, Any] = (
        {"type": "isNotNull", "attribute": "videoMeetingLink"}
        if any_link
        else {"type": "contains", "attribute": "videoMeetingLink",
              "value": "meet.google.com"}
    )
    where = [
        link_clause,
        {"type": "after", "attribute": "dateStart", "value": _fmt_stamp(cutoff)},
        {"type": "before", "attribute": "dateStart", "value": _fmt_stamp(now)},
        # The app only ever writes a non-empty transcript, so null == untried.
        {"type": "isNull", "attribute": TRANSCRIPT_FIELD},
    ]
    sessions: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await espo.list(
            SESSION, where=where, select=select, max_size=_PAGE, offset=offset
        )
        rows = data.get("list", [])
        sessions.extend(rows)
        if len(rows) < _PAGE:
            return sessions
        offset += _PAGE


async def _mentor_mailboxes(espo: Any) -> dict[str, str]:
    """Login-User id -> CBM mailbox, over every linked mentor profile (one
    paginated sweep per cycle; matched in Python, never a ``where`` on
    ``assignedUserId`` — prod forbids it)."""
    mailboxes: dict[str, str] = {}
    offset = 0
    while True:
        data = await espo.list(
            MENTOR_PROFILE,
            select="id,assignedUserId,assignedUsersIds,cbmEmail",
            max_size=_PAGE,
            offset=offset,
        )
        rows = data.get("list", [])
        for r in rows:
            email = (r.get("cbmEmail") or "").strip().lower()
            uid = assigned_user_id(r)
            if email and uid:
                mailboxes.setdefault(uid, email)
        if len(rows) < _PAGE:
            return mailboxes
        offset += _PAGE


async def _organizer_mailbox(
    espo: Any, session: dict[str, Any], mailboxes: dict[str, str]
) -> Optional[str]:
    """The meeting organizer's CBM mailbox.

    First the session's own assigned users (the calendar hook stamped the
    creator, whose mailbox the event was created with); then the parent
    record's manager profile as a fallback for sessions stamped differently.
    """
    user_ids = [session.get("assignedUserId")] + list(
        session.get("assignedUsersIds") or []
    )
    for uid in user_ids:
        if uid and mailboxes.get(uid):
            return mailboxes[uid]
    for cfg in DOMAINS.values():
        parent_id = session.get(cfg.session_parent_fk)
        if not parent_id or not cfg.parent_manager_link:
            continue
        try:
            parent = await espo.get(
                cfg.parent_entity, parent_id,
                select=f"{cfg.parent_manager_link}Id",
            )
            profile_id = parent.get(f"{cfg.parent_manager_link}Id")
            if not profile_id:
                continue
            profile = await espo.get(MENTOR_PROFILE, profile_id, select="cbmEmail")
            email = (profile.get("cbmEmail") or "").strip().lower()
            if email:
                return email
        except Exception as exc:  # noqa: BLE001 — fallback is best-effort
            log.debug("organizer fallback failed via %s/%s: %s",
                      cfg.parent_entity, parent_id, exc)
    return None


def clamp_transcript(html_text: str) -> str:
    """Cut an oversized transcript at a paragraph boundary + truncation note."""
    if len(html_text) <= TRANSCRIPT_MAX_CHARS:
        return html_text
    cut = html_text.rfind("</p>", 0, TRANSCRIPT_MAX_CHARS)
    kept = html_text[: cut + 4] if cut > 0 else html_text[:TRANSCRIPT_MAX_CHARS]
    return kept + "\n" + _TRUNCATION_NOTE


_TAG_RE = re.compile(r"<[^>]+>")


def richtext_empty(value: Any) -> bool:
    """Whether a wysiwyg value is empty for routing purposes — null, blank,
    or blank markup (``<p><br></p>`` etc.; tags and &nbsp; don't count)."""
    text = _TAG_RE.sub(" ", str(value or ""))
    return not text.replace("&nbsp;", " ").strip()


async def _write_back(
    espo: Any,
    session: dict[str, Any],
    result: SourceResult,
    has_doc_url: bool,
    has_ai_summary: bool,
) -> None:
    session_id = session["id"]
    payload: dict[str, Any] = {TRANSCRIPT_FIELD: clamp_transcript(result.html)}
    if has_doc_url and result.doc_url:
        payload[TRANSCRIPT_DOC_URL_FIELD] = result.doc_url
    # Action-items routing (Doug's 2026-07-21 ruling): the task list fills an
    # EMPTY nextSteps; anything the mentor already wrote diverts the list into
    # the AI summary instead — human content is never touched. This runs once
    # per session (candidates are transcript-null), so a mentor's later next
    # steps can never be overwritten.
    summary_html = result.summary_html
    if result.action_items_html:
        if richtext_empty(session.get("nextSteps")):
            payload["nextSteps"] = result.action_items_html
        elif has_ai_summary:
            summary_html = (
                (summary_html + "\n" if summary_html else "")
                + "<p><strong>Action items</strong></p>\n"
                + result.action_items_html
            )
        else:
            log.info("action items dropped for session %s: nextSteps has "
                     "content and the CRM has no %s field",
                     session_id, AI_SUMMARY_FIELD)
    if summary_html:
        if has_ai_summary:
            payload[AI_SUMMARY_FIELD] = summary_html
        else:
            log.info("AI summary dropped for session %s: the CRM has no %s "
                     "field", session_id, AI_SUMMARY_FIELD)
    await espo.update(SESSION, session_id, payload)
    log.info("transcript stored for session %s (%d chars%s%s%s)",
             session_id, len(payload[TRANSCRIPT_FIELD]),
             ", doc link" if payload.get(TRANSCRIPT_DOC_URL_FIELD) else "",
             ", ai summary" if payload.get(AI_SUMMARY_FIELD) else "",
             ", action items" if payload.get("nextSteps") else "")
