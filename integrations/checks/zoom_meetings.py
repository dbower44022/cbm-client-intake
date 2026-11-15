"""The Zoom Meetings integration test (Integrations tab phase 9; the check list
Doug approved 11-15-26, phase 9 stopping point 1; rulings EH1, EH6, EH8 and
EH11 of prds/events/event-hosting-plan.md).

The calls are the ones ``scripts/probe_zoom.py --meetings`` proved on the
Business Mentors Association's Zoom Pro account on 11-15-26. Every call is a
read. Checks, in order:

1. **Settings present** — account ID, client ID, client secret, event host user.
2. **Token by Server-to-Server OAuth** — 400/401 failed, network unknown.
   Fact: the scopes on the token.
3. **The meeting scopes** — the eleven in :data:`REQUIRED_SCOPES` on the token.
   Failed names each one missing; unknown when Zoom reports no scopes.
4. **The event host user** — ``GET /users/{host}``; must be Licensed
   (``type`` 2): a Basic user cannot take registrations.
5. **Co-host** — ``GET /users/{host}/settings`` → ``in_meeting.co_host``.
   Only the host shares (EH11), so a co-presenter shares by being made
   co-host. Fact: Zoom's meeting capacity beside the capacity limit setting.
6. **The host's meetings** — ``GET /users/{host}/meetings?type=upcoming``.
7. **Attendance report** — the latest past meeting's participant report. No
   past meeting is skipped: a new account must be able to pass.

A Zoom refusal for a missing scope (code 4711, "does not contain
scopes:[…]") is shown in Zoom's own words.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from integrations.testing import (
    FAILED,
    OK,
    SKIPPED,
    UNKNOWN,
    Blocked,
    Check,
    Context,
    run_checks,
)

from .zoom import LICENCES

#: The scopes Zoom Meetings needs: ``user:read:user:admin`` and the ten of
#: plan § 3, proved 11-15-26.
REQUIRED_SCOPES: tuple[str, ...] = (
    "user:read:user:admin",
    "user:read:settings:admin",
    "meeting:read:list_meetings:admin",
    "meeting:read:meeting:admin",
    "meeting:write:meeting:admin",
    "meeting:update:meeting:admin",
    "meeting:delete:meeting:admin",
    "meeting:write:registrant:admin",
    "meeting:read:list_registrants:admin",
    "meeting:update:registrant_status:admin",
    "report:read:list_meeting_participants:admin",
)


def _account(settings: Any) -> Any:
    from core.zoom import meetings_account

    return meetings_account(settings)


def _default_client(settings: Any) -> Any:
    from core.zoom import client_for

    return client_for(_account(settings), settings, timeout=10)


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client


def _transport(exc: Exception) -> bool:
    from core.zoom import ZoomTransportError

    return isinstance(exc, ZoomTransportError)


def _answer(exc: Exception, what: str) -> tuple[str, str]:
    """A Zoom error, as an outcome: unreachable or 5xx is unknown; any other
    answer is failed, a missing scope in Zoom's own words."""
    status = getattr(exc, "status_code", None)
    if _transport(exc) or status is None or status >= 500:
        return UNKNOWN, f"Could not read {what}: {exc}"
    text = str(exc)
    if "4711" in text or "does not contain scopes" in text:
        return FAILED, f"The app lacks a scope for {what}. Zoom says: {text}"
    return FAILED, f"Zoom refused {what}: {text}"


def _host(ctx: Context) -> str:
    return _account(ctx.settings).host


def _needs(ctx: Context, key: str, why: str) -> None:
    if not ctx.state.get(key):
        raise Blocked(f"Not checked: {why}.")


async def _settings(ctx: Context) -> tuple[str, str]:
    a = _account(ctx.settings)
    missing = [label for label, value in (
        ("account ID", a.account_id), ("client ID", a.client_id),
        ("client secret", a.client_secret), ("event host user", a.host),
    ) if not value]
    if missing:
        return FAILED, "Not set: " + ", ".join(missing) + "."
    ctx.state["settings_ok"] = True
    return OK, "The account ID, client ID, client secret and event host user are set."


async def _token(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "settings_ok", "a setting is missing (check 1)")
    client = ctx.deps.client(ctx.settings)
    ctx.state["client"] = client
    try:
        await client._access_token()
    except Exception as exc:  # noqa: BLE001
        if _transport(exc):
            return UNKNOWN, f"Could not reach Zoom: {exc}"
        status = getattr(exc, "status_code", None)
        if status is not None and status >= 500:
            return UNKNOWN, f"Zoom could not issue a token just now: {exc}"
        return FAILED, f"{exc}"
    scopes = sorted((getattr(client, "scopes", "") or "").split())
    ctx.state["scopes"] = scopes
    ctx.fact("Scopes on the token", ", ".join(scopes) if scopes else "not reported")
    ctx.state["token_ok"] = True
    return OK, "Zoom issued a token for the Server-to-Server OAuth app."


async def _scopes(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "token_ok", "no Zoom token (check 2)")
    granted = set(ctx.state.get("scopes") or ())
    if not granted:
        return UNKNOWN, "Zoom did not report the token's scopes, so they cannot be compared."
    missing = [s for s in REQUIRED_SCOPES if s not in granted]
    if missing:
        return FAILED, ("Missing from the app: " + ", ".join(missing)
                        + ". Add them on the app's Scopes page, through Add Scopes.")
    return OK, f"All {len(REQUIRED_SCOPES)} meeting scopes are on the app."


async def _host_user(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "token_ok", "no Zoom token (check 2)")
    host = _host(ctx)
    try:
        user = await ctx.state["client"].get_user(host)
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "status_code", None) == 404:
            return FAILED, f"Zoom has no user {host} on this account. Check the event host user's address."
        return _answer(exc, f"the event host user {host}")
    licence = LICENCES.get(user.get("type"), f"type {user.get('type')}")
    ctx.fact("Event host user", f"{user.get('email') or host} ({licence})")
    if user.get("account_number"):
        ctx.fact("Account number", user.get("account_number"))
    ctx.state["host_ok"] = True
    if user.get("type") != 2:
        return FAILED, (f"{user.get('email') or host} is a {licence} user. A Basic user cannot "
                        "take registrations: put the user on a paid plan.")
    return OK, f"Found {user.get('email') or host}, a Licensed user."


async def _co_host(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "host_ok", "the event host user could not be read (check 4)")
    host = _host(ctx)
    try:
        settings = await ctx.state["client"].get_user_settings(host) or {}
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, f"the settings of {host}")
    capacity = (settings.get("feature") or {}).get("meeting_capacity")
    limit = getattr(ctx.settings, "zoom_meetings_capacity", None)
    ctx.fact("Meeting capacity", f"Zoom {capacity if capacity else 'not reported'} · "
                                 f"limit setting {limit}")
    in_meeting = settings.get("in_meeting") or {}
    if "co_host" not in in_meeting:
        return UNKNOWN, f"Zoom did not report whether co-host is on for {host}."
    if in_meeting.get("co_host"):
        return OK, "Co-host is on, so a co-presenter can be made co-host to share their screen."
    return FAILED, ("Co-host is off. Turn it on in Zoom (Settings, Meeting, In Meeting (Basic)), "
                    "or a co-presenter cannot share their screen: only the host shares.")


async def _meetings(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "host_ok", "the event host user could not be read (check 4)")
    host = _host(ctx)
    try:
        data = await ctx.state["client"].list_meetings(host, kind="upcoming", page_size=30)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, f"the meetings of {host}")
    total = (data or {}).get("total_records")
    if total is None:
        total = len((data or {}).get("meetings") or [])
    ctx.fact("Upcoming meetings", total)
    return OK, f"Listed the meetings of {host}: {total} upcoming."


async def _attendance(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "host_ok", "the event host user could not be read (check 4)")
    host = _host(ctx)
    client = ctx.state["client"]
    try:
        past = await client.list_meetings(host, kind="previous_meetings", page_size=5)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, f"the past meetings of {host}")
    meetings = (past or {}).get("meetings") or []
    if not meetings:
        return SKIPPED, ("No past meeting to check yet: the attendance report can be "
                         "read after the first meeting has run.")
    target = meetings[0]
    try:
        participants = await client.list_meeting_participants(str(target.get("uuid") or target.get("id")))
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the meeting participant report")
    return OK, (f"Read the participant report of “{target.get('topic') or target.get('id')}”: "
                f"{len(participants)} participant(s).")


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("token", "Token by Server-to-Server OAuth", _token),
    Check("scopes", "The meeting scopes", _scopes),
    Check("host", "The event host user", _host_user),
    Check("co_host", "Co-host", _co_host),
    Check("meetings", "The host's meetings", _meetings),
    Check("attendance", "Attendance report", _attendance),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("zoom_meetings", CHECKS, ctx)
