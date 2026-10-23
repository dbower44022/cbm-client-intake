"""Partner application -> Account (Partner) + Contact (Partner) + CPartnerProfile.

Mirrors the client/mentor pattern: an Account for the partner organization, a
Contact for the applicant, and a CPartnerProfile hub linking the two and holding
the partnership-specific data.

INSTANCE MAPPING — reconciled against crm-test.clevelandbusinessmentors.org
(2026-06-17) by reading the deployed EspoCRM metadata:

  * Account.cCompanyType (multiEnum) takes ["Partner"] — the type discriminator
    on the entity the CRM presents as "Company". (The former cAccountType was
    removed from BOTH instances — verified 2026-07-28.)
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

from core.config import get_settings
from campaigns import attribution as attrib
from campaigns import config as campaign_cfg
from campaigns.attribution import Attribution
from core.crm_upsert import (
    COMPANY_SELECT, CompanyConflict, conflicting_website, fill_company_website,
    find_create_or_fill, merge_company_type, merge_contact_type,
)
from core.enum_filter import EnumSanitizer
from core.espo import EspoApi, EspoError
from core.phone import e164_or_none

from .schemas import PartnerApplication

log = logging.getLogger("cbm_intake.partner")

ACCOUNT = "Account"
CONTACT = "Contact"
PARTNER_PROFILE = "CPartnerProfile"
TEAM = "Team"

# --- Discriminator attributes (reconciled against the deployed instance) ---
A_COMPANY_TYPE = "cCompanyType"   # multiEnum on Account/Company — the type discriminator
C_CONTACT_TYPE = "cContactType"   # multiEnum on Contact
C_HOW_HEARD = "cHowDidYouHear"    # enum on Contact
# The single consent checkbox sets all three Contact bools.
C_TERMS_ACCEPTED = "cTermsOfUseAccepted"       # bool on Contact
C_SMS_OPT_IN = "cSmsOptIn"                     # bool on Contact — texts (ruling 9), true-only
C_PRIVACY_ACCEPTED = "cPrivacyPolicyAccepted"  # bool on Contact
C_CODE_OF_CONDUCT = "cCodeOfConductAccepted"   # bool on Contact

# Contact fields eligible for null-fill on a repeat submission (match key, FK,
# and discriminator excluded so they are never back-written).
_CONTACT_FILL_KEYS = (
    C_SMS_OPT_IN,
    "firstName", "lastName", "phoneNumber", C_HOW_HEARD,
    C_TERMS_ACCEPTED, C_PRIVACY_ACCEPTED, C_CODE_OF_CONDUCT,
)
#: Consent and opt-in boxes: a tick sets True over a stored False, never the
#: reverse (Doug's ruling 10-22-26); an unticked box is simply not sent.
_TRUE_WINS = (C_SMS_OPT_IN, C_TERMS_ACCEPTED, C_PRIVACY_ACCEPTED, C_CODE_OF_CONDUCT)

# --- CPartnerProfile attributes / links ---
P_COMPANY_LINK = "partnerCompanyId"          # belongsTo Account (FK)
P_PRIMARY_CONTACT_LINK = "primaryPartnercontactId"  # belongsTo Contact (FK)
P_STATUS = "partnershipStatus"               # enum
P_TYPE = "partnershipType"                   # enum
P_VALUE = "partnershipValue"                 # multiEnum
P_DESCRIPTION = "description"                 # text — notes any dropped values
PARTNER_CONTACTS = "contacts"                # CPartnerProfile hasMany Contact

# --- System-set values ---
COMPANY_TYPE_PARTNER = "Partner"
CONTACT_TYPE_PARTNER = "Partner"
PARTNERSHIP_STATUS_NEW = "Candidate"


async def _find_or_create_account(
    sub: PartnerApplication, client: EspoApi, attr: Attribution | None = None
) -> str:
    """Find-or-create the partner Account by name and return its id.

    Reusing a same-named Account dedupes repeat submitters and avoids EspoCRM's
    duplicate-detection 409 (same rule as the client-intake form). A prospect
    record's PROMOTED company is used by id before any name match (prospect
    marketing § 5 step 3); typed Prospect, it becomes a Partner through
    ``merge_company_type`` (the § 1.9 relabel).
    """
    attr = attr or Attribution()
    promoted = await attrib.promoted_company(client, attr, select=COMPANY_SELECT)
    if promoted is not None:
        log.info("using converted Account %s from lead %s", promoted["id"],
                 (attr.prospect or {}).get("id"))
        await fill_company_website(client, promoted, sub.business_website)
        await merge_company_type(client, promoted, COMPANY_TYPE_PARTNER)
        return promoted["id"]

    existing = await client.find_one(ACCOUNT, "name", sub.company, select=COMPANY_SELECT)
    if existing:
        log.info("matched existing Account %s for %r", existing["id"], sub.company)
        # Same name at a DIFFERENT web address is a different company: hold
        # for staff before anything is written (company-website-hold-plan.md).
        stored = conflicting_website(existing, sub.business_website)
        if stored:
            raise CompanyConflict(sub.company, existing["id"], stored, sub.business_website or "")
        await fill_company_website(client, existing, sub.business_website)
        # A company CBM knows in another role gains this one (merge-only).
        await merge_company_type(client, existing, COMPANY_TYPE_PARTNER)
        return existing["id"]

    payload: dict = {
        "name": sub.company,
        A_COMPANY_TYPE: [COMPANY_TYPE_PARTNER],
    }
    if sub.business_website:
        payload["website"] = sub.business_website
    # This submission creates the company, so it carries the campaign (ruling 27).
    attrib.stamp_new(payload, attr)
    created = await client.create(ACCOUNT, payload)
    return created["id"]


async def _find_or_create_contact(
    sub: PartnerApplication, client: EspoApi, account_id: str, san: EnumSanitizer,
    attr: Attribution | None = None,
) -> str:
    """Find-or-create the applicant Contact by email and return its id.

    On a repeat email the matched Contact is reused and any *empty* field is
    backfilled — never overwriting curated data (see ``find_create_or_fill``).
    The one exception is the type: a matched Contact typed Prospect gains this
    door's type and loses Prospect (``merge_contact_type``, the § 1.9 relabel).
    A NEW contact carries the campaign it arrived through (ruling 27).
    """
    attr = attr or Attribution()
    payload: dict = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "accountId": account_id,
        C_CONTACT_TYPE: [CONTACT_TYPE_PARTNER],
        C_TERMS_ACCEPTED: bool(sub.terms_accepted),
        C_PRIVACY_ACCEPTED: bool(sub.terms_accepted),
        C_CODE_OF_CONDUCT: bool(sub.terms_accepted),
    }
    phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
    if phone:
        payload["phoneNumber"] = phone
    if sub.how_did_you_hear:
        how_heard = await san.enum(CONTACT, C_HOW_HEARD, sub.how_did_you_hear)
        if how_heard:
            payload[C_HOW_HEARD] = how_heard
    if sub.sms_consent:
        # True-only: an unticked box never flips a prior opt-in (the EV-12 rule).
        payload[C_SMS_OPT_IN] = True
    attrib.stamp_new(payload, attr)

    async def _relabel(existing: dict) -> None:
        await merge_contact_type(client, existing, CONTACT_TYPE_PARTNER)

    contact_id, action = await find_create_or_fill(
        client, CONTACT,
        match_attr="emailAddress", match_value=str(sub.email),
        create_payload=payload, fill_keys=_CONTACT_FILL_KEYS, true_wins=_TRUE_WINS,
        select_extra=(C_CONTACT_TYPE,), on_match=_relabel,
    )
    log.info("Contact %s (%s) for %s", contact_id, action, sub.email)
    return contact_id


async def _partner_team_ids(client: EspoApi) -> list[str]:
    """The Team ids to stamp on a new CPartnerProfile (``PARTNER_TEAM_NAME``).

    New partners carry the Partner Management Team so team-scoped roles see the
    whole partner list in /partnersessions. Best-effort: the team not being
    resolvable (name lookup empty — e.g. the intake API role has no Team read
    grant yet — or the read failing outright) logs a WARNING and returns [],
    so a missing grant can never block a partner application.
    """
    name = get_settings().partner_team_name.strip()
    if not name:
        return []
    try:
        team = await client.find_one(TEAM, "name", name)
    except EspoError as exc:
        log.warning("Team %r lookup failed (%s) — partner profile created "
                    "without a team; grant the intake API role Team read", name, exc)
        return []
    if not team:
        log.warning("Team %r not found/readable — partner profile created "
                    "without a team; grant the intake API role Team read "
                    "(or create the team)", name)
        return []
    return [team["id"]]


async def _create_partner_profile(
    sub: PartnerApplication, client: EspoApi, account_id: str, contact_id: str,
    san: EnumSanitizer, attr: Attribution | None = None,
) -> str:
    """Create the CPartnerProfile hub linked to the Account and Contact.

    User-supplied enums (partnershipType/Value) are sanitized against the live CRM
    options — a drifted value is dropped (not fatal) and noted on ``description``
    — so the partner record + contact info are always captured. The shared ``san``
    spans the whole delivery (Contact + profile).
    """
    payload: dict = {
        "name": sub.company,
        P_COMPANY_LINK: account_id,
        P_PRIMARY_CONTACT_LINK: contact_id,
        P_STATUS: PARTNERSHIP_STATUS_NEW,
    }
    team_ids = await _partner_team_ids(client)
    if team_ids:
        payload["teamsIds"] = team_ids
    if sub.partnership_type:
        partnership_type = await san.enum(PARTNER_PROFILE, P_TYPE, sub.partnership_type)
        if partnership_type:
            payload[P_TYPE] = partnership_type
    if sub.partnership_value:
        partnership_value = await san.multi(PARTNER_PROFILE, P_VALUE, sub.partnership_value)
        if partnership_value:
            payload[P_VALUE] = partnership_value
    attr = attr or Attribution()
    notes: list[str] = []
    if attr.campaign:
        # The campaign lands on the relationship record every time (ruling 27),
        # with the notes line that says the LINK did it (§ 5 step 8).
        payload[attrib.CAMPAIGN_FK] = attr.campaign["id"]
        notes.append(attr.note())
    note = san.note()
    if note:
        notes.append(note)
    if notes:
        payload[P_DESCRIPTION] = "\n".join(notes)
    created = await client.create(PARTNER_PROFILE, payload)
    return created["id"]


async def submit_partner(sub: PartnerApplication, client: EspoApi) -> dict[str, str]:
    """Run the Account -> Contact -> CPartnerProfile create-and-link sequence.

    Each id is captured as its step succeeds; on a later-step failure the caller
    routes to the failed-submission store and already-created records are kept.
    """
    san = EnumSanitizer(client)
    # The campaign id and the prospect id the form carried, validated or
    # dropped (prospect marketing § 5 step 1) — never a reason to lose the lead.
    attr = await attrib.resolve(client, sub, entity=PARTNER_PROFILE)
    account_id = await _find_or_create_account(sub, client, attr)
    contact_id = await _find_or_create_contact(sub, client, account_id, san, attr)
    profile_id = await _create_partner_profile(sub, client, account_id, contact_id, san, attr)
    # Add the applicant to the profile's Contacts (hasMany), alongside the
    # primaryPartnercontact set on the profile itself.
    await client.relate(PARTNER_PROFILE, profile_id, PARTNER_CONTACTS, contact_id)
    # Ruling 48: the lead the form named is Converted, or a new record gets a
    # lead behind it, Converted at once, its Lead Source this form.
    await attrib.record_lead(client, attr, source=campaign_cfg.SOURCE_PARTNER_APPLICATION,
                             company_id=account_id, contact_id=contact_id, values=attrib.lead_values(sub))
    return {
        "accountId": account_id,
        "contactId": contact_id,
        "partnerProfileId": profile_id,
        **attr.result(),
    }
