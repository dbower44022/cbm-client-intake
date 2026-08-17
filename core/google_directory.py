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
import secrets
import string
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.google_directory")

# Read-only Directory scope — used for the mailbox-existence lookup.
DIRECTORY_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
# Read-write Directory scope — required only to CREATE a mailbox. Must be
# separately authorized in the domain-wide-delegation grant for the service
# account; an account with only the read-only scope can check but not create.
DIRECTORY_WRITE_SCOPE = "https://www.googleapis.com/auth/admin.directory.user"
# Group-membership scope — required only to add a mailbox to a Google Group.
# A THIRD scope: it must be authorized for domain-wide delegation separately
# from the two user scopes above, and the impersonated admin needs group-admin
# privilege. Without it the member insert 403s `unauthorized_client`.
DIRECTORY_GROUP_SCOPE = "https://www.googleapis.com/auth/admin.directory.group"
_USER_URL = "https://admin.googleapis.com/admin/directory/v1/users/{email}"
_USERS_URL = "https://admin.googleapis.com/admin/directory/v1/users"
_GROUP_MEMBERS_URL = "https://admin.googleapis.com/admin/directory/v1/groups/{group}/members"
_GROUP_MEMBER_URL = (
    "https://admin.googleapis.com/admin/directory/v1/groups/{group}/members/{member}"
)


class MailboxStatus(str, Enum):
    """Outcome of a mailbox lookup. ``UNKNOWN`` = could not determine (the gate
    treats it as non-blocking — fail open)."""

    EXISTS = "exists"
    MISSING = "missing"
    UNKNOWN = "unknown"


class GoogleDirectoryError(Exception):
    """A Directory write (mailbox creation) or auth step failed — caller should
    stop provisioning and surface the message (unlike a *read* check, which fails
    open)."""


def gen_temp_password(length: int = 16) -> str:
    """A strong random password that satisfies Workspace complexity rules
    (mixed case, a digit, a symbol). The mentor must change it at first login."""
    alphabet = string.ascii_letters + string.digits
    base = "".join(secrets.choice(alphabet) for _ in range(max(length - 3, 8)))
    # Guarantee one of each required class regardless of the random draw.
    return (
        base
        + secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.digits)
        + secrets.choice("!@#$%^&*-_")
    )


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
        """Build from ``Settings`` env vars, or ``None`` when off/unconfigured."""
        if not (
            settings.google_directory_check
            and settings.google_service_account_json
            and settings.google_delegated_admin
        ):
            return None
        return cls._build(
            settings.google_service_account_json,
            settings.google_delegated_admin,
            settings.request_timeout_seconds,
            label="GOOGLE_SERVICE_ACCOUNT_JSON",
        )

    @classmethod
    def from_config(cls, cfg: dict[str, Any], timeout: int = 20) -> Optional["GoogleDirectory"]:
        """Build from a stored Email-Setup config dict (``service_account_json`` +
        ``delegated_admin``), or ``None`` when either is missing/invalid."""
        if not cfg:
            return None
        if not (cfg.get("service_account_json") and cfg.get("delegated_admin")):
            return None
        return cls._build(
            cfg["service_account_json"], cfg["delegated_admin"], timeout,
            label="the stored Email-Setup service account",
        )

    @classmethod
    def _build(cls, raw_json: str, admin: str, timeout: int, *, label: str) -> Optional["GoogleDirectory"]:
        try:
            info = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            log.warning("%s is not valid JSON — Google directory disabled", label)
            return None
        return cls(info, admin, timeout)

    async def _access_token(self, scopes: Optional[list[str]] = None) -> Optional[str]:
        """Mint a delegated access token for ``scopes`` (default: read-only)."""
        wanted = scopes or [DIRECTORY_SCOPE]
        try:
            # Imported lazily so the rest of the app doesn't depend on google-auth
            # unless the check is actually exercised.
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account

            def mint() -> str:
                creds = service_account.Credentials.from_service_account_info(
                    self._info, scopes=wanted, subject=self._subject
                )
                creds.refresh(Request())
                return creds.token

            return await asyncio.to_thread(mint)
        except Exception as exc:  # bad key, delegation not authorized, network, …
            log.warning("Google directory auth failed: %s", exc)
            return None

    async def create_user(
        self,
        primary_email: str,
        first_name: str,
        last_name: str,
        *,
        recovery_email: Optional[str],
        temp_password: str,
    ) -> None:
        """Create a Workspace mailbox. Idempotent (a 409 = already exists is fine).

        Raises :class:`GoogleDirectoryError` on auth failure or any other error so
        the caller stops before issuing a login for a non-existent inbox. Sets
        ``changePasswordAtNextLogin`` and a recovery email (the mentor's personal
        address) so they can claim the account via Google's password-reset flow.
        """
        token = await self._access_token(scopes=[DIRECTORY_WRITE_SCOPE])
        if not token:
            raise GoogleDirectoryError(
                "could not authenticate to Google Workspace to create the mailbox — "
                "check the service account and that the read-write Directory scope is "
                "authorized for domain-wide delegation"
            )
        body: dict[str, Any] = {
            "primaryEmail": primary_email,
            "name": {"givenName": first_name or "Mentor", "familyName": last_name or "Mentor"},
            "password": temp_password,
            "changePasswordAtNextLogin": True,
        }
        if recovery_email:
            body["recoveryEmail"] = recovery_email
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _USERS_URL, json=body, headers={"Authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as exc:
            raise GoogleDirectoryError(f"Google Workspace request failed: {exc}") from exc
        if resp.status_code in (200, 201):
            return
        if resp.status_code == 409:  # already exists — treat as success (idempotent)
            return
        raise GoogleDirectoryError(
            f"Google Workspace rejected the mailbox create (HTTP {resp.status_code}): "
            f"{resp.text[:300]}"
        )

    async def add_group_member(self, group_email: str, member_email: str) -> None:
        """Add ``member_email`` to the Google Group ``group_email`` as a MEMBER.

        Idempotent: a 409 (already a member) is success, exactly like
        :meth:`create_user`. Raises :class:`GoogleDirectoryError` on anything
        else — including a 404, which means the GROUP address is wrong and must
        never read as "added". Callers treat the failure as non-fatal (the
        mailbox itself is what matters) but must surface the message.
        """
        token = await self._access_token(scopes=[DIRECTORY_GROUP_SCOPE])
        if not token:
            raise GoogleDirectoryError(
                "could not authenticate to Google Workspace to update the group — "
                "check that the Directory *group* scope is authorized for "
                "domain-wide delegation and that the delegated admin can manage groups"
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _GROUP_MEMBERS_URL.format(group=group_email),
                    json={"email": member_email, "role": "MEMBER"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise GoogleDirectoryError(f"Google Workspace request failed: {exc}") from exc
        if resp.status_code in (200, 201, 409):  # 409 = already a member
            return
        if resp.status_code == 404:
            raise GoogleDirectoryError(
                f"the group {group_email} was not found in Google Workspace — "
                "check the address configured in Email Setup"
            )
        raise GoogleDirectoryError(
            f"Google Workspace rejected the group membership (HTTP {resp.status_code}): "
            f"{resp.text[:300]}"
        )

    async def is_group_member(self, group_email: str, member_email: str) -> Optional[bool]:
        """Whether ``member_email`` is in ``group_email``: True / False (404) /
        ``None`` when the check could not be made (fails open, like
        :meth:`mailbox_status`) — used by the Update-Mentor-Status sweep, which
        reports rather than acts."""
        token = await self._access_token(scopes=[DIRECTORY_GROUP_SCOPE])
        if not token:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    _GROUP_MEMBER_URL.format(group=group_email, member=member_email),
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            log.warning("Group membership lookup failed for %s: %s", member_email, exc)
            return None
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:  # not a member (or no such group — reported as absent)
            return False
        log.warning(
            "Group membership lookup for %s in %s returned HTTP %s",
            member_email, group_email, resp.status_code,
        )
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


@dataclass
class ResolvedGoogle:
    """The effective Google-Workspace integration for a request: the directory
    client (or None when unconfigured) plus which capabilities are switched on.

    ``members_group`` is the Google Group every CBM member belongs to (the
    "All Members" list). Empty = the group step is skipped entirely — no error,
    no flag of its own; the address IS the switch.
    """

    directory: Optional[GoogleDirectory]
    check_enabled: bool
    create_enabled: bool
    members_group: str = ""


def resolve_google_directory(settings: Any, db_config: Optional[dict[str, Any]]) -> ResolvedGoogle:
    """Pick the Google config to use: the in-app Email-Setup config (DB) first,
    else the ``GOOGLE_*`` environment variables. ``create_enabled`` always implies
    a configured directory (you can't create without credentials)."""
    if db_config and db_config.get("service_account_json") and db_config.get("delegated_admin"):
        directory = GoogleDirectory.from_config(db_config, settings.request_timeout_seconds)
        check = bool(db_config.get("directory_check", True)) and directory is not None
        create = bool(db_config.get("create_mailbox", False)) and directory is not None
        # The stored config wins as a whole (it is the screen an admin edits), so
        # a blank group here means blank — it does NOT fall back to the env var.
        group = (db_config.get("members_group") or "").strip()
        return ResolvedGoogle(directory, check, create, group)
    directory = GoogleDirectory.from_settings(settings)
    check = directory is not None  # from_settings already honors google_directory_check
    create = bool(getattr(settings, "google_create_mailbox", False)) and directory is not None
    group = (getattr(settings, "google_members_group", "") or "").strip()
    return ResolvedGoogle(directory, check, create, group)
