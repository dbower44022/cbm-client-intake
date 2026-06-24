"""Google Workspace Directory check — does a CBM mailbox actually exist?

Used to **hard-gate mentor-login provisioning**: we won't create an EspoCRM login
(and fire its ``sendAccessInfo`` welcome email) for a ``…@cbmentors.org`` address
that has no real Google Workspace mailbox, because the credentials email would
bounce and strand the mentor with a login they can never receive.

Auth is a Google Cloud **service account with domain-wide delegation** for the
read-only Directory scope, impersonating a Workspace admin. Disabled (a no-op,
``from_settings`` → ``None``) until both the service-account JSON and the
delegated admin are configured. The lookup *fails open* — an unconfigured or
erroring check returns :data:`MailboxStatus.UNKNOWN`, which the caller treats as
"don't block" so a Google outage can't freeze every approval.
"""

from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.google_directory")

# Read-only Directory scope — we only ever look users up, never modify them.
DIRECTORY_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
_USER_URL = "https://admin.googleapis.com/admin/directory/v1/users/{email}"


class MailboxStatus(str, Enum):
    """Outcome of a mailbox lookup. ``UNKNOWN`` = could not determine (the gate
    treats it as non-blocking — fail open)."""

    EXISTS = "exists"
    MISSING = "missing"
    UNKNOWN = "unknown"


class GoogleDirectory:
    """Looks up whether an address resolves to a Google Workspace mailbox."""

    def __init__(
        self, service_account_info: dict[str, Any], delegated_admin: str, timeout: int = 20
    ) -> None:
        self._info = service_account_info
        self._subject = delegated_admin
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings: Any) -> Optional["GoogleDirectory"]:
        """Build from ``Settings``, or ``None`` when the check is off/unconfigured."""
        if not (
            settings.google_directory_check
            and settings.google_service_account_json
            and settings.google_delegated_admin
        ):
            return None
        try:
            info = json.loads(settings.google_service_account_json)
        except (json.JSONDecodeError, TypeError):
            log.warning(
                "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON — directory check disabled"
            )
            return None
        return cls(info, settings.google_delegated_admin, settings.request_timeout_seconds)

    async def _access_token(self) -> Optional[str]:
        """Mint a delegated, read-only access token (best-effort)."""
        try:
            # Imported lazily so the rest of the app doesn't depend on google-auth
            # unless the check is actually exercised.
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account

            def mint() -> str:
                creds = service_account.Credentials.from_service_account_info(
                    self._info, scopes=[DIRECTORY_SCOPE], subject=self._subject
                )
                creds.refresh(Request())
                return creds.token

            return await asyncio.to_thread(mint)
        except Exception as exc:  # bad key, delegation not authorized, network, …
            log.warning("Google directory auth failed: %s", exc)
            return None

    async def mailbox_status(self, email: str) -> MailboxStatus:
        """``EXISTS`` (200) / ``MISSING`` (404) / ``UNKNOWN`` (anything else)."""
        token = await self._access_token()
        if not token:
            return MailboxStatus.UNKNOWN
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    _USER_URL.format(email=email),
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            log.warning("Directory lookup failed for %s: %s", email, exc)
            return MailboxStatus.UNKNOWN
        if resp.status_code == 200:
            return MailboxStatus.EXISTS
        if resp.status_code == 404:
            return MailboxStatus.MISSING
        log.warning("Directory lookup for %s returned HTTP %s", email, resp.status_code)
        return MailboxStatus.UNKNOWN
