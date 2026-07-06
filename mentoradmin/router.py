"""FastAPI routes for the Mentor Admin app (``/mentoradmin/api``).

Same EspoCRM team-based auth as the assignment dashboard, but gated to the
**Mentor Administration Team** and kept in its own session key, so it is
isolated from the assignment tool. All reads/writes run as the logged-in user
(their token) — EspoCRM enforces their edit permissions on CMentorProfile.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from assignments import service as assign_service
from assignments.auth import (
    AuthError,
    authenticate,
    clear_session,
    current_user,
    login_token,
    session_expired,
    set_session,
)
from assignments.espo_user import client_for
from core.app_config import make_app_config_store
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError
from core.google_directory import ResolvedGoogle, resolve_google_directory

from . import service

router = APIRouter(prefix="/mentoradmin/api", tags=["mentoradmin"])
log = logging.getLogger("cbm_intake.mentoradmin")

# Distinct session key so a Mentor-Admin login is separate from /assignments.
SESSION_KEY = "mentoradmin_user"


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UpdateIn(BaseModel):
    changes: dict
    # When False (the browser default), the save only writes fields — the
    # provisioning of a mentor's login is driven separately by the live status
    # window via the streaming /provision endpoint. True keeps the inline
    # (non-streaming) provisioning for API clients / the JS-off fallback.
    provision: bool = True


class GoogleSetupIn(BaseModel):
    # Blank service_account_json on an update keeps the stored key (lets an admin
    # toggle flags / change the delegated admin without re-pasting the secret).
    service_account_json: str = ""
    delegated_admin: str = ""
    directory_check: bool = True
    create_mailbox: bool = False


def _require_user(request: Request) -> dict:
    user = current_user(request, SESSION_KEY)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _require_admin(request: Request) -> dict:
    user = _require_user(request)
    if not user.get("isAdmin"):
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    if session_expired(exc):
        clear_session(request, SESSION_KEY)
        return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    # Log the full CRM error (includes the response body) so failures like a
    # value rejected by EspoCRM are diagnosable from the run logs.
    log.warning("%s: %s", message, exc)
    return HTTPException(status_code=502, detail=f"{message}: {exc}")


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    settings = get_settings()
    try:
        user = await authenticate(
            settings, body.username, body.password,
            allowed_teams=settings.mentor_admin_allowed_teams_list, allowed_roles=[],
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    set_session(request, user, SESSION_KEY)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request, SESSION_KEY)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.get("/mentors")
async def mentors(request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return {"mentors": await assign_service.list_all_mentors(client)}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load mentors")


@router.post("/mentors/status-check")
async def mentor_status_check(request: Request) -> dict:
    """"Update Mentor Status" — verify every mentor's login User + mailbox.

    Sweeps the roster and reports, per mentor, whether the linked EspoCRM
    login User actually exists (and is active) and whether the
    ``@cbmentors.org`` mailbox exists in Google Workspace; also re-syncs the
    stored recordStatus from live completeness. The User reads run as the
    provisioning admin when that account is configured (regular staff can't
    read Users); the mailbox check reports ``unavailable`` until the Google
    Directory integration is configured in Email Setup.
    """
    user = _require_user(request)
    settings = get_settings()
    client = client_for(settings, user)

    user_client = client
    factory = _provision_factory(settings)
    if factory is not None:
        try:
            user_client = await factory()
        except Exception:  # admin login unavailable — staff token still tries
            user_client = client

    google = await _resolve_google(settings)
    directory = google.directory if google.check_enabled else None

    try:
        rows = await service.verify_all_mentor_statuses(
            client, user_client=user_client, directory=directory
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not verify mentor statuses")
    return {"mentors": rows, "mailboxCheckEnabled": directory is not None}


@router.get("/fields")
async def fields(request: Request) -> dict:
    """The editable-field spec + live enum options, for the detail form."""
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return {"fields": service.EDITABLE_FIELDS, "options": await service.field_options(client)}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load field options")


@router.get("/mentors/{mentor_id}")
async def mentor_detail(mentor_id: str, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        rec = await service.get_mentor(client, mentor_id)
        rec["completeness"] = await service.check_completeness(client, rec)
        # Self-heal the stored recordStatus so the roster grid matches this live
        # badge. sync_record_status only writes when the value actually changed
        # (and never over a manual "Duplicate"), so a view corrects a drifted
        # record once, then is a no-op — the grid no longer goes stale.
        rec["recordStatus"] = await service.sync_record_status(
            client, mentor_id, rec, rec["completeness"]["status"]
        )
        return rec
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load mentor")


def _provision_factory(settings: Settings):
    """A lazy login factory for the provisioning admin, or None when disabled.

    EspoCRM only lets admins create Users (API keys can't), so provisioning acts
    as a dedicated admin service account via the App/user token flow — never the
    staff user's token. The returned async callable logs that account in (once,
    when a provisioning transition actually happens) and yields a privileged
    client. Gated on ``mentor_provision_users`` + configured credentials + a real
    (non-dry-run) base.
    """
    if (
        not settings.mentor_provision_users
        or settings.espo_dry_run
        or not (settings.espo_provision_username and settings.espo_provision_password)
    ):
        return None

    async def factory():
        user_name, token = await login_token(
            settings.espo_base_url,
            settings.espo_provision_username,
            settings.espo_provision_password,
            settings.request_timeout_seconds,
        )
        return EspoClient.for_user_token(
            settings.espo_base_url, user_name, token, settings.request_timeout_seconds
        )

    return factory


async def _resolve_google(settings: Settings) -> ResolvedGoogle:
    """The effective Google-Workspace integration: the in-app Email-Setup config
    (encrypted in Postgres) takes precedence, falling back to the GOOGLE_* env
    vars. Reads the stored config (best-effort) then resolves capabilities."""
    db_config = None
    store = make_app_config_store(settings)
    if store is not None:
        try:
            db_config = await store.get_google_config()
        except Exception:  # DB hiccup — fall back to env config
            db_config = None
        finally:
            await store.dispose()
    return resolve_google_directory(settings, db_config)


@router.put("/mentors/{mentor_id}")
async def mentor_update(mentor_id: str, body: UpdateIn, request: Request) -> dict:
    settings = get_settings()
    user = _require_user(request)
    client = client_for(settings, user)
    # Inline provisioning is the JS-off / API fallback only; it never creates a
    # mailbox (directory=None) — the browser drives the full check+create flow via
    # the streaming /provision endpoint, so the common path leaves PUT cheap.
    factory = _provision_factory(settings) if body.provision else None
    try:
        result = await service.update_mentor(
            client, mentor_id, body.changes,
            team_name=settings.mentor_team_name,
            admin_client_factory=factory,
        )
        comp = await service.check_completeness(client, result)
        result["completeness"] = comp
        result["recordStatus"] = await service.sync_record_status(client, mentor_id, result, comp["status"])
        return result
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save mentor")


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("/mentors/{mentor_id}/provision")
async def mentor_provision(mentor_id: str, request: Request) -> StreamingResponse:
    """Provision the mentor's CBM mailbox + EspoCRM login, streaming a status
    event per step (Server-Sent Events) to drive the live status window."""
    settings = get_settings()
    user = _require_user(request)
    client = client_for(settings, user)
    factory = _provision_factory(settings)
    resolved = await _resolve_google(settings)

    async def stream():
        if factory is None:
            yield _sse(service._step(
                "login", "error",
                "Mentor login provisioning is turned off on this server. An "
                "administrator must enable it (MENTOR_PROVISION_USERS + a service "
                "account).",
            ))
            return
        # Idempotency: skip a mentor that already has a login, or one not at an
        # approval status (the button is only offered for Approved/Active anyway).
        try:
            prof = await client.get(
                service.MENTOR_PROFILE, mentor_id,
                select="assignedUserId,assignedUsersIds,assignedUsersNames,mentorStatus",
            )
        except EspoError as exc:
            yield _sse(service._step("login", "error", f"Could not read the mentor: {exc}"))
            return
        if service.assigned_user_id(prof):
            yield _sse(service._step("login", "done", "This mentor already has an EspoCRM login — nothing to provision."))
            yield _sse({"step": "done", "status": "done", "message": "No provisioning needed", "result": {"skipped": True}})
            return
        if prof.get("mentorStatus") not in (service.STATUS_APPROVED, service.STATUS_ACTIVE):
            yield _sse(service._step("login", "error", "A login is only created for an Approved or Active mentor."))
            return
        try:
            admin_client = await factory()
        except Exception as exc:  # admin service-account login failed
            yield _sse(service._step("login", "error", f"Could not sign in the provisioning service account: {exc}"))
            return
        try:
            async for event in service.provision_mentor_user_steps(
                admin_client, client, mentor_id,
                team_name=settings.mentor_team_name,
                directory=resolved.directory,
                create_mailbox=resolved.create_enabled,
            ):
                yield _sse(event)
        except Exception as exc:  # never leak a raw 500 into the stream
            yield _sse(service._step("login", "error", f"Provisioning failed: {exc}"))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# --- Email Setup (admin-only): configure the Google Workspace integration ---

@router.get("/setup/google")
async def google_setup_get(request: Request) -> dict:
    """Current Google-Workspace config status (never the private key)."""
    _require_admin(request)
    settings = get_settings()
    store = make_app_config_store(settings)
    if store is None:
        # No DB + encryption key: the in-app store is unavailable; report whether
        # the env-var fallback is configured so the UI can explain the options.
        return {
            "available": False,
            "reason": "Set DATABASE_URL and APP_ENCRYPTION_KEY to configure Google from here.",
            "envConfigured": bool(settings.google_service_account_json and settings.google_delegated_admin),
        }
    try:
        cfg = await store.get_google_config()
        meta = await store.get_meta("google_workspace")
    finally:
        await store.dispose()
    cfg = cfg or {}
    return {
        "available": True,
        "configured": bool(cfg.get("service_account_json") and cfg.get("delegated_admin")),
        "delegatedAdmin": cfg.get("delegated_admin", ""),
        "directoryCheck": bool(cfg.get("directory_check", True)),
        "createMailbox": bool(cfg.get("create_mailbox", False)),
        "updatedAt": (meta or {}).get("updatedAt"),
    }


def _validate_service_account(raw: str) -> dict:
    try:
        info = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Service-account JSON is not valid JSON: {exc}")
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise HTTPException(status_code=400, detail="That does not look like a Google service-account key (expected a JSON object with \"type\": \"service_account\").")
    return info


def _build_google_payload(body: GoogleSetupIn, existing: dict) -> dict:
    raw = body.service_account_json.strip()
    if raw:
        _validate_service_account(raw)
    else:
        raw = (existing or {}).get("service_account_json", "")
        if not raw:
            raise HTTPException(status_code=400, detail="Paste the service-account JSON key (none is stored yet).")
    if not body.delegated_admin.strip():
        raise HTTPException(status_code=400, detail="A delegated Workspace admin email is required.")
    return {
        "service_account_json": raw,
        "delegated_admin": body.delegated_admin.strip(),
        "directory_check": body.directory_check,
        "create_mailbox": body.create_mailbox,
    }


@router.put("/setup/google")
async def google_setup_put(body: GoogleSetupIn, request: Request) -> dict:
    _require_admin(request)
    store = make_app_config_store(get_settings())
    if store is None:
        raise HTTPException(status_code=503, detail="In-app Google setup is unavailable (set DATABASE_URL and APP_ENCRYPTION_KEY).")
    try:
        existing = await store.get_google_config() or {}
        payload = _build_google_payload(body, existing)
        await store.set_google_config(payload)
    finally:
        await store.dispose()
    return {"status": "saved", "createMailbox": payload["create_mailbox"], "directoryCheck": payload["directory_check"]}


@router.post("/setup/google/test")
async def google_setup_test(body: GoogleSetupIn, request: Request) -> dict:
    """Verify the configured credentials by looking up the delegated admin's own
    mailbox — a successful EXISTS proves auth + the read scope + delegation."""
    _require_admin(request)
    settings = get_settings()
    store = make_app_config_store(settings)
    existing: dict = {}
    if store is not None:
        try:
            existing = await store.get_google_config() or {}
        finally:
            await store.dispose()
    # Use the submitted values if present, else what's stored.
    raw = body.service_account_json.strip() or existing.get("service_account_json", "")
    admin = body.delegated_admin.strip() or existing.get("delegated_admin", "")
    if not raw or not admin:
        raise HTTPException(status_code=400, detail="Provide (or save) a service-account JSON and a delegated admin email first.")
    _validate_service_account(raw)
    from core.google_directory import GoogleDirectory, MailboxStatus

    directory = GoogleDirectory.from_config(
        {"service_account_json": raw, "delegated_admin": admin}, settings.request_timeout_seconds
    )
    if directory is None:
        raise HTTPException(status_code=400, detail="Could not build a Google client from the provided values.")
    status = await directory.mailbox_status(admin)
    if status is MailboxStatus.EXISTS:
        return {"ok": True, "message": f"Connected to Google Workspace and found {admin}."}
    if status is MailboxStatus.MISSING:
        return {"ok": True, "message": f"Authenticated, but {admin} was not found — double-check the delegated admin address."}
    return {"ok": False, "message": "Could not authenticate. Check the service-account key, that the Admin SDK API is enabled, and that domain-wide delegation is authorized for the Directory scopes."}
