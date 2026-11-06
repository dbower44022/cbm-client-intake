"""Condition 7 — a login with no mentor profile opens Client Management or My
Mentor Profile (mentor login integrity plan § 4.2, step 4c).

Runs on the web component, which has the database and already sends alerts.
Behind ``INTEGRITY_SIGNIN_ALERT``. The page that found no profile answers at
once; this runs after the response (a FastAPI background task), so the person
never waits on it.

* **Confirmed under the key.** The page read the profiles as the person, whose
  role may not see their own profile; the key reads every profile (check C1).
  A profile found that way is no fault.
* **Once per login per day** (in ``LOGIN_INTEGRITY_TZ``): the fault key carries
  the day, and the store's open-key index refuses a second row.
* **Emailed at once** to the integrity recipients, only while
  ``INTEGRITY_DIGEST`` (the emailing switch) is on. The event is also listed
  in Mentor Administration's fault list, and the next daily run closes it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core import login_guard
from core.branding import abbr
from core.config import Settings, get_settings

log = logging.getLogger("cbm_intake.integrity")

APP_CLIENT_MANAGEMENT = "Client Management"
APP_MY_MENTOR_PROFILE = "My Mentor Profile"

#: (login id, day) pairs this process has already handled — checked before
#: the CRM read, so an unlinked login reloading the page all day costs one
#: read a day per process. The store's open-key index covers other processes.
_handled: set[tuple[str, str]] = set()


def _day(settings: Settings, now: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        return now.astimezone(ZoneInfo(settings.login_integrity_tz)).date().isoformat()
    except Exception:  # noqa: BLE001 — a bad timezone name: UTC days
        return now.date().isoformat()


async def report_no_profile(user: dict[str, Any], app: str, *,
                            settings: Optional[Settings] = None, reader: Any = None,
                            store: Any = None, send: Any = None,
                            now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Record (and, with the digest on, email) one no-profile sign-in. The
    recorded row, or None when nothing was recorded. Never raises."""
    settings = settings or get_settings()
    if not settings.integrity_signin_alert:
        return None
    try:
        if store is None:
            from .store import get_store

            store = get_store(settings)
        reader = reader or login_guard.reader()
        uid = user.get("userId") or ""
        if store is None or reader is None or not uid:
            return None
        # Only a login on a mentor team is expected to have a mentor profile;
        # an administrator or staff member without one opens the page freely.
        from .check import team_names

        if not set(user.get("teams") or []) & set(team_names(settings)):
            return None
        now = now or datetime.now(timezone.utc)
        day = _day(settings, now)
        if (uid, day) in _handled:
            return None
        _handled.add((uid, day))  # before the read: a failing read is not retried per load
        if await login_guard.profiles_carrying(reader, uid):
            return None  # the person's role hides it; the key sees a profile
        login = user.get("userName") or uid
        row = await store.record_event({
            "key": f"7:{uid}:{day}", "condition": 7, "mentors": [],
            "login": {"id": uid, "userName": login},
            "summary": f"{user.get('name') or login} ({login}) opened {app}, but no "
                       f"mentor profile carries this login.",
        }, now=now)
        if row is None:
            return None  # already reported today
        log.warning("login-integrity: no-profile sign-in user=%r app=%r", login, app)
        if settings.integrity_digest and settings.integrity_recipients:
            if send is None:
                from core.monitoring import _email_alert

                async def send(to: list[str], subject: str, text: str) -> None:
                    await _email_alert(settings, text, to=to, subject=subject,
                                       sender_name=f"{abbr()} Login Integrity")
            from .digest import faults_url

            await send(
                settings.integrity_recipients,
                f"[{abbr()} — {settings.environment}] A login with no mentor profile signed in",
                f"{row['summary']}\n\n"
                f"They see no mentor profile and no records. Link this login to their "
                f"mentor profile, or take it off the mentor teams if they are not a "
                f"mentor.\n\nFault list: {faults_url(settings)}\n"
                f"Environment: {settings.environment}.",
            )
            await store.mark_notified([row["id"]], now=now)
        return row
    except Exception as exc:  # noqa: BLE001 — an alert never breaks the page
        log.warning("login integrity: the no-profile sign-in report failed: %s", exc)
        return None
