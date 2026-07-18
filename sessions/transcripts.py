"""Worker retrieval job: Google Meet transcripts -> ``CSession``.

Plan: ``prds/meet-transcript-integration.md`` §4. Runs on its own worker timer
(``MEET_TRANSCRIPTS_POLL_SECONDS``, monitoring-check pattern) under the
**API-key client** (comms-sync precedent — the CustomAppAPIRole needs CSession
read + edit). For every recent past session with a Meet link and no transcript
yet, it impersonates the meeting organizer (their ``CMentorProfile.cbmEmail``,
the same identity the calendar hook created the event with), finds the
conference's ended transcript, formats speaker-attributed HTML, and writes it
back to ``sessionTranscription`` plus the permanent Google Doc link to
``transcriptDocUrl`` (both CRM fields feature-detected).

Best-effort throughout: no Google/CRM failure ever crashes a worker cycle, and
a per-session failure never blocks the rest of the batch. No retry state is
stored — a session simply stays a candidate until it gains a transcript or its
``dateStart`` falls out of the ``TRANSCRIPT_GIVE_UP_DAYS`` window (meeting
never happened, or transcription was off).

Provider seam: :class:`TranscriptSource` — phase 1 ships only
:class:`MeetTranscriptSource`; a Zoom source can slot in later keyed off the
link's host.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from assignments.service import assigned_user_id
from core.gmeet import (
    MeetClient,
    format_transcript_html,
    meeting_code,
    participant_names,
)
from sessions.config import (
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


class TranscriptSource:
    """Provider seam: given (session, organizer mailbox), find its transcript."""

    def matches(self, link: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    async def fetch(
        self, session: dict[str, Any], mailbox: str
    ) -> SourceResult:  # pragma: no cover - interface
        raise NotImplementedError


class MeetTranscriptSource(TranscriptSource):
    """Google Meet REST v2, impersonating the organizer (DWD)."""

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


# --- the worker cycle ---------------------------------------------------------


async def run_transcript_cycle(
    settings: Any,
    espo: Any,
    *,
    source: Optional[TranscriptSource] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """One retrieval pass. Returns a summary dict (logged by the caller too).

    ``source`` is a test-injection seam; by default the Meet source is built
    from the shared Google service account (Email-Setup config first, env
    fallback — the same resolution the gcal hook uses).
    """
    if not getattr(settings, "meet_transcripts", False):
        return {"skipped": "disabled"}
    fields = await espo.metadata(f"entityDefs.{SESSION}.fields")
    if TRANSCRIPT_FIELD not in fields:
        log.info("transcript retrieval waiting: the CRM has no %s field yet",
                 TRANSCRIPT_FIELD)
        return {"skipped": f"no {TRANSCRIPT_FIELD} field"}
    has_doc_url = TRANSCRIPT_DOC_URL_FIELD in fields

    if source is None:
        from comms.service import get_service_account  # shared, process-cached

        sa_info = await get_service_account(settings)
        if sa_info is None:
            log.warning("transcript retrieval: no Google service account configured")
            return {"skipped": "no service account"}
        source = MeetTranscriptSource(
            sa_info, getattr(settings, "request_timeout_seconds", 20)
        )

    now = now or datetime.now(timezone.utc)
    candidates = await _candidate_sessions(settings, espo, now)
    summary = {"candidates": len(candidates), "stored": 0, "pending": 0, "skipped": 0}
    mailboxes: Optional[dict[str, str]] = None  # user id -> cbmEmail, lazy
    for session in candidates:
        try:
            if not source.matches(session.get("videoMeetingLink") or ""):
                summary["skipped"] += 1
                continue
            if mailboxes is None:
                mailboxes = await _mentor_mailboxes(espo)
            mailbox = await _organizer_mailbox(espo, session, mailboxes)
            if not mailbox:
                log.info("transcript skip %s: no resolvable organizer mailbox",
                         session.get("id"))
                summary["skipped"] += 1
                continue
            result = await source.fetch(session, mailbox)
            if result.status == "ready":
                await _write_back(espo, session["id"], result, has_doc_url)
                summary["stored"] += 1
            elif result.status == "not_ready":
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
    settings: Any, espo: Any, now: datetime
) -> list[dict[str, Any]]:
    """Past Meet-linked sessions still awaiting a transcript, inside the
    give-up window. Status is deliberately NOT required to be Completed —
    mentors don't reliably flip it."""
    give_up_days = getattr(settings, "transcript_give_up_days", 14)
    cutoff = now - timedelta(days=give_up_days)
    parent_fks = [cfg.session_parent_fk for cfg in DOMAINS.values()]
    select = ",".join(
        ["id", "name", "dateStart", "videoMeetingLink",
         "assignedUserId", "assignedUsersIds", *parent_fks]
    )
    where = [
        {"type": "contains", "attribute": "videoMeetingLink",
         "value": "meet.google.com"},
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


async def _write_back(
    espo: Any, session_id: str, result: SourceResult, has_doc_url: bool
) -> None:
    payload: dict[str, Any] = {TRANSCRIPT_FIELD: clamp_transcript(result.html)}
    if has_doc_url and result.doc_url:
        payload[TRANSCRIPT_DOC_URL_FIELD] = result.doc_url
    await espo.update(SESSION, session_id, payload)
    log.info("transcript stored for session %s (%d chars%s)",
             session_id, len(payload[TRANSCRIPT_FIELD]),
             ", doc link" if payload.get(TRANSCRIPT_DOC_URL_FIELD) else "")
