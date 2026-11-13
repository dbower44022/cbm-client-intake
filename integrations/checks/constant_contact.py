"""The Constant Contact integration test (prds/integrations-tab-plan.md § 3;
the check list Doug approved 11-13-26, phase 3 stopping point 1).

Checks, in order:

1. **Settings present** — the client ID and client secret.
2. **The connection** — the stored connection row, read from this
   application's database: none is failed ("click Connect"); one marked for
   re-authorisation is failed with its stored error; a missing scope is
   failed. Facts: who connected it and when, the scopes, the token's expiry,
   the last refresh. Never a token.
3. **Read the account** — ``GET /account/summary`` through the existing
   client. **The token is refreshed only when due** (Doug's ruling 11-13-26,
   option A): the client's own path refreshes inside the last 5 minutes or
   after a 401, and stores the new pair under the row lock. The test adds no
   refresh of its own. Fact: the organisation name.
4. **The named list** — the list named by ``mailing_list_name``. Absent is ok
   with a note: the first push creates it. Fact: its ``membership_count``
   (``include_membership_count=all``, the vendor's guide, read 11-13-26).
5. **The lead-code field** — the ``cbm_lead_code`` custom field; skipped while
   ``campaign_list_sync`` is off. Absent is ok with a note: the next push
   creates it.

Every call is a read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from integrations.testing import (
    FAILED, OK, UNKNOWN, Blocked, Check, Context, Skip, run_checks,
)


def _default_store(settings: Any) -> Any:
    from core.mailing import shared_connection_store

    return shared_connection_store(settings)


def _default_client(store: Any, settings: Any) -> Any:
    from core.mailing import DEFAULT_BASE_URL, make_client

    return make_client(store, settings.mailing_client_id, settings.mailing_client_secret,
                       base_url=getattr(settings, "mailing_base_url", "") or DEFAULT_BASE_URL)


@dataclass
class Deps:
    store: Callable[[Any], Any] = _default_store
    client: Callable[[Any, Any], Any] = _default_client


def _when(value: Any) -> str:
    if not value:
        return "never"
    try:
        return value.strftime("%m-%d-%y %H:%M UTC")
    except AttributeError:
        return str(value)


def _answer(exc: Exception, what: str) -> tuple[str, str]:
    from core.mailing import MailingAuthError, MailingNotConnected, MailingRateLimited

    if isinstance(exc, (MailingAuthError, MailingNotConnected)):
        return FAILED, f"{exc} An administrator must click Connect again."
    if isinstance(exc, MailingRateLimited):
        return UNKNOWN, f"Could not read {what}: {exc}"
    status = getattr(exc, "status_code", None)
    if status is None or status >= 500 or status == 429:
        return UNKNOWN, f"Could not read {what}: {exc}"
    return FAILED, f"Constant Contact refused to show {what}: {exc}"


async def _settings(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    missing = [label for label, value in (
        ("client ID", s.mailing_client_id), ("client secret", s.mailing_client_secret),
    ) if not (value or "").strip()]
    if missing:
        return FAILED, "Not set: " + ", ".join(missing) + "."
    ctx.state["settings_ok"] = True
    return OK, "The client ID and client secret are set."


async def _connection(ctx: Context) -> tuple[str, str]:
    from core.mailing import SCOPES

    if not ctx.state.get("settings_ok"):
        raise Blocked("Not checked: a setting is missing (check 1).")
    store = ctx.deps.store(ctx.settings)
    if store is None:
        return FAILED, "No database is attached, so there is nowhere to hold the connection."
    try:
        conn = await store.get()
    except Exception as exc:  # noqa: BLE001
        return UNKNOWN, f"The connection could not be read from the database: {type(exc).__name__}."
    if conn is None:
        return FAILED, "Constant Contact is not connected. Click Connect on this sub-tab."
    ctx.fact("Connected by", f"{conn.connected_by or 'not recorded'}, {_when(conn.connected_at)}")
    ctx.fact("Scopes", ", ".join(conn.scopes) if conn.scopes else "not recorded")
    ctx.fact("Access token expires", _when(conn.expires_at))
    ctx.fact("Last refreshed", _when(conn.last_refresh_at))
    if not conn.usable:
        return FAILED, ("The connection needs re-authorisation: "
                        + (conn.last_error or "Constant Contact refused the refresh token.")
                        + " Click Connect again.")
    missing = [s for s in SCOPES if conn.scopes and s not in conn.scopes]
    if missing:
        return FAILED, ("The connection lacks the scope(s) " + ", ".join(missing)
                        + ". Disconnect, then Connect again to grant them.")
    ctx.state["store"] = store
    return OK, "Connected" + (f" as {conn.account_label}." if conn.account_label else ".")


async def _account(ctx: Context) -> tuple[str, str]:
    if "store" not in ctx.state:
        raise Blocked("Not checked: there is no usable connection (check 2).")
    client = ctx.deps.client(ctx.state["store"], ctx.settings)
    ctx.state["client"] = client
    try:
        summary = await client.account_summary()
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the account")
    if not isinstance(summary, dict) or not summary:
        return UNKNOWN, "Constant Contact answered without the account summary; its API may have changed."
    name = summary.get("organization_name") or summary.get("contact_email")
    ctx.fact("Account", name or "not reported")
    ctx.state["account_ok"] = True
    return OK, "Read the account" + (f": {name}." if name else ".")


async def _list(ctx: Context) -> tuple[str, str]:
    if not ctx.state.get("account_ok"):
        raise Blocked("Not checked: the account could not be read (check 3).")
    name = (ctx.settings.mailing_list_name or "").strip()
    if not name:
        return FAILED, "Not set: the list name."
    try:
        lists = await ctx.state["client"].lists(membership_count=True)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the contact lists")
    want = name.casefold()
    found = next((x for x in lists if str((x or {}).get("name") or "").strip().casefold() == want), None)
    if found is None:
        ctx.fact("List", f"{name}: not there yet")
        return OK, f"There is no list named “{name}” yet. The first push creates it."
    count = found.get("membership_count")
    ctx.fact("List", f"{found.get('name')} ({count if count is not None else 'count not reported'} members)")
    return OK, f"Found the list “{found.get('name')}”."


async def _field(ctx: Context) -> tuple[str, str]:
    from campaigns.list_sync import CODE_FIELD

    if not getattr(ctx.settings, "campaign_list_sync", False):
        raise Skip()
    if not ctx.state.get("account_ok"):
        raise Blocked("Not checked: the account could not be read (check 3).")
    try:
        field = await ctx.state["client"].find_custom_field(CODE_FIELD)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the custom fields")
    if field is None:
        ctx.fact("Lead-code field", "not there yet")
        return OK, f"The custom field {CODE_FIELD} is not there yet. The next push creates it."
    ctx.fact("Lead-code field", str(field.get("name") or CODE_FIELD))
    return OK, f"Found the custom field {field.get('name') or CODE_FIELD}."


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("connection", "The connection", _connection),
    Check("account", "Read the account", _account),
    Check("list", "The named list", _list),
    Check("field", "The lead-code field", _field),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("constant_contact", CHECKS, ctx)
