"""Per-domain configuration for the Session Management engine.

Each :class:`DomainConfig` describes ONE domain (mentor / partner / sponsor).
The engine (:mod:`sessions.service`) and router are otherwise identical across
domains — everything that differs is data here: which parent entity the user
owns, how "records I own" is resolved (a reverse link on the user's
``CMentorProfile``), which ``CSession`` link points back to the parent, and how
the list grid + parent detail summary are laid out.

Field/link names verified live against the production CRM (2026-07-08); see
CLAUDE.md and the plan. ``CSession`` is a single shared entity related to all
three parents; the ``sessionType`` discriminator + the parent link distinguish
the domains.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# --- Entity names ---
SESSION = "CSession"
CONTACT = "Contact"
MENTOR_PROFILE = "CMentorProfile"
ENGAGEMENT = "CEngagement"
PARTNER_PROFILE = "CPartnerProfile"
SPONSOR_PROFILE = "CSponsorProfile"


@dataclass(frozen=True)
class Column:
    """A grid column / detail row: ``key`` in the API row, ``label`` for the UI,
    ``attr`` read from the raw EspoCRM record. ``type`` tells the grid how to
    render the cell: ``text`` (default), ``date`` (YYYY-MM-DD), or ``datetime``
    (friendly "Mon, Aug 4 — 3:30 PM" with abbreviated weekday)."""

    key: str
    label: str
    attr: str
    type: str = "text"


@dataclass(frozen=True)
class OverviewItem:
    """One fact on the Overview tab.

    ``attr`` is read (display value) from the parent record; ``type`` tells the
    frontend how to render it (badge / chips / date / currency / rich-text block).
    A linkable value (contact / company / client) sets ``link_entity`` +
    ``id_attr`` so the UI can open the pop-up detail panel for that record.
    ``block=True`` renders the item full-width below the fact grid (used for the
    long rich-text items — the mentoring need, partner notes, sponsor message).
    """

    label: str
    attr: str
    type: str = "text"  # text|badge|date|datetime|int|currency|multiEnum|html|longtext
    link_entity: Optional[str] = None  # peek target entity when this value is a link
    id_attr: Optional[str] = None  # attr on the parent holding the linked record id
    block: bool = False
    # An "organization" link that aggregates several 1:1 records (the company
    # Account + its profile) into ONE pop-up. Each pair is (entity, id_attr on the
    # parent — use "id" for the parent record itself). When set, this item is a
    # single link labelled with the company name; the peek merges every record.
    aggregate: tuple[tuple[str, str], ...] = ()
    name_fallback_attr: Optional[str] = None  # display name when ``attr`` is empty
    # Render this fact even when the value is empty (shown as "—"). For slots
    # that must stay discoverable — e.g. Referring partner, which otherwise
    # vanished on unlinked engagements and read as a missing feature (Doug's
    # 2026-07-22 report).
    always: bool = False
    # Which fact group on the Overview rail this belongs to (the frontend renders
    # one card per section, in first-seen order): "key" (identity) / "activity"
    # (session stats & tags). ``block`` items ignore this — they stack at the bottom.
    section: str = "key"


@dataclass(frozen=True)
class DomainConfig:
    slug: str  # route segment, e.g. "mentorsessions"
    title: str  # page heading
    subtitle: str
    # Settings attribute (a property returning list[str]) holding the allowed teams.
    allowed_teams_attr: str

    parent_entity: str
    parent_label: str  # "Engagement" / "Partner" / "Sponsor"

    # belongsTo link on CSession that points at this parent. The FK we write on a
    # new session is ``<session_parent_link>Id``.
    session_parent_link: str
    # hasMany reverse link on the manager's CMentorProfile listing the parents
    # they own (mentor's engagements / managed partners / managed sponsors).
    manager_owned_link: str
    # hasMany link on the parent to its sessions (existing sessions on the detail).
    parent_sessions_link: str
    # hasMany link on the parent to its related contacts (attendee options).
    parent_contacts_link: str
    # attr on the parent holding the PRIMARY contact's id, so the Overview can
    # separate "other contacts" from the primary shown in the key facts.
    primary_contact_id_attr: str

    default_session_type: str

    # List grid.
    list_select: str
    list_columns: tuple[Column, ...]

    # Parent detail summary card.
    detail_select: str
    detail_fields: tuple[Column, ...]

    # Friendly empty-grid message (shown whether the user has no linked profile or
    # simply owns no records yet — no action implied; a refresh picks up new ones).
    empty_message: str = "No records found."

    # Trailing "date" column on the grid: (key, label, attr). Defaults to Created;
    # None => no trailing date column (a domain that lays its date columns out
    # inline via ``list_columns`` sets this None).
    list_date_column: Optional[tuple[str, str, str]] = ("created", "Created", "createdAt")
    # Grid column key that is the primary contact + the parent attr holding its id
    # (so the cell links to the contact pop-up). None => not linkable.
    list_contact_key: Optional[str] = None
    list_contact_id_attr: Optional[str] = None
    # Grid column key that holds the record's status (enables the status filter).
    list_status_key: Optional[str] = None
    # List EVERY parent record the user's CRM ACL lets them read (a plain
    # entity list) instead of only the ones reverse-linked to their own
    # CMentorProfile. The partner domain uses this (Doug's ruling 2026-07-18:
    # the grid shows ALL partners; visibility is governed CRM-side by team
    # permissions — partner records carry the Partner Management Team and the
    # role reads CPartnerProfile at "team" scope), and the sponsor domain since
    # 2026-07-20 (all funders visible to every sponsor-team member; this also
    # drops the list's CMentorProfile read, which the sponsor team's role may
    # not have at all).
    list_all: bool = False
    # Attr on the raw record holding the assigned manager's CMentorProfile id
    # (mentorProfileId / partnerManagerId). Feeds the grid's manager column
    # link -> the mentor-profile pop-up, whose CBM/personal email rows are
    # compose links (the quick-email path).
    list_manager_id_attr: Optional[str] = None
    # Optional one-click status transition on the grid's status cell:
    # (from, to) — a row whose status equals ``from`` renders as a two-step
    # accept button that moves it to ``to`` (the mentor accepting an assigned
    # engagement). The server re-checks ``from`` before writing (stale guard).
    list_status_accept: Optional[tuple[str, str]] = None
    # Grid column key that is the COMPANY — rendered as a link opening the
    # standard aggregated company/client pop-up (same peek the Overview uses).
    # ``list_company_aggregate`` = (entity, id attr on the raw record; "id" =
    # the record itself). Sections the user's ACL can't read are omitted.
    list_company_key: Optional[str] = None
    list_company_aggregate: tuple = ()
    # Legacy-data fallback: when the parent's own company link is empty, resolve
    # it through a 1:1 related record instead — intake-created engagements carry
    # the Account on the CLIENT PROFILE (CClientProfile.linkedCompany), not on
    # the engagement itself. (own company id attr, own company name attr,
    # via-record id attr on the parent, via entity, company id attr on the via
    # record, company name attr on the via record.)
    company_fallback: tuple = ()

    # Details tab: the org records shown as editable sections — (title, entity,
    # id_attr on the parent). id_attr "id" means the parent record itself.
    # Related contacts are added as their own sections automatically.
    details_entities: tuple[tuple[str, str, str], ...] = ()

    # Overview tab: the curated "most important" facts (top of the detail view).
    overview_items: tuple[OverviewItem, ...] = ()

    # "Overall notes" about the whole engagement / partner / sponsor (NOT tied to
    # any one session) — shown above the per-session note feed, since they're
    # usually the most important. Empty attr => no panel.
    overall_notes_attr: Optional[str] = None
    overall_notes_label: str = "Notes"
    overall_notes_type: str = "html"  # html (wysiwyg) | longtext (plain text)

    # Mentor-only: attach co-mentors to the engagement (additionalMentors).
    supports_comentor: bool = False
    # Optional second reverse link on the manager's CMentorProfile: parents where
    # they are a CO-mentor (reverse of CEngagement.additionalMentors — the CRM
    # link is named ``engagements``, verified live on crm-test AND prod
    # 2026-07-15). Rows are merged into the owned list, deduped by id.
    manager_comentor_link: Optional[str] = None
    # belongsTo link on the parent naming the assigned CBM manager's
    # CMentorProfile (e.g. CEngagement.mentorProfile). Feeds the CBM-contacts
    # invitee resolution; None when the domain has no such link.
    parent_manager_link: Optional[str] = None
    # Mentor-only: restrict the owned list to these parent statuses (in Python;
    # empty => no status filter). ``status_attr`` is the record attribute.
    status_attr: Optional[str] = None
    status_values: tuple[str, ...] = ()

    # --- Contributions (the funder ledger — sponsor domain only; plan:
    # prds/funder-contributions-plan.md). Setting ``contributions_link`` (the
    # hasMany link on the parent to its CContribution rows) enables the whole
    # feature: the Contributions detail tab + the contribution endpoints.
    contributions_link: Optional[str] = None
    # FK attr written on a new CContribution to bind it to the parent.
    contributions_parent_fk: str = "sponsorProfileId"
    # Parent attrs the create defaults the contribution's donor links from
    # (the funder's company Account + primary Contact); blank parent values
    # simply leave the link unset.
    contributions_donor_account_attr: Optional[str] = None
    contributions_donor_contact_attr: Optional[str] = None

    @property
    def session_parent_fk(self) -> str:
        return f"{self.session_parent_link}Id"


# --- CSession editable-field spec (shared across domains) --------------------
# Drives BOTH the editor form layout and the server-side update whitelist. Enum/
# multiEnum *options* are pulled live from CRM metadata (service.field_options),
# so the CRM stays the source of truth. ``sessionAttendees`` is handled
# separately (a picker over the parent's contacts), not as a generic field.
SESSION_FIELDS: list[dict] = [
    {"name": "name", "label": "Session title", "type": "varchar", "group": "Session"},
    # Status / Session type / Start / Duration on one line (no raw End date —
    # the CRM's ``duration`` is virtual: dateEnd − dateStart. The editor shows a
    # duration select and the frontend translates it to ``dateEnd`` on save).
    {"name": "status", "label": "Status", "type": "enum", "group": "Session", "row": "top"},
    {"name": "sessionType", "label": "Session type", "type": "enum", "group": "Session", "row": "top"},
    {"name": "dateStart", "label": "Start", "type": "datetime", "group": "Session", "row": "top"},
    {"name": "duration", "label": "Duration", "type": "duration", "group": "Session", "row": "top"},
    {"name": "meetingType", "label": "Meeting type", "type": "multiEnum", "group": "Session"},
    {"name": "meetingLocationType", "label": "Location type", "type": "enum", "group": "Session", "row": "loc"},
    {"name": "locationDetails", "label": "Location details", "type": "varchar", "group": "Session", "row": "loc"},
    {"name": "videoMeetingLink", "label": "Video meeting link", "type": "varchar", "group": "Session"},
    # The two most important fields — rendered large (see `big`) and side by side.
    {"name": "sessionNotes", "label": "Session notes", "type": "wysiwyg", "group": "Notes", "row": "content", "big": True},
    {"name": "nextSteps", "label": "Action items / next steps", "type": "wysiwyg", "group": "Notes", "row": "content", "big": True},
    {"name": "nextSessionDateTime", "label": "Next session", "type": "datetime", "group": "Notes", "row": "meta"},
    {"name": "topicsCovered", "label": "Topics covered", "type": "multiEnum", "group": "Notes", "row": "meta"},
    {"name": "description", "label": "Description", "type": "text", "group": "Notes"},
    # The meeting transcript (Display Standard §12.5). The CRM field is a
    # planned Phase-3 build (Meet transcription), so the editor/view show it
    # ONLY when the live CRM actually has it — field_spec_live / get_session
    # feature-detect via metadata; a save never sends what the form never
    # rendered. Until the field lands, nothing renders (no stub).
    {"name": "sessionTranscription", "label": "Transcript", "type": "wysiwyg", "group": "Notes", "row": "transcript", "big": True},
]

# The §12.5 feature-detected field: present in the spec above, gated at runtime.
TRANSCRIPT_FIELD = "sessionTranscription"

# The permanent transcript/recording link (csession-transcript-fields.md):
# app-managed (written by the worker retrieval job), never user-editable — NOT
# in SESSION_FIELDS; feature-detected like the transcript, shown read-only in
# the session view's facts grid. Carries the Google Doc export link (Meet
# source) or the Fathom share link (Fathom source).
TRANSCRIPT_DOC_URL_FIELD = "transcriptDocUrl"

# The Fathom AI summary — csession-ai-summary-field.md
# (prds/fathom-transcript-integration.md): app-managed (worker write-back),
# never user-editable — NOT in SESSION_FIELDS; feature-detected like the
# transcript, rendered read-only as the session view's AI Summary zone. Also
# carries the action-items overflow when the mentor already wrote nextSteps.
AI_SUMMARY_FIELD = "sessionAiSummary"

# ``duration`` is EspoCRM's virtual duration type (notStorable — computed as
# dateEnd − dateStart), so the writable/readable scalar is ``dateEnd``: the
# editor sends dateEnd (start + chosen duration) and reads compute the difference.
SESSION_EDIT_NAMES = ({f["name"] for f in SESSION_FIELDS} - {"duration"}) | {"dateEnd"}
SESSION_ENUM_FIELDS = [f["name"] for f in SESSION_FIELDS if f["type"] in ("enum", "multiEnum")]
# Fields whose live *options* the editor needs from CRM metadata (enums + the
# duration presets, which are seconds ints on the duration field's metadata).
SESSION_OPTION_FIELDS = SESSION_ENUM_FIELDS + [
    f["name"] for f in SESSION_FIELDS if f["type"] == "duration"
]

# --- CContribution editable-field spec (sponsor domain — the funder ledger) --
# Same contract as SESSION_FIELDS: ONE spec drives the editor form layout AND
# the server-side update whitelist; enum options + required flags are read live
# from CRM metadata. The entity was built CRM-side (verified live 2026-07-20);
# ``inKindOnly`` marks the pair the editor shows only when giftType = In-Kind
# (display-only — both stay whitelisted). Soft delete = status Cancelled; there
# is deliberately NO delete surface anywhere.
CONTRIBUTION_FIELDS: list[dict] = [
    {"name": "name", "label": "Contribution", "type": "varchar", "group": "Contribution"},
    {"name": "contributionType", "label": "Type", "type": "enum", "group": "Contribution", "row": "top"},
    {"name": "status", "label": "Status", "type": "enum", "group": "Contribution", "row": "top"},
    {"name": "amount", "label": "Amount", "type": "currency", "group": "Contribution", "row": "top"},
    {"name": "applicationDate", "label": "Application date", "type": "date", "group": "Contribution", "row": "dates"},
    {"name": "commitmentDate", "label": "Commitment date", "type": "date", "group": "Contribution", "row": "dates"},
    {"name": "expectedPaymentDate", "label": "Expected payment", "type": "date", "group": "Contribution", "row": "dates"},
    {"name": "receivedDate", "label": "Received date", "type": "date", "group": "Contribution", "row": "dates"},
    {"name": "nextGrantDeadline", "label": "Next grant deadline", "type": "date", "group": "Contribution", "row": "dates2"},
    {"name": "giftType", "label": "Gift type", "type": "enum", "group": "Payment", "row": "pay"},
    {"name": "designation", "label": "Designation", "type": "varchar", "group": "Payment", "row": "pay"},
    {"name": "inKindDescription", "label": "In-kind description", "type": "varchar", "group": "Payment", "row": "inkind", "inKindOnly": True},
    {"name": "inKindValuationBasis", "label": "In-kind valuation basis", "type": "varchar", "group": "Payment", "row": "inkind", "inKindOnly": True},
    {"name": "acknowledgmentSent", "label": "Acknowledgment sent", "type": "bool", "group": "Acknowledgment", "row": "ack"},
    {"name": "acknowledgmentDate", "label": "Acknowledgment date", "type": "date", "group": "Acknowledgment", "row": "ack"},
    {"name": "notes", "label": "Notes", "type": "wysiwyg", "group": "Notes", "big": True},
    {"name": "description", "label": "Description", "type": "text", "group": "Notes"},
]

# ``amountCurrency`` rides along with the currency amount (EspoCRM currency
# type); the editor doesn't collect it (server/instance default applies) but a
# supplied value must not be dropped by the whitelist.
CONTRIBUTION_EDIT_NAMES = {f["name"] for f in CONTRIBUTION_FIELDS} | {"amountCurrency"}
CONTRIBUTION_ENUM_FIELDS = [
    f["name"] for f in CONTRIBUTION_FIELDS if f["type"] in ("enum", "multiEnum")
]

# Fields read for the tab's grid + summary math (notes/description load on the
# editor's per-record GET, not the list).
CONTRIBUTION_LIST_SELECT = (
    "name,contributionType,status,amount,amountCurrency,applicationDate,"
    "commitmentDate,expectedPaymentDate,receivedDate,acknowledgmentDate,"
    "acknowledgmentSent,nextGrantDeadline,giftType,designation,createdAt"
)


# Fields read for each session on the parent detail — feeds both the Sessions
# table and the Overview note feed (sessionNotes/nextSteps stamped with the time;
# attendees are read separately via the sessionAttendees relationship link).
DETAIL_SESSION_SELECT = (
    "name,status,sessionType,dateStart,dateStartDate,dateEnd,sessionNotes,"
    "nextSteps,videoMeetingLink"
)


MENTOR = DomainConfig(
    slug="mentorsessions",
    # Display name only (Doug's renames 2026-07-19) — the package/route stay
    # mentorsessions, like assignments/"Client Administration".
    title="Client Management",
    subtitle="Review your client engagements and record mentoring sessions.",
    allowed_teams_attr="session_mentor_allowed_teams_list",
    parent_entity=ENGAGEMENT,
    parent_label="Engagement",
    empty_message="No client engagements found.",
    session_parent_link="engagement",
    manager_owned_link="engagements1",  # reverse of CEngagement.mentorProfile
    parent_sessions_link="engagementSessions",
    parent_contacts_link="engagementContacts",
    primary_contact_id_attr="primaryEngagementContactId",
    default_session_type="Client Session",
    list_select=(
        "name,engagementStatus,engagementClientName,clientOrganizationName,"
        "clientOrganizationId,engagementClientId,"
        "primaryEngagementContactName,primaryEngagementContactId,"
        "nextSessionDateTime,engagementStartDate,mentorProfileName,mentorProfileId,createdAt"
    ),
    # Order: Engagement, Status, Primary contact, Next session, Start date,
    # Company, Client, Assigned Mentor (far right — so a co-mentor can see
    # who the primary mentor is, 2026-07-16). Both date columns are laid out
    # inline (so no trailing date column — list_date_column=None below).
    # Next Session's stored attr (nextSessionDateTime) is never populated by
    # the CRM — the frontend fills the cell from the row's upcomingSessions
    # (see service._attach_sessions_near_now).
    list_columns=(
        Column("name", "Engagement", "name"),
        Column("status", "Status", "engagementStatus"),
        Column("contact", "Primary contact", "primaryEngagementContactName"),
        Column("nextSession", "Next Session", "nextSessionDateTime", type="datetime"),
        Column("startDate", "Start Date", "engagementStartDate", type="date"),
        Column("company", "Company", "clientOrganizationName"),
        Column("client", "Client", "engagementClientName"),
        Column("mentor", "Assigned Mentor", "mentorProfileName"),
    ),
    list_date_column=None,
    list_contact_key="contact",
    list_contact_id_attr="primaryEngagementContactId",
    list_status_key="status",
    list_manager_id_attr="mentorProfileId",
    # A mentor accepts a newly-assigned engagement straight from the grid.
    list_status_accept=("Pending Acceptance", "Assigned"),
    list_company_key="company",
    list_company_aggregate=(("Account", "clientOrganizationId"),
                            ("CClientProfile", "engagementClientId")),
    company_fallback=("clientOrganizationId", "clientOrganizationName",
                      "engagementClientId", "CClientProfile",
                      "linkedCompanyId", "linkedCompanyName"),
    detail_select=(
        "name,engagementStatus,meetingCadence,"
        "engagementClientName,engagementClientId,"
        "clientOrganizationName,clientOrganizationId,"
        "primaryEngagementContactName,primaryEngagementContactId,"
        "mentorProfileId,mentorProfileName,"
        "engagementStartDate,lastSessionDate,nextSessionDateTime,"
        "totalSessions,totalSessionHours,totalSessionsLast30Days,"
        "referringPartnerName,referringPartnerId,"
        "mentoringFocusAreas,mentoringNeedsDescription,engagementNotes,createdAt"
    ),
    detail_fields=(
        Column("status", "Status", "engagementStatus"),
        Column("client", "Client", "engagementClientName"),
        Column("company", "Company", "clientOrganizationName"),
        Column("cadence", "Meeting cadence", "meetingCadence"),
        Column("primaryContact", "Primary contact", "primaryEngagementContactName"),
    ),
    overview_items=(
        # key identity — top of the rail (cadence closes the group)
        OverviewItem("Status", "engagementStatus", "badge", section="key"),
        # single "Company" link — the client's business profile + the company
        # Account are one org; the pop-up aggregates both.
        OverviewItem("Company", "clientOrganizationName", "text", section="key",
                     name_fallback_attr="engagementClientName",
                     aggregate=(("Account", "clientOrganizationId"),
                                ("CClientProfile", "engagementClientId"))),
        OverviewItem("Primary contact", "primaryEngagementContactName", "text", section="key",
                     link_entity="Contact", id_attr="primaryEngagementContactId"),
        OverviewItem("Assigned mentor", "mentorProfileName", "text", section="key",
                     link_entity="CMentorProfile", id_attr="mentorProfileId"),
        OverviewItem("Meeting cadence", "meetingCadence", section="key"),
        OverviewItem("Referring partner", "referringPartnerName", "text", section="key",
                     link_entity="CPartnerProfile", id_attr="referringPartnerId",
                     always=True),
        # session activity
        OverviewItem("Start date", "engagementStartDate", "date", section="activity"),
        OverviewItem("Total sessions", "totalSessions", "int", section="activity"),
        OverviewItem("Session hours", "totalSessionHours", "int", section="activity"),
        OverviewItem("Last session", "lastSessionDate", "date", section="activity"),
        OverviewItem("Last 30 days", "totalSessionsLast30Days", "int", section="activity"),
        OverviewItem("Focus areas", "mentoringFocusAreas", "multiEnum", section="activity"),
        # long-form, bottom of the rail
        OverviewItem("Mentoring need", "mentoringNeedsDescription", "html", block=True),
    ),
    overall_notes_attr="engagementNotes",
    overall_notes_label="Engagement Notes",
    overall_notes_type="html",
    details_entities=(
        ("Engagement", "CEngagement", "id"),  # the engagement record itself, first
        ("Company", "Account", "clientOrganizationId"),
        ("Client Business Profile", "CClientProfile", "engagementClientId"),
    ),
    supports_comentor=True,
    manager_comentor_link="engagements",  # reverse of CEngagement.additionalMentors
    parent_manager_link="mentorProfile",
    # No status pre-filter: load ALL of the mentor's engagements so the grid's
    # Status filter can offer every status (the user filters as they like).
    status_attr="engagementStatus",
)

PARTNER = DomainConfig(
    slug="partnersessions",
    title="Partner Management",  # display name only — route stays partnersessions
    subtitle="Review the partners you manage and record partner sessions.",
    allowed_teams_attr="session_partner_allowed_teams_list",
    parent_entity=PARTNER_PROFILE,
    parent_label="Partner",
    empty_message="No partners found.",
    session_parent_link="partnerSession",
    manager_owned_link="managedPartners",  # reverse of CPartnerProfile.partnerManager
    parent_manager_link="partnerManager",
    parent_sessions_link="sessions",
    parent_contacts_link="contacts",
    primary_contact_id_attr="primaryPartnercontactId",
    default_session_type="Partner Session",
    # The partner grid lists ALL partners the user's ACL can read (not just the
    # ones they manage) — visibility is team-governed CRM-side.
    list_all=True,
    list_select=(
        "name,partnershipStatus,partnerCompanyName,partnerCompanyId,"
        "primaryPartnercontactName,primaryPartnercontactId,"
        "partnerManagerName,partnerManagerId,"
        "partnershipStartDate,createdAt"
    ),
    list_columns=(
        Column("name", "Partner", "name"),
        Column("status", "Partnership status", "partnershipStatus"),
        Column("company", "Company", "partnerCompanyName"),
        Column("contact", "Primary contact", "primaryPartnercontactName"),
        # Links to the manager's CMentorProfile pop-up (CBM/personal email
        # compose links there — the quick-email path).
        Column("mentor", "Partner Manager", "partnerManagerName"),
    ),
    list_date_column=("startDate", "Start Date", "partnershipStartDate"),
    list_contact_key="contact",
    list_contact_id_attr="primaryPartnercontactId",
    list_status_key="status",
    list_manager_id_attr="partnerManagerId",
    list_company_key="company",
    list_company_aggregate=(("Account", "partnerCompanyId"),
                            ("CPartnerProfile", "id")),
    detail_select=(
        "name,partnershipStatus,partnershipType,"
        "partnerCompanyName,partnerCompanyId,"
        "primaryPartnercontactName,primaryPartnercontactId,"
        "partnerContactCadence,partnershipStartDate,partnershipAgreementDate,"
        "lastContacted,partnershipValue,cBMValueProvided,partnerNotes,createdAt"
    ),
    detail_fields=(
        Column("status", "Partnership status", "partnershipStatus"),
        Column("type", "Partnership type", "partnershipType"),
        Column("company", "Company", "partnerCompanyName"),
        Column("primaryContact", "Primary contact", "primaryPartnercontactName"),
    ),
    overview_items=(
        OverviewItem("Partnership status", "partnershipStatus", "badge", section="key"),
        OverviewItem("Partnership type", "partnershipType", section="key"),
        # single "Company" link — the partner profile + the company Account are
        # one org; the pop-up aggregates both.
        OverviewItem("Company", "partnerCompanyName", "text", section="key",
                     aggregate=(("Account", "partnerCompanyId"),
                                ("CPartnerProfile", "id"))),
        OverviewItem("Primary contact", "primaryPartnercontactName", "text", section="key",
                     link_entity="Contact", id_attr="primaryPartnercontactId"),
        OverviewItem("Contact cadence", "partnerContactCadence", section="activity"),
        OverviewItem("Partnership start", "partnershipStartDate", "date", section="activity"),
        OverviewItem("Agreement date", "partnershipAgreementDate", "date", section="activity"),
        OverviewItem("Last contacted", "lastContacted", "date", section="activity"),
        OverviewItem("Partnership value", "partnershipValue", "multiEnum", section="activity"),
        OverviewItem("CBM value provided", "cBMValueProvided", "multiEnum", section="activity"),
    ),
    overall_notes_attr="partnerNotes",
    overall_notes_label="Partner Notes",
    overall_notes_type="html",
    details_entities=(
        ("Partnership", "CPartnerProfile", "id"),  # the partnership record itself, first
        ("Company", "Account", "partnerCompanyId"),
    ),
)

SPONSOR = DomainConfig(
    slug="sponsorsessions",
    # "Funder" is the user-facing word (Doug's rename 2026-07-19); the CRM
    # records and route keep the sponsor naming.
    title="Funder Management",
    subtitle="Review the funders you manage and record sessions.",
    allowed_teams_attr="session_sponsor_allowed_teams_list",
    parent_entity=SPONSOR_PROFILE,
    parent_label="Sponsor",
    empty_message="No sponsors found.",
    session_parent_link="sponsorProfile",
    manager_owned_link="managedSponsors",  # reverse of CSponsorProfile.cBMSponsorManager
    parent_manager_link="cBMSponsorManager",
    parent_sessions_link="sponsorSessions",
    parent_contacts_link="sponsorContacts",
    primary_contact_id_attr="sponsorContactId",
    default_session_type="Sponsor Session",
    # The sponsor grid lists ALL sponsors the user's ACL can read (not just the
    # ones they manage) — every sponsor-team member works the shared list
    # (Doug's ruling 2026-07-20, the partner-domain precedent). This also means
    # the list never reads CMentorProfile, which the sponsor team's role may
    # not be granted.
    list_all=True,
    list_select=(
        "name,sponsorCompanyName,sponsorCompanyId,sponsorContactName,"
        "sponsorContactId,cBMSponsorManagerName,cBMSponsorManagerId,createdAt"
    ),
    list_columns=(
        Column("name", "Sponsor", "name"),
        Column("company", "Company", "sponsorCompanyName"),
        Column("contact", "Primary contact", "sponsorContactName"),
        # Links to the manager's CMentorProfile pop-up (CBM/personal email
        # compose links there — the quick-email path); "—" when unmanaged.
        Column("mentor", "Sponsor Manager", "cBMSponsorManagerName"),
    ),
    list_contact_key="contact",
    list_contact_id_attr="sponsorContactId",
    list_manager_id_attr="cBMSponsorManagerId",
    list_company_key="company",
    list_company_aggregate=(("Account", "sponsorCompanyId"),
                            ("CSponsorProfile", "id")),
    detail_select=(
        "name,sponsorCompanyName,sponsorCompanyId,"
        "sponsorContactName,sponsorContactId,"
        "totalContribution,totalContributionCurrency,"
        "lastContribution,lastContacted,description,createdAt"
    ),
    detail_fields=(
        Column("company", "Company", "sponsorCompanyName"),
        Column("primaryContact", "Primary contact", "sponsorContactName"),
    ),
    overview_items=(
        # single "Company" link — the sponsor profile + the company Account are
        # one org; the pop-up aggregates both.
        OverviewItem("Company", "sponsorCompanyName", "text", section="key",
                     aggregate=(("Account", "sponsorCompanyId"),
                                ("CSponsorProfile", "id"))),
        OverviewItem("Primary contact", "sponsorContactName", "text", section="key",
                     link_entity="Contact", id_attr="sponsorContactId"),
        OverviewItem("Total contribution", "totalContribution", "currency", section="activity"),
        OverviewItem("Last contribution", "lastContribution", "date", section="activity"),
        OverviewItem("Last contacted", "lastContacted", "date", section="activity"),
    ),
    overall_notes_attr="description",
    overall_notes_label="Sponsor Notes",
    overall_notes_type="longtext",
    details_entities=(
        ("Sponsorship", "CSponsorProfile", "id"),  # the sponsor record itself, first
        ("Company", "Account", "sponsorCompanyId"),
    ),
    # The funder ledger (prds/funder-contributions-plan.md): the Contributions
    # tab + endpoints, reading the CRM-built CContribution entity through the
    # parent's sponsorContributions link. Donor links on a new contribution
    # default from the funder's company + primary contact.
    contributions_link="sponsorContributions",
    contributions_parent_fk="sponsorProfileId",
    contributions_donor_account_attr="sponsorCompanyId",
    contributions_donor_contact_attr="sponsorContactId",
)

DOMAINS: dict[str, DomainConfig] = {d.slug: d for d in (MENTOR, PARTNER, SPONSOR)}
