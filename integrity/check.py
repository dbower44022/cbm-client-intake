"""The six daily conditions — mentor login integrity plan § 4.2, step 4a.

Once a day the worker reads every mentor profile, every login (``User``) and
every mentor's own Contact under the key-based account (check C1: the key
reads every login, both CRMs) and lists what disagrees. "Ignoring case"
applies to every address comparison (``login_guard.same_address``).

1. One login on more than one mentor profile.
2. A CBM email that differs from its login's user name.
3. One CBM email on more than one mentor profile.
4. An Approved or Active mentor profile with no login.
5. An active login on the Mentor, Partner Management or Sponsor Management
   team linked to no mentor profile.
6. A mentor's own Contact carrying a login that is not its mentor profile's
   login.

Condition 7 is not a daily condition; it fires at sign-in (``signin.py``).

:func:`find_faults` is pure — it takes what :func:`read_crm` read and returns
one dict per fault, each with a stable ``key`` so the store can tell a fault
it already knows from a new one. A read that fails part-way raises: a partial
read must never close faults it simply did not see.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.config import Settings
from core.espo import is_not_found
from core.login_guard import MENTOR_PROFILE, login_ids, same_address

log = logging.getLogger("cbm_intake.integrity")

_PAGE = 200  # a list maxSize over 200 is a 403 (root CLAUDE.md)
CONTACT = "Contact"
#: Statuses at which a mentor must have a login (condition 4).
NEEDS_LOGIN = ("Approved", "Active")
#: Login types a person signs in with. ``api`` and ``system`` are not people.
PERSON_TYPES = ("regular", "admin")

CONDITIONS: dict[int, str] = {
    1: "One login on several mentor profiles",
    2: "CBM email differs from the login",
    3: "One CBM email on several mentor profiles",
    4: "Approved or Active with no login",
    5: "Team login with no mentor profile",
    6: "Mentor's Contact carries another login",
    7: "Signed in with no mentor profile",
}
DAILY = (1, 2, 3, 4, 5, 6)


@dataclass
class CrmSnapshot:
    """What one run read. ``team_members`` maps a team name to the login ids
    on it; ``contacts`` maps a Contact id to its login ids."""

    profiles: list[dict[str, Any]]
    users: dict[str, dict[str, Any]]
    team_members: dict[str, set[str]] = field(default_factory=dict)
    contacts: dict[str, list[str]] = field(default_factory=dict)


async def _all(client: Any, entity: str, select: str,
               where: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(entity, select=select, where=where, max_size=_PAGE,
                                 offset=offset, order_by="id", order="asc")
        rows = data.get("list", [])
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        offset += _PAGE


def team_names(settings: Settings) -> list[str]:
    """The Mentor, Partner Management and Sponsor Management teams, by the
    names this chapter's gates use (condition 5)."""
    names: list[str] = []
    for n in (settings.session_mentor_allowed_teams_list
              + settings.session_partner_allowed_teams_list
              + settings.session_sponsor_allowed_teams_list):
        if n not in names:
            names.append(n)
    return names


class IncompleteRead(RuntimeError):
    """The CRM answered, but with less than everything (a grant narrowed, a
    team renamed). The run must change nothing rather than close faults it
    simply did not see, or invent faults for records it could not read."""


async def _confirm_gone(client: Any, entity: str, ids: list[str]) -> set[str]:
    """Of ``ids`` missing from a list, the ones that are really gone (404).
    One that reads fine means the list was short: raise."""
    gone: set[str] = set()
    for rid in ids:
        try:
            rec = await client.get(entity, rid, select="id,deleted")
            if rec.get("deleted"):  # an admin reads a soft-deleted row (CLAUDE.md)
                gone.add(rid)
                continue
        except Exception as exc:  # noqa: BLE001
            if is_not_found(exc):
                gone.add(rid)
                continue
            raise
        raise IncompleteRead(f"the {entity} list left out {rid}, which reads fine on its own")
    return gone


async def read_crm(client: Any, settings: Settings) -> CrmSnapshot:
    """Everything the six conditions need, under the key-based account.
    Raises :class:`IncompleteRead` when the CRM's answer is short."""
    profiles = await _all(
        client, MENTOR_PROFILE,
        "id,name,cbmEmail,mentorStatus,contactRecordId,assignedUserId,assignedUsersIds")
    users = {u["id"]: u for u in await _all(client, "User", "id,userName,name,isActive,type")}
    if profiles and not any(login_ids(p) for p in profiles):
        raise IncompleteRead("no mentor profile carries a login — the assigned users were not read")
    missing = sorted({uid for p in profiles for uid in login_ids(p)} - set(users))
    await _confirm_gone(client, "User", missing)  # gone logins stay out of ``users``

    team_members: dict[str, set[str]] = {}
    teams = await _all(client, "Team", "id,name")
    by_name = {t.get("name"): t["id"] for t in teams}
    for name in team_names(settings):
        team_id = by_name.get(name)
        if not team_id:
            raise IncompleteRead(f"no team named {name!r} in this CRM (renamed, or "
                                 "the key cannot read it) — check the team gate settings")
        rows = await _all(client, "User", "id",
                          where=[{"type": "linkedWith", "attribute": "teams",
                                  "value": [team_id]}])
        team_members[name] = {r["id"] for r in rows}

    contact_ids = sorted({p["contactRecordId"] for p in profiles if p.get("contactRecordId")})
    contacts: dict[str, list[str]] = {}
    for i in range(0, len(contact_ids), 100):
        chunk = contact_ids[i:i + 100]
        data = await client.list(
            CONTACT, select="id,assignedUserId,assignedUsersIds", max_size=len(chunk),
            where=[{"type": "in", "attribute": "id", "value": chunk}])
        for c in data.get("list", []):
            contacts[c["id"]] = login_ids(c)
    await _confirm_gone(client, CONTACT, [c for c in contact_ids if c not in contacts])
    return CrmSnapshot(profiles, users, team_members, contacts)


def _mentor(p: dict[str, Any]) -> dict[str, str]:
    return {"id": p["id"], "name": p.get("name") or "(no name)"}


def _login(users: dict[str, dict[str, Any]], uid: str) -> dict[str, str]:
    u = users.get(uid) or {}
    return {"id": uid, "userName": u.get("userName") or "(unknown login)"}


def _names(ms: list[dict[str, Any]]) -> str:
    return ", ".join(m.get("name") or "(no name)" for m in ms)


def find_faults(snap: CrmSnapshot) -> list[dict[str, Any]]:
    """Every fault the six conditions find, in condition order."""
    faults: list[dict[str, Any]] = []
    users = snap.users

    def add(condition: int, key: str, summary: str, *, mentors: list[dict[str, Any]],
            login: Optional[str] = None) -> None:
        faults.append({
            "key": f"{condition}:{key}", "condition": condition, "summary": summary,
            "mentors": [_mentor(m) for m in mentors],
            "login": _login(users, login) if login else None,
        })

    # Who carries which login, over every profile.
    holders: dict[str, list[dict[str, Any]]] = {}
    for p in snap.profiles:
        for uid in login_ids(p):
            holders.setdefault(uid, []).append(p)

    # 1. One login on more than one mentor profile.
    for uid, ps in holders.items():
        if len(ps) > 1:
            add(1, uid, f"The login {_login(users, uid)['userName']} is on {len(ps)} "
                        f"mentor profiles: {_names(ps)}.", mentors=ps, login=uid)

    for p in snap.profiles:
        logins = login_ids(p)
        known = [uid for uid in logins if uid in users]
        cbm = (p.get("cbmEmail") or "").strip()
        name = p.get("name") or "(no name)"
        # 2. A CBM email that differs from its login's user name.
        if known and not any(same_address(users[uid].get("userName"), cbm) for uid in known):
            login_names = ", ".join(users[uid].get("userName") or "?" for uid in known)
            add(2, p["id"],
                f"{name}'s CBM email is {cbm or 'blank'}, but the login is {login_names}.",
                mentors=[p], login=known[0])
        # 4. An Approved or Active mentor profile with no login.
        status = p.get("mentorStatus") or ""
        if status in NEEDS_LOGIN and not known:
            why = ("its login no longer exists in the CRM" if logins
                   else "has no login")
            add(4, p["id"], f"{name} is {status} but {why}.", mentors=[p])

    # 3. One CBM email on more than one mentor profile.
    by_email: dict[str, list[dict[str, Any]]] = {}
    for p in snap.profiles:
        cbm = (p.get("cbmEmail") or "").strip().casefold()
        if cbm:
            by_email.setdefault(cbm, []).append(p)
    for cbm, ps in by_email.items():
        if len(ps) > 1:
            add(3, cbm, f"The CBM email {cbm} is on {len(ps)} mentor profiles: "
                        f"{_names(ps)}.", mentors=ps)

    # 5. An active login on a mentor team linked to no mentor profile.
    for uid in sorted({u for members in snap.team_members.values() for u in members}):
        u = users.get(uid) or {}
        if not u.get("isActive") or u.get("type") not in PERSON_TYPES or uid in holders:
            continue
        teams = [t for t, members in snap.team_members.items() if uid in members]
        add(5, uid, f"The login {u.get('userName') or uid} ({u.get('name') or 'no name'}) "
                    f"is on the {', '.join(teams)} but linked to no mentor profile.",
            mentors=[], login=uid)

    # 6. A mentor's own Contact carrying a login that is not its profile's.
    for p in snap.profiles:
        contact_id = p.get("contactRecordId")
        if not contact_id or contact_id not in snap.contacts:
            continue
        own = set(login_ids(p))
        for uid in snap.contacts[contact_id]:
            if uid not in own:
                add(6, f"{p['id']}:{uid}",
                    f"{p.get('name') or '(no name)'}'s own Contact carries the login "
                    f"{_login(users, uid)['userName']}, which is not this mentor "
                    f"profile's login.", mentors=[p], login=uid)
    return faults
