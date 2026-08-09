"""What the System Settings page may show and change (plan §4, rulings 2–3).

Three things live here and nowhere else:

* **:data:`DENYLIST`** — keys that can never be overridden from the browser,
  enforced server-side rather than merely hidden in the UI. Every secret, the
  CRM target, the database, and the switches guarding this feature itself. The
  page must not be able to lock you out of the page that fixes it.
* **:data:`SETTINGS`** — the curated, editable settings, grouped. Ruling 3:
  these are the flags and knobs that actually get tuned; every other field on
  ``Settings`` is still *shown* (read-only) but not editable.
* **Boot-read settings are denylisted, not badged.** ``create_app`` decides
  router mounting and builds the middleware from the ENVIRONMENT, and the
  override layer only loads afterwards in the startup hook — so an override for
  one of those keys never takes effect, not even after a redeploy, because the
  redeploy re-runs mounting first. v0.190.1 shipped them as editable-with-a-
  "takes effect on next deploy" badge, which was simply wrong: toggling
  ``events_enabled`` here made the portal show an Event Administration tile
  whose routes did not exist. They now live on the denylist and are changed in
  the deployment overlay, which is the only thing that can change them.

``component`` records which process actually reads the setting — the worker owns
delivery, monitoring, Gmail sync, Drive reconciliation, transcripts and receipt
sweeps; web owns everything user-facing. It drives the readiness panel, and it
exists because "the flag is on but nothing happens" is usually this.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Kind = Literal["bool", "int", "text", "csv", "choice"]
Component = Literal["web", "worker", "both"]

# --- groups, in display order ----------------------------------------------
GROUP_FEATURES = "Features"
GROUP_INTEGRATIONS = "Integrations"
GROUP_EMAIL = "Email"
GROUP_RELIABILITY = "Reliability"
GROUP_GATES = "Team gates"
GROUP_PRESENTATION = "Presentation"

GROUP_ORDER = [
    GROUP_FEATURES,
    GROUP_INTEGRATIONS,
    GROUP_EMAIL,
    GROUP_RELIABILITY,
    GROUP_GATES,
    GROUP_PRESENTATION,
]

# Keys that may NEVER be overridden from the UI, whatever the request says.
# Enforced in core/settings_store.py, not just omitted from the page.
#
#   * secrets — never stored in app_setting, never rendered (plan §3);
#   * espo_base_url / espo_dry_run — which CRM this app writes to, and whether
#     it writes at all. A mistake here is unrecoverable from inside the app;
#   * database_url / session_secret / app_encryption_key — the app's own
#     foundations, read once at boot;
#   * setup_enabled / settings_overrides — the break-glass pair. If the page
#     could switch itself (or the whole override layer) off, recovery would
#     need a redeploy;
#   * BOOT_READ_KEYS — see below. An override for these is inert by
#     construction, so offering one would be a lie.
BOOT_READ_KEYS: frozenset[str] = frozenset({
    # Decide router mounting / static mounts / portal tiles in create_app.
    "analytics_enabled",
    "events_enabled",
    "events_public_api",
    "assignments_enabled",
    # Built into middleware at app construction.
    "intake_rate_limit",
    "intake_rate_window_seconds",
    "intake_max_body_mb",
    # Applied once by logging_setup at process start.
    "log_level",
})

DENYLIST: frozenset[str] = BOOT_READ_KEYS | frozenset({
    "espo_base_url",
    "espo_api_key",
    "espo_dry_run",
    "database_url",
    "session_secret",
    "app_encryption_key",
    "espo_provision_username",
    "espo_provision_password",
    "google_service_account_json",
    "anthropic_api_key",
    "zoom_account_id",
    "zoom_client_id",
    "zoom_client_secret",
    "fathom_api_key",
    "youtube_api_key",
    "allowed_origins",
    "session_cookie_secure",
    "setup_enabled",
    "settings_overrides",
    "setup_peer_url",
    "setup_peer_token",
})

# Settings whose VALUE must never be sent to the browser, even read-only. The
# page shows "set / not set" for these instead.
SECRET_KEYS: frozenset[str] = frozenset({
    "espo_api_key",
    "session_secret",
    "app_encryption_key",
    "espo_provision_password",
    "google_service_account_json",
    "anthropic_api_key",
    "zoom_client_secret",
    "fathom_api_key",
    "youtube_api_key",
    "setup_peer_token",
})


@dataclass(frozen=True)
class SettingSpec:
    key: str
    group: str
    label: str
    kind: Kind = "text"
    help: str = ""
    restart: bool = False
    component: Component = "web"
    choices: tuple[str, ...] = ()
    unit: str = ""


def _s(key: str, group: str, label: str, **kw) -> SettingSpec:
    return SettingSpec(key=key, group=group, label=label, **kw)


SETTINGS: tuple[SettingSpec, ...] = (
    # --- Features ----------------------------------------------------------
    _s("zoom_events", GROUP_FEATURES, "Zoom webinar provisioning", kind="bool",
       component="both",
       help="Public webinars only — mentor 1:1 sessions never use the CBM Zoom account."),
    _s("gmail_sync", GROUP_FEATURES, "Gmail conversation sync", kind="bool",
       component="both",
       help="The whole Communications pipeline. Needs the Google service account."),
    _s("gcal_events", GROUP_FEATURES, "Google Calendar events", kind="bool",
       help="Saving a Scheduled session reconciles an event on the manager's calendar."),
    _s("meet_transcripts", GROUP_FEATURES, "Meet transcripts", kind="bool",
       component="both",
       help="Do NOT switch on before the meetings.space.created DWD scope exists — "
            "every Scheduled save would show mentors a transcription failure."),
    _s("fathom_transcripts", GROUP_FEATURES, "Fathom transcripts", kind="bool",
       component="worker",
       help="Worker-only: Fathom auto-joins from the mentor's own calendar."),
    _s("gdrive_docs", GROUP_FEATURES, "Google Drive documents", kind="bool",
       component="both", help="The Documents tab. Needs a database and the shared drive."),
    _s("comms_ai_summary", GROUP_FEATURES, "AI conversation summaries", kind="bool",
       component="worker", help="Optional. Requires ANTHROPIC_API_KEY."),
    _s("comms_digest", GROUP_FEATURES, "Daily email digest", kind="bool",
       component="worker", help="Needs Gmail sync, the shared mailbox and the database."),
    _s("mentor_provision_users", GROUP_FEATURES, "Provision mentor logins", kind="bool",
       help="Creates an EspoCRM User on approval, via the admin service account."),
    _s("google_directory_check", GROUP_FEATURES, "Verify CBM mailbox exists", kind="bool",
       help="Blocks provisioning when a mailbox is confirmed missing. Fails open."),
    _s("google_create_mailbox", GROUP_FEATURES, "Create missing mailboxes", kind="bool",
       help="Needs the read-WRITE Directory scope."),
    _s("async_delivery", GROUP_FEATURES, "Asynchronous delivery", kind="bool",
       component="both",
       help="Capture returns immediately and the worker delivers with retries. "
            "Off = synchronous. Needs a database."),
    _s("gmail_resync", GROUP_FEATURES, "Gmail one-shot resync", kind="bool",
       component="worker",
       help="Clears every mailbox cursor on worker start so the next pass re-runs the "
            "backfill. Set it, let ONE pass complete, then turn it off — left on, every "
            "restart re-reads all mailboxes. A good candidate for a temporary override."),

    # --- Integrations ------------------------------------------------------
    _s("gdrive_identity", GROUP_INTEGRATIONS, "Drive identity", kind="choice",
       choices=("user", "service"), component="both",
       help="'service' is the operational mode — nobody is a shared-drive member."),
    _s("gdrive_shared_drive_id", GROUP_INTEGRATIONS, "Shared drive ID", component="both"),
    _s("gdrive_entity_labels", GROUP_INTEGRATIONS, "Drive folder labels", kind="csv",
       component="both", help="Entity=Label pairs, e.g. CEngagement=Clients."),
    _s("gdrive_doc_types", GROUP_INTEGRATIONS, "Document types", kind="csv"),
    _s("gdrive_max_file_mb", GROUP_INTEGRATIONS, "Max upload size", kind="int", unit="MB"),
    _s("gdrive_reconcile_seconds", GROUP_INTEGRATIONS, "Drive grant reconciliation",
       kind="int", unit="s", component="worker", help="0 disables the nightly job."),
    _s("google_delegated_admin", GROUP_INTEGRATIONS, "Delegated Workspace admin",
       component="both", help="Must be a real licensed mailbox — a group or alias 403s."),
    _s("zoom_host_email", GROUP_INTEGRATIONS, "Zoom host", component="both"),
    _s("zoom_base_url", GROUP_INTEGRATIONS, "Zoom API base URL", component="both"),
    _s("fathom_base_url", GROUP_INTEGRATIONS, "Fathom API base URL", component="worker"),
    _s("meet_transcripts_poll_seconds", GROUP_INTEGRATIONS, "Transcript retrieval",
       kind="int", unit="s", component="worker", help="Shared by the Meet and Fathom sources."),
    _s("transcript_give_up_days", GROUP_INTEGRATIONS, "Transcript give-up window",
       kind="int", unit="days", component="worker",
       help="Keep inside Google's 30-day transcript retention."),
    _s("summary_model", GROUP_INTEGRATIONS, "Summary model", component="worker"),
    _s("youtube_playlist_id", GROUP_INTEGRATIONS, "YouTube playlist"),

    # --- Email -------------------------------------------------------------
    _s("ops_mailbox", GROUP_EMAIL, "Shared mailbox", component="both",
       help="Submission Admin sends and reads as this. Must be a REAL mailbox, not a "
            "group. Only ONE environment may poll it — setting it on both double-captures."),
    _s("ops_mailbox_name", GROUP_EMAIL, "Shared mailbox display name", component="both"),
    _s("ops_reply_template", GROUP_EMAIL, "Canned reply template"),
    _s("ops_inbound_seconds", GROUP_EMAIL, "Inbound poll", kind="int", unit="s",
       component="worker", help="0 turns inbound capture off."),
    _s("ops_inbound_window_days", GROUP_EMAIL, "Inbound sweep window", kind="int",
       unit="days", component="worker"),
    _s("alert_email_to", GROUP_EMAIL, "Alert recipients", kind="csv", component="both"),
    _s("alert_email_from", GROUP_EMAIL, "Alert sender", component="both",
       help="Must be a real licensed mailbox; falls back to the shared mailbox."),
    _s("alert_webhook_url", GROUP_EMAIL, "Alert webhook", component="both"),
    _s("gmail_sync_seconds", GROUP_EMAIL, "Gmail sync cadence", kind="int", unit="s",
       component="worker"),
    _s("gmail_backfill", GROUP_EMAIL, "Initial sync window", component="worker"),
    _s("gmail_dead_letter_passes", GROUP_EMAIL, "Dead-letter after", kind="int",
       unit="passes", component="worker"),
    _s("comms_digest_hour", GROUP_EMAIL, "Digest hour", kind="int", component="worker"),
    _s("comms_digest_tz", GROUP_EMAIL, "Digest timezone", component="worker"),
    _s("comms_digest_seconds", GROUP_EMAIL, "Digest re-check", kind="int", unit="s",
       component="worker"),
    _s("comms_internal_domains", GROUP_EMAIL, "Internal domains", kind="csv",
       component="both", help="Mail between these domains links to Contacts, never records."),
    _s("comms_engagement_statuses", GROUP_EMAIL, "Active engagement statuses", kind="csv",
       component="both"),
    _s("comms_partner_excluded_statuses", GROUP_EMAIL, "Excluded partner statuses",
       kind="csv", component="both"),

    # --- Reliability -------------------------------------------------------
    _s("duplicate_hold_seconds", GROUP_RELIABILITY, "Near-duplicate hold", kind="int",
       unit="s", component="both", help="0 disables the hold entirely."),
    _s("worker_poll_seconds", GROUP_RELIABILITY, "Worker poll", kind="int", unit="s",
       component="worker"),
    _s("worker_batch_size", GROUP_RELIABILITY, "Worker batch size", kind="int",
       component="worker"),
    _s("worker_lease_seconds", GROUP_RELIABILITY, "Delivery lease", kind="int", unit="s",
       component="worker", help="How long a claimed row stays leased before reclaim."),
    _s("max_delivery_attempts", GROUP_RELIABILITY, "Max delivery attempts", kind="int",
       component="worker"),
    _s("alert_check_seconds", GROUP_RELIABILITY, "Alert evaluation", kind="int", unit="s",
       component="worker"),
    _s("alert_needs_attention_threshold", GROUP_RELIABILITY, "Needs-attention threshold",
       kind="int", component="worker"),
    _s("alert_pending_age_minutes", GROUP_RELIABILITY, "Oldest-pending threshold",
       kind="int", unit="min", component="worker"),
    _s("alert_cooldown_seconds", GROUP_RELIABILITY, "Alert cooldown", kind="int", unit="s",
       component="worker"),
    _s("schema_check_seconds", GROUP_RELIABILITY, "Schema-drift check", kind="int",
       unit="s", component="worker", help="0 disables."),
    _s("worker_liveness_check_seconds", GROUP_RELIABILITY, "Worker liveness watch",
       kind="int", unit="s", help="Runs on WEB — a dead worker can't alert on itself."),
    _s("worker_heartbeat_alert_seconds", GROUP_RELIABILITY, "Heartbeat staleness",
       kind="int", unit="s"),
    _s("receipt_reconcile_seconds", GROUP_RELIABILITY, "Receipt reconciliation",
       kind="int", unit="s", component="worker", help="0 disables the timer."),
    _s("assignment_reconcile_seconds", GROUP_RELIABILITY, "Assignment-stamp reconciliation",
       kind="int", unit="s", component="worker", help="0 disables."),
    _s("analytics_refresh_seconds", GROUP_RELIABILITY, "Analytics warm job", kind="int",
       unit="s", component="worker"),
    _s("analytics_default_cache_ttl_seconds", GROUP_RELIABILITY, "Analytics cache TTL",
       kind="int", unit="s"),
    _s("membership_refresh_seconds", GROUP_RELIABILITY, "Membership re-read", kind="int",
       unit="s", help="How long a session's cached team membership stays trusted."),
    _s("request_timeout_seconds", GROUP_RELIABILITY, "CRM request timeout", kind="int",
       unit="s", component="both"),

    # --- Team gates --------------------------------------------------------
    _s("assign_allowed_teams", GROUP_GATES, "Client Administration", kind="csv"),
    _s("assign_allowed_roles", GROUP_GATES, "Client Administration (roles)", kind="csv",
       help="A regular user's token cannot read its own roles — prefer teams."),
    _s("mentor_admin_allowed_teams", GROUP_GATES, "Mentor Administration", kind="csv"),
    _s("mentor_profile_allowed_teams", GROUP_GATES, "My Mentor Profile", kind="csv"),
    _s("ops_allowed_teams", GROUP_GATES, "Submission Admin", kind="csv"),
    _s("session_mentor_allowed_teams", GROUP_GATES, "Client Management", kind="csv"),
    _s("session_partner_allowed_teams", GROUP_GATES, "Partner Management", kind="csv"),
    _s("session_sponsor_allowed_teams", GROUP_GATES, "Funder Management", kind="csv"),
    _s("workspace_allowed_teams", GROUP_GATES, "Workspace Directories", kind="csv"),
    _s("events_allowed_teams", GROUP_GATES, "Event Administration", kind="csv"),
    _s("analytics_view_allowed_teams", GROUP_GATES, "Analytics — view", kind="csv"),
    _s("analytics_admin_allowed_teams", GROUP_GATES, "Analytics — author", kind="csv"),
    _s("mentor_team_name", GROUP_GATES, "Mentor team (provisioning)"),
    _s("partner_team_name", GROUP_GATES, "Partner team stamp",
       help="Stamped on new CPartnerProfiles. Empty disables the stamp."),
    _s("sponsor_team_name", GROUP_GATES, "Funder team stamp"),

    # --- Presentation ------------------------------------------------------
    _s("env_label", GROUP_PRESENTATION, "Environment label",
       help="Overrides the auto-derived Production/Test/Dev wording in the footer."),
    _s("docs_site_url", GROUP_PRESENTATION, "Documentation site"),
    _s("app_base_url", GROUP_PRESENTATION, "This app's public URL",
       help="Used for deep links in alert emails and the digest."),
    _s("events_public_base_url", GROUP_PRESENTATION, "Public event page base"),
    _s("events_cache_seconds", GROUP_PRESENTATION, "Public read cache", kind="int", unit="s"),
)

BY_KEY: dict[str, SettingSpec] = {s.key: s for s in SETTINGS}


def spec_for(key: str) -> Optional[SettingSpec]:
    return BY_KEY.get(key)


def is_editable(key: str) -> bool:
    """Editable = curated AND not on the denylist. Both conditions, always."""
    return key in BY_KEY and key not in DENYLIST


def is_secret(key: str) -> bool:
    return key in SECRET_KEYS


# Sanity: a curated setting that is also denylisted would render an editable
# control the server always refuses. Catch it at import rather than in the UI.
_conflict = sorted(set(BY_KEY) & DENYLIST)
if _conflict:  # pragma: no cover — a coding error, not a runtime condition
    raise RuntimeError(f"settings registry: curated but denylisted: {_conflict}")
