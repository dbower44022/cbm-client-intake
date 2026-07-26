"""What counts as an item "awaiting processing" — the single home of the
per-app work-queue definitions (Doug's rulings 2026-07-26), shared by:

* the portal tile badges (``GET /api/portal/attention`` in :mod:`portal.router`)
  — counts computed AS THE SIGNED-IN USER, so each badge reflects what that
  user's CRM ACL lets the app show them; and
* the analytics **Items awaiting processing** rows metric
  (:mod:`analytics.computed`) — the full record list with links, computed under
  the org-wide analytics identity.

The definitions:

===================  ==========================================================
Client Administration  ``CEngagement`` with ``engagementStatus = Submitted``
                       (awaiting a mentor assignment)
Mentor Administration  ``CMentorProfile`` with ``mentorStatus = Candidate``
                       (new volunteer/mentor applications)
Partner Management     ``CPartnerProfile`` with ``partnershipStatus = Candidate``
                       (new partner applications)
Funder Management      ``CSponsorProfile`` with no Funder Manager assigned —
                       the entity has no candidate/new status of its own, so
                       the unmanaged set is the awaiting-processing signal
Submission Admin       open admin-queue submissions (the durable store — see
                       ``core.store.OPEN_REVIEW_STATUSES``; not defined here
                       because it is store data, not a CRM query)
===================  ==========================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AttentionType:
    """One CRM-backed awaiting-processing category."""

    key: str
    app_url: str                      # the portal tile this count badges
    label: str                        # human description ("Clients awaiting …")
    row_label: str                    # the analytics table's Type cell
    entity: str
    where: tuple                      # EspoCRM where clauses (tuple of dicts)
    # App record page per item ("/partnersessions/record/{id}"); None => the
    # item links to its CRM record instead (no app-side per-record page).
    href_template: Optional[str] = None


ENGAGEMENTS = AttentionType(
    key="engagements",
    app_url="/assignments/",
    label="Clients awaiting mentor assignment",
    row_label="Client awaiting mentor",
    entity="CEngagement",
    where=({"type": "equals", "attribute": "engagementStatus", "value": "Submitted"},),
)

MENTORS = AttentionType(
    key="mentors",
    app_url="/mentoradmin/",
    label="New mentor applications",
    row_label="Mentor application",
    entity="CMentorProfile",
    where=({"type": "equals", "attribute": "mentorStatus", "value": "Candidate"},),
)

PARTNERS = AttentionType(
    key="partners",
    app_url="/partnersessions/",
    label="New partner applications",
    row_label="Partner application",
    entity="CPartnerProfile",
    where=({"type": "equals", "attribute": "partnershipStatus", "value": "Candidate"},),
    href_template="/partnersessions/record/{id}",
)

FUNDERS = AttentionType(
    key="funders",
    app_url="/sponsorsessions/",
    label="Funders with no manager assigned",
    row_label="Funder without a manager",
    entity="CSponsorProfile",
    where=({"type": "isNull", "attribute": "cBMSponsorManagerId"},),
    href_template="/sponsorsessions/record/{id}",
)

CRM_TYPES = (ENGAGEMENTS, MENTORS, PARTNERS, FUNDERS)

# The Submission Admin category (store-backed, no CRM query).
OPS_APP_URL = "/ops/"
OPS_LABEL = "Open submissions"
OPS_ROW_LABEL = "Open submission"


async def crm_count(espo, t: AttentionType) -> int:
    """A cheap count of one category via the list ``total`` envelope."""
    env = await espo.list(t.entity, where=list(t.where), select="id", max_size=1)
    return int(env.get("total") or 0)


async def crm_records(espo, t: AttentionType, *, limit: int = 10) -> list[dict[str, Any]]:
    """The oldest ``limit`` records of one category (the analytics row list)."""
    env = await espo.list(
        t.entity,
        where=list(t.where),
        select="id,name,createdAt",
        max_size=limit,
        order_by="createdAt",
        order="asc",
    )
    return list(env.get("list") or [])
