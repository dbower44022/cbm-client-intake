"""Preview the portal birthday greetings locally — without changing any CRM data.

Runs the REAL application on your machine against the configured CRM
(``ESPO_BASE_URL``, crm-test by default), with one thing changed: the app's idea
of what **today** is. That makes it possible to see a birthday that is months
away, using real member records, without editing anyone's Contact.

    uv run python scripts/preview_birthday.py                  # today
    uv run python scripts/preview_birthday.py --date 11-07     # pretend it is 7 Nov
    uv run python scripts/preview_birthday.py --list           # just report, don't serve

Then open http://localhost:8010/ and sign in with a real CRM username and
password:

* signed in as the person whose birthday it is  -> "Happy Birthday, <name>!"
* signed in as anyone else                      -> "Wish <name> a Happy Birthday!"

Reads only: the roster read is a GET, and signing in writes nothing. The
overlay shows once per day per browser, so use a private window (or run
``localStorage.clear()`` in devtools) to see it again.

Full reference: birthday-greetings.md
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import sys

# Must be set before core.config is imported (real env beats the .env file).
os.environ["ESPO_DRY_RUN"] = "false"
os.environ.setdefault("SESSION_SECRET", "local-birthday-preview")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")   # plain http on localhost

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from portal import birthday  # noqa: E402


def _parse_date(raw: str) -> datetime.date:
    """``YYYY-MM-DD`` or ``MM-DD`` (this year)."""
    raw = raw.strip()
    for fmt, prefix in (("%Y-%m-%d", ""), ("%m-%d", f"{datetime.date.today().year}-")):
        try:
            return datetime.datetime.strptime(prefix + raw, "%Y-%m-%d").date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"not a date: {raw!r} (use YYYY-MM-DD or MM-DD)")


async def _report(settings, when: datetime.date) -> list[dict]:
    people = await birthday.todays_people(settings)
    print(f"\n  Pretending today is {when:%A %d %B %Y}.")
    if not people:
        print("  Nobody in this CRM has that birthday recorded — nothing will show.")
        print("  (Birthdays live on each member's Contact, field cBirthday; members")
        print("   set their own in My Mentor Profile -> Personal details.)")
        return people
    print("  Birthdays on that date:")
    for p in people:
        who = "announced to everyone" if p["announce"] else "greeted, but NOT announced (not a current member)"
        print(f"    - {p['name']} — {who}")
    return people


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", type=_parse_date, default=datetime.date.today(),
                    help="the date to pretend it is (YYYY-MM-DD or MM-DD)")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--list", action="store_true",
                    help="report whose birthday falls on that date, then exit")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.espo_api_key:
        print("No ESPO_API_KEY configured — the birthday roster cannot be read.")
        return 1

    birthday.today_local = lambda: args.date          # the one thing we change
    people = asyncio.run(_report(settings, args.date))
    if args.list:
        return 0

    print(f"\n  CRM:    {settings.espo_base_url}")
    print(f"  Portal: http://localhost:{args.port}/    (sign in with a real CRM login)")
    if people:
        first = people[0]
        print(f"    - as {first['name']}: their own greeting")
        print(f"    - as anyone else:   'Wish {first['name']} a Happy Birthday!'")
    print("  Nothing is written to the CRM. Ctrl-C to stop.\n")

    import uvicorn

    from main import app

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
