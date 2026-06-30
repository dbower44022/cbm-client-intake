/*
 * Form value lists.
 *
 * Sourced from the canonical CBM lists where available (the 8-value "how did
 * you hear", the 20 NAICS sectors, and the 42 Mentoring Focus Areas match the
 * Contact/Account/Engagement Entity PRDs). Per Requirements Specification §11,
 * the Mentoring Focus Areas and the NAICS *subsector* lists are owned upstream
 * and not yet finalized — the subsector map below is an illustrative placeholder
 * so the dependent dropdown (BR-2) is demonstrable. Reconcile before go-live.
 */
window.CBM_OPTIONS = {
  // To change CRM-backed lists, edit the CRM enum then run:
  //   uv run python scripts/sync_form_options.py --write
  // >>> crm-enum key=businessStage field=Account.cBusinessStage — generated; do not hand-edit between the markers.
  businessStage: [
    "Pre-Startup",
    "Startup",
    "Early Stage",
    "Growth Stage",
    "Established",
  ],
  // <<< crm-enum

  // >>> crm-enum key=meetingPreference field=Contact.cMeetingPreference — generated; do not hand-edit between the markers.
  meetingPreference: [
    "Video",
    "Phone",
    "Email",
    "In Person",
    "No Preference",
  ],
  // <<< crm-enum

  // >>> crm-enum key=notificationPreference field=Contact.cNotificationPreference — generated; do not hand-edit between the markers.
  notificationPreference: [
    "Email",
    "Text",
  ],
  // <<< crm-enum

  // >>> crm-enum key=howDidYouHear field=Contact.cHowDidYouHear — generated; do not hand-edit between the markers.
  howDidYouHear: [
    "CBM Client or Volunteer",
    "CBM Email",
    "News or Media",
    "Online Search",
    "Partner Referral",
    "Personal Referral",
    "Social Media",
    "Workshop or Event",
    "Other",
  ],
  // <<< crm-enum

  // NOTE: this is the NAICS sector taxonomy. The orchestrator sanitizes it against
  // Account.cIndustrySector, so if the CRM enum uses a different taxonomy the synced
  // list will replace these values — and industrySubsector (below) is keyed by them.
  // Review the sync diff before --write; reconcile the subsector keys to match.
  // >>> crm-enum key=industrySector field=Account.cIndustrySector — generated; do not hand-edit between the markers.
  industrySector: [
    "Agriculture, Forestry, Fishing and Hunting",
    "Mining, Quarrying, and Oil and Gas Extraction",
    "Utilities",
    "Construction",
    "Manufacturing",
    "Wholesale Trade",
    "Retail Trade",
    "Transportation and Warehousing",
    "Information",
    "Finance and Insurance",
    "Real Estate and Rental and Leasing",
    "Professional, Scientific, and Technical Services",
    "Management of Companies and Enterprises",
    "Administrative and Support and Waste Management",
    "Educational Services",
    "Health Care and Social Assistance",
    "Arts, Entertainment, and Recreation",
    "Accommodation and Food Services",
    "Other Services (except Public Administration)",
    "Public Administration",
  ],
  // <<< crm-enum

  // Aligned to the CRM's CEngagement.mentoringFocusAreas enum (the field the
  // orchestrator writes — the client's mentoring request). Keep in sync with it.
  // >>> crm-enum key=mentoringFocusAreas field=CEngagement.mentoringFocusAreas — generated; do not hand-edit between the markers.
  mentoringFocusAreas: [
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

  // PLACEHOLDER — canonical ~100-value list is unresolved upstream (Req Spec §11).
  // Keyed by industry sector; sectors not listed fall back to ["Other"].
  industrySubsector: {
    "Manufacturing": ["Food Manufacturing", "Apparel Manufacturing", "Machinery Manufacturing", "Other"],
    "Retail Trade": ["Food and Beverage Retailers", "Clothing and Accessories", "Online Retail", "Other"],
    "Construction": ["Residential Building", "Nonresidential Building", "Specialty Trade Contractors", "Other"],
    "Health Care and Social Assistance": ["Ambulatory Health Care", "Hospitals", "Social Assistance", "Other"],
    "Professional, Scientific, and Technical Services": ["Legal Services", "Accounting Services", "Computer Systems Design", "Other"],
  },
};
