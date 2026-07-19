"""Per-kind configuration for the Workspace Directory engine.

Each :class:`DirectoryConfig` describes ONE browsable directory (companies /
contacts / mentors). The engine (:mod:`directory.service`) and router are
otherwise identical across kinds — everything that differs is data here: which
EspoCRM entity it lists, whether records are edited inline (Contacts/Companies)
or by handing off to another tool (Mentors → My Mentor Profile), and which
fields are offered as grid filters.

Columns and the detail arrangement are NOT configured here — they are read LIVE
from the CRM's own list/detail layouts (``EspoClient.layout``), so the grids
match the CRM and stay in sync when someone edits a layout. See the plan in
``prds/workspace-directories-plan.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DirectoryConfig:
    slug: str  # route segment under /directory/, e.g. "companies"
    title: str
    entity: str  # the EspoCRM entity listed
    search_attr: str = "name"  # attribute the top-center search box filters (contains)
    default_order: str = "name"
    # Inline edit (in the detail pop-up) is offered for records the user owns.
    # Mentors edit through My Mentor Profile instead (edit_handoff), so their
    # directory is inline-read-only.
    editable: bool = True
    # When set, the Edit button opens this tool (named-tab) instead of an inline
    # editor — used for Mentors (their own CMentorProfile is edited in
    # /mentorprofile/). Only offered on the user's OWN row.
    edit_handoff: Optional[str] = None
    # Field names offered as grid filters (top-left). Their kind (enum / multiEnum
    # / bool) and options are resolved live from CRM metadata; a field that turns
    # out not to be filterable is silently dropped.
    filters: tuple[str, ...] = field(default_factory=tuple)
    # A hasMany link to the record's contacts (e.g. Account -> "contacts"). When
    # set, the detail pop-up lists them (name/phone/email) at the bottom.
    contacts_link: Optional[str] = None
    # An enum/multiEnum field naming the record's TYPE (e.g. Account ->
    # "cCompanyType"). When set, detail panels titled "<Type> Profile" are shown
    # only when the record's type includes that type — so a Client company hides
    # the Partner Profile panel, etc. Non-"… Profile" panels are never filtered.
    type_field: Optional[str] = None


COMPANIES = DirectoryConfig(
    slug="companies",
    title="Companies",
    entity="Account",
    filters=("cCompanyType",),
    contacts_link="contacts",
    type_field="cCompanyType",
)

CONTACTS = DirectoryConfig(
    slug="contacts",
    title="Contacts",
    entity="Contact",
    filters=("cContactType",),
)

MENTORS = DirectoryConfig(
    slug="mentors",
    title="Mentors",
    entity="CMentorProfile",
    editable=False,
    edit_handoff="/mentorprofile/",
    filters=("mentorStatus", "mentorType", "acceptingNewClients"),
)

PARTNERS = DirectoryConfig(
    slug="partners",
    title="Partners",
    entity="CPartnerProfile",
    filters=("partnershipStatus", "partnershipType"),
)

DIRECTORIES: dict[str, DirectoryConfig] = {
    d.slug: d for d in (COMPANIES, CONTACTS, MENTORS, PARTNERS)
}
