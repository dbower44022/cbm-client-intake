/*
 * Volunteer form value lists (SCORE form 6). The industry, expertise, and
 * language lists are aligned to the deployed CRM enum options
 * (CMentorProfile.industryExperience / mentoringFocusAreas / fluentLanguages), so
 * every selectable value is accepted on submit. Contact-method + employment are
 * CRM-backed Contact enums, and "how did you hear" tracks the profile field it's
 * written to — all CRM-backed lists are kept in sync via:
 *   uv run python scripts/sync_form_options.py --write
 */
window.VOL_OPTIONS = {
  phoneType: ["Mobile", "Home", "Work"],
  // >>> crm-enum key=contactPreference field=Contact.cPreferredContactMethod — generated; do not hand-edit between the markers.
  contactPreference: [
    "Email",
    "Phone",
    "Text",
  ],
  // <<< crm-enum
  // >>> crm-enum key=employment field=Contact.cEmploymentStatus — generated; do not hand-edit between the markers.
  employment: [
    "Yes, Full-time",
    "Yes, Part-time",
    "No",
  ],
  // <<< crm-enum

  // Synced to the field the volunteer orchestrator actually writes
  // (CMentorProfile.howDidYouHearAboutCBM), not Contact.cHowDidYouHear — keeps the
  // dropdown aligned with the write target so a future enum drift can't silently drop it.
  // >>> crm-enum key=howDidYouHear field=CMentorProfile.howDidYouHearAboutCBM — generated; do not hand-edit between the markers.
  howDidYouHear: [
    "CBM Email",
    "Partner Referral",
    "Personal Referral",
    "News or Media",
    "Social Media",
    "Online Search",
    "CBM Client or Volunteer",
    "Workshop or Event",
    "Other",
  ],
  // <<< crm-enum

  // The mentor "Industry Experience" multi-select maps to the multiEnum
  // CMentorProfile.industryExperience (all selections stored). Keep in sync with it:
  //   uv run python scripts/sync_form_options.py --write
  // >>> crm-enum key=industryExperience field=CMentorProfile.industryExperience — generated; do not hand-edit between the markers.
  industryExperience: [
    "Accounting and Bookkeeping",
    "Advertising, Design, Marketing",
    "Agriculture, Farming, Livestock",
    "Architecture, Engineering",
    "Arts, Entertainment and Recreation",
    "Auto Repair",
    "Beauty, Cosmetics and Salon Services",
    "Business Consulting and Coaching",
    "Childcare",
    "Commercial and Residential Services",
    "Construction & Real Estate",
    "Counseling and Therapy",
    "Cybersecurity",
    "E-Commerce & Online Business",
    "Education",
    "Energy & Utilities",
    "Financial Services & Banking",
    "Group Homes",
    "Healthcare & Medical",
    "Hospitality, Restaurants & Food Service",
    "Manufacturing & Industrial",
    "Media, Marketing & Publishing",
    "Nonprofit & Social Impact",
    "Professional Services",
    "Retail & Consumer Products",
    "Technology & Software",
    "Transportation and Logistics",
    "Wellness and Fitness",
  ],
  // <<< crm-enum

  // The mentor "Areas of Expertise" multi-select maps to CMentorProfile.areaOfExpertise
  // (skill areas, distinct from the Industry Experience question).
  // >>> crm-enum key=areasOfExpertise field=CMentorProfile.areaOfExpertise — generated; do not hand-edit between the markers.
  areasOfExpertise: [
    "Accounting",
    "Artificial Intelligence for Small Businesses",
    "Arts: Visual, Crafts, Music, etc.",
    "Business Strategy & Planning",
    "Compliance & Accreditation Audits",
    "Customer Experience & Service Excellence",
    "Digital Marketing & Social Media",
    "E-Commerce",
    "Finance & Cash Flow Management",
    "Franchising",
    "Funding & Capital Access",
    "Government Contracting and Regulations",
    "Group Homes",
    "Hospitality, Restaurants, Food Trucks, Lodging",
    "Human Resources & Talent Management",
    "International Business & Market Expansion",
    "Leadership & Executive Coaching",
    "Marketing & Branding",
    "Mergers, Acquisitions & Exit Planning",
    "Nonprofit Management & Fundraising",
    "Operations & Process Improvement",
    "Product Development & Innovation",
    "Program Design & Implementation",
    "Retail and Merchandising",
    "Sales & Business Development",
    "Social Assistance & Family Services",
    "Startup Launch & Entrepreneurship",
    "Strategic Planning",
    "Technology & Digital Transformation",
    "Transportation and Logistics",
    "Websites",
  ],
  // <<< crm-enum

  // MUST match CMentorProfile.fluentLanguages verbatim — values outside this enum
  // 400 the create. The live crm-test enum currently holds only these two; it
  // looks under-populated and should be expanded CRM-side, after which a sync
  // run will grow this list to match.
  // >>> crm-enum key=fluentLanguages field=CMentorProfile.fluentLanguages — generated; do not hand-edit between the markers.
  fluentLanguages: [
    "English",
    "Spanish",
  ],
  // <<< crm-enum

  // "Choose up to N" constraint applied to industry + expertise.
  maxChoices: 6,
};
