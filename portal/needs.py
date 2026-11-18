"""The home page's Needs you list (HOME_V2, phase 3; prds/home-page-plan.md
§ 4.2, Doug's answers at the phase's first stop, 11-18-26, all eight as
recommended).

The rules live here, as plain functions over rows already read, so each kind
is tested on its own. The reads are in :func:`portal.router.home_needs`.

The kinds, most urgent first (answer 7):

1. **No contact** (red, the day count): an Active, Assigned or Pending
   Acceptance engagement whose last contact, else its assignment, is older
   than the threshold (``HOME_NO_CONTACT_DAYS``, default 21). On-Hold is
   left out (answer 6).
2. **Notes** (amber): a Completed session of the last 30 days with neither
   session notes nor next steps, and no meeting summary (answer 1).
3. **Email** (navy): a conversation My Email marks awaiting a reply whose
   last message is at least one working day old (answer 3).
4. **Summary** (navy): a Completed session of the last 14 days with a
   meeting summary and empty session notes (answer 2). Only the session
   notes count here: the note taker writes its action items into an empty
   next steps field, so next steps say nothing about a person's review.
5. **New** (navy): an engagement at Pending Acceptance, or assigned in the
   last 7 days (answer 5).
6. **Staff** (purple): each staff queue with items, after every mentoring
   row, largest count first (answer 7; ruling 3 is kept by the attention
   counts' own team gates).

Closing is left out until a planned end date exists (answer 4).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

#: Urgency, most urgent first (answer 7).
RANK = {"nocontact": 0, "notes": 1, "email": 2, "summary": 3, "new": 4, "staff": 5}
#: Each kind's chip colour and word (plan § 5.3). No contact's word is the
#: day count, set per row.
CHIP = {
    "nocontact": ("red", ""),
    "notes": ("amber", "Notes"),
    "email": ("navy", "Email"),
    "summary": ("navy", "Summary"),
    "new": ("navy", "New"),
    "staff": ("purple", "Staff"),
}
#: The statuses the no-contact rule watches (answer 6: never On-Hold).
NO_CONTACT_STATUSES = ("Active", "Assigned", "Pending Acceptance")
#: The statuses an engagement may be "new" in.
NEW_STATUSES = ("Active", "Assigned", "Pending Acceptance")
NOTES_DAYS = 30
SUMMARY_DAYS = 14
NEW_DAYS = 7
EMAIL_WORKING_DAYS = 1

CM = "/mentorsessions/"


def parse_stamp(value: Any) -> Optional[datetime]:
    """A CRM stamp ("2026-11-18 14:00:00", UTC) or date ("2026-11-18") as an
    aware UTC datetime; None for anything else."""
    if not value:
        return None
    s = str(value).strip().replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def html_empty(value: Any) -> bool:
    """True when a rich-text field holds no words: tags, non-breaking spaces
    and whitespace only."""
    text = re.sub(r"<[^>]+>|&nbsp;|&#160;", "", str(value or ""))
    return not text.strip()


def add_working_days(start: datetime, days: int) -> datetime:
    """``start`` moved forward by ``days`` weekdays (Saturday and Sunday are
    skipped), keeping the time of day."""
    out = start
    left = days
    while left > 0:
        out += timedelta(days=1)
        if out.weekday() < 5:
            left -= 1
    return out


def _record(rid: str, tab: Optional[str] = None) -> dict[str, str]:
    url = f"{CM}record/{rid}" + (f"?tab={tab}" if tab else "")
    return {"url": url, "target": f"cbm-rec-mentorsessions-{rid}"}


def _item(kind: str, name: str, reason: str, link: dict[str, str], *,
          age: float = 0.0, chip: Optional[str] = None) -> dict[str, Any]:
    tone, word = CHIP[kind]
    return {"kind": kind, "tone": tone, "chip": chip or word, "name": name,
            "reason": reason, "url": link["url"], "target": link["target"],
            "age": round(age, 3)}


def _days(now: datetime, then: datetime) -> float:
    return (now - then).total_seconds() / 86400


def no_contact_items(clients: Iterable[dict[str, Any]], now: datetime,
                     threshold: int) -> list[dict[str, Any]]:
    """``clients``: the home page's engagement rows (``id``, ``name``,
    ``status``, ``lastContact``, ``assignedDate``). A threshold of 0 or less
    switches the kind off."""
    if threshold <= 0:
        return []
    out = []
    for c in clients:
        if c.get("status") not in NO_CONTACT_STATUSES:
            continue
        last = parse_stamp(c.get("lastContact"))
        since = last or parse_stamp(c.get("assignedDate"))
        if not since:
            continue
        days = _days(now, since)
        if days <= threshold:
            continue
        n = int(days)
        reason = (f"No contact for {n} days" if last
                  else f"No contact since assigned {n} days ago")
        out.append(_item("nocontact", c["name"], reason, _record(c["id"]),
                         age=days, chip=f"{n} days"))
    return out


def new_items(clients: Iterable[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    out = []
    for c in clients:
        status = c.get("status")
        if status not in NEW_STATUSES:
            continue
        assigned = parse_stamp(c.get("assignedDate"))
        recent = assigned is not None and _days(now, assigned) <= NEW_DAYS
        if status == "Pending Acceptance":
            reason = "Assigned to you, waiting for you to accept"
        elif recent:
            reason = "Newly assigned to you"
        else:
            continue
        age = _days(now, assigned) if assigned else 0.0
        out.append(_item("new", c["name"], reason, _record(c["id"]), age=age))
    return out


def session_items(sessions: Iterable[dict[str, Any]], names: dict[str, str],
                  now: datetime, *, summary_field: Optional[str]) -> list[dict[str, Any]]:
    """``sessions``: Completed sessions of the member's engagements (the
    caller has kept only those), with ``engagementId``, ``name``,
    ``dateStart``, ``sessionNotes``, ``nextSteps`` and, where the CRM has it,
    the summary field. ``names``: engagement id → the name the page shows."""
    out = []
    for s in sessions:
        if s.get("status") not in (None, "Completed"):
            continue
        eid = s.get("engagementId")
        when = parse_stamp(s.get("dateStart"))
        if not eid or eid not in names or not when or when > now:
            continue
        days = _days(now, when)
        has_summary = bool(summary_field) and not html_empty(s.get(summary_field))
        notes_empty = html_empty(s.get("sessionNotes"))
        label = s.get("name") or "A session"
        held = when.strftime("%b %-d")
        if has_summary:
            if notes_empty and days <= SUMMARY_DAYS:
                out.append(_item("summary", names[eid],
                                 f"{label} ({held}): meeting summary to review",
                                 _record(eid, "sessions"), age=days))
        elif notes_empty and html_empty(s.get("nextSteps")) and days <= NOTES_DAYS:
            out.append(_item("notes", names[eid], f"{label} ({held}): no notes yet",
                             _record(eid, "sessions"), age=days))
    return out


def email_items(conversations: Iterable[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """My Email's own rows (``build_inbox``): awaiting a reply, and waiting
    at least one working day."""
    out = []
    for c in conversations:
        if not c.get("awaitingReply"):
            continue
        last = parse_stamp(c.get("lastMessageAt"))
        if not last or add_working_days(last, EMAIL_WORKING_DAYS) > now:
            continue
        records = c.get("records") or []
        name = (records[0].get("name") if records else "") or "A conversation"
        subject = (c.get("subject") or c.get("name") or "").strip()
        reason = "Waiting for your reply" + (f": {subject}" if subject else "")
        link = {"url": f"/myemail/?conversation={c['id']}", "target": "cbm-myemail"}
        out.append(_item("email", name, reason, link, age=_days(now, last)))
    return out


def staff_items(attention: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Today's attention counts (``GET /api/portal/attention`` items), one
    row per queue with items. The age slot carries the count, so the sort
    puts the largest queue first."""
    out = []
    for a in attention:
        n = int(a.get("count") or 0)
        if n <= 0:
            continue
        url = a.get("url") or "/"
        target = "cbm-" + url.strip("/").split("/")[0] if url.strip("/") else "_blank"
        label = a.get("label") or "Items awaiting processing"
        out.append(_item("staff", label, f"{n} waiting", {"url": url, "target": target},
                         age=float(n)))
    return out


def ordered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Most urgent kind first, then the oldest (for staff rows, the largest)
    first; the first row is marked urgent when it is a red one (plan § 5.2:
    the single most urgent row may carry the red tint)."""
    rows = sorted(items, key=lambda i: (RANK[i["kind"]], -i["age"], i["name"]))
    for i, r in enumerate(rows):
        r["urgent"] = i == 0 and r["tone"] == "red"
    return rows
