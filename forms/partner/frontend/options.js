/*
 * Become-a-Partner form value lists. partnershipType and partnershipValue are
 * aligned to the deployed CRM enums (CPartnerProfile.partnershipType /
 * partnershipValue), so every selectable value is accepted on submit.
 * "How did you hear" maps to a free-text field, so its list is presentational.
 */
window.PARTNER_OPTIONS = {
  // To change these, edit the CRM enum then run:
  //   uv run python scripts/sync_form_options.py --write
  // >>> crm-enum key=partnershipType field=CPartnerProfile.partnershipType — generated; do not hand-edit between the markers.
  partnershipType: [
    "Referral Partner",
    "Training Partner",
    "Cohort",
    "Service Partner",
    "Funding Partner",
    "Community Partner",
    "other",
  ],
  // <<< crm-enum

  // Aligned to CPartnerProfile.partnershipValue (multiEnum). "None" is omitted
  // from the form — an applicant offering nothing simply checks nothing — so the
  // sync excludes it (exclude="None") even though the CRM enum carries it.
  // >>> crm-enum key=partnershipValue field=CPartnerProfile.partnershipValue exclude="None" — generated; do not hand-edit between the markers.
  partnershipValue: [
    "Connection to stakeholders / expanding influence",
    "Co-Hosted Events",
    "Facilities",
    "Link on Website",
    "Funding / Donations",
    "Workshop Speakers / Educational Resources",
    "Other",
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
};
