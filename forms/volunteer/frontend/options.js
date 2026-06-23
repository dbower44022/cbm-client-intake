/*
 * Volunteer form value lists (SCORE form 6). The industry, expertise, and
 * language lists are aligned to the deployed CRM enum options
 * (CMentorProfile.industrySector / mentoringFocusAreas / fluentLanguages), so
 * every selectable value is accepted on submit. "How did you hear" maps to a
 * free-text CRM field, so its list is presentational only.
 */
window.VOL_OPTIONS = {
  phoneType: ["Mobile", "Home", "Work"],
  contactPreference: ["Email", "Phone", "Text", "No Preference"],
  employment: ["Yes, Full-time", "Yes, Part-time", "No"],

  howDidYouHear: [
    "Friend or relative", "Newspaper", "Online search", "Radio", "SBA",
    "CBM client or volunteer", "Social media", "TV", "Workshop/Event", "Other",
  ],

  // MUST match CMentorProfile.industrySector verbatim — a value outside this enum
  // 400s the whole CMentorProfile create. Mirrored from the live crm-test enum
  // (2026-06-23); the misspellings ("Livestoack", "Archtecture", "Group  homes")
  // are the CRM's actual option strings, so they are kept exactly. Fix CRM-side
  // first, then update here.
  industryExperience: [
    "Accounting and bookkeeping", "Advertising, Design, Marketing",
    "Agriculture, Farming, Livestoack", "Archtecture, Engineering",
    "Arts, Entertainment and Recreation", "Auto Repair",
    "Beauty, Cosmetics and Salon Services", "Business Consulting and Coaching",
    "Childcare", "Commercial and Residential Services", "Construction & Real Estate",
    "Counseling and Therapy", "Cybersecurity", "E-Commerce & Online Business",
    "Education", "Energy & Utilities", "Financial Services & Banking",
    "Group  homes", "Healthcare & Medical",
    "Hospitality, Restaurants & Food Service", "Manufacturing & Industrial",
    "Media, Marketing & Publishing", "Nonprofit & Social Impact",
    "Professional Services", "Retail & Consumer Products", "Technology & Software",
    "Transportation and Logistics", "Wellness and Fitness",
  ],

  // Aligned to CMentorProfile.mentoringFocusAreas.
  areasOfExpertise: [
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

  // MUST match CMentorProfile.fluentLanguages verbatim — values outside this enum
  // 400 the create. The live crm-test enum currently holds only these two
  // (2026-06-23); it looks under-populated and should be expanded CRM-side, after
  // which this list can grow to match.
  fluentLanguages: ["English", "Spanish"],

  // "Choose up to N" constraint applied to industry + expertise.
  maxChoices: 6,
};
