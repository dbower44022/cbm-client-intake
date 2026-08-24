"""Build the grant schema (CGrant / CGrantDeliverable / CGrantReport) via the API.

Implements sections 3, 4 and 5 of ``cgrant-entities-crm-handoff.md``. Modelled
on ``scripts/migrate_event_schema.py``, which built the event schema on crm-test
in July — that run is why the API contract used here is known rather than
guessed.

**Why a script at all**: the Entity Manager's Create Link dialog puts the name
of the link that lands on the FOREIGN entity under the panel of the entity you
opened it from, which has caused a reversed link on this CRM four times. The API
has no such inversion — ``link`` is the link stored on ``entity`` and
``linkForeign`` the one stored on ``entityForeign``, full stop.

**Idempotent** — an entity, field or link that already exists is left alone — so
it is safe to re-run, and running it against production later produces exactly
the same schema as crm-test. That is the point: this project has been bitten
repeatedly by crm-test/prod drift.

Schema changes are admin-only in EspoCRM (the intake API key gets 403 on
``Admin/fieldManager``), so this needs an Admin-type account. Credentials come
from the environment and are never written to disk or logged::

    # dry run (default) - prints the plan, changes nothing
    PYTHONPATH=. ADMIN_BASE=https://crm-test.clevelandbusinessmentors.org \
    ADMIN_USER=... ADMIN_PASS=... uv run python scripts/migrate_grant_schema.py

    # apply
    ... uv run python scripts/migrate_grant_schema.py --apply

Deliberately NOT included, both because a script should not do them unasked:

* **deleting the mis-named ``CCGrant`` / ``CCGrantDeliverable`` /
  ``CCGrantReport`` entities** created on crm-test on 2026-08-23 (EspoCRM
  prepends the ``C`` itself, so the handoff's old "Name: CGrant" produced a
  double). Remove them by hand first — handoff §2 — or this script's entity
  creates will sit alongside them.
* **role grants** (handoff §7), which stay a UI step.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from assignments.auth import login_token
from core.espo import EspoClient

# --- The build list ---------------------------------------------------------
# NOTE: entity names are given WITHOUT the leading C. EspoCRM's
# NameUtil::addCustomPrefix() prepends it unconditionally (verified in source,
# and `customPrefixDisabled` is false on this instance), so "Grant" becomes
# "CGrant". Passing "CGrant" here would create "CCGrant".

NEW_ENTITIES: list[dict[str, Any]] = [
    {"name": "Grant", "type": "BasePlus",
     "labelSingular": "Grant", "labelPlural": "Grants", "stream": False},
    {"name": "GrantDeliverable", "type": "BasePlus",
     "labelSingular": "Grant Deliverable", "labelPlural": "Grant Deliverables",
     "stream": False},
    {"name": "GrantReport", "type": "BasePlus",
     "labelSingular": "Grant Report", "labelPlural": "Grant Reports",
     "stream": False},
]

# Field names are NOT prefixed, because these entities are custom
# (FieldManager::create prefixes only on non-custom scopes).
# (entity, name, definition)
NEW_FIELDS: list[tuple[str, str, dict[str, Any]]] = [
    # --- CGrant (handoff 4.1) ---
    ("CGrant", "awardNumber", {
        "type": "varchar", "maxLength": 50, "label": "Award number",
        "tooltipText": "The funder's own reference for the award."}),
    ("CGrant", "grantStatus", {
        "type": "enum", "label": "Status", "required": True, "default": "Applied",
        "options": ["Applied", "Awarded", "Active", "Reporting", "Closed",
                    "Declined", "Cancelled"],
        "tooltipText": "Declined and Cancelled are the soft delete - the grant "
                       "stays visible and stops counting. Nothing is ever deleted."}),
    ("CGrant", "awardAmount", {"type": "currency", "label": "Award amount"}),
    ("CGrant", "periodStart", {"type": "date", "label": "Period start"}),
    ("CGrant", "periodEnd", {"type": "date", "label": "Period end"}),
    ("CGrant", "programArea", {
        "type": "varchar", "maxLength": 100, "label": "Programme area"}),
    ("CGrant", "reportingFrequency", {
        "type": "enum", "label": "Reporting frequency",
        "options": ["", "Monthly", "Quarterly", "Semi-annual", "Annual",
                    "Final only", "Ad hoc"], "default": ""}),
    ("CGrant", "firstReportDue", {"type": "date", "label": "First report due"}),
    ("CGrant", "nextReportDue", {
        "type": "date", "label": "Next report due",
        "tooltipText": "Seeded from the first report due date and never "
                       "overwritten once set by hand."}),
    ("CGrant", "renewalDeadline", {
        "type": "date", "label": "Renewal deadline",
        "tooltipText": "When the next application is due - what keeps the "
                       "funding continuous."}),
    ("CGrant", "notes", {"type": "wysiwyg", "label": "Notes"}),

    # --- CGrantDeliverable (handoff 4.2) ---
    ("CGrantDeliverable", "deliverableType", {
        "type": "enum", "label": "Type", "required": True, "default": "Numeric",
        "options": ["Numeric", "Rate", "Percentage", "Milestone", "Narrative"],
        "tooltipText": "Drives the progress arithmetic. Narrative has no "
                       "percentage at all - a written answer is not a quantity."}),
    ("CGrantDeliverable", "targetValue", {"type": "float", "label": "Target"}),
    ("CGrantDeliverable", "unit", {
        "type": "varchar", "maxLength": 50, "label": "Unit",
        "tooltipText": "seminars / hours / clients - shown after the number."}),
    ("CGrantDeliverable", "ratingScaleMax", {
        "type": "float", "label": "Rating scale max", "default": 5}),
    ("CGrantDeliverable", "currentValue", {
        "type": "float", "label": "Progress to date"}),
    ("CGrantDeliverable", "currentNote", {
        "type": "text", "label": "Progress note",
        "tooltipText": "Where the current figure came from - what makes a "
                       "typed-in number defensible to a funder a year later."}),
    ("CGrantDeliverable", "dueBy", {"type": "date", "label": "Due by"}),
    ("CGrantDeliverable", "deliverableStatus", {
        "type": "enum", "label": "Status",
        "options": ["", "On track", "At risk", "Behind", "Met", "Not met"],
        "default": "",
        "tooltipText": "A stored value always beats the app's arithmetic."}),
    ("CGrantDeliverable", "measurementSource", {
        "type": "enum", "label": "Measured", "default": "Manual",
        "options": ["Manual", "Automatic"]}),
    ("CGrantDeliverable", "measureKey", {
        "type": "varchar", "maxLength": 100, "label": "Measure"}),
    ("CGrantDeliverable", "measurementNotes", {
        "type": "text", "label": "How it is measured"}),
    ("CGrantDeliverable", "sortOrder", {"type": "int", "label": "Order"}),

    # --- CGrantReport (handoff 4.3) ---
    ("CGrantReport", "periodStart", {"type": "date", "label": "Period start"}),
    ("CGrantReport", "periodEnd", {"type": "date", "label": "Period end"}),
    ("CGrantReport", "dueDate", {"type": "date", "label": "Due date"}),
    ("CGrantReport", "reportStatus", {
        "type": "enum", "label": "Status", "default": "Due",
        "options": ["Due", "Draft", "Submitted", "Accepted"]}),
    ("CGrantReport", "submittedDate", {"type": "date", "label": "Submitted"}),
    ("CGrantReport", "narrative", {"type": "wysiwyg", "label": "Narrative"}),
    ("CGrantReport", "results", {
        "type": "text", "label": "Results (JSON)",
        "tooltipText": "The frozen per-deliverable figures for the period. "
                       "Written once at submission and never recomputed - it is "
                       "what CBM told the funder. Do not hand-edit."}),
    ("CGrantReport", "gmailThreadId", {
        "type": "varchar", "maxLength": 100, "label": "Email thread"}),
    ("CGrantReport", "documentUrl", {"type": "url", "label": "Filed copy"}),
]

# Links - handoff section 5. In the API there is NO inversion: `link` is stored
# on `entity`, `linkForeign` on `entityForeign`. linkType uses the
# Create-Relationship dialog vocabulary ("manyToOne"), NOT metadata terms
# ("belongsTo"), which return HTTP 400.
NEW_LINKS: list[dict[str, Any]] = [
    {"entity": "CGrant", "link": "sponsorProfile", "linkType": "manyToOne",
     "entityForeign": "CSponsorProfile", "linkForeign": "grants",
     "label": "Funder", "labelForeign": "Grants"},

    {"entity": "CGrantDeliverable", "link": "grant", "linkType": "manyToOne",
     "entityForeign": "CGrant", "linkForeign": "deliverables",
     "label": "Grant", "labelForeign": "Deliverables"},

    {"entity": "CGrantReport", "link": "grant", "linkType": "manyToOne",
     "entityForeign": "CGrant", "linkForeign": "reports",
     "label": "Grant", "labelForeign": "Reports"},

    {"entity": "CContribution", "link": "grant", "linkType": "manyToOne",
     "entityForeign": "CGrant", "linkForeign": "payments",
     "label": "Grant", "labelForeign": "Payments"},

    {"entity": "CGrant", "link": "fundedEngagements", "linkType": "manyToMany",
     "entityForeign": "CEngagement", "linkForeign": "fundingGrants",
     "relationName": "grantEngagement",
     "label": "Funded Clients", "labelForeign": "Funding Grants"},

    {"entity": "CGrant", "link": "grantManager", "linkType": "manyToOne",
     "entityForeign": "CMentorProfile", "linkForeign": "managedGrants",
     "label": "Grant Manager", "labelForeign": "Managed Grants"},
]


class Migrator:
    def __init__(self, client: EspoClient, apply: bool) -> None:
        self.c = client
        self.apply = apply
        self.done: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

    async def _write(self, method: str, path: str, payload: dict, what: str) -> bool:
        if not self.apply:
            self.done.append(f"WOULD {what}")
            return True
        resp = await self.c._request(
            method, f"{self.c._base}/{path}", op=what, json_body=payload
        )
        if resp.status_code < 300:
            self.done.append(what)
            return True
        self.failed.append(f"{what} -> HTTP {resp.status_code} {resp.text[:200]}")
        return False

    async def _scope_exists(self, entity: str) -> bool:
        return bool(await self.c.metadata(f"scopes.{entity}"))

    async def _scope_ready(self, entity: str) -> bool:
        """Is this entity available to hang a field or link on?

        In a DRY RUN against a CRM that doesn't have the entities yet, one this
        same run would create counts as ready — otherwise the plan reads as 30
        failures when nothing is wrong, which would make the dry run useless
        exactly when it matters most (the first time anyone runs it).
        """
        if await self._scope_exists(entity):
            return True
        return not self.apply and entity in self._pending_entities

    @property
    def _pending_entities(self) -> set[str]:
        return {"C" + spec["name"] for spec in NEW_ENTITIES}

    async def _get_field(self, entity: str, name: str) -> dict[str, Any] | None:
        resp = await self.c._request(
            "GET", f"{self.c._base}/Admin/fieldManager/{entity}/{name}",
            op=f"read field {entity}.{name}",
        )
        return resp.json() if resp.status_code == 200 else None

    async def create_entities(self) -> None:
        for spec in NEW_ENTITIES:
            actual = "C" + spec["name"]          # what EspoCRM will really call it
            if await self._scope_exists(actual):
                self.skipped.append(f"{actual} already exists")
                continue
            await self._write(
                "POST", "EntityManager/action/createEntity", spec,
                f"create entity {actual} ({spec['type']}) from name '{spec['name']}'",
            )

    async def create_fields(self) -> None:
        for entity, name, definition in NEW_FIELDS:
            if not await self._scope_ready(entity):
                self.failed.append(f"{entity} does not exist - cannot add {name}")
                continue
            if entity in self._pending_entities and not await self._scope_exists(entity):
                self.done.append(f"WOULD create field {entity}.{name} "
                                 f"({definition['type']})")
                continue
            if await self._get_field(entity, name) is not None:
                self.skipped.append(f"{entity}.{name} already exists")
                continue
            await self._write(
                "POST", f"Admin/fieldManager/{entity}",
                {"name": name, **definition},
                f"create field {entity}.{name} ({definition['type']})",
            )

    async def create_links(self) -> None:
        for link in NEW_LINKS:
            for side in ("entity", "entityForeign"):
                if not await self._scope_ready(link[side]):
                    self.failed.append(
                        f"{link[side]} does not exist - cannot create "
                        f"{link['entity']}.{link['link']}")
                    break
            else:
                if not await self._scope_exists(link["entity"]):
                    self.done.append(
                        f"WOULD create link {link['entity']}.{link['link']} -> "
                        f"{link['entityForeign']}.{link['linkForeign']} "
                        f"({link['linkType']})")
                    continue
                defs = await self.c.metadata(f"entityDefs.{link['entity']}.links")
                if link["link"] in (defs or {}):
                    self.skipped.append(
                        f"{link['entity']}.{link['link']} link exists")
                    continue
                await self._write(
                    "POST", "EntityManager/action/createLink", link,
                    f"create link {link['entity']}.{link['link']} -> "
                    f"{link['entityForeign']}.{link['linkForeign']} "
                    f"({link['linkType']})",
                )

    async def rebuild(self) -> None:
        if not self.apply:
            self.done.append("WOULD rebuild")
            return
        resp = await self.c._request(
            "POST", f"{self.c._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        (self.done if resp.status_code < 300 else self.failed).append(
            f"rebuild -> HTTP {resp.status_code}"
        )

    async def verify(self) -> None:
        """Read the links back and confirm each one landed on the side intended.

        A reversed link is the failure this whole exercise exists to prevent,
        and it is invisible in a success response — only the metadata shows it.
        """
        for link in NEW_LINKS:
            if not self.apply:
                continue
            near = await self.c.metadata(f"entityDefs.{link['entity']}.links.{link['link']}")
            far = await self.c.metadata(
                f"entityDefs.{link['entityForeign']}.links.{link['linkForeign']}")
            if not near or not far:
                self.failed.append(
                    f"VERIFY {link['entity']}.{link['link']}: "
                    f"near={'ok' if near else 'MISSING'} "
                    f"far={link['entityForeign']}.{link['linkForeign']}="
                    f"{'ok' if far else 'MISSING'}")
                continue
            if near.get("entity") != link["entityForeign"]:
                self.failed.append(
                    f"VERIFY {link['entity']}.{link['link']} points at "
                    f"{near.get('entity')}, expected {link['entityForeign']}")
            else:
                self.done.append(
                    f"verified {link['entity']}.{link['link']} <-> "
                    f"{link['entityForeign']}.{link['linkForeign']}")


async def main() -> int:
    apply = "--apply" in sys.argv
    base = os.environ.get("ADMIN_BASE", "")
    user = os.environ.get("ADMIN_USER", "")
    password = os.environ.get("ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ADMIN_BASE, ADMIN_USER, ADMIN_PASS.", file=sys.stderr)
        return 2

    name, token = await login_token(base, user, password, 30)
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{user} is type={profile.get('type')} - schema changes need an "
              f"Admin-type account.", file=sys.stderr)
        return 2

    print(f"CRM:  {base}")
    print(f"User: {name} (type={profile.get('type')})")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")

    m = Migrator(client, apply)
    await m.create_entities()
    if apply:
        # Fields and links need the entities to be real, and createEntity's
        # metadata is not visible until a rebuild.
        await m.rebuild()
    await m.create_fields()
    await m.create_links()
    await m.rebuild()
    await m.verify()

    for title, rows in (("CHANGES", m.done), ("SKIPPED (already correct)", m.skipped),
                        ("FAILED", m.failed)):
        if rows:
            print(f"{title}:")
            for row in rows:
                print(f"  {'!' if title == 'FAILED' else '-'} {row}")
            print()

    if not apply:
        print("Dry run only. Re-run with --apply to make these changes.")
    return 1 if m.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
