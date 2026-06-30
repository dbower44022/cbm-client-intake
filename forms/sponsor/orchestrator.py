"""Sponsor application -> Account (Donor/Sponsor) + Contact (Sponsor) + CSponsorProfile.

Mirrors the partner/mentor pattern: an Account for the sponsoring organization,
a Contact for the applicant, and a CSponsorProfile hub linking the two.

INSTANCE MAPPING — reconciled against crm-test.clevelandbusinessmentors.org
(2026-06-17) by reading the deployed EspoCRM metadata:

  * Account.cAccountType (multiEnum, REQUIRED) takes ["Donor/Sponsor"].
  * Contact.cContactType (multiEnum) takes ["Sponsor"] — option added to the CRM
    2026-06-22 (previously ["Donor"] as the nearest fit). The CRM enum is the
    source of truth; the app writes exactly what it expects.
  * CSponsorProfile links: ``sponsorCompany`` (belongsTo Account, set via
    ``sponsorCompanyId``) and ``sponsorContact`` (belongsTo Contact, set via
    ``sponsorContactId``); the applicant is also added to the ``sponsorContacts``
    hasMany link via a relationship POST.
  * The applicant's message is stored on CSponsorProfile.description.

DEFERRED: totalContribution / lastContribution and the sponsor-manager links are
internal/admin (staff fill them later) and are not collected by the form.
"""

from __future__ import annotations

import logging

from core.crm_upsert import find_create_or_fill
from core.enum_filter import EnumSanitizer
from core.espo import EspoApi
from core.phone import e164_or_none

from .schemas import SponsorApplication

log = logging.getLogger("cbm_intake.sponsor")

ACCOUNT = "Account"
CONTACT = "Contact"
SPONSOR_PROFILE = "CSponsorProfile"

# --- Discriminator attributes (reconciled against the deployed instance) ---
A_ACCOUNT_TYPE = "cAccountType"   # multiEnum on Account — REQUIRED
C_CONTACT_TYPE = "cContactType"   # multiEnum on Contact
C_HOW_HEARD = "cHowDidYouHear"    # enum on Contact

# Contact fields eligible for null-fill on a repeat submission (match key, FK,
# and discriminator excluded so they are never back-written).
_CONTACT_FILL_KEYS = ("firstName", "lastName", "phoneNumber", C_HOW_HEARD)

# --- CSponsorProfile attributes / links ---
S_COMPANY_LINK = "sponsorCompanyId"   # belongsTo Account (FK)
S_CONTACT_LINK = "sponsorContactId"   # belongsTo Contact (FK)
SPONSOR_CONTACTS = "sponsorContacts"  # CSponsorProfile hasMany Contact

# --- System-set values ---
ACCOUNT_TYPE_SPONSOR = "Donor/Sponsor"
CONTACT_TYPE_SPONSOR = "Sponsor"


async def _find_or_create_account(sub: SponsorApplication, client: EspoApi) -> str:
    """Find-or-create the sponsor Account by name and return its id.

    Reusing a same-named Account dedupes repeat submitters and avoids EspoCRM's
    duplicate-detection 409 (same rule as the client-intake form).
    """
    existing = await client.find_one(ACCOUNT, "name", sub.company)
    if existing:
        log.info("matched existing Account %s for %r", existing["id"], sub.company)
        return existing["id"]

    payload: dict = {
        "name": sub.company,
        A_ACCOUNT_TYPE: [ACCOUNT_TYPE_SPONSOR],
    }
    if sub.business_website:
        payload["website"] = sub.business_website
    created = await client.create(ACCOUNT, payload)
    return created["id"]


async def _find_or_create_contact(
    sub: SponsorApplication, client: EspoApi, account_id: str, san: EnumSanitizer
) -> str:
    """Find-or-create the applicant Contact by email and return its id.

    On a repeat email the matched Contact is reused and any *empty* field is
    backfilled — never overwriting curated data (see ``find_create_or_fill``).
    """
    payload: dict = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "accountId": account_id,
        C_CONTACT_TYPE: [CONTACT_TYPE_SPONSOR],
    }
    phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
    if phone:
        payload["phoneNumber"] = phone
    if sub.how_did_you_hear:
        how_heard = await san.enum(CONTACT, C_HOW_HEARD, sub.how_did_you_hear)
        if how_heard:
            payload[C_HOW_HEARD] = how_heard
    contact_id, action = await find_create_or_fill(
        client, CONTACT,
        match_attr="emailAddress", match_value=str(sub.email),
        create_payload=payload, fill_keys=_CONTACT_FILL_KEYS,
    )
    log.info("Contact %s (%s) for %s", contact_id, action, sub.email)
    return contact_id


async def _create_sponsor_profile(
    sub: SponsorApplication, client: EspoApi, account_id: str, contact_id: str
) -> str:
    """Create the CSponsorProfile hub linked to the Account and Contact."""
    payload: dict = {
        "name": sub.company,
        S_COMPANY_LINK: account_id,
        S_CONTACT_LINK: contact_id,
        "description": sub.message.strip(),
    }
    created = await client.create(SPONSOR_PROFILE, payload)
    return created["id"]


async def submit_sponsor(sub: SponsorApplication, client: EspoApi) -> dict[str, str]:
    """Run the Account -> Contact -> CSponsorProfile create-and-link sequence.

    Each id is captured as its step succeeds; on a later-step failure the caller
    routes to the failed-submission store and already-created records are kept.
    """
    san = EnumSanitizer(client)
    account_id = await _find_or_create_account(sub, client)
    contact_id = await _find_or_create_contact(sub, client, account_id, san)
    profile_id = await _create_sponsor_profile(sub, client, account_id, contact_id)
    # Add the applicant to the profile's Contacts (hasMany), alongside the
    # sponsorContact set on the profile itself.
    await client.relate(SPONSOR_PROFILE, profile_id, SPONSOR_CONTACTS, contact_id)
    return {
        "accountId": account_id,
        "contactId": contact_id,
        "sponsorProfileId": profile_id,
    }
