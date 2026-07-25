"""Apply the Events & Webinars schema change list to an EspoCRM instance.

Implements sections 2 and 3 of ``cevent-entities-crm-handoff.md`` against
``CEvent`` / ``CEventRegistration``. **Idempotent** - a field that already
exists is left alone, an enum option that is already present is not re-added -
so it is safe to re-run, and running it against production later produces
exactly the same schema as crm-test (which is the point: this project has been
bitten twice by crm-test/prod drift).

Schema changes are **admin-only** in EspoCRM (the intake API key gets 403 on
``Admin/fieldManager``), so this needs an Admin-type account. Credentials come
from the environment and are never written to disk or logged::

    # dry run (default) - prints the plan, changes nothing
    PYTHONPATH=. ADMIN_BASE=https://crm-test.clevelandbusinessmentors.org \
    ADMIN_USER=... ADMIN_PASS=... uv run python scripts/migrate_event_schema.py

    # apply
    ... uv run python scripts/migrate_event_schema.py --apply

Deliberately NOT included: the ``CEvent.topic`` vocabulary change (handoff
section 5 - an open decision), and anything destructive. The only non-additive
edits are clearing ``readOnly`` flags and removing one blank enum option that no
record uses.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from assignments.auth import login_token
from core.espo import EspoClient

# --- The change list -------------------------------------------------------

# New fields: (entity, name, definition)
NEW_FIELDS: list[tuple[str, str, dict[str, Any]]] = [
    # CEvent - handoff 2.1
    ("CEvent", "publishToWebsite", {
        "type": "bool", "default": False, "label": "Publish To Website",
        "tooltipText": "When on, this event appears on the public website. "
                       "Internal calendar entries must leave this off.",
    }),
    ("CEvent", "slug", {"type": "varchar", "maxLength": 100, "label": "Slug"}),
    ("CEvent", "zoomWebinarId", {
        "type": "varchar", "maxLength": 50, "label": "Zoom Webinar ID"}),
    ("CEvent", "registrationCloses", {
        "type": "datetime", "label": "Registration Closes"}),

    # CEventRegistration - handoff 3.1
    ("CEventRegistration", "email", {
        "type": "varchar", "maxLength": 255, "label": "Email",
        "tooltipText": "Plain varchar on purpose - a custom email-type field on "
                       "a custom entity binds to the primary address and stores "
                       "nothing.",
    }),
    ("CEventRegistration", "firstName", {
        "type": "varchar", "maxLength": 100, "label": "First Name"}),
    ("CEventRegistration", "lastName", {
        "type": "varchar", "maxLength": 100, "label": "Last Name"}),
    ("CEventRegistration", "joinTime", {"type": "datetime", "label": "Join Time"}),
    ("CEventRegistration", "leaveTime", {"type": "datetime", "label": "Leave Time"}),
    ("CEventRegistration", "minutesAttended", {
        "type": "int", "label": "Minutes Attended"}),
    ("CEventRegistration", "attendanceSource", {
        "type": "enum", "label": "Attendance Source",
        "options": ["", "Zoom Report", "Check-in", "Manual"], "default": "",
        "tooltipText": "How attendance was determined. 'Manual' is never "
                       "overwritten by an automatic Zoom pull.",
    }),
    ("CEventRegistration", "zoomRegistrantId", {
        "type": "varchar", "maxLength": 100, "label": "Zoom Registrant ID"}),
    ("CEventRegistration", "zoomJoinUrl", {
        "type": "url", "label": "Zoom Join URL",
        "tooltipText": "The per-registrant join link returned by Zoom.",
    }),
    ("CEventRegistration", "marketingOptIn", {
        "type": "bool", "default": False, "label": "Marketing Opt-In"}),
    ("CEventRegistration", "followUpsSent", {
        "type": "multiEnum", "label": "Follow-Ups Sent",
        "options": ["Recording", "No Show", "Mentor CTA", "Survey"],
    }),
    ("CEventRegistration", "unmatchedParticipant", {
        "type": "bool", "default": False, "label": "Unmatched Participant",
        "tooltipText": "A Zoom attendee who matched no registration; created "
                       "for review rather than dropped.",
    }),
]

# Enum options to ADD (never removing an option that records use)
ADD_OPTIONS: list[tuple[str, str, list[str]]] = [
    ("CEvent", "status", ["Cancelled"]),
    ("CEventRegistration", "attendanceStatus", ["Waitlisted"]),
    ("CEventRegistration", "registrationSource", ["Staff", "Import"]),
]

# Blank enum options to strip (verified unused by any record)
DROP_BLANK_OPTION: list[tuple[str, str]] = [("CEvent", "eventType")]

# readOnly flags to clear - handoff section 4
CLEAR_READONLY: list[tuple[str, str]] = [
    ("CEvent", "registrationUrl"),
    ("CEventRegistration", "registrationDate"),
    ("CEventRegistration", "registrationSource"),
    ("CEventRegistration", "cancellationDate"),
]

RELABEL: list[tuple[str, str, str]] = [("CEvent", "venueCapacity", "Capacity")]

# New link - handoff 2.4
NEW_LINKS: list[dict[str, Any]] = [
    {
        # linkType uses the Create-Relationship dialog vocabulary ("manyToOne"),
        # NOT metadata terms ("belongsTo") - the latter returns HTTP 400.
        "entity": "CEvent", "link": "partnerHost", "linkType": "manyToOne",
        "entityForeign": "CPartnerProfile", "linkForeign": "hostedEvents",
        "label": "Partner Host", "labelForeign": "Hosted Events",
    },
]


class Migrator:
    def __init__(self, client: EspoClient, apply: bool) -> None:
        self.c = client
        self.apply = apply
        self.done: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

    async def _get_field(self, entity: str, name: str) -> dict[str, Any] | None:
        resp = await self.c._request(
            "GET", f"{self.c._base}/Admin/fieldManager/{entity}/{name}",
            op=f"read field {entity}.{name}",
        )
        return resp.json() if resp.status_code == 200 else None

    async def _patch_field(
        self, entity: str, name: str, current: dict[str, Any],
        changes: dict[str, Any], what: str,
    ) -> bool:
        """Update a field definition.

        ``Admin/fieldManager`` PUT requires the **complete** definition - a
        partial body (just the changed key) returns HTTP 500 with no detail.
        Verified against EspoCRM 9.3.6, 2026-07-25. So merge onto what we read.
        """
        return await self._write(
            "PUT", f"Admin/fieldManager/{entity}/{name}", {**current, **changes}, what
        )

    async def _write(self, method: str, path: str, payload: dict, what: str) -> bool:
        if not self.apply:
            self.done.append(f"WOULD {what}")
            return True
        resp = await self.c._request(
            method, f"{self.c._base}/{path}", op=what, json_body=payload
        )
        if resp.status_code < 300:
            self.done.append(what)
            return True
        self.failed.append(f"{what} -> HTTP {resp.status_code} {resp.text[:200]}")
        return False

    async def create_fields(self) -> None:
        for entity, name, definition in NEW_FIELDS:
            if await self._get_field(entity, name) is not None:
                self.skipped.append(f"{entity}.{name} already exists")
                continue
            await self._write(
                "POST", f"Admin/fieldManager/{entity}",
                {"name": name, **definition},
                f"create field {entity}.{name} ({definition['type']})",
            )

    async def patch_fields(self) -> None:
        for entity, name, additions in ADD_OPTIONS:
            current = await self._get_field(entity, name)
            if current is None:
                self.failed.append(f"{entity}.{name} not found - cannot add options")
                continue
            options = list(current.get("options") or [])
            missing = [o for o in additions if o not in options]
            if not missing:
                self.skipped.append(f"{entity}.{name} already has {additions}")
                continue
            await self._patch_field(
                entity, name, current, {"options": options + missing},
                f"add options {missing} to {entity}.{name}",
            )

        for entity, name in DROP_BLANK_OPTION:
            current = await self._get_field(entity, name)
            if current is None:
                continue
            options = list(current.get("options") or [])
            if "" not in options:
                self.skipped.append(f"{entity}.{name} has no blank option")
                continue
            await self._patch_field(
                entity, name, current, {"options": [o for o in options if o != ""]},
                f"remove blank option from {entity}.{name}",
            )

        for entity, name in CLEAR_READONLY:
            current = await self._get_field(entity, name)
            if current is None:
                self.failed.append(f"{entity}.{name} not found - cannot clear readOnly")
                continue
            if not current.get("readOnly"):
                self.skipped.append(f"{entity}.{name} is already writable")
                continue
            await self._patch_field(
                entity, name, current, {"readOnly": False},
                f"clear readOnly on {entity}.{name}",
            )

        for entity, name, label in RELABEL:
            current = await self._get_field(entity, name)
            if current is None:
                continue
            if current.get("label") == label:
                self.skipped.append(f"{entity}.{name} already labelled '{label}'")
                continue
            await self._patch_field(
                entity, name, current, {"label": label},
                f"relabel {entity}.{name} -> '{label}'",
            )

    async def create_links(self) -> None:
        for link in NEW_LINKS:
            defs = await self.c.metadata(f"entityDefs.{link['entity']}.links")
            if link["link"] in (defs or {}):
                self.skipped.append(f"{link['entity']}.{link['link']} link exists")
                continue
            await self._write(
                "POST", "EntityManager/action/createLink", link,
                f"create link {link['entity']}.{link['link']} -> {link['entityForeign']}",
            )

    async def rebuild(self) -> None:
        if not self.apply:
            self.done.append("WOULD rebuild")
            return
        resp = await self.c._request(
            "POST", f"{self.c._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        (self.done if resp.status_code < 300 else self.failed).append(
            f"rebuild -> HTTP {resp.status_code}"
        )


async def main() -> int:
    apply = "--apply" in sys.argv
    base = os.environ.get("ADMIN_BASE", "")
    user = os.environ.get("ADMIN_USER", "")
    password = os.environ.get("ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ADMIN_BASE, ADMIN_USER, ADMIN_PASS.", file=sys.stderr)
        return 2

    name, token = await login_token(base, user, password, 30)
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{user} is type={profile.get('type')} - schema changes need an "
              f"Admin-type account.", file=sys.stderr)
        return 2

    print(f"CRM:  {base}")
    print(f"User: {name} (type={profile.get('type')})")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")

    m = Migrator(client, apply)
    await m.create_fields()
    await m.patch_fields()
    await m.create_links()
    await m.rebuild()

    for title, rows in (("CHANGES", m.done), ("SKIPPED (already correct)", m.skipped),
                        ("FAILED", m.failed)):
        if rows:
            print(f"{title}:")
            for row in rows:
                print(f"  {'!' if title == 'FAILED' else '-'} {row}")
            print()

    if not apply:
        print("Dry run only. Re-run with --apply to make these changes.")
    return 1 if m.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
