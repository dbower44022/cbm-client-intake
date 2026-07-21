"""Read-only audit: calendar invites sent to CBM members' PERSONAL addresses.

Before v0.122.0 the calendar hook invited every session attendee at their
Contact record's primary email. For CBM members (the assigned mentor +
co-mentors, who are default invitees) that is usually their PERSONAL address —
so the acting mentor received a self-invitation there, and accepting it
created a duplicate event copy (the 2026-07-20 customer report; deleting the
organizer copy then cancelled the meeting for the client too).

v0.122.0 fixes the hook (CBM members are invited at their ``cbmEmail`` ONLY).
This script measures the RETROACTIVE blast radius: every **upcoming Scheduled
session that already has a Google Calendar event**, listing any attendee who
is a CBM member whose Contact email differs from their CBM mailbox — i.e.
whose invitation went to a personal address under the old code.

It reads the CRM only — it never touches Google. To repair a flagged session
after v0.122.0 deploys: open it in the session tool and re-save with any
schedule-relevant change (or re-tick its attendees) — the hook re-patches the
event with the corrected invite list, which removes the personal-address
attendee (Google emails that address a cancellation, clearing the duplicate
copy) — or simply notify the affected mentors instead.

Usage (reads ESPO_BASE_URL / ESPO_API_KEY from the env / .env — crm-test by
default; for prod use the overlay-key one-liner from CLAUDE.md's "Form
dropdown lists" section). The API key needs CSession read (granted for the
transcript work; a 403 is reported readably):

    uv run python scripts/audit_calendar_invites.py                 # upcoming only
    uv run python scripts/audit_calendar_invites.py --include-past  # everything
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from sessions.config import DOMAINS  # noqa: E402
from sessions.service import cbm_member_email_map  # noqa: E402

SESSION = "CSession"
PAGE = 200


async def run(include_past: bool) -> int:
    settings = get_settings()
    base, key = settings.espo_base_url, settings.espo_api_key
    if not base or not key:
        print("ESPO_BASE_URL / ESPO_API_KEY must be set (see the module docstring).")
        return 2
    client = EspoClient(base, key)

    cfg_by_fk = {cfg.session_parent_fk: cfg for cfg in DOMAINS.values()}
    select = "id,name,status,dateStart,googleCalendarEventId," + ",".join(cfg_by_fk)

    where = [
        {"type": "equals", "attribute": "status", "value": "Scheduled"},
        {"type": "isNotNull", "attribute": "googleCalendarEventId"},
    ]
    if not include_past:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        where.append({"type": "after", "attribute": "dateStart", "value": now})

    sessions: list[dict] = []
    offset = 0
    try:
        while True:
            data = await client.list(
                SESSION, where=where, select=select, max_size=PAGE, offset=offset
            )
            rows = data.get("list", [])
            sessions.extend(rows)
            if len(rows) < PAGE:
                break
            offset += PAGE
    except EspoError as exc:
        print(f"Could not list sessions (does the API role have CSession read?): {exc}")
        return 2

    scope = "upcoming" if not include_past else "all"
    print(f"Auditing {len(sessions)} {scope} Scheduled session(s) with a "
          f"calendar event on {base}\n")

    affected = 0
    for sess in sessions:
        cfg = pid = None
        for fk, candidate in cfg_by_fk.items():
            if sess.get(fk):
                cfg, pid = candidate, sess[fk]
                break
        if cfg is None:
            print(f"⚠ session {sess.get('name')!r} ({sess['id']}): no parent link — skipped")
            continue
        try:
            atts = await client.list_related(
                SESSION, sess["id"], "sessionAttendees",
                select="name,emailAddress", max_size=PAGE,
            )
            members = await cbm_member_email_map(client, cfg, pid)
        except EspoError as exc:
            print(f"⚠ session {sess.get('name')!r} ({sess['id']}): read failed: {exc}")
            continue
        flagged = []
        for att in atts.get("list", []):
            cbm = members.get(str(att.get("id")))
            if cbm is None:
                continue  # a client contact — personal email is correct
            personal = (att.get("emailAddress") or "").strip().lower()
            if personal and personal != cbm:
                flagged.append((att.get("name"), personal, cbm or "(no cbmEmail!)"))
        if not flagged:
            continue
        affected += 1
        print(f"✗ {sess.get('dateStart')}  {sess.get('name')!r}  "
              f"[{cfg.slug} {pid}]  event {sess.get('googleCalendarEventId')}")
        for name, personal, cbm in flagged:
            print(f"    {name}: invited at PERSONAL {personal}  (CBM mailbox: {cbm})")

    print()
    if affected:
        print(f"{affected} session(s) have CBM members invited at a personal address.")
        print("Repair after v0.122.0 deploys: re-save each session with a "
              "schedule-relevant change (re-patches the event), or notify the mentors.")
    else:
        print("No sessions with personal-address CBM invites. ✔")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--include-past", action="store_true",
                    help="audit past Scheduled sessions too (default: upcoming only)")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.include_past)))
