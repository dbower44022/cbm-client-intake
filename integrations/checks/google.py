"""The Google Workspace integration test (prds/integrations-tab-plan.md § 3;
the check list Doug approved 11-13-26, phase 2 stopping point 1).

Checks, in order:

1. **Service account key** — the key parses, and a token is minted as the
   service account itself (no delegation). ``invalid_grant`` (a deleted or
   disabled key) is failed; a network failure is unknown.
2. **Delegation, one line per scope a switched-on feature needs** — a
   delegated token is minted for that scope. ``unauthorized_client`` means the
   domain-wide delegation grant lacks the scope: failed, naming it. Minting a
   token sends nothing.
3. **Each switched-on feature's own read**: the shared drive, the shared
   mailbox's Gmail profile, the delegated admin's calendar, the delegated
   admin's directory record (and the All Members group when provisioning is
   on). Meet has no read without a meeting code, so its delegation token is
   the whole check, and its line says so.

A feature that is switched off gets one line: "Not checked — switched off".
The key is found as the features find it: the stored Email Setup first, then
the setting. Every call is a read.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

import httpx

from integrations.testing import (
    FAILED,
    OK,
    UNKNOWN,
    Blocked,
    Check,
    Context,
    Skip,
    run_checks,
)

S_GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"
S_GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
S_CALENDAR = "https://www.googleapis.com/auth/calendar.events"
S_MEET = "https://www.googleapis.com/auth/meetings.space.created"
S_DRIVE = "https://www.googleapis.com/auth/drive"
S_DIR_READ = "https://www.googleapis.com/auth/admin.directory.user.readonly"
S_DIR_USER = "https://www.googleapis.com/auth/admin.directory.user"
S_DIR_GROUP = "https://www.googleapis.com/auth/admin.directory.group"

# The token used for the key check: any scope will do, since no subject is
# impersonated; Drive's is one every deployment's key may hold.
_KEY_SCOPE = S_DRIVE


class TokenError(Exception):
    """A token could not be minted. ``kind``: ``unauthorized`` (the scope is
    not granted to this client), ``invalid`` (a bad key or subject), or
    ``transport`` (Google was not reached)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _classify(exc: Exception) -> TokenError:
    text = str(exc)
    name = type(exc).__name__
    if name == "TransportError" or isinstance(exc, (OSError, httpx.TransportError)):
        return TokenError("transport", f"Google could not be reached ({name}).")
    if "unauthorized_client" in text:
        return TokenError("unauthorized", "unauthorized_client")
    if "invalid_grant" in text:
        return TokenError("invalid", _short(text))
    return TokenError("invalid", _short(text) or name)


def _short(text: str) -> str:
    # google-auth puts the response dict after the message; keep the message.
    return text.split("{", 1)[0].strip().rstrip(",(").strip()


def _default_mint(info: dict, scopes: list[str], subject: Optional[str]) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=scopes, subject=subject
    )
    creds.refresh(Request())
    return creds.token


async def _default_get(url: str, token: str, params: Optional[dict] = None) -> tuple[int, Any]:
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


async def _default_stored_config(settings: Any) -> Optional[dict[str, Any]]:
    from core.app_config import make_app_config_store

    store = make_app_config_store(settings)
    if store is None:
        return None
    try:
        return await store.get_google_config()
    finally:
        await store.dispose()


@dataclass
class Deps:
    # Synchronous (google-auth is); run in a thread. Returns the token.
    mint: Callable[[dict, list[str], Optional[str]], str] = _default_mint
    get: Callable[[str, str, Optional[dict]], Awaitable[tuple[int, Any]]] = _default_get
    stored_config: Callable[[Any], Awaitable[Optional[dict[str, Any]]]] = _default_stored_config


# --- what is switched on, and what it needs ---------------------------------

@dataclass(frozen=True)
class Need:
    """One delegated scope a switched-on feature needs, as one subject."""

    scope: str
    # The account impersonated; None = the service account itself (no
    # delegation); "" = the delegated admin is needed but not set.
    subject: Optional[str]
    features: tuple[str, ...]


@dataclass
class Plan:
    info: Optional[dict[str, Any]] = None
    key_problem: str = ""
    admin: str = ""
    needs: list[Need] = field(default_factory=list)


def _on(settings: Any, key: str) -> bool:
    return bool(getattr(settings, key, False))


def scope_needs(settings: Any, admin: str) -> list[Need]:
    """The (scope, subject) pairs the switched-on features need, merged."""
    s = settings
    mailbox = (getattr(s, "ops_mailbox", "") or "").strip()
    sender = mailbox or admin
    wanted: list[tuple[str, Optional[str], str]] = []  # (scope, subject, feature)
    if _on(s, "gmail_sync") or _on(s, "gmail_resync"):
        wanted.append((S_GMAIL_READ, admin, "Gmail sync"))
    if mailbox:
        wanted.append((S_GMAIL_READ, mailbox, "the shared mailbox"))
        wanted.append((S_GMAIL_SEND, mailbox, "the shared mailbox"))
    for key, label in (("events_confirmations", "event confirmations"),
                       ("events_reminders", "event reminders"),
                       ("lead_outreach", "lead outreach")):
        if _on(s, key):
            wanted.append((S_GMAIL_SEND, sender, label))
    if _on(s, "gcal_events"):
        wanted.append((S_CALENDAR, admin, "Calendar"))
    if _on(s, "meet_transcripts"):
        wanted.append((S_MEET, admin, "Meet transcripts"))
    if _on(s, "gdrive_docs"):
        service = getattr(s, "gdrive_identity", "user") == "service"
        wanted.append((S_DRIVE, None if service else admin, "Drive"))
    if _on(s, "google_directory_check"):
        wanted.append((S_DIR_READ, admin, "the directory check"))
    if _on(s, "google_create_mailbox") or _on(s, "mentor_provision_users"):
        label = "mailbox creation and mentor provisioning"
        wanted.append((S_DIR_USER, admin, label))
        wanted.append((S_DIR_GROUP, admin, label))
    merged: dict[tuple[str, Optional[str]], list[str]] = {}
    for scope, subject, label in wanted:
        labels = merged.setdefault((scope, subject), [])
        if label not in labels:
            labels.append(label)
    return [Need(scope, subject, tuple(labels)) for (scope, subject), labels in merged.items()]


def _scope_name(scope: str) -> str:
    return scope.rsplit("/", 1)[-1]


async def _mint(ctx: Context, scopes: list[str], subject: Optional[str]) -> str:
    try:
        return await asyncio.to_thread(ctx.deps.mint, ctx.state["plan"].info, scopes, subject)
    except TokenError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _classify(exc) from exc


# --- the checks ---------------------------------------------------------------

async def _key(ctx: Context) -> tuple[str, str]:
    plan: Plan = ctx.state["plan"]
    if plan.key_problem:
        return FAILED, plan.key_problem
    info = plan.info or {}
    ctx.fact("Service account", info.get("client_email") or "not in the key")
    ctx.fact("Client ID (for the delegation grant)", info.get("client_id") or "not in the key")
    ctx.fact("Delegated admin", plan.admin or "not set")
    try:
        await _mint(ctx, [_KEY_SCOPE], None)
    except TokenError as exc:
        if exc.kind == "transport":
            return UNKNOWN, str(exc)
        return FAILED, f"Google refused the key: {exc}. It may have been deleted or disabled."
    ctx.state["key_ok"] = True
    detail = f"A working key for {info.get('client_email')}."
    if not plan.admin:
        detail += " No delegated admin is set, so no delegated check can run."
    return OK, detail


def _needs_key(ctx: Context) -> None:
    if not ctx.state.get("key_ok"):
        raise Blocked("Not checked: the service account key did not work (check 1).")


def _delegation_check(need: Need) -> Check:
    async def run(ctx: Context) -> tuple[str, str]:
        _needs_key(ctx)
        name = _scope_name(need.scope)
        who = "the service account itself" if need.subject is None else need.subject
        used = ", ".join(need.features)
        if need.subject == "":
            return FAILED, f"No delegated admin is set, so {name} cannot be checked ({used})."
        try:
            token = await _mint(ctx, [need.scope], need.subject)
        except TokenError as exc:
            missing = ctx.state.setdefault("missing", [])
            if exc.kind == "transport":
                return UNKNOWN, str(exc)
            if exc.kind == "unauthorized":
                if name not in missing:
                    missing.append(name)
                return FAILED, (f"Domain-wide delegation does not grant {name} "
                                f"(needed by {used}). Add it to the grant for this client ID.")
            return FAILED, f"No token as {who}: {exc}. Check that {who} is a real, licensed account."
        ctx.state.setdefault("tokens", {})[(need.scope, need.subject)] = token
        granted = ctx.state.setdefault("granted", [])
        if name not in granted:
            granted.append(name)
        return OK, f"Granted, as {who} (needed by {used})."

    who = "the service account" if need.subject is None else (need.subject or "(no admin set)")
    return Check(f"scope:{_scope_name(need.scope)}:{need.subject or ''}",
                 f"Delegation: {_scope_name(need.scope)} as {who}", run)


def _token_for(ctx: Context, scope: str, subject: Optional[str]) -> str:
    token = (ctx.state.get("tokens") or {}).get((scope, subject))
    if not token:
        raise Blocked(f"Not checked: no {_scope_name(scope)} token (its delegation line above).")
    return token


def _http_outcome(status: int, body: Any, what: str) -> tuple[str, str]:
    message = ""
    if isinstance(body, dict):
        message = str(((body.get("error") or {}) if isinstance(body.get("error"), dict)
                       else {}).get("message") or body.get("error") or "")
    if status >= 500:
        return UNKNOWN, f"Google answered HTTP {status} for {what}: {message}".rstrip(": ")
    return FAILED, f"Google answered HTTP {status} for {what}: {message}".rstrip(": ")


async def _get(ctx: Context, url: str, token: str, params: Optional[dict] = None):
    try:
        return await ctx.deps.get(url, token, params)
    except httpx.TransportError as exc:
        raise Blocked(f"Google could not be reached ({type(exc).__name__}).") from exc


async def _drive(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    if not _on(s, "gdrive_docs"):
        raise Skip()
    _needs_key(ctx)
    drive_id = (getattr(s, "gdrive_shared_drive_id", "") or "").strip()
    if not drive_id:
        return FAILED, "Drive is on, but the shared drive ID is not set."
    service = getattr(s, "gdrive_identity", "user") == "service"
    admin = ctx.state["plan"].admin
    token = _token_for(ctx, S_DRIVE, None if service else admin)
    params = {"fields": "id,name"}
    if not service:
        # The delegated admin need not be a member; an administrator may read
        # any shared drive in the domain this way.
        params["useDomainAdminAccess"] = "true"
    status, body = await _get(ctx, f"https://www.googleapis.com/drive/v3/drives/{drive_id}",
                              token, params)
    if status == 200:
        name = (body or {}).get("name") or drive_id
        ctx.fact("Shared drive", name)
        return OK, f"The shared drive “{name}” is there."
    if status == 404:
        return FAILED, ("No shared drive with that ID is visible "
                        + ("to the service account: check the ID, and that the service "
                           "account is a member." if service else
                           "to the delegated admin: check the ID."))
    return _http_outcome(status, body, "the shared drive")


async def _mailbox(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    mailbox = (getattr(s, "ops_mailbox", "") or "").strip()
    if not mailbox:
        raise Skip("Not checked — no shared mailbox is set.")
    _needs_key(ctx)
    token = _token_for(ctx, S_GMAIL_READ, mailbox)
    status, body = await _get(ctx, "https://gmail.googleapis.com/gmail/v1/users/me/profile", token)
    if status == 200:
        address = (body or {}).get("emailAddress") or mailbox
        total = (body or {}).get("messagesTotal")
        ctx.fact("Shared mailbox", address + (f" ({total} messages)" if total is not None else ""))
        return OK, f"Read the profile of {address}."
    return _http_outcome(status, body, f"the profile of {mailbox}")


async def _calendar(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    if not _on(s, "gcal_events"):
        raise Skip()
    _needs_key(ctx)
    admin = ctx.state["plan"].admin
    token = _token_for(ctx, S_CALENDAR, admin)
    now = datetime.now(timezone.utc)
    params = {"timeMin": now.isoformat(), "timeMax": (now + timedelta(days=1)).isoformat(),
              "maxResults": "1", "singleEvents": "true"}
    status, body = await _get(ctx, "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                              token, params)
    if status == 200:
        return OK, f"Read the next day of {admin}'s calendar."
    return _http_outcome(status, body, f"{admin}'s calendar")


async def _meet(ctx: Context) -> tuple[str, str]:
    if not _on(ctx.settings, "meet_transcripts"):
        raise Skip()
    _needs_key(ctx)
    _token_for(ctx, S_MEET, ctx.state["plan"].admin)
    return OK, ("The delegation token is the whole check: Meet has no read "
                "without a meeting code.")


async def _directory(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    provisioning = _on(s, "google_create_mailbox") or _on(s, "mentor_provision_users")
    if not (_on(s, "google_directory_check") or provisioning):
        raise Skip()
    _needs_key(ctx)
    admin = ctx.state["plan"].admin
    scope = S_DIR_READ if _on(s, "google_directory_check") else S_DIR_USER
    token = _token_for(ctx, scope, admin)
    status, body = await _get(
        ctx, f"https://admin.googleapis.com/admin/directory/v1/users/{admin}", token,
        {"fields": "primaryEmail,isAdmin,isDelegatedAdmin"})
    if status != 200:
        return _http_outcome(status, body, f"the directory record of {admin}")
    record = body or {}
    if record.get("isAdmin"):
        detail = f"{admin} is a Workspace super administrator."
    elif record.get("isDelegatedAdmin"):
        detail = f"{admin} is a Workspace delegated administrator."
    else:
        return FAILED, f"{admin} is not a Workspace administrator."
    if provisioning:
        group = (getattr(s, "google_members_group", "") or "").strip()
        if not group:
            return FAILED, detail + " The All Members group is not set."
        gtoken = _token_for(ctx, S_DIR_GROUP, admin)
        gstatus, gbody = await _get(
            ctx, f"https://admin.googleapis.com/admin/directory/v1/groups/{group}", gtoken,
            {"fields": "email,name"})
        if gstatus == 404:
            return FAILED, detail + f" There is no group {group}."
        if gstatus != 200:
            return _http_outcome(gstatus, gbody, f"the group {group}")
        detail += f" The All Members group {group} exists."
    return OK, detail


async def _plan(settings: Any, deps: Deps, ctx: Context) -> Plan:
    plan = Plan()
    stored = None
    try:
        stored = await deps.stored_config(settings)
    except Exception:  # noqa: BLE001 — fall back to the settings, as the features do
        stored = None
    raw = (stored or {}).get("service_account_json") or getattr(
        settings, "google_service_account_json", "")
    plan.admin = ((stored or {}).get("delegated_admin")
                  or getattr(settings, "google_delegated_admin", "") or "").strip()
    if raw:
        ctx.secrets.append(str(raw))
    if not raw:
        plan.key_problem = "No service account key is set."
        return plan
    try:
        info = json.loads(raw)
    except (TypeError, ValueError):
        plan.key_problem = "The service account key is not valid JSON."
        return plan
    if not isinstance(info, dict) or info.get("type") != "service_account":
        plan.key_problem = "The key is not a service-account key."
        return plan
    missing = [f for f in ("client_email", "private_key", "token_uri") if not info.get(f)]
    if missing:
        plan.key_problem = f"The key is missing {', '.join(missing)}."
        return plan
    for secret_field in ("private_key", "private_key_id"):
        if info.get(secret_field):
            ctx.secrets.append(str(info[secret_field]))
    plan.info = info
    plan.needs = scope_needs(settings, plan.admin)
    return plan


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    deps = deps or Deps()
    ctx = Context(settings=settings, deps=deps)
    plan = await _plan(settings, deps, ctx)
    ctx.state["plan"] = plan
    checks = [Check("key", "Service account key", _key)]
    checks += [_delegation_check(n) for n in plan.needs]
    checks += [
        Check("drive", "Drive: the shared drive", _drive),
        Check("mailbox", "Gmail: the shared mailbox", _mailbox),
        Check("calendar", "Calendar", _calendar),
        Check("meet", "Meet", _meet),
        Check("directory", "Workspace accounts: the directory", _directory),
    ]

    result = await run_checks("google_workspace", checks, ctx)
    granted = ctx.state.get("granted") or []
    missing = ctx.state.get("missing") or []
    if plan.needs:
        result["facts"].append({"label": "Scopes granted", "value": ", ".join(granted) or "none"})
        result["facts"].append({"label": "Scopes missing", "value": ", ".join(missing) or "none"})
    return result
