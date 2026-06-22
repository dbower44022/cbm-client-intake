"""What the forms/tools require from the EspoCRM enums — V2 Phase 3, Requirement 6.

The schema-drift check (``core.monitoring``) fetches each field's live options
from EspoCRM and alerts if any expected value has gone missing (renamed or
removed), so staff are warned *before* a real submission fails on it.

Keys are ``(entity, field)``; values are the option strings the app writes or
filters on. Extend this as forms add enum-backed fields. (Values verified against
crm-test; sourced from the orchestrators and the assignment/ops tooling.)
"""

from __future__ import annotations

EXPECTED_ENUMS: dict[tuple[str, str], list[str]] = {
    # Engagement lifecycle the intake + assignment tools depend on.
    ("CEngagement", "engagementStatus"): ["Submitted", "Pending Acceptance"],
    # The assignment dropdown filters mentors on this exact value.
    ("CMentorProfile", "mentorStatus"): ["Active"],
    # Discriminators the orchestrators write.
    ("Account", "cAccountType"): ["Client", "Partner", "Donor/Sponsor"],
    ("Account", "cClientStatus"): ["Prospect"],
    ("Contact", "cContactType"): ["Client", "Mentor", "Partner", "Donor", "Prospect"],
}
