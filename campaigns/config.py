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
EVENT = "CEvent"
ACCOUNT = "Account"
CONTACT = "Contact"

# --- relationships on the campaign (read through list_related, written with
# relate / unrelate, never through a *Ids attribute) ---------------------------
LINK_PARTNERS = "partnerProfiles"       # CM-2, reverse CPartnerProfile.sponsoredCampaigns
LINK_EVENTS = "events"                  # CM-6, reverse CEvent.outreachCampaigns
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


def kinds_built(calls_on: bool, sms_on: bool = False) -> tuple[str, ...]:
    """The kinds a campaign may be created as on this deployment."""
    return PHASE_1_KINDS + (CALL_KINDS if calls_on else ()) + (SMS_KINDS if sms_on else ())

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
#: Ruling 20's three call outcomes (§ 3.4).
OUTCOME_NO_ANSWER = "No answer"
OUTCOME_INTERESTED = "Interested"
OUTCOME_DECLINED = "Declined"
CALL_OUTCOMES = (OUTCOME_NO_ANSWER, OUTCOME_INTERESTED, OUTCOME_DECLINED)

# --- prospect records (§ 1.2) --------------------------------------------------
STAGE_UNVERIFIED = "Unverified"
STAGE_QUALIFIED = "Qualified"
STAGE_LEAD = "Lead"
STAGE_WARM_LEAD = "Warm Lead"
STAGE_OPPORTUNITY = "Opportunity"
STAGES = (STAGE_UNVERIFIED, STAGE_QUALIFIED, STAGE_LEAD, STAGE_WARM_LEAD, STAGE_OPPORTUNITY)
#: Advance-only: a rung is written only when it is later on the ladder.
STAGE_RANK = {s: i for i, s in enumerate(STAGES)}

ADDRESS_USABLE = "Usable"
ADDRESS_DEAD = "Dead"

DOOR_FILING = "State filing"
DOOR_LIST = "List"
DOOR_PARTNER_FILE = "Partner file"

EXIT_ALREADY_KNOWN = "Already known"
EXIT_UNQUALIFIED = "Unqualified"
EXIT_DO_NOT_CONTACT = "Do Not Contact"
EXIT_DECLINED = "Declined"
EXIT_STALE = "Stale"

#: The Company type a promoted business carries (ruling 21).
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
    "addressDeadAt,website,email,phone,funnelStage,entryStage,stageChangedAt,entryDoor,"
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

#: The hidden fields every public door carries (§ 3.7, § 5).
PAYLOAD_CAMPAIGN_ID = "campaign_id"
PAYLOAD_CAMPAIGN_LINK = "campaign_link"
PAYLOAD_PROSPECT_ID = "prospect_id"
