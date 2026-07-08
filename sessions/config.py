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

# CEngagement statuses that count as a mentor's "active" list (Doug, 2026-07-08).
MENTOR_ACTIVE_STATUSES = ("Active", "Assigned", "Pending Acceptance", "On-Hold")


@dataclass(frozen=True)
class Column:
    """A grid column / detail row: ``key`` in the API row, ``label`` for the UI,
    ``attr`` read from the raw EspoCRM record."""

    key: str
    label: str
    attr: str


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

    default_session_type: str

    # List grid.
    list_select: str
    list_columns: tuple[Column, ...]

    # Parent detail summary card.
    detail_select: str
    detail_fields: tuple[Column, ...]

    # Mentor-only: attach co-mentors to the engagement (additionalMentors).
    supports_comentor: bool = False
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
    {"name": "status", "label": "Status", "type": "enum", "group": "Session", "row": "statustype"},
    {"name": "sessionType", "label": "Session type", "type": "enum", "group": "Session", "row": "statustype"},
    {"name": "dateStart", "label": "Start", "type": "datetime", "group": "Session", "row": "when"},
    {"name": "dateEnd", "label": "End", "type": "datetime", "group": "Session", "row": "when"},
    {"name": "meetingType", "label": "Meeting type", "type": "multiEnum", "group": "Session"},
    {"name": "meetingLocationType", "label": "Location type", "type": "enum", "group": "Session", "row": "loc"},
    {"name": "locationDetails", "label": "Location details", "type": "varchar", "group": "Session", "row": "loc"},
    {"name": "videoMeetingLink", "label": "Video meeting link", "type": "varchar", "group": "Session"},
    {"name": "sessionNotes", "label": "Session notes", "type": "wysiwyg", "group": "Notes"},
    {"name": "nextSteps", "label": "Action items / next steps", "type": "wysiwyg", "group": "Notes"},
    {"name": "nextSessionDateTime", "label": "Next session", "type": "datetime", "group": "Notes"},
    {"name": "topicsCovered", "label": "Topics covered", "type": "multiEnum", "group": "Notes"},
    {"name": "description", "label": "Description", "type": "text", "group": "Notes"},
]

SESSION_EDIT_NAMES = {f["name"] for f in SESSION_FIELDS}
SESSION_ENUM_FIELDS = [f["name"] for f in SESSION_FIELDS if f["type"] in ("enum", "multiEnum")]


MENTOR = DomainConfig(
    slug="mentorsessions",
    title="Mentor Sessions",
    subtitle="Review your engagements and record mentoring sessions.",
    allowed_teams_attr="session_mentor_allowed_teams_list",
    parent_entity=ENGAGEMENT,
    parent_label="Engagement",
    session_parent_link="engagement",
    manager_owned_link="engagements1",  # reverse of CEngagement.mentorProfile
    parent_sessions_link="engagementSessions",
    parent_contacts_link="engagementContacts",
    default_session_type="Client Session",
    list_select=(
        "name,engagementStatus,engagementClientName,clientOrganizationName,"
        "primaryEngagementContactName,createdAt"
    ),
    list_columns=(
        Column("name", "Engagement", "name"),
        Column("status", "Status", "engagementStatus"),
        Column("client", "Client", "engagementClientName"),
        Column("company", "Company", "clientOrganizationName"),
        Column("contact", "Primary contact", "primaryEngagementContactName"),
    ),
    detail_select=(
        "name,engagementStatus,meetingCadence,engagementClientName,"
        "clientOrganizationName,primaryEngagementContactName,createdAt"
    ),
    detail_fields=(
        Column("status", "Status", "engagementStatus"),
        Column("client", "Client", "engagementClientName"),
        Column("company", "Company", "clientOrganizationName"),
        Column("cadence", "Meeting cadence", "meetingCadence"),
        Column("primaryContact", "Primary contact", "primaryEngagementContactName"),
    ),
    supports_comentor=True,
    status_attr="engagementStatus",
    status_values=MENTOR_ACTIVE_STATUSES,
)

PARTNER = DomainConfig(
    slug="partnersessions",
    title="Partner Sessions",
    subtitle="Review the partners you manage and record partner sessions.",
    allowed_teams_attr="session_partner_allowed_teams_list",
    parent_entity=PARTNER_PROFILE,
    parent_label="Partner",
    session_parent_link="partnerSession",
    manager_owned_link="managedPartners",  # reverse of CPartnerProfile.partnerManager
    parent_sessions_link="sessions",
    parent_contacts_link="contacts",
    default_session_type="Partner Session",
    list_select="name,partnershipStatus,partnerCompanyName,primaryPartnercontactName,createdAt",
    list_columns=(
        Column("name", "Partner", "name"),
        Column("status", "Partnership status", "partnershipStatus"),
        Column("company", "Company", "partnerCompanyName"),
        Column("contact", "Primary contact", "primaryPartnercontactName"),
    ),
    detail_select="name,partnershipStatus,partnershipType,partnerCompanyName,primaryPartnercontactName,createdAt",
    detail_fields=(
        Column("status", "Partnership status", "partnershipStatus"),
        Column("type", "Partnership type", "partnershipType"),
        Column("company", "Company", "partnerCompanyName"),
        Column("primaryContact", "Primary contact", "primaryPartnercontactName"),
    ),
)

SPONSOR = DomainConfig(
    slug="sponsorsessions",
    title="Sponsor Sessions",
    subtitle="Review the sponsors you manage and record sponsor sessions.",
    allowed_teams_attr="session_sponsor_allowed_teams_list",
    parent_entity=SPONSOR_PROFILE,
    parent_label="Sponsor",
    session_parent_link="sponsorProfile",
    manager_owned_link="managedSponsors",  # reverse of CSponsorProfile.cBMSponsorManager
    parent_sessions_link="sponsorSessions",
    parent_contacts_link="sponsorContacts",
    default_session_type="Sponsor Session",
    list_select="name,sponsorCompanyName,sponsorContactName,createdAt",
    list_columns=(
        Column("name", "Sponsor", "name"),
        Column("company", "Company", "sponsorCompanyName"),
        Column("contact", "Primary contact", "sponsorContactName"),
    ),
    detail_select="name,sponsorCompanyName,sponsorContactName,createdAt",
    detail_fields=(
        Column("company", "Company", "sponsorCompanyName"),
        Column("primaryContact", "Primary contact", "sponsorContactName"),
    ),
)

DOMAINS: dict[str, DomainConfig] = {d.slug: d for d in (MENTOR, PARTNER, SPONSOR)}
