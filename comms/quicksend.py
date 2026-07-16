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

log = logging.getLogger("cbm_intake.comms.quicksend")


class QuickSendIn(BaseModel):
    to: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""


def register_quicksend(
    router: Any,
    require_user: Callable[[Request], dict],
    client_for: Callable[..., Any],
    crm_failure: Callable[..., HTTPException],
) -> None:
    """Attach the two quick-send endpoints to a staff app's router."""

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

    @router.post("/sendmail")
    async def quick_send(body: QuickSendIn, request: Request) -> dict:
        user = require_user(request)
        settings = get_settings()
        if not settings.gmail_sync:
            raise HTTPException(
                status_code=503, detail="Email sending isn't enabled on this deployment."
            )
        client = client_for(settings, user)
        try:
            gmail = await comms_service.gmail_for_user(settings, client, user)
            result = await comms_service.send_quick_message(
                gmail=gmail, to=body.to, subject=body.subject, body_html=body.body
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
