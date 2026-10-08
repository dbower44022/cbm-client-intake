"""Grant the roles that presenters on events need (Track F, F4 — design D1).

Doug's ruling 10-08-26: the presenter reads and writes in Event Administration
run AS THE SIGNED-IN USER, so the CRM enforces the permission and records the
staff member as a new Contact's creator. The Marketing Admin Role held NO grant
on ``Contact`` or ``CMentorProfile`` (read on crm-test 10-08-26), so without
this a presenter could be neither searched for, copied from nor created.

Grants, from ``prds/events/CBM_Events_Presenters_Design.md`` § 10 D1:

* Marketing Admin Role — ``Contact`` create yes, read all (edit stays NO: adding
  someone as a presenter never changes what is stored about them);
  ``CMentorProfile`` read all; ``CEventPresenter`` create yes, read/edit/delete all.
* CustomAppAPIRole (the org-wide API key) — ``CEventPresenter`` read all, for the
  public and portal page reads.
* Marketing Admin Role — **Assignment Permission ``team``** (was not set). Found
  in the live pass 10-08-26: with it unset, ``POST Contact`` as a Marketing Admin
  answered ``403 Assignment failure: assigned user or team not allowed`` even
  with Contact create granted, because EspoCRM stamps the creator's team on a new
  record and then checks the role may assign it. The Mentor Role, which creates
  Contacts daily, carries ``team``; the API role needed the same lesson (#16).

**Idempotent and merge-only.** A level already at or above the wanted one is left
alone; nothing is ever lowered or removed. Needs an Admin-type login::

    PYTHONPATH=. uv run python .claude/skills/espo-crm-changes/scripts/run_with_admin.py \\
        scripts/migrate_presenter_roles.py            # dry run
    ... scripts/migrate_presenter_roles.py --apply    # apply

Order: crm-test first, then production at the Sunday 17:00 UTC slot from inside
the deployed container, then Boston with its next release.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assignments.auth import login_token  # noqa: E402
from core.espo import EspoClient  # noqa: E402

ROLE_SCOPE_GRANTS: list[tuple[str, str, dict[str, str]]] = [
    ("Marketing Admin Role", "Contact", {"create": "yes", "read": "all"}),
    ("Marketing Admin Role", "CMentorProfile", {"read": "all"}),
    ("Marketing Admin Role", "CEventPresenter",
     {"create": "yes", "read": "all", "edit": "all", "delete": "all"}),
    ("CustomAppAPIRole", "CEventPresenter", {"read": "all"}),
]

#: Role-level permissions (not per scope): (role name, permission, minimum level).
ROLE_PERMISSIONS: list[tuple[str, str, str]] = [
    ("Marketing Admin Role", "assignmentPermission", "team"),
]

# ``create`` is yes/no; the others are no/own/team/all. One ranking covers both.
LEVEL_RANK: dict[str, int] = {"no": 0, "not-set": 0, "own": 1, "team": 2, "all": 3, "yes": 3}


def _rank(level: Any) -> int:
    return LEVEL_RANK.get(level, 0) if isinstance(level, str) else 0


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
        print(f"{user} is type={profile.get('type')} - role changes need an Admin-type account.",
              file=sys.stderr)
        return 2
    print(f"CRM:  {base}")
    print(f"User: {name} (type={profile.get('type')})")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")

    # The entity must exist first (scripts/plans/cevent-presenters.json).
    meta = await client.metadata("entityDefs.CEventPresenter")
    if not (isinstance(meta, dict) and meta.get("fields")):
        print("CEventPresenter does not exist on this CRM - apply the plan first.", file=sys.stderr)
        return 2

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
                skipped.append(f"{role_name}: {scope}.{action} already '{current_map.get(action)}'")
                continue
            new_map[action] = level
            changes.append(f"{action}: {current_map.get(action, '(not set)')} -> {level}")
        if not changes:
            continue
        # A scope that was absent (no access at all) gets explicit 'no' for the
        # actions not granted, so the stored map is complete and readable.
        for action in ("create", "read", "edit", "delete", "stream"):
            new_map.setdefault(action, "no")
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
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{label} - {exc}")

    for role_name, permission, level in ROLE_PERMISSIONS:
        role = await _find_role(client, role_name)
        if role is None:
            failed.append(f"role '{role_name}' does not exist on this instance")
            continue
        current = role.get(permission)
        if _rank(current) >= _rank(level):
            skipped.append(f"{role_name}: {permission} already '{current}'")
            continue
        label = f"{role_name}: {permission} {current or '(not set)'} -> {level}"
        if not apply:
            done.append(f"WOULD set {label}")
            continue
        try:
            await client.update("Role", role["id"], {permission: level})
            back = await client.get("Role", role["id"])
            if _rank(back.get(permission)) < _rank(level):
                failed.append(f"{label} - read-back is '{back.get(permission)}'")
            else:
                done.append(f"set {label} - read back OK")
                touched = True
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{label} - {exc}")

    if touched:
        resp = await client._request(
            "POST", f"{client._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        (done if resp.status_code < 300 else failed).append(f"rebuild -> HTTP {resp.status_code}")
    elif not apply and done:
        done.append("WOULD rebuild")

    for title, rows in (("CHANGES", done), ("SKIPPED (already correct)", skipped), ("FAILED", failed)):
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
