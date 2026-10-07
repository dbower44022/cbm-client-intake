"""Let the action log's ``record`` link point at an event.

``CActionLog.record`` is a parent link whose entity list decides which record
types an action-log row may reference. Events were never on it, so the
reporting half of EVERY Event Administration action (Event Created / Updated /
Sponsors Updated, attendance, check-in) was refused with *400 Field validation
failure, field: record* and logged as a warning — found in the crm-test web
log on 2026-10-07 during the Phase B live pass. The stream-note half always
posted, so the record's history is intact; only the reporting table missed it.

This adds ``CEvent`` and ``CEventRegistration`` to that list. **Idempotent**: a
value already present is not re-added; nothing is ever removed. Dry run by
default. Runbook: ``OPEN-ITEMS.md`` → CRM prerequisites.

Inside a deployed web container (the administrator there is the provisioning
service account)::

    ESPO_ADMIN_BASE="$ESPO_BASE_URL" ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME" \\
    ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD" PYTHONPATH=/app \\
    python scripts/migrate_actionlog_record_entities.py            # dry run
    ... python scripts/migrate_actionlog_record_entities.py --apply

The field manager's update needs the COMPLETE field definition (a partial body
is an HTTP 500 with no detail — the lesson of 2026-09-29), so the script reads
the definition and writes it back whole with the longer list.
"""

from __future__ import annotations

import asyncio
import os
import sys

from assignments.auth import login_token
from core.espo import EspoClient

ENTITY = "CActionLog"
FIELD = "record"
ADD = ("CEvent", "CEventRegistration")


async def main() -> int:
    apply = "--apply" in sys.argv
    env = os.environ
    base = env.get("ESPO_ADMIN_BASE") or env.get("ADMIN_BASE") or ""
    user = env.get("ESPO_ADMIN_USER") or env.get("ADMIN_USER") or ""
    password = env.get("ESPO_ADMIN_PASS") or env.get("ADMIN_PASS") or ""
    if not (base and user and password):
        print("Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER, ESPO_ADMIN_PASS.", file=sys.stderr)
        return 2
    name, token = await login_token(base, user, password, 30)
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{user} is type={profile.get('type')} - this needs an Admin-type account.",
              file=sys.stderr)
        return 2

    print(f"CRM:  {base}")
    print(f"User: {name} (type=admin)")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")

    resp = await client._request(
        "GET", f"{client._base}/Admin/fieldManager/{ENTITY}/{FIELD}",
        op=f"read field {ENTITY}.{FIELD}",
    )
    if resp.status_code != 200:
        print(f"! could not read {ENTITY}.{FIELD}: HTTP {resp.status_code} — "
              f"is the action-log entity built on this CRM?")
        return 1
    field = resp.json()
    if field.get("type") != "linkParent":
        print(f"! {ENTITY}.{FIELD} is type {field.get('type')!r}, not linkParent — stop and look.")
        return 1
    current = list(field.get("entityList") or [])
    missing = [e for e in ADD if e not in current]
    print(f"entityList now: {', '.join(current)}")
    if not missing:
        print("SKIPPED: already lists every event entity.")
        return 0
    print(f"{'WOULD add' if not apply else 'adding'}: {', '.join(missing)}")
    if not apply:
        print("\nDry run only. Re-run with --apply to make this change.")
        return 0

    payload = {**field, "entityList": current + missing}
    resp = await client._request(
        "PUT", f"{client._base}/Admin/fieldManager/{ENTITY}/{FIELD}",
        op=f"update field {ENTITY}.{FIELD}", json_body=payload,
    )
    if resp.status_code >= 300:
        print(f"! update failed: HTTP {resp.status_code} {resp.text[:200]}")
        return 1
    resp = await client._request(
        "POST", f"{client._base}/Admin/rebuild", op="rebuild", json_body={}
    )
    print(f"rebuild -> HTTP {resp.status_code}")
    got = await client.metadata(f"entityDefs.{ENTITY}.fields.{FIELD}.entityList") or []
    lacking = [e for e in ADD if e not in got]
    if lacking:
        print(f"! after apply the list still lacks {lacking}: {got}")
        return 1
    print(f"verified entityList: {', '.join(got)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
