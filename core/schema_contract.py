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
    # The client-intake form's "Area(s) of Mentoring" checkboxes write here, so
    # its options must stay aligned to this enum.
    ("CEngagement", "mentoringFocusAreas"): [
        "Accounting", "Artificial Intelligence for Small Businesses",
        "Arts: Visual, Crafts, Music, etc.", "Business Strategy & Planning",
        "Compliance & Accreditation Audits", "Customer Experience & Service Excellence",
        "Digital Marketing & Social Media", "E-Commerce", "Finance & Cash Flow Management",
        "Franchising", "Funding & Capital Access", "Government Contracting and Regulations",
        "Group Homes", "Hospitality, Restaurants, Food Trucks, Lodging",
        "Human Resources & Talent Management", "International Business & Market Expansion",
        "Leadership & Executive Coaching", "Marketing & Branding",
        "Mergers, Acquisitions & Exit Planning", "Nonprofit Management & Fundraising",
        "Operations & Process Improvement", "Product Development & Innovation",
        "Program Design & Implementation", "Retail and Merchandising",
        "Sales & Business Development", "Social Assistance & Family Services",
        "Startup Launch & Entrepreneurship", "Strategic Planning",
        "Technology & Digital Transformation", "Transportation and Logistics", "Websites",
    ],
    # The assignment dropdown filters mentors on this exact value.
    ("CMentorProfile", "mentorStatus"): ["Active"],
    # Discriminators the orchestrators write.
    ("Account", "cAccountType"): ["Client", "Partner", "Donor/Sponsor"],
    ("Account", "cClientStatus"): ["Prospect"],
    ("Contact", "cContactType"): ["Client", "Mentor", "Partner", "Donor", "Prospect"],
}
