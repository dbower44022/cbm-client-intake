"""Partner application -> Account (Partner) + Contact (Partner) + CPartnerProfile.

Mirrors the client/mentor pattern: an Account for the partner organization, a
Contact for the applicant, and a CPartnerProfile hub linking the two and holding
the partnership-specific data.

INSTANCE MAPPING — reconciled against crm-test.clevelandbusinessmentors.org
(2026-06-17) by reading the deployed EspoCRM metadata:

  * Account.cAccountType (multiEnum, REQUIRED) takes ["Partner"]; the legacy
    Account.cCompanyType is left unset (it has no "Partner" option).
  * Contact.cContactType (multiEnum) takes ["Partner"].
  * CPartnerProfile links: ``partnerCompany`` (belongsTo Account, set via
    ``partnerCompanyId``) and ``primaryPartnercontact`` (belongsTo Contact, set
    via ``primaryPartnercontactId``); the applicant is also added to the
    ``contacts`` hasMany link via a relationship POST (mirrors client-intake's
    ``engagementContacts``).
  * partnershipStatus -> "Candidate" (the inbound-applicant value, mirroring the
    mentor profile's mentorStatus="Candidate"; the enum default is "Meetings Held").

AMBIGUITY (confirm during live verification): CPartnerProfile has TWO belongsTo
Account links, ``partnerCompany`` (foreign cCompanyPartnerProfile) and ``account``
(foreign cPartnerProfile). This writes the clearly-named ``partnerCompany``; if
the deployed layout expects ``account`` instead, switch the FK below.

DEFERRED: partnershipStartDate / partnershipAgreementDate / partnerContactCadence
/ partnerManager and the currency/contribution fields are internal/admin and not
collected by the form.
"""

from __future__ import annotations

import logging

from core.enum_filter import EnumSanitizer
from core.espo import EspoApi
from core.phone import e164_or_none

from .schemas import PartnerApplication

log = logging.getLogger("cbm_intake.partner")

ACCOUNT = "Account"
CONTACT = "Contact"
PARTNER_PROFILE = "CPartnerProfile"

# --- Discriminator attributes (reconciled against the deployed instance) ---
A_ACCOUNT_TYPE = "cAccountType"   # multiEnum on Account — REQUIRED
C_CONTACT_TYPE = "cContactType"   # multiEnum on Contact

# --- CPartnerProfile attributes / links ---
P_COMPANY_LINK = "partnerCompanyId"          # belongsTo Account (FK)
P_PRIMARY_CONTACT_LINK = "primaryPartnercontactId"  # belongsTo Contact (FK)
P_STATUS = "partnershipStatus"               # enum
P_TYPE = "partnershipType"                   # enum
P_VALUE = "partnershipValue"                 # multiEnum
P_DESCRIPTION = "description"                 # text — notes any dropped values
PARTNER_CONTACTS = "contacts"                # CPartnerProfile hasMany Contact

# --- System-set values ---
ACCOUNT_TYPE_PARTNER = "Partner"
CONTACT_TYPE_PARTNER = "Partner"
PARTNERSHIP_STATUS_NEW = "Candidate"


async def _find_or_create_account(sub: PartnerApplication, client: EspoApi) -> str:
    """Find-or-create the partner Account by name and return its id.

    Reusing a same-named Account dedupes repeat submitters and avoids EspoCRM's
    duplicate-detection 409 (same rule as the client-intake form).
    """
    existing = await client.find_one(ACCOUNT, "name", sub.company)
    if existing:
        log.info("matched existing Account %s for %r", existing["id"], sub.company)
        return existing["id"]

    payload: dict = {
        "name": sub.company,
        A_ACCOUNT_TYPE: [ACCOUNT_TYPE_PARTNER],
    }
    if sub.business_website:
        payload["website"] = sub.business_website
    created = await client.create(ACCOUNT, payload)
    return created["id"]


async def _find_or_create_contact(
    sub: PartnerApplication, client: EspoApi, account_id: str
) -> str:
    """Find-or-create the applicant Contact by email and return its id."""
    existing = await client.find_one(CONTACT, "emailAddress", str(sub.email))
    if existing:
        log.info("matched existing Contact %s for %s", existing["id"], sub.email)
        return existing["id"]

    payload: dict = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "accountId": account_id,
        C_CONTACT_TYPE: [CONTACT_TYPE_PARTNER],
    }
    phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
    if phone:
        payload["phoneNumber"] = phone
    created = await client.create(CONTACT, payload)
    return created["id"]


async def _create_partner_profile(
    sub: PartnerApplication, client: EspoApi, account_id: str, contact_id: str
) -> str:
    """Create the CPartnerProfile hub linked to the Account and Contact.

    User-supplied enums (partnershipType/Value) are sanitized against the live CRM
    options — a drifted value is dropped (not fatal) and noted on ``description``
    — so the partner record + contact info are always captured.
    """
    san = EnumSanitizer(client)
    payload: dict = {
        "name": sub.company,
        P_COMPANY_LINK: account_id,
        P_PRIMARY_CONTACT_LINK: contact_id,
        P_STATUS: PARTNERSHIP_STATUS_NEW,
    }
    if sub.partnership_type:
        partnership_type = await san.enum(PARTNER_PROFILE, P_TYPE, sub.partnership_type)
        if partnership_type:
            payload[P_TYPE] = partnership_type
    if sub.partnership_value:
        partnership_value = await san.multi(PARTNER_PROFILE, P_VALUE, sub.partnership_value)
        if partnership_value:
            payload[P_VALUE] = partnership_value
    note = san.note()
    if note:
        payload[P_DESCRIPTION] = note
    created = await client.create(PARTNER_PROFILE, payload)
    return created["id"]


async def submit_partner(sub: PartnerApplication, client: EspoApi) -> dict[str, str]:
    """Run the Account -> Contact -> CPartnerProfile create-and-link sequence.

    Each id is captured as its step succeeds; on a later-step failure the caller
    routes to the failed-submission store and already-created records are kept.
    """
    account_id = await _find_or_create_account(sub, client)
    contact_id = await _find_or_create_contact(sub, client, account_id)
    profile_id = await _create_partner_profile(sub, client, account_id, contact_id)
    # Add the applicant to the profile's Contacts (hasMany), alongside the
    # primaryPartnercontact set on the profile itself.
    await client.relate(PARTNER_PROFILE, profile_id, PARTNER_CONTACTS, contact_id)
    return {
        "accountId": account_id,
        "contactId": contact_id,
        "partnerProfileId": profile_id,
    }
