"""Apply a written EspoCRM configuration change, idempotently, and prove it landed.

**The idea.** A change is described once, as a plan file, and that same file is
applied to crm-test and later to production. Two instances built from one plan
cannot drift from each other, which is the failure this project keeps paying for.
The plan is also the written definition of the correct end state — without one a
change can be admired but not verified.

**What it protects you from**, all of which have actually happened here:

* **Silent renaming.** EspoCRM rewrites names by three different rules, and the
  UI shows labels that hide the result. Give every name here **unprefixed**; this
  script computes what EspoCRM will really store and checks *that*.
* **Reversed relationships.** Got wrong four times through the Entity Manager
  dialog, whose two name boxes are inverted. The API has no inversion — ``link``
  is stored on ``entity``, ``linkForeign`` on ``entityForeign`` — and every link
  is read back afterwards to confirm which way it actually points.
* **A plan that moved between review and apply.** ``--expect`` refuses to run if
  the work is no longer the work you read.

**Why it lives under ``scripts/``.** The deployed image is built from the
repository, and ``.claude/`` is not tracked, so a script kept there never
reaches a container. Production's structural changes run from inside the
deployed web container (the only place its administrator credential
exists), so this file, ``espo_admin.py`` beside it and the plans under
``scripts/plans/`` ship in the image. The CRM-changes skill's copies are
shims that run these. Inside a container::

    export ESPO_ADMIN_BASE="$ESPO_BASE_URL"
    export ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME"
    export ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD"
    cd /app && PYTHONPATH=/app .venv/bin/python scripts/apply_crm_plan.py \
        scripts/plans/<plan>.json                                 # dry run
    ... scripts/plans/<plan>.json --apply --production --expect <fingerprint>

**Idempotent**: anything already correct is skipped, so a re-run is safe and an
interrupted run can simply be run again.

**Additive only.** It creates entities, fields and links, and adds enum options.
It never deletes or renames anything — deleting a link in EspoCRM leaves the
column and its data behind, so a mis-named recreate strands data invisibly and
reads exactly like data loss. Removals are a human decision, made deliberately.

Usage::

    # 1. Dry run (the default). Changes nothing; prints the plan and a fingerprint.
    PYTHONPATH=. uv run python scripts/apply_crm_plan.py plan.json

    # 2. Apply exactly the plan you just read.
    PYTHONPATH=. ... apply_crm_plan.py plan.json --apply --expect a1b2c3d4

Credentials come from ``ESPO_ADMIN_BASE`` / ``ESPO_ADMIN_USER`` /
``ESPO_ADMIN_PASS`` (or the older ``ADMIN_*`` spelling), or ``.env``. Structural
changes need an **Admin-type** account: see ``SETUP.md`` in this skill directory.

Exit codes::

    0  everything in the plan is now true on the instance
    1  something failed, or verification did not agree — details printed
    2  credential or usage problem; nothing was attempted
    3  could not be checked (transport failure) — state is UNKNOWN, not bad
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.espo import EspoClient, EspoError  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espo_admin import connect, credentials, load_env  # noqa: E402


# --- Naming -----------------------------------------------------------------
# EspoCRM's NameUtil::addCustomPrefix() is 'c' . ucfirst($name), applied by three
# different rules depending on what is being named. Everything below exists so
# that a name is never checked by eye.

def custom_prefixed(name: str) -> str:
    return "c" + name[0].upper() + name[1:] if name else name


def stored_entity_name(name: str) -> str:
    """Entities ALWAYS gain a leading C. Asking for 'CGrant' yields 'CCGrant',
    which is exactly what a handoff document reading "Name: CGrant" produced on
    crm-test in August 2026."""
    return "C" + name


class Applier:
    def __init__(self, client: EspoClient, plan: dict[str, Any], apply: bool) -> None:
        self.c = client
        self.plan = plan
        self.apply = apply
        self.actions: list[str] = []      # what will be / was changed
        self.skipped: list[str] = []      # already correct
        self.failed: list[str] = []
        self._custom: dict[str, bool] = {}
        self._new_entities = {
            stored_entity_name(e["name"]) for e in plan.get("entities", [])
        }

    # --- state reads --------------------------------------------------------

    async def _meta(self, key: str) -> Any:
        """Read a metadata key, tolerating one that does not exist.

        EspoCRM answers a missing key with **HTTP 200 and a completely empty
        body** — not ``null``, not ``{}`` (measured on crm-test 2026-08-27).
        ``core.espo.EspoClient.metadata`` calls ``resp.json()`` on that and
        raises a JSON decode error, which is not an ``EspoError`` and so passes
        straight through every ``except EspoError`` in the codebase. Since
        asking about things that may not exist yet is this script's whole job,
        it reads metadata itself.
        """
        resp = await self.c._request(
            "GET", f"{self.c._base}/Metadata", op=f"metadata {key}",
            params={"key": key},
        )
        if resp.status_code >= 400:
            raise EspoError(f"metadata {key} failed: HTTP {resp.status_code}")
        if not resp.content:
            return None
        return resp.json()

    async def _scope(self, entity: str) -> dict[str, Any]:
        return await self._meta(f"scopes.{entity}") or {}

    async def _exists(self, entity: str) -> bool:
        return bool(await self._scope(entity))

    async def _is_custom(self, entity: str) -> bool:
        """Custom scopes take names as typed; system scopes get a 'c' prefix.
        An entity this run is creating is custom by definition, which is what
        makes a first-run dry run readable instead of a wall of failures."""
        if entity in self._custom:
            return self._custom[entity]
        if entity in self._new_entities:
            self._custom[entity] = True
            return True
        scope = await self._scope(entity)
        self._custom[entity] = bool(scope.get("isCustom"))
        return self._custom[entity]

    async def stored_field(self, entity: str, name: str) -> str:
        return name if await self._is_custom(entity) else custom_prefixed(name)

    async def _pending(self, entity: str) -> bool:
        """True when this entity does not exist yet but this run creates it —
        so a dry run can describe the whole change rather than stopping at the
        first thing that isn't there yet."""
        return entity in self._new_entities and not await self._exists(entity)

    # --- writes -------------------------------------------------------------

    async def _write(self, method: str, path: str, body: dict, what: str) -> bool:
        if not self.apply:
            self.actions.append(what)
            return True
        resp = await self.c._request(
            method, f"{self.c._base}/{path}", op=what, json_body=body
        )
        if resp.status_code < 300:
            self.actions.append(what)
            return True
        self.failed.append(f"{what} -> HTTP {resp.status_code} {resp.text[:200]}")
        return False

    async def do_entities(self) -> None:
        for spec in self.plan.get("entities", []):
            spec = dict(spec)
            given = spec["name"]
            if given.startswith("C") and len(given) > 1 and given[1].isupper():
                self.failed.append(
                    f"entity name {given!r} looks already-prefixed — give it "
                    f"unprefixed, or EspoCRM will store 'C{given}'")
                continue
            actual = stored_entity_name(given)
            if await self._exists(actual):
                self.skipped.append(f"entity {actual} exists")
                continue
            await self._write(
                "POST", "EntityManager/action/createEntity", spec,
                f"create entity {actual} (from name '{given}', type "
                f"{spec.get('type', 'Base')})",
            )

    async def do_fields(self) -> None:
        for spec in self.plan.get("fields", []):
            spec = dict(spec)
            entity, given = spec.pop("entity"), spec["name"]
            if not (await self._exists(entity) or await self._pending(entity)):
                self.failed.append(
                    f"{entity} does not exist — cannot add field {given}")
                continue
            stored = await self.stored_field(entity, given)
            if await self._pending(entity):
                self.actions.append(
                    f"create field {entity}.{stored} ({spec.get('type')})")
                continue
            existing = await self._read_field(entity, stored)
            if existing is not None:
                self.skipped.append(f"field {entity}.{stored} exists")
                continue
            await self._write(
                "POST", f"Admin/fieldManager/{entity}", spec,
                f"create field {entity}.{stored} ({spec.get('type')})"
                + ("" if stored == given else f"  [typed '{given}']"),
            )

    async def _read_field(self, entity: str, stored: str) -> dict[str, Any] | None:
        resp = await self.c._request(
            "GET", f"{self.c._base}/Admin/fieldManager/{entity}/{stored}",
            op=f"read field {entity}.{stored}",
        )
        return resp.json() if resp.status_code == 200 else None

    async def do_links(self) -> None:
        for spec in self.plan.get("links", []):
            spec = dict(spec)
            near, far = spec["entity"], spec["entityForeign"]
            missing = [
                e for e in (near, far)
                if not (await self._exists(e) or await self._pending(e))
            ]
            if missing:
                self.failed.append(
                    f"{', '.join(missing)} does not exist — cannot create link "
                    f"{near}.{spec['link']}")
                continue
            stored_near = await self.stored_field(near, spec["link"])
            stored_far = await self.stored_field(far, spec["linkForeign"])
            what = (f"create link {near}.{stored_near} -> {far}.{stored_far} "
                    f"({spec['linkType']})")
            if await self._pending(near) or await self._pending(far):
                self.actions.append(what)
                continue
            links = await self._meta(f"entityDefs.{near}.links") or {}
            if stored_near in links:
                self.skipped.append(f"link {near}.{stored_near} exists")
                continue
            await self._write("POST", "EntityManager/action/createLink", spec, what)

    async def do_enum_options(self) -> None:
        """Adding an option is additive and safe. Removing one orphans stored
        data, so it is never done here."""
        for spec in self.plan.get("enumOptions", []):
            entity, given = spec["entity"], spec["field"]
            if not await self._exists(entity):
                self.failed.append(f"{entity} does not exist — cannot alter {given}")
                continue
            stored = await self.stored_field(entity, given)
            field = await self._read_field(entity, stored)
            if field is None:
                self.failed.append(f"field {entity}.{stored} not found")
                continue
            current = list(field.get("options") or [])
            wanted = [o for o in spec.get("add", []) if o not in current]
            if not wanted:
                self.skipped.append(
                    f"enum {entity}.{stored} already offers "
                    f"{', '.join(spec.get('add', [])) or '(nothing)'}")
                continue
            # The fieldManager PUT needs the COMPLETE definition: an options-only
            # body is a 500 (found adding CEventRegistration.registrationSource
            # "Portal", 2026-09-29; migrate_event_schema.py already merged).
            body: dict[str, Any] = {**field, "options": current + wanted}
            if spec.get("labels"):
                translated = dict(field.get("translatedOptions") or {})
                translated.update(spec["labels"])
                body["translatedOptions"] = translated
            await self._write(
                "PUT", f"Admin/fieldManager/{entity}/{stored}", body,
                f"add enum options to {entity}.{stored}: {', '.join(wanted)}",
            )

    async def rebuild(self) -> None:
        """EspoCRM caches metadata aggressively — a change that does not appear
        is usually a missed rebuild rather than a failed write."""
        if not self.apply:
            return
        resp = await self.c._request(
            "POST", f"{self.c._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        if resp.status_code >= 300:
            self.failed.append(f"rebuild -> HTTP {resp.status_code}")

    # --- verification -------------------------------------------------------

    async def verify(self) -> None:
        """Read every change back from the data.

        Not from the Entity Manager list view, which shows labels and hides
        exactly the naming errors this script exists to prevent. A reversed link
        is invisible in a success response — only the metadata shows it.
        """
        if not self.apply:
            return
        for spec in self.plan.get("entities", []):
            actual = stored_entity_name(spec["name"])
            if await self._exists(actual):
                self.actions.append(f"verified entity {actual}")
            else:
                self.failed.append(f"VERIFY entity {actual} is not present")
            if await self._exists("C" + actual):
                self.failed.append(
                    f"VERIFY '{'C' + actual}' also exists — a double prefix, "
                    f"which means a name was supplied already-prefixed somewhere")

        for spec in self.plan.get("fields", []):
            entity = spec["entity"]
            stored = await self.stored_field(entity, spec["name"])
            if await self._meta(f"entityDefs.{entity}.fields.{stored}"):
                self.actions.append(f"verified field {entity}.{stored}")
            else:
                self.failed.append(f"VERIFY field {entity}.{stored} is not present")

        for spec in self.plan.get("links", []):
            near, far = spec["entity"], spec["entityForeign"]
            stored_near = await self.stored_field(near, spec["link"])
            stored_far = await self.stored_field(far, spec["linkForeign"])
            near_def = await self._meta(
                f"entityDefs.{near}.links.{stored_near}") or {}
            far_def = await self._meta(
                f"entityDefs.{far}.links.{stored_far}") or {}
            if not near_def or not far_def:
                self.failed.append(
                    f"VERIFY link {near}.{stored_near}: "
                    f"near={'ok' if near_def else 'MISSING'}, "
                    f"far {far}.{stored_far}={'ok' if far_def else 'MISSING'}")
            elif near_def.get("entity") != far:
                self.failed.append(
                    f"VERIFY link {near}.{stored_near} points at "
                    f"{near_def.get('entity')}, expected {far} — the link was "
                    f"built the wrong way round")
            else:
                self.actions.append(
                    f"verified link {near}.{stored_near} <-> {far}.{stored_far}")

    # --- driving ------------------------------------------------------------

    async def run(self) -> None:
        await self.do_entities()
        if self.apply and self.plan.get("entities"):
            # Fields and links need the entities to be real, and createEntity's
            # metadata is not visible until a rebuild.
            await self.rebuild()
        await self.do_fields()
        await self.do_links()
        await self.do_enum_options()
        await self.rebuild()
        await self.verify()

    def fingerprint(self) -> str:
        """A hash of the work itself, not of the file. Cosmetic edits to the plan
        do not change it; a change in what would actually happen does — including
        someone else altering the CRM between your review and your apply."""
        planned = [a for a in self.actions if not a.startswith("verified")]
        blob = json.dumps(sorted(planned), ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


def report(app: Applier, base: str, profile: dict, args) -> int:
    if args.json:
        print(json.dumps({
            "crm": base,
            "user": profile.get("userName"),
            "mode": "apply" if args.apply else "dry-run",
            "fingerprint": app.fingerprint(),
            "actions": app.actions,
            "skipped": app.skipped,
            "failed": app.failed,
        }, indent=2))
        return 1 if app.failed else 0

    for title, rows, mark in (
        ("WOULD CHANGE" if not args.apply else "CHANGED", app.actions, "-"),
        ("ALREADY CORRECT", app.skipped, "="),
        ("FAILED", app.failed, "!"),
    ):
        if rows:
            print(f"{title}:")
            for row in rows:
                print(f"  {mark} {row}")
            print()

    if not app.actions and not app.failed:
        print("Nothing to do — the instance already matches this plan.\n")
    if not args.apply:
        print(f"Dry run only. Nothing changed.\nPlan fingerprint: "
              f"{app.fingerprint()}\n\nTo apply exactly this plan:\n"
              f"  ... apply_crm_plan.py {args.plan} --apply "
              f"--expect {app.fingerprint()}")
    elif not app.failed:
        print("Applied and verified against the CRM's own metadata.\n\n"
              "Still owed, and neither is optional:\n"
              "  1. Grant any new entity to the org-wide API key's role, then "
              "prove it\n     with a 200 from outside (SETUP.md, part 3).\n"
              "  2. Check it as a real non-admin in the relevant team. "
              "Administrators\n     bypass ACL entirely, so your own test proves "
              "nothing about staff.")
    return 1 if app.failed else 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="path to the plan JSON file")
    parser.add_argument("--apply", action="store_true",
                        help="make the changes (default is a dry run)")
    parser.add_argument("--expect", metavar="FINGERPRINT",
                        help="refuse to apply if the plan has moved since the "
                             "dry run printed this fingerprint")
    parser.add_argument("--production", action="store_true",
                        help="acknowledge that the target is not crm-test")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read plan {args.plan}: {exc}", file=sys.stderr)
        return 2

    env = load_env()
    base, _, _ = credentials(env)
    if args.apply and "crm-test" not in base and not args.production:
        print(
            f"Target is {base}, which is not crm-test.\n"
            "Changes go to crm-test first, always — it is the only place a "
            "mistake is\nrecoverable without a support call. Production goes at "
            "the Sunday 17:00 UTC\nslot, run by a person from inside the deployed "
            "container.\n\nIf that is where you are, pass --production.",
            file=sys.stderr,
        )
        return 2

    try:
        client, profile = await connect(env)
    except SystemExit as exc:
        return int(exc.code or 2)
    if profile.get("type") != "admin":
        print(f"{profile.get('userName')} is type={profile.get('type')}. "
              f"Structural changes need an Admin-type account — see SETUP.md.",
              file=sys.stderr)
        return 2

    if not args.json:
        print(f"CRM:  {base}")
        print(f"User: {profile.get('userName')} (type=admin)")
        print(f"Plan: {args.plan}  {plan.get('name', '')}")
        print(f"Mode: {'APPLY' if args.apply else 'DRY RUN — nothing will change'}\n")

    app = Applier(client, plan, apply=False)
    try:
        # Always resolve the plan against current state first, so --expect
        # compares like with like and the apply run knows what it is committing to.
        await app.run()
        if args.apply:
            if args.expect and app.fingerprint() != args.expect:
                print(f"Plan has moved: expected {args.expect}, now "
                      f"{app.fingerprint()}.\nNothing was changed. Re-run the dry "
                      f"run and read the new plan — either\nyour plan file "
                      f"changed, or someone else has altered this CRM.",
                      file=sys.stderr)
                return 2
            app = Applier(client, plan, apply=True)
            await app.run()
    except EspoError as exc:
        print(f"Could not complete: {exc}\nState is UNKNOWN, which is not the "
              f"same as bad — re-run the dry run to see where it got to.",
              file=sys.stderr)
        return 3

    return report(app, base, profile, args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
