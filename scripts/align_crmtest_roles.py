"""Bring crm-test's roles to the ruled standard — the seven cells still owed.

**These are not new rulings.** On 2026-08-31 the two live CRMs' roles were
captured and laid side by side
(``prds/chapter-network/roles-standard/differences-2026-08-31.md``) and Doug
ruled **production is the standard**, with one sanctioned exception: the
application role's ``delete`` grants stay wider on crm-test, because staging has
to be able to clean up after a test. That document's closing section lists six
cells still owed a crm-test edit, plus one inside the sanctioned block that is
not part of the delete deviation and "should follow production too". Those seven
were never applied. Measured live 2026-09-13: 192 cells agree, 15 are the
sanctioned deviation, and exactly these seven still differ.

Four of the seven **reduce** what crm-test grants. That is the point rather than
a side effect: a sandbox more permissive than production is what lets a missing
production grant pass testing unseen, which is exactly how the Client
Assignment Role shipped unable to assign a mentor (v0.221.1, 2026-09-07).

Idempotent — a cell already at the standard is reported and skipped — so it is
safe to re-run, and re-running is how you check. ``role`` is a KEEP table in the
sandbox reset, so what this writes survives the nightly restore. Role changes
are admin-only, so this needs an Admin-type login; credentials come from the
environment (the ``espo-crm-changes`` skill's ``run_with_admin.py`` supplies
them from ``.env``) and are never logged::

    # dry run (default) - prints the plan, changes nothing
    PYTHONPATH=. uv run python .claude/skills/espo-crm-changes/scripts/run_with_admin.py \\
        scripts/align_crmtest_roles.py

    # apply
    ... scripts/align_crmtest_roles.py --apply

**crm-test only.** It refuses any other instance by name: production is already
the standard, so running this there could only move production away from itself.
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
# (role, kind, target, value, why). Kinds:
#   scope-remove  drop the scope key entirely -> EspoCRM reads it as "not set"
#   scope-enable  set the scope to True (a boolean, personal-UI surface)
#   scope-key     change ONE action inside a scope, leaving the others alone
#   permission    set a top-level permission field
CHANGES: list[tuple[str, str, Any, Any, str]] = [
    ("Mentor Role", "scope-remove", "EmailAccountScope", None,
     "personal mail-account surface; production does not grant it"),
    ("Standard User", "scope-remove", "ExternalAccount", None,
     "personal external-account surface; production does not grant it"),
    ("Marketing Admin Role", "scope-enable", "Activities", True,
     "production grants it; crm-test does not"),
    ("Sponsor Manager Role", "scope-remove", "CCommunication", None,
     "production does not grant funder managers the communication scope"),
    ("Sponsor Manager Role", "scope-remove", "CConversation", None,
     "production does not grant funder managers the conversation scope"),
    ("CustomAppAPIRole", "scope-key", ("CInformationRequest", "stream"), "no",
     "inside the sanctioned block but NOT part of the delete deviation, so it "
     "follows production; delete stays wider on purpose"),
    ("CustomAppAPIRole", "permission", "assignmentPermission", "not-set",
     "production leaves it unset"),
]

REQUIRED_HOST = "crm-test"


async def _find_role(client: EspoClient, name: str) -> dict[str, Any] | None:
    page = await client.list(
        "Role", where=[{"type": "equals", "attribute": "name", "value": name}],
        select="id,name", max_size=5,
    )
    for row in page.get("list", []):
        if row.get("name") == name:
            return await client.get("Role", row["id"])
    return None


def _plan_one(role: dict[str, Any], kind: str, target: Any, value: Any):
    """Return (needs_change, description, patch) without mutating ``role``."""
    data: dict[str, Any] = dict(role.get("data") or {})
    if kind == "scope-remove":
        if target not in data:
            return False, f"{target} already not set", None
        was = json.dumps(data.pop(target))
        return True, f"{target}: {was} -> (not set)", {"data": data}
    if kind == "scope-enable":
        if data.get(target) is True:
            return False, f"{target} already on", None
        was = json.dumps(data.get(target)) if target in data else "(not set)"
        data[target] = True
        return True, f"{target}: {was} -> true", {"data": data}
    if kind == "scope-key":
        scope, action = target
        current = data.get(scope)
        if not isinstance(current, dict):
            return False, f"{scope} is not a scope map here; skipped", None
        if current.get(action) == value:
            return False, f"{scope}.{action} already {value!r}", None
        merged = dict(current)
        was = merged.get(action)
        merged[action] = value
        data[scope] = merged
        return True, f"{scope}.{action}: {was!r} -> {value!r}", {"data": data}
    if kind == "permission":
        if role.get(target) == value:
            return False, f"{target} already {value!r}", None
        return True, f"{target}: {role.get(target)!r} -> {value!r}", {target: value}
    raise ValueError(f"unknown kind {kind!r}")


async def main() -> int:
    apply = "--apply" in sys.argv
    base = (os.environ.get("ESPO_ADMIN_BASE") or os.environ.get("ADMIN_BASE", "")).rstrip("/")
    user = os.environ.get("ESPO_ADMIN_USER") or os.environ.get("ADMIN_USER", "")
    password = os.environ.get("ESPO_ADMIN_PASS") or os.environ.get("ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER, ESPO_ADMIN_PASS.", file=sys.stderr)
        return 2
    if REQUIRED_HOST not in base.lower():
        print(f"REFUSING: {base} is not the crm-test sandbox. Production is already "
              f"the standard; this would move it away from itself.", file=sys.stderr)
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

    # Group by role so each role is read once and written once, even though two
    # of its cells may change: two writes would make the second overwrite the
    # first's `data` with a stale copy.
    for role_name in dict.fromkeys(c[0] for c in CHANGES):
        role = await _find_role(client, role_name)
        if role is None:
            failed.append(f"role '{role_name}' does not exist on this instance")
            continue
        patch: dict[str, Any] = {}
        labels: list[str] = []
        for _r, kind, target, value, why in (c for c in CHANGES if c[0] == role_name):
            staged = dict(role)
            staged.update(patch)  # so two cells on one role compose
            changed, desc, one = _plan_one(staged, kind, target, value)
            if not changed:
                skipped.append(f"{role_name}: {desc}")
                continue
            patch.update(one or {})
            labels.append(f"{desc}   [{why}]")
        if not patch:
            continue
        for label in labels:
            done.append(f"{'WOULD set ' if not apply else 'set '}{role_name}: {label}")
        if not apply:
            continue
        try:
            await client.update("Role", role["id"], patch)
            back = await client.get("Role", role["id"])
            bad = []
            for _r, kind, target, value, _why in (c for c in CHANGES if c[0] == role_name):
                still, _desc, _one = _plan_one(back, kind, target, value)
                if still:
                    bad.append(target)
            if bad:
                failed.append(f"{role_name}: read-back still differs on {bad}")
            else:
                touched = True
        except Exception as exc:  # noqa: BLE001 - report, then continue
            failed.append(f"{role_name}: {exc}")

    if touched:
        resp = await client._request(
            "POST", f"{client._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        (done if resp.status_code < 300 else failed).append(
            f"rebuild -> HTTP {resp.status_code}"
        )
    elif not apply and done:
        done.append("WOULD rebuild")

    for title, rows in (("CHANGES", done), ("SKIPPED (already at the standard)", skipped),
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
