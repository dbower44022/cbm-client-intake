"""Application configuration, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

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

    # Environment label shown as a corner badge on every form (via /healthz ->
    # shared/footer.js). Empty => auto-derived from the CRM target below
    # ("production" / "test" / "dev"); set explicitly to override the wording.
    env_label: str = ""

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

    # --- V2 Phase 3: monitoring + alerting (run as periodic worker tasks) ---
    # Where to send alerts (a Slack-compatible {"text": ...} webhook). Empty =>
    # alerts are logged at WARNING only.
    alert_webhook_url: str = ""
    alert_check_seconds: int = 300          # how often the worker evaluates thresholds
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
    # Session Management tools — one engine, three team-gated routes
    # (/mentorsessions, /partnersessions, /sponsorsessions). Each lets its users
    # record CSession meetings against the records they own.
    session_mentor_allowed_teams: str = "Mentor Team"
    session_partner_allowed_teams: str = "Partner Management Team"
    session_sponsor_allowed_teams: str = "Sponsor Management Team"
    # My Mentor Profile (/mentorprofile) — a mentor edits their OWN profile +
    # Contact, with a live website preview. Gated to the Mentor Team.
    mentor_profile_allowed_teams: str = "Mentor Team"
    # Team that approved mentors' new login users are placed in.
    mentor_team_name: str = "Mentor Team"
    # Team stamped onto every NEW CPartnerProfile the partner intake form
    # creates, so team-scoped roles (Partner Management Team members) can see
    # all partners in /partnersessions. Best-effort: an unresolvable team
    # (e.g. the API role lacks Team read) logs a WARNING and the partner is
    # created without it. Empty string disables the stamp.
    partner_team_name: str = "Partner Management Team"
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
    # OPTIONAL AI layer: per-conversation Claude summaries/status/action items.
    # Off by default — with it off, nothing leaves Google/the CRM and no
    # Anthropic key is needed. Requires ANTHROPIC_API_KEY when on.
    comms_ai_summary: bool = False
    anthropic_api_key: str = ""
    summary_model: str = "claude-opus-4-8"

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
    # the operational mode; "user" remains for compatibility.
    gdrive_identity: str = "user"
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

    # --- Encrypted runtime config (core/app_config.py) ---
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt secrets stored in the
    # app_config table — currently the Google service-account credentials set via
    # the Email Setup screen. Empty => the in-app setup store is disabled and the
    # app uses only the GOOGLE_* env vars above. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    app_encryption_key: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

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
    def assignments_active(self) -> bool:
        """The tool needs a session secret to sign cookies; off without one."""
        return self.assignments_enabled and bool(self.session_secret)

    @property
    def store_enabled(self) -> bool:
        """Durable submission store is active only when a database is configured."""
        return bool(self.database_url)

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
def get_settings() -> Settings:
    return Settings()
