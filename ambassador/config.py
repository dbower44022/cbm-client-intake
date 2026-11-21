"""The Ambassador Program's fixed words and CRM names
(prds/Ambassador Program/ambassador-program-prd.md; decisions AM1 to AM7).

Every stored value here is CRM data, not page wording: it never carries the
organization's name or acronym, so one value serves every chapter. The page
draws its own labels, with ``{{abbr}}``, from ``ACTIVITY_LABELS``.
"""

from __future__ import annotations

# --- CRM record types and links -------------------------------------------------

ACTIVITY = "CAmbassadorActivity"
CONTACT = "Contact"
ACCOUNT = "Account"
SESSION = "CSession"
ENGAGEMENT = "CEngagement"
PARTNER = "CPartnerProfile"
SPONSOR = "CSponsorProfile"
MENTOR = "CMentorProfile"

#: Referred by (PRD § 7.2). On Contact the link is typed unprefixed and stored
#: with EspoCRM's ``c`` prefix; on the custom record types it is stored as typed.
CONTACT_REFERRED_BY = "cReferredBy"
REFERRED_BY = "referredBy"

#: The session type every count of sessions ignores (PRD § 4.3). The value
#: itself lives in ``core/session_kinds.py``, which the counting code imports.
from core.session_kinds import AMBASSADOR_SESSION_TYPE  # noqa: E402

LEAD_SOURCE = "Ambassador referral"

# --- the six activities (PRD § 3.3) -------------------------------------------

LIKED = "Liked or shared a post"
REFERRED = "Referred someone"
INVITED = "Invited someone to an event"
INTRODUCTION = "Made a community introduction"
REPRESENTED = "Represented us at an event"
SUCCESS_STORY = "Identified a success story"

ACTIVITY_TYPES: tuple[str, ...] = (LIKED, REFERRED, INVITED, INTRODUCTION, REPRESENTED,
                                   SUCCESS_STORY)

#: What the mentor reads on the six buttons ({{abbr}} filled on the page).
ACTIVITY_LABELS: dict[str, str] = {
    LIKED: "I liked or shared a {{abbr}} post",
    REFERRED: "I referred someone to {{abbr}}",
    INVITED: "I invited someone to an event",
    INTRODUCTION: "I made a community introduction",
    REPRESENTED: "I represented {{abbr}} at an event",
    SUCCESS_STORY: "I identified a success story",
}

#: Activities with no contact block (PRD § 3.2 question 3).
NO_CONTACT = frozenset({LIKED})
#: Activities whose contact block must name someone.
CONTACT_REQUIRED = frozenset({REFERRED})

# --- who the person is (question 4) ---------------------------------------------

POTENTIAL_CLIENT = "Potential client"
POTENTIAL_PARTNER = "Potential partner"
POTENTIAL_FUNDER = "Potential funder"
EXISTING_ORG = "Existing organization"
SOMEONE_ELSE = "Someone else"

PERSON_KINDS: tuple[str, ...] = (POTENTIAL_CLIENT, POTENTIAL_PARTNER, POTENTIAL_FUNDER,
                                 EXISTING_ORG, SOMEONE_ELSE)
PERSON_LABELS: dict[str, str] = {
    POTENTIAL_CLIENT: "A potential client",
    POTENTIAL_PARTNER: "A potential partner",
    POTENTIAL_FUNDER: "A potential funder",
    EXISTING_ORG: "From an organization we already work with",
    SOMEONE_ELSE: "Someone else",
}
REFERRAL_KINDS = frozenset({POTENTIAL_CLIENT, POTENTIAL_PARTNER, POTENTIAL_FUNDER})

# --- what the delivery found (matchStatus) --------------------------------------

M_PENDING = "Pending"
M_MATCHED = "Matched"
M_CREATED = "Created"
M_NOT_MATCHED = "Not matched"
M_MANY = "More than one match"
M_MEMBER = "Member"
M_NO_CONTACT = "No contact"
MATCH_STATUSES: tuple[str, ...] = (M_PENDING, M_MATCHED, M_CREATED, M_NOT_MATCHED, M_MANY,
                                   M_MEMBER, M_NO_CONTACT)
#: The match states that put a contact on the review list.
NEEDS_REVIEW = frozenset({M_NOT_MATCHED, M_MANY})

# --- the review list (PRD § 5.2) ------------------------------------------------

R_LINKED = "Linked"
R_CREATED = "Created"
R_DISMISSED = "Dismissed"
R_SEEN = "Seen"
REVIEW_OUTCOMES: tuple[str, ...] = ("", R_LINKED, R_CREATED, R_DISMISSED, R_SEEN)

# --- a referral's outcome -------------------------------------------------------

O_NONE = ""
O_NOT_YET = "Not yet"
O_APPLIED = "Applied"
REFERRAL_OUTCOMES: tuple[str, ...] = (O_NONE, O_NOT_YET, O_APPLIED)

# --- partner and funder Candidate statuses (PRD § 4.5) -------------------------

#: A referred partner's profile starts as the partner form's own inbound value.
PARTNER_STATUS_FIELD = "partnershipStatus"
PARTNER_CANDIDATE = "Candidate"
#: A referred funder starts Prospective, the funder status (ruling 67) that
#: means "being approached" — no new value is needed on the CRM.
SPONSOR_STATUS_FIELD = "funderStatus"
SPONSOR_CANDIDATE = "Prospective"

#: Where each kind of organisation keeps its links (from sessions/config.py).
PARTNER_COMPANY = "partnerCompanyId"
SPONSOR_COMPANY = "sponsorCompanyId"
PARTNER_CONTACTS = "contacts"
SPONSOR_CONTACTS = "sponsorContacts"
ENGAGEMENT_CONTACTS = "engagementContacts"
PARTNER_MANAGER = "partnerManagerId"
SPONSOR_MANAGER = "cBMSponsorManagerId"
PARTNER_PRIMARY = "primaryPartnercontactId"
SPONSOR_PRIMARY = "sponsorContactId"
PARTNER_SESSION_FK = "partnerSessionId"
SPONSOR_SESSION_FK = "sponsorProfileId"
ENGAGEMENT_SESSION_FK = "engagementId"
ATTENDEE_LINK = "sessionAttendees"

#: The domain team each new referred profile is stamped with.
PARTNER_TEAM_SETTING = "partner_team_name"
SPONSOR_TEAM_SETTING = "sponsor_team_name"

#: A slow first delivery: the web tries once inline, then leaves the row to
#: the worker, which waits this long before claiming it.
INLINE_LEASE_SECONDS = 300

#: Engagement statuses that make an engagement a client's "current" one
#: (the Client Administration set, ruling 2026-09-29).
CURRENT_ENGAGEMENT_STATUSES = ("Active", "Assigned", "Pending Acceptance", "On-Hold")

APP = "Ambassador Activity"
