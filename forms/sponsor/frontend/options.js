/*
 * Become-a-Sponsor form value lists. "How did you hear" maps to the
 * Contact.cHowDidYouHear enum, kept in sync via:
 *   uv run python scripts/sync_form_options.py --write
 */
window.SPONSOR_OPTIONS = {
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
