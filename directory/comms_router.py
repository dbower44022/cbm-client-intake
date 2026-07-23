"""Contact-scoped Communications endpoints for the View Contact page.

Registered onto the Contacts directory router (``/directory/contacts/api``)
when the kind's :class:`directory.config.DirectoryConfig` has ``contact_page``
set. The machinery is the session tools' Communications tab parameterized to
ONE Contact instead of a parent record (engagement/partner/sponsor):

- the conversation list reads the Contact-side ``cConversations`` reverse link
  and is filtered server-side to conversations the SIGNED-IN USER is a
  participant of (Doug's ruling 2026-07-23: the page shows *my* communications
  with the contact — manager roles read CConversation broadly, so this filter
  is the privacy boundary and lives here, never in the frontend);
- compose/reply/include scope through a Contact :class:`comms.crm.RecordRef`
  (``comms.service.contact_ref``): the contact's own addresses are the
  known-recipient allowlist, and the write-through links the conversation to
  the contact only — no parent record;
- exclude/include overrides key off ``("Contact", contact_id)``.

Everything 503s unless GMAIL_SYNC is on (the frontend shows a readable notice
when ``commsEnabled`` is false). All reads/writes run as the logged-in user.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from assignments.espo_user import client_for
from comms import service as comms_service
from comms import templates as comms_templates
from core import action_log
from core.config import get_settings
from core.espo import EspoError
from core.gmail import GmailError
from sessions import service as sessions_service

from .config import DirectoryConfig

log = logging.getLogger("cbm_intake.directory")


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
    # contact's own (the server refuses otherwise).
    allowUnknownRecipients: bool = False
    # Each: {"espoId": …} (a template-attachment chip) or
    # {"filename","contentType","dataBase64"} (a local upload). The record
    # tools' {"documentId": …} chips are NOT accepted here — the contact page
    # has no record Documents tab.
    attachments: list[dict] = []


class TemplateParseIn(BaseModel):
    emailAddress: str = ""


class AddressIn(BaseModel):
    address: str


def register_contact_comms(
    router,
    cfg: DirectoryConfig,
    require_user: Callable[[Request], dict],
    crm_failure: Callable[[Request, EspoError, str], HTTPException],
) -> None:
    """Mount the View Contact page's Communications endpoints on ``router``."""

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

    async def _user_mailbox(client, user: dict) -> Optional[str]:
        """The signed-in user's own CBM mailbox — the only-mine filter key."""
        return await sessions_service.resolve_user_mailbox(client, user["userId"])

    _NO_MAILBOX_NOTICE = (
        "Your login isn't linked to a CBM mailbox, so your conversations with "
        "this contact can't be shown. Ask CBM staff to link your mentor "
        "profile and CBM email address."
    )

    @router.get("/records/{contact_id}/conversations")
    async def conversations(contact_id: str, request: Request) -> dict:
        user = require_user(request)
        _, store = _comms_ready()
        client = client_for(get_settings(), user)
        try:
            mailbox = await _user_mailbox(client, user)
            if not mailbox:
                return {"conversations": [], "notice": _NO_MAILBOX_NOTICE}
            from comms import crm as comms_crm

            rows = [
                r
                for r in await comms_service.list_contact_conversations(client, contact_id)
                if comms_crm.participants_contain(r.get("participants") or "", mailbox)
            ]
            await comms_service.enrich_conversation_rows(
                client, store, user["userName"], rows
            )
            return {"conversations": rows, "mailbox": mailbox}
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not load conversations")

    @router.get("/conversations/{conversation_id}")
    async def conversation_detail(conversation_id: str, request: Request) -> dict:
        user = require_user(request)
        _, store = _comms_ready()
        client = client_for(get_settings(), user)
        try:
            # The only-mine ruling holds on direct thread opens too: the user
            # must be a participant of the conversation they open here.
            from comms import crm as comms_crm

            mailbox = await _user_mailbox(client, user)
            conv = await client.get(
                comms_crm.CONVERSATION, conversation_id, select="participants"
            )
            if not mailbox or not comms_crm.participants_contain(
                conv.get("participants") or "", mailbox
            ):
                raise HTTPException(
                    status_code=404, detail="That conversation isn't yours to view here."
                )
            # No parent-record scope: attachment chips are per record and don't
            # apply on the contact page (the myemail precedent).
            thread = await comms_service.get_conversation(client, conversation_id)
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not load the conversation")
        try:
            await store.mark_seen(user["userName"], conversation_id)
        except Exception as exc:  # noqa: BLE001 — a read stamp never blocks reading
            log.warning("mark_seen failed for %s: %s", user.get("userName"), exc)
        return thread

    @router.post("/records/{contact_id}/conversations/{conversation_id}/exclude")
    async def exclude_conversation(
        contact_id: str, conversation_id: str, request: Request
    ) -> dict:
        user = require_user(request)
        settings, store = _comms_ready()
        try:
            # D5 posture: the unlink runs as the signed-in user (their ACL,
            # their name in Espo history).
            await comms_service.exclude_conversation(
                client_for(settings, user), store, "Contact", contact_id,
                conversation_id, user.get("userName", ""),
            )
        except comms_service.CommsError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not remove the conversation")
        log.info(
            "conversation %s removed from Contact/%s by %s",
            conversation_id, contact_id, user.get("userName"),
        )
        await action_log.log_action(
            app=f"{cfg.title} directory", category=action_log.CAT_COMMUNICATION,
            action=action_log.ACT_CONVERSATION_REMOVED,
            parent_type="Contact", parent_id=contact_id,
            summary="Conversation removed from the contact.",
            actor_id=user["userId"], actor_name=user["name"],
            details={"conversationId": conversation_id},
        )
        return {"status": "ok"}

    @router.get("/mailsearch")
    async def mailsearch(q: str, request: Request) -> dict:
        user = require_user(request)
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
            raise crm_failure(request, exc, "Could not search the mailbox")

    @router.post("/records/{contact_id}/conversations/include")
    async def include_thread(contact_id: str, body: IncludeIn, request: Request) -> dict:
        user = require_user(request)
        settings, store = _comms_ready()
        client = client_for(settings, user)
        try:
            api_client = _api_client(settings)
            ref = await comms_service.contact_ref(api_client, contact_id)
            gmail = await comms_service.gmail_for_user(settings, client, user)
            conv_id = await comms_service.include_thread(
                settings=settings, api_client=api_client, store=store,
                gmail=gmail, gmail_thread_id=body.gmailThreadId, user=user,
                ref=ref,
            )
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except GmailError as exc:
            log.warning("include failed (%s): %s", cfg.slug, exc)
            raise HTTPException(status_code=502, detail="Couldn't reach the mailbox — try again.")
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not add the conversation")
        await action_log.log_action(
            app=f"{cfg.title} directory", category=action_log.CAT_COMMUNICATION,
            action=action_log.ACT_CONVERSATION_LINKED,
            parent_type="Contact", parent_id=contact_id,
            summary="Email thread attached to the contact.",
            actor_id=user["userId"], actor_name=user["name"],
            details={"gmailThreadId": body.gmailThreadId, "conversationId": conv_id},
        )
        return {"status": "ok", "conversationId": conv_id}

    @router.post("/records/{contact_id}/messages")
    async def send_message(contact_id: str, body: SendIn, request: Request) -> dict:
        user = require_user(request)
        settings, store = _comms_ready()
        client = client_for(settings, user)
        try:
            if any(a.get("documentId") for a in body.attachments):
                raise comms_service.CommsError(
                    "Document attachments are only available on a record's "
                    "Communications tab — attach the file directly instead."
                )
            api_client = _api_client(settings)
            ref = await comms_service.contact_ref(api_client, contact_id)
            gmail = await comms_service.gmail_for_user(settings, client, user)
            result = await comms_service.send_message(
                settings=settings, api_client=api_client, store=store,
                gmail=gmail, user=user, ref=ref,
                to=body.to, cc=body.cc, bcc=body.bcc,
                subject=body.subject, body_html=body.body,
                reply_to_communication_id=body.replyToCommunicationId,
                allow_unknown_recipients=body.allowUnknownRecipients,
                user_client=client, attachments=body.attachments,
            )
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except GmailError as exc:
            log.warning("send failed (%s): %s", cfg.slug, exc)
            raise HTTPException(status_code=502, detail="Couldn't send the message — try again.")
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not send the message")
        await action_log.log_action(
            app=f"{cfg.title} directory", category=action_log.CAT_COMMUNICATION,
            action=action_log.ACT_EMAIL_SENT,
            parent_type="Contact", parent_id=contact_id,
            summary="Email sent to the contact.",
            actor_id=user["userId"], actor_name=user["name"],
            details={"subject": body.subject},
        )
        return {"status": "ok", **result}

    # (GET /emailtemplates, GET /mailbox, POST /emailwriteback already register
    # via register_quicksend on this router — record-less list, per-user
    # mailbox + signature, ET-142 retry. Only the parse below is contact-aware:
    # it feeds the contact as {Parent.*}/its own type into the render context.)

    @router.post("/records/{contact_id}/emailtemplates/{template_id}/parse")
    async def email_template_parse(
        contact_id: str, template_id: str, body: TemplateParseIn, request: Request
    ) -> dict:
        user = require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            # {CMentorProfile.*} resolves via the SENDER's own linked profile
            # (a contact has no manager link — the quick-compose posture).
            profile_id = await comms_templates.related_manager_profile(
                client, user_id=user["userId"],
            )
            return await comms_templates.parse_template(
                client, template_id,
                parent_type="Contact", parent_id=contact_id,
                email_address=body.emailAddress or None,
                related_type="CMentorProfile" if profile_id else None,
                related_id=profile_id,
            )
        except EspoError as exc:
            # ET-114: non-destructive — the frontend leaves the draft untouched.
            raise crm_failure(request, exc, "Could not apply the template")

    @router.get("/communications/{communication_id}/original")
    async def communication_original(communication_id: str, request: Request) -> dict:
        user = require_user(request)
        settings, _ = _comms_ready()
        client = client_for(settings, user)
        try:
            return await comms_service.get_original(
                settings, client, communication_id,
                cid_base=(
                    f"/directory/{cfg.slug}/api/communications/"
                    f"{communication_id}/original/cid"
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
            raise crm_failure(request, exc, "Could not load the original message")

    @router.get("/communications/{communication_id}/original/cid/{content_id}")
    async def communication_original_cid(
        communication_id: str, content_id: str, request: Request
    ) -> Response:
        user = require_user(request)
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
            raise crm_failure(request, exc, "Could not load the image")
        return Response(
            content=part["data"],
            media_type=part["mime_type"],
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @router.get("/contactlookup")
    async def contact_lookup(email: str, request: Request) -> dict:
        """CRM-wide: does any contact already carry this email address? Drives
        the compose dialog's unknown-recipient panel."""
        user = require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            return await comms_service.lookup_contact_by_email(client, email)
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not look up the address")

    @router.post("/contacts/{contact_id}/addresses")
    async def add_contact_address(contact_id: str, body: AddressIn, request: Request) -> dict:
        user = require_user(request)
        _comms_ready()
        client = client_for(get_settings(), user)
        try:
            await comms_service.add_contact_address(client, contact_id, body.address)
        except comms_service.CommsError as exc:
            raise _comms_error(exc)
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not update the contact")
        await action_log.log_action(
            app=f"{cfg.title} directory", category=action_log.CAT_COMMUNICATION,
            action=action_log.ACT_CONTACT_EMAIL_ADDED,
            parent_type="Contact", parent_id=contact_id,
            summary="Email address added to the contact.",
            actor_id=user["userId"], actor_name=user["name"],
            details={"address": body.address},
        )
        return {"status": "ok"}
