"""Apply the event partner-sponsorship schema (Phase A of the mailing-list and
event-sponsorship plan).

Reads ``scripts/plans/cevent-partner-sponsorship.json`` — the single definition
of the change, the same file the CRM-changes skill's applier takes — and applies
its ``fields`` and ``links`` sections. **Idempotent**: a field or link that
exists is left alone, so it is safe to re-run and every system it runs on ends
with the same schema. It never removes or renames anything: taking the old
single ``partnerHost`` link away is a hand step in the handoff, done afterwards.

Why a script of its own: the skill's applier lives under ``.claude/``, which is
not tracked and so is not in the deployed image, while production's schema
changes run from inside the deployed web container. This file and the plan ship
in the image. Runbook: ``cevent-partner-sponsorship-crm-handoff.md``.

Inside a deployed web container (the administrator there is the provisioning
service account)::

    ESPO_ADMIN_BASE="$ESPO_BASE_URL" ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME" \\
    ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD" PYTHONPATH=/app \\
    python scripts/migrate_event_sponsorship_schema.py            # dry run
    ... python scripts/migrate_event_sponsorship_schema.py --apply

``--carry-host`` additionally copies every event's existing ``partnerHost``
into the new many-to-many link (relate, idempotent), so nothing is lost when
the old link is removed by hand. Dry run lists what it would carry.

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
from core.espo import EspoClient, EspoError

PLAN = Path(__file__).resolve().parent / "plans" / "cevent-partner-sponsorship.json"
OLD_HOST_LINK = "partnerHost"


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

    async def links(self) -> None:
        # In the API there is no inversion: ``link`` is stored on ``entity`` and
        # ``linkForeign`` on ``entityForeign``. Both entities here are custom,
        # so neither name gains a prefix.
        for spec in self.plan.get("links", []):
            near, far = spec["entity"], spec["entityForeign"]
            existing = await self.c.metadata(f"entityDefs.{near}.links.{spec['link']}")
            if isinstance(existing, dict) and existing:
                if existing.get("entity") != far:
                    self.failed.append(
                        f"link {near}.{spec['link']} exists but points at "
                        f"{existing.get('entity')}, not {far} — stop and look")
                else:
                    self.skipped.append(f"link {near}.{spec['link']} already exists")
                continue
            await self._write(
                "POST", "EntityManager/action/createLink", dict(spec),
                f"create link {near}.{spec['link']} <-> {far}.{spec['linkForeign']} "
                f"({spec['linkType']}, relation {spec.get('relationName')})")

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
        for spec in self.plan.get("links", []):
            near, far = spec["entity"], spec["entityForeign"]
            a = await self.c.metadata(f"entityDefs.{near}.links.{spec['link']}") or {}
            b = await self.c.metadata(f"entityDefs.{far}.links.{spec['linkForeign']}") or {}
            ok = (a.get("entity") == far and a.get("foreign") == spec["linkForeign"]
                  and b.get("entity") == near and b.get("foreign") == spec["link"]
                  and a.get("type") == "hasMany" and b.get("type") == "hasMany")
            (self.done if ok else self.failed).append(
                f"verified link {near}.{spec['link']} <-> {far}.{spec['linkForeign']} "
                f"(relation {a.get('relationName')})" if ok
                else f"link {near}.{spec['link']} did not land as intended: "
                     f"{near} side {a}, {far} side {b}")

    async def carry_host(self) -> None:
        """Copy each event's old single partner host into the new link."""
        link = self.plan["links"][0]
        near, new_link = link["entity"], link["link"]
        if not await self.c.metadata(f"entityDefs.{near}.links.{OLD_HOST_LINK}"):
            self.skipped.append(f"{near}.{OLD_HOST_LINK} is already gone — nothing to carry")
            return
        offset, carried = 0, 0
        while True:
            try:
                page = await self.c.list(
                    near, select=f"id,name,{OLD_HOST_LINK}Id,{OLD_HOST_LINK}Name",
                    where=[{"type": "isNotNull", "attribute": f"{OLD_HOST_LINK}Id"}],
                    max_size=200, offset=offset,
                )
            except EspoError as exc:
                self.failed.append(f"could not list events with a {OLD_HOST_LINK}: {exc}")
                return
            rows = page.get("list", [])
            for ev in rows:
                host_id = ev.get(f"{OLD_HOST_LINK}Id")
                if not host_id:
                    continue
                what = (f"carry {ev.get('name')!r} host {ev.get(f'{OLD_HOST_LINK}Name')!r} "
                        f"into {near}.{new_link}")
                if not self.apply:
                    self.done.append(f"WOULD {what}")
                    carried += 1
                    continue
                try:
                    already = await self.c.list_related(
                        near, ev["id"], new_link, select="id", max_size=200)
                except EspoError:
                    already = {"list": []}
                if any(r.get("id") == host_id for r in already.get("list", [])):
                    self.skipped.append(f"{what} — already there")
                    continue
                try:
                    await self.c.relate(near, ev["id"], new_link, host_id)
                    self.done.append(what)
                    carried += 1
                except EspoError as exc:
                    self.failed.append(f"{what} -> {exc}")
            if len(rows) < 200:
                break
            offset += 200
        self.done.append(f"{carried} host value(s) {'would be ' if not self.apply else ''}carried")


async def main() -> int:
    apply = "--apply" in sys.argv
    carry = "--carry-host" in sys.argv
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
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}"
          f"{' + carry partnerHost values' if carry else ''}\n")

    a = Applier(client, plan, apply)
    await a.fields()
    await a.links()
    await a.rebuild()
    await a.verify()
    if carry and not a.failed:
        await a.carry_host()

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
