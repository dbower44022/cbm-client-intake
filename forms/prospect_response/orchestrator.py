"""Deliver a postcard landing-page response (build plan § 4, the five steps).

1. The corrections go to the prospect record (``businessName``, the mailing
   address; ``addressStatus`` back to Usable when the address changed — the
   person has just told us where they are).
2. **Email given → the person is promoted** (ruling 21): find-or-create the
   Contact by email; a new one is typed Prospect, carries the stage fields copied
   from the prospect record, the consent ticks and the campaign (ruling 27: this
   submission created it); an existing one is null-filled, keeps its type, and
   gets the ticks written true-only. ``promotedContact`` is set if empty.
3. **Website given → the business is promoted** (ruling 21): match by website
   key, then by name; a same-named company at a different web address raises
   ``CompanyConflict`` and the row holds for Submission Admin, exactly as the
   company-creating forms do. A new Company is typed Prospect; a matched one is
   null-filled and gains ``Prospect`` only if it holds no type at all.
4. **Neither given → nothing is promoted.** The corrections and the scan are the
   whole result.
5. Never a relationship record. The engagement or the information request is
   the standard forms' (rulings 4 and 5).

Runs under the intake API client like every orchestrator. The touch is found by
its scan token; a token that resolves to nothing is a permanent failure (the
row goes to needs_attention and names the reason).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from campaigns import config as cfg
from campaigns.service import advance_stage
from core.crm_upsert import (
    COMPANY_SELECT, CompanyConflict, conflicting_website, create_dropping_invalid,
    find_create_or_fill, website_key,
)
from core.espo import EspoApi
from core.phone import e164_or_none

from .schemas import ProspectResponse

log = logging.getLogger("cbm_intake.prospect_response")

C_MARKETING_OPT_IN = "cMarketingOptIn"
C_SMS_OPT_IN = "cSmsOptIn"
C_CONTACT_TYPE = "cContactType"
C_FUNNEL_STAGE = "cFunnelStage"
C_ENTRY_STAGE = "cEntryStage"
C_CAMPAIGN = "cOutreachCampaignId"
COMPANY_TYPE = "cCompanyType"

_CONTACT_FILL_KEYS = ("firstName", "lastName", "phoneNumber", C_MARKETING_OPT_IN, C_SMS_OPT_IN)


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _address_changed(prospect: dict[str, Any], sub: ProspectResponse) -> bool:
    pairs = (
        ("mailingAddressStreet", sub.mailing_street), ("mailingAddressCity", sub.mailing_city),
        ("mailingAddressState", sub.mailing_state), ("mailingAddressPostalCode", sub.mailing_zip),
    )
    return any(v.strip() and (prospect.get(k) or "").strip() != v.strip() for k, v in pairs)


async def orchestrate(sub: ProspectResponse, client: EspoApi) -> dict[str, Any]:
    touch = await client.find_one(cfg.TOUCH, "scanToken", sub.scan_token, select=cfg.TOUCH_SELECT)
    if not touch:
        raise ValueError(f"No postcard carries the token {sub.scan_token!r}; the response cannot be filed.")
    campaign_id = touch.get("outreachCampaignId") or sub.campaign_id or None
    prospect = None
    if touch.get("prospectId"):
        prospect = await client.get(cfg.PROSPECT, touch["prospectId"], select=cfg.PROSPECT_SELECT)
    result: dict[str, Any] = {"touchId": touch["id"], "campaignId": campaign_id}
    stage = (prospect or {}).get("funnelStage") or cfg.STAGE_LEAD
    entry = (prospect or {}).get("entryStage") or stage

    # 1. corrections on the prospect record
    if prospect:
        corrections: dict[str, Any] = {}
        if sub.business_name.strip() and sub.business_name.strip() != (prospect.get("businessName") or ""):
            corrections["businessName"] = sub.business_name.strip()[:255]
            corrections["name"] = corrections["businessName"]
        if _address_changed(prospect, sub):
            corrections.update({
                "mailingAddressStreet": sub.mailing_street.strip() or None,
                "mailingAddressCity": sub.mailing_city.strip() or None,
                "mailingAddressState": sub.mailing_state.strip() or None,
                "mailingAddressPostalCode": sub.mailing_zip.strip() or None,
                "addressStatus": cfg.ADDRESS_USABLE, "addressDeadAt": None,
            })
        if sub.website.strip() and not prospect.get("website"):
            corrections["website"] = sub.website.strip()
        if sub.email and not prospect.get("email"):
            corrections["email"] = str(sub.email)
        if sub.phone.strip() and not prospect.get("phone"):
            corrections["phone"] = sub.phone.strip()
        if corrections:
            await client.update(cfg.PROSPECT, prospect["id"], corrections)
            result["corrected"] = sorted(corrections)
        result["prospectId"] = prospect["id"]

    # 3. website → the business (done before the person so the Contact can link to it)
    company_id = (prospect or {}).get("promotedCompanyId") or touch.get("companyId")
    if sub.website.strip() and not company_id:
        name = sub.business_name.strip() or (prospect or {}).get("businessName") or ""
        key = website_key(sub.website)
        existing = None
        if key:
            page = await client.list(cfg.ACCOUNT, select=COMPANY_SELECT, max_size=50,
                                     where=[{"type": "contains", "attribute": "website", "value": key.split("/")[0]}])
            for c in page.get("list", []):
                if website_key(c.get("website")) == key:
                    existing = c
                    break
        if existing is None and name:
            existing = await client.find_one(cfg.ACCOUNT, "name", name, select=COMPANY_SELECT)
            if existing is not None:
                stored = conflicting_website(existing, sub.website)
                if stored:
                    raise CompanyConflict(name, existing["id"], stored, sub.website)
        if existing is None:
            payload: dict[str, Any] = {
                "name": name[:255] or key, "website": sub.website.strip(),
                COMPANY_TYPE: [cfg.COMPANY_TYPE_PROSPECT],
                C_FUNNEL_STAGE: stage, C_ENTRY_STAGE: entry,
            }
            if prospect:
                payload.update({
                    "billingAddressStreet": prospect.get("mailingAddressStreet"),
                    "billingAddressCity": prospect.get("mailingAddressCity"),
                    "billingAddressState": prospect.get("mailingAddressState"),
                    "billingAddressPostalCode": prospect.get("mailingAddressPostalCode"),
                    "billingAddressCountry": prospect.get("mailingAddressCountry") or "US",
                })
            if campaign_id:
                payload[C_CAMPAIGN] = campaign_id
            created = await client.create(cfg.ACCOUNT, {k: v for k, v in payload.items() if v})
            company_id = created["id"]
            result["companyCreated"] = True
        else:
            company_id = existing["id"]
            fill: dict[str, Any] = {}
            if not existing.get("website"):
                fill["website"] = sub.website.strip()
            if not (existing.get(COMPANY_TYPE) or []):
                fill[COMPANY_TYPE] = [cfg.COMPANY_TYPE_PROSPECT]
            if fill:
                await client.update(cfg.ACCOUNT, existing["id"], fill)
        result["companyId"] = company_id
        if prospect and not prospect.get("promotedCompanyId"):
            await client.update(cfg.PROSPECT, prospect["id"], {"promotedCompanyId": company_id})

    # 2. email → the person
    if sub.email:
        payload = {
            "firstName": sub.first_name.strip()[:100],
            "lastName": (sub.last_name.strip() or sub.business_name.strip() or "Prospect")[:100],
            "emailAddress": str(sub.email),
            C_CONTACT_TYPE: [cfg.CONTACT_TYPE_PROSPECT],
            C_FUNNEL_STAGE: stage, C_ENTRY_STAGE: entry,
        }
        phone = e164_or_none(sub.phone)
        if phone:
            payload["phoneNumber"] = phone
        # Consent is written true-only: an unticked box never flips a prior opt-in.
        if sub.marketing_consent:
            payload[C_MARKETING_OPT_IN] = True
        if sub.sms_consent:
            payload[C_SMS_OPT_IN] = True
        if company_id:
            payload["accountId"] = company_id
        if campaign_id:
            payload[C_CAMPAIGN] = campaign_id
        contact_id, action = await find_create_or_fill(
            client, cfg.CONTACT, match_attr="emailAddress", match_value=str(sub.email),
            create_payload=payload, fill_keys=_CONTACT_FILL_KEYS,
        )
        result["contactId"] = contact_id
        result["contactCreated"] = action == "created"
        if prospect and not prospect.get("promotedContactId"):
            await client.update(cfg.PROSPECT, prospect["id"], {"promotedContactId": contact_id})

    # the rung: a response is a scan's evidence too (ruling 16), advance-only
    if prospect:
        new_stage = advance_stage(prospect.get("funnelStage"), cfg.STAGE_LEAD)
        if new_stage:
            await client.update(cfg.PROSPECT, prospect["id"], {"funnelStage": new_stage, "stageChangedAt": _now_crm()})
    result["action"] = sub.action
    return result
