"""Every number prospect marketing reports (build plan § 6, reworked for the
lead model § 7a). One module, so the campaign record page, the Responses tab and
the Analytics page read the same rule and agree — the active-client-count
discipline.

**The three campaign counts (ruling 46).** *Responded*: every delivered or
pending submission that carried the campaign. *Converted*: a lead became a
Prospect — a response whose delivery converted the lead it named, or created a
lead Converted at once (ruling 48), plus every call marked Interested that
converted its lead (the touch then names the new Contact or Company). *Became a
client, partner or funder*: a response whose delivery created a relationship
record (ruling 22's event, "a relationship begins").

* :func:`summarize_responses` — the Responses tab, from the durable store.
* :func:`touches_by_campaign` — every campaign: the touch counts, the call
  outcomes, the position each target held when touched, and the three counts.
* :func:`leads_by_source` — every lead by Lead Source and current status.
* :func:`funnel` — the lead statuses, then the stages after first contact,
  then Candidate and Client from the engagements.

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

#: The result keys that mean a RELATIONSHIP record was created — *became a
#: client, partner or funder* (ruling 46).
RELATIONSHIP_KEYS = ("engagementId", "partnerProfileId", "sponsorProfileId")
#: Rows that never count: the honeypot and a discard.
NOT_A_RESPONSE = ("held_honeypot", "discarded")

#: The result keys that mean a lead was converted (ruling 46): the landing
#: response and a form naming a lead write ``leadConverted``; a form whose new
#: record got a lead Converted at once (ruling 48) writes ``leadId``.
CONVERSION_KEYS = ("leadConverted", "leadId")


def _converted(result: dict[str, Any]) -> bool:
    return any(result.get(k) for k in CONVERSION_KEYS)


def summarize_responses(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The Responses tab's payload: the rows with their record ids, the per-form
    totals, and the three counts of ruling 46 — *responded* (every delivered
    or pending submission that carried the campaign, the honeypot and discards
    excluded), *converted* (a lead became a Prospect) and *became*
    (a relationship record was created: an engagement, a partner or a funder
    profile)."""
    totals: dict[str, int] = {}
    responded = converted = became = 0
    out = []
    for r in rows:
        result = r.get("result") or {}
        if not isinstance(result, dict):
            result = {}
        records = {k: v for k, v in result.items() if isinstance(v, str) and k.endswith("Id")}
        counted = r["status"] not in NOT_A_RESPONSE
        is_conversion = counted and _converted(result)
        is_relationship = counted and any(records.get(k) for k in RELATIONSHIP_KEYS)
        if counted:
            totals[r["form_slug"]] = totals.get(r["form_slug"], 0) + 1
            responded += 1
        converted += int(is_conversion)
        became += int(is_relationship)
        received = r.get("received_at")
        out.append({
            "id": r["id"], "form": r["form_slug"], "status": r["status"],
            "receivedAt": received.isoformat() if hasattr(received, "isoformat") else received,
            "linkToken": r.get("link_token"), "email": r.get("email"),
            "records": records, "converted": is_conversion, "became": is_relationship,
        })
    return {"responses": out, "totals": totals, "responded": responded, "converted": converted,
            "became": became}


def call_conversions(touches: Iterable[dict[str, Any]]) -> int:
    """Calls marked Interested that converted their lead: the touch names the
    lead AND the Contact or Company the conversion made (``calls``)."""
    return sum(1 for t in touches
               if t.get("outcome") == cfg.OUTCOME_INTERESTED and t.get("prospectId")
               and (t.get("contactId") or t.get("companyId")))


def touch_breakdown(touches: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One campaign's touch counts: the record page's summary plus the call
    outcomes and the position each target held when its touch left Planned
    (a lead's status, a Company's or Contact's stage)."""
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
    out["stageAtTouch"] = {s: stages[s] for s in cfg.TOUCH_POSITIONS if s in stages}
    out["callConversions"] = call_conversions(touches)
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
    """Every campaign that selects an audience, newest first, with ruling 46's
    three counts. ``responded`` / ``converted`` / ``became`` are None (rendered
    "—") without the application database."""
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
            "responded": None, "converted": None, "became": None,
        }
        if campaign_store is not None:
            try:
                summary = summarize_responses(await campaign_store.recent_submissions(c["id"], limit=10000))
                row["responded"], row["became"] = summary["responded"], summary["became"]
                row["converted"] = summary["converted"] + row["callConversions"]
            except Exception as exc:  # noqa: BLE001 — a store failure reads "—", never 0
                log.warning("responses of campaign %s unreadable: %s", c["id"], exc)
        out.append(row)
    return out


async def campaign_counts(client: EspoApi, campaign_store, campaign_id: str) -> dict[str, int]:
    """Ruling 46's three counts for one campaign — the same rule as the
    Responses tab and :func:`touches_by_campaign`."""
    page = await client.list(cfg.TOUCH, select="id,outcome,prospectId,contactId,companyId", max_size=_PAGE,
                             where=[{"type": "equals", "attribute": "outreachCampaignId", "value": campaign_id},
                                    {"type": "equals", "attribute": "outcome", "value": cfg.OUTCOME_INTERESTED}])
    calls = call_conversions(page.get("list", []))
    summary = summarize_responses(await campaign_store.recent_submissions(campaign_id, limit=10000))
    return {"responded": summary["responded"], "converted": summary["converted"] + calls,
            "became": summary["became"]}


async def _count(client: EspoApi, entity: str, where: list[dict[str, Any]]) -> int:
    env = await client.list(entity, where=where, select="id", max_size=1)
    return int(env.get("total") or 0)


async def leads_by_source(client: EspoApi) -> list[dict[str, Any]]:
    """One row per Lead Source, a count per lead status and a total — where
    leads came from and what became of them (rulings 41, 48)."""
    out: list[dict[str, Any]] = []
    sources = (*cfg.IMPORT_SOURCES, cfg.SOURCE_MENTOR_REQUEST, cfg.SOURCE_VOLUNTEER, cfg.SOURCE_INFO_REQUEST,
               cfg.SOURCE_PARTNER_APPLICATION, cfg.SOURCE_FUNDER_APPLICATION, cfg.SOURCE_EVENT_REGISTRATION,
               cfg.SOURCE_EMAIL)
    for source in sources:
        row: dict[str, Any] = {"source": source}
        for status in cfg.LEAD_STATUSES:
            row[status] = await _count(client, cfg.PROSPECT, [
                {"type": "equals", "attribute": "leadSource", "value": source},
                {"type": "equals", "attribute": "leadStatus", "value": status},
            ])
        row["total"] = sum(row[s] for s in cfg.LEAD_STATUSES)
        out.append(row)
    return out


def stage_text(stages: Optional[dict[str, int]]) -> str:
    """``{"Qualified": 12, "Prospect": 3}`` as "Qualified 12 · Prospect 3", or "—"."""
    if not stages:
        return "—"
    return " · ".join(f"{k} {v}" for k, v in stages.items())


# --- the funnel (§ 6 item 1) --------------------------------------------------------------

#: The funnel's bands: a lead before first contact, a Prospect after it
#: (rulings 42, 43, 50), and Candidate and Client from the engagement.
BANDS = {
    cfg.LEAD_UNQUALIFIED: "Lead", cfg.LEAD_QUALIFIED: "Lead",
    cfg.STAGE_PROSPECT: "Prospect", cfg.STAGE_ENGAGED: "Prospect", cfg.STAGE_OPPORTUNITY: "Prospect",
    "Candidate": "Client", "Client": "Client",
}
#: Candidate: asked for mentoring, no session yet. Client: active mentoring.
#: Read from the engagement's status, which the first completed session moves
#: from Assigned to Active (the activation rule) — so the status IS the
#: "has a completed session" test.
CANDIDATE_STATUSES = ("Submitted", "Pending Acceptance", "Assigned", "Assignment Dormant")
CLIENT_STATUSES = ("Active", "On-Hold")


async def funnel(client: EspoApi) -> list[dict[str, Any]]:
    """A count per position, nothing counted twice: leads still being worked
    (Unqualified, Qualified — no reason, not converted); Companies typed
    Prospect at a stage; Contacts typed Prospect whose Company is not itself a
    Company typed Prospect (the person is counted under the company, § 1.8);
    then Candidate and Client from the engagements."""
    counts: dict[str, int] = {s: 0 for s in (*cfg.LEAD_OPEN_STATUSES, *cfg.STAGES)}
    for p in await service._page_all(client, cfg.PROSPECT, select="id,leadStatus,sideExit",
                                     where=[{"type": "isNull", "attribute": "sideExit"},
                                            {"type": "in", "attribute": "leadStatus",
                                             "value": list(cfg.LEAD_OPEN_STATUSES)}], limit=50000):
        if not p.get("sideExit") and p.get("leadStatus") in cfg.LEAD_OPEN_STATUSES:
            counts[p["leadStatus"]] += 1
    prospect_companies: set[str] = set()
    for a in await service._page_all(client, cfg.ACCOUNT, select="id,cCompanyType,cFunnelStage",
                                     where=[{"type": "in", "attribute": "cFunnelStage", "value": list(cfg.STAGES)}],
                                     limit=50000):
        if cfg.COMPANY_TYPE_PROSPECT in (a.get("cCompanyType") or []) and a.get("cFunnelStage") in counts:
            prospect_companies.add(a["id"])
            counts[a["cFunnelStage"]] += 1
    for c in await service._page_all(client, cfg.CONTACT, select="id,cContactType,cFunnelStage,accountId",
                                     where=[{"type": "in", "attribute": "cFunnelStage", "value": list(cfg.STAGES)}],
                                     limit=50000):
        if cfg.CONTACT_TYPE_PROSPECT not in (c.get("cContactType") or []):
            continue
        if c.get("accountId") and c["accountId"] in prospect_companies:
            continue
        if c.get("cFunnelStage") in counts:
            counts[c["cFunnelStage"]] += 1
    out = [{"band": BANDS[s], "rung": s, "count": counts[s]} for s in counts]
    for rung, statuses in (("Candidate", CANDIDATE_STATUSES), ("Client", CLIENT_STATUSES)):
        out.append({"band": BANDS[rung], "rung": rung,
                    "count": await _count(client, "CEngagement", [
                        {"type": "in", "attribute": "engagementStatus", "value": list(statuses)}])})
    return out


async def campaign_results(client: EspoApi, campaign_id: str) -> dict[str, int]:
    """One campaign's results down the funnel (§ 6, the campaign dashboard):
    the relationship records and registrations carrying it."""
    eq = {"type": "equals", "attribute": "outreachCampaignId", "value": campaign_id}
    return {
        "candidates": await _count(client, "CEngagement", [eq, {"type": "in", "attribute": "engagementStatus",
                                                                "value": list(CANDIDATE_STATUSES)}]),
        "clients": await _count(client, "CEngagement", [eq, {"type": "in", "attribute": "engagementStatus",
                                                             "value": list(CLIENT_STATUSES)}]),
        "registered": await _count(client, "CEventRegistration", [eq]),
        "attended": await _count(client, "CEventRegistration", [eq, {"type": "equals", "attribute": "attendanceStatus",
                                                                     "value": "Attended"}]),
        "informationRequests": await _count(client, "CInformationRequest", [eq]),
        "partners": await _count(client, "CPartnerProfile", [eq]),
        "funders": await _count(client, "CSponsorProfile", [eq]),
    }
