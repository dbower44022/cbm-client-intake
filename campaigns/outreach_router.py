"""Personal outreach — the lead page's endpoints on ``/campaigns/api`` (build
plan § 7e.5). Registered on the campaigns ``api_router`` by ``router.py``'s
tail import; the gate, the actor and the CRM-failure mapping are the router's
own. Dark behind ``LEAD_OUTREACH`` (read per request). The rules are in
``outreach.py``; the send is ``comms.service.send_message`` with a lead
``RecordRef``; the call's consequences are ``calls.apply_outcome``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from comms import crm as comms_crm
from comms import service as comms_service
from comms import templates as comms_templates
from core.action_log import CAT_COMMUNICATION, record_action
from core.config import Settings, get_settings
from core.espo import EspoError
from core.gmail import GmailError

from . import calls, config as cfg, ladder, outreach
from .conversion import Details
from .router import (
    APP_CAMPAIGNS, _actor, _api_client, _crm_failure, _lead_or_404, _lead_select, api_router,
)
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.outreach")

ACTION_EMAILED = "Lead Emailed"
ACTION_CALLED = "Lead Called"


def _require_outreach(settings: Settings) -> None:
    if not settings.lead_outreach:
        raise HTTPException(status_code=404, detail="Personal outreach is switched off (Personal outreach to leads at /setup).")


def _mail_ready(settings: Settings):
    """The comms store, or a 503 in words — the same two conditions the
    session tools' compose needs."""
    if not settings.gmail_sync:
        raise HTTPException(status_code=503, detail="The email integration isn't enabled on this deployment, so personal email cannot be sent.")
    store = comms_service.get_store(settings)
    if store is None:
        raise HTTPException(status_code=503, detail="The email integration needs the application database (DATABASE_URL).")
    return store


async def _lead_for_outreach(request: Request, client) -> tuple[dict[str, Any], bool]:
    select, has_ladder = await _lead_select(client)
    lead = await _lead_or_404(request, client, request.path_params["prospect_id"], select=select)
    if not has_ladder:
        raise HTTPException(status_code=409, detail="This CRM does not carry the lead's Assigned to field yet, so personal outreach is not available here.")
    return lead, has_ladder


@api_router.get("/mailbox")
async def outreach_mailbox(request: Request) -> dict[str, Any]:
    """The From line of the lead page's composer: the sender's own chapter
    mailbox by ruling 120, with their signature; or ``mailbox: null`` and the
    reason in words (the composer shows it; the send refuses with it too)."""
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    try:
        mailbox = await comms_service.sender_mailbox(client, user, settings)
    except comms_service.CommsError as exc:
        return {"mailbox": None, "sendEnabled": False, "signature": "", "reason": str(exc)}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not look up your mailbox")
    return {
        "mailbox": mailbox,
        "sendEnabled": bool(settings.gmail_sync),
        "signature": await comms_service.user_signature(client, user.get("userId") or ""),
    }


@api_router.get("/emailtemplates")
async def outreach_templates(request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    try:
        return await outreach.marketing_templates(client)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load email templates")


class TemplateParseIn(BaseModel):
    emailAddress: str = ""


@api_router.post("/prospects/{prospect_id}/emailtemplates/{template_id}/parse")
async def outreach_template_parse(prospect_id: str, template_id: str, body: TemplateParseIn,
                                  request: Request) -> dict[str, Any]:
    """EspoCRM renders the template with the lead as the record, so
    ``{CProspect.*}`` resolves; the sender's own mentor profile, when they have
    one, rides as the related record for ``{CMentorProfile.*}``. Unresolved
    placeholders stay literal and the composer warns, as everywhere."""
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    lead = await _lead_or_404(request, client, prospect_id, select="id,name,businessName,email")
    try:
        profile_id = await comms_templates.related_manager_profile(client, user_id=user.get("userId") or "")
        return await comms_templates.parse_template(
            client, template_id, parent_type=cfg.PROSPECT, parent_id=prospect_id,
            email_address=(body.emailAddress or lead.get("email") or "").strip().lower() or None,
            related_type="CMentorProfile" if profile_id else None, related_id=profile_id,
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not apply the template")


class SendIn(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)


@api_router.post("/prospects/{prospect_id}/messages")
async def outreach_send(prospect_id: str, body: SendIn, request: Request) -> dict[str, Any]:
    """Send one personal email to the lead from the assignee's own mailbox
    (rulings 107, 108, 120, 122). The guardrails run here, before anything
    leaves; the opt-out sentence and the postal address are appended when
    missing; the conversation is linked to the lead through the write-through
    ingest; one *Personal email* touch is written as the user; the action is
    logged with the subject, never the body."""
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    store = _mail_ready(settings)
    lead, _ = await _lead_for_outreach(request, client)
    why = outreach.why_not_email(lead, user)
    if why:
        raise HTTPException(status_code=400, detail=why)
    try:
        email = outreach.check_recipients(lead, body.to, body.cc, body.bcc)
        body_html = outreach.append_footer(body.body, settings.chapter_postal_address)
        attachments = outreach.attachments_for_lead(body.attachments)
        mailbox = await comms_service.sender_mailbox(client, user, settings)
    except (CampaignError, comms_service.CommsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not look up your mailbox")
    api_client = _api_client(settings, request)
    name = outreach.lead_name(lead)
    ref = comms_crm.RecordRef(entity=cfg.PROSPECT, id=prospect_id, name=name, addresses={email})
    try:
        gmail = await comms_service.gmail_for_shared_mailbox(settings, mailbox)
        result = await comms_service.send_message(
            settings=settings, api_client=api_client, store=store, gmail=gmail, user=user,
            to=[email], subject=body.subject, body_html=body_html,
            user_client=client, attachments=attachments, ref=ref,
        )
    except comms_service.CommsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GmailError as exc:
        log.warning("personal email send failed for lead %s: %s", prospect_id, exc)
        raise HTTPException(status_code=502, detail=f"Couldn't send the message from {mailbox} — the mailbox refused ({exc}).")
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not send the message")
    # The message is out. The touch and the log are best-effort from here:
    # a refusal is reported, never a failed send.
    warnings: list[str] = []
    touch_id: Optional[str] = None
    try:
        teams = await outreach.team_ids(api_client, settings.campaigns_allowed_teams_list)
        touch = await client.create(cfg.TOUCH, outreach.email_touch_payload(
            lead, body.subject, user_id=user.get("userId") or "", team_ids=teams))
        touch_id = touch.get("id")
    except EspoError as exc:
        log.warning("personal email touch for lead %s not written: %s", prospect_id, exc)
        warnings.append(f"The email was sent, but it could not be recorded on the lead's Activity ({exc}).")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_COMMUNICATION, action=ACTION_EMAILED,
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=f"Emailed the lead \"{name}\": {(body.subject or '(no subject)').strip()}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"subject": body.subject, "to": email, "from": mailbox, "touchId": touch_id,
                 "conversationId": result.get("conversationId")},
    )
    return {"status": "ok", **result, "touchId": touch_id, "warnings": warnings, "from": mailbox}


class CallIn(BaseModel):
    outcome: str
    notes: str = Field(default="", max_length=4000)
    calledPhone: str = Field(default="", max_length=100)


@api_router.post("/prospects/{prospect_id}/calls")
async def outreach_call(prospect_id: str, body: CallIn, request: Request) -> dict[str, Any]:
    """Log a personal call (ruling 108): one campaign-less *Personal call*
    touch written as the user, then the campaign calls' own consequences
    under the API client — Interested converts (ruling 47), Not interested
    stops the lead by Declined with the note, No reply yet writes the touch
    only — then placement."""
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    lead, _ = await _lead_for_outreach(request, client)
    why = outreach.why_not_call(lead, user)
    if why:
        raise HTTPException(status_code=400, detail=why)
    api_client = _api_client(settings, request)
    try:
        teams = await outreach.team_ids(api_client, settings.campaigns_allowed_teams_list)
        payload = outreach.call_touch_payload(lead, body.outcome, body.notes, body.calledPhone,
                                              user_id=user.get("userId") or "", team_ids=teams)
        touch = await client.create(cfg.TOUCH, payload)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not record the call")
    result: dict[str, Any] = {"touchId": touch.get("id"), "outcome": body.outcome, "consequences": [], "warnings": []}
    stored = cfg.PERSONAL_OUTCOME_STORED[body.outcome]
    try:
        await calls.apply_outcome(
            api_client, prospect_id, stored, body.notes.strip(), details=Details(),
            touch_id=touch.get("id") or "", campaign_id=None, result=result)
    except EspoError as exc:
        result["warnings"].append(f"The call is recorded, but its consequence could not be written ({exc}).")
    if stored == cfg.OUTCOME_NO_ANSWER:
        await ladder.after_write(prospect_id, client=api_client, settings=settings,
                                 store=getattr(request.app.state, "campaign_store", None))
    name = outreach.lead_name(lead)
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_COMMUNICATION, action=ACTION_CALLED,
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=f"Logged a call on the lead \"{name}\": {body.outcome}"
                + (f" — {body.notes.strip()[:120]}" if body.notes.strip() else ""),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"outcome": body.outcome, "stored": stored, "calledPhone": payload.get("calledPhone"),
                 "touchId": touch.get("id"), "consequences": result["consequences"], "warnings": result["warnings"]},
    )
    return result


@api_router.get("/prospects/{prospect_id}/conversations")
async def outreach_conversations(prospect_id: str, request: Request) -> dict[str, Any]:
    """The lead's email conversations, read as the user (the Marketing Admin
    Role reads its own conversations). Never an error the page must handle:
    with email off, or the lead unreadable, ``available`` is false and
    ``reason`` says why."""
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    if not settings.gmail_sync:
        return {"available": False, "reason": "The email integration isn't enabled on this deployment.", "conversations": []}
    store = comms_service.get_store(settings)
    await _lead_or_404(request, client, prospect_id, select="id,name")
    try:
        rows = await comms_service.list_conversations(client, cfg.PROSPECT, prospect_id)
        if store is not None:
            await comms_service.enrich_conversation_rows(client, store, user.get("userName") or "", rows)
    except EspoError as exc:
        log.info("lead %s conversations not read: %s", prospect_id, exc)
        return {"available": False, "conversations": [],
                "reason": "The lead's conversations could not be read — this CRM may not carry the conversation link yet, or your role may not read conversations."}
    return {"available": True, "reason": "", "conversations": rows}


@api_router.get("/conversations/{conversation_id}")
async def outreach_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    store = _mail_ready(settings)
    try:
        thread = await comms_service.get_conversation(client, conversation_id, store=store)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load the conversation")
    try:
        await store.mark_seen(user.get("userName") or "", conversation_id)
    except Exception as exc:  # noqa: BLE001 — a read stamp never blocks reading
        log.warning("mark_seen failed for %s: %s", user.get("userName"), exc)
    return thread


class WriteBackIn(BaseModel):
    subject: str = ""
    bodyHtml: str = ""
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    parentType: Optional[str] = None
    parentId: Optional[str] = None
    messageId: str = ""


@api_router.post("/emailwriteback")
async def outreach_write_back(body: WriteBackIn, request: Request) -> dict[str, Any]:
    """The composer's retry of a failed CRM Email record after a successful
    send — never silent."""
    user, client = _actor(request)
    settings = get_settings()
    _require_outreach(settings)
    _mail_ready(settings)
    try:
        mailbox = await comms_service.sender_mailbox(client, user, settings)
        email_id = await comms_service.write_back_email(
            client, subject=body.subject, body_html=body.bodyHtml, sender=mailbox,
            to=body.to, cc=body.cc, bcc=body.bcc, parent_type=body.parentType, parent_id=body.parentId,
            message_id=body.messageId,
        )
        return {"status": "ok", "emailId": email_id}
    except comms_service.CommsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not record the email in the CRM")
