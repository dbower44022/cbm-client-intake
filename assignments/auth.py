"""EspoCRM username/password authentication + session handling.

Login posts the credentials to EspoCRM's ``App/user`` endpoint via the
``Espo-Authorization`` header. On success EspoCRM returns the user record plus a
reusable auth ``token``; that token (not the password) is stored in the signed
session cookie and replayed as the user on every later request.

Login itself only requires an active internal user (type ``admin``/``regular``);
the **portal** (``/``) signs everyone in once, stores the session under the
shared ``SESSION_KEY``, and each staff app enforces its own team gate **per
request** via :func:`is_member` (admins always pass).
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Any, Optional

import httpx

from core.config import Settings
from core.espo import EspoClient, EspoError

log = logging.getLogger("cbm_intake.assignments.auth")

# ONE shared staff session for the portal and all staff apps — sign in once at
# /, each app checks its own team against the session's ``teams`` per request.
# (Was "assign_user" per-app keys; renaming invalidates old sessions — re-login.)
SESSION_KEY = "staff_user"
# Keys persisted in the (signed) session cookie. Excludes nothing sensitive
# beyond the EspoCRM token, which is the user's own and travels over HTTPS.
# teams/roles ride along so per-request gates don't re-query the CRM; the
# portal refreshes them from the CRM on every session restore (see
# :func:`refresh_membership`) so membership changes don't need a re-login.
_SESSION_FIELDS = ("userId", "userName", "name", "token", "isAdmin", "teams", "roles")


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
    except EspoError as exc:
        # An empty team list fails closed at every staff gate — a user losing
        # tool access because this read failed must be diagnosable.
        log.warning("membership fallback read failed for User/%s: %s", user_id, exc)
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
    gate: bool = True,
) -> dict[str, Any]:
    """Validate credentials against EspoCRM and return the session user dict.

    Authorization (``gate=True``): EspoCRM admins always pass; otherwise the
    user must belong to an allowed Team or hold an allowed Role.
    ``allowed_teams``/``allowed_roles`` default to the assignment tool's
    settings (``ASSIGN_ALLOWED_TEAMS`` / ``ASSIGN_ALLOWED_ROLES``). With
    ``gate=False`` (the portal's single sign-on), any active internal user
    signs in — each staff app then enforces its own team per request via
    :func:`is_member` on the session's ``teams``. Team/role names are read
    from the user's own ``App/user`` payload (falling back to their User
    record).

    :raises AuthError: bad credentials, inactive/non-internal account, or
        (when gated) the user is not authorized.
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

    if gate and not is_admin:
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


async def _password_change_request(
    base_url: str, payload: dict[str, str], timeout: int
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(
            f"{base_url.rstrip('/')}/api/v1/User/passwordChangeRequest", json=payload
        )


async def request_password_reset(settings: Settings, username: str, email: str) -> None:
    """Ask EspoCRM to email the user a password-recovery link.

    Proxies the CRM's own unauthenticated ``User/passwordChangeRequest``
    endpoint (the one behind EspoCRM's login-page "Forgot Password?"), so the
    reset email, the recovery link, and the new-password screen are all the
    CRM's — the app never sees or sets a password. Requires password recovery
    to be enabled in the CRM (Administration → Authentication) and working
    outbound email.

    :raises AuthError: with a user-readable message — no matching user/email,
        recovery disabled (or the CRM throttled a repeat request), the email
        couldn't be sent, or the CRM couldn't be reached.
    """
    try:
        resp = await _password_change_request(
            settings.espo_base_url,
            {"userName": username, "emailAddress": email},
            settings.request_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        log.warning("password reset: CRM unreachable: %s", exc)
        raise AuthError("The CRM could not be reached — please try again in a moment.")
    if resp.status_code < 400:
        log.info("password reset email requested for userName=%s", username)
        return
    reason = resp.headers.get("X-Status-Reason", "")
    log.warning(
        "password reset refused for userName=%s: HTTP %s %s",
        username, resp.status_code, reason,
    )
    if resp.status_code == 404:
        raise AuthError(
            "No user with that username and email address was found — "
            "check both and try again."
        )
    if resp.status_code == 403:
        # EspoCRM uses 403 both for "recovery disabled" and for a repeat
        # request made while an earlier reset link is still valid.
        raise AuthError(
            "The CRM refused the request — password recovery may be disabled, "
            "or a reset link was already sent recently. Check your email, or "
            "contact a CBM administrator."
        )
    raise AuthError(
        "The password reset email could not be sent — please contact a CBM administrator."
    )


async def refresh_membership(settings: Settings, user: dict[str, Any]) -> dict[str, Any]:
    """Re-read the session user's team/role membership (and admin flag) from the
    CRM, as the user, and return the updated session dict.

    The signed session cookie caches ``teams``/``roles`` at LOGIN time, so a
    membership change made in the CRM afterwards stayed invisible until the user
    signed out and back in — the portal looked like it "wasn't reviewing all
    teams". The portal calls this on every session restore and re-saves the
    session, so entitlements always reflect current CRM membership (the staff
    apps' per-request gates read the same refreshed cookie).

    Best-effort on CRM hiccups: a failed read keeps the cached values (never
    locks a user out over a blip). A field the CRM didn't serialize is also
    kept from cache rather than treated as "no teams".

    :raises AuthError: the stored token is no longer valid — the caller clears
        the session so the user signs in again.
    """
    client = EspoClient.for_user_token(
        settings.espo_base_url, user["userName"], user["token"],
        settings.request_timeout_seconds,
    )
    try:
        rec = await client.get("User", user["userId"], select="type,teamsNames,rolesNames")
    except EspoError as exc:
        if session_expired(exc):
            raise AuthError("Your session has expired — please sign in again.")
        log.warning(
            "membership refresh failed for %s (keeping cached teams): %s",
            user.get("userName"), exc,
        )
        return user
    updated = dict(user)
    teams = _names(rec, "teamsNames")
    if teams is not None:
        updated["teams"] = teams
    roles = _names(rec, "rolesNames")
    if roles is not None:
        updated["roles"] = roles
    if rec.get("type"):
        updated["isAdmin"] = rec["type"] == "admin"
    return updated


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


def is_member(
    user: dict[str, Any],
    allowed_teams: list[str],
    allowed_roles: Optional[list[str]] = None,
) -> bool:
    """Whether a session user may use an app gated by ``allowed_teams`` /
    ``allowed_roles``. Admins always pass. Used by each staff router's
    per-request gate (the portal signs users in ungated)."""
    if user.get("isAdmin"):
        return True
    if set(user.get("teams") or []) & set(allowed_teams):
        return True
    return bool(set(user.get("roles") or []) & set(allowed_roles or []))


# --- session helpers (Starlette SessionMiddleware backs request.session) ---

def set_session(request, user: dict[str, Any], key: str = SESSION_KEY) -> None:
    data = {k: user.get(k) for k in _SESSION_FIELDS}
    # Membership-freshness stamp (P1-12): every caller writes the session right
    # after reading membership from the CRM (login, portal restore, the TTL
    # middleware), so "now" is correct by construction. The staff-gate TTL
    # middleware re-reads membership when this stamp is older than
    # MEMBERSHIP_REFRESH_SECONDS.
    data["refreshedAt"] = time.time()
    request.session[key] = data


def current_user(request, key: str = SESSION_KEY) -> Optional[dict[str, Any]]:
    return request.session.get(key)


def clear_session(request, key: str = SESSION_KEY) -> None:
    request.session.pop(key, None)


_HTTP_STATUS_RE = re.compile(r"HTTP (\d{3})")


def session_expired(exc: Exception) -> bool:
    """True if a per-user CRM call failed because the EspoCRM auth token is no
    longer valid (expired/revoked). The shared staff session is signed but the
    token inside it has a finite life, so a still-"logged in" session can hit
    this — callers clear the session and return 401 so the UI re-prompts login.

    Match the *first* ``HTTP <code>`` in the message — ``EspoError`` always puts
    the real status code there, ahead of the (echoed) response body, so a 502
    whose body merely contains the text "HTTP 401" is not misread as expiry.
    """
    match = _HTTP_STATUS_RE.search(str(exc))
    return bool(match) and match.group(1) == "401"
