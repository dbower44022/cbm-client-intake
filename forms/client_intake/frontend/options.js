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
  businessStage: [
    "Pre-Startup", "Startup", "Early Stage", "Growth Stage", "Established",
  ],

  meetingPreference: ["No Preference", "Video", "Phone", "Email", "In Person"],

  notificationPreference: ["Email", "Text Message"],

  howDidYouHear: [
    "Partner Referral", "Social Media", "CBM Email", "Workshop or Event",
    "Search Engine", "News or Media", "Personal Referral", "Other",
  ],

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

  mentoringFocusAreas: [
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
