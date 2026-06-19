"""EspoCRM username/password authentication + session handling.

Login posts the credentials to EspoCRM's ``App/user`` endpoint via the
``Espo-Authorization`` header. On success EspoCRM returns the user record plus a
reusable auth ``token``; that token (not the password) is stored in the signed
session cookie and replayed as the user on every later request.

Access is gated to active internal users (type ``admin``/``regular``) who are
either an admin or hold one of ``ASSIGN_ALLOWED_ROLES``.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

from core.config import Settings
from core.espo import EspoClient, EspoError

log = logging.getLogger("cbm_intake.assignments.auth")

SESSION_KEY = "assign_user"
# Keys persisted in the (signed) session cookie. Excludes nothing sensitive
# beyond the EspoCRM token, which is the user's own and travels over HTTPS.
_SESSION_FIELDS = ("userId", "userName", "name", "token", "isAdmin")


class AuthError(Exception):
    """Login failed or the user is not authorized to use the tool."""


def _role_names(user: dict[str, Any]) -> Optional[list[str]]:
    """Role names from a user record, or None if the field is absent."""
    rn = user.get("rolesNames")
    if rn is None:
        return None
    return list(rn.values()) if isinstance(rn, dict) else list(rn)


async def _app_user(base_url: str, headers: dict[str, str], timeout: int) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.get(
            f"{base_url.rstrip('/')}/api/v1/App/user", headers=headers
        )


async def _fetch_role_names(
    settings: Settings, user_name: str, token: str, user_id: str
) -> list[str]:
    """Read the user's own roles with their fresh token (App/user fallback)."""
    client = EspoClient.for_user_token(
        settings.espo_base_url, user_name, token, settings.request_timeout_seconds
    )
    try:
        rec = await client.get("User", user_id, select="rolesNames")
    except EspoError:
        return []
    return _role_names(rec) or []


async def authenticate(
    settings: Settings, username: str, password: str
) -> dict[str, Any]:
    """Validate credentials against EspoCRM and return the session user dict.

    :raises AuthError: bad credentials, inactive/non-internal account, or the
        user is not authorized by role.
    """
    cred = base64.b64encode(f"{username}:{password}".encode()).decode()
    resp = await _app_user(
        settings.espo_base_url,
        {"Espo-Authorization": cred},
        settings.request_timeout_seconds,
    )
    if resp.status_code in (401, 403):
        raise AuthError("Invalid username or password.")
    if resp.status_code >= 400:
        raise AuthError(f"Login failed (HTTP {resp.status_code}).")

    data = resp.json()
    user = data.get("user") or {}
    token = data.get("token")
    if not token or not user.get("id"):
        raise AuthError("Login did not return a usable session.")
    if not user.get("isActive", False):
        raise AuthError("This account is not active.")
    if user.get("type") not in ("admin", "regular"):
        raise AuthError("This tool is for internal staff users only.")

    is_admin = user.get("type") == "admin" or bool(user.get("isAdmin"))
    roles = _role_names(user)
    from_fallback = roles is None
    if from_fallback:
        roles = await _fetch_role_names(
            settings, user["userName"], token, user["id"]
        )

    if not is_admin:
        allowed = settings.assign_allowed_roles_list
        if not allowed or not (set(roles) & set(allowed)):
            # Diagnostic: shows WHY a valid login was refused — role names are
            # not secret. Distinguishes "user lacks the role" (roles populated,
            # no match) from "role names couldn't be read" (roles empty).
            log.warning(
                "assignment login denied user=%s isAdmin=%s roles=%s "
                "(source=%s) allowed=%s",
                user.get("userName"), is_admin, roles,
                "App/user-fallback" if from_fallback else "App/user", allowed,
            )
            raise AuthError("Your account is not authorized to use this tool.")

    return {
        "userId": user["id"],
        "userName": user["userName"],
        "name": user.get("name") or user["userName"],
        "token": token,
        "isAdmin": is_admin,
        "roles": roles,
    }


# --- session helpers (Starlette SessionMiddleware backs request.session) ---

def set_session(request, user: dict[str, Any]) -> None:
    request.session[SESSION_KEY] = {k: user[k] for k in _SESSION_FIELDS}


def current_user(request) -> Optional[dict[str, Any]]:
    return request.session.get(SESSION_KEY)


def clear_session(request) -> None:
    request.session.pop(SESSION_KEY, None)
