/*
 * Volunteer form value lists (SCORE form 6). Sourced from the form's own
 * dropdowns; per the mapping doc §4 these reconcile to canonical CBM lists
 * (industry/expertise/languages/how-heard) before go-live.
 */
window.VOL_OPTIONS = {
  phoneType: ["Mobile", "Home", "Work"],
  contactPreference: ["Email", "Phone", "Text", "No Preference"],
  employment: ["Yes, Full-time", "Yes, Part-time", "No"],

  howDidYouHear: [
    "Friend or relative", "Newspaper", "Online search", "Radio", "SBA",
    "SCORE client or volunteer", "Social media", "TV", "Workshop/Event", "Other",
  ],

  industryExperience: [
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
    "Social Assistance & Family Services", "Travel, Hospitality, & Tourism",
    "Warehousing", "Waste Management & Disposal", "Website Development",
    "Wellness, Healthcare, & Home Health", "Wholesale", "Transportation",
  ],

  areasOfExpertise: [
    "Accounting & Finance", "Advertising", "Bookkeeping", "Branding", "Budgeting",
    "Business Plan", "Business Structure", "Cash Flow", "Communications Tech",
    "Contracts", "Customer Service", "Cybersecurity", "Digital Marketing",
    "Disaster Prep & Recovery", "Ecommerce", "Financial Literacy", "Franchising",
    "Funding/Loans", "Government Contracting", "Government Regulations",
    "Hardware & Equipment", "Human Resources", "Import & Export",
    "Intellectual Property", "Legal", "Management & Operations", "Marketing",
    "Marketing Strategy", "PR/Media", "Pricing", "Product Development", "Sales",
    "Social Media", "Software & Applications", "Strategy Development",
    "Supply Chain Management", "Tax Planning", "Technology", "Websites",
    "Work/Life Balance",
  ],

  fluentLanguages: [
    "English", "Spanish", "Chinese", "Tagalog", "Vietnamese", "French", "Korean",
    "Arabic", "American Sign Language", "Bengali", "Cantonese", "Dutch", "German",
    "Greek", "Gujarati", "Hebrew", "Hindi", "Italian", "Japanese", "Mandarin",
    "Polish", "Portuguese", "Punjabi", "Russian", "Swedish", "Telugu", "Urdu",
    "Other",
  ],

  // "Choose up to N" constraint applied to industry + expertise.
  maxChoices: 6,
};
