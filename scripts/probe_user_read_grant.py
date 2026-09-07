"""Prove, as a real non-admin, that a team's role can read other users' User records.

This is the outside-in proof for the Client Assignment Role change
(``scripts/migrate_client_assignment_role.py``): assigning a mentor stamps the
mentor's login User into ``assignedUsers``, and EspoCRM's link check refuses that
write unless the acting user can READ every User being linked. An administrator
bypasses ACL entirely, so an admin test proves nothing - this script creates a
throwaway **regular** user whose ONLY team is the one under test, reads one other
user's record as them, and deletes the throwaway user again::

    HTTP 200  the role grants User read - the assignment write will pass
    HTTP 403  it does not - the assignment write will be refused

Dry-run by default (it only lists what it would do); ``--apply`` creates the
throwaway user, runs the check and deletes the user in one go, whatever the
outcome. The throwaway password is minted in-process and never printed. Needs an
Admin-type login from the environment (``ESPO_ADMIN_BASE`` / ``ESPO_ADMIN_USER``
/ ``ESPO_ADMIN_PASS``; the older ``ADMIN_*`` spelling is accepted) - the
``espo-crm-changes`` skill's ``run_with_admin.py`` supplies them from ``.env``
on a laptop; inside a deployed container they are the web component's
environment. Nothing is ever logged.

    PYTHONPATH=. uv run python .claude/skills/espo-crm-changes/scripts/run_with_admin.py \\
        scripts/probe_user_read_grant.py --team "Client Administration Team"

    ... scripts/probe_user_read_grant.py --team "Client Administration Team" --apply

The target read is the first active regular user found who is on the Mentor Team
and NOT on the team under test (override with ``--target-username``). The
throwaway user name defaults to ``acl.probe`` (override with ``--username``); if
a user of that name already exists the script refuses rather than reusing it.

EspoCRM soft-deletes: the throwaway row stays in the database with
``deleted=1`` (an administrator's GET still returns it) until the CRM's own
cleanup job or, on crm-test, ``reset_crm_sandbox.py purge-deleted`` removes it.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import secrets
import string
import sys

import httpx

from assignments.auth import login_token
from core.espo import EspoClient, EspoError


def _mint(n: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--team", required=True, help="the team whose role is under test")
    ap.add_argument("--username", default="acl.probe", help="throwaway user name (default acl.probe)")
    ap.add_argument("--target-username", default=None,
                    help="the user record to read; default: first active regular Mentor Team "
                         "member not on --team")
    ap.add_argument("--apply", action="store_true", help="create, check and delete the throwaway user")
    args = ap.parse_args()

    base = (os.environ.get("ESPO_ADMIN_BASE") or os.environ.get("ADMIN_BASE", "")).rstrip("/")
    user = os.environ.get("ESPO_ADMIN_USER") or os.environ.get("ADMIN_USER", "")
    password = os.environ.get("ESPO_ADMIN_PASS") or os.environ.get("ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER, ESPO_ADMIN_PASS.", file=sys.stderr)
        return 2
    name, token = await login_token(base, user, password, 30)
    admin = EspoClient.for_user_token(base, name, token)
    profile = (await admin.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{user} is type={profile.get('type')} - creating a user needs an Admin-type account.",
              file=sys.stderr)
        return 2
    print(f"CRM:  {base}")
    print(f"User: {name} (type={profile.get('type')})")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN - nothing will change'}\n")

    teams = {t["name"]: t["id"] for t in (await admin.list("Team", select="name", max_size=200)).get("list", [])}
    if args.team not in teams:
        print(f"team '{args.team}' does not exist on this instance", file=sys.stderr)
        return 1

    users = (await admin.list("User", select="userName,teamsNames,type,isActive", max_size=200)).get("list", [])
    if any(u.get("userName") == args.username for u in users):
        print(f"a user named '{args.username}' already exists - refusing to reuse it; pass --username",
              file=sys.stderr)
        return 1
    target = None
    for u in users:
        names = set((u.get("teamsNames") or {}).values())
        if args.target_username:
            if u.get("userName") == args.target_username:
                target = u
                break
        elif u.get("type") == "regular" and u.get("isActive") and "Mentor Team" in names and args.team not in names:
            target = u
            break
    if not target:
        print("no target user found - pass --target-username", file=sys.stderr)
        return 1
    print(f"Team under test: {args.team}")
    print(f"Target record:   User/{target['id']} ({target.get('userName')}, teams "
          f"{sorted((target.get('teamsNames') or {}).values())})")
    if not args.apply:
        print(f"\nWOULD create regular user '{args.username}' in only that team, read the target as them, "
              f"then delete '{args.username}'.\nDry run only. Re-run with --apply.")
        return 0

    pw = _mint()
    created = await admin.create("User", {
        "userName": args.username, "firstName": "ACL", "lastName": "Probe", "type": "regular",
        "isActive": True, "password": pw, "passwordConfirm": pw, "teamsIds": [teams[args.team]],
    })
    uid = created["id"]
    print(f"created User/{uid} ('{args.username}')")
    verdict = 1
    try:
        auth = base64.b64encode(f"{args.username}:{pw}".encode()).decode()
        async with httpx.AsyncClient(base_url=f"{base}/api/v1", timeout=30,
                                     headers={"Espo-Authorization": auth}) as probe:
            me = await probe.get("/App/user")
            if me.status_code != 200:
                print(f"! throwaway login failed: HTTP {me.status_code}")
            else:
                j = me.json()
                print(f"as '{args.username}': teams {sorted((j['user'].get('teamsNames') or {}).values())}, "
                      f"acl.User = {j.get('acl', {}).get('table', {}).get('User')}")
                r = await probe.get(f"/User/{target['id']}", params={"select": "userName"})
                print(f"GET User/{target['id']} as '{args.username}' -> HTTP {r.status_code}")
                if r.status_code == 200:
                    print("\nRESULT: PASS - the role grants User read; Assign will not be refused for this.")
                    verdict = 0
                elif r.status_code == 403:
                    print("\nRESULT: FAIL - no User read; Assign is refused (cannotRelateForbidden).")
                else:
                    print(f"\nRESULT: INCONCLUSIVE - unexpected HTTP {r.status_code}")
    finally:
        try:
            await admin.delete("User", uid)
            print(f"deleted User/{uid} ('{args.username}')")
        except EspoError as exc:
            print(f"! could not delete User/{uid}: {exc} - delete it by hand", file=sys.stderr)
    return verdict


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
