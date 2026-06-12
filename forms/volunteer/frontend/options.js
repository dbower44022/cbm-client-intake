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

  // Aligned to CMentorProfile.industrySector (20 NAICS sectors).
  industryExperience: [
    "Agriculture, Forestry, Fishing and Hunting",
    "Mining, Quarrying, and Oil and Gas Extraction", "Utilities", "Construction",
    "Manufacturing", "Wholesale Trade", "Retail Trade",
    "Transportation and Warehousing", "Information", "Finance and Insurance",
    "Real Estate and Rental and Leasing",
    "Professional, Scientific, and Technical Services",
    "Management of Companies and Enterprises",
    "Administrative and Support and Waste Management", "Educational Services",
    "Health Care and Social Assistance", "Arts, Entertainment, and Recreation",
    "Accommodation and Food Services",
    "Other Services (except Public Administration)", "Public Administration",
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

  // Aligned to CMentorProfile.fluentLanguages.
  fluentLanguages: [
    "American Sign Language", "Arabic", "Bengali", "Cantonese", "Chinese",
    "Czech", "Danish", "Dutch", "English", "French", "German", "Greek",
    "Gujarati", "Hebrew", "Hindi", "Hungarian", "Indonesian", "Italian",
    "Japanese", "Korean", "Lithuanian", "Malay", "Mandarin", "Marathi",
    "Norwegian", "Pashto", "Polish", "Portuguese", "Punjabi", "Russian",
    "Spanish", "Swedish", "Tagalog", "Telugu", "Urdu", "Other",
  ],

  // "Choose up to N" constraint applied to industry + expertise.
  maxChoices: 6,
};
