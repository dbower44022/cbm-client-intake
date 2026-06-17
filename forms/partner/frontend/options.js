/*
 * Become-a-Partner form value lists. partnershipType and partnershipValue are
 * aligned to the deployed CRM enums (CPartnerProfile.partnershipType /
 * partnershipValue), so every selectable value is accepted on submit.
 * "How did you hear" maps to a free-text field, so its list is presentational.
 */
window.PARTNER_OPTIONS = {
  partnershipType: [
    "Referral Partner",
    "Training Partner",
    "Cohort",
    "Service Partner",
    "Funding Partner",
    "Community Partner",
  ],

  // Aligned to CPartnerProfile.partnershipValue (multiEnum). "None" is omitted
  // from the form — an applicant offering nothing simply checks nothing.
  partnershipValue: [
    "Connection to stakeholders / expanding influence",
    "Workshop Speakers / Educational Resources",
    "Co-Hosted Events",
    "Link on Website",
    "Facilities",
    "Funding / Donations",
    "Other",
  ],

  howDidYouHear: [
    "Friend or relative", "Newspaper", "Online search", "Radio", "SBA",
    "CBM client or volunteer", "Social media", "TV", "Workshop/Event", "Other",
  ],
};
