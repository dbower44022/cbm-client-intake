/*
 * Volunteer form value lists (SCORE form 6). The industry, expertise, and
 * language lists are aligned to the deployed CRM enum options
 * (CMentorProfile.industrySector / mentoringFocusAreas / fluentLanguages), so
 * every selectable value is accepted on submit. Contact-method, employment, and
 * "how did you hear" are also CRM-backed (Contact enums) — all CRM-backed lists
 * are kept in sync via: uv run python scripts/sync_form_options.py --write
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

  // MUST match CMentorProfile.industrySector verbatim — a value outside this enum
  // 400s the whole CMentorProfile create. The misspellings ("Livestoack",
  // "Archtecture", "Group  homes") are the CRM's actual option strings. To change
  // them, fix the CRM enum then run: uv run python scripts/sync_form_options.py --write
  // >>> crm-enum key=industryExperience field=CMentorProfile.industrySector — generated; do not hand-edit between the markers.
  industryExperience: [
    "Accommodation and Food Services",
    "Administrative and Support and Waste Management",
    "Agriculture, Forestry, Fishing and Hunting",
    "Arts, Entertainment, and Recreation",
    "Construction",
    "Educational Services",
    "Finance and Insurance",
    "Health Care and Social Assistance",
    "Information",
    "Management of Companies and Enterprises",
    "Manufacturing",
    "Mining, Quarrying, and Oil and Gas Extraction",
    "Other Services (except Public Administration)",
    "Professional, Scientific, and Technical Services",
    "Public Administration",
    "Real Estate and Rental and Leasing",
    "Retail Trade",
    "Transportation and Warehousing",
    "Utilities",
    "Wholesale Trade",
  ],
  // <<< crm-enum

  // Aligned to CMentorProfile.mentoringFocusAreas.
  // >>> crm-enum key=areasOfExpertise field=CMentorProfile.mentoringFocusAreas — generated; do not hand-edit between the markers.
  areasOfExpertise: [
    "Accounting & Tax Services",
    "Advertising, Design, & Marketing",
    "Agriculture",
    "Animal & Veterinary Services",
    "Architecture, Engineering, & Related Services",
    "Arts, Entertainment, & Recreation",
    "Auto Repair & Mechanic",
    "Beauty, Cosmetics & Salon Services",
    "Business Consulting & Coaching",
    "Childcare",
    "Commercial & Residential Services",
    "Construction",
    "Counseling & Therapy",
    "Distribution & Transportation of Goods",
    "Education",
    "Farming & Livestock",
    "Fine Arts, Artisan, & Craft Work",
    "Fishing & Hunting",
    "Food & Beverage",
    "Forestry",
    "Funeral & Death Care Services",
    "Information Technology",
    "Manufacturing",
    "Media & Publishing",
    "Mining, Quarry, & Utilities",
    "Nonprofit",
    "Personal Care Services",
    "Photography & Video Services",
    "Professional Services",
    "Public Relations & Communications",
    "Real Estate",
    "Recruiting & Staffing",
    "Rental & Leasing",
    "Restaurant & Bar",
    "Retail",
    "Social Assistance & Family Services",
    "Transportation",
    "Travel, Hospitality, & Tourism",
    "Warehousing",
    "Waste Management & Disposal",
    "Website Development",
    "Wellness, Healthcare, & Home Health",
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
