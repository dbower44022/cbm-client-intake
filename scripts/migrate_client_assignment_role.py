"""Grant the Client Assignment Role the User scope it needs to assign a mentor.

Assigning a mentor writes the mentor's login User into ``CEngagement.assignedUsers``
(and the same list on the client's Contact, CClientProfile and Account). EspoCRM's
link check (``Record/Access/LinkCheck``, identical in 9.3.4 and 10.0.6) refuses that
write unless the acting user can **read** every User being linked. The Client
Assignment Role - the only role attached to the Client Administration Team - grants
nothing on the User scope, so a member of that team and no other gets::

    HTTP 403  No foreign record access for link operation (CEngagement:assignedUsers)
    cannotRelateForbidden  foreignEntityType=User  action=read

Cleveland never saw it because every Client Administration Team member there also
sits on the Mentor Team or Mentor Administration Team, whose roles carry User read.
Lakeside's single-team rehearsal user was the first to hit it (2026-09-07). Doug's
ruling the same day: the role becomes self-sufficient - ``User: read all, edit own``,
the shape production's ``ClientMentorIntakeRole`` already has.

**Idempotent and merge-only.** A level already at or above the wanted one is left
alone; nothing is ever lowered or removed. Safe to re-run, and running it against
each instance in turn is what keeps them identical. Role changes are admin-only, so
this needs an Admin-type login. Credentials come from the environment (the
``espo-crm-changes`` skill's ``run_with_admin.py`` supplies them from ``.env``) and
are never written or logged::

    # dry run (default) - prints the plan, changes nothing
    PYTHONPATH=. uv run python .claude/skills/espo-crm-changes/scripts/run_with_admin.py \\
        scripts/migrate_client_assignment_role.py

    # apply
    ... scripts/migrate_client_assignment_role.py --apply

Order: Lakeside (where it was found), crm-test (the standard), then production at
the Sunday 17:00 UTC slot, run by a human from inside the deployed container.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from assignments.auth import login_token
from core.espo import EspoClient

# --- The change list -------------------------------------------------------
# (role name, scope, {action: minimum level}). Levels are ranked below; a grant
# is written only when the live level ranks lower than the wanted one.
ROLE_SCOPE_GRANTS: list[tuple[str, str, dict[str, str]]] = [
    ("Client Assignment Role", "User", {"read": "all", "edit": "own"}),
]

LEVEL_RANK: dict[str, int] = {"no": 0, "own": 1, "team": 2, "all": 3}


def _rank(level: Any) -> int:
    """Rank a stored level. Absent / not-set / False all rank as 'no'."""
    if isinstance(level, str):
        return LEVEL_RANK.get(level, 0)
    return 0


async def _find_role(client: EspoClient, name: str) -> dict[str, Any] | None:
    page = await client.list(
        "Role", where=[{"type": "equals", "attribute": "name", "value": name}],
        select="id,name", max_size=5,
    )
    for row in page.get("list", []):
        if row.get("name") == name:
            return await client.get("Role", row["id"])
    return None


async def main() -> int:
    apply = "--apply" in sys.argv
    base = (os.environ.get("ESPO_ADMIN_BASE") or os.environ.get("ADMIN_BASE", "")).rstrip("/")
    user = os.environ.get("ESPO_ADMIN_USER") or os.environ.get("ADMIN_USER", "")
    password = os.environ.get("ESPO_ADMIN_PASS") or os.environ.get("ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER, ESPO_ADMIN_PASS.", file=sys.stderr)
        return 2
    name, token = await login_token(base, user, password, 30)
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{user} is type={profile.get('type')} - role changes need an "
              f"Admin-type account.", file=sys.stderr)
        return 2
    print(f"CRM:  {base}")
    print(f"User: {name} (type={profile.get('type')})")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")

    done: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    touched = False

    for role_name, scope, wanted in ROLE_SCOPE_GRANTS:
        role = await _find_role(client, role_name)
        if role is None:
            failed.append(f"role '{role_name}' does not exist on this instance")
            continue
        data: dict[str, Any] = dict(role.get("data") or {})
        current = data.get(scope)
        current_map: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
        new_map = dict(current_map)
        changes: list[str] = []
        for action, level in wanted.items():
            if _rank(current_map.get(action)) >= _rank(level):
                skipped.append(f"{role_name}: {scope}.{action} already "
                               f"'{current_map.get(action)}' (>= '{level}')")
                continue
            new_map[action] = level
            changes.append(f"{action}: {current_map.get(action, '(not set)')} -> {level}")
        if not changes:
            continue
        label = f"{role_name}: {scope} {{{', '.join(changes)}}}"
        if not apply:
            done.append(f"WOULD set {label}")
            continue
        data[scope] = new_map
        try:
            await client.update("Role", role["id"], {"data": data})
            back = await client.get("Role", role["id"])
            stored = (back.get("data") or {}).get(scope) or {}
            missing = [a for a, lv in wanted.items() if _rank(stored.get(a)) < _rank(lv)]
            if missing:
                failed.append(f"{label} - read-back is missing {missing}: {stored}")
            else:
                done.append(f"set {label} - read back OK: {stored}")
                touched = True
        except Exception as exc:  # noqa: BLE001 - report, then continue
            failed.append(f"{label} - {exc}")

    # A role edit takes effect once the ACL cache is cleared; a rebuild does that
    # and is the proven call from the other migration scripts.
    if touched:
        resp = await client._request(
            "POST", f"{client._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        (done if resp.status_code < 300 else failed).append(
            f"rebuild -> HTTP {resp.status_code}"
        )
    elif not apply and done:
        done.append("WOULD rebuild")

    for title, rows in (("CHANGES", done), ("SKIPPED (already correct)", skipped),
                        ("FAILED", failed)):
        if rows:
            print(f"{title}:")
            for row in rows:
                print(f"  {'!' if title == 'FAILED' else '-'} {row}")
            print()
    if not apply:
        print("Dry run only. Re-run with --apply to make these changes.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
