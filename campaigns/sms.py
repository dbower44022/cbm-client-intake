"""The text-message kind (build plan § 3.5; rulings 9, 38 and 39).

**Select (ruling 9).** A Contact typed Prospect with ``cSmsOptIn`` true, a phone
number, ``phoneNumberIsOptedOut`` false, a rung in the chosen set, holding no
relationship type, whose prospect record (if any) has not left the ladder. A
prospect record is never selected: consent lives on the Contact.

**Build, sign off.** *Build the list* reconciles the Planned touches as the
call kind does. *Sign off and send* needs the campaign's wording
(``smsMessage``, ruling 39), refuses wording that does not say how to opt out
(the word STOP), shows the recipients and the message parts, and asks for the
typed recipient count, because a send cannot be called back (ruling 13's
gate). The wording is frozen from then on.

**Send (ruling 38) — the worker's.** The CRM's campaign status is the queue, as
for the postcard run: Signed off is picked up, Running resumed. Texts go out only
inside ``SMS_SEND_HOURS`` (chapter time). Twilio takes no idempotency key, so
each touch is marked *sending* before the call; a touch found still marked
after a crash is **never resent by itself** — it is reported for review. A
number the service refuses for good (unsubscribed, invalid) cancels the touch.

**Replies and delivery reports.** A STOP reply sets every Contact holding that
number to ``cSmsOptIn`` false — honoured at once (ruling 38). A delivery report
moves the touch to Delivered, or notes the failure on it.

Who acts: the selection, the touches and every send under the org-wide API
client (machine writes); the wording and the sign-off stamps as the signed-in
user.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.crm_upsert import CONTACT_TYPE_FIELD, PROSPECT_TYPE
from core.espo import EspoApi, EspoError
from core.phone import e164_or_none
from core.sms import SmsClient, SmsError, make_client, segments, tells_how_to_opt_out, within_send_hours

from . import config as cfg
from . import service
from .attribution import holds_relationship
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.sms")

_PAGE = 200
MESSAGE_FIELD = "smsMessage"
TEXTABLE_STAGES = (cfg.STAGE_QUALIFIED, cfg.STAGE_LEAD, cfg.STAGE_WARM_LEAD, cfg.STAGE_OPPORTUNITY)
DEFAULT_RULE: dict[str, Any] = {"stages": [cfg.STAGE_QUALIFIED, cfg.STAGE_LEAD, cfg.STAGE_WARM_LEAD]}
CONTACT_SELECT = (
    f"id,name,phoneNumber,phoneNumberIsOptedOut,cSmsOptIn,{CONTACT_TYPE_FIELD},cFunnelStage"
)
#: A touch the worker began sending and never finished (vendorStatus).
SENDING = "sending"
NEEDS_REVIEW = "sending interrupted — check the texting service before resending"


def _crm_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def message_field_available(client: EspoApi) -> bool:
    """Ruling 39's field, feature-detected; fails closed."""
    try:
        fields = await client.metadata(f"entityDefs.{cfg.CAMPAIGN}.fields") or {}
    except Exception:  # noqa: BLE001
        return False
    return isinstance(fields, dict) and MESSAGE_FIELD in fields


def normalise_rule(rule: Optional[dict[str, Any]]) -> dict[str, Any]:
    stages = [s for s in ((rule or {}).get("stages") or []) if s in TEXTABLE_STAGES]
    return {"stages": stages or list(DEFAULT_RULE["stages"])}


def rule_summary(rule: dict[str, Any]) -> str:
    return (f"Contacts typed Prospect at {' or '.join(rule['stages'])} who ticked the text consent "
            "(ruling 9), with a phone number not opted out, still on the ladder.")


async def select_targets(client: EspoApi, rule: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    rule = normalise_rule(rule)
    left: set[str] = set()
    for p in await service._page_all(
        client, cfg.PROSPECT, select="id,sideExit,promotedContactId",
        where=[{"type": "isNotNull", "attribute": "sideExit"}], limit=20000,
    ):
        if p.get("sideExit") and p.get("promotedContactId"):
            left.add(p["promotedContactId"])
    out = []
    for c in await service._page_all(
        client, cfg.CONTACT, select=CONTACT_SELECT,
        where=[{"type": "in", "attribute": "cFunnelStage", "value": rule["stages"]},
               {"type": "isTrue", "attribute": "cSmsOptIn"}],
        order_by="createdAt", order="asc", limit=10000,
    ):
        types = c.get(CONTACT_TYPE_FIELD) or []
        if (c["id"] in left or not c.get("cSmsOptIn") or PROSPECT_TYPE not in types
                or holds_relationship(c) or c.get("phoneNumberIsOptedOut")):
            continue
        phone = e164_or_none(c.get("phoneNumber"))
        if not phone:
            continue
        out.append({"key": f"contact:{c['id']}", "kind": "contact", "id": c["id"],
                    "name": c.get("name") or "", "phone": phone, "stage": c.get("cFunnelStage")})
    return out


async def build_list(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any],
                     rule: Optional[dict[str, Any]]) -> dict[str, Any]:
    if campaign.get("campaignKind") != cfg.KIND_SMS:
        raise CampaignError("This is not a text-message campaign.")
    status = campaign.get("campaignStatus") or cfg.STATUS_DRAFT
    if status not in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING):
        raise CampaignError(f"The list cannot be rebuilt once the campaign is {status}.")
    rule = normalise_rule(rule)
    targets = await select_targets(api_client, rule)
    planned = {}
    for t in await service.campaign_touches(api_client, campaign["id"]):
        if t.get("touchStatus") == cfg.TOUCH_PLANNED and t.get("contactId"):
            planned[f"contact:{t['contactId']}"] = t
    wanted = {t["key"]: t for t in targets}
    created = kept = cancelled = 0
    for key, touch in planned.items():
        if key not in wanted:
            await api_client.update(cfg.TOUCH, touch["id"], {"touchStatus": cfg.TOUCH_CANCELLED})
            cancelled += 1
    for key, target in wanted.items():
        if key in planned:
            kept += 1
            continue
        await api_client.create(cfg.TOUCH, {
            "name": f"{campaign.get('name') or 'Campaign'} — {target['name']}"[:255],
            "channel": cfg.KIND_SMS, "touchStatus": cfg.TOUCH_PLANNED, "plannedAt": _crm_now(),
            "outreachCampaignId": campaign["id"], "contactId": target["id"],
        })
        created += 1
    stamps: dict[str, Any] = {"selectionRule": json.dumps(rule), "selectionSummary": rule_summary(rule)}
    if status == cfg.STATUS_DRAFT:
        stamps["campaignStatus"] = cfg.STATUS_AWAITING
    await user_client.update(cfg.CAMPAIGN, campaign["id"], stamps)
    return {"pieces": kept + created, "created": created, "kept": kept, "cancelled": cancelled,
            "rule": rule, "summary": stamps["selectionSummary"]}


def check_message(text: Optional[str]) -> dict[str, Any]:
    """The wording's readiness: its parts, and the refusals the sign-off makes."""
    text = (text or "").strip()
    problems = []
    if not text:
        problems.append("Write the text message first (the campaign's form, Text message).")
    elif not tells_how_to_opt_out(text):
        problems.append("The text must tell people how to stop texts — include the word STOP "
                        "(for example: Reply STOP to opt out).")
    return {**segments(text), "problems": problems}


async def sign_off(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any], *,
                   confirm: str, user_name: str) -> dict[str, Any]:
    if campaign.get("campaignKind") != cfg.KIND_SMS:
        raise CampaignError("This is not a text-message campaign.")
    if campaign.get("campaignStatus") not in (cfg.STATUS_AWAITING, cfg.STATUS_DRAFT):
        raise CampaignError(f"A campaign at {campaign.get('campaignStatus')} cannot be signed off.")
    whole = await api_client.get(cfg.CAMPAIGN, campaign["id"])
    check = check_message((whole or {}).get(MESSAGE_FIELD))
    if check["problems"]:
        raise CampaignError(check["problems"][0])
    touches = await service.campaign_touches(api_client, campaign["id"])
    count = sum(1 for t in touches if t.get("touchStatus") == cfg.TOUCH_PLANNED)
    if count == 0:
        raise CampaignError("Build the list first — there is nobody on it to text.")
    if str(confirm or "").strip() != str(count):
        raise CampaignError(f"Type the number of people, {count}, to confirm. A text cannot be called back.")
    return await user_client.update(cfg.CAMPAIGN, campaign["id"], {
        "pieceCount": count, "signedOffByName": user_name[:255], "signedOffAt": _crm_now(),
        "campaignStatus": cfg.STATUS_SIGNED_OFF,
    })


# --- the send (worker) ------------------------------------------------------------------------

async def run_campaign(client: EspoApi, campaign: dict[str, Any], *, sender: SmsClient,
                       settings: Settings, stop=None) -> dict[str, int]:
    totals = {"sent": 0, "failed": 0, "skipped": 0, "review": 0}
    whole = await client.get(cfg.CAMPAIGN, campaign["id"])
    body = ((whole or {}).get(MESSAGE_FIELD) or "").strip()
    if check_message(body)["problems"]:
        log.warning("sms campaign %s: no usable wording; nothing sent", campaign["id"])
        return totals
    base = (settings.app_base_url or "").rstrip("/")
    callback = f"{base}/api/campaigns/sms/status" if base else ""
    if campaign.get("campaignStatus") == cfg.STATUS_SIGNED_OFF:
        await client.update(cfg.CAMPAIGN, campaign["id"],
                            {"campaignStatus": cfg.STATUS_RUNNING, "runStartedAt": _crm_now()})
    planned = [t for t in await service.campaign_touches(client, campaign["id"])
               if t.get("touchStatus") == cfg.TOUCH_PLANNED]
    for touch in planned:
        if stop is not None and stop.is_set():
            break
        if (touch.get("vendorStatus") or "").startswith(SENDING):
            # Begun and never finished: the person may already have it.
            if touch.get("vendorStatus") != NEEDS_REVIEW:
                await client.update(cfg.TOUCH, touch["id"], {"vendorStatus": NEEDS_REVIEW})
            totals["review"] += 1
            continue
        try:
            contact = await client.get(cfg.CONTACT, touch.get("contactId") or "", select=CONTACT_SELECT)
        except EspoError as exc:
            log.warning("sms touch %s: contact unreadable: %s", touch["id"], exc)
            totals["failed"] += 1
            continue
        phone = e164_or_none((contact or {}).get("phoneNumber"))
        if (not contact or not contact.get("cSmsOptIn") or contact.get("phoneNumberIsOptedOut") or not phone):
            await client.update(cfg.TOUCH, touch["id"], {
                "touchStatus": cfg.TOUCH_CANCELLED, "vendorStatus": "no consent or no usable number at send time"})
            totals["skipped"] += 1
            continue
        await client.update(cfg.TOUCH, touch["id"], {"vendorStatus": SENDING})
        try:
            sent = await sender.send(key=touch["id"], to=phone, body=body, status_callback=callback)
        except SmsError as exc:
            if exc.ambiguous:
                await client.update(cfg.TOUCH, touch["id"], {"vendorStatus": NEEDS_REVIEW})
                totals["review"] += 1
            elif exc.permanent:
                await client.update(cfg.TOUCH, touch["id"], {
                    "touchStatus": cfg.TOUCH_CANCELLED, "vendorStatus": f"refused: {exc}"[:255]})
                totals["failed"] += 1
            else:
                await client.update(cfg.TOUCH, touch["id"], {"vendorStatus": f"not sent: {exc}"[:255]})
                totals["failed"] += 1
                break   # a service-wide failure: stop this pass, retry on the next
            continue
        await client.update(cfg.TOUCH, touch["id"], {
            "touchStatus": cfg.TOUCH_SENT, "sentAt": _crm_now(), "vendorPieceId": sent.id,
            "vendorStatus": sent.status, "calledPhone": phone, "stageAtTouch": contact.get("cFunnelStage"),
        })
        totals["sent"] += 1
    remaining = [t for t in await service.campaign_touches(client, campaign["id"])
                 if t.get("touchStatus") == cfg.TOUCH_PLANNED]
    if not remaining:
        await client.update(cfg.CAMPAIGN, campaign["id"],
                            {"campaignStatus": cfg.STATUS_COMPLETE, "runCompletedAt": _crm_now()})
    log.info("sms campaign %s: %s (remaining planned %s)", campaign["id"], totals, len(remaining))
    return totals


async def run_sms_cycle(settings: Settings, *, client: Optional[EspoApi] = None,
                        sender: Optional[SmsClient] = None, stop=None, now: Optional[datetime] = None) -> dict[str, int]:
    """One worker pass over every Signed off or Running text-message campaign.
    Best effort, never raises; outside the texting hours it sends nothing."""
    totals = {"campaigns": 0, "sent": 0, "failed": 0, "skipped": 0, "review": 0, "errors": 0}
    if not (settings.campaigns_enabled and settings.campaigns_sms) or settings.espo_dry_run:
        return totals
    if not within_send_hours(settings, now):
        return totals
    if client is None:
        from core.espo import EspoClient
        client = EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)
    try:
        sender = sender or make_client(settings)
    except SmsError as exc:
        log.warning("sms run: %s", exc)
        totals["errors"] += 1
        return totals
    try:
        page = await client.list(cfg.CAMPAIGN, select=cfg.CAMPAIGN_SELECT, max_size=_PAGE, where=[
            {"type": "equals", "attribute": "campaignKind", "value": cfg.KIND_SMS},
            {"type": "in", "attribute": "campaignStatus", "value": [cfg.STATUS_SIGNED_OFF, cfg.STATUS_RUNNING]},
        ])
    except EspoError as exc:
        log.warning("sms run: could not list campaigns: %s", exc)
        totals["errors"] += 1
        return totals
    for campaign in page.get("list", []):
        totals["campaigns"] += 1
        try:
            result = await run_campaign(client, campaign, sender=sender, settings=settings, stop=stop)
            for k in ("sent", "failed", "skipped", "review"):
                totals[k] += result.get(k, 0)
        except Exception as exc:  # noqa: BLE001 — one campaign never stops the others
            totals["errors"] += 1
            log.warning("sms campaign %s errored: %s", campaign.get("id"), exc)
    return totals


# --- replies and delivery reports ---------------------------------------------------------------

async def contacts_with_phone(client: EspoApi, phone: str) -> list[dict[str, Any]]:
    """Every Contact holding this number, however it was typed in the CRM."""
    want = e164_or_none(phone)
    if not want:
        return []
    digits = want[-10:]
    page = await client.list(cfg.CONTACT, select="id,name,phoneNumber,cSmsOptIn", max_size=_PAGE,
                             where=[{"type": "contains", "attribute": "phoneNumber", "value": digits[-4:]}])
    return [c for c in page.get("list", []) if e164_or_none(c.get("phoneNumber")) == want]


async def apply_stop(client: EspoApi, phone: str) -> list[str]:
    """Ruling 38: a STOP reply opts the number out of texts at once."""
    changed = []
    for c in await contacts_with_phone(client, phone):
        if c.get("cSmsOptIn"):
            await client.update(cfg.CONTACT, c["id"], {"cSmsOptIn": False})
            changed.append(c["id"])
    return changed


async def apply_status(client: EspoApi, *, message_id: str, status: str, error_code: str = "") -> dict[str, Any]:
    if not message_id:
        return {"applied": False, "reason": "no message id"}
    touch = await client.find_one(cfg.TOUCH, "vendorPieceId", message_id, select="id,touchStatus")
    if not touch:
        return {"applied": False, "reason": "no touch carries this message id"}
    status = (status or "").lower()
    if status == "delivered":
        await client.update(cfg.TOUCH, touch["id"], {"touchStatus": cfg.TOUCH_DELIVERED, "deliveredAt": _crm_now(),
                                                     "vendorStatus": "delivered"})
    elif status in ("undelivered", "failed"):
        await client.update(cfg.TOUCH, touch["id"], {
            "vendorStatus": f"{status}{(' ' + error_code) if error_code else ''}"[:255]})
    else:
        await client.update(cfg.TOUCH, touch["id"], {"vendorStatus": status[:255]})
    return {"applied": True, "touchId": touch["id"], "status": status}
