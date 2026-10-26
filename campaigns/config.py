"""The CRM names and the declared field specs for Campaign Management.

Every name here is the STORED name from ``scripts/plans/coutreach-entities.json``
as applied on crm-test 10-15-26 (``coutreach-entities-crm-handoff.md`` § 5).
One declared spec serves as both the form layout and the write whitelist, the
house pattern; enum options are read live from CRM metadata, never copied here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# --- entities -----------------------------------------------------------------
CAMPAIGN = "COutreachCampaign"
PROSPECT = "CProspect"
TOUCH = "COutreachTouch"
PARTNER_PROFILE = "CPartnerProfile"
SPONSOR_PROFILE = "CSponsorProfile"
EVENT = "CEvent"
ACCOUNT = "Account"
CONTACT = "Contact"

# --- relationships on the campaign (read through list_related, written with
# relate / unrelate, never through a *Ids attribute) ---------------------------
LINK_PARTNERS = "partnerProfiles"       # CM-2, reverse CPartnerProfile.sponsoredCampaigns
LINK_EVENTS = "events"                  # CM-6, reverse CEvent.outreachCampaigns
#: Ruling 57: the funders a campaign names (CM-2's twin), reverse
#: CSponsorProfile.sponsoredCampaigns. Feature-detected: a CRM without the
#: link (scripts/plans/coutreach-funders.json) shows no Funders picker.
#: (COutreachCampaign.sponsorProfiles is the ruling-27 attribution reverse.)
LINK_FUNDERS = "funderProfiles"
LINK_TOUCHES = "touches"

# --- campaign kinds and statuses (build plan § 1.3; the CRM enum is the truth,
# these are the values the application writes) --------------------------------
KIND_POSTCARD = "Postcard"
KIND_EMAIL = "Email"
KIND_SMS = "SMS"
KIND_CALL = "Call"
KIND_SOCIAL = "Social media"
SELECTING_KINDS = (KIND_POSTCARD, KIND_EMAIL, KIND_SMS, KIND_CALL)
#: Phase 1 builds the postcard and the social kind; the rest are offered on the
#: screen only when their phase lands.
PHASE_1_KINDS = (KIND_POSTCARD, KIND_SOCIAL)
#: Phase 3 adds the call kind, behind CAMPAIGNS_CALLS.
CALL_KINDS = (KIND_CALL,)
#: Phase 4 adds the text-message kind, behind CAMPAIGNS_SMS (rulings 38, 39).
SMS_KINDS = (KIND_SMS,)
EMAIL_KINDS = (KIND_EMAIL,)


def kinds_built(calls_on: bool, sms_on: bool = False, email_on: bool = False) -> tuple[str, ...]:
    """The kinds a campaign may be created as on this deployment."""
    return (PHASE_1_KINDS + (CALL_KINDS if calls_on else ()) + (SMS_KINDS if sms_on else ())
            + (EMAIL_KINDS if email_on else ()))

STATUS_DRAFT = "Draft"
STATUS_AWAITING = "Awaiting sign-off"
STATUS_SIGNED_OFF = "Signed off"
STATUS_RUNNING = "Running"
STATUS_COMPLETE = "Complete"
STATUS_CANCELLED = "Cancelled"

# --- touches (§ 1.4) ----------------------------------------------------------
TOUCH_PLANNED = "Planned"
TOUCH_SENT = "Sent"
TOUCH_DELIVERED = "Delivered"
TOUCH_RETURNED = "Returned"
TOUCH_DONE = "Done"
TOUCH_CANCELLED = "Cancelled"
OUTCOME_SCANNED = "Scanned"
#: A personal link opened from an email, a text or a call follow-up (§ 7d.3).
OUTCOME_CLICKED = "Clicked"
#: Ruling 20's three call outcomes (§ 3.4).
OUTCOME_NO_ANSWER = "No answer"
OUTCOME_INTERESTED = "Interested"
OUTCOME_DECLINED = "Declined"
CALL_OUTCOMES = (OUTCOME_NO_ANSWER, OUTCOME_INTERESTED, OUTCOME_DECLINED)
#: Personal outreach from the lead's page (build plan § 7e.5; rulings 107-109,
#: 115, 119): a touch with no campaign, on one of these two channels.
KIND_PERSONAL_CALL = "Personal call"
KIND_PERSONAL_EMAIL = "Personal email"
PERSONAL_KINDS = (KIND_PERSONAL_CALL, KIND_PERSONAL_EMAIL)
#: Ruling 108's three outcomes of a personal call, in the screen's words. The
#: touch's ``outcome`` enum carries the campaign calls' words (read from
#: crm-test 10-25-26: No answer, Interested, Declined), so each is STORED as
#: the campaign call's equivalent — ruling 115: the same kind of call with the
#: same outcomes, one vocabulary on the record.
OUTCOME_NOT_INTERESTED = "Not interested"
OUTCOME_NO_REPLY = "No reply yet"
PERSONAL_CALL_OUTCOMES = (OUTCOME_INTERESTED, OUTCOME_NOT_INTERESTED, OUTCOME_NO_REPLY)
PERSONAL_OUTCOME_STORED = {
    OUTCOME_INTERESTED: OUTCOME_INTERESTED,
    OUTCOME_NOT_INTERESTED: OUTCOME_DECLINED,
    OUTCOME_NO_REPLY: OUTCOME_NO_ANSWER,
}

# --- leads (rulings 41-52; build plan § 7a) -------------------------------------
#: A lead's status (``CProspect.leadStatus``, ruling 49). Every lead starts
#: Unqualified; a business lead with no website, or a person lead with no
#: email, can never be Qualified (ruling 42). Converted: first contact created
#: its Company and/or Contact (ruling 43).
LEAD_UNQUALIFIED = "Unqualified"
LEAD_QUALIFIED = "Qualified"
LEAD_DISQUALIFIED = "Disqualified"
LEAD_CONVERTED = "Converted"
LEAD_STATUSES = (LEAD_UNQUALIFIED, LEAD_QUALIFIED, LEAD_DISQUALIFIED, LEAD_CONVERTED)
#: The statuses a lead is still worked at — selectable by a postcard or a call
#: campaign (ruling 44) and swept by the Stale sweep.
LEAD_OPEN_STATUSES = (LEAD_UNQUALIFIED, LEAD_QUALIFIED)

#: The level inside Qualified (``CProspect.qualificationLevel``; rulings 105,
#: 106; build plan § 7e.3). Empty unless the lead is Qualified. Identified: a
#: real business, no named person or direct line. Contactable: a named person
#: and a phone or an email. Referred: a referrer and a phone or an email. The
#: rule is ``campaigns/ladder.py``; the level never moves backwards.
LEVEL_IDENTIFIED = "Identified"
LEVEL_CONTACTABLE = "Contactable"
LEVEL_REFERRED = "Referred"
LEVELS = (LEVEL_IDENTIFIED, LEVEL_CONTACTABLE, LEVEL_REFERRED)
LEVEL_RANK = {lv: i + 1 for i, lv in enumerate(LEVELS)}

# --- a Company's or Contact's stages after first contact (ruling 50) -----------
#: ``cFunnelStage`` / ``cEntryStage`` on Contact and Account. Candidate and
#: Client are read from the engagement, never stored here.
STAGE_PROSPECT = "Prospect"
STAGE_ENGAGED = "Engaged"
STAGE_OPPORTUNITY = "Opportunity"
STAGES = (STAGE_PROSPECT, STAGE_ENGAGED, STAGE_OPPORTUNITY)
#: Advance-only: a stage is written only when it is later than the stored one.
STAGE_RANK = {s: i for i, s in enumerate(STAGES)}
#: What a touch records as the target's position when it leaves Planned: the
#: lead's status for a lead, the stage for a Company or Contact.
TOUCH_POSITIONS = LEAD_OPEN_STATUSES + STAGES

ADDRESS_USABLE = "Usable"
ADDRESS_DEAD = "Dead"

#: ``CProspect.leadSource`` (rulings 41, 48): the three imports, then the
#: public forms, event registration and the info mailbox.
SOURCE_FILING = "State filing"
SOURCE_LIST = "List"
SOURCE_PARTNER_FILE = "Partner file"
IMPORT_SOURCES = (SOURCE_FILING, SOURCE_LIST, SOURCE_PARTNER_FILE)
SOURCE_MENTOR_REQUEST = "Mentor request"
SOURCE_VOLUNTEER = "Volunteer application"
SOURCE_INFO_REQUEST = "Information request"
SOURCE_PARTNER_APPLICATION = "Partner application"
SOURCE_FUNDER_APPLICATION = "Funder application"
SOURCE_EVENT_REGISTRATION = "Event registration"
SOURCE_EMAIL = "Email"

#: The reasons a lead stops being worked (``sideExit``, ruling 50).
#: Disqualified is a status, not a reason.
EXIT_DUPLICATE = "Duplicate"
EXIT_DO_NOT_CONTACT = "Do Not Contact"
EXIT_DECLINED = "Declined"
EXIT_STALE = "Stale"

#: The type a converted Company or Contact carries (ruling 43).
COMPANY_TYPE_PROSPECT = "Prospect"
CONTACT_TYPE_PROSPECT = "Prospect"

# --- the fields the screens read ----------------------------------------------
CAMPAIGN_SELECT = (
    "id,name,campaignKind,platform,campaignStatus,selectionRule,selectionSummary,"
    "pieceCount,estimatedCost,estimatedCostCurrency,signedOffByName,signedOffAt,"
    "startDate,endDate,vendorTemplateId,postcardSize,runStartedAt,runCompletedAt,"
    "description,assignedUserId,assignedUserName,createdAt,modifiedAt"
)
PROSPECT_SELECT = (
    "id,name,businessName,firstName,lastName,mailingAddressStreet,mailingAddressCity,"
    "mailingAddressState,mailingAddressPostalCode,mailingAddressCountry,addressStatus,"
    "addressDeadAt,website,email,phone,leadStatus,leadStatusChangedAt,leadSource,"
    "externalReference,importBatch,qualifiedBy,qualifiedAt,sideExit,sideExitAt,"
    "sideExitNote,promotedCompanyId,promotedCompanyName,promotedContactId,"
    "promotedContactName,alreadyKnownCompanyId,alreadyKnownCompanyName,description,createdAt"
)
TOUCH_SELECT = (
    "id,name,channel,touchStatus,outcome,stageAtTouch,plannedAt,sentAt,deliveredAt,"
    "returnedAt,doneAt,scanToken,firstScannedAt,scanCount,vendorPieceId,vendorStatus,"
    "mailedAddress,calledPhone,callNotes,outreachCampaignId,outreachCampaignName,"
    "prospectId,prospectName,contactId,contactName,companyId,companyName,assignedUserId"
)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    type: str            # text | textarea | enum | date | wysiwyg
    group: str
    required: bool = False
    help: str = ""
    #: Shown only for these kinds (None: every kind).
    kinds: Optional[tuple[str, ...]] = None


#: What a marketing user fills in (§ 1.3): one spec, both the form layout and the
#: update whitelist. The sign-off and run stamps are not here — the application
#: writes them and the screen shows them read-only.
CAMPAIGN_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "Name", "text", "Campaign", required=True,
              help="A name, not a source value (ruling 26) — e.g. the filing month and the kind."),
    FieldSpec("campaignKind", "Kind", "enum", "Campaign", required=True,
              help="How the campaign runs. Postcard selects an audience and mails; Social media is its links alone."),
    FieldSpec("platform", "Platform", "enum", "Campaign", kinds=(KIND_SOCIAL,),
              help="Where a social media campaign runs."),
    FieldSpec("startDate", "Start date", "date", "Window"),
    FieldSpec("endDate", "End date", "date", "Window"),
    FieldSpec("vendorTemplateId", "Mail vendor template", "text", "Postcard", kinds=(KIND_POSTCARD,),
              help="The vendor's template for the card. Empty uses the dry-run preview."),
    FieldSpec("postcardSize", "Postcard size", "enum", "Postcard", kinds=(KIND_POSTCARD,)),
    FieldSpec("smsMessage", "Text message", "textarea", "Text message", kinds=(KIND_SMS,),
              help="What each person on the list receives. Must say how to stop texts (the word STOP). "
                   "Paste the campaign's short link in from the Links tab. Frozen at sign-off."),
    FieldSpec("description", "Notes", "wysiwyg", "Notes",
              help="The brief, the offer, the creative notes."),
)
CAMPAIGN_EDIT_NAMES: frozenset[str] = frozenset(f.name for f in CAMPAIGN_FIELDS)
CAMPAIGN_ENUM_NAMES: frozenset[str] = frozenset(f.name for f in CAMPAIGN_FIELDS if f.type == "enum")
#: The campaign fields the APPLICATION writes (ruling 40): never staff. They
#: are written under the org-wide API client — the Marketing Admin Role holds
#: a field rule of read-only on them (scripts/migrate_outreach_roles.py), and
#: before ruling 40 they were Read-only in the CRM, which dropped every write.
CAMPAIGN_APP_FIELDS: frozenset[str] = frozenset({
    "selectionRule", "selectionSummary", "pieceCount", "estimatedCost", "estimatedCostCurrency",
    "signedOffByName", "signedOffAt", "runStartedAt", "runCompletedAt",
    # The email picked at the mailing service (§ 7e.9, ruling 95; feature-detected).
    "vendorEmailId",
})

#: Fields a CRM may not carry yet (feature-detected, dropped from the form and
#: the write when absent): ruling 39's text-message wording.
CAMPAIGN_OPTIONAL_FIELDS: frozenset[str] = frozenset({"smsMessage"})

# --- the campaign's links (§ 3.7): closed destinations ------------------------
DEST_FORM = "form"
DEST_PROGRAMME = "programme"
DEST_EVENT = "event"
DEST_LANDING = "landing"
#: The five public forms a link may open. Validated against the live form
#: registry at creation, so a renamed form cannot be targeted.
FORM_DESTINATIONS = ("client-intake", "info-request", "volunteer", "partner", "sponsor")
LINK_ACTIVE = "active"
LINK_RETIRED = "retired"

#: The hidden fields every public form carries (§ 3.7, § 5).
PAYLOAD_CAMPAIGN_ID = "campaign_id"
PAYLOAD_CAMPAIGN_LINK = "campaign_link"
PAYLOAD_PROSPECT_ID = "prospect_id"
#: The person's lead code (§ 7d.3, rulings 71-74). Replaces ``prospect_id`` on
#: the forms; capture keeps both for one release so a held submission from
#: before the change still delivers.
PAYLOAD_LEAD_CODE = "lead_code"

# --- the per-form prefill allowlist (ruling 75, build plan § 7d.4) --------------
#: What ``GET /api/campaigns/public/lead/{code}?form=<key>`` may answer for each
#: form, and nothing more. THIS TABLE IS RULING 75: widening a row is a new
#: ruling, never an edit. Keys are the public response's names; ``company*`` come
#: from the person's Company when they have one, else from the lead's business
#: half. ``businessName`` and ``mailing*`` on the landing row are what the card
#: printed (ruling 16).
PREFILL_FIELDS: dict[str, tuple[str, ...]] = {
    # "Everything the form asks" (ruling 75). The registration form asks name,
    # email, phone and ZIP; § 7d.4's row also named a company and a business-
    # stage question, which the form does not ask (read 10-22-26).
    "event-registration": ("firstName", "lastName", "email", "phone", "zip"),
    "info-request": ("firstName", "lastName", "email", "phone", "companyName"),
    "client-intake": ("firstName", "lastName", "email", "phone", "companyName", "companyWebsite",
                      "companyStreet", "companyCity", "companyState", "companyZip"),
    "volunteer": ("firstName", "lastName", "email", "phone"),
    "partner": ("firstName", "lastName", "email", "phone", "companyName", "companyWebsite"),
    "sponsor": ("firstName", "lastName", "email", "phone", "companyName", "companyWebsite"),
    "landing": ("businessName", "mailingStreet", "mailingCity", "mailingState", "mailingZip"),
}
