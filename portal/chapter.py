"""The home page's At the chapter panel (HOME_V2, phase 4;
prds/home-page-plan.md § 4.1, Doug's eight answers at the phase's first
stop, 11-20-26, all as recommended).

The rules live here, as plain functions over rows already read; the reads
are in :func:`portal.router.home_chapter`.

* **The chapter's numbers for the year** (answers 1 and 2): from one read of
  the calendar year's Completed sessions, in the chapter's own time zone.
  *Clients served* is the engagements with at least one such session (a
  client with two engagements counts twice); *sessions held* is the
  sessions; *hours mentored* is their total length.
* **The member's own** (answer 4): the same three over the member's own
  engagements, owned and co-mentored, every status (a co-mentored session
  counts for both mentors).
* **Where you're needed** (answer 7): each Running call campaign naming one
  of the member's teams, with the calls still to make, counted the way the
  Calls tab counts them (``campaigns.calls.call_list``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

#: The chapter's own clock (the events programme's zone), for "this year".
from events.config import PUBLIC_TIMEZONE

CALLS_URL = "/campaigns/#calls"
CALLS_TARGET = "cbm-campaigns"


def year_start(now: datetime) -> tuple[int, str]:
    """The chapter's current calendar year and its first moment as a CRM UTC
    stamp ("YYYY-MM-DD HH:MM:SS")."""
    zone = ZoneInfo(PUBLIC_TIMEZONE)
    local = now.astimezone(zone)
    first = datetime(local.year, 1, 1, tzinfo=zone).astimezone(timezone.utc)
    return local.year, first.strftime("%Y-%m-%d %H:%M:%S")


def _stamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def session_facts(sessions: Iterable[dict[str, Any]]) -> list[tuple[str, float]]:
    """(engagement id, hours) per Completed session: all the figures need,
    and small enough to keep for every member. A session with no end, or an
    end before its start, counts as a session of no length."""
    out = []
    for s in sessions:
        eid = s.get("engagementId") or ""
        start, end = _stamp(s.get("dateStart")), _stamp(s.get("dateEnd"))
        hours = (end - start).total_seconds() / 3600 if start and end and end > start else 0.0
        out.append((eid, hours))
    return out


def figures(facts: Iterable[tuple[str, float]],
            engagements: Optional[set[str]] = None) -> dict[str, Any]:
    """Clients served, sessions held and hours mentored, over every session
    or, given ``engagements``, over those engagements' sessions only."""
    rows = [(e, h) for e, h in facts if engagements is None or e in engagements]
    return {
        "clients": len({e for e, _ in rows if e}),
        "sessions": len(rows),
        "hours": round(sum(h for _, h in rows)),
    }


def calls_to_make(touches: Iterable[dict[str, Any]], user_id: str) -> int:
    """The Planned calls a member would see on the Calls tab: every one, or,
    once any is assigned, those unassigned or assigned to the member."""
    planned = [t for t in touches if t.get("touchStatus") == "Planned"]
    if any(t.get("assignedUserId") for t in planned):
        planned = [t for t in planned
                   if not t.get("assignedUserId") or t.get("assignedUserId") == user_id]
    return len(planned)


def ask_row(campaign: dict[str, Any], calls: int) -> dict[str, Any]:
    return {
        "name": campaign.get("name") or "A call campaign",
        "reason": f"{calls} call{'' if calls == 1 else 's'} to make",
        "calls": calls,
        "url": CALLS_URL,
        "target": CALLS_TARGET,
    }
