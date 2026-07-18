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
    # The assignment dropdown filters on "Active"; the volunteer orchestrator
    # writes "Candidate" on a new mentor.
    ("CMentorProfile", "mentorStatus"): ["Active", "Candidate"],
    ("CMentorProfile", "mentorType"): ["Mentor"],
    # The volunteer ("Become a Mentor") form writes these — their options.js lists
    # must stay aligned or the CMentorProfile create 400s (drift caused a live
    # failure 2026-06-23). Industry Experience writes the multiEnum
    # `industryExperience` (v0.14.0 — the old single-enum `industrySector` is
    # no longer written by any form, so it is no longer monitored; retargeted
    # 2026-07-18 after the CRM team's typo cleanup on the enum fired a stale
    # alert against the old field/values).
    ("CMentorProfile", "industryExperience"): [
        "Accounting and Bookkeeping", "Advertising, Design, Marketing",
        "Agriculture, Farming, Livestock", "Architecture, Engineering",
        "Arts, Entertainment and Recreation", "Auto Repair",
        "Beauty, Cosmetics and Salon Services", "Business Consulting and Coaching",
        "Childcare", "Commercial and Residential Services", "Construction & Real Estate",
        "Counseling and Therapy", "Cybersecurity", "E-Commerce & Online Business",
        "Education", "Energy & Utilities", "Financial Services & Banking",
        "Group Homes", "Healthcare & Medical",
        "Hospitality, Restaurants & Food Service", "Manufacturing & Industrial",
        "Media, Marketing & Publishing", "Nonprofit & Social Impact",
        "Professional Services", "Retail & Consumer Products", "Technology & Software",
        "Transportation and Logistics", "Wellness and Fitness",
    ],
    ("CMentorProfile", "fluentLanguages"): ["English", "Spanish"],
    # "Areas of Expertise" checkboxes write here (aligned today; monitored so the
    # next drift is caught before a submission fails).
    ("CMentorProfile", "mentoringFocusAreas"): [
        "Accounting & Tax Services", "Advertising, Design, & Marketing", "Agriculture",
        "Animal & Veterinary Services", "Architecture, Engineering, & Related Services",
        "Arts, Entertainment, & Recreation", "Auto Repair & Mechanic",
        "Beauty, Cosmetics & Salon Services", "Business Consulting & Coaching",
        "Childcare", "Commercial & Residential Services", "Construction",
        "Counseling & Therapy", "Distribution & Transportation of Goods", "Education",
        "Farming & Livestock", "Fine Arts, Artisan, & Craft Work", "Fishing & Hunting",
        "Food & Beverage", "Forestry", "Funeral & Death Care Services",
        "Information Technology", "Manufacturing", "Media & Publishing",
        "Mining, Quarry, & Utilities", "Nonprofit", "Personal Care Services",
        "Photography & Video Services", "Professional Services",
        "Public Relations & Communications", "Real Estate", "Recruiting & Staffing",
        "Rental & Leasing", "Restaurant & Bar", "Retail",
        "Social Assistance & Family Services", "Transportation",
        "Travel, Hospitality, & Tourism", "Warehousing", "Waste Management & Disposal",
        "Website Development", "Wellness, Healthcare, & Home Health",
    ],
    # Discriminators the orchestrators write.
    ("Account", "cAccountType"): ["Client", "Partner", "Donor/Sponsor"],
    ("Account", "cClientStatus"): ["Prospect"],
    ("Contact", "cContactType"): ["Client", "Mentor", "Partner", "Donor", "Prospect"],
}
