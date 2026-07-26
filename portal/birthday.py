"""Is today the signed-in mentor's birthday?

The portal (``/``) is where everyone signs in, so it is also where a mentor's
birthday greeting belongs: the answer computed here rides the portal payload
and the page shows a fireworks overlay before the user's screen.

The birthday lives on the mentor's linked **Contact** (``cBirthday`` — the
field ``/mentorprofile`` edits under "Personal details"), reached from their own
``CMentorProfile``. Everything is resolved server-side from the session's user
id (``resolve_manager_profile`` — a Python-side ``assignedUser`` match, never a
``where`` on ``assignedUserId``, which prod's field ACL forbids) and read AS THE
USER, so no record id is ever taken from the client and EspoCRM enforces the
caller's own ACL.

Entirely **best-effort**: no linked profile, no linked Contact, an empty
birthday, or any CRM failure simply means "no greeting" — signing in must never
depend on this.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import Any, Optional
from zoneinfo import ZoneInfo

from assignments.espo_user import client_for
from core.config import Settings
from sessions.service import resolve_manager_profile

log = logging.getLogger("cbm_intake.portal.birthday")

MENTOR_PROFILE = "CMentorProfile"
CONTACT_ENTITY = "Contact"
BIRTHDAY_FIELD = "cBirthday"

# CBM is a Cleveland organization: "today" is the local calendar day there, not
# the server's UTC day (which would start the greeting five hours early and end
# it five hours early too).
_LOCAL = ZoneInfo("America/New_York")


def today_local() -> date:
    """Today's calendar date in Cleveland."""
    from datetime import datetime

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
    alternative is greeting those mentors once every four years.
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


async def mentor_birthday(settings: Settings, user: dict[str, Any]) -> Optional[dict]:
    """``{"firstName": ..., "date": "YYYY-MM-DD"}`` when today is this user's
    birthday, else None. Never raises."""
    today = today_local()
    try:
        client = client_for(settings, user)
        profile_id = await resolve_manager_profile(client, user.get("userId"))
        if not profile_id:
            return None
        profile = await client.get(MENTOR_PROFILE, profile_id, select="contactRecordId")
        contact_id = profile.get("contactRecordId")
        if not contact_id:
            return None
        contact = await client.get(
            CONTACT_ENTITY, contact_id, select=f"firstName,{BIRTHDAY_FIELD}"
        )
    except Exception as exc:  # noqa: BLE001 — a greeting must never block sign-in
        log.warning("birthday check skipped for %s: %s", user.get("userName"), exc)
        return None
    if not is_birthday(contact.get(BIRTHDAY_FIELD), today):
        return None
    first = (contact.get("firstName") or "").strip()
    log.info("birthday greeting for %s", user.get("userName"))
    return {"firstName": first, "date": today.isoformat()}
