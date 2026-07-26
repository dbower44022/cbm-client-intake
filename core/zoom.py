"""Zoom Webinar API client — Server-to-Server OAuth.

Used by the Events & Webinars feature to provision the webinar behind a public
workshop, push registrants to it, and pull the attendance report afterwards.

**This is the CBM *account* Zoom integration and is deliberately separate from
the mentor-session rule.** Mentor 1:1 sessions use the mentor's own personal
meeting link and never touch a CBM Zoom account or its API (see
``cmentorprofile-meeting-fields.md``); that ruling is untouched. This module
exists only for the public webinar programme, per PRD D-03/D-04.

Verified integration contract (the ``comms/templates.py`` convention — keep this
accurate, it is what the next person will trust):

* **Auth** — ``POST https://zoom.us/oauth/token`` with
  ``grant_type=account_credentials&account_id=...`` and HTTP Basic
  ``client_id:client_secret``. Returns a bearer token, typically 1 h. Cached in
  process and refreshed shortly before expiry; a 401 forces one re-auth and
  retry, because a token can be revoked server-side at any time.
* **Create** — ``POST /users/{host}/webinars``. ``type: 5`` is a single-occurrence
  webinar. ``start_time`` is UTC ISO-8601 ending in ``Z``; ``duration`` is
  MINUTES (not seconds — the CRM stores seconds, so callers must convert).
  Returns ``id`` (the numeric webinar id), ``join_url``, ``registration_url``.
* **Registration** — ``settings.approval_type: 0`` means "register, approved
  automatically", which is what makes the registrants endpoint usable. With
  ``2`` (no registration) adding a registrant fails.
* **Emails (EV-24)** — Zoom's *confirmation* stays ON, because the join link is
  per-registrant and only Zoom can send it (D-13). Zoom's *reminder* and
  *follow-up* emails are turned OFF, because CBM sends branded ones; leaving
  both on sends registrants two of everything.
* **Update** — ``PATCH /webinars/{id}`` returns **204 No Content**, not a body.
* **Cancel** — ``DELETE /webinars/{id}``. ``cancel_webinar_reminder=true`` makes
  Zoom notify registrants that it is off.
* **Registrants** — ``POST /webinars/{id}/registrants`` returns the per-registrant
  ``join_url`` and ``registrant_id``. Careful: the ``id`` in that response is the
  WEBINAR id, not the registrant's. Cancelling is
  ``PUT /webinars/{id}/registrants/status`` with ``{"action": "cancel"}``.
* **Attendance** — ``GET /report/webinars/{id}/participants`` (paged by
  ``next_page_token``). Needs a paid plan and the report scope; the report is not
  available the instant a webinar ends, so callers retry within a window rather
  than treating an empty result as "nobody came".

429 and 5xx are retried with backoff honouring ``Retry-After``. Every failure
raises :class:`ZoomError`; callers treat Zoom as best-effort and never fail a
save because of it.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.zoom")

DEFAULT_BASE_URL = "https://api.zoom.us/v2"
TOKEN_URL = "https://zoom.us/oauth/token"

#: Single-occurrence webinar.
WEBINAR_TYPE_SINGLE = 5
#: ``approval_type`` 0 = registration required, automatically approved.
APPROVAL_AUTOMATIC = 0

#: Refresh this many seconds before the token actually expires.
_TOKEN_SKEW = 120

# Test seam: monkeypatched so backoff tests don't sleep for real.
_sleep = asyncio.sleep


class ZoomError(Exception):
    """Any Zoom API or transport failure."""


class ZoomAuthError(ZoomError):
    """Credentials were rejected — a configuration problem, not a blip."""


def to_zoom_time(value: datetime) -> str:
    """UTC ISO-8601 with the ``Z`` suffix Zoom expects."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_zoom_time(value: Optional[str]) -> Optional[datetime]:
    """Parse a Zoom timestamp (always UTC, ``Z``-suffixed)."""
    if not value:
        return None
    try:
        return datetime.strptime(
            str(value).strip(), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def webinar_settings(*, cbm_sends_reminders: bool = True) -> dict[str, Any]:
    """The settings block for a CBM webinar.

    Registration on and auto-approved (so the registrants API works), Zoom's
    confirmation email ON (it carries the unique join link), Zoom's reminders
    and follow-ups OFF when CBM is sending its own (EV-24).
    """
    off = {"enable": False}
    settings: dict[str, Any] = {
        "approval_type": APPROVAL_AUTOMATIC,
        "registrants_confirmation_email": True,
        "registrants_email_notification": True,
        "practice_session": False,
        "hd_video": True,
    }
    if cbm_sends_reminders:
        settings.update({
            "attendees_and_panelists_reminder_email_notification": off,
            "follow_up_attendees_email_notification": off,
            "follow_up_absentees_email_notification": off,
        })
    return settings


class ZoomClient:
    """Zoom API v2, authenticated by Server-to-Server OAuth."""

    def __init__(
        self,
        account_id: str,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 30,
    ) -> None:
        if not (account_id and client_id and client_secret):
            raise ZoomAuthError("Zoom account id, client id and secret are required.")
        self._account_id = account_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._token: Optional[str] = None
        self._token_expires: float = 0.0

    # --- auth --------------------------------------------------------------

    async def _access_token(self, *, force: bool = False) -> str:
        if not force and self._token and time.monotonic() < self._token_expires:
            return self._token
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                resp = await http.post(
                    TOKEN_URL,
                    params={
                        "grant_type": "account_credentials",
                        "account_id": self._account_id,
                    },
                    headers={"Authorization": f"Basic {basic}"},
                )
        except httpx.HTTPError as exc:
            raise ZoomError(f"Zoom token request failed: {type(exc).__name__}") from exc
        if resp.status_code in (400, 401):
            # Never echo the response body — it can contain the client id.
            raise ZoomAuthError(
                f"Zoom rejected the app credentials (HTTP {resp.status_code}). "
                "Check ZOOM_ACCOUNT_ID / ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET."
            )
        if resp.status_code >= 400:
            raise ZoomError(f"Zoom token request failed: HTTP {resp.status_code}")
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ZoomAuthError("Zoom returned no access token.")
        self._token = token
        self._token_expires = time.monotonic() + max(
            60, int(data.get("expires_in") or 3600) - _TOKEN_SKEW
        )
        return token

    # --- transport ---------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        expect_body: bool = True,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        reauthed = False
        resp: Optional[httpx.Response] = None
        for attempt in range(4):
            token = await self._access_token()
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    resp = await http.request(
                        method, url, params=params, json=json_body,
                        headers={"Authorization": f"Bearer {token}"},
                    )
            except httpx.HTTPError as exc:
                raise ZoomError(
                    f"Zoom {method} {path} failed: could not reach Zoom "
                    f"({type(exc).__name__})"
                ) from exc

            # A token can be revoked mid-life; re-auth once, then give up.
            if resp.status_code == 401 and not reauthed:
                reauthed = True
                await self._access_token(force=True)
                continue

            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                await _sleep(_retry_after(resp) or (2 ** attempt))
                continue
            break

        assert resp is not None  # the loop either breaks with a response or raises
        if resp.status_code >= 400:
            raise ZoomError(
                f"Zoom {method} {path} failed: HTTP {resp.status_code} "
                f"{resp.text[:300]}"
            )
        if not expect_body or resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}

    # --- webinars ----------------------------------------------------------

    async def create_webinar(
        self,
        host: str,
        *,
        topic: str,
        start: datetime,
        duration_minutes: int,
        agenda: str = "",
        timezone_name: str = "America/New_York",
        cbm_sends_reminders: bool = True,
    ) -> dict[str, Any]:
        """Create a single-occurrence webinar with registration enabled."""
        body = {
            "topic": topic[:200],  # Zoom caps the topic length
            "type": WEBINAR_TYPE_SINGLE,
            "start_time": to_zoom_time(start),
            "duration": max(1, int(duration_minutes)),
            "timezone": timezone_name,
            "agenda": (agenda or "")[:2000],
            "settings": webinar_settings(cbm_sends_reminders=cbm_sends_reminders),
        }
        return await self._request("POST", f"/users/{host}/webinars", json_body=body)

    async def update_webinar(
        self,
        webinar_id: str,
        *,
        topic: Optional[str] = None,
        start: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        agenda: Optional[str] = None,
    ) -> None:
        """Patch an existing webinar. Zoom answers 204 with no body."""
        body: dict[str, Any] = {}
        if topic is not None:
            body["topic"] = topic[:200]
        if start is not None:
            body["start_time"] = to_zoom_time(start)
        if duration_minutes is not None:
            body["duration"] = max(1, int(duration_minutes))
        if agenda is not None:
            body["agenda"] = agenda[:2000]
        if not body:
            return
        await self._request(
            "PATCH", f"/webinars/{webinar_id}", json_body=body, expect_body=False
        )

    async def delete_webinar(
        self, webinar_id: str, *, notify_registrants: bool = True
    ) -> None:
        """Cancel a webinar. Zoom emails registrants when notify is on."""
        await self._request(
            "DELETE",
            f"/webinars/{webinar_id}",
            params={"cancel_webinar_reminder": str(notify_registrants).lower()},
            expect_body=False,
        )

    async def get_webinar(self, webinar_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/webinars/{webinar_id}")

    # --- registrants -------------------------------------------------------

    async def add_registrant(
        self,
        webinar_id: str,
        *,
        email: str,
        first_name: str,
        last_name: str = "",
        phone: str = "",
        zip_code: str = "",
    ) -> dict[str, Any]:
        """Register someone. Zoom emails them the unique join link.

        Returns Zoom's response; note ``id`` there is the WEBINAR id — the
        registrant's own id is ``registrant_id``.
        """
        body: dict[str, Any] = {
            "email": email,
            "first_name": (first_name or email.split("@")[0])[:64],
        }
        if last_name:
            body["last_name"] = last_name[:64]
        if phone:
            body["phone"] = phone
        if zip_code:
            body["zip"] = zip_code
        return await self._request(
            "POST", f"/webinars/{webinar_id}/registrants", json_body=body
        )

    async def cancel_registrant(
        self, webinar_id: str, *, registrant_id: str, email: str = ""
    ) -> None:
        """Cancel one registration, freeing the seat."""
        entry: dict[str, Any] = {"id": registrant_id}
        if email:
            entry["email"] = email
        await self._request(
            "PUT",
            f"/webinars/{webinar_id}/registrants/status",
            json_body={"action": "cancel", "registrants": [entry]},
            expect_body=False,
        )

    # --- attendance --------------------------------------------------------

    async def list_participants(self, webinar_id: str) -> list[dict[str, Any]]:
        """The post-event participant report, following pagination.

        An empty list can legitimately mean "the report is not ready yet" —
        Zoom does not publish it the instant a webinar ends. Callers must treat
        empty as "retry later", never as "nobody attended" (EV-31).
        """
        participants: list[dict[str, Any]] = []
        token: Optional[str] = None
        while True:
            params: dict[str, Any] = {"page_size": 300}
            if token:
                params["next_page_token"] = token
            data = await self._request(
                "GET", f"/report/webinars/{webinar_id}/participants", params=params
            )
            participants.extend(data.get("participants", []))
            token = data.get("next_page_token") or None
            if not token:
                break
        return participants


def _retry_after(resp: httpx.Response) -> Optional[float]:
    try:
        value = float(resp.headers.get("Retry-After", ""))
        return min(value, 30.0) if value > 0 else None
    except ValueError:
        return None


def make_client(settings: Any) -> Optional[ZoomClient]:
    """Build a client from settings, or None when Zoom isn't configured.

    Returning None (rather than raising) lets every caller treat "Zoom is off"
    and "Zoom is broken" the same way: skip, record why, carry on.
    """
    if not getattr(settings, "zoom_events", False):
        return None
    try:
        return ZoomClient(
            settings.zoom_account_id,
            settings.zoom_client_id,
            settings.zoom_client_secret,
            base_url=getattr(settings, "zoom_base_url", DEFAULT_BASE_URL),
        )
    except ZoomAuthError as exc:
        log.warning("Zoom is enabled but not configured: %s", exc)
        return None
