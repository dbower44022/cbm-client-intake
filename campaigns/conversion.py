"""Converting a lead: first contact creates its Company and/or Contact
(build plan § 7a; rulings 43, 44, 47, 52).

One function, :func:`convert_lead`, serves the three places first contact
happens to a lead: a postcard landing-page response, a call marked Interested,
and (through ``attribution``) a public form carrying the lead's id.

* **A website or an email converts; nothing else does** (rulings 44, 47). A
  scan alone converts nothing (ruling 51).
* **A business lead converts to a Company and its Contact** (ruling 52): the
  Company is made from the lead's business name and mailing address even
  without a website, and the Contact for the email is linked to it. A person
  lead (no business name) converts to a Contact only, and only with an email.
* **The Company is matched before it is created**: a converted lead's own
  Company by id first; then by website key; then by name AND postal code —
  the import's already-known rule (ruling 12), so a same-named business in
  another ZIP is a different Company. A same-named, same-ZIP Company at a
  different web address raises :class:`~core.crm_upsert.CompanyConflict`; the
  landing response holds for Submission Admin as the company-creating forms
  do, and the call screen refuses with the existing company named.
* **The Contact is matched by email** (``find_create_or_fill``): a known email
  reuses its Contact, null-filled, its type untouched (ruling 47).
* **A new Company or Contact is typed Prospect at stage Prospect** (rulings
  43, 50) and carries the campaign (ruling 27: this conversion created it).
* **The lead becomes Converted** (ruling 49), stamped, and its *Converted to
  company / contact* links set when empty.

Runs under the intake API client (the Marketing Admin and Mentor Roles create
neither Company nor Contact). Pure of HTTP; the caller decides what a
:class:`ConversionRefused` means on its screen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.crm_upsert import (
    COMPANY_SELECT, CompanyConflict, conflicting_website, create_dropping_invalid,
    find_create_or_fill, website_key,
)
from core.espo import EspoApi
from core.phone import e164_or_none

from . import config as cfg

log = logging.getLogger("cbm_intake.campaigns.conversion")

C_MARKETING_OPT_IN = "cMarketingOptIn"
C_SMS_OPT_IN = "cSmsOptIn"
C_CONTACT_TYPE = "cContactType"
C_FUNNEL_STAGE = "cFunnelStage"
C_ENTRY_STAGE = "cEntryStage"
C_CAMPAIGN = "cOutreachCampaignId"
COMPANY_TYPE = "cCompanyType"

CONTACT_FILL_KEYS = ("firstName", "lastName", "phoneNumber", C_MARKETING_OPT_IN, C_SMS_OPT_IN)


class ConversionRefused(Exception):
    """Neither a website nor an email — the lead stays a lead (ruling 47)."""


@dataclass
class Details:
    """What first contact brought: the typed values, each optional."""

    email: str = ""
    website: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    business_name: str = ""
    marketing_consent: bool = False
    sms_consent: bool = False


@dataclass
class Converted:
    company_id: Optional[str] = None
    contact_id: Optional[str] = None
    company_created: bool = False
    contact_created: bool = False
    lead_converted: bool = False
    notes: list[str] = field(default_factory=list)

    def result(self) -> dict[str, Any]:
        out: dict[str, Any] = {"leadConverted": self.lead_converted}
        if self.company_id:
            out["companyId"] = self.company_id
            out["companyCreated"] = self.company_created
        if self.contact_id:
            out["contactId"] = self.contact_id
            out["contactCreated"] = self.contact_created
        return out


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def is_business(lead: dict[str, Any]) -> bool:
    return bool((lead.get("businessName") or "").strip())


def can_convert(lead: dict[str, Any], details: Details) -> bool:
    """Ruling 47: an email converts any lead; a website converts a business
    lead. A person lead with a website and no email has nothing to create."""
    email = (details.email or lead.get("email") or "").strip()
    website = (details.website or lead.get("website") or "").strip()
    if email:
        return True
    return bool(website) and is_business(lead)


async def find_company(client: EspoApi, *, name: str, postal_code: str, website: str) -> Optional[dict[str, Any]]:
    """The Company this business already is, or None. Website key first, then
    name AND postal code (a Company with no stored ZIP matches on the name
    alone — nothing says it is elsewhere). A same-named Company that matches
    at a different web address raises :class:`CompanyConflict`."""
    key = website_key(website) if website else ""
    if key:
        page = await client.list(cfg.ACCOUNT, select=COMPANY_SELECT + ",billingAddressPostalCode", max_size=50,
                                 where=[{"type": "contains", "attribute": "website", "value": key.split("/")[0]}])
        for c in page.get("list", []):
            if website_key(c.get("website")) == key:
                return c
    zip5 = (postal_code or "")[:5]
    if name:
        page = await client.list(cfg.ACCOUNT, select=COMPANY_SELECT + ",billingAddressPostalCode", max_size=20,
                                 where=[{"type": "equals", "attribute": "name", "value": name}])
        for c in page.get("list", []):
            stored_zip = (c.get("billingAddressPostalCode") or "")[:5]
            if zip5 and stored_zip and stored_zip != zip5:
                continue      # a same-named business in another ZIP is another Company
            if website:
                stored = conflicting_website(c, website)
                if stored:
                    raise CompanyConflict(name, c["id"], stored, website)
            return c
    return None


async def convert_lead(client: EspoApi, lead: dict[str, Any], details: Details, *,
                       campaign_id: Optional[str] = None,
                       stage: str = cfg.STAGE_PROSPECT) -> Converted:
    """Convert ``lead`` (a ``cfg.PROSPECT_SELECT`` read). Raises
    :class:`ConversionRefused` when there is neither a website nor an email,
    and :class:`CompanyConflict` on a same-named company at another address.
    Writes nothing before deciding it can convert."""
    if not can_convert(lead, details):
        raise ConversionRefused(
            "A lead converts only with an email or a website (ruling 47); it stays a lead.")
    out = Converted()
    email = (details.email or "").strip().lower() or (lead.get("email") or "").strip().lower()
    website = (details.website or "").strip() or (lead.get("website") or "").strip()
    business = (details.business_name or "").strip() or (lead.get("businessName") or "").strip()

    # The business first, so the Contact can link to it (ruling 52).
    if is_business(lead) or details.business_name.strip():
        company_id = lead.get("promotedCompanyId")
        if not company_id:
            existing = await find_company(client, name=business, website=website,
                                          postal_code=lead.get("mailingAddressPostalCode") or "")
            if existing is None:
                payload: dict[str, Any] = {
                    "name": business[:255] or website_key(website) or "Business",
                    "website": website or None,
                    COMPANY_TYPE: [cfg.COMPANY_TYPE_PROSPECT],
                    C_FUNNEL_STAGE: stage, C_ENTRY_STAGE: stage,
                    "billingAddressStreet": lead.get("mailingAddressStreet"),
                    "billingAddressCity": lead.get("mailingAddressCity"),
                    "billingAddressState": lead.get("mailingAddressState"),
                    "billingAddressPostalCode": lead.get("mailingAddressPostalCode"),
                    "billingAddressCountry": lead.get("mailingAddressCountry") or "US",
                    C_CAMPAIGN: campaign_id,
                }
                created = await client.create(cfg.ACCOUNT, {k: v for k, v in payload.items() if v})
                company_id = created["id"]
                out.company_created = True
            else:
                company_id = existing["id"]
                fill: dict[str, Any] = {}
                if website and not existing.get("website"):
                    fill["website"] = website
                if not (existing.get(COMPANY_TYPE) or []):
                    fill[COMPANY_TYPE] = [cfg.COMPANY_TYPE_PROSPECT]
                if fill:
                    await client.update(cfg.ACCOUNT, company_id, fill)
        out.company_id = company_id

    if email:
        first = (details.first_name or lead.get("firstName") or "").strip()
        last = (details.last_name or lead.get("lastName") or "").strip() or business or "Prospect"
        payload = {
            "firstName": first[:100],
            "lastName": last[:100],
            "emailAddress": email,
            C_CONTACT_TYPE: [cfg.CONTACT_TYPE_PROSPECT],
            C_FUNNEL_STAGE: stage, C_ENTRY_STAGE: stage,
        }
        phone = e164_or_none(details.phone or lead.get("phone") or "")
        if phone:
            payload["phoneNumber"] = phone
        # Consent is written true-only: an unticked box never flips a prior opt-in.
        if details.marketing_consent:
            payload[C_MARKETING_OPT_IN] = True
        if details.sms_consent:
            payload[C_SMS_OPT_IN] = True
        if out.company_id:
            payload["accountId"] = out.company_id
        if campaign_id:
            payload[C_CAMPAIGN] = campaign_id
        contact_id, action = await find_create_or_fill(
            client, cfg.CONTACT, match_attr="emailAddress", match_value=email,
            create_payload=payload, fill_keys=CONTACT_FILL_KEYS,
        )
        out.contact_id = contact_id
        out.contact_created = action == "created"

    await mark_converted(client, lead, company_id=out.company_id, contact_id=out.contact_id)
    out.lead_converted = True
    return out


async def mark_converted(client: EspoApi, lead: dict[str, Any], *, company_id: Optional[str] = None,
                         contact_id: Optional[str] = None) -> dict[str, Any]:
    """The lead's side of a conversion: Converted, stamped (once), and its
    *Converted to* links set when empty. Returns what was written."""
    fill: dict[str, Any] = {}
    if lead.get("leadStatus") != cfg.LEAD_CONVERTED:
        fill["leadStatus"] = cfg.LEAD_CONVERTED
        fill["leadStatusChangedAt"] = _now_crm()
    if company_id and not lead.get("promotedCompanyId"):
        fill["promotedCompanyId"] = company_id
    if contact_id and not lead.get("promotedContactId"):
        fill["promotedContactId"] = contact_id
    if fill:
        await client.update(cfg.PROSPECT, lead["id"], fill)
    # § 7d.1: one code per person — the Contact takes the lead's (never a second).
    from .leadcode import sync_on_conversion
    await sync_on_conversion(client, lead["id"], contact_id or lead.get("promotedContactId"))
    return fill
