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


from events.email_templates import TEMPLATES  # noqa: E402  (the wording lives there)


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
