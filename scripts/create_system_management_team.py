"""Create the System Management Team — the activity page's team gate
(`system-management-team-crm-handoff.md`; Doug's ruling 11-06-26, option 1:
a new team, not a reuse of the System Administration Team or a rename of the
Data Integrity Team).

Dry run by default: reads the CRM and says what it would do. ``--apply``
creates the team (no roles, no members) and reads it back. Idempotent: a
team already holding the exact name is left alone. Runs as the
administrator account from ``.env`` (parsed, never sourced):

    PYTHONPATH=. uv run python scripts/run_with_admin.py \\
      scripts/create_system_management_team.py            # dry run
    PYTHONPATH=. uv run python scripts/run_with_admin.py \\
      scripts/create_system_management_team.py --apply

Another chapter's CRM: ``run_with_admin.py --env <file> …``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espo_admin import connect  # noqa: E402

TEAM = "System Management Team"
DESCRIPTION = ("Sees the activity page — every change by a person or in a date range, "
               "across every record — and later System Management functions. "
               "Grants no CRM records by itself.")


async def _find(client) -> list[dict]:
    page = await client.list("Team", select="id,name,description", max_size=10,
                             where=[{"type": "equals", "attribute": "name", "value": TEAM}])
    return list((page or {}).get("list") or [])


async def main(apply: bool) -> int:
    client, me = await connect(dict(os.environ))
    print(f"CRM: {client._base.rsplit('/api/', 1)[0]} as {me.get('userName')}")  # noqa: SLF001
    found = await _find(client)
    if found:
        print(f"Already there: {TEAM!r} ({len(found)} team). Nothing to do.")
        return 0
    if not apply:
        print(f"Dry run: would create {TEAM!r} with no roles and no members.")
        print("Run again with --apply to create it.")
        return 0
    await client.create("Team", {"name": TEAM, "description": DESCRIPTION})
    back = await _find(client)
    if len(back) != 1 or back[0].get("name") != TEAM:
        print(f"Read-back FAILED: found {[t.get('name') for t in back]!r}")
        return 1
    print(f"Created and read back: {TEAM!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--apply" in sys.argv[1:])))
