"""Create the event email templates in EspoCRM, with default wording staff then edit.

The application sends every event email from an EspoCRM email template so the
wording is the staff's, not the code's (EV-60) — but a template that does not
exist is a send that refuses, and eight of them had to be written by hand
before any event email could go out (Track D, D1). This writes each one ONCE,
by its exact name, with plain default wording; a template that already exists
is never touched, so staff edits survive every re-run.

Usage::

    # dry run (default) — lists what would be created, changes nothing
    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/seed_event_templates.py

    # create the missing ones
    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/seed_event_templates.py --apply

Inside a deployed web container (production): export the three ``ESPO_ADMIN_*``
from ``ESPO_BASE_URL`` / ``ESPO_PROVISION_USERNAME`` / ``ESPO_PROVISION_PASSWORD``
first, as the CRM plan applier is run.

Placeholders: EspoCRM's own ``{Contact.firstName}`` style resolves at render;
the ``{{token}}`` style is this application's (``events/confirm.py``,
``TOKEN_NAMES``): ``{{firstName}}``, ``{{eventName}}``, ``{{when}}``,
``{{where}}``, ``{{joinBlock}}`` (a ready "Join online" paragraph, empty when
there is no link), ``{{joinUrl}}``, ``{{cancelUrl}}``, ``{{eventUrl}}``,
``{{recordingUrl}}``, ``{{orgName}}``, ``{{orgAbbr}}``.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

sys.path.insert(0, ".")

from scripts.espo_admin import connect, load_env  # noqa: E402


def _p(text: str) -> str:
    return f"<p>{text}</p>"


SIGN_OFF = _p("Warm regards,<br>{{orgName}}")

TEMPLATES: list[dict[str, str]] = [
    {
        "name": "EventConfirmation",
        "subject": "You're registered: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("You are registered for <strong>{{eventName}}</strong>."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            "{{joinBlock}}",
            _p("A calendar entry is attached. Details: <a href=\"{{eventUrl}}\">{{eventUrl}}</a>"),
            _p("Can't make it? <a href=\"{{cancelUrl}}\">Cancel your registration</a> so the place can go to someone else."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventWaitlisted",
        "subject": "You're on the waiting list: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("<strong>{{eventName}}</strong> is full, and you are on the waiting list."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            _p("If a place opens up we will email you straight away with everything you need."),
            _p("No longer interested? <a href=\"{{cancelUrl}}\">Leave the waiting list</a>."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventSeatOffered",
        "subject": "A place opened up: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("Good news: a place has opened up and you are now registered for <strong>{{eventName}}</strong>."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            "{{joinBlock}}",
            _p("A calendar entry is attached. Details: <a href=\"{{eventUrl}}\">{{eventUrl}}</a>"),
            _p("Can't make it after all? <a href=\"{{cancelUrl}}\">Cancel your registration</a>."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventReminder",
        "subject": "Tomorrow: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("A reminder that <strong>{{eventName}}</strong> is tomorrow."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            "{{joinBlock}}",
            _p("Can't make it? <a href=\"{{cancelUrl}}\">Cancel your registration</a> so the place can go to someone else."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventRecordingAvailable",
        "subject": "Recording available: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("The recording of <strong>{{eventName}}</strong> is now available:"),
            _p("<a href=\"{{recordingUrl}}\">{{recordingUrl}}</a>"),
            _p("You can find every recorded webinar at <a href=\"{{eventUrl}}\">{{eventUrl}}</a>."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventNoShow",
        "subject": "We missed you at {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("We missed you at <strong>{{eventName}}</strong>. Things come up — the recording, when there is one, will be on our site, and the next session is never far away."),
            _p("If you would like a hand with your business in the meantime, our mentors are free and happy to help."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventMentorCTA",
        "subject": "Thank you for joining {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("Thank you for joining <strong>{{eventName}}</strong>."),
            _p("{{orgName}} offers free, confidential mentoring to small business owners and nonprofit leaders. If you would like to work one-to-one with an experienced mentor, request one on our website and we will match you within a few days."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventSurvey",
        "subject": "Two minutes on {{eventName}}?",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("Thank you for attending <strong>{{eventName}}</strong>. Would you give us two minutes of feedback? Reply to this email with what worked and what we should change — every reply is read by the people who plan the next session."),
            SIGN_OFF,
        ]),
    },
]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="create the missing templates")
    args = parser.parse_args()
    env = load_env()
    client, profile = await connect(env)
    try:
        print(f"CRM:  {env.get('ESPO_ADMIN_BASE')}")
        print(f"User: {profile.get('userName')} (type={profile.get('type')})")
        print(f"Mode: {'APPLY' if args.apply else 'DRY RUN — nothing will change'}\n")
        existing: dict[str, dict[str, Any]] = {}
        page = await client.list("EmailTemplate", select="id,name", max_size=200)
        for row in page.get("list", []):
            existing[(row.get("name") or "").strip()] = row
        created = skipped = 0
        for spec in TEMPLATES:
            if spec["name"] in existing:
                print(f"  = {spec['name']}: exists (id {existing[spec['name']]['id']}) — untouched")
                skipped += 1
                continue
            if args.apply:
                row = await client.create("EmailTemplate", {
                    "name": spec["name"], "subject": spec["subject"],
                    "body": spec["body"], "isHtml": True, "oneOff": False,
                })
                print(f"  + {spec['name']}: created (id {row.get('id')})")
            else:
                print(f"  + {spec['name']}: would create")
            created += 1
        print(f"\n{created} {'created' if args.apply else 'to create'}, {skipped} already there.")
        if not args.apply and created:
            print("Dry run only. Re-run with --apply to create them.")
        return 0
    finally:
        closer = getattr(client, "aclose", None)
        if closer is not None:
            await closer()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
