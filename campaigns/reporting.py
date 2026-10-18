"""Every number prospect marketing reports (build plan § 6). One module, so the
campaign record page, the Responses tab and the Analytics page read the same
rule and agree — the active-client-count discipline.

* :func:`summarize_responses` — the Responses tab's *responded* and *converted*
  (§ 6 item 2), from the durable submission store.
* :func:`touches_by_campaign` — § 6 item 2 across every campaign: the touch
  counts the record page shows (``service.touch_summary``), the call outcomes,
  the ``stageAtTouch`` breakdown, and responded / converted.
* :func:`entry_rung_by_door` — § 6 item 3: ``entryStage`` × ``entryDoor`` on
  the prospect records, plus the Contacts the information request and
  registration doors created (``cEntryStage`` Warm Lead — the only entry those
  two doors write), so a door entering half-way down is never read as
  converting better.

The system reads run under the org-wide API key (the Analytics rule for system
metrics); none of these functions writes anything.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from core.espo import EspoApi, EspoError

from . import config as cfg
from . import service

log = logging.getLogger("cbm_intake.campaigns.reporting")

_PAGE = 200

#: The result keys that mean a RELATIONSHIP record was created (§ 6 item 2:
#: *converted* = a relationship record carrying the campaign).
RELATIONSHIP_KEYS = ("engagementId", "partnerProfileId", "sponsorProfileId")
#: Rows that never count: the honeypot and a discard.
NOT_A_RESPONSE = ("held_honeypot", "discarded")

#: The row label for Contacts the information request and registration doors
#: created (they enter at Warm Lead, ruling 17).
DOOR_INFO_OR_REGISTRATION = "Information request or registration"


def summarize_responses(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The Responses tab's payload: the rows with their record ids, the per-form
    totals, and the two campaign counts of § 6 item 2 — *responded* (every
    delivered or pending submission that carried the campaign, the honeypot
    and discards excluded) and *converted* (those whose delivery created a
    relationship record: an engagement, a partner or a funder profile)."""
    totals: dict[str, int] = {}
    responded = converted = 0
    out = []
    for r in rows:
        result = r.get("result") or {}
        records = ({k: v for k, v in result.items() if isinstance(v, str) and k.endswith("Id")}
                   if isinstance(result, dict) else {})
        counted = r["status"] not in NOT_A_RESPONSE
        is_conversion = counted and any(records.get(k) for k in RELATIONSHIP_KEYS)
        if counted:
            totals[r["form_slug"]] = totals.get(r["form_slug"], 0) + 1
            responded += 1
        if is_conversion:
            converted += 1
        received = r.get("received_at")
        out.append({
            "id": r["id"], "form": r["form_slug"], "status": r["status"],
            "receivedAt": received.isoformat() if hasattr(received, "isoformat") else received,
            "linkToken": r.get("link_token"), "email": r.get("email"),
            "records": records, "converted": is_conversion,
        })
    return {"responses": out, "totals": totals, "responded": responded, "converted": converted}


def touch_breakdown(touches: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One campaign's touch counts: the record page's summary plus the call
    outcomes and the rung each target was on when its touch left Planned."""
    touches = list(touches)
    out: dict[str, Any] = dict(service.touch_summary(touches))
    out["done"] = sum(1 for t in touches if t.get("touchStatus") == cfg.TOUCH_DONE)
    for outcome in cfg.CALL_OUTCOMES:
        out[outcome] = sum(1 for t in touches if t.get("outcome") == outcome)
    stages: dict[str, int] = {}
    for t in touches:
        stage = t.get("stageAtTouch")
        if stage:
            stages[stage] = stages.get(stage, 0) + 1
    out["stageAtTouch"] = {s: stages[s] for s in cfg.STAGES if s in stages}
    return out


async def _all_touches(client: EspoApi) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await client.list(cfg.TOUCH, select=cfg.TOUCH_SELECT, max_size=_PAGE, offset=offset,
                                 order_by="createdAt", order="asc")
        batch = page.get("list", [])
        rows.extend(batch)
        if len(batch) < _PAGE or len(rows) >= 50000:
            break
        offset += _PAGE
    return rows


async def touches_by_campaign(client: EspoApi, campaign_store=None) -> list[dict[str, Any]]:
    """§ 6 item 2 for every campaign that selects an audience, newest first.
    ``responded`` / ``converted`` are None (rendered "—") without the
    application database."""
    campaigns = await service.list_campaigns(client)
    touches = await _all_touches(client)
    by_campaign: dict[str, list[dict[str, Any]]] = {}
    for t in touches:
        if t.get("outreachCampaignId"):
            by_campaign.setdefault(t["outreachCampaignId"], []).append(t)
    out = []
    for c in campaigns:
        if c.get("campaignKind") not in cfg.SELECTING_KINDS:
            continue
        row: dict[str, Any] = {
            "id": c["id"], "name": c.get("name") or "(unnamed)", "kind": c.get("campaignKind"),
            "status": c.get("campaignStatus"), **touch_breakdown(by_campaign.get(c["id"], [])),
            "responded": None, "converted": None,
        }
        if campaign_store is not None:
            try:
                summary = summarize_responses(await campaign_store.recent_submissions(c["id"], limit=10000))
                row["responded"], row["converted"] = summary["responded"], summary["converted"]
            except Exception as exc:  # noqa: BLE001 — a store failure reads "—", never 0
                log.warning("responses of campaign %s unreadable: %s", c["id"], exc)
        out.append(row)
    return out


async def _count(client: EspoApi, entity: str, where: list[dict[str, Any]]) -> int:
    env = await client.list(entity, where=where, select="id", max_size=1)
    return int(env.get("total") or 0)


async def entry_rung_by_door(client: EspoApi) -> list[dict[str, Any]]:
    """§ 6 item 3: one row per door, a count per entry rung, and a total. The
    Contacts row is None per rung when the CRM lacks the field (rendered "—")."""
    out: list[dict[str, Any]] = []
    for door in (cfg.DOOR_FILING, cfg.DOOR_LIST, cfg.DOOR_PARTNER_FILE):
        row: dict[str, Any] = {"door": door}
        for stage in cfg.STAGES:
            row[stage] = await _count(client, cfg.PROSPECT, [
                {"type": "equals", "attribute": "entryDoor", "value": door},
                {"type": "equals", "attribute": "entryStage", "value": stage},
            ])
        row["total"] = sum(row[s] for s in cfg.STAGES)
        out.append(row)
    contacts: dict[str, Any] = {"door": DOOR_INFO_OR_REGISTRATION}
    try:
        n = await _count(client, cfg.CONTACT, [
            {"type": "equals", "attribute": "cEntryStage", "value": cfg.STAGE_WARM_LEAD}])
        for stage in cfg.STAGES:
            contacts[stage] = n if stage == cfg.STAGE_WARM_LEAD else 0
        contacts["total"] = n
    except EspoError as exc:
        log.warning("Contact entry rungs unreadable: %s", exc)
        for stage in cfg.STAGES:
            contacts[stage] = None
        contacts["total"] = None
    out.append(contacts)
    return out


def stage_text(stages: Optional[dict[str, int]]) -> str:
    """``{"Qualified": 12, "Lead": 3}`` as "Qualified 12 · Lead 3", or "—"."""
    if not stages:
        return "—"
    return " · ".join(f"{k} {v}" for k, v in stages.items())
