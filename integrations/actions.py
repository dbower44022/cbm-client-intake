"""Coded actions: the setup assistant's only way to act on an outside service
(prds/integrations-tab-plan.md § 6.5, ruling I11; the list Doug approved
11-13-26, phase 7 stopping point 1).

The setup assistant chooses an action by name from this list and gives it one
input; it never writes its own call. The application runs it, and only when
an administrator confirms the step (ruling I12):

* ``dry_run`` first, when the step comes up — it reads, changes nothing and
  says what the real run would do;
* ``apply`` on confirmation — idempotent, so a second run changes nothing.

An action may **propose setting values** (for example the new shared drive's
ID). The application saves each one through the checked save path as the
confirming administrator; an action never writes a setting itself.

Three actions for now: create the Google shared drive; look up the Twilio
sender number; confirm the Zoom host. Applying CRM structure from a button
was left out by Doug's decision (it would bypass the crm-test-first runbook).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

DRIVE_API = "https://www.googleapis.com/drive/v3"
S_DRIVE = "https://www.googleapis.com/auth/drive"


@dataclass
class Result:
    ok: bool
    summary: str
    proposes: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "summary": self.summary, "proposes": dict(self.proposes)}


Run = Callable[[Any, str, Any], Awaitable[Result]]


@dataclass(frozen=True)
class CodedAction:
    name: str
    integration: str
    label: str
    description: str
    input_label: str
    dry_run: Run
    apply: Run


# --- Google: create the shared drive -----------------------------------------------------

async def _default_stored_google(settings: Any) -> Optional[dict[str, Any]]:
    from core.app_config import make_app_config_store

    store = make_app_config_store(settings)
    return await store.get_google_config() if store is not None else None


def _default_mint(info: dict, scopes: list[str], subject: Optional[str]) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes, subject=subject)
    creds.refresh(Request())
    return creds.token


async def _default_http(method: str, url: str, token: str, params: Optional[dict] = None,
                        body: Optional[dict] = None) -> tuple[int, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.request(method, url, params=params, json=body,
                                  headers={"Authorization": f"Bearer {token}"})
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


@dataclass
class GoogleDeps:
    stored: Callable[[Any], Awaitable[Optional[dict[str, Any]]]] = _default_stored_google
    mint: Callable[[dict, list[str], Optional[str]], str] = _default_mint
    http: Callable[..., Awaitable[tuple[int, Any]]] = _default_http


async def _google_session(settings: Any, deps: GoogleDeps) -> tuple[Optional[dict], str, str]:
    """(the service-account key, the delegated admin, why not) — the key as the
    features find it: the stored Email Setup first, then the setting."""
    stored = None
    try:
        stored = await deps.stored(settings)
    except Exception:  # noqa: BLE001
        stored = None
    raw = (stored or {}).get("service_account_json") or getattr(settings, "google_service_account_json", "")
    admin = ((stored or {}).get("delegated_admin") or getattr(settings, "google_delegated_admin", "") or "").strip()
    if not raw:
        return None, admin, "No service-account key is set."
    if not admin:
        return None, admin, "No delegated admin is set, so nobody can create the shared drive."
    try:
        info = json.loads(raw)
    except (TypeError, ValueError):
        return None, admin, "The service-account key is not valid JSON."
    return info, admin, ""


def _drive_name(settings: Any, value: str) -> str:
    from core import branding

    name = (value or "").strip()
    return name or f"{branding.abbr(settings)} Documents"


def _request_id(settings: Any, name: str) -> str:
    """Fixed for this deployment and name: Google returns the same drive for a
    repeated request instead of creating a second (drives.create, requestId)."""
    base = (getattr(settings, "app_base_url", "") or "").strip() or "this-deployment"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{base}|shared-drive|{name}"))


async def _find_drive(deps: GoogleDeps, token: str, name: str) -> tuple[Optional[dict], str]:
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    status, body = await deps.http("GET", f"{DRIVE_API}/drives", token,
                                   params={"q": f"name = '{escaped}'", "pageSize": 10})
    if status != 200:
        return None, f"Google refused to list shared drives (HTTP {status})."
    drives = (body or {}).get("drives") or []
    return (drives[0] if drives else None), ""


async def _token(settings: Any, deps: GoogleDeps) -> tuple[Optional[str], Optional[dict], str]:
    info, admin, why = await _google_session(settings, deps)
    if why:
        return None, None, why
    try:
        token = await asyncio.to_thread(deps.mint, info, [S_DRIVE], admin)
    except Exception as exc:  # noqa: BLE001
        return None, info, (f"Google refused a Drive token as {admin}: {type(exc).__name__}. "
                            "Check the delegation grant includes the Drive scope.")
    return token, info, ""


async def drive_dry_run(settings: Any, value: str, deps: Optional[GoogleDeps] = None) -> Result:
    deps = deps or GoogleDeps()
    name = _drive_name(settings, value)
    token, _info, why = await _token(settings, deps)
    if why:
        return Result(False, why)
    found, why = await _find_drive(deps, token, name)
    if why:
        return Result(False, why)
    if found:
        return Result(True, f"A shared drive named “{name}” already exists. Running this saves its ID "
                            "and makes sure the service account is a member.",
                      {"gdrive_shared_drive_id": str(found.get("id"))})
    return Result(True, f"Would create a shared drive named “{name}”, add the service account to it, "
                        "and save its ID.")


async def drive_apply(settings: Any, value: str, deps: Optional[GoogleDeps] = None) -> Result:
    deps = deps or GoogleDeps()
    name = _drive_name(settings, value)
    token, info, why = await _token(settings, deps)
    if why:
        return Result(False, why)
    found, why = await _find_drive(deps, token, name)
    if why:
        return Result(False, why)
    if found:
        drive_id = str(found.get("id"))
        created = False
    else:
        status, body = await deps.http("POST", f"{DRIVE_API}/drives", token,
                                       params={"requestId": _request_id(settings, name)}, body={"name": name})
        if status != 200 or not (body or {}).get("id"):
            return Result(False, f"Google refused to create the shared drive (HTTP {status}). "
                                 "The delegated admin may not be allowed to create shared drives.")
        drive_id, created = str(body["id"]), True
    member = str((info or {}).get("client_email") or "")
    status, body = await deps.http("GET", f"{DRIVE_API}/files/{drive_id}/permissions", token,
                                   params={"supportsAllDrives": "true", "fields": "permissions(emailAddress,role)"})
    have = {str(p.get("emailAddress") or "").lower() for p in ((body or {}).get("permissions") or [])} \
        if status == 200 else set()
    if member and member.lower() not in have:
        status, _ = await deps.http("POST", f"{DRIVE_API}/files/{drive_id}/permissions", token,
                                    params={"supportsAllDrives": "true", "sendNotificationEmail": "false"},
                                    body={"type": "user", "role": "fileOrganizer", "emailAddress": member})
        if status not in (200, 201):
            return Result(False, f"The shared drive exists, but Google refused to add the service account "
                                 f"(HTTP {status}).", {"gdrive_shared_drive_id": drive_id})
    verb = "Created" if created else "Found"
    return Result(True, f"{verb} the shared drive “{name}”; the service account is a member.",
                  {"gdrive_shared_drive_id": drive_id})


# --- Twilio: look up the sender number ---------------------------------------------------------

def _twilio(settings: Any) -> Any:
    from core.sms import TwilioSmsClient

    return TwilioSmsClient(settings.sms_account_sid, settings.sms_auth_token,
                           settings.sms_from_number or "+10000000000", timeout=10.0)


async def twilio_numbers(settings: Any, value: str, deps: Optional[Callable[[Any], Any]] = None) -> Result:
    if not (settings.sms_account_sid and settings.sms_auth_token):
        return Result(False, "The Twilio account SID and auth token are not set yet.")
    client = (deps or _twilio)(settings)
    try:
        data = await client.list_numbers()
    except Exception as exc:  # noqa: BLE001
        return Result(False, f"Twilio refused to list the account's numbers: {exc}")
    numbers = [n for n in (data or {}).get("incoming_phone_numbers") or []
               if ((n or {}).get("capabilities") or {}).get("sms")]
    if not numbers:
        return Result(False, "The Twilio account has no number that can send texts. Buy one first (guide step 5.15).")
    if len(numbers) > 1:
        listed = ", ".join(str(n.get("phone_number")) for n in numbers)
        return Result(False, f"The account has {len(numbers)} numbers that can send texts ({listed}). "
                             "Choose one and set it by hand.")
    number = str(numbers[0].get("phone_number"))
    return Result(True, f"The account's one texting number is {number}.", {"sms_from_number": number})


# --- Zoom: confirm the host ------------------------------------------------------------------------

def _zoom(settings: Any) -> Any:
    from core.zoom import DEFAULT_BASE_URL, ZoomClient

    return ZoomClient(settings.zoom_account_id, settings.zoom_client_id, settings.zoom_client_secret,
                      base_url=getattr(settings, "zoom_base_url", "") or DEFAULT_BASE_URL, timeout=10)


async def zoom_host(settings: Any, value: str, deps: Optional[Callable[[Any], Any]] = None) -> Result:
    host = (value or settings.zoom_host_email or "").strip()
    if not host:
        return Result(False, "No host address is given or set.")
    if not (settings.zoom_account_id and settings.zoom_client_id and settings.zoom_client_secret):
        return Result(False, "The Zoom account ID, client ID and client secret are not all set yet.")
    client = (deps or _zoom)(settings)
    try:
        user = await client.get_user(host)
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "status_code", None) == 404:
            return Result(False, f"Zoom has no user {host} on this account.")
        return Result(False, f"Zoom could not be asked about {host}: {exc}")
    if user.get("type") != 2:
        return Result(False, f"{host} is on the account but is not a licensed user, so it cannot host webinars.")
    return Result(True, f"{host} is a licensed user on this Zoom account.", {"zoom_host_email": host})


ACTIONS: dict[str, CodedAction] = {a.name: a for a in (
    CodedAction("google.create_shared_drive", "google_workspace", "Create the shared drive",
                "Creates the Google shared drive the documents feature files into (or finds one with the "
                "same name), adds the service account to it, and saves its ID.",
                "The drive's name (empty for the default)", drive_dry_run, drive_apply),
    CodedAction("twilio.find_sender_number", "twilio", "Look up the sender number",
                "Lists the Twilio account's numbers that can send texts and, if there is exactly one, "
                "saves it as the sender number. Reads only.",
                "Not used (leave empty)", twilio_numbers, twilio_numbers),
    CodedAction("zoom.confirm_host", "zoom", "Confirm the Zoom host",
                "Checks the host address is a licensed user on the Zoom account and saves it as the host. "
                "Reads only.", "The host address (empty for the current setting)", zoom_host, zoom_host),
)}


def for_integration(integration: str) -> list[CodedAction]:
    return [a for a in ACTIONS.values() if a.integration == integration]


async def run(name: str, settings: Any, value: str, *, dry: bool, deps: Any = None) -> Result:
    """Run one action. Never raises."""
    action = ACTIONS.get(name)
    if action is None:
        return Result(False, f"There is no coded action called {name}.")
    try:
        fn = action.dry_run if dry else action.apply
        return await fn(settings, value, deps) if deps is not None else await fn(settings, value)
    except Exception as exc:  # noqa: BLE001
        return Result(False, f"The action could not be run: {type(exc).__name__}: {exc}")
