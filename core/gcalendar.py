"""Delegated Google Calendar access for the Session Management tools.

One :class:`CalendarClient` per organizer: the shared Google service account
(the same key Gmail/Directory use) mints a short-lived access token with
domain-wide delegation, impersonating exactly ONE ``@cbmentors.org`` user
(``subject``) — the signed-in manager, resolved from their own CRM identity
(``CMentorProfile.cbmEmail``), never from request input. Events are created on
that user's OWN primary calendar, so the manager is the meeting organizer.

Plain REST via httpx (like :mod:`core.gmail`) — no google-api-python-client
dependency. Every impersonated access is logged.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.gcalendar")

CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"

_BASE = "https://www.googleapis.com/calendar/v3"

# Every write carries these: sendUpdates emails the attendees their invitation /
# update / cancellation; conferenceDataVersion=1 is required for Google to act
# on (and return) conferenceData — without it the Meet request is ignored.
_WRITE_PARAMS = {"sendUpdates": "all", "conferenceDataVersion": 1}


class CalendarError(Exception):
    """Any Calendar API / auth failure."""


class CalendarClient:
    """Calendar REST for ONE organizer, authenticated by delegated impersonation."""

    def __init__(
        self, service_account_info: dict[str, Any], mailbox: str, timeout: int = 20
    ) -> None:
        self.mailbox = mailbox
        self._info = service_account_info
        self._timeout = timeout
        self._tokens: dict[str, tuple[str, float]] = {}  # scope -> (token, expiry)

    # --- auth -----------------------------------------------------------

    async def _token(self, scope: str = CALENDAR_EVENTS_SCOPE) -> str:
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
            raise CalendarError(f"Calendar auth failed for {self.mailbox}: {exc}") from exc
        self._tokens[scope] = (token, expiry)
        log.info("calendar access as %s", self.mailbox)
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        ok_statuses: tuple[int, ...] = (),
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
            raise CalendarError(f"Calendar request failed ({path}): {exc}") from exc
        if resp.status_code >= 400 and resp.status_code not in ok_statuses:
            raise CalendarError(
                f"Calendar {method} {path} for {self.mailbox}: HTTP {resp.status_code} "
                f"{resp.text[:300]}"
            )
        return resp.json() if resp.content and resp.status_code < 400 else {}

    # --- events (all on the impersonated user's own primary calendar) ------

    async def create_event(self, body: dict[str, Any]) -> dict[str, Any]:
        event = await self._request(
            "POST", "/calendars/primary/events", params=_WRITE_PARAMS, json_body=body
        )
        log.info("calendar event created as %s -> %s", self.mailbox, event.get("id"))
        return event

    async def get_event(self, event_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/calendars/primary/events/{event_id}")

    async def patch_event(self, event_id: str, body: dict[str, Any]) -> dict[str, Any]:
        event = await self._request(
            "PATCH",
            f"/calendars/primary/events/{event_id}",
            params=_WRITE_PARAMS,
            json_body=body,
        )
        log.info("calendar event updated as %s -> %s", self.mailbox, event_id)
        return event

    async def delete_event(self, event_id: str) -> None:
        """Cancel an event (attendees get the cancellation email). An event
        that is already gone (404) or already cancelled (410) counts as done."""
        await self._request(
            "DELETE",
            f"/calendars/primary/events/{event_id}",
            params={"sendUpdates": "all"},
            ok_statuses=(404, 410),
        )
        log.info("calendar event cancelled as %s -> %s", self.mailbox, event_id)


# --- pure helpers (no HTTP) ---------------------------------------------------


def event_times(date_start: str, date_end: Optional[str]) -> tuple[dict, dict]:
    """CRM ``"YYYY-MM-DD HH:MM:SS"`` UTC stamps -> Calendar start/end objects.

    A missing/blank ``dateEnd`` defaults to start + 60 minutes (the CRM
    duration field's default)."""

    def parse(stamp: str) -> datetime:
        return datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S")

    try:
        start = parse(date_start)
    except (ValueError, AttributeError, TypeError) as exc:
        raise CalendarError(f"session has no usable start time: {date_start!r}") from exc
    try:
        end = parse(date_end) if date_end and str(date_end).strip() else None
    except (ValueError, TypeError):
        end = None
    if end is None or end <= start:
        end = start + timedelta(minutes=60)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return {"dateTime": start.strftime(fmt)}, {"dateTime": end.strftime(fmt)}


def build_event_body(
    *,
    summary: str,
    description: str,
    date_start: str,
    date_end: Optional[str],
    attendee_emails: list[str],
    request_id: Optional[str] = None,
    external_link: Optional[str] = None,
) -> dict[str, Any]:
    """Assemble a Calendar event resource.

    ``request_id`` set => ask Google to create a Meet conference on the event.
    ``external_link`` set (a hand-typed non-Meet meeting link) => no conference;
    the link goes into ``location`` and the description instead.
    """
    start, end = event_times(date_start, date_end)
    body: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "start": start,
        "end": end,
        "attendees": [{"email": e} for e in attendee_emails],
    }
    if request_id:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": request_id,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    elif external_link:
        body["location"] = external_link
        body["description"] = f"{description}\nJoin: {external_link}".strip()
    return body


def meet_link(event: dict[str, Any]) -> str:
    """The event's Meet URL: ``hangoutLink``, else the video entry point."""
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    for ep in (event.get("conferenceData") or {}).get("entryPoints") or []:
        if ep.get("entryPointType") == "video" and ep.get("uri"):
            return ep["uri"]
    return ""
