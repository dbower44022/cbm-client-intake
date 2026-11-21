"""Give a past public event one attendee, for the feedback surveys check on the
Business Mentors Association's system (phases 8 and 9, runbook step 4.2).

The CRM's own Create Event Registration form has no Event or Email field, so
the registration is made here, under an Admin-type login: the event, the
address, the names, Attended, source Staff, registered now. Idempotent: a
registration for the same event and address is set to Attended instead of
made twice. Dry run by default::

    PYTHONPATH=. uv run python scripts/run_with_admin.py --env ~/.config/cbm-bma/bma.env \
        scripts/feedback_bma_attendee.py            # dry run
    ... scripts/feedback_bma_attendee.py --apply   # make it

Through the wrapper: ``./scripts/evaluation_bma.sh feedback-attendee``.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assignments.auth import login_token  # noqa: E402
from core.espo import EspoClient  # noqa: E402

EVENT_ID = "6af32c9779a91d451"          # Business Association Welcome, ended 11-17-26
EMAIL = "doug@dougbower.com"
FIRST, LAST = "Doug", "Bower"


async def main() -> int:
    apply = "--apply" in sys.argv
    base = (os.environ.get("ESPO_ADMIN_BASE") or "").rstrip("/")
    if "businessmentorsassociation" not in base:
        print("This script runs only against the Business Mentors Association's CRM.",
              file=sys.stderr)
        return 2
    name, token = await login_token(base, os.environ["ESPO_ADMIN_USER"],
                                    os.environ["ESPO_ADMIN_PASS"], 30)
    client = EspoClient.for_user_token(base, name, token)
    event = await client.get("CEvent", EVENT_ID, select="name,audience,dateEnd,status")
    print(f"CRM:   {base}\nEvent: {event.get('name')} (ended {event.get('dateEnd')} UTC, "
          f"audience {event.get('audience')})")
    found = await client.list("CEventRegistration", where=[
        {"type": "equals", "attribute": "eventId", "value": EVENT_ID},
        {"type": "equals", "attribute": "email", "value": EMAIL}],
        select="id,attendanceStatus", max_size=5)
    rows = found.get("list") or []
    if rows:
        row = rows[0]
        print(f"A registration for {EMAIL} exists ({row['id']}, {row.get('attendanceStatus')}).")
        if row.get("attendanceStatus") == "Attended":
            print("Nothing to do.")
            return 0
        if not apply:
            print("WOULD set it to Attended. Re-run with --apply.")
            return 0
        await client.update("CEventRegistration", row["id"], {"attendanceStatus": "Attended"})
        print("Set to Attended.")
        return 0
    payload = {
        "name": f"{FIRST} {LAST} — {event.get('name')}",
        "eventId": EVENT_ID, "email": EMAIL, "firstName": FIRST, "lastName": LAST,
        "attendanceStatus": "Attended", "registrationSource": "Staff",
        "registrationDate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not apply:
        print(f"WOULD create a registration for {EMAIL}, Attended. Re-run with --apply.")
        return 0
    made = await client.create("CEventRegistration", payload)
    back = await client.get("CEventRegistration", made["id"],
                            select="eventId,email,attendanceStatus")
    ok = back.get("eventId") == EVENT_ID and back.get("email") == EMAIL \
        and back.get("attendanceStatus") == "Attended"
    print(f"Created {made['id']}: read back {'OK' if ok else 'WRONG: ' + str(back)}.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
