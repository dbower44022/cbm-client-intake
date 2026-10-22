"""The training sandbox's demo campaign links — put back every night.

Campaign links live in the application's own database (ruling 31), and the
app half of the nightly sandbox reset empties that table (``core/sandbox_reset``).
The demo campaigns themselves are CRM records, restored each night from the
baseline by the CRM half. Without this module every demo campaign came back
each morning with no links, and every seeded postcard's card address
(``/c/<link>/<scan>``) answered 404.

So the reset puts a FIXED list of demo links back, right after it empties the
table (Doug's ruling 10-20-26, option 1). The codes are fixed so the training
guide's addresses and QR codes never change; a trainee's edits to a demo link
still vanish overnight, like every other edit on the sandbox.

The campaign names below are the ones ``scripts/sandbox/seed_outreach_data.py``
creates — it imports them from here, and ``tests/test_sandbox_demo.py`` fails if
a link names a campaign the seeder does not make. A demo campaign the CRM does
not hold (before the seeder has run, or a trainee renamed it) is skipped and
reported, never an error.

Refuses to run anywhere but crm-test, by the same CRM-address check as the reset.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoError

from . import config as cfg
from .tokens import ALPHABET, LINK_TOKEN_LENGTH, SCAN_TOKEN_LENGTH

log = logging.getLogger("cbm_intake.campaigns.sandbox_demo")

# --- the demo campaigns (the seeder creates exactly these names) -------------------
POSTCARD_DONE = "September 2026 filings — Postcard"
POSTCARD_DRAFT = "November 2026 filings — Postcard"
CALLS = "Fall follow-up calls"
EMAIL = "Marketing on a Shoestring — Email"
TEXT = "Webinar reminder — Text"
SOCIAL = "LinkedIn — Spring workshops"
DEMO_CAMPAIGNS: tuple[str, ...] = (POSTCARD_DONE, POSTCARD_DRAFT, CALLS, EMAIL, TEXT, SOCIAL)

#: The event the email campaign's link opens (a seeded event, by name).
EMAIL_EVENT = "Marketing on a Shoestring"


@dataclass(frozen=True)
class DemoLink:
    campaign: str
    name: str
    kind: str                       # cfg.DEST_*
    target: Optional[str] = None    # a form slug; for an event, the event's NAME
    token: str = ""


DEMO_LINKS: tuple[DemoLink, ...] = (
    DemoLink(POSTCARD_DONE, "Postcard landing page", cfg.DEST_LANDING, None, "sbxcard2"),
    DemoLink(EMAIL, "Webinar page", cfg.DEST_EVENT, EMAIL_EVENT, "sbxevnt7"),
    DemoLink(TEXT, "Request a mentor", cfg.DEST_FORM, "client-intake", "sbxtext8"),
    DemoLink(SOCIAL, "Workshops and webinars", cfg.DEST_PROGRAMME, None, "sbxweb23"),
    DemoLink(SOCIAL, "Request a mentor", cfg.DEST_FORM, "client-intake", "sbxmntr4"),
    DemoLink(SOCIAL, "Ask a question", cfg.DEST_FORM, "info-request", "sbxask56"),
)

#: The scan codes printed on the September postcard's five cards, in the order
#: the seeder creates its touches. A card's address is
#: ``/c/sbxcard2/<scan code>`` — the training guide names them.
DEMO_SCAN_TOKENS: tuple[str, ...] = (
    "sbxscan23456", "sbxscan23457", "sbxscan23458", "sbxscan23459", "sbxscan2345a",
)

CREATED_BY = "the sandbox reset"


def valid_token(token: str, length: int) -> bool:
    return len(token) == length and all(c in ALPHABET for c in token)


assert all(valid_token(l.token, LINK_TOKEN_LENGTH) for l in DEMO_LINKS)
assert all(valid_token(t, SCAN_TOKEN_LENGTH) for t in DEMO_SCAN_TOKENS)


async def _by_name(client, entity: str, name: str, select: str = "id,name") -> Optional[dict[str, Any]]:
    data = await client.list(entity, select=select, max_size=1,
                             where=[{"type": "equals", "attribute": "name", "value": name}])
    rows = data.get("list", [])
    return rows[0] if rows else None


async def plan_demo_links(store, client) -> list[dict[str, Any]]:
    """One entry per demo link: ``create`` (with the row to insert), or
    ``present`` / ``skip`` with the reason. Reads only."""
    plan: list[dict[str, Any]] = []
    campaigns: dict[str, Optional[dict[str, Any]]] = {}
    for link in DEMO_LINKS:
        entry: dict[str, Any] = {"token": link.token, "campaign": link.campaign, "name": link.name}
        if await store.get_link_by_token(link.token):
            plan.append({**entry, "action": "present"})
            continue
        if link.campaign not in campaigns:
            campaigns[link.campaign] = await _by_name(client, cfg.CAMPAIGN, link.campaign)
        campaign = campaigns[link.campaign]
        if not campaign:
            plan.append({**entry, "action": "skip", "reason": "the CRM holds no campaign of that name"})
            continue
        target, slug = link.target, None
        if link.kind == cfg.DEST_EVENT:
            event = await _by_name(client, cfg.EVENT, link.target or "", select="id,name,slug")
            if not event:
                plan.append({**entry, "action": "skip", "reason": f"the CRM holds no event {link.target!r}"})
                continue
            target, slug = event["id"], event.get("slug")
        plan.append({**entry, "action": "create", "row": {
            "campaign_id": campaign["id"], "name": link.name, "destination_kind": link.kind,
            "destination_target": target, "destination_slug": slug,
            "created_by": CREATED_BY, "token": link.token,
        }})
    return plan


def plan_text(plan: list[dict[str, Any]]) -> str:
    lines = []
    for e in plan:
        what = {"create": "would create", "present": "already present", "skip": "skipped"}[e["action"]]
        tail = f" — {e['reason']}" if e.get("reason") else ""
        lines.append(f"{e['token']}  {e['campaign']} / {e['name']}: {what}{tail}")
    counts = {a: sum(1 for e in plan if e["action"] == a) for a in ("create", "present", "skip")}
    lines.append(f"{counts['create']} to create, {counts['present']} present, {counts['skip']} skipped.")
    return "\n".join(lines)


async def restore_demo_codes(client) -> dict[str, int]:
    """Build plan § 7d.1 on the sandbox: each demo card's lead holds the card's
    own token as its lead code, so the training guide's card addresses and
    every personal link built from those leads stay fixed. The codes live in
    the CRM, which the nightly restore puts back to its baseline — a baseline
    captured before the code fields existed holds none — so they are written
    here every night, like the links. Idempotent; a lead already holding its
    code is left. Skipped entirely on a CRM without the code fields."""
    from . import leadcode

    totals = {"set": 0, "present": 0, "skipped": 0}
    if not await leadcode.available(client):
        totals["skipped"] = len(DEMO_SCAN_TOKENS)
        return totals
    for code in DEMO_SCAN_TOKENS:
        touch = await client.find_one(cfg.TOUCH, "scanToken", code, select="id,prospectId,contactId")
        lead_id = (touch or {}).get("prospectId")
        if not lead_id:
            totals["skipped"] += 1
            continue
        lead = await client.get(cfg.PROSPECT, lead_id, select=leadcode.LEAD_SELECT)
        if lead.get(leadcode.LEAD_FIELD) == code:
            totals["present"] += 1
        else:
            await client.update(cfg.PROSPECT, lead_id, {leadcode.LEAD_FIELD: code})
            totals["set"] += 1
        if lead.get("promotedContactId"):
            await leadcode.sync_on_conversion(client, lead_id, lead["promotedContactId"])
    return totals


async def restore_demo_links(store, client) -> dict[str, int]:
    """Create every demo link the store lacks. Idempotent by code: a link that
    is already there is left exactly as it is."""
    totals = {"created": 0, "present": 0, "skipped": 0}
    for e in await plan_demo_links(store, client):
        if e["action"] == "create":
            await store.create_link(**e["row"])
            totals["created"] += 1
        elif e["action"] == "present":
            totals["present"] += 1
        else:
            totals["skipped"] += 1
            log.info("sandbox demo link %s skipped: %s", e["token"], e.get("reason"))
    return totals


def _parts(settings: Settings):
    # Only the CRM check, not the reset's switch: ``sandbox_nightly_reset`` is a
    # worker setting, and the /setup job runs in the web process. Creating six
    # links is not the destructive half — the address alone keeps it off any
    # CRM but the sandbox, read straight from the URL as the reset reads it.
    from core.sandbox_reset import SANDBOX_URL_MARKER, SandboxResetRefused

    if SANDBOX_URL_MARKER not in (settings.espo_base_url or "").lower():
        raise SandboxResetRefused(
            f"CRM base URL is not the sandbox ({settings.espo_base_url!r}) — refusing")
    if settings.espo_dry_run or not settings.espo_api_key:
        raise RuntimeError("This deployment has no CRM credential (dry-run mode or no API key).")
    from core.espo import EspoClient

    from .store import make_campaign_store

    store = make_campaign_store(settings)
    if store is None:
        raise RuntimeError("This deployment has no database, so it holds no campaign links.")
    return store, EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


async def run_after_reset(settings: Settings) -> dict[str, int]:
    """The worker's call, straight after the nightly app-table reset.
    Best-effort: never raises."""
    try:
        store, client = _parts(settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("sandbox demo links not restored: %s", exc)
        return {"created": 0, "present": 0, "skipped": 0}
    try:
        totals = await restore_demo_links(store, client)
        log.info("sandbox demo links: %s created, %s present, %s skipped",
                 totals["created"], totals["present"], totals["skipped"])
        try:
            codes = await restore_demo_codes(client)
            log.info("sandbox demo lead codes: %s set, %s present, %s skipped",
                     codes["set"], codes["present"], codes["skipped"])
        except Exception as exc:  # noqa: BLE001 — the links still count
            log.warning("sandbox demo lead codes not restored: %s", exc)
        return totals
    except (EspoError, Exception) as exc:  # noqa: BLE001
        log.warning("sandbox demo links not restored: %s", exc)
        return {"created": 0, "present": 0, "skipped": 0}
    finally:
        await store.dispose()


async def job_dry_run(settings: Settings) -> str:
    store, client = _parts(settings)
    try:
        return plan_text(await plan_demo_links(store, client))
    finally:
        await store.dispose()


async def job_apply(settings: Settings) -> str:
    store, client = _parts(settings)
    try:
        t = await restore_demo_links(store, client)
        c = await restore_demo_codes(client)
        return (f"{t['created']} demo links created, {t['present']} already present, {t['skipped']} skipped. "
                f"Lead codes: {c['set']} set, {c['present']} present, {c['skipped']} skipped.")
    finally:
        await store.dispose()
