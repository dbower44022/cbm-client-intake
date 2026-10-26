"""The email kind (build plan § 3.3; rulings 19 and 25; the mailing-list plan).

**No cold email, ever (ruling 19).** An email campaign selects **Contacts**
only, with the standing list's own audience rule (``core/mailing_sync``:
``cMarketingOptIn`` true and the address neither opted out nor invalid), typed
Prospect at a chosen stage (Prospect, Engaged, Opportunity — ruling 50), whose
lead (if any) is still being worked — or, the dormant-client term of ruling 25,
typed Client whose engagements are all closed, the latest more than N days ago.
A lead is never selected.

**The application does not send.** Sign-off queues the campaign; the worker
pushes its people as a **named Constant Contact list** — one list per
campaign, named after it — through the same connection the nightly push uses.
The standing list is never touched: its push manages its own list only, and
this push never reads or writes the standing list's id. An address the vendor
holds as unsubscribed or on hold is withheld, never re-added, and its touch
cancelled. Staff design and send the notice at the vendor with the campaign's
links (mailing-list ruling 6), then press **Mark as sent**: every pushed touch
moves to Sent and the campaign completes (until the mailing plan's Phase D
reads the send report).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import Settings
from core.crm_upsert import CONTACT_TYPE_FIELD, PROSPECT_TYPE
from core.espo import EspoApi, EspoError

from . import config as cfg
from .audience import address_for_email, email_consented
from .audience import audience_result as _audience_result
from . import service
from .attribution import holds_relationship
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.email")

#: The stages after first contact (ruling 50). A lead is never emailed: it has
#: no Contact, and no Contact means no opt-in (ruling 19 — no cold email).
EMAILABLE_STAGES = cfg.STAGES
DEFAULT_RULE: dict[str, Any] = {"stages": list(cfg.STAGES), "dormantDays": None}
DEFAULT_DORMANT_DAYS = 365
CONTACT_SELECT = (
    f"id,name,firstName,lastName,emailAddress,cMarketingOptIn,emailAddressIsOptedOut,"
    f"emailAddressIsInvalid,{CONTACT_TYPE_FIELD},cFunnelStage"
)
#: Engagement statuses that mean the relationship is still open — a client in
#: any of these is not dormant (Candidate and Client in reporting, plus the
#: paused ones).
OPEN_STATUSES = ("Submitted", "Pending Acceptance", "Assigned", "Assignment Dormant", "Active", "On-Hold")
PUSHED = "pushed to the mailing list"
WITHHELD = "withheld — unsubscribed or on hold at the mailing service"


def _crm_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def normalise_rule(rule: Optional[dict[str, Any]]) -> dict[str, Any]:
    rule = rule or {}
    stages = [s for s in (rule.get("stages") or []) if s in EMAILABLE_STAGES]
    dormant = rule.get("dormantDays")
    try:
        dormant = int(dormant) if dormant not in (None, "", False) else None
    except (TypeError, ValueError):
        dormant = None
    if dormant is not None and dormant < 0:
        dormant = None
    if not stages and dormant is None:
        stages = list(DEFAULT_RULE["stages"])
    return {"stages": stages, "dormantDays": dormant}


def rule_summary(rule: dict[str, Any]) -> str:
    parts = []
    if rule["stages"]:
        parts.append(f"Contacts typed Prospect at {' or '.join(rule['stages'])}")
    if rule["dormantDays"] is not None:
        parts.append(f"clients whose last engagement closed more than {rule['dormantDays']} days ago (ruling 25)")
    return (" and ".join(parts) + ", who opted in to marketing email with a usable address "
            "(ruling 19 — no cold email).")


def _usable(c: dict[str, Any]) -> bool:
    return bool(c.get("emailAddress")) and bool(c.get("cMarketingOptIn")) \
        and not c.get("emailAddressIsOptedOut") and not c.get("emailAddressIsInvalid")


def _parse(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def dormant_client_contacts(client: EspoApi, days: int, *, now: Optional[datetime] = None) -> set[str]:
    """Contact ids whose engagements are all closed, the latest closing more than
    ``days`` ago (ruling 25). An engagement with no close date counts as closed
    at its creation."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(0, days))
    latest: dict[str, datetime] = {}
    open_: set[str] = set()
    for e in await service._page_all(client, "CEngagement",
                                     select="id,engagementStatus,closeDate,createdAt,primaryEngagementContactId",
                                     limit=50000):
        cid = e.get("primaryEngagementContactId")
        if not cid:
            continue
        if e.get("engagementStatus") in OPEN_STATUSES:
            open_.add(cid)
            continue
        closed = _parse(e.get("closeDate")) or _parse(e.get("createdAt"))
        if closed and (cid not in latest or closed > latest[cid]):
            latest[cid] = closed
    return {cid for cid, when in latest.items() if cid not in open_ and when < cutoff}


async def select_targets(client: EspoApi, rule: Optional[dict[str, Any]],
                         *, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    rule = normalise_rule(rule)
    out: dict[str, dict[str, Any]] = {}
    if rule["stages"]:
        left: set[str] = set()
        for p in await service._page_all(client, cfg.PROSPECT, select="id,sideExit,promotedContactId",
                                         where=[{"type": "isNotNull", "attribute": "sideExit"}], limit=20000):
            if p.get("sideExit") and p.get("promotedContactId"):
                left.add(p["promotedContactId"])
        for c in await service._page_all(
            client, cfg.CONTACT, select=CONTACT_SELECT,
            where=[{"type": "in", "attribute": "cFunnelStage", "value": rule["stages"]},
                   {"type": "isTrue", "attribute": "cMarketingOptIn"}],
            order_by="createdAt", order="asc", limit=20000,
        ):
            if (c["id"] in left or PROSPECT_TYPE not in (c.get(CONTACT_TYPE_FIELD) or [])
                    or holds_relationship(c) or not _usable(c)):
                continue
            out[c["id"]] = {"key": f"contact:{c['id']}", "kind": "contact", "id": c["id"],
                            "name": c.get("name") or "", "email": c["emailAddress"].strip(),
                            "first": c.get("firstName") or "", "last": c.get("lastName") or "",
                            "stage": c.get("cFunnelStage")}
    if rule["dormantDays"] is not None:
        ids = await dormant_client_contacts(client, rule["dormantDays"], now=now)
        for cid in sorted(ids - set(out)):
            try:
                c = await client.get(cfg.CONTACT, cid, select=CONTACT_SELECT)
            except EspoError:
                continue
            if not c or "Client" not in (c.get(CONTACT_TYPE_FIELD) or []) or not _usable(c):
                continue
            out[cid] = {"key": f"contact:{cid}", "kind": "contact", "id": cid, "name": c.get("name") or "",
                        "email": c["emailAddress"].strip(), "first": c.get("firstName") or "",
                        "last": c.get("lastName") or "", "stage": None}
    # One address, one person: the first contact holding it wins (the standing
    # push's rule).
    seen: set[str] = set()
    result = []
    for t in out.values():
        key = t["email"].lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(t)
    return result


async def build_list(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any],
                     rule: Optional[dict[str, Any]], audience: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if campaign.get("campaignKind") != cfg.KIND_EMAIL:
        raise CampaignError("This is not an email campaign.")
    status = campaign.get("campaignStatus") or cfg.STATUS_DRAFT
    if status not in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING):
        raise CampaignError(f"The list cannot be rebuilt once the campaign is {status}.")
    rule = normalise_rule(rule)
    # A campaign that names a list sends to it (build plan § 7c); else its rule.
    targets = audience["targets"] if audience else await select_targets(api_client, rule)
    planned = {}
    for t in await service.campaign_touches(api_client, campaign["id"]):
        if t.get("touchStatus") == cfg.TOUCH_PLANNED and t.get("contactId"):
            planned[f"contact:{t['contactId']}"] = t
    wanted = {t["key"]: t for t in targets}
    created = kept = cancelled = 0
    for key, touch in planned.items():
        if key not in wanted:
            await api_client.update(cfg.TOUCH, touch["id"], {"touchStatus": cfg.TOUCH_CANCELLED})
            cancelled += 1
    for key, target in wanted.items():
        if key in planned:
            kept += 1
            continue
        await api_client.create(cfg.TOUCH, {
            "name": f"{campaign.get('name') or 'Campaign'} — {target['name']}"[:255],
            "channel": cfg.KIND_EMAIL, "touchStatus": cfg.TOUCH_PLANNED, "plannedAt": _crm_now(),
            "outreachCampaignId": campaign["id"], "contactId": target["id"],
        })
        created += 1
    stamps: dict[str, Any] = {
        "selectionRule": json.dumps({"list": audience["list"]} if audience else rule),
        "selectionSummary": audience["summary"] if audience else rule_summary(rule),
    }
    if status == cfg.STATUS_DRAFT:
        stamps["campaignStatus"] = cfg.STATUS_AWAITING
    await service.stamp_campaign(user_client, api_client, campaign["id"], stamps)
    return {"pieces": kept + created, "created": created, "kept": kept, "cancelled": cancelled,
            "rule": rule, "summary": stamps["selectionSummary"],
            **({"audience": _audience_result(audience)} if audience else {})}


def list_name(campaign: dict[str, Any]) -> str:
    """The vendor list's name: the campaign's, marked so it never collides with
    the standing list."""
    return f"Campaign — {campaign.get('name') or campaign.get('id')}"[:255]


async def sign_off(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any], *,
                   confirm: str, user_name: str, settings: Settings) -> dict[str, Any]:
    if campaign.get("campaignKind") != cfg.KIND_EMAIL:
        raise CampaignError("This is not an email campaign.")
    if campaign.get("campaignStatus") not in (cfg.STATUS_AWAITING, cfg.STATUS_DRAFT):
        raise CampaignError(f"A campaign at {campaign.get('campaignStatus')} cannot be signed off.")
    if not settings.mailing_client_id or not settings.mailing_client_secret:
        raise CampaignError("The mailing service is not connected on this deployment (System Settings, Mailing).")
    if list_name(campaign).casefold() == (settings.mailing_list_name or "").strip().casefold():
        raise CampaignError("The campaign's list name would be the standing mailing list's — rename the campaign.")
    touches = await service.campaign_touches(api_client, campaign["id"])
    count = sum(1 for t in touches if t.get("touchStatus") == cfg.TOUCH_PLANNED)
    if count == 0:
        raise CampaignError("Build the list first — there is nobody on it.")
    if str(confirm or "").strip() != str(count):
        raise CampaignError(f"Type the number of people, {count}, to confirm the push to the mailing service.")
    return await service.stamp_campaign(user_client, api_client, campaign["id"], {
        "pieceCount": count, "signedOffByName": user_name[:255], "signedOffAt": _crm_now(),
        "campaignStatus": cfg.STATUS_SIGNED_OFF,
    })


# --- the copy of a list (CAMPAIGN_LIST_SYNC; § 7e.9, ruling 95) ---------------------------
#
# With the switch on, an email campaign sends to its list's kept-current copy in
# Constant Contact. Build writes no touch (Doug's ruling at the M7 plan,
# 10-26-26: the send report of M9 writes one per real recipient), sign-off syncs
# the copy, staff send the notice at the vendor to that copy, and *Pick the
# email* records which one and moves the campaign on. The per-campaign push
# below, ``push_campaign`` and *Mark as sent*, serve the switch-off path only;
# they go when the switch is retired.

VENDOR_EMAIL_FIELD = "vendorEmailId"
NEEDS_A_LIST = ("Choose a list for this email campaign first (Audience and content). An email goes to "
                "a list's copy in Constant Contact.")


async def build_for_copy(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any],
                         audience: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Build with the switch on: the list's count and its skips, no touches.
    Planned touches left from a build before the switch are cancelled — the
    send report writes the real ones."""
    if campaign.get("campaignKind") != cfg.KIND_EMAIL:
        raise CampaignError("This is not an email campaign.")
    status = campaign.get("campaignStatus") or cfg.STATUS_DRAFT
    if status not in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING):
        raise CampaignError(f"The list cannot be rebuilt once the campaign is {status}.")
    if not audience:
        raise CampaignError(NEEDS_A_LIST)
    cancelled = 0
    for t in await service.campaign_touches(api_client, campaign["id"]):
        if t.get("touchStatus") == cfg.TOUCH_PLANNED:
            await api_client.update(cfg.TOUCH, t["id"], {"touchStatus": cfg.TOUCH_CANCELLED})
            cancelled += 1
    stamps: dict[str, Any] = {"selectionRule": json.dumps({"list": audience["list"]}),
                              "selectionSummary": audience["summary"]}
    if status == cfg.STATUS_DRAFT:
        stamps["campaignStatus"] = cfg.STATUS_AWAITING
    await service.stamp_campaign(user_client, api_client, campaign["id"], stamps)
    reached = len(audience["targets"])
    return {"pieces": reached, "created": 0, "kept": 0, "cancelled": cancelled, "rule": {"list": audience["list"]},
            "summary": stamps["selectionSummary"], "audience": _audience_result(audience), "copy": True}


def copy_refusal(list_row: Optional[dict[str, Any]]) -> str:
    """Why this list cannot carry the email, in words, or empty."""
    if not list_row:
        return NEEDS_A_LIST
    if list_row.get("status") != "active":
        return f"The list \"{list_row['name']}\" is retired — choose an active list."
    if not list_row.get("cc_sync"):
        return (f"The list \"{list_row['name']}\" keeps no copy in Constant Contact. Open it on the Lists tab "
                "and tick Keep a copy in Constant Contact, then sign off again.")
    return ""


def check_sign_off_to_copy(campaign: dict[str, Any], *, confirm: str, built: Optional[dict[str, Any]],
                           list_row: Optional[dict[str, Any]], settings: Settings) -> int:
    """Every refusal before the sync runs; the number of people the build
    reached, which the typed confirmation must match."""
    if campaign.get("campaignKind") != cfg.KIND_EMAIL:
        raise CampaignError("This is not an email campaign.")
    if campaign.get("campaignStatus") not in (cfg.STATUS_AWAITING, cfg.STATUS_DRAFT):
        raise CampaignError(f"A campaign at {campaign.get('campaignStatus')} cannot be signed off.")
    if not settings.mailing_client_id or not settings.mailing_client_secret:
        raise CampaignError("The mailing service is not connected on this deployment (System Settings, Mailing).")
    problem = copy_refusal(list_row)
    if problem:
        raise CampaignError(problem)
    if not built:
        raise CampaignError("Build the list first — it counts who the email will reach.")
    count = int(built.get("reached") or 0)
    if count == 0:
        raise CampaignError("Nobody on the list can be emailed — build it again once it holds people who opted in.")
    if str(confirm or "").strip() != str(count):
        raise CampaignError(f"Type the number of people, {count}, to confirm.")
    return count


async def signed_off_to_copy(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any], *,
                             user_name: str, synced: dict[str, Any]) -> dict[str, Any]:
    """After the sync: the stamps and Signed off. ``pieceCount`` is who the copy
    holds now."""
    return await service.stamp_campaign(user_client, api_client, campaign["id"], {
        "pieceCount": int(synced.get("audience") or 0), "signedOffByName": user_name[:255],
        "signedOffAt": _crm_now(), "campaignStatus": cfg.STATUS_SIGNED_OFF,
    })


async def vendor_email_available(client: EspoApi) -> bool:
    try:
        fields = await client.metadata(f"entityDefs.{cfg.CAMPAIGN}.fields")
    except Exception as exc:  # noqa: BLE001 — unreadable is "not available"
        log.warning("could not read the campaign fields (%s) — no email can be picked", exc)
        return False
    return isinstance(fields, dict) and isinstance(fields.get(VENDOR_EMAIL_FIELD), dict)


def check_pick(campaign: dict[str, Any]) -> None:
    if campaign.get("campaignKind") != cfg.KIND_EMAIL:
        raise CampaignError("This is not an email campaign.")
    if campaign.get(VENDOR_EMAIL_FIELD):
        raise CampaignError("An email is already picked for this campaign.")
    if campaign.get("campaignStatus") != cfg.STATUS_SIGNED_OFF:
        raise CampaignError("Pick the email after the campaign is signed off and the email has gone out "
                            "from Constant Contact.")


async def pick_email(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any], *,
                     email_id: str, sent: list[dict[str, Any]]) -> dict[str, Any]:
    """Record the email staff sent to the copy and move the campaign on (the
    strip's Sent). ``sent`` is the vendor's listing, read again for this
    request, so only an email that really went to the list can be picked."""
    check_pick(campaign)
    if not await vendor_email_available(api_client):
        raise CampaignError("The CRM has no place for the picked email yet (the campaign's Constant Contact "
                            "email id field) — the CRM change for the redesign is owed on this CRM.")
    chosen = next((e for e in sent if e.get("id") == str(email_id or "")), None)
    if not chosen:
        raise CampaignError("That email was not sent to this campaign's list in the last 30 days — "
                            "choose one from the list shown.")
    updated = await service.stamp_campaign(user_client, api_client, campaign["id"], {
        VENDOR_EMAIL_FIELD: chosen["id"][:64], "campaignStatus": cfg.STATUS_RUNNING, "runStartedAt": _crm_now(),
    })
    return {"campaign": updated, "email": chosen}


# --- the push (worker) --------------------------------------------------------------------

async def push_campaign(client: EspoApi, mail, campaign: dict[str, Any]) -> dict[str, int]:
    """Create or find the campaign's own list and import its Planned people.
    Never touches the standing list or its stored id."""
    from core.mailing_sync import vendor_unsubscribed

    totals = {"pushed": 0, "withheld": 0, "skipped": 0}
    if campaign.get("campaignStatus") == cfg.STATUS_SIGNED_OFF:
        await client.update(cfg.CAMPAIGN, campaign["id"],
                            {"campaignStatus": cfg.STATUS_RUNNING, "runStartedAt": _crm_now()})
    planned = [t for t in await service.campaign_touches(client, campaign["id"])
               if t.get("touchStatus") == cfg.TOUCH_PLANNED and (t.get("vendorStatus") or "") != PUSHED]
    if not planned:
        return totals
    name = list_name(campaign)
    found = await mail.find_list(name)
    list_id = str(found.get("list_id")) if found else ""
    if not list_id:
        created = await mail.create_list(name)
        list_id = str(created.get("list_id") or "")
    if not list_id:
        raise CampaignError("The mailing service returned no list id.")
    gone = await vendor_unsubscribed(mail)
    rows, touched = [], []
    for t in planned:
        c = await client.get(cfg.CONTACT, t.get("contactId") or "", select=CONTACT_SELECT)
        # Consent is the person's own; a chapter member is reached at their
        # cbmEmail only (ruling 60), everyone else at their own address.
        email = await address_for_email(client, c) if c and email_consented(c) else None
        if not c or not email:
            await client.update(cfg.TOUCH, t["id"], {"touchStatus": cfg.TOUCH_CANCELLED,
                                                     "vendorStatus": "no consent or no usable address at push time"})
            totals["skipped"] += 1
            continue
        if email.lower() in gone:
            await client.update(cfg.TOUCH, t["id"], {"touchStatus": cfg.TOUCH_CANCELLED, "vendorStatus": WITHHELD})
            totals["withheld"] += 1
            continue
        row = {"email": email}
        if c.get("firstName"):
            row["first_name"] = c["firstName"][:50]
        if c.get("lastName"):
            row["last_name"] = c["lastName"][:50]
        rows.append(row)
        touched.append((t, c))
    if rows:
        await mail.import_contacts(rows, list_id=list_id)
        for t, c in touched:
            await client.update(cfg.TOUCH, t["id"], {"vendorStatus": PUSHED, "vendorPieceId": list_id,
                                                     "stageAtTouch": c.get("cFunnelStage")})
        totals["pushed"] = len(rows)
    return totals


async def run_email_cycle(settings: Settings, *, client: Optional[EspoApi] = None, mail=None,
                          store=None) -> dict[str, int]:
    """One worker pass over every Signed off or Running email campaign with
    people not yet pushed. Best effort, never raises."""
    totals = {"campaigns": 0, "pushed": 0, "withheld": 0, "skipped": 0, "errors": 0}
    if not (settings.campaigns_enabled and settings.campaigns_email) or settings.espo_dry_run:
        return totals
    if settings.campaign_list_sync and settings.campaign_lists:
        # Copies on: an email goes to its list's copy, which the mailing pass
        # keeps current; there is no per-campaign list to push.
        return totals
    if not settings.mailing_client_id or not settings.mailing_client_secret:
        return totals
    try:
        from core.mailing_sync import _clients
        client, mail, store = _clients(settings, client, mail, store)
        page = await client.list(cfg.CAMPAIGN, select=cfg.CAMPAIGN_SELECT, max_size=200, where=[
            {"type": "equals", "attribute": "campaignKind", "value": cfg.KIND_EMAIL},
            {"type": "in", "attribute": "campaignStatus", "value": [cfg.STATUS_SIGNED_OFF, cfg.STATUS_RUNNING]},
        ])
    except Exception as exc:  # noqa: BLE001
        log.warning("email campaign run: %s", exc)
        totals["errors"] += 1
        return totals
    for campaign in page.get("list", []):
        totals["campaigns"] += 1
        try:
            result = await push_campaign(client, mail, campaign)
            for k in ("pushed", "withheld", "skipped"):
                totals[k] += result[k]
        except Exception as exc:  # noqa: BLE001 — one campaign never stops the others
            totals["errors"] += 1
            log.warning("email campaign %s push failed: %s", campaign.get("id"), exc)
    if totals["campaigns"]:
        log.info("email campaign pass: %s", totals)
    return totals


async def mark_as_sent(api_client: EspoApi, campaign: dict[str, Any]) -> dict[str, int]:
    """Staff sent the notice at the mailing service: every pushed touch is Sent,
    and the campaign completes. Refused while people are still waiting for the
    push (the notice would have gone to a list missing them)."""
    if campaign.get("campaignKind") != cfg.KIND_EMAIL:
        raise CampaignError("This is not an email campaign.")
    if campaign.get("campaignStatus") != cfg.STATUS_RUNNING:
        raise CampaignError("Mark as sent comes after the list has been pushed (the campaign reads Running).")
    touches = await service.campaign_touches(api_client, campaign["id"])
    waiting = [t for t in touches if t.get("touchStatus") == cfg.TOUCH_PLANNED and t.get("vendorStatus") != PUSHED]
    if waiting:
        raise CampaignError(f"{len(waiting)} people are not on the mailing list yet — wait for the push (a minute), then mark it sent.")
    now = _crm_now()
    sent = 0
    for t in touches:
        if t.get("touchStatus") == cfg.TOUCH_PLANNED and t.get("vendorStatus") == PUSHED:
            await api_client.update(cfg.TOUCH, t["id"], {"touchStatus": cfg.TOUCH_SENT, "sentAt": now})
            sent += 1
    await api_client.update(cfg.CAMPAIGN, campaign["id"],
                            {"campaignStatus": cfg.STATUS_COMPLETE, "runCompletedAt": now})
    return {"sent": sent}
