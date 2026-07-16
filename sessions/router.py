"""FastAPI routes for a Session Management domain (``/{slug}/api``).

:func:`make_router` builds one router per domain from a
:class:`sessions.config.DomainConfig`. All three share this code; only the
config differs. Uses the shared staff session (sign in once at the portal),
gated per request to the domain's team (admins always pass). All reads/writes
run as the logged-in user, so EspoCRM enforces their ACL.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from assignments.auth import clear_session, current_user, is_member, session_expired
from assignments.espo_user import client_for
from comms import service as comms_service
from comms import templates as comms_templates
from core.config import get_settings
from core.espo import EspoError, forbidden_hint, validation_message
from core.gdrive import DriveError
from core.gmail import GmailError
from docs import service as docs_service

from . import details as details_svc
from . import service
from .config import DomainConfig

log = logging.getLogger("cbm_intake.sessions")


class SessionIn(BaseModel):
    changes: dict = {}
    # Contact ids for the session's attendees. None => leave attendees unchanged
    # (on edit); [] => clear them. Sent by the frontend attendee picker.
    attendees: Optional[list[str]] = None
    # True = the user declined the automatic calendar invite in the pre-save
    # prompt (new Scheduled sessions only) — save the session, skip the event.
    skipCalendar: bool = False


class CoMentorIn(BaseModel):
    mentorProfileId: str


class DetailsSaveIn(BaseModel):
    changes: dict = {}


class IncludeIn(BaseModel):
    gmailThreadId: str


class SendIn(BaseModel):
    to: list[str] = []
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
        log.warning("%s (%s): %s", message, cfg.slug, exc)
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
            "contactKey": cfg.list_contact_key,
            "companyKey": cfg.list_company_key,
            "emptyMessage": cfg.empty_message,
            "noProfileMessage": NO_PROFILE_MESSAGE,
            "detailTabs": COMMON_DETAIL_TABS,
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
        }

    @router.post("/logout")
    async def logout(request: Request) -> dict:
        clear_session(request)
        return {"status": "ok"}

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

    @router.get("/records/{parent_id}")
    async def record_detail(parent_id: str, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.get_detail(cfg, client, parent_id)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load record")

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

    @router.put("/details/{entity}/{record_id}")
    async def save_details(entity: str, record_id: str, body: DetailsSaveIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await details_svc.save_details(client, entity, record_id, body.changes)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save details")

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
        try:
            return await service.create_session(
                cfg, client, parent_id, body.changes, body.attendees,
                owner_user_id=user["userId"], settings=get_settings(),
                skip_calendar=body.skipCalendar,
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not create session")

    @router.put("/sessions/{session_id}")
    async def update_session(session_id: str, body: SessionIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.update_session(
                cfg, client, session_id, body.changes, body.attendees,
                user_id=user["userId"], settings=get_settings(),
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save session")

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
                return await service.add_comentor(client, parent_id, body.mentorProfileId)
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not add co-mentor")

        @router.delete("/records/{parent_id}/comentors/{mentor_profile_id}")
        async def remove_comentor(
            parent_id: str, mentor_profile_id: str, request: Request
        ) -> dict:
            """Detach a co-mentor (the additionalMentors relation only — the
            assigned mentor is managed in Client Administration)."""
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return await service.remove_comentor(client, parent_id, mentor_profile_id)
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not remove the co-mentor")

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
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            rows = await comms_service.list_conversations(client, cfg.parent_entity, parent_id)
            return {"conversations": rows}
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load conversations")

    @router.get("/conversations/{conversation_id}")
    async def conversation_detail(conversation_id: str, request: Request) -> dict:
        user = _require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            return await comms_service.get_conversation(client, conversation_id)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the conversation")

    @router.post("/records/{parent_id}/conversations/{conversation_id}/exclude")
    async def exclude_conversation(
        parent_id: str, conversation_id: str, request: Request
    ) -> dict:
        user = _require_user(request)
        settings, store = _comms_ready()
        await comms_service.exclude_conversation(
            _api_client(settings), store, cfg.parent_entity, parent_id,
            conversation_id, user.get("userName", ""),
        )
        return {"status": "ok"}

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
        return {"mailbox": box, "sendEnabled": bool(settings.gmail_sync and box)}

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

    @router.post("/records/{parent_id}/messages")
    async def send_message(parent_id: str, body: SendIn, request: Request) -> dict:
        user = _require_user(request)
        settings, store = _comms_ready()
        client = client_for(settings, user)
        try:
            gmail = await comms_service.gmail_for_user(settings, client, user)
            result = await comms_service.send_message(
                settings=settings, api_client=_api_client(settings), store=store,
                gmail=gmail, cfg=cfg, parent_id=parent_id, user=user,
                to=body.to, subject=body.subject, body_html=body.body,
                reply_to_communication_id=body.replyToCommunicationId,
                allow_unknown_recipients=body.allowUnknownRecipients,
                user_client=client, attachments=body.attachments,
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
            return await comms_templates.parse_template(
                client, template_id,
                parent_type=cfg.parent_entity, parent_id=parent_id,
                email_address=body.emailAddress or None,
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

    # --- Documents tab (Google Drive document management — DOC-MGMT Phase 1) --
    # Everything below 503s unless GDRIVE_DOCS is enabled; the frontend shows a
    # "coming soon" placeholder in that case (config.docsEnabled). The list
    # renders from the app_document metadata table only (no Drive call, DOC-02);
    # uploads go to the shared drive as the signed-in user (DOC-01).

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
    async def documents(parent_id: str, request: Request) -> dict:
        _require_user(request)
        settings, store = _docs_ready()
        rows = await docs_service.list_documents(store, cfg.parent_entity, parent_id)
        return {"documents": rows, "docTypes": settings.gdrive_doc_types_list}

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

    # POST /sendmail — the record-less quick send behind email links shown
    # OUTSIDE an open record (grid-page peeks). This router already serves its
    # own /mailbox above. See comms/quicksend.py.
    from comms.quicksend import register_quicksend

    register_quicksend(
        router, _require_user, client_for, _crm_failure, include_mailbox=False
    )

    return router
