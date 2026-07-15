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

# Fields read for each session on the parent detail — feeds both the Sessions
# table and the Overview note feed (sessionNotes/nextSteps stamped with the time;
# attendees are read separately via the sessionAttendees relationship link).
DETAIL_SESSION_SELECT = (
    "name,status,sessionType,dateStart,dateStartDate,dateEnd,sessionNotes,"
    "nextSteps,videoMeetingLink"
)


MENTOR = DomainConfig(
    slug="mentorsessions",
    title="Mentor Sessions",
    subtitle="Review your engagements and record mentoring sessions.",
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
        "nextSessionDateTime,engagementStartDate,createdAt"
    ),
    # Order: Engagement, Status, Primary contact, Next session, Start date,
    # Company, Client. Both date columns are laid out inline (so no trailing
    # date column — list_date_column=None below).
    list_columns=(
        Column("name", "Engagement", "name"),
        Column("status", "Status", "engagementStatus"),
        Column("contact", "Primary contact", "primaryEngagementContactName"),
        Column("nextSession", "Next Session", "nextSessionDateTime", type="datetime"),
        Column("startDate", "Start Date", "engagementStartDate", type="date"),
        Column("company", "Company", "clientOrganizationName"),
        Column("client", "Client", "engagementClientName"),
    ),
    list_date_column=None,
    list_contact_key="contact",
    list_contact_id_attr="primaryEngagementContactId",
    list_status_key="status",
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
                     link_entity="CPartnerProfile", id_attr="referringPartnerId"),
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
    title="Partner Sessions",
    subtitle="Review the partners you manage and record partner sessions.",
    allowed_teams_attr="session_partner_allowed_teams_list",
    parent_entity=PARTNER_PROFILE,
    parent_label="Partner",
    empty_message="No partners found.",
    session_parent_link="partnerSession",
    manager_owned_link="managedPartners",  # reverse of CPartnerProfile.partnerManager
    parent_sessions_link="sessions",
    parent_contacts_link="contacts",
    primary_contact_id_attr="primaryPartnercontactId",
    default_session_type="Partner Session",
    list_select=(
        "name,partnershipStatus,partnerCompanyName,partnerCompanyId,"
        "primaryPartnercontactName,primaryPartnercontactId,"
        "partnershipStartDate,createdAt"
    ),
    list_columns=(
        Column("name", "Partner", "name"),
        Column("status", "Partnership status", "partnershipStatus"),
        Column("company", "Company", "partnerCompanyName"),
        Column("contact", "Primary contact", "primaryPartnercontactName"),
    ),
    list_date_column=("startDate", "Start Date", "partnershipStartDate"),
    list_contact_key="contact",
    list_contact_id_attr="primaryPartnercontactId",
    list_status_key="status",
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
    title="Sponsor Sessions",
    subtitle="Review the sponsors you manage and record sponsor sessions.",
    allowed_teams_attr="session_sponsor_allowed_teams_list",
    parent_entity=SPONSOR_PROFILE,
    parent_label="Sponsor",
    empty_message="No sponsors found.",
    session_parent_link="sponsorProfile",
    manager_owned_link="managedSponsors",  # reverse of CSponsorProfile.cBMSponsorManager
    parent_sessions_link="sponsorSessions",
    parent_contacts_link="sponsorContacts",
    primary_contact_id_attr="sponsorContactId",
    default_session_type="Sponsor Session",
    list_select=(
        "name,sponsorCompanyName,sponsorCompanyId,sponsorContactName,"
        "sponsorContactId,createdAt"
    ),
    list_columns=(
        Column("name", "Sponsor", "name"),
        Column("company", "Company", "sponsorCompanyName"),
        Column("contact", "Primary contact", "sponsorContactName"),
    ),
    list_contact_key="contact",
    list_contact_id_attr="sponsorContactId",
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
)

DOMAINS: dict[str, DomainConfig] = {d.slug: d for d in (MENTOR, PARTNER, SPONSOR)}
