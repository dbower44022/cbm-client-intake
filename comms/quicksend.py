"""Quick-send email endpoints shared by the staff tools.

Every email address the staff UIs display is a compose link (Doug's ruling
2026-07-16: no more bare ``mailto:`` — a shown address opens the app's own
compose dialog). The session tools already have the full record-scoped
compose; Client Administration and Mentor Administration get this lightweight
pair instead, backing ``frontend/shared/quickmail.js``:

- ``GET  <app>/api/mailbox``  — who a message would go out as (the signed-in
  user's ``CMentorProfile.cbmEmail``) and whether sending is available at all.
  Never errors for "can't send" — the widget falls back to ``mailto:``.
- ``POST <app>/api/sendmail`` — send To/Subject/Message as that mailbox via
  the same delegated-Gmail stack the session tools use. No record linking —
  the regular Gmail sync ingests the sent copy when it matches a record the
  sender manages, exactly like mail sent from Gmail itself.

Both run per-request behind the host router's own team gate (the passed
``require_user``), acting as the signed-in user.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core.config import get_settings
from core.espo import EspoError
from core.gmail import GmailError

from . import service as comms_service
from . import templates as comms_templates

log = logging.getLogger("cbm_intake.comms.quicksend")


class QuickSendIn(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    # {"espoId": …} template chips / {"filename","contentType","dataBase64"}
    # local uploads — comms.service.resolve_attachments.
    attachments: list[dict] = Field(default_factory=list)
    # Reply threading (Submission Admin follow-ups, 2026-07-19): keeps the
    # send on the original Gmail thread + RFC chain. All optional — absent
    # means a fresh message, the pre-existing behavior.
    threadId: str | None = None
    inReplyTo: str = ""
    references: str = ""
    # /ops only (v0.110.0): the submission this compose belongs to — the
    # after_send hook anchors the sent message's Gmail thread to it. Ignored
    # by routers registered without an after_send hook.
    submissionId: str | None = None


class QuickParseIn(BaseModel):
    emailAddress: str = ""


class QuickWriteBackIn(BaseModel):
    subject: str = ""
    bodyHtml: str = ""
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    parentType: str | None = None
    parentId: str | None = None
    messageId: str = ""


def register_quicksend(
    router: Any,
    require_user: Callable[[Request], dict],
    client_for: Callable[..., Any],
    crm_failure: Callable[..., HTTPException],
    include_mailbox: bool = True,
    shared_mailbox: Callable[[Any], tuple[str, str] | None] | None = None,
    after_send: Callable[..., Any] | None = None,
) -> None:
    """Attach the quick-send endpoints to a staff app's router.

    ``include_mailbox=False`` for routers that already serve their own
    ``GET /mailbox`` (the session tools) — they get only ``POST /sendmail``.

    ``shared_mailbox(settings) -> (mailbox, display_name) | None`` makes the
    router send (and report on ``GET /mailbox``) as a SHARED mailbox instead
    of the signed-in user's own — /ops speaks as info@cbmentors.org with the
    generic "CBM Info" name (Doug's ruling 2026-07-19). Returning None falls
    back to the per-user behavior, so a deploy without OPS_MAILBOX keeps
    working. The shared identity deliberately seeds NO personal signature.

    ``after_send(request, body, result)`` (async, best-effort) runs after a
    successful send — /ops uses it to anchor the sent message's Gmail thread
    to ``body.submissionId``. A hook failure never fails the send response.
    """

    def _sending_on() -> Any:
        settings = get_settings()
        if not settings.gmail_sync:
            raise HTTPException(
                status_code=503, detail="Email sending isn't enabled on this deployment."
            )
        return settings

    def _shared(settings: Any) -> tuple[str, str] | None:
        return shared_mailbox(settings) if shared_mailbox else None

    @router.post("/sendmail")
    async def quick_send(body: QuickSendIn, request: Request) -> dict:
        user = require_user(request)
        settings = _sending_on()
        client = client_for(settings, user)
        try:
            shared = _shared(settings)
            if shared:
                gmail = await comms_service.gmail_for_shared_mailbox(settings, shared[0])
                sender_name = shared[1]
            else:
                gmail = await comms_service.gmail_for_user(settings, client, user)
                sender_name = user.get("name") or ""
            result = await comms_service.send_quick_message(
                gmail=gmail, to=body.to, cc=body.cc, bcc=body.bcc,
                subject=body.subject, body_html=body.body,
                sender_name=sender_name,
                user_client=client, attachments=body.attachments,
                thread_id=body.threadId, in_reply_to=body.inReplyTo,
                references=body.references,
            )
            if after_send is not None:
                try:
                    await after_send(request, body, result)
                except Exception as exc:  # noqa: BLE001 — the message is out;
                    # anchoring is bookkeeping and must never fail the response.
                    log.warning("after-send hook failed: %s", exc)
            return {"status": "ok", **result}
        except comms_service.CommsError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except GmailError as exc:
            log.warning("quick send failed for %s: %s", user.get("userName"), exc)
            raise HTTPException(
                status_code=502, detail="Couldn't send the message — try again."
            )
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not send the message")

    # --- Email templates (ET) on the quick-compose surface ------------------
    # No record context: {Person.*} resolves from the recipient address the
    # widget passes (verified on crm-test — see comms/templates.py). The
    # record-less parse + write-back register on EVERY router (the widget
    # lives on grid pages of the session tools too); GET /emailtemplates only
    # where the router doesn't already serve its own context-filtered list —
    # the same split as /mailbox.

    if include_mailbox:
        @router.get("/emailtemplates")
        async def quick_email_templates(request: Request, q: str = "") -> dict:
            user = require_user(request)
            settings = _sending_on()
            client = client_for(settings, user)
            try:
                return await comms_templates.list_templates(client, q=q)
            except EspoError as exc:
                raise crm_failure(request, exc, "Could not load email templates")

    @router.post("/emailtemplates/{template_id}/parse")
    async def quick_email_template_parse(
        template_id: str, body: QuickParseIn, request: Request
    ) -> dict:
        user = require_user(request)
        settings = _sending_on()
        client = client_for(settings, user)
        try:
            # Record-less: {CMentorProfile.*} resolves to the SENDER's own
            # linked profile.
            profile_id = await comms_templates.related_manager_profile(
                client, user_id=user["userId"],
            )
            return await comms_templates.parse_template(
                client, template_id, email_address=body.emailAddress or None,
                related_type="CMentorProfile" if profile_id else None,
                related_id=profile_id,
            )
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not apply the template")

    @router.post("/emailwriteback")
    async def quick_email_write_back(body: QuickWriteBackIn, request: Request) -> dict:
        """Retry a failed CRM Email record after a successful send (ET-142)."""
        user = require_user(request)
        settings = _sending_on()
        client = client_for(settings, user)
        from sessions.service import resolve_user_mailbox  # avoid import cycle

        try:
            shared = _shared(settings)
            if shared:
                mailbox = shared[0]
            else:
                mailbox = await resolve_user_mailbox(client, user["userId"])
            email_id = await comms_service.write_back_email(
                client, subject=body.subject, body_html=body.bodyHtml,
                sender=mailbox or "", to=body.to, cc=body.cc, bcc=body.bcc,
                parent_type=body.parentType, parent_id=body.parentId,
                message_id=body.messageId,
            )
            return {"status": "ok", "emailId": email_id}
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not record the email in the CRM")

    if not include_mailbox:
        return

    @router.get("/mailbox")
    async def quick_mailbox(request: Request) -> dict:
        """The signed-in user's send-from address. ``sendEnabled`` is the one
        flag the frontend needs: Gmail integration on AND a CBM mailbox on
        the user's linked profile."""
        user = require_user(request)
        settings = get_settings()
        if not settings.gmail_sync:
            return {"mailbox": None, "sendEnabled": False, "signature": ""}
        shared = _shared(settings)
        if shared:
            # The shared channel identity: generic display name, no personal
            # signature (the recipient sees "CBM Info", not a staffer's name).
            return {
                "mailbox": shared[0],
                "mailboxName": shared[1],
                "sendEnabled": True,
                "signature": "",
            }
        from sessions.service import resolve_user_mailbox  # avoid import cycle

        client = client_for(settings, user)
        try:
            mailbox = await resolve_user_mailbox(client, user["userId"])
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not look up your mailbox")
        return {
            "mailbox": mailbox,
            "sendEnabled": bool(mailbox),
            "signature": await comms_service.user_signature(client, user["userId"]),
        }
