# System Settings — finding a setting

Last Updated: 11-18-26 01:39 · Revision 0.3 · **Built (v0.345.0); Stop 2 — Doug's review on the Association**

## 1. What this changes

The Settings tab of System Settings (`/setup`) holds 286 settings in 11 groups. The Features group alone holds 85 of them, in the order they were built, so related settings sit far apart. The filter box needs the exact phrase: "zoom meeting" finds a setting, "meeting zoom" finds nothing (`setup/frontend/app.js:194`).

Doug chose option A on 11-18-26: three parts, built together.

1. **Sub-tabs by application.** The Settings tab gets ten sub-tabs, one per application area. A setting sits in the area whose screen it changes.
2. **Headings, then a fixed order.** Inside a sub-tab, settings fall under short headings. Under each heading the feature's main on/off switch comes first, and everything else follows A to Z by label.
3. **A search that matches each word and spans every sub-tab.** Each word typed must appear somewhere in the label, the key, the help, the area or the heading, in any order. While the box holds text, each sub-tab's label shows its count of matches, such as "Events (3)", and a sub-tab with none is dimmed, never hidden.

## 2. The ten areas

Marketing Management (47), Events (26), Business Evaluation (7), Staff and mentor tools (25), Email (22), Documents, calendar and meetings (12), Website and branding (39), Team gates (17), Connected services (40), Platform (51). Counts are from the draft assignment in the appendix.

**Connected services** holds what belongs to an outside service rather than to a feature: its *in use* switch, its account details, keys and web addresses. A feature's own behaviour stays with the feature. So *Campaign texts* is in Marketing Management, and the Twilio account details are in Connected services.

**Platform** holds the plumbing: delivery and retries, alerts, the CRM connection, access and security, the training sandbox and the deployment's own foundations.

## 3. How it is built

- **Registry.** Each `SettingSpec` in `core/settings_registry.py` gains two fields: `area` and `heading`. Each area names its main switch per heading. The existing `group` field and `GROUP_ORDER` stay while the old layout is still served (§ 4), and are removed at the end.
- **Order.** The server sends each area's headings in the registry's order and each heading's settings already sorted: the main switch first, then A to Z by label. The browser does not re-sort.
- **Restart-required settings** show a *Restart required* badge on their row in their own area, and *Waiting for restart* when the stored value and the value in force differ, as today. The summary at the top of the page that lists every setting waiting for a restart stays, and each name in it opens that setting. Ruling Q1.
- **The website images panel** moves with the Website and branding area.
- **Only overridden** and the search both work across every sub-tab.
- **Opening a setting by name** (the History tab and the restart summary do this, `setup/frontend/app.js:890`) selects its sub-tab first, then scrolls to it.
- **The last sub-tab opened is remembered** in the browser, with a fallback to the first sub-tab.
- **Guard tests.** Every setting names an area and a heading from the known lists, and every heading's settings come out switch-first then A to Z. A new setting without an area fails the test suite. That is the rule for future features, and `setup/CLAUDE.md` says so.

## 4. Switch and rollback

Built dark behind a new setting, **Settings page sub-tabs** (`SETTINGS_AREAS`), default off, read per request so no restart is needed. Off, the page is exactly as it is today. Rollback is switching it off. Once Doug has used it on the Association's system and then on production, a later release removes the old layout and the switch.

## 5. Stopping points

Work pauses for Doug at each of these. Between them it proceeds without asking.

1. **Stop 1 — rulings.** Doug rules on § 6 and corrects the appendix. The plan becomes revision 0.2.
2. Build: the registry fields and guard tests; the server payload; the sub-tabs, order, search and remembered sub-tab; the documentation (`SYSTEM-SETTINGS-SETUP.md`, `setup/CLAUDE.md`, `CHANGELOG.md`) and the version bump. Committed locally, tests passing.
3. **Stop 2 — review.** Doug pushes, switches it on at the Association's System Settings and uses it. Corrections go in before production.
4. **Stop 3 — production.** Switched on at production's System Settings. The removal of the old layout is a separate, later release.

## 6. Rulings

All eight decided by Doug on 11-18-26, each as recommended (option A), after one-at-a-time discussion.

**Q1. Restart-required settings go to their own areas.** Each of the nine moves to the area of the application it controls (*Events & Webinars* and *Public events API* to Events, *Analytics* and *Staff applications* to Staff and mentor tools, the other five to Platform). Each row keeps its *Restart required* badge and its *Waiting for restart* marker, and the summary at the top of the page keeps listing every restart that is waiting, each name opening its setting. This keeps the honesty of the 08-28-26 ruling; only the side-by-side group goes.

**Q2. An outside service's account details live in Connected services.** One heading per service: its *in use* switch, account details, keys and web addresses. A feature's own behaviour stays with the feature. A feature that needs a service says so in its help text, naming Connected services.

**Q3. The login integrity check's ten settings go to Staff and mentor tools,** under *Login integrity check*: the four switches (now in Features) and the six details (now in Email).

**Q4. The seven alert settings go to Platform,** under *Alerts and checks*: the three addresses (now in Email) and the four thresholds (now in Reliability).

**Q5. *Promote this event* goes to Events.** The rule: a setting lives where its screen is. Its help text says it needs Marketing Management.

**Q6. *Personal outreach to leads* goes to Marketing Management,** under *Leads and fit scores*, by the Q5 rule. Its help text names Gmail sync as a requirement.

**Q7. *Verify CBM mailbox exists* and *Create missing mailboxes* go to Staff and mentor tools,** under *Mentor logins*, by the Q2 rule: they are feature behaviour, not account details.

**Q8. With the Integrations tab on, feature settings stay in their areas** and also appear on their service's sub-tab of the Integrations tab. Only the Connected services sub-tab is hidden while the Integrations tab is on, because that tab holds the same settings. A setting shown in two places shows the same stored value, and a save in either updates both. With sub-tabs off, the Integrations tab behaves exactly as today.

## Appendix — draft assignment of every setting

> **As built, `core/settings_areas.py` is the authority**, not this list. It
> differs from the list below in three places: *Campaign texts* moved under
> *Text messages* as that heading's main switch; the Zoom heading split into
> *Zoom Meetings* and *Zoom Webinars*, each led by its *in use* switch; and two
> settings added since were placed — *New home page* (`home_v2`) in Staff and
> mentor tools, and *Settings page sub-tabs* (`settings_areas`) in Platform,
> under *This deployment*.

Generated from `core/settings_registry.py` on 11-18-26. The first heading of each area is its main switch heading. Order within a heading here is the registry's, not the final A-to-Z order. "now in" names today's group. The new switch `SETTINGS_AREAS` itself goes in Platform, under *This deployment*.

### Marketing Management — 47 settings


**Marketing Management**

- Marketing Management (`campaigns_enabled`) — now in Features
- Postcard landing page (`campaigns_landing_public`) — now in Features
- Campaign run poll (`campaigns_run_seconds`) — now in Features
- Campaign calls (`campaigns_calls`) — now in Features
- Calls tab side panel (`calls_panel`) — now in Features
- Campaign emails (`campaigns_email`) — now in Features
- Campaign texts (`campaigns_sms`) — now in Features
- Campaign send report (`campaign_send_report`) — now in Features
- Campaign send report interval (`campaign_send_report_seconds`) — now in Features

**Campaign lists**

- Campaign lists (`campaign_lists`) — now in Features
- Campaign list copies (`campaign_list_sync`) — now in Features
- Campaigns send to lists only (`campaign_lists_only`) — now in Features
- Campaign list screens (`campaign_list_screens`) — now in Features
- Campaign list count interval (`campaign_list_count_seconds`) — now in Features
- Campaign list fields (`campaign_list_fields`) — now in Features

**Leads and fit scores**

- Lead fit scores (`enrichment_free_pass`) — now in Features
- Lead web checks (`enrichment_web_checks`) — now in Features
- Lead fit sweep (`enrichment_sweep_seconds`) — now in Features
- Lead fit batch (`enrichment_batch`) — now in Features
- Service area counties (`chapter_counties`) — now in Features
- Fit score weights (`fit_weights`) — now in Features
- Segment list address (`chapter_segments_url`) — now in Features
- Name rules address (`enrichment_terms_url`) — now in Features
- Lead qualification ladder (`lead_ladder`) — now in Features
- Lead level sweep (`lead_level_sweep_seconds`) — now in Features
- Prospect stale after (`prospect_stale_days`) — now in Features
- Prospect stale sweep (`prospect_stale_sweep_seconds`) — now in Features
- Personal outreach to leads (`lead_outreach`) — now in Features
- Import templates (`import_templates`) — now in Features
- Import plan poll (`import_plan_poll_seconds`) — now in Features

**AI research**

- AI research (`enrichment_ai`) — now in Features
- AI research model (`enrichment_ai_model`) — now in Features
- Enrichment monthly budget (`enrichment_monthly_budget`) — now in Features
- AI research searches per business (`enrichment_ai_max_searches`) — now in Features
- AI research cap per business (`enrichment_ai_record_cap`) — now in Features
- AI research records per run (`enrichment_ai_max_records`) — now in Features
- AI research fallback (`enrichment_ai_fallback`) — now in Features
- AI research queue poll (`enrichment_ai_poll_seconds`) — now in Features

**Postcards**

- Postcard unit cost (`postal_unit_cost`) — now in Integrations
- Postcard cost currency (`postal_currency`) — now in Integrations

**Text messages**

- Texting sender number (`sms_from_number`) — now in Integrations
- Texting hours (`sms_send_hours`) — now in Integrations
- Texting time zone (`sms_timezone`) — now in Integrations

**Mailing list**

- Mailing list sync (`mailing_sync`) — now in Features
- Mailing list name (`mailing_list_name`) — now in Integrations
- Mailing push interval (`mailing_push_seconds`) — now in Integrations
- Mailing pull interval (`mailing_pull_seconds`) — now in Integrations

### Events — 26 settings


**Events**

- Events & Webinars (`events_enabled`) — now in Restart required; restart required
- Presenters on events (`event_presenters`) — now in Features
- Promote this event (`event_promote`) — now in Features
- Registration confirmation emails (`events_confirmations`) — now in Features

**Hosting**

- Zoom webinar provisioning (`zoom_events`) — now in Features
- Zoom meeting provisioning (`zoom_meetings_events`) — now in Features
- Default hosting method, public events (`events_default_method_public`) — now in Features
- Default hosting method, members-only events (`events_default_method_members`) — now in Features
- Events on another platform (`events_other_platform`) — now in Features
- Attendance pull (`events_attendance_seconds`) — now in Reliability
- Attendance grace (`events_attendance_grace_minutes`) — now in Reliability
- Attendance give-up (`events_attendance_give_up_hours`) — now in Reliability

**Reminders**

- Event reminder emails (`events_reminders`) — now in Features
- Reminder sweep (`events_reminder_seconds`) — now in Reliability
- Reminder lead time (`events_reminder_lead_hours`) — now in Reliability

**Public programme page**

- Public events API (`events_public_api`) — now in Restart required; restart required
- Public event page base (`events_public_base_url`) — now in Presentation
- Public read cache (`events_cache_seconds`) — now in Presentation
- Programme page tagline (`events_hero_tagline`) — now in Presentation
- Programme page pillars (`events_hero_pillars`) — now in Presentation
- Programme page band (`events_hero_band`) — now in Presentation
- Default event graphic (`events_default_graphic_url`) — now in Presentation
- Programme contact address (`events_contact_email`) — now in Presentation
- YouTube playlists (`youtube_playlist_id`) — now in Integrations

**Portal calendar**

- Events on the portal home page (`portal_calendar`) — now in Features
- Portal calendar window (`portal_events_window_days`) — now in Features

### Business Evaluation — 7 settings


**Business Evaluation**

- Business Evaluation (`business_evaluation`) — now in Features
- Evaluation link lifetime (`evaluation_link_days`) — now in Features
- Evaluation retry interval (`evaluation_retry_seconds`) — now in Features
- Evaluation analysis interval (`evaluation_analysis_seconds`) — now in Features
- Evaluation analysis model (`evaluation_model`) — now in Features
- Analyze evaluations before a mentor is assigned (`evaluation_analyze_unassigned`) — now in Features
- Intake survey (`intake_survey`) — now in Features

### Staff and mentor tools — 25 settings


**Staff and mentor tools**

- Staff applications (`assignments_enabled`) — now in Restart required; restart required
- Add partners & funders in-app (`record_quick_add`) — now in Features
- History tab on records (`record_history_tab`) — now in Features
- Activity page (`activity_page`) — now in Features
- My Mentor Profile — website profile preview (`mentor_preview_shared`) — now in Features
- Grants on funder records (`grants_enabled`) — now in Features

**Mentor logins**

- Provision mentor logins (`mentor_provision_users`) — now in Features
- Verify CBM mailbox exists (`google_directory_check`) — now in Features
- Create missing mailboxes (`google_create_mailbox`) — now in Features
- Strict mentor profile choice (`manager_profile_strict`) — now in Features
- Lock the mentor CBM email (`cbm_email_lock`) — now in Features
- Stop login repairs on disagreement (`login_repair_guards`) — now in Features

**Login integrity check**

- Daily login integrity check (`login_integrity_check`) — now in Features
- Tell staff about login faults (`integrity_digest`) — now in Features
- Report work in the CRM's own screens (`integrity_crm_use_report`) — now in Features
- Alert when a login has no mentor profile (`integrity_signin_alert`) — now in Features
- Login fault recipients (`integrity_digest_to`) — now in Email
- Integrity check hour (`login_integrity_hour`) — now in Email
- Integrity check timezone (`login_integrity_tz`) — now in Email
- Shared CRM accounts (`integrity_shared_accounts`) — now in Email
- Logins not reported for CRM edits (`integrity_excluded_logins`) — now in Email
- This application's network addresses (`integrity_app_addresses`) — now in Email

**Analytics**

- Analytics (`analytics_enabled`) — now in Restart required; restart required
- Analytics warm job (`analytics_refresh_seconds`) — now in Reliability
- Analytics cache TTL (`analytics_default_cache_ttl_seconds`) — now in Reliability

### Email — 22 settings


**Email**

- Gmail conversation sync (`gmail_sync`) — now in Features
- Gmail sync cadence (`gmail_sync_seconds`) — now in Email
- Initial sync window (`gmail_backfill`) — now in Email
- Dead-letter after (`gmail_dead_letter_passes`) — now in Email
- Gmail one-shot resync (`gmail_resync`) — now in Features
- Mailbox scope rebuild (`comms_scope_rebuild_seconds`) — now in Email
- Internal domains (`comms_internal_domains`) — now in Email
- Mentor email domain (`mentor_email_domain`) — now in Email
- Active engagement statuses (`comms_engagement_statuses`) — now in Email
- Excluded partner statuses (`comms_partner_excluded_statuses`) — now in Email
- Never file these attachments (`comms_attachment_excluded_types`) — now in Email

**Shared mailbox**

- Shared mailbox (`ops_mailbox`) — now in Email
- Shared mailbox display name (`ops_mailbox_name`) — now in Email
- Canned reply template (`ops_reply_template`) — now in Email
- Inbound poll (`ops_inbound_seconds`) — now in Email
- Inbound sweep window (`ops_inbound_window_days`) — now in Email

**Summaries and digest**

- AI conversation summaries (`comms_ai_summary`) — now in Features
- Summary model (`summary_model`) — now in Integrations
- Daily email digest (`comms_digest`) — now in Features
- Digest hour (`comms_digest_hour`) — now in Email
- Digest timezone (`comms_digest_tz`) — now in Email
- Digest re-check (`comms_digest_seconds`) — now in Email

### Documents, calendar and meetings — 12 settings


**Google Drive documents**

- Google Drive documents (`gdrive_docs`) — now in Features
- Drive identity (`gdrive_identity`) — now in Integrations
- Shared drive ID (`gdrive_shared_drive_id`) — now in Integrations
- Drive folder labels (`gdrive_entity_labels`) — now in Integrations
- Document types (`gdrive_doc_types`) — now in Integrations
- Max upload size (`gdrive_max_file_mb`) — now in Integrations
- Drive grant reconciliation (`gdrive_reconcile_seconds`) — now in Integrations

**Calendar**

- Google Calendar events (`gcal_events`) — now in Features

**Transcripts**

- Meet transcripts (`meet_transcripts`) — now in Features
- Fathom transcripts (`fathom_transcripts`) — now in Features
- Transcript retrieval (`meet_transcripts_poll_seconds`) — now in Integrations
- Transcript give-up window (`transcript_give_up_days`) — now in Integrations

### Website and branding — 39 settings


**Chapter identity**

- Organisation name (`organization_name`) — now in Website
- Chapter acronym (`organization_abbreviation`) — now in Website
- Chapter short label (`chapter_key`) — now in Presentation
- Chapter postal address (`chapter_postal_address`) — now in Website
- Chapter contact email (`chapter_email`) — now in Website
- Chapter telephone (`chapter_phone`) — now in Website
- Employer identification number (`chapter_ein`) — now in Website
- Donation payment page (`chapter_payment_url`) — now in Website
- Social media addresses (`chapter_social_links`) — now in Website
- Organisation logo URL (`organization_logo_url`) — now in Website
- Organisation website (`organization_website_url`) — now in Website
- Documentation site (`docs_site_url`) — now in Presentation

**Policies**

- Client code of conduct URL (`policy_client_conduct_url`) — now in Presentation
- Mentor code of ethics URL (`policy_mentor_ethics_url`) — now in Presentation
- Terms of use URL (`policy_terms_url`) — now in Presentation
- Privacy policy URL (`policy_privacy_url`) — now in Presentation

**Chapter website**

- Chapter website connection (`website_api`) — now in Features
- Chapter website addresses (`website_origins`) — now in Website
- Forms in website frames (`form_framing`) — now in Features
- Newsletter signup form (`newsletter_form`) — now in Features
- Website menu (`organization_site_nav`) — now in Website
- Key page refresh (`website_cache_seconds`) — now in Website
- Key page — Find a Mentor (`website_page_mentors`) — now in Website
- Key page — Workshops and Events (`website_page_events`) — now in Website
- Key page — Recordings (`website_page_recordings`) — now in Website
- Key page — Our Partners (`website_page_partners`) — now in Website
- Key page — Our Sponsors (`website_page_sponsors`) — now in Website
- Key page — Client Stories (`website_page_stories`) — now in Website

**Colours and fonts**

- Chapter design-token override (`chapter_tokens_url`) — now in Website
- Colour — background (`website_color_base`) — now in Website
- Colour — text (`website_color_contrast`) — now in Website
- Colour — main brand (`website_color_accent_1`) — now in Website
- Colour — light brand tint (`website_color_accent_2`) — now in Website
- Colour — highlight (`website_color_accent_3`) — now in Website
- Colour — muted text (`website_color_accent_4`) — now in Website
- Colour — light section background (`website_color_accent_5`) — now in Website
- Colour — borders (`website_color_accent_6`) — now in Website
- Font — headings (`website_font_heading`) — now in Website
- Font — body text (`website_font_body`) — now in Website

### Team gates — 17 settings


**Who can open each application**

- Client Administration (`assign_allowed_teams`) — now in Team gates
- Client Administration (roles) (`assign_allowed_roles`) — now in Team gates
- Mentor Administration (`mentor_admin_allowed_teams`) — now in Team gates
- System Management (`system_management_allowed_teams`) — now in Team gates
- My Mentor Profile (`mentor_profile_allowed_teams`) — now in Team gates
- Submission Admin (`ops_allowed_teams`) — now in Team gates
- Client Management (`session_mentor_allowed_teams`) — now in Team gates
- Partner Management (`session_partner_allowed_teams`) — now in Team gates
- Funder Management (`session_sponsor_allowed_teams`) — now in Team gates
- Workspace Directories (`workspace_allowed_teams`) — now in Team gates
- Event Administration (`events_allowed_teams`) — now in Team gates
- Marketing Management (`campaigns_allowed_teams`) — now in Team gates
- Analytics — view (`analytics_view_allowed_teams`) — now in Team gates
- Analytics — author (`analytics_admin_allowed_teams`) — now in Team gates

**Team stamps**

- Mentor team (provisioning) (`mentor_team_name`) — now in Team gates
- Partner team stamp (`partner_team_name`) — now in Team gates
- Funder team stamp (`sponsor_team_name`) — now in Team gates

### Connected services — 40 settings


**Connected services**

- Integrations tab (`integrations_tab`) — now in Features

**Google Workspace**

- Google Workspace in use (`google_workspace_in_use`) — now in Integrations
- Google service account (`google_service_account_json`) — now in Integrations
- Delegated Workspace admin (`google_delegated_admin`) — now in Integrations
- All Members group (`google_members_group`) — now in Integrations

**Zoom**

- Zoom Webinars in use (`zoom_in_use`) — now in Integrations
- Zoom Meetings in use (`zoom_meetings_in_use`) — now in Integrations
- Zoom Meetings account ID (`zoom_meetings_account_id`) — now in Integrations
- Zoom Meetings client ID (`zoom_meetings_client_id`) — now in Integrations
- Zoom Meetings client secret (`zoom_meetings_client_secret`) — now in Integrations
- Event host user (`zoom_event_host_email`) — now in Integrations
- Zoom Meetings capacity limit (`zoom_meetings_capacity`) — now in Integrations
- Zoom Webinars on the same account as Zoom Meetings (`zoom_webinars_same_account`) — now in Integrations
- Zoom Webinars host (separate account only) (`zoom_host_email`) — now in Integrations
- Zoom Webinars account ID (separate account only) (`zoom_account_id`) — now in Integrations
- Zoom Webinars client ID (separate account only) (`zoom_client_id`) — now in Integrations
- Zoom Webinars client secret (separate account only) (`zoom_client_secret`) — now in Integrations
- Zoom API base URL (`zoom_base_url`) — now in Integrations

**Fathom**

- Fathom in use (`fathom_in_use`) — now in Integrations
- Fathom API key (`fathom_api_key`) — now in Integrations
- Fathom API base URL (`fathom_base_url`) — now in Integrations

**Constant Contact**

- Constant Contact in use (`constant_contact_in_use`) — now in Integrations
- Mailing service client ID (`mailing_client_id`) — now in Integrations
- Mailing service client secret (`mailing_client_secret`) — now in Integrations
- Mailing service API base URL (`mailing_base_url`) — now in Integrations

**Lob**

- Lob in use (`lob_in_use`) — now in Integrations
- Mail vendor (`postal_provider`) — now in Integrations
- Mail vendor API key (`postal_api_key`) — now in Integrations
- Mail vendor webhook secret (`postal_webhook_secret`) — now in Integrations
- Mail vendor test mode (`postal_test_mode`) — now in Integrations

**Twilio**

- Twilio in use (`twilio_in_use`) — now in Integrations
- Texting service (`sms_provider`) — now in Integrations
- Texting account SID (`sms_account_sid`) — now in Integrations
- Texting auth token (`sms_auth_token`) — now in Integrations

**Anthropic**

- Anthropic in use (`anthropic_in_use`) — now in Integrations
- Anthropic API key (`anthropic_api_key`) — now in Integrations
- Integration agent model (`integration_agent_model`) — now in Integrations
- Integration agent monthly budget (`integration_agent_monthly_budget`) — now in Integrations

**YouTube**

- YouTube in use (`youtube_in_use`) — now in Integrations
- YouTube API key (`youtube_api_key`) — now in Integrations

### Platform — 51 settings


**Submissions and delivery**

- Asynchronous delivery (`async_delivery`) — now in Features
- Near-duplicate hold (`duplicate_hold_seconds`) — now in Reliability
- Worker poll (`worker_poll_seconds`) — now in Reliability
- Worker batch size (`worker_batch_size`) — now in Reliability
- Delivery lease (`worker_lease_seconds`) — now in Reliability
- Max delivery attempts (`max_delivery_attempts`) — now in Reliability
- Receipt reconciliation (`receipt_reconcile_seconds`) — now in Reliability
- Assignment-stamp reconciliation (`assignment_reconcile_seconds`) — now in Reliability
- Intake rate limit (`intake_rate_limit`) — now in Restart required; restart required
- Intake rate window (`intake_rate_window_seconds`) — now in Restart required; restart required
- Maximum submission size (`intake_max_body_mb`) — now in Restart required; restart required

**Alerts and checks**

- Alert recipients (`alert_email_to`) — now in Email
- Alert sender (`alert_email_from`) — now in Email
- Alert webhook (`alert_webhook_url`) — now in Email
- Alert evaluation (`alert_check_seconds`) — now in Reliability
- Needs-attention threshold (`alert_needs_attention_threshold`) — now in Reliability
- Oldest-pending threshold (`alert_pending_age_minutes`) — now in Reliability
- Alert cooldown (`alert_cooldown_seconds`) — now in Reliability
- Nightly integration test hour (`integration_test_hour`) — now in Reliability
- Nightly integration test timezone (`integration_test_tz`) — now in Reliability
- Schema-drift check (`schema_check_seconds`) — now in Reliability
- Worker liveness watch (`worker_liveness_check_seconds`) — now in Reliability
- Heartbeat staleness (`worker_heartbeat_alert_seconds`) — now in Reliability
- CRM configuration check (`crm_config_refresh_seconds`) — now in Restart required; restart required

**CRM connection**

- CRM address (`espo_base_url`) — now in CRM connection
- CRM API key (`espo_api_key`) — now in CRM connection
- Dry run (no CRM writes) (`espo_dry_run`) — now in CRM connection
- Provisioning admin username (`espo_provision_username`) — now in CRM connection
- Provisioning admin password (`espo_provision_password`) — now in CRM connection
- CRM request timeout (`request_timeout_seconds`) — now in Reliability
- CRM metadata cache (`crm_metadata_cache_seconds`) — now in Reliability

**Access and security**

- This Settings page (`setup_enabled`) — now in Access & security
- Settings overrides (`settings_overrides`) — now in Access & security
- Session signing secret (`session_secret`) — now in Access & security
- HTTPS-only session cookie (`session_cookie_secure`) — now in Access & security
- Allowed origins (`allowed_origins`) — now in Access & security
- Peer deployment URL (`setup_peer_url`) — now in Access & security
- Peer deployment token (`setup_peer_token`) — now in Access & security
- Settings refresh (`setup_refresh_seconds`) — now in Reliability
- Membership re-read (`membership_refresh_seconds`) — now in Reliability

**Training sandbox**

- Nightly sandbox wipe (`sandbox_nightly_reset`) — now in Access & security
- Sandbox wipe hour (`sandbox_reset_hour`) — now in Access & security
- Sandbox wipe timezone (`sandbox_reset_tz`) — now in Access & security
- Sandbox address domain (`sandbox_address_domain`) — now in Email

**This deployment**

- This app's public URL (`app_base_url`) — now in Presentation
- Environment label (`env_label`) — now in Presentation
- Log level (`log_level`) — now in Restart required; restart required
- Timing log threshold (`request_timing_log_ms`) — now in Reliability
- Database (`database_url`) — now in Foundations
- Encryption key (`app_encryption_key`) — now in Foundations
- Release tag (`release_tag`) — now in Foundations

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.3 | 11-18-26 01:39 | Claude (Claude Code) | Built as v0.345.0 (steps 2 complete); the appendix notes where the build differs from the draft list. |
| 0.2 | 11-18-26 01:02 | Claude (Claude Code) | § 6 rewritten as the eight rulings, all option A (Doug, 11-18-26). Q3 corrected: the four integrity switches were in Features, not Email. Q8's two-places behaviour written into § 6. |
| 0.1 | 11-18-26 00:25 | Claude (Claude Code) | First draft after Doug chose option A (sub-tabs, fixed order, word-by-word search). Draft assignment of all 286 settings; eight rulings asked. |
