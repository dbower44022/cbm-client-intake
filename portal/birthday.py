"""Whose birthday is it today?

The portal (``/``) is where everyone signs in, so it is where CBM's birthdays
are surfaced: the signing-in member gets "Happy Birthday, <name>!", and every
other member gets "Wish <name> a Happy Birthday!" so the whole organization
knows.

**CBM member = ``CMentorProfile``** (the member record — mentors, partner and
funder managers, staff), and the birthday lives on that profile's linked
**Contact** (``cBirthday`` — the field members maintain themselves in
``/mentorprofile`` under "Personal details").

One read serves everyone: the day's roster is fetched ONCE per process (hourly,
under the org-wide API key) and cached, because it is the same for every viewer
— an announcement everyone is meant to see. That also means a portal request
costs **no** CRM call of its own, and the answer doesn't vary with the viewer's
ACL. Only names are ever exposed: no birth date, no year, no age.

Entirely **best-effort**: no API key, no profile, no linked Contact, an empty
birthday, or any CRM failure simply means no greeting — signing in must never
depend on this.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import time
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from assignments.service import is_assigned_to
from core.config import Settings
from core.espo import EspoClient

log = logging.getLogger("cbm_intake.portal.birthday")

MENTOR_PROFILE = "CMentorProfile"
CONTACT_ENTITY = "Contact"
BIRTHDAY_FIELD = "cBirthday"

# CBM is a Cleveland organization: "today" is the local calendar day there, not
# the server's UTC day (which would start the greeting five hours early and end
# it five hours early too).
_LOCAL = ZoneInfo("America/New_York")

# Whose birthday is ANNOUNCED to the rest of CBM: people who are currently part
# of the organization. Applicants (Prospect/Candidate/Under Review) aren't
# members yet, and former members (Resigned/Retired/Terminated/Declined/
# Inactive/Dormant) shouldn't be announced as though they were still here.
# A member's OWN greeting is deliberately NOT status-gated — if they can sign
# in, CBM wishes them a happy birthday.
ANNOUNCED_STATUSES = frozenset(
    {"Active", "Approved", "Provisional", "Accepted-Provisional", "Paused"}
)

_PAGE = 200
_CHUNK = 100          # ids per Contact `in` query
_TTL_SECONDS = 3600   # the roster changes at most once a day
_RETRY_SECONDS = 60   # after a failure, don't hammer a struggling CRM

# Process-wide cache. Safe to share across users because the roster is read
# under the API key (identical for every viewer) and holds names only.
_cache: dict[str, Any] = {"date": None, "until": 0.0, "people": []}
_lock = asyncio.Lock()


def today_local() -> date:
    """Today's calendar date in Cleveland."""
    return datetime.now(_LOCAL).date()


def _parse(value: Any) -> Optional[date]:
    """A CRM date value (``YYYY-MM-DD``) as a date, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def is_birthday(value: Any, today: date) -> bool:
    """Whether the stored birthday falls on ``today`` (year ignored).

    A 29 February birthday is celebrated on 28 February in non-leap years — the
    alternative is greeting those members once every four years.
    """
    born = _parse(value)
    if born is None:
        return False
    if (born.month, born.day) == (today.month, today.day):
        return True
    return (
        (born.month, born.day) == (2, 29)
        and (today.month, today.day) == (2, 28)
        and not calendar.isleap(today.year)
    )


def _system_client(settings: Settings) -> Optional[EspoClient]:
    """The org-wide API-key CRM client (None in dry-run / keyless deploys).

    The birthday roster is deliberately NOT read as the signed-in user: it is an
    organization-wide announcement, so it must be the same for everyone and
    cacheable once for all viewers (the directory's mentor-availability
    precedent)."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


def _display_name(contact: dict[str, Any], profile: dict[str, Any]) -> str:
    name = (contact.get("name") or "").strip()
    if not name:
        name = " ".join(
            p for p in (contact.get("firstName"), contact.get("lastName")) if p
        ).strip()
    return name or (profile.get("name") or "").strip()


async def _profiles(client: EspoClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            MENTOR_PROFILE,
            select="id,name,mentorStatus,contactRecordId,assignedUserId,assignedUsersIds",
            max_size=_PAGE,
            offset=offset,
        )
        page = data.get("list", [])
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


async def _fetch(settings: Settings, today: date) -> list[dict[str, Any]]:
    """Today's birthday people, newest read from the CRM. Raises on failure."""
    client = _system_client(settings)
    if client is None:
        return []
    by_contact: dict[str, dict[str, Any]] = {}
    for profile in await _profiles(client):
        contact_id = profile.get("contactRecordId")
        if contact_id:
            by_contact.setdefault(contact_id, profile)
    if not by_contact:
        return []

    people: list[dict[str, Any]] = []
    ids = list(by_contact)
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        data = await client.list(
            CONTACT_ENTITY,
            where=[{"type": "in", "attribute": "id", "value": chunk}],
            select=f"id,name,firstName,lastName,{BIRTHDAY_FIELD}",
            max_size=_CHUNK,
        )
        for contact in data.get("list", []):
            if not is_birthday(contact.get(BIRTHDAY_FIELD), today):
                continue
            profile = by_contact.get(contact.get("id")) or {}
            name = _display_name(contact, profile)
            if not name:
                continue                      # nobody to name in the greeting
            people.append({
                "name": name,
                "firstName": (contact.get("firstName") or name.split(" ")[0]).strip(),
                "userIds": [
                    u for u in (
                        [profile.get("assignedUserId")]
                        + list(profile.get("assignedUsersIds") or [])
                    ) if u
                ],
                "announce": (profile.get("mentorStatus") or "") in ANNOUNCED_STATUSES,
                "profile": profile,
            })
    people.sort(key=lambda p: p["name"].lower())
    return people


async def todays_people(settings: Settings) -> list[dict[str, Any]]:
    """The cached roster of CBM members whose birthday is today. Never raises."""
    today = today_local()
    now = time.monotonic()
    if _cache["date"] == today and now < _cache["until"]:
        return _cache["people"]
    async with _lock:
        # Re-check: another request may have refreshed while we waited.
        now = time.monotonic()
        if _cache["date"] == today and now < _cache["until"]:
            return _cache["people"]
        try:
            people = await _fetch(settings, today)
        except Exception as exc:  # noqa: BLE001 — a greeting never blocks sign-in
            log.warning("birthday roster unavailable: %s", exc)
            people, until = [], now + _RETRY_SECONDS
        else:
            until = now + _TTL_SECONDS
            if people:
                log.info(
                    "birthdays today (%s): %s",
                    today.isoformat(), ", ".join(p["name"] for p in people),
                )
        _cache.update(date=today, until=until, people=people)
        return people


async def greetings_for(settings: Settings, user: dict[str, Any]) -> Optional[dict]:
    """What the portal should celebrate for this viewer, or None if nothing.

    ``own`` is the viewer's own birthday (matched by their login on their member
    record — membership over the whole collaborators list, never equality with
    the first entry); ``others`` are today's other CURRENT members, for the
    "wish them a happy birthday" announcement.
    """
    people = await todays_people(settings)
    if not people:
        return None
    user_id = user.get("userId")
    own = next((p for p in people if is_assigned_to(p["profile"], user_id)), None)
    others = [p for p in people if p is not own and p["announce"]]
    if own is None and not others:
        return None
    return {
        "date": today_local().isoformat(),
        "own": {"firstName": own["firstName"], "name": own["name"]} if own else None,
        "others": [{"firstName": p["firstName"], "name": p["name"]} for p in others],
    }


def reset_cache() -> None:
    """Drop the cached roster (tests; also a manual lever if one is ever needed)."""
    _cache.update(date=None, until=0.0, people=[])
