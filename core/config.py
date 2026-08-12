"""Application configuration, loaded from environment / .env."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    espo_base_url: str = "https://crm.example.org"
    espo_api_key: str = ""
    espo_dry_run: bool = True
    allowed_origins: str = "http://localhost:8000"
    request_timeout_seconds: int = 20

    # --- public intake POST limits (Phase 6, decision D3: 2 MB / 30 per
    # 10 min). The volunteer form keeps a larger body cap sized for its
    # base64 resume (see core/app.py); photo/document uploads are separate
    # endpoints with their own caps. rate limit 0 = disabled.
    intake_max_body_mb: int = 2
    intake_rate_limit: int = 30
    intake_rate_window_seconds: int = 600

    # Environment label shown as a corner badge on every form (via /healthz ->
    # shared/footer.js). Empty => auto-derived from the CRM target below
    # ("production" / "test" / "dev"); set explicitly to override the wording.
    env_label: str = ""

    # The CBM documentation site (BookStack), linked from the portal home page
    # so signed-in users can find the app user guides. Empty hides the link.
    docs_site_url: str = "https://docs.clevelandbusinessmentors.org"
    # This app's own public base URL (no trailing slash) — used to build
    # absolute record deep links in the daily email digest (§4.2.4). Empty =>
    # the digest lists records without hyperlinks (still useful). Prod:
    # https://apps.clevelandbusinessmentors.org
    app_base_url: str = ""

    # Logging level for both processes (web + worker) — e.g. "DEBUG" exposes
    # the comms triage decisions without a redeploy. See core/logging_setup.py.
    log_level: str = "INFO"

    # How long the staff session's cached team/role membership stays trusted
    # before the gates re-read it from the CRM (P1-12: a staffer removed from a
    # team — or whose token was revoked — loses app access within this window
    # even if they bookmark an app and never revisit the portal). Seconds.
    membership_refresh_seconds: int = 900

    # --- V2 Phase 0: durable submission store (prds/v2) ---
    # When set, every submission is captured to Postgres before any CRM work and
    # idempotency is enforced durably. Empty => the app keeps its V1 in-memory
    # behavior (no store), so this is a safe no-op until a database is attached.
    database_url: str = ""

    # --- V2 Phase 1: asynchronous delivery (worker) ---
    # When true (and a store is configured), the accept endpoint returns as soon
    # as the submission is captured and the background worker delivers it into the
    # CRM with retries. False => Phase 0 (synchronous) behavior.
    async_delivery: bool = False
    worker_poll_seconds: int = 5
    worker_batch_size: int = 10
    max_delivery_attempts: int = 8
    # How long a claimed ("processing") row stays leased to a worker. If the
    # worker dies mid-delivery (redeploy, OOM, SIGKILL), the row is reclaimable
    # once this lease expires — without it, a crash strands the row in
    # "processing" forever. Generous, because delivery is resumable: a rare
    # double-claim re-runs the same chain and skips already-created records.
    worker_lease_seconds: int = 900

    # --- Near-duplicate hold (2026-07-27) ---
    # A second submission of the SAME form from the SAME email within this window
    # is captured but NOT delivered: it is held for staff review in Submission
    # Admin, where Approve delivers it and Discard drops it. Prevents the
    # duplicate CClientProfile/CEngagement pairs that a client re-filling the
    # form produces (both observed cases were ~2 minutes apart; the window is
    # deliberately wider to also catch same-day second thoughts).
    # 0 disables the check entirely — every submission delivers as before.
    duplicate_hold_seconds: int = 86400

    # --- V2 Phase 3: monitoring + alerting (run as periodic worker tasks) ---
    # Where to send alerts (a Slack-compatible {"text": ...} webhook). Empty =>
    # webhook delivery is off.
    alert_webhook_url: str = ""
    # EMAIL alert delivery (2026-07-20 — CBM uses no messaging service): every
    # alert is emailed via the existing Gmail service-account delegation, sent
    # AS `alert_email_from` (must be a real @cbmentors.org Workspace mailbox;
    # falls back to OPS_MAILBOX when empty) TO `alert_email_to` (comma list —
    # any addresses, personal Gmail included). Both delivery channels can be
    # on at once; with NEITHER configured (or all deliveries failing), alerts
    # log at WARNING as before. Set on the WORKER component (alerts originate
    # there).
    alert_email_to: str = ""
    alert_email_from: str = ""
    # Nightly assignment-stamp reconciliation (layer 3 of the stamp-drift
    # prevention plan, 2026-07-20): the worker re-derives each assigned
    # engagement's entitled users from the CRM's own links (mentorProfile +
    # additionalMentors) and MERGES missing users onto the engagement /
    # contacts / client profile / company assignedUsers — merge-only, never
    # removes. Makes the Anthony-Sacco drift class self-healing regardless of
    # how the drift happened (pre-stamp-era records, the collaborators
    # switch, hand edits in the CRM UI). 0 disables.
    assignment_reconcile_seconds: int = 86400
    alert_check_seconds: int = 300          # how often the worker evaluates thresholds
    # WEB-side worker-liveness watch (2026-07-23): the web process checks the
    # worker's heartbeat row and alerts (email/webhook, same channels) when it
    # goes stale — a dead worker can't alert on itself. Runs only with a
    # durable store AND async delivery. 0 disables. Set ALERT_EMAIL_TO/FROM on
    # the WEB component too for email delivery of these.
    worker_liveness_check_seconds: int = 120
    worker_heartbeat_alert_seconds: int = 180
    alert_needs_attention_threshold: int = 1  # alert when this many are stuck
    alert_pending_age_minutes: int = 30     # alert when the oldest pending is older
    alert_cooldown_seconds: int = 3600      # minimum gap between repeats of an alert
    schema_check_seconds: int = 3600        # CRM schema-drift cadence (0 disables)

    # --- Mentor assignment tool (/assignments) ---
    # Staff-only dashboard; authenticates each user against EspoCRM and acts as
    # them. Disabled if no session secret is set (see ``assignments_active``).
    assignments_enabled: bool = True
    session_secret: str = ""
    # Comma-separated EspoCRM Team names / Role names allowed to use the tool.
    # A user passes if they are an admin, belong to an allowed Team, OR hold an
    # allowed Role. Both empty => admins only. Defaults to the real team name
    # (same convention as every other gate below) so a deploy that doesn't set
    # ASSIGN_ALLOWED_TEAMS doesn't silently hide the tool from team members.
    assign_allowed_teams: str = "Client Administration Team"
    assign_allowed_roles: str = ""
    # Mentor Admin app (/mentoradmin) — gated to its own team.
    mentor_admin_allowed_teams: str = "Mentor Administration Team"
    # Submission Admin app (/ops) — gated to its own team (v0.30.0; it
    # previously shared the assignments gate). The team must exist in the CRM.
    ops_allowed_teams: str = "Marketing Admin Team"
    # EspoCRM email template pre-applied when Submission Admin starts a NEW
    # conversation on an info-request (the canned reply; the compose opens
    # blank if no template with this name exists — silent fallback).
    ops_reply_template: str = "InfoRequestReply"
    # The SHARED mailbox Submission Admin speaks as (Doug's ruling 2026-07-19:
    # the public information channel is info@cbmentors.org, not any staffer's
    # personal CBM address). When set (and GMAIL_SYNC is on):
    #   * ops replies SEND as this mailbox (generic display name below),
    #   * the submission conversation READS this mailbox's threads — every
    #     admin sees the same conversation (the per-admin-visibility caveat of
    #     v0.106.0 goes away), and only the threads anchored to the submission
    #     (no more from:X OR to:X address search picking up unrelated mail),
    #   * the worker polls its inbox and captures each NEW inbound thread as a
    #     held info-email submission in the /ops work queue (triage-first —
    #     no CRM records until staff approve; Discard leaves no CRM residue).
    # Must be a REAL Workspace mailbox (not a group/alias) — Gmail delegation
    # only works against a licensed user mailbox. Empty = the pre-v0.110.0
    # behavior (per-admin mailbox + address search, no inbound capture).
    ops_mailbox: str = ""
    ops_mailbox_name: str = "Cleveland Business Mentors"  # From display name on shared sends
    ops_inbound_seconds: int = 300          # inbound info@ poll cadence (0 = off)
    # How far back the inbound poll sweeps each cycle (Gmail `newer_than:Nd`).
    # The poll paginates the WHOLE window (not just the newest 100) so a burst
    # can't scroll a new request past the page; dedup skips already-tracked
    # threads. 2 days is ~576× the 5-min cadence — ample margin for worker
    # downtime, while bounding the repeated listing.
    ops_inbound_window_days: int = 2
    # Intake-receipt reconciliation (the CRM-as-source-of-truth sweep, Doug's
    # 2026-07-27 redesign): every app-store submission row is compared against
    # its CIntakeSubmission receipt in the CRM — missing receipts created,
    # stale ones updated. 0 disables the timer (the manual /ops trigger and
    # the per-action writes still work).
    receipt_reconcile_seconds: int = 3600
    # Session Management tools — one engine, three team-gated routes
    # (/mentorsessions, /partnersessions, /sponsorsessions). Each lets its users
    # record CSession meetings against the records they own.
    session_mentor_allowed_teams: str = "Mentor Team"
    session_partner_allowed_teams: str = "Partner Management Team"
    session_sponsor_allowed_teams: str = "Sponsor Management Team"
    # My Mentor Profile (/mentorprofile) — a mentor edits their OWN profile +
    # Contact, with a live website preview. Gated to the Mentor Team.
    mentor_profile_allowed_teams: str = "Mentor Team"
    # Workspace directories (/directory/{companies,contacts,mentors}) — the
    # CRM-style browsable grids launched from the portal. Gated to this team;
    # the real data scope is each user's EspoCRM ACL (reads run as them), so
    # this is only "who sees the workspace at all". Mentor Team by default.
    workspace_allowed_teams: str = "Mentor Team"
    # Team that approved mentors' new login users are placed in.
    mentor_team_name: str = "Mentor Team"
    # Quick add (Doug's request 2026-08-12): the "+ Add partner" / "+ Add
    # funder" button on the Partner and Funder Management grids, which runs the
    # same Account → Contact → profile create the public intake forms do, as
    # the signed-in user. Off by default — build dark, review on crm-test, then
    # enable on prod. Read per request (never at boot), so /setup can toggle it.
    record_quick_add: bool = False
    # Team stamped onto every NEW CPartnerProfile the partner intake form
    # creates, so team-scoped roles (Partner Management Team members) can see
    # all partners in /partnersessions — also stamped by the quick add above.
    # Best-effort: an unresolvable team (e.g. the API role lacks Team read) logs
    # a WARNING and the partner is created without it. Empty disables the stamp.
    partner_team_name: str = "Partner Management Team"
    # Same stamp for every NEW CSponsorProfile the sponsor intake form creates
    # (all funders are visible to every sponsor-team member — /sponsorsessions
    # lists ALL sponsors the user's ACL can read). Empty string disables.
    sponsor_team_name: str = "Sponsor Management Team"
    # Auto-provision a login User when a mentor is Approved. Off by default.
    # User creation is admin-only in EspoCRM (API keys can't do it), so this runs
    # as a dedicated admin service account via the App/user token flow — NEVER
    # the staff user's token. Mentor Admin staff stay non-admin.
    mentor_provision_users: bool = False
    # Credentials of that dedicated admin account (used only for provisioning).
    espo_provision_username: str = ""
    espo_provision_password: str = ""
    # Marks a session cookie Secure; set false only for plain-HTTP local dev.
    session_cookie_secure: bool = True

    # --- Google Workspace mailbox check (hard-gates mentor provisioning) ---
    # When on (and creds set), provisioning first verifies the mentor's CBM
    # mailbox actually exists in Google Workspace before creating the EspoCRM
    # login + welcome email — otherwise the credentials email bounces and the
    # mentor is stranded. A *confirmed-missing* mailbox blocks provisioning; an
    # inconclusive check (not configured, API/auth error) fails OPEN so a Google
    # outage can never freeze all approvals. Needs a Google Cloud service account
    # with domain-wide delegation for the read-only Directory scope, impersonating
    # a Workspace admin. Off (a no-op) until both values below are set.
    google_directory_check: bool = False
    google_service_account_json: str = ""   # the service-account JSON key (secret)
    google_delegated_admin: str = ""        # a Workspace admin to impersonate
    # When on (and the service account has the read-WRITE Directory scope), a
    # confirmed-missing CBM mailbox is CREATED in Google Workspace during mentor
    # approval instead of blocking — then the EspoCRM login is provisioned once
    # the new mailbox verifies. Off => the missing-mailbox check only blocks
    # (the pre-existing behavior). Can also be set via the in-app Email Setup
    # screen (DB config takes precedence over these env vars).
    google_create_mailbox: bool = False

    # --- Communications: Gmail conversation integration (prds/communications-
    # gmail-integration.md). Master flag; the whole pipeline (sync, endpoints,
    # send) is a no-op until enabled. Needs the Google service account (above /
    # Email Setup) with gmail.readonly + gmail.send authorized for delegation.
    gmail_sync: bool = False
    gmail_sync_seconds: int = 300           # worker sync cadence
    # One-shot ops lever: on worker start, clear every mailbox's sync cursor so
    # the next pass re-runs the initial backfill (Message-ID dedup makes that
    # idempotent — already-stored mail is skipped). Set true, deploy, let one
    # pass complete, then unset. Used to re-drive messages a bug dropped.
    gmail_resync: bool = False
    gmail_backfill: str = "newer_than:365d"  # initial-sync history window
    # P1-5: a message failing ingest holds the cursor back (nothing skipped);
    # after this many CONSECUTIVE failing passes it is dead-lettered (skipped,
    # logged, visible in /ops metrics) so one poison message can't wedge the
    # mailbox forever. Doug's decision D6 (2026-07-18): 5.
    gmail_dead_letter_passes: int = 5
    # Statuses that make a record "active" (mail is only ingested for active
    # records). Comma-separated; engagement set matches the sessions tools.
    comms_engagement_statuses: str = "Active,Assigned,Pending Acceptance,On-Hold"
    comms_partner_excluded_statuses: str = "Ended,Declined"
    # Internal email domains (comma-separated). The background sync exists to
    # capture mentor↔client correspondence — addresses at these domains are
    # dropped from the sweep's match scope, and a message whose every
    # participant is internal is never auto-stored (Doug's ruling 2026-07-21:
    # cbmentor-to-cbmentor internal mail is useless in the CRM). Explicit user
    # actions (record-page compose, "Add emails" thread include) are exempt.
    comms_internal_domains: str = "cbmentors.org"
    # OPTIONAL AI layer: per-conversation Claude summaries/status/action items.
    # Off by default — with it off, nothing leaves Google/the CRM and no
    # Anthropic key is needed. Requires ANTHROPIC_API_KEY when on.
    comms_ai_summary: bool = False
    anthropic_api_key: str = ""
    summary_model: str = "claude-opus-4-8"
    # Daily email digest (email-quality plan §4.2.4): a once-a-day worker job
    # that emails each manager a summary of their records with unread /
    # awaiting-reply conversations, each a deep link to the record page. Sent
    # from the shared identity (ops_mailbox / ops_mailbox_name) to the
    # manager's cbmEmail; nothing pending => no email (no empty digests).
    # Off by default; needs GMAIL_SYNC + OPS_MAILBOX (the send identity) + the
    # database (unread state). Anchored to comms_digest_hour in
    # comms_digest_tz so it lands each morning, not at a worker-restart offset.
    comms_digest: bool = False
    comms_digest_seconds: int = 86400       # re-check cadence (the hour gate does the timing)
    comms_digest_hour: int = 7              # local hour to send (0–23)
    comms_digest_tz: str = "America/New_York"

    # --- Google Calendar events for sessions (sessions/gcal.py). When on, saving
    # a Scheduled session in the session tools creates/updates a Google Calendar
    # event on the manager's OWN calendar (delegated as their cbmEmail), with a
    # Google Meet link written back to CSession.videoMeetingLink and the
    # attendees invited (Google emails the invitations). Also needs: the shared
    # service account (above / Email Setup) with the calendar.events scope
    # authorized for delegation, AND the CSession.googleCalendarEventId CRM field
    # (csession-calendar-field.md) — the hook feature-detects the field and stays
    # inert until it exists. Off => the hook is a silent no-op.
    gcal_events: bool = False

    # --- Meeting transcripts: Google Meet (prds/meet-transcript-integration.md).
    # When on, every Meet the calendar hook schedules gets auto-transcription
    # enabled on its Meet space (web), and the worker periodically retrieves
    # finished transcripts into CSession.sessionTranscription + transcriptDocUrl
    # (both CRM fields feature-detected — csession-transcript-fields.md). Needs
    # the shared service account with the meetings.space.created scope authorized
    # for delegation, the Meet API enabled in GCP, and Workspace licensing that
    # includes Meet transcripts (Business Standard+) for the session-hosting
    # users. Off => both hooks are silent no-ops.
    meet_transcripts: bool = False
    meet_transcripts_poll_seconds: int = 1800   # worker retrieval cadence
    # How many days after a session's start the worker keeps looking for a
    # transcript before giving up (a meeting never held / transcription off).
    # Keep comfortably inside Google's 30-day transcript-entries retention.
    transcript_give_up_days: int = 14

    # --- Meeting transcripts: Fathom note taker
    # (prds/fathom-transcript-integration.md). When on (worker only — there is
    # no schedule-time Fathom hook; Fathom auto-joins from the mentor's own
    # calendar), the retrieval cycle tries Fathom FIRST for every past session
    # with a meeting link on any platform Fathom records (Meet/Zoom/Teams),
    # falling back to the Meet-native source when both are enabled. Auth is ONE
    # team API key — Fathom keys are user-level and read meetings recorded by
    # that account or shared to its Team, so CBM's team-sharing setup is the
    # coverage prerequisite. Shares MEET_TRANSCRIPTS_POLL_SECONDS and
    # TRANSCRIPT_GIVE_UP_DAYS with the Meet path. Off => the source isn't built.
    fathom_transcripts: bool = False
    fathom_api_key: str = ""  # SECRET (worker component)
    fathom_base_url: str = "https://api.fathom.ai/external/v1"

    # --- Documents: Google Drive document management (DOC-MGMT Phase 1). When
    # on (and a database is attached), the session tools' Documents tab lets a
    # manager upload files to the "CBM Documents" shared drive and lists each
    # record's documents from the app_document metadata table. Drive access
    # impersonates the signed-in user's own cbmEmail via the shared service
    # account (above / Email Setup) — the https://www.googleapis.com/auth/drive
    # scope must be authorized for its domain-wide delegation. Off => the tab
    # stays a "coming soon" placeholder and the endpoints 503.
    gdrive_docs: bool = False
    # The shared drive ("CBM Documents") all managed documents live in.
    gdrive_shared_drive_id: str = ""
    # Whose Drive identity performs document operations:
    #   "user"    — impersonate the signed-in manager's own cbmEmail (PRD
    #               D-01; requires EVERY manager to be a shared-drive member).
    #   "service" — the service account acts as ITSELF (add the SA's
    #               client_email as a shared-drive member, Content Manager).
    #               Managers need NO Drive access at all — the app's CRM ACL
    #               check is the sole gate, and the app-level uploaded_by
    #               still records the real person.
    # Doug's ruling 2026-07-16: users are NOT drive members, so "service" is
    # the operational mode; "user" remains for compatibility. Literal so a
    # typo ("Service", "sa") fails the boot loudly instead of silently
    # meaning "user" (Phase 6, reliability review 2026-07-17).
    gdrive_identity: Literal["user", "service"] = "user"
    # Top-level Drive folders are DISPLAY LABELS mapped from anchor entity
    # types (PRD v1.2 §3.2 rule 3), not raw entity names: Mentors/, Clients/…
    # An unmapped entity type falls back to the raw name.
    gdrive_entity_labels: str = (
        "Contact=Mentors,CEngagement=Clients,"
        "CPartnerProfile=Partners,CSponsorProfile=Sponsors"
    )
    # The doc_type choices offered at upload time (comma-separated).
    gdrive_doc_types: str = "Resume,Agreement,Intake Document,Pitch Deck,Other"
    gdrive_max_file_mb: int = 100
    # How often the worker re-derives the complete Drive grant set from the
    # CRM and corrects drift in both directions (DOC-09's nightly
    # reconciliation; it also re-checks the DOC-08 documentsFolderUrl
    # write-back). Runs only under the service-identity access model
    # (GDRIVE_IDENTITY=service). 0 disables the job.
    gdrive_reconcile_seconds: int = 86400

    # --- Events & Webinars (prds/events/) — the public /webinars/ data layer,
    # registration into the CRM, Zoom webinar sync, attendance, and the /events
    # staff app. Master flag; nothing is mounted and no CRM write happens until
    # it is on. The public read API has its OWN flag so the website cutover is a
    # separate, instantly reversible switch from turning the feature on for
    # staff.
    events_enabled: bool = False
    events_public_api: bool = False
    # Zoom (PRD D-03/D-04) — the CBM webinar account, via a Server-to-Server
    # OAuth app. Off by default; with it off the feature still runs for
    # in-person events and simply provisions no webinars. NOTE this is the
    # public-webinar programme only — mentor 1:1 sessions keep using the
    # mentor's own personal meeting link and never touch this account.
    zoom_events: bool = False
    zoom_account_id: str = ""
    zoom_client_id: str = ""
    zoom_client_secret: str = ""      # SECRET (web + worker)
    # The single licensed host every webinar runs under.
    zoom_host_email: str = "zweb@cbmentors.org"
    zoom_base_url: str = "https://api.zoom.us/v2"
    # --- Phase 6a: attendance from the Zoom participant report ---
    # The worker pulls each finished online event's report and matches
    # participants to registrations by email. Inert without Zoom. 0 disables.
    events_attendance_seconds: int = 1800
    # Zoom does not publish the report the instant a webinar ends, so the pull
    # waits this long after dateEnd before its first attempt...
    events_attendance_grace_minutes: int = 20
    # ...and stops retrying after this, so an event that was never held is not
    # polled forever (the transcript give-up pattern).
    events_attendance_give_up_hours: int = 72

    # Team gate for the /events staff app (Phase 5).
    events_allowed_teams: str = "Marketing Admin Team"
    # In-process cache for the public read endpoints. The WordPress plugin
    # caches too, so a normal page load makes no live call to us at all.
    events_cache_seconds: int = 60
    # Where per-event pages live, for the `url` in the public payload. The
    # WordPress plugin owns these URLs so they stay on the marketing domain.
    events_public_base_url: str = "https://clevelandbusinessmentors.org/webinars"
    # YouTube: needed ONLY by the playlist backfill (EV-42). Rendering the
    # recorded library derives thumbnails from the video id with no key and no
    # API call - which is what gets the key out of the browser (EV-05).
    youtube_api_key: str = ""
    youtube_playlist_id: str = ""

    # --- Analytics (prds/analytics-app-plan.md) — the /analytics app + the
    # embedded record tabs + the portal dashboard. Master flag; the app is
    # absent (not mounted, no portal tile) until enabled. Metric definitions +
    # panels + pages are code-seeded in Phase A; cached-metric results live in
    # the analytics_cache table (needs DATABASE_URL — without it the app runs
    # live-only, recomputing each view). System pages compute under the org-wide
    # API key, so the team gates below (plus per-panel visibility) are the
    # access boundary.
    analytics_enabled: bool = False
    # How often the worker recomputes the seeded system dashboard's cached
    # metrics (0 disables the warm job; a cache miss still recomputes on view).
    analytics_refresh_seconds: int = 3600
    # Default TTL for a cached metric that doesn't set its own refresh_seconds.
    analytics_default_cache_ttl_seconds: int = 3600
    # Team(s) allowed to AUTHOR metrics/panels/pages (Phase B). CSV; admins pass.
    analytics_admin_allowed_teams: str = "Analytics Admin Team"
    # Team(s) allowed to VIEW analytics pages (per-panel visibility layers on
    # top). Defaults to the same team as authoring — widen per deploy if desired.
    analytics_view_allowed_teams: str = "Analytics Admin Team"

    # --- Encrypted runtime config (core/app_config.py) ---
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt secrets stored in the
    # app_config table — currently the Google service-account credentials set via
    # the Email Setup screen. Empty => the in-app setup store is disabled and the
    # app uses only the GOOGLE_* env vars above. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    app_encryption_key: str = ""

    # --- System Settings page (/setup, prds/system-settings-plan.md) ---
    # The admin-only page that overrides the settings below from the browser
    # instead of an overlay edit + `doctl apps update`. Off by default — the
    # feature ships dark like every other, which is the process it exists to
    # serve. Needs the staff stack (it uses the shared session) and a database
    # (overrides live in `app_setting`).
    setup_enabled: bool = False
    # BREAK-GLASS. False disables the override layer entirely and the app runs
    # on pure environment configuration. Env-only and denylisted, so a bad
    # override can never stop you from turning overrides off.
    settings_overrides: bool = True
    # How often each process re-reads the override table. This is the lag
    # between toggling something on web and the worker acting on it, so it is
    # also what the "worker picked up" indicator measures.
    setup_refresh_seconds: int = 45
    # Phase 3 — the environment diff. The OTHER deployment's base URL and a
    # shared token authorizing the read-only settings snapshot between them.
    setup_peer_url: str = ""
    setup_peer_token: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def alert_email_to_list(self) -> list[str]:
        return [a.strip() for a in self.alert_email_to.split(",") if a.strip()]

    @property
    def assign_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.assign_allowed_teams.split(",") if t.strip()]

    @property
    def assign_allowed_roles_list(self) -> list[str]:
        return [r.strip() for r in self.assign_allowed_roles.split(",") if r.strip()]

    @property
    def mentor_admin_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.mentor_admin_allowed_teams.split(",") if t.strip()]

    @property
    def ops_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.ops_allowed_teams.split(",") if t.strip()]

    @property
    def session_mentor_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.session_mentor_allowed_teams.split(",") if t.strip()]

    @property
    def session_partner_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.session_partner_allowed_teams.split(",") if t.strip()]

    @property
    def session_sponsor_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.session_sponsor_allowed_teams.split(",") if t.strip()]

    @property
    def mentor_profile_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.mentor_profile_allowed_teams.split(",") if t.strip()]

    @property
    def workspace_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.workspace_allowed_teams.split(",") if t.strip()]

    @property
    def comms_engagement_statuses_list(self) -> list[str]:
        return [s.strip() for s in self.comms_engagement_statuses.split(",") if s.strip()]

    @property
    def gdrive_doc_types_list(self) -> list[str]:
        return [t.strip() for t in self.gdrive_doc_types.split(",") if t.strip()]

    @property
    def gdrive_entity_labels_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.gdrive_entity_labels.split(","):
            if "=" in pair:
                entity, label = pair.split("=", 1)
                if entity.strip() and label.strip():
                    out[entity.strip()] = label.strip()
        return out

    @property
    def comms_partner_excluded_statuses_list(self) -> list[str]:
        return [s.strip() for s in self.comms_partner_excluded_statuses.split(",") if s.strip()]

    @property
    def comms_internal_domains_list(self) -> list[str]:
        return [
            d.strip().lower().lstrip("@")
            for d in self.comms_internal_domains.split(",")
            if d.strip()
        ]

    @property
    def assignments_active(self) -> bool:
        """The tool needs a session secret to sign cookies; off without one."""
        return self.assignments_enabled and bool(self.session_secret)

    @property
    def analytics_admin_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.analytics_admin_allowed_teams.split(",") if t.strip()]

    @property
    def analytics_view_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.analytics_view_allowed_teams.split(",") if t.strip()]

    @property
    def zoom_active(self) -> bool:
        """Zoom calls are possible: enabled, credentialed, and a host set."""
        return bool(
            self.zoom_events
            and self.zoom_account_id
            and self.zoom_client_id
            and self.zoom_client_secret
            and self.zoom_host_email
        )

    @property
    def events_allowed_teams_list(self) -> list[str]:
        return [t.strip() for t in self.events_allowed_teams.split(",") if t.strip()]

    @property
    def events_active(self) -> bool:
        """The Events feature as a whole (staff app + CRM writes)."""
        return self.events_enabled and self.assignments_active

    @property
    def events_public_active(self) -> bool:
        """The public read API. Needs the feature on AND its own flag, and a
        real CRM to read from - there is nothing to serve in dry-run."""
        return (
            self.events_enabled
            and self.events_public_api
            and not self.espo_dry_run
        )

    @property
    def analytics_active(self) -> bool:
        """The Analytics app is mounted only when enabled AND the staff stack is
        on (it uses the shared session)."""
        return self.analytics_enabled and self.assignments_active

    @property
    def store_enabled(self) -> bool:
        """Durable submission store is active only when a database is configured."""
        return bool(self.database_url)

    @property
    def setup_active(self) -> bool:
        """The System Settings page: enabled, on the staff stack, with a database
        to hold the overrides. Without all three there is nothing to serve."""
        return self.setup_enabled and self.assignments_active and bool(self.database_url)

    @property
    def overrides_active(self) -> bool:
        """Whether the DB override layer is consulted at all (break-glass off =>
        pure environment configuration, whatever is in the table)."""
        return self.settings_overrides and bool(self.database_url)

    @property
    def environment(self) -> str:
        """Canonical deploy label for the form badge.

        Honors an explicit ``env_label`` override; otherwise derives from the
        CRM target: a dry-run app is ``"dev"``, a ``crm-test`` base URL is
        ``"test"``, and any other live CRM is ``"production"``. This resolves
        correctly for all three App Platform apps without per-deploy config.
        """
        if self.env_label:
            return self.env_label
        if self.espo_dry_run:
            return "dev"
        if "crm-test" in self.espo_base_url.lower():
            return "test"
        return "production"


@lru_cache
def _env_settings() -> Settings:
    """The environment baseline — .env + process environment, no overrides."""
    return Settings()


# --- the runtime override layer (prds/system-settings-plan.md §3) -----------
#
# `get_settings()` stays the single accessor the whole codebase already calls;
# it just returns the env baseline with any admin overrides merged on top.
# Refreshing is out of band (a periodic task in each process calls
# `apply_overrides`), so reads stay synchronous and free.
#
# Ruling 6 — degrade to the OVERLAY, never to the code default: if merging the
# overrides fails for any reason, this returns the env baseline unchanged and
# logs. A database incident must not silently reconfigure the application.

_overrides: dict[str, object] = {}
_overrides_version = 0
_pristine: Optional[dict[str, object]] = None


def _baseline() -> dict[str, object]:
    """The environment's own values, captured before any override touched them.

    Taken once, from the singleton's initial state — everything after that is
    computed against this, so clearing an override restores the deployment value
    rather than the code default.
    """
    global _pristine
    if _pristine is None:
        _pristine = _env_settings().model_dump()
    return _pristine


def apply_overrides(values: dict[str, object]) -> None:
    """Install the current override set (called by the periodic refresher).

    Mutates the **one** ``Settings`` instance in place rather than replacing it.
    That matters: ``create_app`` captures a settings object at boot and its
    request handlers close over it, as do the intake handlers. Returning a new
    object from ``get_settings()`` would leave every one of those references
    frozen at boot — which is exactly the bug that made an override save
    correctly and change nothing (2026-08-09).
    """
    global _overrides, _overrides_version
    if values == _overrides:
        return
    baseline = _baseline()
    try:
        validated = Settings(**{**baseline, **values})
    except Exception as exc:  # noqa: BLE001 — a bad override changes nothing
        logging.getLogger("cbm_intake.config").warning(
            "settings overrides rejected, configuration unchanged: %s", exc
        )
        return
    live = _env_settings()
    for name in Settings.model_fields:
        new_value = getattr(validated, name)
        if getattr(live, name) != new_value:
            setattr(live, name, new_value)
    _overrides = dict(values)
    _overrides_version += 1


def env_values() -> dict[str, object]:
    """The DEPLOYMENT's own values — what each setting would be with no override.

    Since ``apply_overrides`` mutates the live instance in place, the live object
    can no longer answer "what does the overlay say?". This can, and it is what
    the page shows beside an overridden value so the overlay never silently lies
    about what the app is doing (ruling 2).
    """
    return dict(_baseline())


def env_value(key: str) -> object:
    return _baseline().get(key)


def override_values() -> dict[str, object]:
    """The overrides currently in effect in THIS process."""
    return dict(_overrides)


def overrides_version() -> int:
    """Bumped on every change — surfaced on /healthz so you can see a process
    pick a change up (the worker is a separate container from web)."""
    return _overrides_version


def get_settings() -> Settings:
    """The live configuration. Always the SAME object, so a reference captured
    at boot keeps reflecting later overrides."""
    return _env_settings()


def _clear_settings_cache() -> None:
    """Reset both layers. Exposed as ``get_settings.cache_clear`` so the many
    tests that call it keep working unchanged."""
    global _overrides, _overrides_version, _pristine
    _env_settings.cache_clear()
    _pristine = None
    _overrides = {}
    _overrides_version = 0


get_settings.cache_clear = _clear_settings_cache  # type: ignore[attr-defined]
