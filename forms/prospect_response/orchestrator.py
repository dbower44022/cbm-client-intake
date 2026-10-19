"""Deliver a postcard landing-page response (build plan § 4, reworked for the
lead model § 7a; rulings 43, 44, 51, 52).

1. **The corrections go to the lead** (``businessName``, the mailing address;
   ``addressStatus`` back to Usable when the address changed — the person has
   just told us where they are). A website, email or phone the lead lacked is
   filled in.
2. **A response converts the lead when the lead and the response together hold
   a website or an email** (rulings 42-44, 52): a response is first contact,
   so a Qualified lead that already had a website converts on a name alone. Through
   ``campaigns.conversion``: a business lead becomes a Company typed Prospect
   at stage Prospect and the Contact for the email, linked to it; a person lead
   becomes a Contact. The lead is Converted. A same-named company at a
   different web address raises ``CompanyConflict`` and the row holds for
   Submission Admin, exactly as the company-creating forms do.
3. **Neither anywhere → nothing is converted.** The corrections are the whole
   result; the scan changed nothing either (ruling 51).
4. **A card sent to an already-converted lead's Company** (no lead on the
   touch): an email is find-or-created as a Contact linked to that Company.
5. Never a relationship record. The engagement or the information request is
   the standard forms' (rulings 4 and 5).

Runs under the intake API client like every orchestrator. The touch is found by
its scan token; a token that resolves to nothing is a permanent failure (the
row goes to needs_attention and names the reason).
"""

from __future__ import annotations

import logging
from typing import Any

from campaigns import config as cfg
from campaigns.conversion import (
    C_CAMPAIGN, C_CONTACT_TYPE, C_ENTRY_STAGE, C_FUNNEL_STAGE, C_MARKETING_OPT_IN, C_SMS_OPT_IN,
    CONTACT_FILL_KEYS, Details, can_convert, convert_lead,
)
from core.crm_upsert import find_create_or_fill
from core.espo import EspoApi
from core.phone import e164_or_none

from .schemas import ProspectResponse

log = logging.getLogger("cbm_intake.prospect_response")


def _address_changed(lead: dict[str, Any], sub: ProspectResponse) -> bool:
    pairs = (
        ("mailingAddressStreet", sub.mailing_street), ("mailingAddressCity", sub.mailing_city),
        ("mailingAddressState", sub.mailing_state), ("mailingAddressPostalCode", sub.mailing_zip),
    )
    return any(v.strip() and (lead.get(k) or "").strip() != v.strip() for k, v in pairs)


def _details(sub: ProspectResponse) -> Details:
    return Details(
        email=str(sub.email) if sub.email else "", website=sub.website.strip(),
        first_name=sub.first_name.strip(), last_name=sub.last_name.strip(), phone=sub.phone.strip(),
        business_name=sub.business_name.strip(),
        marketing_consent=bool(sub.marketing_consent), sms_consent=bool(sub.sms_consent),
    )


async def orchestrate(sub: ProspectResponse, client: EspoApi) -> dict[str, Any]:
    touch = await client.find_one(cfg.TOUCH, "scanToken", sub.scan_token, select=cfg.TOUCH_SELECT)
    if not touch:
        raise ValueError(f"No postcard carries the token {sub.scan_token!r}; the response cannot be filed.")
    campaign_id = touch.get("outreachCampaignId") or sub.campaign_id or None
    lead = None
    if touch.get("prospectId"):
        lead = await client.get(cfg.PROSPECT, touch["prospectId"], select=cfg.PROSPECT_SELECT)
    result: dict[str, Any] = {"touchId": touch["id"], "campaignId": campaign_id}

    # 1. corrections on the lead
    if lead:
        corrections: dict[str, Any] = {}
        if sub.business_name.strip() and sub.business_name.strip() != (lead.get("businessName") or ""):
            corrections["businessName"] = sub.business_name.strip()[:255]
            corrections["name"] = corrections["businessName"]
        if _address_changed(lead, sub):
            corrections.update({
                "mailingAddressStreet": sub.mailing_street.strip() or None,
                "mailingAddressCity": sub.mailing_city.strip() or None,
                "mailingAddressState": sub.mailing_state.strip() or None,
                "mailingAddressPostalCode": sub.mailing_zip.strip() or None,
                "addressStatus": cfg.ADDRESS_USABLE, "addressDeadAt": None,
            })
        if sub.website.strip() and not lead.get("website"):
            corrections["website"] = sub.website.strip()
        if sub.email and not lead.get("email"):
            corrections["email"] = str(sub.email)
        if sub.phone.strip() and not lead.get("phone"):
            corrections["phone"] = sub.phone.strip()
        if corrections:
            await client.update(cfg.PROSPECT, lead["id"], corrections)
            lead = {**lead, **corrections}
            result["corrected"] = sorted(corrections)
        result["prospectId"] = lead["id"]

        # 2. a website or an email converts the lead (rulings 44, 52)
        details = _details(sub)
        if can_convert(lead, details):
            converted = await convert_lead(client, lead, details, campaign_id=campaign_id)
            result.update(converted.result())
        result["action"] = sub.action
        return result

    # 4. a card to a converted lead's Company: the email is its Contact
    company_id = touch.get("companyId")
    if company_id and sub.email:
        payload: dict[str, Any] = {
            "firstName": sub.first_name.strip()[:100],
            "lastName": (sub.last_name.strip() or sub.business_name.strip() or "Prospect")[:100],
            "emailAddress": str(sub.email),
            C_CONTACT_TYPE: [cfg.CONTACT_TYPE_PROSPECT],
            C_FUNNEL_STAGE: cfg.STAGE_PROSPECT, C_ENTRY_STAGE: cfg.STAGE_PROSPECT,
            "accountId": company_id,
        }
        phone = e164_or_none(sub.phone)
        if phone:
            payload["phoneNumber"] = phone
        if sub.marketing_consent:
            payload[C_MARKETING_OPT_IN] = True
        if sub.sms_consent:
            payload[C_SMS_OPT_IN] = True
        if campaign_id:
            payload[C_CAMPAIGN] = campaign_id
        contact_id, action = await find_create_or_fill(
            client, cfg.CONTACT, match_attr="emailAddress", match_value=str(sub.email),
            create_payload=payload, fill_keys=CONTACT_FILL_KEYS,
        )
        result.update({"companyId": company_id, "contactId": contact_id, "contactCreated": action == "created"})
    result["action"] = sub.action
    return result
