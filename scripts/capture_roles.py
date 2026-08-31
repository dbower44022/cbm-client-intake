#!/usr/bin/env python3
"""Capture a live EspoCRM's roles, teams and their permission maps. READ-ONLY.

WHY THIS EXISTS
===============
The applications gate every screen on **teams** — seven of them, named in
``core/config.py``. They name **no role anywhere**, deliberately: a regular
user's own token cannot read its ``rolesNames``, so gating on roles was never an
option ([[crm-test-assignment-acl-fields]]).

But a team is an empty vessel. What a team actually *permits* is defined by the
roles attached to it, and **those definitions exist only inside the live CRMs**.
They are not in this repo, not derivable from the code, and are documented as
divergent between crm-test and production — role scopes especially. So the
network's configuration standard cannot be written until someone reads both,
lays them side by side, and rules which is correct where they differ.

Reading them is mechanical, which is this script. **Deciding which is right is a
ruling**, and it is Doug's. Producing the table now converts the single largest
unknown in the CRM-configuration phase into something rulable in an afternoon,
and it is the input the CRMBuilder requirements session (due 2026-09-19)
otherwise lacks.

WHY IT MUST RUN INSIDE A DEPLOYED CONTAINER
===========================================
The org-wide API key **cannot read roles** — probed read-only against crm-test
on 2026-08-24: ``Team`` returns HTTP 200 and ``Role`` returns **HTTP 403**. That
wall is real, and it is the reason the configuration stamp was put in a custom
entity rather than under admin Settings.

So this needs an Admin-type account, and those credentials
(``ESPO_PROVISION_USERNAME`` / ``ESPO_PROVISION_PASSWORD``) exist **only on the
deployed web component** — never on a laptop. Run it in the DigitalOcean app
console for each environment ([[do-app-console-scripting]]). That is also how
you avoid copying an admin password anywhere.

    # in the crm-test app console, then again in the production one
    .venv/bin/python scripts/capture_roles.py > /tmp/roles.json
    cat /tmp/roles.json

SAFETY
======
Every call is a GET. There is no write path in this file, and it refuses to run
if the account it logged in as is not Admin-type — not because a non-admin could
do damage, but because a non-admin's answer would be silently PARTIAL, and a
partial capture adjudicated as if it were complete is worse than no capture.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from core.admin_client import admin_client_factory  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.espo import EspoError, is_forbidden  # noqa: E402

# EspoCRM's own list ceiling. A maxSize above recordListMaxSizeLimit (200) is a
# 403 rather than a truncation, and inside a best-effort handler that reads as
# "no records" ([[espo-list-maxsize-403]]). Nothing here asks for more.
PAGE = 200


async def _fetch_all(client, entity: str) -> list[dict[str, Any]]:
    """Every record of ``entity``, paged at the CRM's own limit."""
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        envelope = await client.list(entity, max_size=PAGE, offset=offset)
        rows = (envelope or {}).get("list") or []
        out.extend(rows)
        total = (envelope or {}).get("total")
        offset += len(rows)
        if not rows or (isinstance(total, int) and offset >= total):
            break
    return out


async def capture() -> dict[str, Any]:
    settings = get_settings()
    factory = admin_client_factory(settings)
    if factory is None:
        raise SystemExit(
            "No admin credentials here. ESPO_PROVISION_USERNAME/_PASSWORD live on "
            "the deployed WEB component only — run this in the app console, not "
            "on a laptop. (Or the app is in dry-run.)"
        )

    client = await factory()

    # Refuse a partial capture. A non-admin CAN read some of this and the gaps
    # would not announce themselves — an adjudication built on a silently
    # incomplete table is the failure mode worth preventing.
    me = await client.app_user()
    user = (me or {}).get("user") or {}
    if user.get("type") != "admin":
        raise SystemExit(
            f"Logged in as type={user.get('type')!r}, not 'admin'. A non-admin's "
            "answer would be silently partial. Refusing."
        )

    result: dict[str, Any] = {
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "instance": {
            "baseUrl": settings.espo_base_url,
            "environment": settings.environment,
            "organization": settings.organization_name,
        },
        "capturedBy": user.get("userName"),
        "teams": [],
        "roles": [],
        "notes": [],
    }

    # --- Teams: the names the application actually gates on ----------------
    for team in await _fetch_all(client, "Team"):
        result["teams"].append({
            "id": team.get("id"),
            "name": team.get("name"),
            "rolesIds": team.get("rolesIds") or [],
            "rolesNames": team.get("rolesNames") or {},
        })

    # --- Roles: the definitions that make those teams mean anything --------
    # The list envelope carries only summary columns; `data` (per-entity
    # create/read/edit/delete levels) and `fieldData` (the field-level ACL that
    # silently strips writes — [[espo-field-acl-silently-strips-writes]]) come
    # back only on the full record, so each role is fetched individually.
    try:
        roles = await _fetch_all(client, "Role")
    except EspoError as exc:
        if is_forbidden(exc):
            raise SystemExit(
                "HTTP 403 listing Role even as an admin — that should not happen. "
                "Check the account really is Admin-type in the CRM."
            ) from exc
        raise

    for summary in roles:
        rid = summary.get("id")
        try:
            full = await client.get("Role", rid)
        except EspoError as exc:
            # Record the gap rather than dropping the role silently: a role
            # missing from the table would read as "this instance does not have
            # it", which is the absent-vs-forbidden confusion in another guise.
            result["notes"].append(
                f"Role {summary.get('name')!r} ({rid}) could not be read: {exc}"
            )
            continue
        result["roles"].append({
            "id": rid,
            "name": full.get("name"),
            # The two permission maps. These are the whole point of the capture.
            "data": full.get("data") or {},
            "fieldData": full.get("fieldData") or {},
            # The scope-wide defaults that apply where `data` says nothing.
            "assignmentPermission": full.get("assignmentPermission"),
            "userPermission": full.get("userPermission"),
            "portalPermission": full.get("portalPermission"),
            "groupEmailAccountPermission": full.get("groupEmailAccountPermission"),
            "exportPermission": full.get("exportPermission"),
            "massUpdatePermission": full.get("massUpdatePermission"),
            "followerManagementPermission": full.get("followerManagementPermission"),
            "auditPermission": full.get("auditPermission"),
            # Which teams and users this role reaches, so the team→role
            # attachment is captured from both directions. It has gone missing
            # twice in this project's history — and the record GET is NOT how
            # to read it: measured on both live CRMs 2026-08-31, GET Role/{id}
            # returns empty teamsIds/usersIds even where attachments exist
            # (crm-test's database holds 7). The relationship endpoint is the
            # truth. Best-effort with a note, never silently empty.
            "teamsIds": await _related_ids(client, rid, "teams", result["notes"]),
            "teamsNames": await _related_names(client, rid, "teams", result["notes"]),
            "usersIds": await _related_ids(client, rid, "users", result["notes"]),
        })

    result["counts"] = {
        "teams": len(result["teams"]),
        "roles": len(result["roles"]),
        "unreadableRoles": len(result["notes"]),
    }
    return result


async def _related_list(client, rid: str, link: str, notes: list) -> list:
    resp = await client._request(
        "GET", f"{client._base}/Role/{rid}/{link}",
        op=f"role {link}", params={"maxSize": 200},
    )
    if resp.status_code != 200:
        notes.append(f"Role {rid}: could not read {link} (HTTP {resp.status_code}) — "
                     f"attachments unknown, NOT known-empty")
        return []
    return resp.json().get("list") or []


async def _related_ids(client, rid: str, link: str, notes: list) -> list:
    return [x.get("id") for x in await _related_list(client, rid, link, notes)]


async def _related_names(client, rid: str, link: str, notes: list) -> dict:
    return {x.get("id"): x.get("name") for x in await _related_list(client, rid, link, notes)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Capture a live EspoCRM's roles and teams as JSON. Read-only."
    )
    ap.add_argument(
        "--indent", type=int, default=2,
        help="JSON indent; 0 for one compact line, which is easier to copy out "
             "of a web console (default: 2)",
    )
    args = ap.parse_args()

    captured = asyncio.run(capture())
    print(json.dumps(captured, indent=args.indent or None, sort_keys=True))

    counts = captured["counts"]
    print(
        f"\n# {counts['teams']} teams, {counts['roles']} roles captured from "
        f"{captured['instance']['baseUrl']} ({captured['instance']['environment']})",
        file=sys.stderr,
    )
    if counts["unreadableRoles"]:
        print(
            f"# WARNING: {counts['unreadableRoles']} role(s) could not be read — "
            "see `notes`. The capture is INCOMPLETE.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
