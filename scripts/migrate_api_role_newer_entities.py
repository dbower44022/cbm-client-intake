"""Give the applications' CRM role the record types added after 31 August 2026.

The applications read and write the CRM as ``CustomAppAPIRole`` (the org-wide
API key). A chapter's CRM gets its roles from the roles standard captured on
31 August 2026, which predates six record types, so on the Business Mentors
Association's CRM the applications' key was refused every one of them
(``OPEN-ITEMS.md`` item 76, part 5: the worker logs ``list CProspect failed:
HTTP 403`` every pass). The grants below are crm-test's, read 11-12-26, which
is where every one of these features was reviewed.

**Idempotent and merge-only**, like ``migrate_client_assignment_role.py``: a
level already at or above the wanted one is left alone; nothing is lowered or
removed. Needs an Admin-type login; credentials come from the environment::

    # dry run (default)
    uv run --env-file ~/.config/cbm-bma/bma.env python scripts/migrate_api_role_newer_entities.py
    # apply
    uv run --env-file ~/.config/cbm-bma/bma.env python scripts/migrate_api_role_newer_entities.py --apply

A record type the CRM does not have is reported and skipped.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assignments.auth import login_token  # noqa: E402
from core.espo import EspoClient  # noqa: E402

ROLE = "CustomAppAPIRole"

#: (scope, {action: level}) — crm-test's CustomAppAPIRole, read 11-12-26.
GRANTS: list[tuple[str, dict[str, str]]] = [
    ("CProspect", {"create": "yes", "read": "all", "edit": "all", "delete": "all", "stream": "no"}),
    ("COutreachCampaign", {"create": "no", "read": "all", "edit": "all", "delete": "no", "stream": "no"}),
    ("COutreachTouch", {"create": "yes", "read": "all", "edit": "all", "delete": "no", "stream": "no"}),
    ("CEventPresenter", {"create": "no", "read": "all", "edit": "no", "delete": "no", "stream": "no"}),
    ("CPartnerAssociation", {"create": "yes", "read": "all", "edit": "all", "delete": "no", "stream": "no"}),
    ("CEnrichmentFinding", {"create": "yes", "read": "all", "edit": "all", "delete": "no", "stream": "no"}),
]

RANK: dict[str, int] = {"no": 0, "own": 1, "team": 2, "all": 3, "yes": 3}


def _rank(level: Any) -> int:
    return RANK.get(level, 0) if isinstance(level, str) else 0


def plan_scope(current: Any, wanted: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """The merged scope map and the changes it makes. Never lowers a level;
    an action not yet set at all is written even at 'no', so the scope is
    explicit rather than left to the CRM's default."""
    cur = dict(current) if isinstance(current, dict) else {}
    new = dict(cur)
    changes = []
    for action, level in wanted.items():
        if action in cur and _rank(cur[action]) >= _rank(level):
            continue
        new[action] = level
        changes.append(f"{action}: {cur.get(action, '(not set)')} -> {level}")
    return new, changes


async def main() -> int:
    apply = "--apply" in sys.argv
    base = (os.environ.get("ESPO_ADMIN_BASE") or "").rstrip("/")
    user = os.environ.get("ESPO_ADMIN_USER", "")
    password = os.environ.get("ESPO_ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER, ESPO_ADMIN_PASS.", file=sys.stderr)
        return 2
    name, token = await login_token(base, user, password, 30)
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{user} is type={profile.get('type')} - role changes need an Admin-type account.",
              file=sys.stderr)
        return 2
    print(f"CRM:  {base}\nUser: {name}\nMode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")

    page = await client.list("Role", where=[{"type": "equals", "attribute": "name", "value": ROLE}],
                             select="id,name", max_size=5)
    rows = [r for r in page.get("list", []) if r.get("name") == ROLE]
    if not rows:
        print(f"! role {ROLE!r} does not exist on this CRM")
        return 1
    role = await client.get("Role", rows[0]["id"])
    data: dict[str, Any] = dict(role.get("data") or {})
    scopes = set((await client.metadata("scopes") or {}).keys())

    changed: list[str] = []
    for scope, wanted in GRANTS:
        if scope not in scopes:
            print(f"  - {scope}: not on this CRM - skipped")
            continue
        new, changes = plan_scope(data.get(scope), wanted)
        if not changes:
            print(f"  - {scope}: already as wanted")
            continue
        print(f"  {'set' if apply else 'WOULD set'} {scope}: {', '.join(changes)}")
        data[scope] = new
        changed.append(scope)

    if not changed:
        print("\nNothing to do.")
        return 0
    if not apply:
        print("\nDry run only. Re-run with --apply.")
        return 0

    await client.update("Role", role["id"], {"data": data})
    back = (await client.get("Role", role["id"])).get("data") or {}
    bad = [s for s in changed if plan_scope(back.get(s), dict(GRANTS)[s])[1]]
    resp = await client._request("POST", f"{client._base}/Admin/rebuild", op="rebuild", json_body={})
    print(f"\nread back: {'OK' if not bad else 'MISSING ' + ', '.join(bad)}; rebuild HTTP {resp.status_code}")
    return 1 if bad or resp.status_code >= 300 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
