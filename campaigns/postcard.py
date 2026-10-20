"""The postcard kind (build plan § 3.2): select, sign off, run, and the vendor's
delivery events.

Who acts: the selection and the touches it plans run under the **org-wide API
client** — an aggregate over records the Marketing Admin Role may not read one
by one, and the writes a machine makes on the campaign's behalf. The sign-off
stamps are written as the signed-in user (it is their signature). The run is the
**worker's** (sends never run in a web request); the CRM's campaign status is its
queue: ``Signed off`` is picked up, ``Running`` is resumed, ``Complete`` is left.

Rulings kept here: one card per company, ever (14) — a target with any Sent,
Delivered or Returned postcard touch from any campaign is never selected again;
a returned piece marks the ADDRESS dead and leaves the status alone (15); a touch
is created at selection as ``Planned``, which is what "Active Prospect" means in
storage (10). The lead model (§ 7a, ruling 44): a postcard selects Unqualified
and Qualified leads; a converted lead's Company stands in for it, never carded
twice; Companies typed Prospect (already contacted) are an opt-in, off by
default.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError
from core.postal import (
    EVENT_DELIVERED, EVENT_RETURNED, Address, PostalClient, PostalError, estimated_cost, make_client,
)

from . import config as cfg
from .audience import audience_result as _audience_result
from . import service
from .service import CampaignError
from .tokens import new_scan_token

log = logging.getLogger("cbm_intake.campaigns.postcard")

_PAGE = 200
_RUN_BATCH = 100
_MAX_RUN_FAILURES = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _crm_now() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")


# --- the selection rule -------------------------------------------------------------

DEFAULT_RULE: dict[str, Any] = {"statuses": list(cfg.LEAD_OPEN_STATUSES), "stages": []}


def normalise_rule(rule: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The screen's choices, kept to what the postcard kind allows: leads at
    Unqualified and/or Qualified (ruling 44), and optionally Companies typed
    Prospect at a stage — already contacted, so off by default."""
    rule = rule or {}
    statuses = [s for s in (rule.get("statuses") or []) if s in cfg.LEAD_OPEN_STATUSES]
    stages = [s for s in (rule.get("stages") or []) if s in cfg.STAGES]
    if not statuses and not stages:
        statuses = list(DEFAULT_RULE["statuses"])
    return {"statuses": statuses, "stages": stages}


def rule_summary(rule: dict[str, Any]) -> str:
    parts = []
    if rule["statuses"]:
        parts.append(f"leads at {' or '.join(rule['statuses'])}")
    if rule["stages"]:
        parts.append(f"Companies typed Prospect at {' or '.join(rule['stages'])}")
    joined = ' and '.join(parts)
    return (f"{joined[:1].upper() + joined[1:]}, with a usable mailing address, still being worked, "
            f"and no postcard ever sent to the business (ruling 14).")


async def _carded_targets(client: EspoApi) -> set[str]:
    """Every target that has had a postcard from ANY campaign: ruling 14."""
    out: set[str] = set()
    offset = 0
    while True:
        page = await client.list(
            cfg.TOUCH, select="id,prospectId,companyId,contactId", max_size=_PAGE, offset=offset,
            where=[
                {"type": "equals", "attribute": "channel", "value": cfg.KIND_POSTCARD},
                {"type": "in", "attribute": "touchStatus",
                 "value": [cfg.TOUCH_SENT, cfg.TOUCH_DELIVERED, cfg.TOUCH_RETURNED]},
            ],
        )
        batch = page.get("list", [])
        for t in batch:
            for key, kind in (("prospectId", "prospect"), ("companyId", "company"), ("contactId", "contact")):
                if t.get(key):
                    out.add(f"{kind}:{t[key]}")
        if len(batch) < _PAGE or offset >= 20000:
            break
        offset += _PAGE
    return out


async def select_targets(client: EspoApi, rule: dict[str, Any]) -> list[dict[str, Any]]:
    """The records a postcard campaign would mail to, each as
    ``{key, kind, id, name, address, stage}`` (``stage`` is what the touch
    records: the lead's status, or the Company's stage)."""
    rule = normalise_rule(rule)
    carded = await _carded_targets(client)
    targets: list[dict[str, Any]] = []
    # A business is ONE target: a lead stands for the Company it converted to,
    # so that Company is never selected a second time (two cards to Lakeview
    # Bakery on 10-15-26), and a card to either side counts for both.
    for p in await service._page_all(client, cfg.PROSPECT, select="id,promotedCompanyId",
                                     where=[{"type": "isNotNull", "attribute": "promotedCompanyId"}],
                                     limit=50000):
        if p.get("promotedCompanyId"):
            if f"prospect:{p['id']}" in carded:
                carded.add(f"company:{p['promotedCompanyId']}")

    if rule["statuses"]:
        leads = await service._page_all(
            client, cfg.PROSPECT, select=cfg.PROSPECT_SELECT,
            where=[
                {"type": "in", "attribute": "leadStatus", "value": rule["statuses"]},
                {"type": "equals", "attribute": "addressStatus", "value": cfg.ADDRESS_USABLE},
                {"type": "isNull", "attribute": "sideExit"},
            ],
            order_by="createdAt", order="asc", limit=10000,
        )
    else:
        leads = []
    for p in leads:
        if p.get("sideExit") or p.get("leadStatus") not in rule["statuses"]:
            continue
        key = f"prospect:{p['id']}"
        if key in carded or (p.get("promotedCompanyId") and f"company:{p['promotedCompanyId']}" in carded):
            continue
        address = _prospect_address(p)
        if not address.is_complete():
            continue
        targets.append({"key": key, "kind": "prospect", "id": p["id"],
                        "name": p.get("businessName") or p.get("name") or "",
                        "address": address, "stage": p.get("leadStatus")})

    if rule["stages"]:
        companies = await service._page_all(
            client, cfg.ACCOUNT,
            select="id,name,cCompanyType,cFunnelStage,billingAddressStreet,billingAddressCity,"
                   "billingAddressState,billingAddressPostalCode,billingAddressCountry",
            where=[{"type": "in", "attribute": "cFunnelStage", "value": rule["stages"]}],
            order_by="createdAt", order="asc", limit=10000,
        )
        for c in companies:
            types = c.get("cCompanyType") or []
            if cfg.COMPANY_TYPE_PROSPECT not in types:
                continue
            key = f"company:{c['id']}"
            if key in carded:
                continue
            address = Address(
                name=c.get("name") or "", line1=c.get("billingAddressStreet") or "",
                city=c.get("billingAddressCity") or "", state=c.get("billingAddressState") or "",
                postal_code=c.get("billingAddressPostalCode") or "",
                country=c.get("billingAddressCountry") or "US",
            )
            if not address.is_complete():
                continue
            targets.append({"key": key, "kind": "company", "id": c["id"], "name": c.get("name") or "",
                            "address": address, "stage": c.get("cFunnelStage")})
    return targets


def _prospect_address(p: dict[str, Any]) -> Address:
    return Address(
        name=p.get("businessName") or p.get("name") or "",
        line1=p.get("mailingAddressStreet") or "", city=p.get("mailingAddressCity") or "",
        state=p.get("mailingAddressState") or "", postal_code=p.get("mailingAddressPostalCode") or "",
        country=p.get("mailingAddressCountry") or "US",
    )


def address_text(a: Address) -> str:
    line2 = " ".join(x for x in (f"{a.city}," if a.city else "", a.state, a.postal_code) if x)
    return "\n".join(x for x in (a.line1, a.line2, line2, a.country if a.country not in ("", "US") else "") if x)


# --- build the list ------------------------------------------------------------------

async def build_list(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any],
                     rule: Optional[dict[str, Any]], settings: Settings,
                     audience: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Step 2 of § 3.1: evaluate the rule, reconcile this campaign's Planned
    touches to the selection (new targets gain a Planned row, dropped targets'
    Planned rows are Cancelled, Sent rows are never touched), and write the rule
    and its summary on the campaign. Draft moves to Awaiting sign-off."""
    if campaign.get("campaignKind") != cfg.KIND_POSTCARD:
        raise CampaignError("Only a postcard campaign builds a mailing list in this phase.")
    status = campaign.get("campaignStatus") or cfg.STATUS_DRAFT
    if status not in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING):
        raise CampaignError(f"The list cannot be rebuilt once the campaign is {status}.")
    rule = normalise_rule(rule)
    # A campaign that names a list sends to it (build plan § 7c); else its rule.
    targets = audience["targets"] if audience else await select_targets(api_client, rule)
    existing = await service.campaign_touches(api_client, campaign["id"])
    planned_by_key: dict[str, dict[str, Any]] = {}
    for t in existing:
        if t.get("touchStatus") != cfg.TOUCH_PLANNED:
            continue
        for key, kind in (("prospectId", "prospect"), ("companyId", "company"), ("contactId", "contact")):
            if t.get(key):
                planned_by_key[f"{kind}:{t[key]}"] = t
    wanted = {t["key"]: t for t in targets}
    created = kept = cancelled = 0
    for key, touch in planned_by_key.items():
        if key not in wanted:
            await api_client.update(cfg.TOUCH, touch["id"], {"touchStatus": cfg.TOUCH_CANCELLED})
            cancelled += 1
    for key, target in wanted.items():
        if key in planned_by_key:
            kept += 1
            continue
        payload: dict[str, Any] = {
            "name": f"{campaign.get('name') or 'Campaign'} — {target['name']}"[:255],
            "channel": cfg.KIND_POSTCARD,
            "touchStatus": cfg.TOUCH_PLANNED,
            "plannedAt": _crm_now(),
            "outreachCampaignId": campaign["id"],
        }
        payload[f"{target['kind']}Id"] = target["id"]
        await api_client.create(cfg.TOUCH, payload)
        created += 1
    pieces = kept + created
    stamps: dict[str, Any] = {
        "selectionRule": json.dumps({"list": audience["list"]} if audience else rule),
        "selectionSummary": audience["summary"] if audience else rule_summary(rule),
    }
    if status == cfg.STATUS_DRAFT:
        stamps["campaignStatus"] = cfg.STATUS_AWAITING
    await service.stamp_campaign(user_client, api_client, campaign["id"], stamps)
    return {"pieces": pieces, "created": created, "kept": kept, "cancelled": cancelled,
            "estimatedCost": estimated_cost(settings, pieces), "currency": settings.postal_currency,
            "rule": rule, "summary": stamps["selectionSummary"],
            **({"audience": _audience_result(audience)} if audience else {})}


# --- sign off --------------------------------------------------------------------------

async def sign_off(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any], *,
                   confirm: str, user_name: str, settings: Settings) -> dict[str, Any]:
    """Ruling 13: the run assembles its list, shows the piece count and the
    estimated cost, and mails nothing until signed. The typed confirmation is the
    piece count, so the signer has read it."""
    if campaign.get("campaignKind") != cfg.KIND_POSTCARD:
        raise CampaignError("Only a postcard campaign is signed off in this phase.")
    if campaign.get("campaignStatus") not in (cfg.STATUS_AWAITING, cfg.STATUS_DRAFT):
        raise CampaignError(f"A campaign at {campaign.get('campaignStatus')} cannot be signed off.")
    touches = await service.campaign_touches(api_client, campaign["id"])
    pieces = sum(1 for t in touches if t.get("touchStatus") == cfg.TOUCH_PLANNED)
    if pieces == 0:
        raise CampaignError("Build the list first — there is nothing planned to sign off.")
    if str(confirm or "").strip() != str(pieces):
        raise CampaignError(f"Type the piece count, {pieces}, to confirm the sign-off.")
    if not settings.store_enabled:
        raise CampaignError("The campaign's link needs the application database, which is not configured.")
    cost = estimated_cost(settings, pieces)
    stamps = {
        "pieceCount": pieces,
        "estimatedCost": cost,
        "estimatedCostCurrency": settings.postal_currency or "USD",
        "signedOffByName": user_name[:255],
        "signedOffAt": _crm_now(),
        "campaignStatus": cfg.STATUS_SIGNED_OFF,
    }
    return await service.stamp_campaign(user_client, api_client, campaign["id"], stamps)


# --- the run (worker) ------------------------------------------------------------------

async def _target_for(client: EspoApi, touch: dict[str, Any]) -> Optional[dict[str, Any]]:
    if touch.get("prospectId"):
        p = await client.get(cfg.PROSPECT, touch["prospectId"], select=cfg.PROSPECT_SELECT)
        return {"kind": "prospect", "record": p, "address": _prospect_address(p),
                "stage": p.get("leadStatus"), "name": p.get("businessName") or p.get("name") or ""}
    if touch.get("companyId"):
        c = await client.get(cfg.ACCOUNT, touch["companyId"],
                             select="id,name,cFunnelStage,billingAddressStreet,billingAddressCity,"
                                    "billingAddressState,billingAddressPostalCode,billingAddressCountry")
        return {"kind": "company", "record": c, "stage": c.get("cFunnelStage"), "name": c.get("name") or "",
                "address": Address(name=c.get("name") or "", line1=c.get("billingAddressStreet") or "",
                                   city=c.get("billingAddressCity") or "", state=c.get("billingAddressState") or "",
                                   postal_code=c.get("billingAddressPostalCode") or "",
                                   country=c.get("billingAddressCountry") or "US")}
    if touch.get("contactId"):
        # A list's contact with no Company: the card goes to the person's own
        # address (build plan § 7c.2).
        from .audience import contact_address
        c = await client.get(cfg.CONTACT, touch["contactId"],
                             select="id,name,cFunnelStage,addressStreet,addressCity,addressState,"
                                    "addressPostalCode,addressCountry")
        return {"kind": "contact", "record": c, "stage": c.get("cFunnelStage"), "name": c.get("name") or "",
                "address": contact_address(c)}
    return None


async def run_campaign(client: EspoApi, campaign: dict[str, Any], *, vendor: PostalClient,
                       store, settings: Settings, stop=None) -> dict[str, int]:
    """Execute one signed-off postcard campaign: each Planned touch becomes a
    piece at the vendor, then Sent on the row. Resumable from the first Planned
    row; the vendor's idempotency key is the touch id."""
    totals = {"sent": 0, "failed": 0, "skipped": 0}
    base = (settings.app_base_url or "").rstrip("/")
    if not base:
        log.warning("campaign run %s: APP_BASE_URL is not set; the card's address cannot be built", campaign["id"])
        return totals
    link = await store.landing_link(campaign["id"])
    if link is None:
        link = await store.create_link(
            campaign_id=campaign["id"], name="Postcard landing page",
            destination_kind=cfg.DEST_LANDING, destination_target=None, destination_slug=None,
            created_by="the postcard run",
        )
    if campaign.get("campaignStatus") == cfg.STATUS_SIGNED_OFF:
        await client.update(cfg.CAMPAIGN, campaign["id"],
                            {"campaignStatus": cfg.STATUS_RUNNING, "runStartedAt": _crm_now()})
    touches = [t for t in await service.campaign_touches(client, campaign["id"])
               if t.get("touchStatus") == cfg.TOUCH_PLANNED]
    failures = 0
    for touch in touches[: _RUN_BATCH * 50]:
        if stop is not None and stop.is_set():
            break
        if failures >= _MAX_RUN_FAILURES:
            log.warning("campaign run %s: %s consecutive vendor failures; pausing until the next cycle",
                        campaign["id"], failures)
            break
        try:
            target = await _target_for(client, touch)
            if target is None or not target["address"].is_complete():
                await client.update(cfg.TOUCH, touch["id"], {
                    "touchStatus": cfg.TOUCH_CANCELLED, "vendorStatus": "no mailable address"})
                totals["skipped"] += 1
                continue
            scan = new_scan_token()
            card_url = f"{base}/c/{link['token']}/{scan}"
            piece = await vendor.create_postcard(
                idempotency_key=touch["id"], to=target["address"],
                template=campaign.get("vendorTemplateId") or "",
                size=campaign.get("postcardSize") or "4x6",
                merge_variables={"business_name": target["name"], "card_url": card_url,
                                 "qr_url": f"{card_url}/qr.png"},
                metadata={"touch_id": touch["id"], "campaign_id": campaign["id"]},
            )
            await client.update(cfg.TOUCH, touch["id"], {
                "touchStatus": cfg.TOUCH_SENT, "sentAt": _crm_now(),
                "vendorPieceId": piece.id, "vendorStatus": piece.status,
                "mailedAddress": address_text(target["address"]), "scanToken": scan,
                "stageAtTouch": target.get("stage"),
            })
            totals["sent"] += 1
            failures = 0
        except (PostalError, EspoError) as exc:
            failures += 1
            totals["failed"] += 1
            log.warning("campaign run %s touch %s failed: %s", campaign["id"], touch.get("id"), exc)
    remaining = sum(1 for t in await service.campaign_touches(client, campaign["id"])
                    if t.get("touchStatus") == cfg.TOUCH_PLANNED)
    if remaining == 0:
        await client.update(cfg.CAMPAIGN, campaign["id"],
                            {"campaignStatus": cfg.STATUS_COMPLETE, "runCompletedAt": _crm_now()})
    log.info("campaign run %s: %s (remaining planned %s)", campaign["id"], totals, remaining)
    return totals


async def run_campaign_cycle(settings: Settings, *, client: Optional[EspoApi] = None,
                             vendor: Optional[PostalClient] = None, store=None, stop=None) -> dict[str, int]:
    """One worker pass: every Signed off or Running postcard campaign. Best
    effort, never raises."""
    totals = {"campaigns": 0, "sent": 0, "failed": 0, "skipped": 0, "errors": 0}
    if not settings.campaigns_enabled or settings.espo_dry_run or not settings.store_enabled:
        return totals
    if client is None:
        from core.espo import EspoClient
        client = EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)
    if store is None:
        from .store import make_campaign_store
        store = make_campaign_store(settings)
        if store is None:
            return totals
    vendor = vendor or make_client(settings)
    try:
        page = await client.list(
            cfg.CAMPAIGN, select=cfg.CAMPAIGN_SELECT, max_size=_PAGE,
            where=[
                {"type": "equals", "attribute": "campaignKind", "value": cfg.KIND_POSTCARD},
                {"type": "in", "attribute": "campaignStatus",
                 "value": [cfg.STATUS_SIGNED_OFF, cfg.STATUS_RUNNING]},
            ],
        )
    except EspoError as exc:
        log.warning("campaign run: could not list campaigns: %s", exc)
        totals["errors"] += 1
        return totals
    for campaign in page.get("list", []):
        totals["campaigns"] += 1
        try:
            result = await run_campaign(client, campaign, vendor=vendor, store=store, settings=settings, stop=stop)
            for k in ("sent", "failed", "skipped"):
                totals[k] += result.get(k, 0)
        except Exception as exc:  # noqa: BLE001 — one campaign never stops the others
            totals["errors"] += 1
            log.warning("campaign run %s errored: %s", campaign.get("id"), exc)
    if totals["campaigns"]:
        log.info("campaign run pass: %s", totals)
    return totals


# --- the vendor's events ----------------------------------------------------------------

async def apply_event(client: EspoApi, *, piece_id: str, kind: str, vendor_status: str) -> dict[str, Any]:
    """One delivery event onto its touch (ruling 15). Returns what was written."""
    if not piece_id:
        return {"applied": False, "reason": "no piece id"}
    touch = await client.find_one(cfg.TOUCH, "vendorPieceId", piece_id, select=cfg.TOUCH_SELECT)
    if not touch:
        return {"applied": False, "reason": "no touch carries this piece id"}
    now = _crm_now()
    if kind == EVENT_DELIVERED:
        if touch.get("touchStatus") == cfg.TOUCH_RETURNED:
            return {"applied": False, "reason": "already returned"}
        await client.update(cfg.TOUCH, touch["id"],
                            {"touchStatus": cfg.TOUCH_DELIVERED, "deliveredAt": now, "vendorStatus": vendor_status})
        return {"applied": True, "touchId": touch["id"], "status": cfg.TOUCH_DELIVERED}
    if kind == EVENT_RETURNED:
        await client.update(cfg.TOUCH, touch["id"],
                            {"touchStatus": cfg.TOUCH_RETURNED, "returnedAt": now, "vendorStatus": vendor_status})
        if touch.get("prospectId"):
            # The address died; the status is untouched (ruling 15).
            await client.update(cfg.PROSPECT, touch["prospectId"],
                                {"addressStatus": cfg.ADDRESS_DEAD, "addressDeadAt": now})
        return {"applied": True, "touchId": touch["id"], "status": cfg.TOUCH_RETURNED}
    await client.update(cfg.TOUCH, touch["id"], {"vendorStatus": vendor_status})
    return {"applied": True, "touchId": touch["id"], "status": touch.get("touchStatus")}
