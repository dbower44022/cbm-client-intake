"""The Zoom Webinars integration test (prds/integrations-tab-plan.md § 3; the check list
Doug approved 11-13-26, phase 2 stopping point 1).

**Which credentials** (phase 9, ruling EH7, Doug's option A 11-15-26):
``core/zoom.webinars_account`` — Zoom Meetings' app and event host user when
Zoom Webinars is on the same account and Zoom Meetings' three credentials are
set, otherwise Zoom Webinars' own four settings. The first check says which.

Zoom has one feature, so its checks run whether ``zoom_events`` is on or not:
Zoom can be tested before it is switched on. Checks, in order:

1. **Settings present** — account ID, client ID, client secret, host.
2. **Token by Server-to-Server OAuth** — 400/401 failed, network unknown.
   Fact: the scopes on the token (the token response's ``scope``).
3. **The host user** — ``GET /users/{host}``; 404 failed (the address is
   wrong). Facts: the host, its licence type, the account number.
4. **Webinar licence** — ``GET /users/{host}/settings`` → ``feature.webinar``
   and ``feature.webinar_capacity``. No licence is failed while
   ``zoom_events`` is on, and only reported while it is off.
5. **The host's webinars** — ``GET /users/{host}/webinars``. Fact: how many
   are scheduled.
6. **Attendance report** — the participant report of the most recent past
   webinar, which needs its own scope. No past webinar is skipped (phase 9):
   there is nothing to read yet, and a new account must be able to pass.

Calls 3, 5 and 6 are the ones ``scripts/probe_zoom.py`` made against the real
account. Every call is a read.
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

LICENCES = {1: "Basic", 2: "Licensed", 3: "On-premises", 4: "Unassigned", 99: "None"}


def _account(settings: Any) -> Any:
    from core.zoom import webinars_account

    return webinars_account(settings)


def _default_client(settings: Any) -> Any:
    from core.zoom import client_for

    return client_for(_account(settings), settings, timeout=10)


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client


def _transport(exc: Exception) -> bool:
    from core.zoom import ZoomTransportError

    return isinstance(exc, ZoomTransportError)


def _status(exc: Exception) -> Optional[int]:
    return getattr(exc, "status_code", None)


def _answer(exc: Exception, what: str) -> tuple[str, str]:
    """A Zoom error, as an outcome: unreachable or 5xx is unknown, any other
    answer is failed."""
    status = _status(exc)
    if _transport(exc) or status is None or status >= 500:
        return UNKNOWN, f"Could not read {what}: {exc}"
    return FAILED, f"Zoom refused {what}: {exc}"


def _host(ctx: Context) -> str:
    return _account(ctx.settings).host


def _needs(ctx: Context, key: str, why: str) -> None:
    if not ctx.state.get(key):
        raise Blocked(f"Not checked: {why}.")


async def _settings(ctx: Context) -> tuple[str, str]:
    a = _account(ctx.settings)
    whose = "Zoom Meetings'" if a.shared else "Zoom Webinars'"
    ctx.fact("Credentials used", "Zoom Meetings' app and event host user (same account)"
             if a.shared else "Zoom Webinars' own (separate account)")
    missing = [label for label, value in (
        ("account ID", a.account_id), ("client ID", a.client_id),
        ("client secret", a.client_secret),
        ("event host user" if a.shared else "host", a.host),
    ) if not value]
    if a.account_id and a.client_id and a.client_secret:
        # The token needs only the three credentials: the setup asks for the
        # host after the secret (phase 11 live review, 11-16-26).
        ctx.state["creds_ok"] = True
    if missing:
        return FAILED, f"Not set ({whose} settings): " + ", ".join(missing) + "."
    ctx.state["settings_ok"] = True
    return OK, f"{whose} account ID, client ID, client secret and host are set."


async def _token(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "creds_ok", "a credential is missing (check 1)")
    client = ctx.deps.client(ctx.settings)
    ctx.state["client"] = client
    try:
        await client._access_token()
    except Exception as exc:  # noqa: BLE001
        if _transport(exc):
            return UNKNOWN, f"Could not reach Zoom: {exc}"
        status = _status(exc)
        if status is not None and status >= 500:
            return UNKNOWN, f"Zoom could not issue a token just now: {exc}"
        return FAILED, f"{exc}"
    scopes = sorted((getattr(client, "scopes", "") or "").split())
    ctx.fact("Scopes on the token", ", ".join(scopes) if scopes else "not reported")
    ctx.state["token_ok"] = True
    return OK, "Zoom issued a token for the Server-to-Server OAuth app."


async def _host_user(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "token_ok", "no Zoom token (check 2)")
    host = _host(ctx)
    if not host:
        raise Blocked("Not checked: the host is not set (check 1).")
    try:
        user = await ctx.state["client"].get_user(host)
    except Exception as exc:  # noqa: BLE001
        if _status(exc) == 404:
            return FAILED, f"Zoom has no user {host} on this account. Check the host's address."
        return _answer(exc, f"the host user {host}")
    licence = LICENCES.get(user.get("type"), f"type {user.get('type')}")
    ctx.fact("Host", f"{user.get('email') or host} ({licence})")
    if user.get("account_number"):
        ctx.fact("Account number", user.get("account_number"))
    ctx.state["host_ok"] = True
    ctx.state["host_user"] = user
    return OK, f"Found {user.get('email') or host}, a {licence} user."


async def _webinar_licence(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "host_ok", "the host user could not be read (check 3)")
    host = _host(ctx)
    feature: dict[str, Any] = {}
    try:
        settings = await ctx.state["client"].get_user_settings(host)
        feature = (settings or {}).get("feature") or {}
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, f"the settings of {host}")
    if "webinar" not in feature:
        # Older answers carried it on the user itself.
        feature = ctx.state.get("host_user", {}).get("feature") or feature
    if "webinar" not in feature:
        return UNKNOWN, f"Zoom did not report whether {host} has a webinar licence."
    capacity = feature.get("webinar_capacity")
    if feature.get("webinar"):
        ctx.fact("Webinar capacity", capacity if capacity else "not reported")
        return OK, f"{host} has a webinar licence" + (f" for {capacity}." if capacity else ".")
    ctx.fact("Webinar capacity", "no webinar licence")
    if getattr(ctx.settings, "zoom_events", False):
        return FAILED, (f"{host} has no webinar licence, and webinar provisioning is on: "
                        "no webinar can be created. Buy the Webinars add-on for this user.")
    return OK, (f"{host} has no webinar licence. That is fine while webinar "
                "provisioning is off; it must be bought before switching it on.")


async def _webinars(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "host_ok", "the host user could not be read (check 3)")
    host = _host(ctx)
    try:
        data = await ctx.state["client"].list_webinars(host, kind="scheduled", page_size=1)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, f"the webinars of {host}")
    total = (data or {}).get("total_records")
    if total is None:
        total = len((data or {}).get("webinars") or [])
    ctx.fact("Scheduled webinars", total)
    return OK, f"Listed the webinars of {host}: {total} scheduled."


async def _attendance(ctx: Context) -> tuple[str, str]:
    _needs(ctx, "host_ok", "the host user could not be read (check 3)")
    host = _host(ctx)
    client = ctx.state["client"]
    try:
        past = await client.list_webinars(host, kind="past", page_size=5)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, f"the past webinars of {host}")
    webinars = (past or {}).get("webinars") or []
    if not webinars:
        return SKIPPED, ("No past webinar to check yet: the attendance report can "
                         "be read after the first webinar has run.")
    target = webinars[0]
    try:
        participants = await client.list_participants(str(target.get("id")))
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the participant report")
    return OK, (f"Read the participant report of “{target.get('topic') or target.get('id')}”: "
                f"{len(participants)} participant(s).")


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("token", "Token by Server-to-Server OAuth", _token),
    Check("host", "The host user", _host_user),
    Check("webinar_licence", "Webinar licence", _webinar_licence),
    Check("webinars", "The host's webinars", _webinars),
    Check("attendance", "Attendance report", _attendance),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("zoom", CHECKS, ctx)
