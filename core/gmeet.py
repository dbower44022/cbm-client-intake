"""Delegated Google Meet REST access for meeting transcripts.

One :class:`MeetClient` per organizer: the shared Google service account (the
same key Gmail/Calendar/Drive use) mints a short-lived access token with
domain-wide delegation, impersonating exactly ONE ``@cbmentors.org`` user
(``subject``) — the meeting organizer, resolved from CRM identity
(``CMentorProfile.cbmEmail``), never from request input. The
``meetings.space.created`` scope covers config writes and artifact reads on
Meet spaces the impersonated user owns, which is exactly our model: the
calendar hook creates the meeting as the organizing manager.

Plain REST via httpx (like :mod:`core.gcalendar`) — no google-api-python-client
dependency. Every impersonated access is logged.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.gmeet")

MEET_SPACE_SCOPE = "https://www.googleapis.com/auth/meetings.space.created"

_BASE = "https://meet.googleapis.com/v2"


class MeetError(Exception):
    """Any Meet API / auth failure."""


class MeetClient:
    """Meet REST for ONE organizer, authenticated by delegated impersonation."""

    def __init__(
        self, service_account_info: dict[str, Any], mailbox: str, timeout: int = 20
    ) -> None:
        self.mailbox = mailbox
        self._info = service_account_info
        self._timeout = timeout
        self._tokens: dict[str, tuple[str, float]] = {}  # scope -> (token, expiry)

    # --- auth -----------------------------------------------------------

    async def _token(self, scope: str = MEET_SPACE_SCOPE) -> str:
        cached = self._tokens.get(scope)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account

            def mint() -> tuple[str, float]:
                creds = service_account.Credentials.from_service_account_info(
                    self._info, scopes=[scope], subject=self.mailbox
                )
                creds.refresh(Request())
                expiry = creds.expiry.timestamp() if creds.expiry else time.time() + 1800
                return creds.token, expiry

            token, expiry = await asyncio.to_thread(mint)
        except Exception as exc:  # bad key, delegation not authorized, network, …
            raise MeetError(f"Meet auth failed for {self.mailbox}: {exc}") from exc
        self._tokens[scope] = (token, expiry)
        log.info("meet access as %s", self.mailbox)
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        token = await self._token()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(
                    method,
                    f"{_BASE}{path}",
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise MeetError(f"Meet request failed ({path}): {exc}") from exc
        if resp.status_code >= 400:
            raise MeetError(
                f"Meet {method} {path} for {self.mailbox}: HTTP {resp.status_code} "
                f"{resp.text[:300]}"
            )
        return resp.json() if resp.content else {}

    async def _paged(
        self, path: str, *, params: Optional[dict[str, Any]] = None, items_key: str
    ) -> list[dict[str, Any]]:
        """Collect every page of a list endpoint (``nextPageToken`` paging)."""
        items: list[dict[str, Any]] = []
        page_params = dict(params or {})
        while True:
            data = await self._request("GET", path, params=page_params)
            items.extend(data.get(items_key) or [])
            token = data.get("nextPageToken")
            if not token:
                return items
            page_params["pageToken"] = token

    # --- spaces (schedule-time transcription enable) ------------------------

    async def get_space(self, meeting_code: str) -> dict[str, Any]:
        """The Meet space for a meeting code (``spaces/{meetingCode}`` lookup)."""
        return await self._request("GET", f"/spaces/{meeting_code}")

    async def enable_auto_transcription(self, space_name: str) -> dict[str, Any]:
        """Turn on automatic transcription for every future call in the space.

        Only the space owner (the impersonated organizer) may set this — which
        is why the client is always built for the manager who scheduled the
        meeting.
        """
        space = await self._request(
            "PATCH",
            f"/{space_name}",
            params={
                "updateMask": (
                    "config.artifactConfig.transcriptionConfig."
                    "autoTranscriptionGeneration"
                )
            },
            json_body={
                "config": {
                    "artifactConfig": {
                        "transcriptionConfig": {"autoTranscriptionGeneration": "ON"}
                    }
                }
            },
        )
        log.info("auto-transcription enabled as %s on %s", self.mailbox, space_name)
        return space

    # --- conference artifacts (retrieval) -----------------------------------

    async def list_conference_records(
        self, meeting_code: str, start_after: datetime, start_before: datetime
    ) -> list[dict[str, Any]]:
        """Past conferences for a meeting code inside a start-time window.

        The window disambiguates reused/recurring codes — the same space hosts
        every occurrence, so the caller brackets the session's own start time.
        Returned newest-first.
        """
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        filter_expr = (
            f'space.meeting_code = "{meeting_code}"'
            f' AND start_time>="{start_after.strftime(fmt)}"'
            f' AND start_time<="{start_before.strftime(fmt)}"'
        )
        records = await self._paged(
            "/conferenceRecords",
            params={"filter": filter_expr},
            items_key="conferenceRecords",
        )
        return sorted(records, key=lambda r: r.get("startTime") or "", reverse=True)

    async def list_transcripts(self, conference_record: str) -> list[dict[str, Any]]:
        """The transcripts of one conference record (``conferenceRecords/{id}``)."""
        return await self._paged(
            f"/{conference_record}/transcripts", items_key="transcripts"
        )

    async def list_transcript_entries(
        self, transcript_name: str, page_size: int = 1000
    ) -> list[dict[str, Any]]:
        """Every structured entry of a transcript, in spoken order."""
        return await self._paged(
            f"/{transcript_name}/entries",
            params={"pageSize": page_size},
            items_key="transcriptEntries",
        )

    async def list_participants(self, conference_record: str) -> list[dict[str, Any]]:
        """The conference's participants (for speaker display names)."""
        return await self._paged(
            f"/{conference_record}/participants", items_key="participants"
        )


# --- pure helpers (no HTTP) ---------------------------------------------------

# Meet meeting codes are lowercase letter groups joined by dashes
# (e.g. "abc-mnop-xyz"); the path may carry a query string after it.
_MEET_CODE_RE = re.compile(r"meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})", re.I)


def meeting_code(link: Optional[str]) -> Optional[str]:
    """The meeting code inside a Google Meet URL, or None for any other link."""
    m = _MEET_CODE_RE.search(link or "")
    return m.group(1).lower() if m else None


def participant_names(participants: list[dict[str, Any]]) -> dict[str, str]:
    """Map participant resource name -> display name (signed-in / anonymous /
    phone participants each carry the name in their own sub-object)."""
    names: dict[str, str] = {}
    for p in participants:
        display = ""
        for kind in ("signedinUser", "anonymousUser", "phoneUser"):
            if p.get(kind, {}).get("displayName"):
                display = p[kind]["displayName"]
                break
        if p.get("name"):
            names[p["name"]] = display
    return names


def _parse_time(stamp: Optional[str]) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _offset_label(start: Optional[datetime], first: Optional[datetime]) -> str:
    """Elapsed [MM:SS] / [H:MM:SS] since the first entry — timezone-free."""
    if start is None or first is None:
        return ""
    secs = max(0, int((start - first).total_seconds()))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"


def format_transcript_html(
    entries: list[dict[str, Any]], names: dict[str, str]
) -> str:
    """Speaker-attributed HTML for ``CSession.sessionTranscription``.

    One paragraph per speaker turn — consecutive entries by the same speaker
    merge into it — each opened with the speaker's name in bold and the elapsed
    time since the transcript began. All text is escaped; only the tags emitted
    here reach the CRM (the UI sanitizes again on render).
    """
    first = _parse_time((entries[0].get("startTime") if entries else None))
    paragraphs: list[str] = []
    current_speaker: Optional[str] = None
    for entry in entries:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        speaker = names.get(entry.get("participant") or "") or "Unknown speaker"
        if speaker != current_speaker:
            label = _offset_label(_parse_time(entry.get("startTime")), first)
            head = f"<strong>{html.escape(speaker)}</strong>"
            if label:
                head += f" <em>{label}</em>"
            paragraphs.append(f"<p>{head}<br>{html.escape(text)}")
            current_speaker = speaker
        else:
            paragraphs[-1] += f" {html.escape(text)}"
    return "</p>\n".join(paragraphs) + ("</p>" if paragraphs else "")
