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
    # allowed Role. Both empty => admins only.
    assign_allowed_teams: str = ""
    assign_allowed_roles: str = ""
    # Mentor Admin app (/mentoradmin) — gated to its own team.
    mentor_admin_allowed_teams: str = "Mentor Administration Team"
    # Team that approved mentors' new login users are placed in.
    mentor_team_name: str = "Mentor Team"
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
    def assignments_active(self) -> bool:
        """The tool needs a session secret to sign cookies; off without one."""
        return self.assignments_enabled and bool(self.session_secret)

    @property
    def store_enabled(self) -> bool:
        """Durable submission store is active only when a database is configured."""
        return bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
