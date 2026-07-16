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
    subject: str = ""
    body: str = ""
    # {"espoId": …} template chips / {"filename","contentType","dataBase64"}
    # local uploads — comms.service.resolve_attachments.
    attachments: list[dict] = Field(default_factory=list)


class QuickParseIn(BaseModel):
    emailAddress: str = ""


class QuickWriteBackIn(BaseModel):
    subject: str = ""
    bodyHtml: str = ""
    to: list[str] = Field(default_factory=list)
    parentType: str | None = None
    parentId: str | None = None
    messageId: str = ""


def register_quicksend(
    router: Any,
    require_user: Callable[[Request], dict],
    client_for: Callable[..., Any],
    crm_failure: Callable[..., HTTPException],
    include_mailbox: bool = True,
) -> None:
    """Attach the quick-send endpoints to a staff app's router.

    ``include_mailbox=False`` for routers that already serve their own
    ``GET /mailbox`` (the session tools) — they get only ``POST /sendmail``.
    """

    def _sending_on() -> Any:
        settings = get_settings()
        if not settings.gmail_sync:
            raise HTTPException(
                status_code=503, detail="Email sending isn't enabled on this deployment."
            )
        return settings

    @router.post("/sendmail")
    async def quick_send(body: QuickSendIn, request: Request) -> dict:
        user = require_user(request)
        settings = _sending_on()
        client = client_for(settings, user)
        try:
            gmail = await comms_service.gmail_for_user(settings, client, user)
            result = await comms_service.send_quick_message(
                gmail=gmail, to=body.to, subject=body.subject, body_html=body.body,
                sender_name=user.get("name") or "",
                user_client=client, attachments=body.attachments,
            )
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
            return await comms_templates.parse_template(
                client, template_id, email_address=body.emailAddress or None,
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
            mailbox = await resolve_user_mailbox(client, user["userId"])
            email_id = await comms_service.write_back_email(
                client, subject=body.subject, body_html=body.bodyHtml,
                sender=mailbox or "", to=body.to,
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
            return {"mailbox": None, "sendEnabled": False}
        from sessions.service import resolve_user_mailbox  # avoid import cycle

        client = client_for(settings, user)
        try:
            mailbox = await resolve_user_mailbox(client, user["userId"])
        except EspoError as exc:
            raise crm_failure(request, exc, "Could not look up your mailbox")
        return {"mailbox": mailbox, "sendEnabled": bool(mailbox)}
