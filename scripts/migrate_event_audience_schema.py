"""Apply the event audience + display-time schema (Track F, F2 + F3).

Reads ``scripts/plans/cevent-audience-display.json`` — the single definition of
the change, the same file the CRM-changes skill's applier takes — and applies
its ``fields`` and ``enumOptions`` sections only. **Idempotent**: a field that
exists is left alone and an option already offered is not re-added, so it is
safe to re-run and every system it runs on ends with the same schema. It never
removes or renames anything.

Why a script of its own: the skill's applier lives under ``.claude/``, which is
not tracked and so is not in the deployed image, while production's schema
changes run from inside the deployed web container. This file and the plan ship
in the image. Runbook: ``cevent-audience-display-crm-handoff.md``.

Inside a deployed web container (the administrator there is the provisioning
service account)::

    ESPO_ADMIN_BASE="$ESPO_BASE_URL" ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME" \\
    ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD" PYTHONPATH=/app \\
    python scripts/migrate_event_audience_schema.py            # dry run
    ... python scripts/migrate_event_audience_schema.py --apply

Credentials come from the environment only (``ESPO_ADMIN_*`` or the older
``ADMIN_*`` spelling) and are never printed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from assignments.auth import login_token
from core.espo import EspoClient

PLAN = Path(__file__).resolve().parent / "plans" / "cevent-audience-display.json"


class Applier:
    def __init__(self, client: EspoClient, plan: dict[str, Any], apply: bool) -> None:
        self.c = client
        self.plan = plan
        self.apply = apply
        self.done: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

    async def _get_field(self, entity: str, name: str) -> dict[str, Any] | None:
        resp = await self.c._request(
            "GET", f"{self.c._base}/Admin/fieldManager/{entity}/{name}",
            op=f"read field {entity}.{name}",
        )
        return resp.json() if resp.status_code == 200 else None

    async def _write(self, method: str, path: str, payload: dict, what: str) -> None:
        if not self.apply:
            self.done.append(f"WOULD {what}")
            return
        resp = await self.c._request(
            method, f"{self.c._base}/{path}", op=what, json_body=payload
        )
        if resp.status_code < 300:
            self.done.append(what)
        else:
            self.failed.append(f"{what} -> HTTP {resp.status_code} {resp.text[:200]}")

    async def fields(self) -> None:
        # Every entity in this plan is custom, so names are stored as typed.
        for spec in self.plan.get("fields", []):
            spec = dict(spec)
            entity = spec.pop("entity")
            if await self._get_field(entity, spec["name"]) is not None:
                self.skipped.append(f"{entity}.{spec['name']} already exists")
                continue
            await self._write("POST", f"Admin/fieldManager/{entity}", spec,
                              f"create field {entity}.{spec['name']} ({spec['type']})")

    async def enum_options(self) -> None:
        for spec in self.plan.get("enumOptions", []):
            entity, name = spec["entity"], spec["field"]
            current = await self._get_field(entity, name)
            if current is None:
                self.failed.append(f"{entity}.{name} not found - cannot add options")
                continue
            options = list(current.get("options") or [])
            missing = [o for o in spec.get("add", []) if o not in options]
            if not missing:
                self.skipped.append(f"{entity}.{name} already offers {spec.get('add')}")
                continue
            # The field manager's update needs the COMPLETE definition; a
            # partial body is an HTTP 500 with no detail.
            await self._write("PUT", f"Admin/fieldManager/{entity}/{name}",
                              {**current, "options": options + missing},
                              f"add options {missing} to {entity}.{name}")

    async def rebuild(self) -> None:
        if not self.apply:
            return
        resp = await self.c._request(
            "POST", f"{self.c._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        (self.done if resp.status_code < 300 else self.failed).append(
            f"rebuild -> HTTP {resp.status_code}")

    async def verify(self) -> None:
        """Read every change back from metadata — the screen hides naming errors."""
        if not self.apply:
            return
        for spec in self.plan.get("fields", []):
            got = await self.c.metadata(f"entityDefs.{spec['entity']}.fields.{spec['name']}")
            ok = isinstance(got, dict) and got.get("type") == spec["type"]
            (self.done if ok else self.failed).append(
                f"verified {spec['entity']}.{spec['name']}" if ok
                else f"{spec['entity']}.{spec['name']} not readable after apply")
        for spec in self.plan.get("enumOptions", []):
            got = await self.c.metadata_enum_options(spec["entity"], spec["field"]) or []
            lacking = [o for o in spec.get("add", []) if o not in got]
            (self.failed if lacking else self.done).append(
                f"{spec['entity']}.{spec['field']} lacks {lacking} after apply" if lacking
                else f"verified {spec['entity']}.{spec['field']} options")


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
        print(f"{user} is type={profile.get('type')} - schema changes need an "
              f"Admin-type account.", file=sys.stderr)
        return 2

    plan = json.loads(PLAN.read_text())
    print(f"CRM:  {base}")
    print(f"User: {name} (type=admin)")
    print(f"Plan: {PLAN.name}")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")

    a = Applier(client, plan, apply)
    await a.fields()
    await a.enum_options()
    await a.rebuild()
    await a.verify()

    for title, rows in (("CHANGES", a.done), ("SKIPPED (already correct)", a.skipped),
                        ("FAILED", a.failed)):
        if rows:
            print(f"{title}:")
            for row in rows:
                print(f"  {'!' if title == 'FAILED' else '-'} {row}")
            print()
    if not apply:
        print("Dry run only. Re-run with --apply to make these changes.")
    return 1 if a.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
