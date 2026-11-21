"""Where each setting sits on the Settings tab's sub-tabs.

Plan: ``prds/settings-page-areas-plan.md`` (rulings Q1 to Q8, Doug 11-18-26).
Shown while ``SETTINGS_AREAS`` is on; off, the page keeps its old groups.

The rule: **a setting lives where its screen is.** An outside service's own
account details (its *in use* switch, keys, account numbers, web addresses)
live in Connected services; how a feature behaves lives with the feature.

Each area is a list of headings. A heading may name its **main switch**, which
is shown first; every other setting under it follows A to Z by label. The
order of the keys written below does not matter — the page sorts them.

A new setting must be placed here, or ``tests/test_settings_areas.py`` fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

AREA_MARKETING = "Marketing Management"
AREA_EVENTS = "Events"
AREA_EVALUATION = "Business Evaluation"
AREA_STAFF = "Staff and mentor tools"
AREA_EMAIL = "Email"
AREA_DOCUMENTS = "Documents, calendar and meetings"
AREA_WEBSITE = "Website and branding"
AREA_GATES = "Team gates"
AREA_CONNECTED = "Connected services"
AREA_PLATFORM = "Platform"


@dataclass(frozen=True)
class Heading:
    title: str
    keys: tuple[str, ...]
    #: The heading's main on/off switch, shown first. One of ``keys``.
    lead: Optional[str] = None


@dataclass(frozen=True)
class Area:
    name: str
    headings: tuple[Heading, ...]


def _h(title: str, keys: str, lead: Optional[str] = None) -> Heading:
    return Heading(title=title, keys=tuple(keys.split()), lead=lead)


AREAS: tuple[Area, ...] = (
    Area(AREA_MARKETING, (
        _h("Marketing Management",
           "campaigns_enabled campaigns_landing_public campaigns_run_seconds campaigns_calls "
           "calls_panel campaigns_email campaign_send_report campaign_send_report_seconds",
           lead="campaigns_enabled"),
        _h("Campaign lists",
           "campaign_lists campaign_list_sync campaign_lists_only campaign_list_screens "
           "campaign_list_count_seconds campaign_list_fields",
           lead="campaign_lists"),
        _h("Leads and fit scores",
           "enrichment_free_pass enrichment_web_checks enrichment_sweep_seconds enrichment_batch "
           "chapter_counties fit_weights chapter_segments_url enrichment_terms_url lead_ladder "
           "lead_level_sweep_seconds prospect_stale_days prospect_stale_sweep_seconds lead_outreach "
           "import_templates import_plan_poll_seconds"),
        _h("AI research",
           "enrichment_ai enrichment_ai_model enrichment_monthly_budget enrichment_ai_max_searches "
           "enrichment_ai_record_cap enrichment_ai_max_records enrichment_ai_fallback "
           "enrichment_ai_poll_seconds",
           lead="enrichment_ai"),
        _h("Postcards", "postal_unit_cost postal_currency"),
        _h("Text messages", "campaigns_sms sms_from_number sms_send_hours sms_timezone",
           lead="campaigns_sms"),
        _h("Mailing list", "mailing_sync mailing_list_name mailing_push_seconds mailing_pull_seconds",
           lead="mailing_sync"),
    )),
    Area(AREA_EVENTS, (
        _h("Events", "events_enabled event_presenters event_promote events_confirmations",
           lead="events_enabled"),
        _h("Hosting",
           "zoom_events zoom_meetings_events events_default_method_public "
           "events_default_method_members events_other_platform events_attendance_seconds "
           "events_attendance_grace_minutes events_attendance_give_up_hours"),
        _h("Reminders", "events_reminders events_reminder_seconds events_reminder_lead_hours",
           lead="events_reminders"),
        _h("Public programme page",
           "events_public_api events_public_base_url events_cache_seconds events_hero_tagline "
           "events_hero_pillars events_hero_band events_default_graphic_url events_contact_email "
           "youtube_playlist_id",
           lead="events_public_api"),
        _h("Portal calendar", "portal_calendar portal_events_window_days", lead="portal_calendar"),
    )),
    Area(AREA_EVALUATION, (
        _h("Business Evaluation",
           "business_evaluation evaluation_link_days evaluation_retry_seconds "
           "evaluation_analysis_seconds evaluation_model evaluation_analyze_unassigned intake_survey "
           "mentor_match mentor_match_model feedback_surveys feedback_link_days "
           "feedback_retry_seconds feedback_quiet_days feedback_sweep_seconds "
           "feedback_lookback_days feedback_session_count feedback_on_close "
           "feedback_on_sessions feedback_on_event feedback_on_evaluation",
           lead="business_evaluation"),
    )),
    Area(AREA_STAFF, (
        _h("Staff and mentor tools",
           "assignments_enabled home_v2 home_no_contact_days chapter_news news_digest news_digest_weekday news_digest_hour ambassador_program ambassador_free_mail_domains ambassador_edit_days ambassador_delivery_seconds record_quick_add record_history_tab activity_page "
           "mentor_preview_shared grants_enabled",
           lead="assignments_enabled"),
        _h("Mentor logins",
           "mentor_provision_users google_directory_check google_create_mailbox "
           "manager_profile_strict cbm_email_lock login_repair_guards",
           lead="mentor_provision_users"),
        _h("Login integrity check",
           "login_integrity_check integrity_digest integrity_crm_use_report integrity_signin_alert "
           "integrity_digest_to login_integrity_hour login_integrity_tz integrity_shared_accounts "
           "integrity_excluded_logins integrity_app_addresses",
           lead="login_integrity_check"),
        _h("Analytics", "analytics_enabled analytics_refresh_seconds analytics_default_cache_ttl_seconds",
           lead="analytics_enabled"),
    )),
    Area(AREA_EMAIL, (
        _h("Email",
           "gmail_sync gmail_sync_seconds gmail_backfill gmail_dead_letter_passes gmail_resync "
           "comms_scope_rebuild_seconds comms_internal_domains mentor_email_domain "
           "comms_engagement_statuses comms_partner_excluded_statuses comms_attachment_excluded_types",
           lead="gmail_sync"),
        _h("Shared mailbox",
           "ops_mailbox ops_mailbox_name ops_reply_template ops_inbound_seconds ops_inbound_window_days"),
        _h("Summaries and digest",
           "comms_ai_summary summary_model comms_digest comms_digest_hour comms_digest_tz "
           "comms_digest_seconds"),
    )),
    Area(AREA_DOCUMENTS, (
        _h("Google Drive documents",
           "gdrive_docs gdrive_identity gdrive_shared_drive_id gdrive_entity_labels gdrive_doc_types "
           "gdrive_max_file_mb gdrive_reconcile_seconds",
           lead="gdrive_docs"),
        _h("Calendar", "gcal_events", lead="gcal_events"),
        _h("Transcripts",
           "meet_transcripts fathom_transcripts meet_transcripts_poll_seconds transcript_give_up_days"),
    )),
    Area(AREA_WEBSITE, (
        _h("Chapter identity",
           "organization_name organization_abbreviation chapter_key chapter_postal_address "
           "chapter_email chapter_phone chapter_ein chapter_payment_url chapter_social_links "
           "organization_logo_url organization_website_url docs_site_url"),
        _h("Policies",
           "policy_client_conduct_url policy_mentor_ethics_url policy_terms_url policy_privacy_url"),
        _h("Chapter website",
           "website_api website_origins form_framing newsletter_form organization_site_nav "
           "website_cache_seconds website_page_mentors website_page_events website_page_recordings "
           "website_page_partners website_page_sponsors website_page_stories",
           lead="website_api"),
        _h("Colours and fonts",
           "chapter_tokens_url website_color_base website_color_contrast website_color_accent_1 "
           "website_color_accent_2 website_color_accent_3 website_color_accent_4 "
           "website_color_accent_5 website_color_accent_6 website_font_heading website_font_body"),
    )),
    Area(AREA_GATES, (
        _h("Who can open each application",
           "assign_allowed_teams assign_allowed_roles mentor_admin_allowed_teams "
           "system_management_allowed_teams news_publish_allowed_teams ambassador_allowed_teams ambassador_review_teams mentor_profile_allowed_teams ops_allowed_teams "
           "session_mentor_allowed_teams session_partner_allowed_teams session_sponsor_allowed_teams "
           "workspace_allowed_teams events_allowed_teams campaigns_allowed_teams "
           "analytics_view_allowed_teams analytics_admin_allowed_teams"),
        _h("Team stamps", "mentor_team_name partner_team_name sponsor_team_name"),
    )),
    Area(AREA_CONNECTED, (
        _h("Connected services", "integrations_tab", lead="integrations_tab"),
        _h("Google Workspace",
           "google_workspace_in_use google_service_account_json google_delegated_admin "
           "google_members_group",
           lead="google_workspace_in_use"),
        _h("Zoom Meetings",
           "zoom_meetings_in_use zoom_meetings_account_id zoom_meetings_client_id "
           "zoom_meetings_client_secret zoom_event_host_email zoom_meetings_capacity",
           lead="zoom_meetings_in_use"),
        _h("Zoom Webinars",
           "zoom_in_use zoom_webinars_same_account zoom_host_email zoom_account_id zoom_client_id "
           "zoom_client_secret zoom_base_url",
           lead="zoom_in_use"),
        _h("Fathom", "fathom_in_use fathom_api_key fathom_base_url", lead="fathom_in_use"),
        _h("Constant Contact",
           "constant_contact_in_use mailing_client_id mailing_client_secret mailing_base_url",
           lead="constant_contact_in_use"),
        _h("Lob", "lob_in_use postal_provider postal_api_key postal_webhook_secret postal_test_mode",
           lead="lob_in_use"),
        _h("Twilio", "twilio_in_use sms_provider sms_account_sid sms_auth_token", lead="twilio_in_use"),
        _h("Anthropic",
           "anthropic_in_use anthropic_api_key integration_agent_model integration_agent_monthly_budget",
           lead="anthropic_in_use"),
        _h("YouTube", "youtube_in_use youtube_api_key", lead="youtube_in_use"),
    )),
    Area(AREA_PLATFORM, (
        _h("Submissions and delivery",
           "async_delivery duplicate_hold_seconds worker_poll_seconds worker_batch_size "
           "worker_lease_seconds max_delivery_attempts receipt_reconcile_seconds "
           "assignment_reconcile_seconds intake_rate_limit intake_rate_window_seconds "
           "intake_max_body_mb",
           lead="async_delivery"),
        _h("Alerts and checks",
           "alert_email_to alert_email_from alert_webhook_url alert_check_seconds "
           "alert_needs_attention_threshold alert_pending_age_minutes alert_cooldown_seconds "
           "integration_test_hour integration_test_tz schema_check_seconds "
           "worker_liveness_check_seconds worker_heartbeat_alert_seconds crm_config_refresh_seconds"),
        _h("CRM connection",
           "espo_base_url espo_api_key espo_dry_run espo_provision_username espo_provision_password "
           "request_timeout_seconds crm_metadata_cache_seconds"),
        _h("Access and security",
           "setup_enabled settings_overrides session_secret session_cookie_secure allowed_origins "
           "setup_peer_url setup_peer_token setup_refresh_seconds membership_refresh_seconds",
           lead="setup_enabled"),
        _h("Training sandbox",
           "sandbox_nightly_reset sandbox_reset_hour sandbox_reset_tz sandbox_address_domain",
           lead="sandbox_nightly_reset"),
        _h("This deployment",
           "settings_areas app_base_url env_label log_level request_timing_log_ms database_url "
           "app_encryption_key release_tag"),
    )),
)

AREA_ORDER: tuple[str, ...] = tuple(a.name for a in AREAS)

#: key -> (area, heading title)
PLACEMENT: dict[str, tuple[str, str]] = {
    key: (area.name, heading.title)
    for area in AREAS
    for heading in area.headings
    for key in heading.keys
}

#: (area, heading title) -> the heading's main switch, or None
LEADS: dict[tuple[str, str], Optional[str]] = {
    (area.name, heading.title): heading.lead
    for area in AREAS
    for heading in area.headings
}
