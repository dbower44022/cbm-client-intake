"""Role grants for feedback surveys — ``CSurveyResponse``.

prds/business-evaluation-plan.md § 5 and rulings BE31, BE32; decision 1 of
phases 8 and 9, approved by Doug 11-20-26 (option A); handoff
survey-response-crm-handoff.md:

* **CustomAppAPIRole** (the org-wide API key the application runs on) creates,
  reads and edits Survey Response records. The public survey page's submit,
  the worker's retry and sweep, the follow-up alerts and the Analytics totals
  all run under it.

* **Mentor Role**: read own only — no create, no edit. "Own", with Multiple
  Assigned Users, is every record carrying the mentor in ``assignedUsers``:
  a response about an engagement is stamped with the engagement's assigned
  users, so its mentor and co-mentors read it. Event feedback carries no
  stamp, so no mentor reads it (BE32).

* **Mentor Administration Role** and **Marketing Admin Role**: read all,
  edit all. Both teams act on follow-up alerts and mark a follow-up done
  (BE32); decision 1, option A: both read every response.

Idempotent and merge-only: a level already at or above the wanted one is left
alone, nothing is lowered or removed. Needs an Admin-type login::

    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/migrate_feedback_roles.py           # dry run
    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/migrate_feedback_roles.py --apply   # apply

Order: the Business Mentors Association's system first (the test system,
11-14-26), then production at the Sunday 17:00 UTC slot from inside the
deployed web container, then Boston with its release. Run after
``crm-plans/survey-response.json``.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assignments.auth import login_token  # noqa: E402
from core.espo import EspoClient  # noqa: E402

ENTITY = "CSurveyResponse"
#: (entity, role, wanted levels).
GRANTS: list[tuple[str, str, dict[str, str]]] = [
    (ENTITY, "CustomAppAPIRole", {"create": "yes", "read": "all", "edit": "all"}),
    (ENTITY, "Mentor Role", {"read": "own"}),
    (ENTITY, "Mentor Administration Role", {"read": "all", "edit": "all"}),
    (ENTITY, "Marketing Admin Role", {"read": "all", "edit": "all"}),
]
LEVEL_RANK: dict[str, int] = {"no": 0, "not-set": 0, "own": 1, "team": 2, "all": 3, "yes": 3}


def _rank(level: Any) -> int:
    return LEVEL_RANK.get(level, 0) if isinstance(level, str) else 0


async def _find_role(client: EspoClient, name: str) -> dict[str, Any] | None:
    page = await client.list("Role", where=[{"type": "equals", "attribute": "name", "value": name}],
                             select="id,name", max_size=5)
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
        print(f"{user} is type={profile.get('type')} - role changes need an Admin-type account.", file=sys.stderr)
        return 2
    print(f"CRM:  {base}\nUser: {name} (type={profile.get('type')})")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")
    meta = await client.metadata(f"entityDefs.{ENTITY}")
    if not (isinstance(meta, dict) and meta.get("fields")):
        print(f"{ENTITY} does not exist on this CRM - apply crm-plans/survey-response.json first.",
              file=sys.stderr)
        return 2
    present = {ENTITY}

    done: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    touched = False
    for entity, role_name, wanted in GRANTS:
        if entity not in present:
            continue
        role = await _find_role(client, role_name)
        if role is None:
            failed.append(f"role '{role_name}' does not exist on this instance")
            continue
        data: dict[str, Any] = dict(role.get("data") or {})
        current = dict(data.get(entity) or {}) if isinstance(data.get(entity), dict) else {}
        new_map = dict(current)
        changes = []
        for action, level in wanted.items():
            if _rank(current.get(action)) >= _rank(level):
                skipped.append(f"{role_name}: {entity}.{action} already '{current.get(action)}'")
                continue
            new_map[action] = level
            changes.append(f"{action}: {current.get(action, '(not set)')} -> {level}")
        if not changes:
            continue
        for action in ("create", "read", "edit", "delete", "stream"):
            new_map.setdefault(action, "no")
        label = f"{role_name}: {entity} {{{', '.join(changes)}}}"
        if not apply:
            done.append(f"WOULD set {label}")
            continue
        data[entity] = new_map
        try:
            await client.update("Role", role["id"], {"data": data})
            stored = ((await client.get("Role", role["id"])).get("data") or {}).get(entity) or {}
            short = [a for a, lv in wanted.items() if _rank(stored.get(a)) < _rank(lv)]
            if short:
                failed.append(f"{label} - read-back is missing {short}: {stored}")
            else:
                done.append(f"set {label} - read back OK: {stored}")
                touched = True
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{label} - {exc}")

    if touched:
        resp = await client._request("POST", f"{client._base}/Admin/rebuild", op="rebuild", json_body={})
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
