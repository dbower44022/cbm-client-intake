"""FastAPI routes for a Session Management domain (``/{slug}/api``).

:func:`make_router` builds one router per domain from a
:class:`sessions.config.DomainConfig`. All three share this code; only the
config differs. Uses the shared staff session (sign in once at the portal),
gated per request to the domain's team (admins always pass). All reads/writes
run as the logged-in user, so EspoCRM enforces their ACL.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from assignments.auth import clear_session, current_user, is_member, session_expired
from assignments.espo_user import client_for
from core import action_log
from comms import service as comms_service
from comms import templates as comms_templates
from core.config import get_settings
from core.espo import EspoError, forbidden_hint, validation_message
from core.gdrive import DriveError
from core.gmail import GmailError
from docs import grants as doc_grants
from docs import service as docs_service

from . import details as details_svc
from . import service
from .config import CONTRIBUTION_FIELDS, DomainConfig

log = logging.getLogger("cbm_intake.sessions")

# --- duplicate-save protection for session creates -------------------------
# The staff tools had no equivalent of the intake forms' ``submission_token``:
# a save that LOOKED like it failed (a slow request with no feedback, or a
# post-create read error reported as "Could not create session") could be saved
# again and silently create a second identical CSession. On 2026-07-17 that put
# three byte-identical Completed sessions on one engagement, 44s and 2s apart.
#
# The editor now also guards re-entry client-side, but that cannot cover a
# genuine retry (lost response, reload, impatient second tab), so the create is
# idempotent per (domain, user, parent, token): the frontend mints one token
# when it opens a NEW-session editor and sends it with every save attempt of
# that editor. The per-key lock makes a CONCURRENT second submit wait for the
# first and then take its result, rather than racing past the cache check.
#
# In-memory is sufficient: both deployed apps run a single web instance
# (``instance_count: 1``), and the window that matters is seconds. A redeploy
# clears it, which only re-opens the duplicate window for saves in flight at
# that moment. Mirrors the storeless idempotency path in ``core/app.py``.
_CREATE_TOKEN_TTL = 900.0  # seconds
_recent_creates: dict[str, tuple[float, str]] = {}  # key -> (stamped_at, session id)
_create_locks: dict[str, tuple[float, asyncio.Lock]] = {}
_locks_guard = asyncio.Lock()


def _prune_create_tokens(now: float) -> None:
    """Drop idempotency entries older than the TTL (keeps both maps bounded)."""
    for key, (stamped, _) in list(_recent_creates.items()):
        if now - stamped > _CREATE_TOKEN_TTL:
            _recent_creates.pop(key, None)
    for key, (stamped, _) in list(_create_locks.items()):
        if now - stamped > _CREATE_TOKEN_TTL:
            _create_locks.pop(key, None)


async def _create_token_lock(key: str) -> asyncio.Lock:
    """The lock for one idempotency key, created on first use."""
    async with _locks_guard:
        entry = _create_locks.get(key)
        if entry is None:
            entry = (time.monotonic(), asyncio.Lock())
            _create_locks[key] = entry
        return entry[1]


class SessionIn(BaseModel):
    changes: dict = {}
    # Contact ids for the session's attendees. None => leave attendees unchanged
    # (on edit); [] => clear them. Sent by the frontend attendee picker.
    attendees: Optional[list[str]] = None
    # True = the user declined the automatic calendar invite in the pre-save
    # prompt (new Scheduled sessions only) — save the session, skip the event.
    skipCalendar: bool = False
    # True = the user declined calendar invitations for the AUTO-CREATED
    # follow-up session (a Completed save with a future "Next session" date
    # books the agreed next meeting — see service._maybe_create_follow_up).
    # The follow-up session is created either way.
    skipFollowUpInvite: bool = False
    # Idempotency key for a CREATE: one token per open new-session editor, sent
    # with every save attempt of that editor, so a retry returns the session
    # already created instead of making a second one. Ignored on update.
    submissionToken: Optional[str] = None


class CoMentorIn(BaseModel):
    mentorProfileId: str


class ContributionIn(BaseModel):
    changes: dict = {}


class DetailsSaveIn(BaseModel):
    changes: dict = {}


class CommentIn(BaseModel):
    body: str


class IncludeIn(BaseModel):
    gmailThreadId: str


class SendIn(BaseModel):
    to: list[str] = []
    cc: list[str] = []
    bcc: list[str] = []
    subject: str = ""
    body: str = ""
    replyToCommunicationId: Optional[str] = None
    # True after the user confirms sending to an address that isn't one of the
    # record's contacts (the server refuses otherwise).
    allowUnknownRecipients: bool = False
    # Each: {"espoId": …} (a template-attachment chip, bytes fetched from the
    # CRM at send time) or {"filename","contentType","dataBase64"} (a local
    # upload). See comms.service.resolve_attachments.
    attachments: list[dict] = []


class TemplateParseIn(BaseModel):
    # {Person.*} resolution hint — normally the compose dialog's first
    # recipient; the record itself is the {Parent.*} context (from the URL).
    emailAddress: str = ""




class AddressIn(BaseModel):
    address: str


class ContactAddIn(BaseModel):
    """Add a contact to the record: link an existing one (``contactId``) OR
    create a new one from ``changes`` and link it — exactly one of the two.
    ``newCompanyName`` (create path only): find-or-create an Account by that
    name and set it as the new contact's company."""

    contactId: Optional[str] = None
    changes: Optional[dict] = None
    newCompanyName: Optional[str] = None


# Phase-one detail tabs, common to all three domains. Overview + Sessions +
# Details (full company/contact/profile fields, editable) are built. The
# Communications tab renders an email-inbox grid (UI only — no CRM email data is
# read yet; the CRM email structure is still being designed). Documents lists +
# uploads Google Drive files (DOC-MGMT Phase 1; a "coming soon" panel until
# GDRIVE_DOCS is enabled — config.docsEnabled).
COMMON_DETAIL_TABS = [
    {"key": "overview", "label": "Overview"},
    {"key": "details", "label": "Details"},
    {"key": "sessions", "label": "Sessions"},
    {"key": "communications", "label": "Communications"},
    {"key": "documents", "label": "Documents"},
]

# Shown instead of the domain's empty message when /records returns
# profileFound=false: the user passed the team gate but no CMentorProfile has
# them as its assigned User, so nothing can be scoped to them. Only an
# administrator can create that link (in the CRM), so this one names them.
NO_PROFILE_MESSAGE = (
    "Your login isn't linked to a CBM Mentor profile yet, so there are no "
    "records to show. Ask an administrator to set your user as the Assigned "
    "User on your profile in the CRM, then Refresh."
)


def _detail_tabs(cfg: DomainConfig) -> list[dict]:
    """The domain's tab bar: the common tabs, plus Contributions (inserted
    right after Sessions) on a domain with a contributions link (sponsor)."""
    tabs = list(COMMON_DETAIL_TABS)
    if cfg.contributions_link:
        idx = next((i for i, t in enumerate(tabs) if t["key"] == "sessions"), len(tabs) - 1)
        tabs.insert(idx + 1, {"key": "contributions", "label": "Contributions"})
    return tabs


def make_router(cfg: DomainConfig) -> APIRouter:
    router = APIRouter(prefix=f"/{cfg.slug}/api", tags=[cfg.slug])

    def _allowed_teams() -> list[str]:
        return getattr(get_settings(), cfg.allowed_teams_attr)

    def _require_user(request: Request) -> dict:
        """Shared staff session + this domain's team gate (401 = not signed in →
        the frontend sends the user to the portal; 403 = signed in but not on the
        domain's team; admins always pass)."""
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        teams = _allowed_teams()
        if not is_member(user, teams):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your account is not authorized to use {cfg.title} "
                    f"(requires the {', '.join(teams) or 'admin'} team)."
                ),
            )
        return user

    def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
        if session_expired(exc):
            clear_session(request)
            return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
        actor = (current_user(request) or {}).get("userName", "?")
        log.warning("%s (%s, user=%s): %s", message, cfg.slug, actor, exc)
        # A CRM validation rejection is the caller's data, not a server fault —
        # answer with a readable 400 naming the field, never a raw 502/504.
        friendly = validation_message(exc)
        if friendly:
            return HTTPException(status_code=400, detail=friendly)
        # A CRM permission rejection is the user's ACL, not a server fault either
        # — surface it as a readable 403 (found live 2026-07-15: a mentor without
        # the Contact create grant got a blank 502→edge 504 from + Add).
        if service._is_forbidden(exc):
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
        # A CRM 5xx is EspoCRM's own server-side failure (e.g. a database
        # rejection — a bare "HTTP 500" reached users as an unexplained 504 on
        # 2026-07-24 when oversized notes tripped MySQL's column limit). Say
        # what is known, what is NOT lost, and where the detail lives.
        if service._is_crm_server_error(exc):
            return HTTPException(
                status_code=502,
                detail=(
                    f"{message}: the CRM reported an internal error while "
                    "processing this request. Nothing you typed has been lost — "
                    "it is still in this editor. Please try again; if it keeps "
                    "failing, tell CBM staff (the CRM server log has the detail)."
                ),
            )
        return HTTPException(status_code=502, detail=f"{message}: {exc}")

    @router.get("/session")
    async def session(request: Request) -> dict:
        user = _require_user(request)
        return {
            "userName": user["userName"],
            "name": user["name"],
            "isAdmin": user["isAdmin"],
            "domain": cfg.slug,
            "title": cfg.title,
            "subtitle": cfg.subtitle,
            "parentLabel": cfg.parent_label,
            "columns": [{"key": c.key, "label": c.label, "type": c.type} for c in cfg.list_columns],
            "dateColumn": (
                {"key": cfg.list_date_column[0], "label": cfg.list_date_column[1]}
                if cfg.list_date_column
                else None
            ),
            "statusKey": cfg.list_status_key,
            # Grid one-click status transition (mentor: accept an assigned
            # engagement — Pending Acceptance → Assigned). None = no action.
            "statusAccept": (
                {"from": cfg.list_status_accept[0], "to": cfg.list_status_accept[1]}
                if cfg.list_status_accept
                else None
            ),
            "contactKey": cfg.list_contact_key,
            "companyKey": cfg.list_company_key,
            "emptyMessage": cfg.empty_message,
            "noProfileMessage": NO_PROFILE_MESSAGE,
            "detailTabs": _detail_tabs(cfg),
            "supportsComentor": cfg.supports_comentor,
            "defaultSessionType": cfg.default_session_type,
            # True => the Communications tab talks to the real endpoints below;
            # false => the frontend keeps its sample-data scaffold.
            "commsEnabled": get_settings().gmail_sync,
            # True => saving a NEW Scheduled session would create a Google
            # Calendar event, so the frontend asks first (create vs. manual).
            "gcalEnabled": get_settings().gcal_events,
            # True => the Documents tab talks to the real endpoints below;
            # false => it shows a "coming soon" placeholder.
            "docsEnabled": get_settings().gdrive_docs,
            # True => the Overview shows the staff-internal Discussion pane
            # (partner + sponsor). Also requires the durable store to be
            # configured; the frontend hides the pane if a comments read 503s.
            "discussionEnabled": cfg.discussion_enabled,
        }

    @router.post("/logout")
    async def logout(request: Request) -> dict:
        clear_session(request)
        return {"status": "ok"}

    @router.get("/calendar/busy")
    async def calendar_busy(
        request: Request, timeMin: str, timeMax: str, session: str = ""
    ) -> dict:
        """Busy blocks on the signed-in user's OWN Google calendar between two
        UTC stamps (``YYYY-MM-DD HH:MM:SS``) — the session editor's time picker
        shades conflicting slots light red. Purely advisory: a shaded time is
        still selectable (deconflicting is the user's responsibility), and any
        failure degrades to ``available: false`` with no shading — this
        endpoint never errors. ``session`` (optional) = the session being
        edited, so its own event doesn't read as a conflict."""
        user = _require_user(request)
        settings = get_settings()
        from sessions import gcal  # lazy — gcal imports sessions.service

        return await gcal.calendar_busy(
            settings, client_for(settings, user), user["userId"],
            timeMin, timeMax, exclude_session_id=session or None,
        )

    @router.get("/records")
    async def records(request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.list_records(cfg, client, user)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load records")

    @router.get("/fields")
    async def fields(request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return {
                "fields": await service.field_spec_live(client),
                "options": await service.field_options(client),
                "required": await service.field_required(client),
            }
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load field options")

    def _discussion_store(request: Request):
        """The durable store when discussion is enabled AND a database is
        configured, else None. The comment endpoints 503 on None; the detail
        merge just omits ``comments`` (the frontend hides the pane)."""
        if not cfg.discussion_enabled:
            return None
        return getattr(request.app.state, "submission_store", None)

    @router.get("/records/{parent_id}")
    async def record_detail(parent_id: str, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            detail = await service.get_detail(cfg, client, parent_id)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load record")
        # The record read above is the ACL gate; the discussion is a best-effort
        # add-on keyed by (parent entity, id). Never fail the detail over it —
        # if the store is absent the frontend simply hides the pane.
        store = _discussion_store(request)
        if store is not None:
            try:
                detail["comments"] = await store.list_record_comments(
                    cfg.parent_entity, parent_id
                )
            except Exception as exc:  # noqa: BLE001 — discussion is non-load-bearing
                log.warning("discussion read failed (%s/%s): %s", cfg.slug, parent_id, exc)
        return detail

    @router.get("/details/{parent_id}")
    async def details(parent_id: str, request: Request) -> dict:
        """The Details tab: editable field sections for the company, profile, and
        related contacts behind this record."""
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await details_svc.build_details(cfg, client, parent_id, user.get("userId"))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load details")

    # The Details tab only ever edits this domain's configured entities plus
    # the related-contact rows. Without this allowlist the PUT below is a
    # generic write proxy bounded only by the caller's CRM ACL — e.g. a Mentor
    # Team member (whose role carries CMentorProfile edit=all for co-mentor
    # relates) could set mentorStatus on anyone's profile (P0-4, reliability
    # review 2026-07-17).
    _details_put_entities = {e for _, e, _ in cfg.details_entities} | {"Contact"}

    @router.put("/details/{entity}/{record_id}")
    async def save_details(entity: str, record_id: str, body: DetailsSaveIn, request: Request) -> dict:
        user = _require_user(request)
        if entity not in _details_put_entities:
            # 404 (not 403) so probing can't confirm which entity names exist.
            raise HTTPException(status_code=404, detail="Not found")
        client = client_for(get_settings(), user)
        try:
            result = await details_svc.save_details(client, entity, record_id, body.changes)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save details")
        # Audit: which fields changed (never the values — they may be PII).
        log.info(
            "details saved %s/%s by %s (fields: %s)",
            entity, record_id, user["userName"], ", ".join(sorted(body.changes)) or "-",
        )
        return result

    @router.get("/contacts")
    async def contacts_search(request: Request, q: str = "") -> dict:
        """Search existing contacts for the add-contact picker (as the user)."""
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return {"contacts": await details_svc.search_contacts(client, q)}
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not search contacts")

    @router.post("/records/{parent_id}/contacts")
    async def add_contact(parent_id: str, body: ContactAddIn, request: Request) -> dict:
        """Link an existing contact to this record, or create-and-link a new one
        (see sessions.details.link_contact / create_contact for the CRM relations)."""
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            if body.contactId:
                await details_svc.link_contact(cfg, client, parent_id, body.contactId)
                return {"status": "ok"}
            changes = dict(body.changes or {})
            if body.newCompanyName:
                account_id = await comms_service.resolve_company(
                    client, _api_client(get_settings()), body.newCompanyName
                )
                if account_id:
                    changes["accountId"] = account_id
            created = await details_svc.create_contact(cfg, client, parent_id, changes)
            return {"status": "ok", "id": created["id"]}
        except service.SessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not add the contact")

    @router.delete("/records/{parent_id}/contacts/{contact_id}")
    async def remove_contact(parent_id: str, contact_id: str, request: Request) -> dict:
        """Detach a contact from this record (removes the link only — the contact
        record itself stays in the CRM)."""
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            await details_svc.unlink_contact(cfg, client, parent_id, contact_id)
            return {"status": "ok"}
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not remove the contact")

    @router.get("/peek/{entity}/{record_id}")
    async def peek(entity: str, record_id: str, request: Request) -> dict:
        """Pop-up detail for a linked contact / company / client on the Overview."""
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.peek(client, entity, record_id)
        except service.SessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load details")

    if cfg.list_status_accept:

        @router.post("/records/{parent_id}/accept")
        async def accept_record(parent_id: str, request: Request) -> dict:
            """The grid's accept action: Pending Acceptance → Assigned, written
            as the signed-in user. 400 (nothing written) when the engagement has
            already moved on — the frontend reloads the grid."""
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                result = await service.accept_engagement(
                    cfg, client, parent_id,
                    actor=user.get("name") or user.get("userName"),
                )
            except service.SessionError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not accept the engagement")
            await action_log.log_action(
                app=cfg.title, category=action_log.CAT_ASSIGNMENT,
                action=action_log.ACT_ENGAGEMENT_ACCEPTED,
                parent_type=cfg.parent_entity, parent_id=parent_id,
                summary=f"Engagement accepted: {result.get('from')} → {result.get('to')}.",
                actor_id=user["userId"], actor_name=user["name"], details=result,
            )
            return result

    if cfg.contributions_link:
        # The funder ledger (prds/funder-contributions-plan.md) — registered
        # ONLY on a domain with a contributions link (sponsor), the
        # accept-endpoint precedent. No DELETE: soft delete = status Cancelled
        # through the normal update.

        @router.get("/contributionfields")
        async def contribution_fields(request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return {
                    "fields": CONTRIBUTION_FIELDS,
                    "options": await service.contribution_field_options(client),
                    "required": await service.contribution_field_required(client),
                }
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load contribution field options")

        @router.get("/records/{parent_id}/contributions")
        async def list_contributions(parent_id: str, request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return await service.list_contributions(cfg, client, parent_id)
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load contributions")

        @router.post("/records/{parent_id}/contributions")
        async def create_contribution(
            parent_id: str, body: ContributionIn, request: Request
        ) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return await service.create_contribution(cfg, client, parent_id, body.changes)
            except service.SessionError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not save the contribution")

        @router.get("/contributions/{contribution_id}")
        async def contribution_detail(contribution_id: str, request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return await service.get_contribution(cfg, client, contribution_id)
            except service.SessionError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load the contribution")

        @router.put("/contributions/{contribution_id}")
        async def update_contribution(
            contribution_id: str, body: ContributionIn, request: Request
        ) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return await service.update_contribution(
                    cfg, client, contribution_id, body.changes
                )
            except service.SessionError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not save the contribution")

    if cfg.discussion_enabled:
        # Staff-internal Discussion pane (partner + sponsor) — an attributed,
        # append-only comment stream keyed by (parent entity, record id) in the
        # durable store. App-only: NEVER written to the CRM or shown to the
        # partner/funder. Registered ONLY on a discussion-enabled domain (the
        # contributions-endpoint precedent), so the mentor router never has it.

        @router.get("/records/{parent_id}/comments")
        async def list_comments(parent_id: str, request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            # Read the parent AS THE USER first — that is the ACL gate (a user who
            # can't read the record can't read its discussion).
            try:
                await client.get(cfg.parent_entity, parent_id, select="id")
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load record")
            store = _discussion_store(request)
            if store is None:
                raise HTTPException(status_code=503, detail="Discussion is not available.")
            comments = await store.list_record_comments(cfg.parent_entity, parent_id)
            return {"comments": comments}

        @router.post("/records/{parent_id}/comments")
        async def add_comment(parent_id: str, body: CommentIn, request: Request) -> dict:
            user = _require_user(request)
            text = (body.body or "").strip()
            if not text:
                raise HTTPException(status_code=422, detail="A comment can't be empty.")
            client = client_for(get_settings(), user)
            # ACL gate: the caller must be able to read the record it's about.
            try:
                await client.get(cfg.parent_entity, parent_id, select="id")
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load record")
            store = _discussion_store(request)
            if store is None:
                raise HTTPException(status_code=503, detail="Discussion is not available.")
            comment = await store.add_record_comment(
                cfg.parent_entity, parent_id,
                author=user["userName"],
                author_name=user.get("name") or user["userName"],
                body=text,
            )
            log.info(
                "discussion comment on %s/%s by %s", cfg.slug, parent_id, user["userName"]
            )
            return {"status": "ok", "comment": comment}

    @router.get("/sessions/{session_id}")
    async def session_detail(session_id: str, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.get_session(client, session_id)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load session")

    @router.post("/records/{parent_id}/sessions")
    async def create_session(parent_id: str, body: SessionIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        token = (body.submissionToken or "").strip()
        if not token:  # no token (older cached frontend) => no dedup, create as before
            return await _do_create_session(client, parent_id, body, user, request)
        key = f"{cfg.slug}:{user['userId']}:{parent_id}:{token}"
        lock = await _create_token_lock(key)
        # Held across the whole check-create-record section so a concurrent
        # duplicate submit waits here and then takes the first one's result.
        async with lock:
            now = time.monotonic()
            _prune_create_tokens(now)
            existing = _recent_creates.get(key)
            if existing is not None:
                session_id = existing[1]
                log.info(
                    "duplicate session create suppressed on %s/%s by %s "
                    "(token=%s, returning CSession/%s)",
                    cfg.parent_entity, parent_id, user["userName"], token, session_id,
                )
                try:
                    result = await service.get_session(client, session_id)
                except EspoError as exc:
                    raise _crm_failure(request, exc, "Could not load session")
                result["idempotent"] = True
                return result
            result = await _do_create_session(client, parent_id, body, user, request)
            if result.get("id"):
                _recent_creates[key] = (now, result["id"])
            return result

    async def _do_create_session(
        client, parent_id: str, body: SessionIn, user: dict, request: Request,
    ) -> dict:
        """The actual create (``cfg`` comes from the enclosing router)."""
        try:
            result = await service.create_session(
                cfg, client, parent_id, body.changes, body.attendees,
                owner_user_id=user["userId"], settings=get_settings(),
                skip_calendar=body.skipCalendar,
                skip_follow_up_invite=body.skipFollowUpInvite,
            )
        except service.SessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not create session")
        log.info(
            "session created on %s/%s by %s (fields: %s)",
            cfg.parent_entity, parent_id, user["userName"],
            ", ".join(sorted(body.changes)) or "-",
        )
        if result.get("id"):
            _label = (result.get("name") or "session").strip()
            _status = result.get("status")
            await action_log.log_action(
                app=cfg.title, category=action_log.CAT_SESSION,
                action=action_log.ACT_SESSION_RECORDED,
                parent_type=cfg.parent_entity, parent_id=parent_id,
                summary=f"Session recorded: {_label}"
                + (f" ({_status})." if _status else "."),
                actor_id=user["userId"], actor_name=user["name"],
                details={"sessionId": result.get("id"), "status": _status,
                         "sessionType": result.get("sessionType")},
            )
        _eng = result.get("engagement") or {}
        if _eng.get("activated"):
            await action_log.log_action(
                app=cfg.title, category=action_log.CAT_STATUS,
                action=action_log.ACT_ENGAGEMENT_ACTIVATED,
                parent_type=cfg.parent_entity, parent_id=parent_id,
                summary=f"Engagement activated: {_eng.get('from')} → {_eng.get('to')} "
                "(first completed session).",
                actor_id=user["userId"], actor_name=user["name"], details=_eng,
            )
        await _log_follow_up(result, user)
        return result

    async def _log_follow_up(result: dict, user: dict) -> None:
        """Action-history entry for a follow-up session the save auto-created
        (the Completed-with-next-date rule)."""
        fu = result.get("followUp") or {}
        if not fu.get("created") or not fu.get("parentId"):
            return
        await action_log.log_action(
            app=cfg.title, category=action_log.CAT_SESSION,
            action=action_log.ACT_SESSION_RECORDED,
            parent_type=cfg.parent_entity, parent_id=fu["parentId"],
            summary="Next session scheduled automatically from the completed "
            f"session's agreed date: {fu.get('name') or fu.get('id')}.",
            actor_id=user["userId"], actor_name=user["name"],
            details={"sessionId": fu.get("id"), "dateStart": fu.get("dateStart"),
                     "autoCreated": True},
        )

    @router.put("/sessions/{session_id}")
    async def update_session(session_id: str, body: SessionIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            result = await service.update_session(
                cfg, client, session_id, body.changes, body.attendees,
                user_id=user["userId"], settings=get_settings(),
                skip_follow_up_invite=body.skipFollowUpInvite,
            )
        except service.SessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save session")
        log.info(
            "session CSession/%s saved by %s (fields: %s)",
            session_id, user["userName"], ", ".join(sorted(body.changes)) or "-",
        )
        _eng = result.get("engagement") or {}
        _eng_id = result.get("engagementId") or result.get("parentId")
        if _eng.get("activated") and _eng_id:
            await action_log.log_action(
                app=cfg.title, category=action_log.CAT_STATUS,
                action=action_log.ACT_ENGAGEMENT_ACTIVATED,
                parent_type=cfg.parent_entity, parent_id=_eng_id,
                summary=f"Engagement activated: {_eng.get('from')} → {_eng.get('to')} "
                "(first completed session).",
                actor_id=user["userId"], actor_name=user["name"], details=_eng,
            )
        await _log_follow_up(result, user)
        return result

    if cfg.supports_comentor:

        @router.get("/mentors")
        async def mentors(request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return {"mentors": await service.mentor_options(client)}
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load mentors")

        @router.post("/records/{parent_id}/comentors")
        async def add_comentor(parent_id: str, body: CoMentorIn, request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                result = await service.add_comentor(
                    client, parent_id, body.mentorProfileId,
                    actor=user.get("name") or user.get("userName"),
                )
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not add co-mentor")
            await action_log.log_action(
                app=cfg.title, category=action_log.CAT_ASSIGNMENT,
                action=action_log.ACT_COMENTOR_ADDED,
                parent_type=cfg.parent_entity, parent_id=parent_id,
                summary="Co-mentor added.",
                actor_id=user["userId"], actor_name=user["name"],
                details={"mentorProfileId": body.mentorProfileId, **(result or {})},
            )
            # DOC-09: the co-mentor gains the engagement folder's Commenter
            # grant in the same action that grants the entitlement. Best-effort
            # — a failure never fails the add (nightly reconciliation backstop).
            await doc_grants.sync_record_grants_safe(
                get_settings(), cfg.parent_entity, parent_id
            )
            return result

        @router.delete("/records/{parent_id}/comentors/{mentor_profile_id}")
        async def remove_comentor(
            parent_id: str, mentor_profile_id: str, request: Request
        ) -> dict:
            """Detach a co-mentor (the additionalMentors relation only — the
            assigned mentor is managed in Client Administration)."""
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                result = await service.remove_comentor(
                    client, parent_id, mentor_profile_id,
                    actor=user.get("name") or user.get("userName"),
                )
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not remove the co-mentor")
            await action_log.log_action(
                app=cfg.title, category=action_log.CAT_ASSIGNMENT,
                action=action_log.ACT_COMENTOR_REMOVED,
                parent_type=cfg.parent_entity, parent_id=parent_id,
                summary="Co-mentor removed.",
                actor_id=user["userId"], actor_name=user["name"],
                details={"mentorProfileId": mentor_profile_id, **(result or {})},
            )
            # DOC-09: revocation rides the same action that ends the
            # entitlement (best-effort, reconciliation backstop).
            await doc_grants.sync_record_grants_safe(
                get_settings(), cfg.parent_entity, parent_id
            )
            return result

    # --- Communications tab (Gmail conversation integration) -----------------
    # Everything below 503s unless GMAIL_SYNC is enabled; the frontend keeps
    # its sample-data scaffold in that case (config.commsEnabled).

    def _comms_ready():
        """(settings, comms_store) — or a 503 when the integration is off."""
        settings = get_settings()
        if not settings.gmail_sync:
            raise HTTPException(status_code=503, detail="The email integration isn't enabled.")
        store = comms_service.get_store(settings)
        if store is None:
            raise HTTPException(
                status_code=503, detail="The email integration needs the database."
            )
        return settings, store

    def _api_client(settings):
        from core.espo import DryRunEspoClient, EspoClient

        if settings.espo_dry_run:
            return DryRunEspoClient()
        return EspoClient(
            settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
        )

    def _comms_error(exc: comms_service.CommsError) -> HTTPException:
        return HTTPException(status_code=400, detail=str(exc))

    @router.get("/records/{parent_id}/conversations")
    async def conversations(parent_id: str, request: Request) -> dict:
        user = _require_user(request)
        _, store = _comms_ready()
        client = client_for(get_settings(), user)
        try:
            rows = await comms_service.list_conversations(client, cfg.parent_entity, parent_id)
            # unread + awaiting-reply badges (best-effort decoration).
            await comms_service.enrich_conversation_rows(
                client, store, user["userName"], rows
            )
            return {"conversations": rows}
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load conversations")

    @router.get("/conversations/{conversation_id}")
    async def conversation_detail(
        conversation_id: str, request: Request, parentId: str = ""
    ) -> dict:
        user = _require_user(request)
        _, store = _comms_ready()
        client = client_for(get_settings(), user)
        try:
            # parentId (the open record) scopes the per-message attachment
            # chips — filings are per record, so the chips must be too.
            thread = await comms_service.get_conversation(
                client, conversation_id,
                store=store,
                parent_entity=cfg.parent_entity if parentId else None,
                parent_id=parentId or None,
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the conversation")
        # Opening the thread stamps it read for THIS user (unread badges).
        try:
            await store.mark_seen(user["userName"], conversation_id)
        except Exception as exc:  # noqa: BLE001 — a read stamp never blocks reading
            log.warning("mark_seen failed for %s: %s", user.get("userName"), exc)
        return thread

    @router.post("/records/{parent_id}/conversations/{conversation_id}/exclude")
    async def exclude_conversation(
        parent_id: str, conversation_id: str, request: Request
    ) -> dict:
        user = _require_user(request)
        settings, store = _comms_ready()
        try:
            # D5: the unlink runs as the signed-in user (their ACL, their name
            # in Espo history) — not the privileged API key.
            await comms_service.exclude_conversation(
                client_for(settings, user), store, cfg.parent_entity, parent_id,
                conversation_id, user.get("userName", ""),
            )
        except comms_service.CommsError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not hide the conversation")
        log.info(
            "conversation %s hidden from %s/%s by %s",
            conversation_id, cfg.parent_entity, parent_id, user.get("userName"),
        )
        return {"status": "ok"}

    @router.get("/communications/{communication_id}/original")
    async def communication_original(communication_id: str, request: Request) -> dict:
        """View original (§3.2): the complete message — real formatting,
        inline images — fetched on demand from the SOURCE mailbox under the
        service delegation. The stored CCommunication row is read first AS THE
        SIGNED-IN USER, so their CRM ACL is the gate (the same one that let
        them read the thread); every access is provenance-logged."""
        user = _require_user(request)
        settings, _ = _comms_ready()
        client = client_for(settings, user)
        try:
            return await comms_service.get_original(
                settings, client, communication_id,
                cid_base=(
                    f"/{cfg.slug}/api/communications/{communication_id}/original/cid"
                ),
                acting_user=user.get("userName", ""),
            )
        except comms_service.OriginalGoneError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except GmailError as exc:
            log.warning("original fetch failed (%s): %s", cfg.slug, exc)
            raise HTTPException(
                status_code=502,
                detail="Couldn't fetch the original from the mailbox — try again.",
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the original message")

    @router.get("/communications/{communication_id}/original/cid/{content_id}")
    async def communication_original_cid(
        communication_id: str, content_id: str, request: Request
    ) -> Response:
        """Inline-image subresource for the View original render (one ``cid:``
        part's bytes). Same ACL gate + provenance logging as the original."""
        user = _require_user(request)
        settings, _ = _comms_ready()
        client = client_for(settings, user)
        try:
            part = await comms_service.get_original_part(
                settings, client, communication_id, content_id,
                acting_user=user.get("userName", ""),
            )
        except comms_service.OriginalGoneError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except comms_service.CommsError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except GmailError as exc:
            log.warning("original cid fetch failed (%s): %s", cfg.slug, exc)
            raise HTTPException(
                status_code=502, detail="Couldn't fetch the image — try again."
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the image")
        return Response(
            content=part["data"],
            media_type=part["mime_type"],
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @router.get("/mailbox")
    async def mailbox(request: Request) -> dict:
        """The signed-in user's own CBM send-from address (their profile's
        ``cbmEmail`` — the same resolution the send path uses), shown as the
        compose dialog's From line. ``null`` when no linked profile / no CBM
        email; the send itself reports why."""
        user = _require_user(request)
        settings = get_settings()
        client = client_for(settings, user)
        try:
            box = await service.resolve_user_mailbox(client, user["userId"])
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not look up your mailbox")
        # sendEnabled feeds the shared quickmail widget (grid-page peeks —
        # no open record, so the record-scoped compose can't be used).
        # signature: the user's EspoCRM Preferences signature, seeded into the
        # compose body (best-effort — "" when unset/unreadable).
        return {
            "mailbox": box,
            "sendEnabled": bool(settings.gmail_sync and box),
            "signature": await comms_service.user_signature(client, user["userId"]),
        }

    @router.get("/mailsearch")
    async def mailsearch(q: str, request: Request) -> dict:
        user = _require_user(request)
        settings, _ = _comms_ready()
        client = client_for(settings, user)
        try:
            gmail = await comms_service.gmail_for_user(settings, client, user)
            return {"threads": await comms_service.search_mailbox(gmail, q)}
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except GmailError as exc:
            log.warning("mailsearch failed (%s): %s", cfg.slug, exc)
            raise HTTPException(status_code=502, detail="Couldn't reach the mailbox — try again.")
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not search the mailbox")

    @router.post("/records/{parent_id}/conversations/include")
    async def include_thread(parent_id: str, body: IncludeIn, request: Request) -> dict:
        user = _require_user(request)
        settings, store = _comms_ready()
        client = client_for(settings, user)
        try:
            gmail = await comms_service.gmail_for_user(settings, client, user)
            conv_id = await comms_service.include_thread(
                settings=settings, api_client=_api_client(settings), store=store,
                gmail=gmail, cfg=cfg, parent_id=parent_id,
                gmail_thread_id=body.gmailThreadId, user=user,
            )
            return {"status": "ok", "conversationId": conv_id}
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except GmailError as exc:
            log.warning("include failed (%s): %s", cfg.slug, exc)
            raise HTTPException(status_code=502, detail="Couldn't reach the mailbox — try again.")
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not add the conversation")

    async def _resolve_document_attachments(
        settings, client, user, parent_id: str, attachments: list[dict]
    ) -> list[dict]:
        """Turn ``{"documentId": …}`` chips (the record's Documents tab) into
        the local-upload shape at send time: the document's ORIGINAL bytes,
        fetched through the same record-scoped path as the Download action —
        a doc id never resolves through another record's route. Any failure
        raises CommsError so the send is BLOCKED, never sent incomplete
        (the ET-131 contract, extended to document attachments)."""
        if not any(a.get("documentId") for a in attachments):
            return attachments
        import base64 as b64

        if not settings.gdrive_docs:
            raise comms_service.CommsError(
                "Document attachments aren't available — the document "
                "integration isn't enabled."
            )
        dstore = docs_service.get_store(settings)
        if dstore is None:
            raise comms_service.CommsError(
                "Document attachments need the database — remove them and send."
            )
        drive = await docs_service.drive_for_user(settings, client, user)
        out: list[dict] = []
        for a in attachments:
            doc_id = (a.get("documentId") or "").strip()
            if not doc_id:
                out.append(a)
                continue
            name = a.get("filename") or "document"
            try:
                doc = await docs_service.fetch_document(
                    dstore, drive, cfg.parent_entity, parent_id, doc_id,
                    original=True,
                )
            except docs_service.DocsNotFound:
                raise comms_service.CommsError(
                    f"The attached document \"{name}\" isn't on this record "
                    "anymore — remove the attachment and send again."
                )
            except DriveError as exc:
                log.warning("document attachment fetch failed (%s): %s", cfg.slug, exc)
                raise comms_service.CommsError(
                    f"Couldn't fetch the document \"{name}\" from Google Drive — "
                    "the message was NOT sent. Remove the attachment or try again."
                )
            out.append({
                "filename": doc["filename"],
                "contentType": doc["mime_type"],
                "dataBase64": b64.b64encode(doc["data"]).decode("ascii"),
            })
        return out

    @router.post("/records/{parent_id}/messages")
    async def send_message(parent_id: str, body: SendIn, request: Request) -> dict:
        user = _require_user(request)
        settings, store = _comms_ready()
        client = client_for(settings, user)
        try:
            attachments = await _resolve_document_attachments(
                settings, client, user, parent_id, body.attachments
            )
            gmail = await comms_service.gmail_for_user(settings, client, user)
            result = await comms_service.send_message(
                settings=settings, api_client=_api_client(settings), store=store,
                gmail=gmail, cfg=cfg, parent_id=parent_id, user=user,
                to=body.to, cc=body.cc, bcc=body.bcc,
                subject=body.subject, body_html=body.body,
                reply_to_communication_id=body.replyToCommunicationId,
                allow_unknown_recipients=body.allowUnknownRecipients,
                user_client=client, attachments=attachments,
            )
            return {"status": "ok", **result}
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except GmailError as exc:
            log.warning("send failed (%s): %s", cfg.slug, exc)
            raise HTTPException(status_code=502, detail="Couldn't send the message — try again.")
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not send the message")

    # --- Email templates (ET) — EspoCRM renders, the app sends -------------
    # The picker lists what the ACTING USER may see (ET-100/101); parse
    # returns the rendered, editable draft (ET-110..112). Both need the Gmail
    # integration on — templates are only useful where sending works.

    @router.get("/emailtemplates")
    async def email_templates(request: Request, q: str = "") -> dict:
        user = _require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            return await comms_templates.list_templates(
                client, q=q, context=comms_templates.CONTEXT_BY_PARENT.get(cfg.parent_entity),
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load email templates")

    @router.post("/records/{parent_id}/emailtemplates/{template_id}/parse")
    async def email_template_parse(
        parent_id: str, template_id: str, body: TemplateParseIn, request: Request
    ) -> dict:
        user = _require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            # {CMentorProfile.*} — the most common template link — resolves
            # via prepare()'s related record: the record's own manager, else
            # the sender's linked profile.
            profile_id = await comms_templates.related_manager_profile(
                client, user_id=user["userId"],
                parent_entity=cfg.parent_entity, parent_id=parent_id,
                manager_link=cfg.parent_manager_link,
            )
            return await comms_templates.parse_template(
                client, template_id,
                parent_type=cfg.parent_entity, parent_id=parent_id,
                email_address=body.emailAddress or None,
                related_type="CMentorProfile" if profile_id else None,
                related_id=profile_id,
            )
        except EspoError as exc:
            # ET-114: non-destructive — the frontend leaves the draft untouched.
            raise _crm_failure(request, exc, "Could not apply the template")

    # (POST /emailwriteback — the ET-142 retry — registers via
    # register_quicksend below, shared with the record-less compose surface.)

    @router.get("/contactlookup")
    async def contact_lookup(email: str, request: Request) -> dict:
        """CRM-wide: does any contact already carry this email address?
        Drives the compose dialog's add-existing-vs-create branch."""
        user = _require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            return await comms_service.lookup_contact_by_email(client, email)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not look up the address")

    @router.get("/companies")
    async def companies(request: Request, q: str = "") -> dict:
        user = _require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            return {"companies": await comms_service.search_companies(client, q)}
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load companies")

    @router.post("/contacts/{contact_id}/addresses")
    async def add_contact_address(contact_id: str, body: AddressIn, request: Request) -> dict:
        user = _require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            await comms_service.add_contact_address(client, contact_id, body.address)
            return {"status": "ok"}
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not update the contact")

    # --- Documents tab (Google Drive document management — DOC-MGMT) ----------
    # Everything below 503s unless GDRIVE_DOCS is enabled; the frontend shows a
    # "coming soon" placeholder in that case (config.docsEnabled). The list
    # renders from the app_document metadata table only (no Drive call, DOC-02);
    # uploads go to the shared drive as the signed-in user (DOC-01). Phase 2:
    # in-app viewing streams through /content (DOC-03/04, browser-cached via
    # modifiedTime-versioned URLs — DOC-06) and /refresh lazily re-syncs
    # modifiedTimes on tab open (DOC-02 completion).

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

    @router.get("/records/{parent_id}/documents")
    async def documents(
        parent_id: str, request: Request, includeArchived: bool = False
    ) -> dict:
        user = _require_user(request)
        settings, store = _docs_ready()
        # Per-record ACL read AS THE USER (review docs-D6): upload/content/
        # refresh all gate on it — without it here, document METADATA
        # (filenames, uploaders, Drive links) was enumerable across ACL
        # boundaries by anyone past the team gate.
        client = client_for(settings, user)
        try:
            await client.get(cfg.parent_entity, parent_id, select="name")
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load documents")
        rows = await docs_service.list_documents(
            store, cfg.parent_entity, parent_id, include_archived=includeArchived
        )
        return {
            "documents": rows,
            "docTypes": settings.gdrive_doc_types_list,
            "maxFileMb": settings.gdrive_max_file_mb,
        }

    @router.post("/records/{parent_id}/documents")
    async def upload_document(
        parent_id: str, request: Request, filename: str = "", docType: str = ""
    ) -> dict:
        """Upload one file (raw request body; filename/docType as query params,
        MIME from the Content-Type header) to the record's Drive folder, then
        record it in the metadata table (rollback on failure — DOC-01)."""
        user = _require_user(request)
        settings, store = _docs_ready()
        client = client_for(settings, user)
        data = await request.body()
        # Receipt log BEFORE any processing: an upload that dies later is
        # diagnosable from the run logs (who, what, how big).
        log.info(
            "document upload received (%s %s): %r %d bytes as %s",
            cfg.slug, parent_id, filename, len(data), user.get("userName"),
        )
        try:
            # Read the parent as the user: their ACL must allow the record, and
            # its name feeds the human-readable folder. Engagement anchors also
            # resolve their parent CLIENT at upload time (PRD v1.2 D-07 — the
            # engagement folder nests inside the client's folder), reusing the
            # same company link + client-profile fallback the rest of the tools
            # use (fill_company_fallback). Unresolvable client => no nesting,
            # never a blocked upload (folders are for human browsing only).
            select, client_id, client_name = "name", None, None
            nested = cfg.parent_entity == "CEngagement" and cfg.company_fallback
            if nested:
                own_id, own_name, via_id = cfg.company_fallback[:3]
                select = f"name,{own_id},{own_name},{via_id}"
            parent = await client.get(cfg.parent_entity, parent_id, select=select)
            if nested:
                await service.fill_company_fallback(cfg, client, [parent])
                client_id = parent.get(own_id) or None
                client_name = parent.get(own_name) or ""
            drive = await docs_service.drive_for_user(settings, client, user)
            row = await docs_service.upload_document(
                settings, store, drive,
                entity_type=cfg.parent_entity,
                record_id=parent_id,
                record_name=parent.get("name") or "",
                filename=filename,
                mime_type=request.headers.get("content-type", ""),
                doc_type=docType,
                data=data,
                client_id=client_id,
                client_name=client_name,
            )
            # DOC-08 (CRM folder-link write-back, self-healing on every upload)
            # + DOC-09 (folder-creation grants). Best-effort by contract —
            # never fails the upload.
            await docs_service.post_upload_hooks(
                settings, drive, cfg.parent_entity, parent_id, row
            )
            return {"status": "ok", "document": row}
        except docs_service.DocsError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except DriveError as exc:
            log.warning("document upload failed (%s): %s", cfg.slug, exc)
            raise HTTPException(
                status_code=502, detail="Couldn't reach Google Drive — try again."
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not upload the document")

    @router.get("/records/{parent_id}/documents/{doc_id}/content")
    async def document_content(
        parent_id: str, doc_id: str, request: Request, original: bool = False
    ) -> Response:
        """DOC-03: stream the document's bytes through the app. The parent
        record is read first AS THE USER (their CRM ACL gates viewing, exactly
        like the upload). Default = viewing: Google-native AND Office formats
        arrive as PDF (DOC-04 / convert-on-view). ``?original=true`` = the
        Download action: the stored file's exact bytes as an attachment, so
        the user opens it in their locally installed application. Served
        immutable — the frontend versions the URL by modifiedTime, so the
        browser is the cache (DOC-06)."""
        user = _require_user(request)
        settings, store = _docs_ready()
        client = client_for(settings, user)
        try:
            await client.get(cfg.parent_entity, parent_id, select="name")
            drive = await docs_service.drive_for_user(settings, client, user)
            if original:
                # Stream the raw bytes (P2): large originals no longer buffer
                # whole in memory. Google-native files (no native bytes) fall
                # through to the buffered export path below.
                streamed = await docs_service.stream_original(
                    store, drive, cfg.parent_entity, parent_id, doc_id
                )
                if streamed is not None:
                    return StreamingResponse(
                        streamed["stream"],
                        media_type=streamed["mime_type"],
                        headers=docs_service.content_headers(
                            streamed["filename"], attachment=True
                        ),
                    )
            doc = await docs_service.fetch_document(
                store, drive, cfg.parent_entity, parent_id, doc_id,
                original=original,
            )
        except docs_service.DocsNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except docs_service.DocsError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except DriveError as exc:
            log.warning("document fetch failed (%s): %s", cfg.slug, exc)
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

    @router.post("/records/{parent_id}/documents/refresh")
    async def refresh_documents(
        parent_id: str, request: Request, includeArchived: bool = False
    ) -> dict:
        """DOC-02 completion — lazy modifiedTime refresh: one files.list scoped
        to the record folder re-syncs each row's modifiedTime; changed rows come
        back flagged ``changedInDrive``. The frontend fires this AFTER rendering
        the list from metadata, so it never blocks the initial render."""
        user = _require_user(request)
        settings, store = _docs_ready()
        client = client_for(settings, user)
        try:
            await client.get(cfg.parent_entity, parent_id, select="name")
            drive = await docs_service.drive_for_user(settings, client, user)
            rows = await docs_service.refresh_documents(
                store, drive, cfg.parent_entity, parent_id,
                include_archived=includeArchived,
            )
            return {
                "documents": rows,
                "docTypes": settings.gdrive_doc_types_list,
                "maxFileMb": settings.gdrive_max_file_mb,
            }
        except docs_service.DocsError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except DriveError as exc:
            log.warning("document refresh failed (%s): %s", cfg.slug, exc)
            raise HTTPException(
                status_code=502, detail="Couldn't reach Google Drive — try again."
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not refresh the documents")

    async def _document_lifecycle(
        parent_id: str, doc_id: str, request: Request, *, archive: bool
    ) -> dict:
        """DOC-07 shared handler: the parent record is read AS THE USER (their
        CRM ACL gates the action, like the upload); the Drive move + status
        flip run in docs.service (move first, flip after, rollback on a
        mid-failure — Doug's ruling 2026-07-17)."""
        user = _require_user(request)
        settings, store = _docs_ready()
        client = client_for(settings, user)
        try:
            await client.get(cfg.parent_entity, parent_id, select="name")
            drive = await docs_service.drive_for_user(settings, client, user)
            fn = (
                docs_service.archive_document if archive
                else docs_service.restore_document
            )
            row = await fn(store, drive, cfg.parent_entity, parent_id, doc_id)
            return {"status": "ok", "document": row}
        except docs_service.DocsNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except docs_service.DocsError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except DriveError as exc:
            log.warning(
                "document %s failed (%s): %s",
                "archive" if archive else "restore", cfg.slug, exc,
            )
            raise HTTPException(
                status_code=502, detail="Couldn't reach Google Drive — try again."
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not update the document")

    @router.post("/records/{parent_id}/documents/{doc_id}/archive")
    async def archive_document(parent_id: str, doc_id: str, request: Request) -> dict:
        """DOC-07: soft-delete — the file moves to the record folder's
        /_Archived subfolder and the row leaves the default list."""
        return await _document_lifecycle(parent_id, doc_id, request, archive=True)

    @router.post("/records/{parent_id}/documents/{doc_id}/restore")
    async def restore_document(parent_id: str, doc_id: str, request: Request) -> dict:
        """DOC-07: reverse of archive — file back to the record folder,
        status back to active."""
        return await _document_lifecycle(parent_id, doc_id, request, archive=False)

    # POST /sendmail — the record-less quick send behind email links shown
    # OUTSIDE an open record (grid-page peeks). This router already serves its
    # own /mailbox above. See comms/quicksend.py.
    from comms.quicksend import register_quicksend

    register_quicksend(
        router, _require_user, client_for, _crm_failure, include_mailbox=False
    )

    return router
