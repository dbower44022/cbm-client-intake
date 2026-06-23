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


def _names(user: dict[str, Any], field: str) -> Optional[list[str]]:
    """The names from a linkMultiple ``*Names`` field, or None if absent.

    EspoCRM stores these as ``{id: name}`` maps (e.g. ``teamsNames``,
    ``rolesNames``). Absent (None) means the field wasn't serialized — the caller
    falls back to reading the User record directly.
    """
    v = user.get(field)
    if v is None:
        return None
    return list(v.values()) if isinstance(v, dict) else list(v)


async def _app_user(base_url: str, headers: dict[str, str], timeout: int) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.get(
            f"{base_url.rstrip('/')}/api/v1/App/user", headers=headers
        )


async def _fetch_names(
    settings: Settings, user_name: str, token: str, user_id: str, field: str
) -> tuple[list[str], str]:
    """Read a ``*Names`` field off the user's own record (App/user fallback).

    Returns ``(names, source)`` where source flags whether the fallback ran.
    """
    client = EspoClient.for_user_token(
        settings.espo_base_url, user_name, token, settings.request_timeout_seconds
    )
    try:
        rec = await client.get("User", user_id, select=field)
    except EspoError:
        return [], "fallback-error"
    return _names(rec, field) or [], "App/user-fallback"


async def _names_with_fallback(
    settings: Settings, user: dict[str, Any], token: str, field: str
) -> tuple[list[str], str]:
    """Names from the App/user payload, else from the User record directly."""
    names = _names(user, field)
    if names is not None:
        return names, "App/user"
    return await _fetch_names(
        settings, user["userName"], token, user["id"], field
    )


async def authenticate(
    settings: Settings,
    username: str,
    password: str,
    *,
    allowed_teams: Optional[list[str]] = None,
    allowed_roles: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Validate credentials against EspoCRM and return the session user dict.

    Authorization: EspoCRM admins always pass; otherwise the user must belong to
    an allowed Team or hold an allowed Role. ``allowed_teams``/``allowed_roles``
    default to the assignment tool's settings (``ASSIGN_ALLOWED_TEAMS`` /
    ``ASSIGN_ALLOWED_ROLES``); other staff apps (e.g. mentor-admin) pass their
    own. Team/role names are read from the user's own ``App/user`` payload
    (falling back to their User record).

    :raises AuthError: bad credentials, inactive/non-internal account, or the
        user is not authorized.
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
    teams, teams_src = await _names_with_fallback(settings, user, token, "teamsNames")
    roles, roles_src = await _names_with_fallback(settings, user, token, "rolesNames")

    if not is_admin:
        allowed_teams = (
            settings.assign_allowed_teams_list if allowed_teams is None else allowed_teams
        )
        allowed_roles = (
            settings.assign_allowed_roles_list if allowed_roles is None else allowed_roles
        )
        team_ok = bool(set(teams) & set(allowed_teams))
        role_ok = bool(set(roles) & set(allowed_roles))
        if not (team_ok or role_ok):
            # Diagnostic: shows WHY a valid login was refused — team/role names
            # are not secret. Empty lists distinguish "not a member" from
            # "names couldn't be read" (a CRM ACL strip).
            log.warning(
                "assignment login denied user=%s isAdmin=%s teams=%s (%s) "
                "roles=%s (%s) allowed_teams=%s allowed_roles=%s",
                user.get("userName"), is_admin, teams, teams_src,
                roles, roles_src, allowed_teams, allowed_roles,
            )
            raise AuthError("Your account is not authorized to use this tool.")

    return {
        "userId": user["id"],
        "userName": user["userName"],
        "name": user.get("name") or user["userName"],
        "token": token,
        "isAdmin": is_admin,
        "teams": teams,
        "roles": roles,
    }


async def login_token(
    base_url: str, username: str, password: str, timeout: int
) -> tuple[str, str]:
    """Authenticate a backend service account and return ``(userName, token)``.

    Like :func:`authenticate` but with **no team/role ACL gating** — for trusted
    server-side accounts (e.g. the dedicated admin used to provision mentor login
    users), not interactive staff. The returned token is replayed via
    ``EspoClient.for_user_token`` so calls run with that account's privileges.
    """
    cred = base64.b64encode(f"{username}:{password}".encode()).decode()
    resp = await _app_user(base_url, {"Espo-Authorization": cred}, timeout)
    if resp.status_code in (401, 403):
        raise AuthError("Service account credentials were rejected.")
    if resp.status_code >= 400:
        raise AuthError(f"Service login failed (HTTP {resp.status_code}).")
    data = resp.json()
    user = data.get("user") or {}
    token = data.get("token")
    if not token or not user.get("userName"):
        raise AuthError("Service login did not return a usable token.")
    # Diagnostic: confirms whether the service account actually has admin rights
    # (User creation is admin-only, so a non-admin here is why provisioning 403s).
    log.info(
        "service login OK: userName=%s type=%s isAdmin=%s",
        user.get("userName"), user.get("type"), user.get("isAdmin"),
    )
    return user["userName"], token


# --- session helpers (Starlette SessionMiddleware backs request.session) ---

def set_session(request, user: dict[str, Any], key: str = SESSION_KEY) -> None:
    request.session[key] = {k: user[k] for k in _SESSION_FIELDS}


def current_user(request, key: str = SESSION_KEY) -> Optional[dict[str, Any]]:
    return request.session.get(key)


def clear_session(request, key: str = SESSION_KEY) -> None:
    request.session.pop(key, None)


def session_expired(exc: Exception) -> bool:
    """True if a per-user CRM call failed because the EspoCRM auth token is no
    longer valid (expired/revoked). The shared staff session is signed but the
    token inside it has a finite life, so a still-"logged in" session can hit
    this — callers clear the session and return 401 so the UI re-prompts login.
    """
    return "HTTP 401" in str(exc)
