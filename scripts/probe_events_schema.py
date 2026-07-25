"""Read-only probe of the CEvent / CEventRegistration schema in EspoCRM.

Used to review the as-built entities against the Events & Webinars requirements
(see ``cevent-entities-crm-handoff.md``) and to re-verify after the CRM team
applies the change list. **Reads only** — it never writes.

Usage::

    # crm-test (reads ESPO_BASE_URL / ESPO_API_KEY from .env)
    PYTHONPATH=. uv run python scripts/probe_events_schema.py

    # production (override for one run; the key lives in the gitignored overlay)
    ESPO_BASE_URL=https://crm.clevelandbusinessmentors.org \
    ESPO_API_KEY=... \
    PYTHONPATH=. uv run python scripts/probe_events_schema.py

Exit code is 0 if both entities exist, 1 otherwise, so it can gate a build step.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

from core.config import Settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

ENTITIES = ("CEvent", "CEventRegistration")

# Fields the integration must be able to WRITE. A readOnly flag on any of these
# means EspoCRM will strip the value on save - see handoff section 4.
MUST_BE_WRITABLE = {
    "CEvent": ("registrationUrl", "recordingUrl", "virtualMeetingUrl"),
    "CEventRegistration": (
        "registrationDate",
        "registrationSource",
        "cancellationDate",
        "attendanceStatus",
    ),
}


def _describe(field_def: dict) -> str:
    ftype = field_def.get("type")
    bits = [str(ftype)]
    if ftype in ("enum", "multiEnum"):
        bits.append("options=" + json.dumps(field_def.get("options")))
    if field_def.get("maxLength"):
        bits.append(f"max={field_def['maxLength']}")
    if field_def.get("required"):
        bits.append("REQUIRED")
    if field_def.get("readOnly"):
        bits.append("READONLY")
    if field_def.get("default") is not None:
        bits.append(f"default={field_def['default']!r}")
    return " ".join(bits)


async def main() -> int:
    settings = Settings()
    if not settings.espo_api_key:
        print("No ESPO_API_KEY available - nothing to probe.", file=sys.stderr)
        return 1

    client = EspoClient(base_url=settings.espo_base_url, api_key=settings.espo_api_key)
    print(f"CRM: {settings.espo_base_url}\n")

    scopes = await client.metadata("scopes")
    related = [e for e in sorted(scopes) if re.search(r"event|registr|webinar", e, re.I)]
    print(f"Event-ish entities present: {related or 'NONE'}\n")

    missing = [e for e in ENTITIES if e not in scopes]
    problems: list[str] = []

    for entity in ENTITIES:
        if entity not in scopes:
            print(f"=== {entity}: NOT PRESENT ===\n")
            problems.append(f"{entity} does not exist")
            continue

        scope = scopes[entity]
        print(
            f"=== {entity} === type={scope.get('type')} custom={scope.get('isCustom')} "
            f"stream={scope.get('stream')}"
        )
        defs = await client.metadata(f"entityDefs.{entity}")

        for name, field_def in sorted(defs.get("fields", {}).items()):
            print(f"  F {name:32s} {_describe(field_def)}")
            if field_def.get("readOnly") and name in MUST_BE_WRITABLE.get(entity, ()):
                flag = "required AND readOnly" if field_def.get("required") else "readOnly"
                problems.append(f"{entity}.{name} is {flag} - API writes will be stripped")

        for name, link_def in sorted(defs.get("links", {}).items()):
            print(
                f"  L {name:32s} {str(link_def.get('type')):16s} -> "
                f"{link_def.get('entity')} foreign={link_def.get('foreign')}"
            )

        # Record counts and shape - tells us whether the entity is already in use
        # for something else (CEvent doubles as the org calendar on crm-test).
        try:
            listing = await client.list(entity, max_size=200, order_by="createdAt", order="desc")
            rows = listing.get("list", [])
            print(f"  records: total={listing.get('total')}")
            if rows:
                for attr in ("eventType", "format", "status", "attendanceStatus", "topic"):
                    values = Counter(r.get(attr) for r in rows if attr in r)
                    if values:
                        print(f"    {attr}: {dict(values)}")
                print("    newest names:")
                for row in rows[:5]:
                    print(f"      - {row.get('name')}")
        except EspoError as exc:
            print(f"  records: not readable with this key ({exc})")
        print()

    if problems:
        print("PROBLEMS FOUND:")
        for problem in problems:
            print(f"  ! {problem}")
    else:
        print("No blocking schema problems found.")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
