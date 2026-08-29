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
# Read once while the process starts, so a change waits for a restart. Grouped
# together rather than scattered, because the thing they share — "saving this
# does not take effect yet" — is the thing a reader most needs told.
GROUP_RESTART = "Restart required"
# Editable, but a wrong value breaks something important — so each is TRIED
# before it is stored and the system is checked afterwards (setup/verify.py).
GROUP_CONNECTION = "CRM connection"
GROUP_SECURITY = "Access & security"
# Visible, never editable here. Two of them are not dangerous but impossible.
GROUP_FOUNDATIONS = "Foundations"

GROUP_ORDER = [
    GROUP_FEATURES,
    GROUP_INTEGRATIONS,
    GROUP_EMAIL,
    GROUP_RELIABILITY,
    GROUP_GATES,
    GROUP_PRESENTATION,
    GROUP_RESTART,
    GROUP_CONNECTION,
    GROUP_SECURITY,
    GROUP_FOUNDATIONS,
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
#
# BOOT_READ_KEYS are NO LONGER denylisted. Doug ruled on 2026-08-28 that every
# setting belongs on the page — hiding one where it cannot be viewed or edited
# is not acceptable — and `core/boot_overrides.load_at_boot` now installs the
# override layer BEFORE create_app mounts anything, so "takes effect on
# restart" is true rather than a promise. They are curated into the
# "Restart required" group, which shows the value in force beside the one
# waiting for a restart.
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
    # The CRM configuration-stamp probe: its refresh task is created once in
    # the lifespan, so changing the interval later cannot start, stop or
    # re-time it. `release_tag` is baked into the image at build time and is
    # not a runtime value at all.
    "crm_config_refresh_seconds",
    "release_tag",
})

# --- what a change can cost, and what proves it safe ------------------------
#
# Doug's ruling, 2026-08-28: "All settings should be editable, unless a change
# would make the system unusable. Then there must be a verification that the
# system is still functional."
#
# So the denylist is now tiny and holds only the two changes that are not
# dangerous but IMPOSSIBLE (see below). Everything else that used to be hidden
# is editable through the verified path in `setup/verify.py`, which tries the
# value before storing it and checks the system afterwards.

# A change here could lock the admin out of this page. Neither a pre-flight
# probe nor a health check catches that: the app would be working perfectly and
# simply refusing to let anyone back in. These get a confirm-or-revert deadline
# instead — the change applies, and unless a human confirms the system still
# works it reverts itself. The network engineer's `commit confirmed`.
LOCKOUT_KEYS: frozenset[str] = frozenset({
    "setup_enabled",        # hides this page
    "settings_overrides",   # switches off the whole override layer
    "session_cookie_secure",  # `true` over plain http means nobody can sign in
    "allowed_origins",
    "session_secret",       # signs every session cookie: changing it signs you out
})

# A wrong value here breaks something important but cannot lock anyone out, so
# the pre-flight probe plus the post-apply check are the whole safety net.
VERIFIED_KEYS: frozenset[str] = frozenset({
    "espo_base_url",
    "espo_api_key",
    "espo_dry_run",
    "espo_provision_username",
    "espo_provision_password",
    "google_service_account_json",
    "anthropic_api_key",
    "zoom_account_id",
    "zoom_client_id",
    "zoom_client_secret",
    "fathom_api_key",
    "youtube_api_key",
    "setup_peer_url",
    "setup_peer_token",
    "sandbox_nightly_reset",
})

DENYLIST: frozenset[str] = frozenset({
    # Baked into the container image at build time. An override would survive a
    # restart and make the deployment MISREPORT which image it is running,
    # which defeats the only reason the stamp exists. Curated read-only instead
    # of hidden, per the 2026-08-28 ruling: visible, explained, not editable.
    "release_tag",
    # NOT caution — a logical impossibility. The override table lives INSIDE the
    # database this names, so an override moving the app to a different database
    # would live in the database being left behind: the new one has no such row,
    # the app reads its own configuration from there, and moves straight back.
    # There is no value of this setting that can change it.
    "database_url",
    # Rotating this makes every already-encrypted stored secret permanently
    # unreadable — the Google configuration and now the secrets on this page.
    # That is data loss rather than lockout, and no verification can undo it.
    # Rotation needs a re-encryption migration, not a text box.
    "app_encryption_key",
})

# Settings whose VALUE must never be sent to the browser, even read-only. The
# page shows "set / not set" for these instead.
SECRET_KEYS: frozenset[str] = frozenset({
    # A Postgres URL carries the password inside it, so rendering the value
    # hands any admin the database credential. It was in the read-only "show
    # all" list in the clear before 2026-08-28; curating it as a visible row
    # would have made that worse rather than better. Read-only AND masked.
    "database_url",
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
    # Shown on the page but never editable. For values the app cannot own — the
    # release tag comes from the image. Ruled 2026-08-28: visible beats hidden,
    # and "read-only, here is why" beats absent.
    readonly: bool = False
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
    _s("record_quick_add", GROUP_FEATURES, "Add partners & funders in-app", kind="bool",
       help="The '+ Add partner' / '+ Add funder' button on those grids. Creates the "
            "company, primary contact and profile as the signed-in user."),
    _s("grants_enabled", GROUP_FEATURES, "Grants on funder records", kind="bool",
       help="The Grants tab in Funder Management — awards, deliverables and (later) "
            "funder reporting. Stays hidden until the CRM has CGrant and "
            "CGrantDeliverable, so it is safe to switch on early."),
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
    _s("google_members_group", GROUP_INTEGRATIONS, "All Members group",
       help="Google Group a mentor's new mailbox joins when their account is created. "
            "Blank skips the group step. Needs the Directory group scope."),
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
    _s("comms_attachment_excluded_types", GROUP_EMAIL, "Never file these attachments",
       kind="csv", component="both",
       help="MIME types (text/calendar) or filenames/extensions (.ics, winmail.dat) "
            "that inbound mail never files to a record's Documents tab. The bytes "
            "stay in the message — View original still shows them."),

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
    _s("organization_name", GROUP_PRESENTATION, "Organisation name", component="both",
       help="The name every page carries — title, footer and the public forms' prose. "
            "Substituted server-side as it is served, so a change here takes effect on "
            "the next page load with no redeploy."),
    _s("policy_client_conduct_url", GROUP_PRESENTATION, "Client code of conduct URL",
       help="Linked from the consent checkbox on the public forms."),
    _s("policy_mentor_ethics_url", GROUP_PRESENTATION, "Mentor code of ethics URL",
       help="The volunteer form's Code of Conduct link — a different document."),
    _s("policy_terms_url", GROUP_PRESENTATION, "Terms of use URL"),
    _s("policy_privacy_url", GROUP_PRESENTATION, "Privacy policy URL"),
    _s("chapter_tokens_url", GROUP_PRESENTATION, "Chapter design-token override",
       help="URL of a stylesheet redefining --cbm-* custom properties on :root. "
            "Loaded after the base tokens; custom properties only, never selectors."),
    _s("env_label", GROUP_PRESENTATION, "Environment label",
       help="Overrides the auto-derived Production/Test/Dev wording in the footer."),
    _s("docs_site_url", GROUP_PRESENTATION, "Documentation site"),
    _s("app_base_url", GROUP_PRESENTATION, "This app's public URL",
       help="Used for deep links in alert emails and the digest."),
    _s("events_public_base_url", GROUP_PRESENTATION, "Public event page base"),
    _s("events_cache_seconds", GROUP_PRESENTATION, "Public read cache", kind="int", unit="s"),

    # Integration credentials. A wrong one disables that integration and nothing
    # else, so the pre-flight check is the whole safety net. None is ever shown
    # back once set.
    _s("google_service_account_json", GROUP_INTEGRATIONS, "Google service account",
       component="both",
       help="The key behind Gmail, Calendar, Drive and Directory. Checked for shape "
            "before it is stored; whether domain-wide delegation has been granted "
            "cannot be seen from here."),
    _s("anthropic_api_key", GROUP_INTEGRATIONS, "Anthropic API key", component="worker",
       help="AI conversation summaries only."),
    _s("zoom_account_id", GROUP_INTEGRATIONS, "Zoom account ID", component="both"),
    _s("zoom_client_id", GROUP_INTEGRATIONS, "Zoom client ID", component="both"),
    _s("zoom_client_secret", GROUP_INTEGRATIONS, "Zoom client secret", component="both",
       help="Public webinars only. Mentor sessions never use the CBM Zoom account."),
    _s("fathom_api_key", GROUP_INTEGRATIONS, "Fathom API key", component="worker"),
    _s("youtube_api_key", GROUP_INTEGRATIONS, "YouTube API key",
       help="The recorded-webinar library."),

    # --- Restart required --------------------------------------------------
    # Every one of these is read while the process starts — routers are mounted,
    # middleware is built and logging is configured before the app serves its
    # first request. Saving one here stores it; the running process keeps the
    # value it booted with until it restarts, and the page shows both.
    _s("analytics_enabled", GROUP_RESTART, "Analytics", kind="bool", restart=True,
       component="both",
       help="Mounts the /analytics routes and its portal tile. The routes do not "
            "exist until the process restarts, so switching this on mid-run would "
            "otherwise produce a tile leading nowhere."),
    _s("events_enabled", GROUP_RESTART, "Events & Webinars", kind="bool", restart=True,
       component="both",
       help="Mounts the /events routes and its portal tile."),
    _s("events_public_api", GROUP_RESTART, "Public events API", kind="bool", restart=True,
       help="The unauthenticated read API the website's programme reads. "
            "Publishing is still gated per event."),
    _s("assignments_enabled", GROUP_RESTART, "Staff applications", kind="bool",
       restart=True, component="both",
       help="The whole staff stack — portal, Client Administration and the rest. "
            "Turning this off leaves only the public intake forms."),
    _s("log_level", GROUP_RESTART, "Log level", kind="choice", restart=True,
       component="both", choices=("DEBUG", "INFO", "WARNING", "ERROR"),
       help="Applied once by logging setup as the process starts."),
    _s("intake_rate_limit", GROUP_RESTART, "Intake rate limit", kind="int",
       restart=True, unit="requests",
       help="Built into the middleware at startup. Submissions allowed per window "
            "from one address."),
    _s("intake_rate_window_seconds", GROUP_RESTART, "Intake rate window", kind="int",
       restart=True, unit="s", help="The window the limit above is counted over."),
    _s("intake_max_body_mb", GROUP_RESTART, "Maximum submission size", kind="int",
       restart=True, unit="MB",
       help="Built into the middleware at startup. Chiefly the volunteer form's "
            "optional resume."),
    _s("crm_config_refresh_seconds", GROUP_RESTART, "CRM configuration check",
       kind="int", restart=True, unit="s",
       help="How often to re-read the CRM's configuration version for the status "
            "page. 0 switches it off. The background task is created once at "
            "startup, so starting or stopping it needs a restart. /healthz always "
            "serves the cached answer and never waits on the CRM."),
    # --- CRM connection ----------------------------------------------------
    # Each of these is tried against the live CRM before it is stored: a key
    # the CRM rejects, or an address that is not a CRM this application can
    # use, is refused with the CRM's own error rather than accepted and left to
    # fail on every later call.
    _s("espo_base_url", GROUP_CONNECTION, "CRM address",
       help="Which EspoCRM this deployment reads and writes. Checked before it is "
            "saved: the address must answer AND hold this application's entities, so "
            "pointing at a stranger's EspoCRM is refused rather than accepted."),
    _s("espo_api_key", GROUP_CONNECTION, "CRM API key",
       help="The org-wide key. Tried against the CRM before it is stored; a key the "
            "CRM rejects is refused. Never shown back once set."),
    _s("espo_dry_run", GROUP_CONNECTION, "Dry run (no CRM writes)", kind="bool",
       component="both",
       help="On, nothing is ever written to the CRM and submissions are logged only. "
            "This is how the dev deployment runs."),
    _s("espo_provision_username", GROUP_CONNECTION, "Provisioning admin username",
       help="The admin service account used for the few operations EspoCRM reserves "
            "for admins — creating mentor logins, team membership."),
    _s("espo_provision_password", GROUP_CONNECTION, "Provisioning admin password",
       help="Never shown back once set."),

    # --- Access & security -------------------------------------------------
    # Everything here can lock somebody out, which no probe can detect — the app
    # would be working perfectly and simply refusing to let anyone in. They
    # apply with a countdown and revert themselves unless confirmed.
    _s("session_secret", GROUP_SECURITY, "Session signing secret",
       help="Signs every session cookie. Changing it signs EVERYONE out, including "
            "you — so confirm you can still sign in, or it reverts itself."),
    _s("session_cookie_secure", GROUP_SECURITY, "HTTPS-only session cookie",
       kind="bool",
       help="On is correct for any real deployment. On over plain http, no one can "
            "sign in at all — hence the countdown."),
    _s("allowed_origins", GROUP_SECURITY, "Allowed origins", kind="csv",
       help="Only matters if a separate frontend origin is ever introduced; the "
            "wizard posts to its own origin."),
    _s("setup_enabled", GROUP_SECURITY, "This Settings page", kind="bool",
       help="Switching this off hides the page you are reading. It reverts itself "
            "unless confirmed, because otherwise recovery would need a redeploy."),
    _s("settings_overrides", GROUP_SECURITY, "Settings overrides", kind="bool",
       component="both",
       help="The break-glass. Off, every stored setting stops applying and the "
            "deployment's own values take over — including the one that switched "
            "this off, so it could never switch itself back on. Reverts unless "
            "confirmed."),
    _s("setup_peer_url", GROUP_SECURITY, "Peer deployment URL",
       help="The other environment, for the comparison on the Environment diff tab."),
    _s("setup_peer_token", GROUP_SECURITY, "Peer deployment token",
       help="Authorises that comparison. No secret value ever crosses the wire."),
    _s("sandbox_nightly_reset", GROUP_SECURITY, "Nightly sandbox wipe", kind="bool",
       component="worker",
       help="Worker-side. Empties this deployment's own submission queue and "
            "document index every night. Correct on the training sandbox, ruinous "
            "anywhere else — which is why it is checked before it is stored."),

    # --- Foundations -------------------------------------------------------
    _s("database_url", GROUP_FOUNDATIONS, "Database", readonly=True,
       help="Cannot be changed here, and this is a logical impossibility rather "
            "than caution: the stored settings live INSIDE this database, so a "
            "setting that moved the app elsewhere would be left behind in the "
            "database being abandoned, and the app would read its configuration "
            "from the new one and move straight back. Change it in the deployment "
            "configuration."),
    _s("app_encryption_key", GROUP_FOUNDATIONS, "Encryption key", readonly=True,
       help="Protects the secrets stored on this page and the Google configuration. "
            "Rotating it makes every one of them permanently unreadable — data "
            "loss, which no verification can undo. Rotation needs a re-encryption "
            "migration, not a text box."),

    # In Foundations, NOT "Restart required", although it is read once at
    # startup. That group means "change it here and it takes effect on the next
    # restart", and this cannot be changed here at all — a restart will never
    # alter it, only rebuilding the image will. Sitting among nine editable
    # settings implied otherwise, which is exactly the confusion the group was
    # created to remove.
    _s("release_tag", GROUP_FOUNDATIONS, "Release tag", readonly=True,
       help="Which release this container was built from — stamped into the image "
            "at build time and supplied by the deployment's own configuration. "
            "Read-only on purpose: a stored value would survive a restart and make "
            "this deployment misreport which build it is running. Empty means an "
            "untagged build."),
)

BY_KEY: dict[str, SettingSpec] = {s.key: s for s in SETTINGS}


def spec_for(key: str) -> Optional[SettingSpec]:
    return BY_KEY.get(key)


def is_editable(key: str) -> bool:
    """Editable = curated AND not on the denylist. Both conditions, always."""
    return key in BY_KEY and key not in DENYLIST


def is_secret(key: str) -> bool:
    return key in SECRET_KEYS


def is_readonly(key: str) -> bool:
    spec = BY_KEY.get(key)
    return bool(spec and spec.readonly) or key in DENYLIST


# Sanity: a curated setting that is also denylisted would render an editable
# control the server always refuses. A spec marked `readonly` is the exception —
# it is curated precisely so the value is VISIBLE and explained rather than
# hidden, and it renders no control at all.
_conflict = sorted(
    k for k in (set(BY_KEY) & DENYLIST) if not BY_KEY[k].readonly
)
if _conflict:  # pragma: no cover — a coding error, not a runtime condition
    raise RuntimeError(f"settings registry: curated but denylisted: {_conflict}")
