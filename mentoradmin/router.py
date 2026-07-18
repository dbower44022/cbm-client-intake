"""FastAPI routes for the Mentor Admin app (``/mentoradmin/api``).

Uses the shared staff session (sign in once at the portal ``/``), gated per
request to the **Mentor Administration Team** (admins always pass). All
reads/writes run as the logged-in user (their token) — EspoCRM enforces their
edit permissions on CMentorProfile.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from assignments import service as assign_service
from assignments.auth import (
    clear_session,
    current_user,
    is_member,
    login_token,
    session_expired,
)
from assignments.espo_user import client_for
from core.app_config import make_app_config_store
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError, forbidden_hint, is_forbidden, validation_message
from core.gdrive import DriveError
from core.google_directory import ResolvedGoogle, resolve_google_directory
from docs import service as docs_service

from . import service

router = APIRouter(prefix="/mentoradmin/api", tags=["mentoradmin"])
log = logging.getLogger("cbm_intake.mentoradmin")

# Provisioning-admin auth tokens, cached per (base URL, username) for the life
# of the process — see _provision_factory.
_PROVISION_TOKEN_CACHE: dict[str, tuple[str, str]] = {}

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
    """The shared staff session + THIS app's team gate, per request (401 = not
    signed in — the frontend sends the user to the portal; 403 = signed in but
    not on the Mentor Administration Team; admins always pass)."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    if not is_member(user, settings.mentor_admin_allowed_teams_list):
        raise HTTPException(
            status_code=403,
            detail=(
                "Your account is not authorized to use Mentor Administration "
                f"(requires the {', '.join(settings.mentor_admin_allowed_teams_list) or 'admin'} team)."
            ),
        )
    return user


def _require_admin(request: Request) -> dict:
    user = _require_user(request)
    if not user.get("isAdmin"):
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    if session_expired(exc):
        clear_session(request)
        return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    # Log the full CRM error (includes the response body) so failures like a
    # value rejected by EspoCRM are diagnosable from the run logs.
    actor = (current_user(request) or {}).get("userName", "?")
    log.warning("%s (user=%s): %s", message, actor, exc)
    # A CRM validation rejection is the caller's data, not a server fault —
    # answer with a readable 400 naming the field, never a raw 502/504.
    friendly = validation_message(exc)
    if friendly:
        return HTTPException(status_code=400, detail=friendly)
    # A CRM 403 is a permission gap — name the exact missing grant (Doug's
    # ask 2026-07-16) so the CRM admin knows what to add.
    if is_forbidden(exc):
        hint = forbidden_hint(exc)
        return HTTPException(
            status_code=403,
            detail=(
                f"{message}: your CRM role is missing {hint} — "
                "ask CBM staff to grant it."
                if hint else
                f"{message}: your account doesn't have permission to do this "
                "in the CRM — ask CBM staff if you need it."
            ),
        )
    return HTTPException(status_code=502, detail=f"{message}: {exc}")


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {
        "userName": user["userName"],
        "name": user["name"],
        "isAdmin": user["isAdmin"],
        # True => the detail screen shows the Documents tab (DOC-MGMT: mentor
        # documents anchored to the mentor's linked Contact record).
        "docsEnabled": get_settings().gdrive_docs,
    }


@router.get("/mentors")
async def mentors(request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        # {"mentors": [...], "metricsAvailable": bool} — served as-is.
        return await assign_service.list_all_mentors(client)
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
        except Exception as exc:  # noqa: BLE001 — admin login unavailable
            # The sweep silently downgrades to the staff token, which usually
            # cannot read Users — every mentor then reports an unverifiable
            # login. Name the downgrade so the sweep results are explainable.
            log.warning(
                "status-check: provisioning admin login failed — falling back "
                "to the staff token (login checks may report unknown): %s", exc,
            )
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


# --- Documents (Google Drive, DOC-MGMT — mentor documents) --------------------
# Mentor documents (resumes, signed agreements, …) anchor to the mentor's
# linked CONTACT record (PRD v1.2: Contact is the Phase 1 mentor anchor) and
# live under Mentors/{Name} (contactId)/ on the shared drive. Everything 503s
# unless GDRIVE_DOCS is enabled (the frontend hides the tab then).


def _docs_ready():
    """(settings, document_store) — or a 503 when the integration is off."""
    settings = get_settings()
    if not settings.gdrive_docs:
        raise HTTPException(
            status_code=503, detail="The document integration isn't enabled."
        )
    store = docs_service.get_store(settings)
    if store is None:
        raise HTTPException(
            status_code=503, detail="The document integration needs the database."
        )
    return settings, store


async def _mentor_contact_anchor(client, mentor_id: str) -> tuple[str, str]:
    """(contact_id, display_name) for a mentor's document anchor — the linked
    Contact record. A profile with no linked Contact can't own documents yet."""
    profile = await client.get(
        service.MENTOR_PROFILE, mentor_id, select="name,contactRecordId,contactRecordName"
    )
    contact_id = profile.get("contactRecordId")
    if not contact_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "This mentor has no linked Contact record, so documents can't "
                "be stored for them yet — link a Contact first."
            ),
        )
    return contact_id, profile.get("contactRecordName") or profile.get("name") or ""


@router.get("/mentors/{mentor_id}/documents")
async def mentor_documents(
    mentor_id: str, request: Request, includeArchived: bool = False
) -> dict:
    user = _require_user(request)
    settings, store = _docs_ready()
    client = client_for(settings, user)
    try:
        contact_id, _ = await _mentor_contact_anchor(client, mentor_id)
        rows = await docs_service.list_documents(
            store, "Contact", contact_id, include_archived=includeArchived
        )
        return {
            "documents": rows,
            "docTypes": settings.gdrive_doc_types_list,
            "maxFileMb": settings.gdrive_max_file_mb,
        }
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load documents")


@router.post("/mentors/{mentor_id}/documents")
async def mentor_upload_document(
    mentor_id: str, request: Request, filename: str = "", docType: str = ""
) -> dict:
    """Upload one file (raw request body; filename/docType as query params,
    MIME from the Content-Type header) to the mentor's Contact folder, then
    record it in the metadata table (rollback on failure — DOC-01)."""
    user = _require_user(request)
    settings, store = _docs_ready()
    client = client_for(settings, user)
    data = await request.body()
    # Receipt log BEFORE any processing: an upload that dies later is
    # diagnosable from the run logs (who, what, how big).
    log.info(
        "mentor document upload received (%s): %r %d bytes as %s",
        mentor_id, filename, len(data), user.get("userName"),
    )
    try:
        contact_id, contact_name = await _mentor_contact_anchor(client, mentor_id)
        drive = await docs_service.drive_for_user(settings, client, user)
        row = await docs_service.upload_document(
            settings, store, drive,
            entity_type="Contact",
            record_id=contact_id,
            record_name=contact_name,
            filename=filename,
            mime_type=request.headers.get("content-type", ""),
            doc_type=docType,
            data=data,
        )
        # DOC-08 write-back (Contact is a participating entity) + DOC-09 grant
        # sync — which for Mentors/ (Contact) folders enforces the rule that
        # they are granted to NO ONE (application-only). Best-effort.
        await docs_service.post_upload_hooks(settings, drive, "Contact", contact_id, row)
        return {"status": "ok", "document": row}
    except docs_service.DocsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DriveError as exc:
        log.warning("mentor document upload failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Couldn't reach Google Drive — try again."
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not upload the document")


@router.get("/mentors/{mentor_id}/documents/{doc_id}/content")
async def mentor_document_content(
    mentor_id: str, doc_id: str, request: Request, original: bool = False
) -> Response:
    """DOC-03: stream a mentor document's bytes through the app. The mentor
    profile is read AS THE USER (their ACL gates viewing) to resolve the
    Contact anchor. Default = viewing (Google-native + Office formats arrive
    as PDF); ``?original=true`` = the Download action (exact stored bytes,
    attachment). Served immutable — the frontend versions the URL by
    modifiedTime (DOC-06)."""
    user = _require_user(request)
    settings, store = _docs_ready()
    client = client_for(settings, user)
    try:
        contact_id, _ = await _mentor_contact_anchor(client, mentor_id)
        drive = await docs_service.drive_for_user(settings, client, user)
        doc = await docs_service.fetch_document(
            store, drive, "Contact", contact_id, doc_id, original=original
        )
    except docs_service.DocsNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except docs_service.DocsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DriveError as exc:
        log.warning("mentor document fetch failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=(
                "Couldn't fetch the document from Google Drive — "
                "try again, or use Open in Drive."
            ),
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load the document")
    return Response(
        content=doc["data"],
        media_type=doc["mime_type"],
        headers=docs_service.content_headers(doc["filename"], attachment=original),
    )


@router.post("/mentors/{mentor_id}/documents/refresh")
async def mentor_refresh_documents(
    mentor_id: str, request: Request, includeArchived: bool = False
) -> dict:
    """DOC-02 completion — lazy modifiedTime refresh for the mentor's Contact
    folder; fired by the frontend after the metadata render, never blocking."""
    user = _require_user(request)
    settings, store = _docs_ready()
    client = client_for(settings, user)
    try:
        contact_id, _ = await _mentor_contact_anchor(client, mentor_id)
        drive = await docs_service.drive_for_user(settings, client, user)
        rows = await docs_service.refresh_documents(
            store, drive, "Contact", contact_id, include_archived=includeArchived
        )
        return {
            "documents": rows,
            "docTypes": settings.gdrive_doc_types_list,
            "maxFileMb": settings.gdrive_max_file_mb,
        }
    except docs_service.DocsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DriveError as exc:
        log.warning("mentor document refresh failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Couldn't reach Google Drive — try again."
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not refresh the documents")


async def _mentor_document_lifecycle(
    mentor_id: str, doc_id: str, request: Request, *, archive: bool
) -> dict:
    """DOC-07 shared handler (mentor documents on the linked Contact): the
    profile is read AS THE USER (ACL gate), then the Drive move + status flip
    run in docs.service (move first, flip after, rollback on a mid-failure)."""
    user = _require_user(request)
    settings, store = _docs_ready()
    client = client_for(settings, user)
    try:
        contact_id, _ = await _mentor_contact_anchor(client, mentor_id)
        drive = await docs_service.drive_for_user(settings, client, user)
        fn = (
            docs_service.archive_document if archive
            else docs_service.restore_document
        )
        row = await fn(store, drive, "Contact", contact_id, doc_id)
        return {"status": "ok", "document": row}
    except docs_service.DocsNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except docs_service.DocsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DriveError as exc:
        log.warning(
            "mentor document %s failed: %s", "archive" if archive else "restore", exc
        )
        raise HTTPException(
            status_code=502, detail="Couldn't reach Google Drive — try again."
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not update the document")


@router.post("/mentors/{mentor_id}/documents/{doc_id}/archive")
async def mentor_archive_document(mentor_id: str, doc_id: str, request: Request) -> dict:
    """DOC-07: soft-delete — the file moves to the Contact folder's /_Archived
    subfolder and the row leaves the default list."""
    return await _mentor_document_lifecycle(mentor_id, doc_id, request, archive=True)


@router.post("/mentors/{mentor_id}/documents/{doc_id}/restore")
async def mentor_restore_document(mentor_id: str, doc_id: str, request: Request) -> dict:
    """DOC-07: reverse of archive."""
    return await _mentor_document_lifecycle(mentor_id, doc_id, request, archive=False)


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
        # Reuse the cached auth token across calls (P2, reliability review
        # 2026-07-17): logging in with the password on EVERY provisioning /
        # sweep call meant a rotated password turned each sweep into a run of
        # failed admin logins — enough to trip EspoCRM's brute-force lockout
        # on the service account. The cached token is validated with one cheap
        # read; only a dead token triggers a fresh password login.
        cache_key = f"{settings.espo_base_url}:{settings.espo_provision_username}"
        cached = _PROVISION_TOKEN_CACHE.get(cache_key)
        if cached:
            client = EspoClient.for_user_token(
                settings.espo_base_url, cached[0], cached[1],
                settings.request_timeout_seconds,
            )
            try:
                await client.app_user()
                return client
            except EspoError as exc:
                if not session_expired(exc):
                    raise
                _PROVISION_TOKEN_CACHE.pop(cache_key, None)
        user_name, token = await login_token(
            settings.espo_base_url,
            settings.espo_provision_username,
            settings.espo_provision_password,
            settings.request_timeout_seconds,
        )
        _PROVISION_TOKEN_CACHE[cache_key] = (user_name, token)
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
        # Audit: which fields changed (never the values — they may be PII).
        log.info(
            "mentor CMentorProfile/%s saved by %s (fields: %s)",
            mentor_id, user["userName"], ", ".join(sorted(body.changes)) or "-",
        )
        return result
    except service.MentorAdminError as exc:
        # e.g. contact fields saved on a mentor with no linked Contact record —
        # nothing was written; tell the user exactly why.
        raise HTTPException(status_code=400, detail=str(exc))
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

    def _emit(event: dict) -> str:
        # Server-side record of the highest-privilege flow in the app (mailbox
        # + User creation) — previously the events went to the browser only.
        # step/status/message ONLY: the extras can carry the temp password.
        log.info(
            "provision %s (by %s): [%s/%s] %s",
            mentor_id, user["userName"],
            event.get("step"), event.get("status"), event.get("message", ""),
        )
        return _sse(event)

    async def stream():
        if factory is None:
            yield _emit(service._step(
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
            yield _emit(service._step("login", "error", f"Could not read the mentor: {exc}"))
            return
        if service.assigned_user_id(prof):
            yield _emit(service._step("login", "done", "This mentor already has an EspoCRM login — nothing to provision."))
            yield _emit({"step": "done", "status": "done", "message": "No provisioning needed", "result": {"skipped": True}})
            return
        if prof.get("mentorStatus") not in (service.STATUS_APPROVED, service.STATUS_ACTIVE):
            yield _emit(service._step("login", "error", "A login is only created for an Approved or Active mentor."))
            return
        try:
            admin_client = await factory()
        except Exception as exc:  # admin service-account login failed
            yield _emit(service._step("login", "error", f"Could not sign in the provisioning service account: {exc}"))
            return
        try:
            async for event in service.provision_mentor_user_steps(
                admin_client, client, mentor_id,
                team_name=settings.mentor_team_name,
                directory=resolved.directory,
                create_mailbox=resolved.create_enabled,
            ):
                yield _emit(event)
        except Exception as exc:  # never leak a raw 500 into the stream
            yield _emit(service._step("login", "error", f"Provisioning failed: {exc}"))

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


# Quick-send email (the email-address links product-wide): GET /mailbox +
# POST /sendmail, behind this app's own gate. See comms/quicksend.py.
from comms.quicksend import register_quicksend  # noqa: E402  (needs router + helpers above)

register_quicksend(router, _require_user, client_for, _crm_failure)
