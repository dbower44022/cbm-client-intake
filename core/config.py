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
    # Marks a session cookie Secure; set false only for plain-HTTP local dev.
    session_cookie_secure: bool = True

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
