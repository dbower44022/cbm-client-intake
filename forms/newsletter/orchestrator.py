"""Newsletter signup -> Contact with marketing consent (ruling 43).

  * Contact — find by email. A NEW contact is typed Prospect, carries the
    campaign (ruling 27) and enters the funnel at Engaged, as the information
    request does: the person gave their details to receive something.
  * An EXISTING contact gains the consent — a ticked box sets
    ``cMarketingOptIn`` true over a stored false, never the reverse (Doug's
    ruling 10-22-26) — and an empty first or last name is filled. Nothing
    else about a known person changes: their type is curated data.
  * Ruling 48: a new record gets a lead behind it, Converted at once, Lead
    Source "Newsletter signup", with the website button that brought them.

The mailing-list synchronisation (core/mailing_sync.py) reads
``cMarketingOptIn`` and passes the contact to the mailing service.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from campaigns import attribution as attrib
from campaigns import config as campaign_cfg
from core.crm_upsert import create_dropping_invalid
from core.espo import EspoApi

from .schemas import NewsletterSignup

log = logging.getLogger("cbm_intake.orchestrator")

CONTACT = "Contact"
C_CONTACT_TYPE = "cContactType"
C_MARKETING_OPT_IN = "cMarketingOptIn"
PROSPECT = "Prospect"
ENGAGED = campaign_cfg.STAGE_ENGAGED


async def submit_signup(sub: NewsletterSignup, client: EspoApi) -> dict[str, str]:
    attr = await attrib.resolve(client, sub, entity=CONTACT)
    existing = await client.find_one(
        CONTACT, "emailAddress", str(sub.email),
        select=f"id,firstName,lastName,{C_MARKETING_OPT_IN},{attrib.FUNNEL_STAGE}",
    )
    if existing:
        contact_id = existing["id"]
        update: dict = {}
        if not existing.get(C_MARKETING_OPT_IN):
            update[C_MARKETING_OPT_IN] = True
        if not (existing.get("firstName") or "").strip():
            update["firstName"] = sub.first_name
        if not (existing.get("lastName") or "").strip():
            update["lastName"] = sub.last_name
        if update:
            await client.update(CONTACT, contact_id, update)
            log.info("newsletter signup updated Contact %s: %s", contact_id, sorted(update))
        if await attrib.rung_available(client, CONTACT):
            await attrib.advance_rung(client, CONTACT, existing, ENGAGED)
    else:
        payload: dict = {
            "firstName": sub.first_name,
            "lastName": sub.last_name,
            "emailAddress": str(sub.email),
            C_CONTACT_TYPE: [PROSPECT],
            C_MARKETING_OPT_IN: True,
            "description": f"[Newsletter signup via website — {datetime.now(timezone.utc):%Y-%m-%d}]",
        }
        stage = ENGAGED if await attrib.rung_available(client, CONTACT) else None
        attrib.stamp_new(payload, attr, stage=stage)
        created = await create_dropping_invalid(client, CONTACT, payload)
        contact_id = created["id"]

    await attrib.record_lead(client, attr, source=campaign_cfg.SOURCE_NEWSLETTER, contact_id=contact_id,
                             values=attrib.lead_values(sub))
    return {"contactId": contact_id, **attr.result()}
