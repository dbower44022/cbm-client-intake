"""Login integrity guards — when login data disagrees, stop and say so.

Mentor login integrity plan (``prds/mentor-login-integrity-plan.md`` § 4.3),
step 2. On 10-16-26 a staff member put Doug Bower's login on David Weissman's
mentor profile; the next night the clean-up job copied it onto David's
Contact. Three repair paths copy a login between a mentor profile and its
Contact, and each trusted whatever it found. Behind ``LOGIN_REPAIR_GUARDS``
they act only when the data agrees:

* **profile → Contact** (the clean-up job's Phase A, and the first half of
  ``reconcile_user_links``): the login sits on exactly one mentor profile —
  this one — and its user name matches the profile's CBM email.
* **Contact → profile** (the second half of ``reconcile_user_links``): the
  Contact carries exactly one login, no other mentor profile carries it, and
  it matches the CBM email.
* **provisioning's login reuse**: no other mentor profile carries the login
  found by the CBM email.

A refusal is a **fault**: logged as a WARNING starting ``login-integrity:``
so it can be found in the runtime log. The daily integrity check (plan step
4) reports the same conditions to staff.

Reads run under the application's key-based account (``reader()``): staff
roles cannot read ``User``, and the key reads every login and mentor profile
(check C1, both CRMs). "Ignoring case" applies to every address comparison.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .config import get_settings
from .espo import EspoClient

log = logging.getLogger("cbm_intake.login_guard")

MENTOR_PROFILE = "CMentorProfile"
_PAGE = 200  # a list maxSize over 200 is a 403 (root CLAUDE.md)


def enabled() -> bool:
    """``LOGIN_REPAIR_GUARDS``, read per call so /setup can switch it."""
    return bool(get_settings().login_repair_guards)


def reader() -> Optional[EspoClient]:
    """The key-based client the guard reads with; None in dry-run."""
    settings = get_settings()
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


def same_address(a: Optional[str], b: Optional[str]) -> bool:
    """Two addresses are the same ignoring case and surrounding space; an
    empty one matches nothing."""
    a, b = (a or "").strip().casefold(), (b or "").strip().casefold()
    return bool(a) and a == b


def login_ids(rec: dict[str, Any]) -> list[str]:
    """Every login on a record: the single field and the collaborators list."""
    ids = list(rec.get("assignedUsersIds") or [])
    single = rec.get("assignedUserId")
    if single and single not in ids:
        ids.insert(0, single)
    return ids


_ONCE_SECONDS = 3600.0
_last_logged: dict[str, float] = {}


def fault(kind: str, *, once: Optional[str] = None, **facts: Any) -> None:
    """Record a refused repair. One greppable line until the integrity check
    (plan step 4) carries faults to staff. ``once``: a key logged at most
    once an hour per process (a fault met on every page request)."""
    if once is not None:
        now = time.monotonic()
        if now - _last_logged.get(once, -_ONCE_SECONDS) < _ONCE_SECONDS:
            return
        _last_logged[once] = now
    log.warning("login-integrity: %s %s", kind,
                " ".join(f"{k}={v!r}" for k, v in facts.items()))


async def profiles_carrying(client: Any, user_id: str) -> list[dict[str, Any]]:
    """Every mentor profile carrying ``user_id`` as a login, matched in Python
    (never a ``where`` on assigned users — production's field rules forbid it)."""
    found: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            MENTOR_PROFILE, select="id,name,cbmEmail,assignedUserId,assignedUsersIds",
            max_size=_PAGE, offset=offset,
        )
        rows = data.get("list", [])
        found.extend(r for r in rows if user_id in login_ids(r))
        if len(rows) < _PAGE:
            return found
        offset += _PAGE


async def user_name(client: Any, user_id: str) -> Optional[str]:
    rec = await client.get("User", user_id, select="userName")
    return rec.get("userName")


async def refuse_profile_to_contact(
    client: Any, profile: dict[str, Any], user_id: str
) -> Optional[str]:
    """Why copying ``user_id`` from ``profile`` onto its Contact must not
    happen, or None when the data agrees."""
    holders = [p["id"] for p in await profiles_carrying(client, user_id)]
    if holders != [profile["id"]]:
        return f"the login is on {len(holders)} mentor profiles"
    name = await user_name(client, user_id)
    if not same_address(name, profile.get("cbmEmail")):
        return (f"the login {name or '?'} does not match the CBM email "
                f"{profile.get('cbmEmail') or '(blank)'}")
    return None


async def refuse_contact_to_profile(
    client: Any, profile: dict[str, Any], contact_logins: list[str]
) -> Optional[str]:
    """Why filling ``profile``'s empty login from its Contact must not happen,
    or None when the data agrees."""
    if len(contact_logins) != 1:
        return f"the Contact carries {len(contact_logins)} logins"
    uid = contact_logins[0]
    others = [p for p in await profiles_carrying(client, uid) if p["id"] != profile["id"]]
    if others:
        return f"the login is already on another mentor profile ({others[0].get('name')})"
    name = await user_name(client, uid)
    if not same_address(name, profile.get("cbmEmail")):
        return (f"the login {name or '?'} does not match the CBM email "
                f"{profile.get('cbmEmail') or '(blank)'}")
    return None


async def refuse_login_reuse(
    client: Any, mentor_id: str, user_id: str
) -> Optional[dict[str, Any]]:
    """The other mentor profile already carrying ``user_id``, or None."""
    others = [p for p in await profiles_carrying(client, user_id) if p["id"] != mentor_id]
    return others[0] if others else None
