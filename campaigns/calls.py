"""The call kind (build plan § 3.4, ruling 20; who calls is ruling 36; reworked
for the lead model § 7a — rulings 44, 47, 52).

**Select.** A target is a lead holding a phone, at a chosen status (Unqualified
or Qualified — ruling 44 lets a campaign reach an Unqualified lead), with no
reason set; or a Contact typed Prospect holding a phone, at a chosen stage
(Prospect, Engaged, Opportunity), with ``doNotCall`` and
``phoneNumberIsOptedOut`` false. Nobody who has Declined a call from any
campaign is selected. A converted lead IS its Contact (one person, one row), so
the Contact's flags govern and the lead's phone is the fallback number. *Build
the list* reconciles the campaign's Planned touches to the selection, as the
postcard kind does; it needs no piece count and no vendor — the Planned
touches ARE the call list.

**Sign off** stamps the signer and starts the list (Running): no worker runs a
call campaign, people do. The application completes the campaign when its last
Planned row is recorded.

**Who calls (ruling 36).** The members of the teams named on the campaign — the
Marketing Admin Team when it names none — and administrators. When a campaign's
rows are assigned to callers, each caller sees only their own rows. The gate
reads the campaign under the org-wide API key (it decides who may look; the
Mentor Role reads no campaign), and everything the caller does runs **as the
caller**: the call list and the targets are read, and the outcome written onto
the touch, as the signed-in user, so the CRM records who called.

**What an outcome does.** *No answer*: the touch is Done (and *Call again*
plans a fresh row). *Interested* on a lead: the caller is asked for an email and
a website, and either one **converts the lead** (ruling 47) — a business lead to
a Company typed Prospect and the Contact for the email (ruling 52), through
``campaigns.conversion``; the touch then names the new Contact or Company too.
With neither, Interested is recorded on the call, the lead stays a lead, the
screen says why, and *Call again* is offered as for No answer. *Interested* on
a Contact changes no stage. *Declined*: Done, and a lead stops being worked by
``Declined`` (never over another reason); a Contact has no reason field, and the
touch's outcome is what keeps it out of every later list. The touch is the
caller's own act; the conversion, the reason, the fresh row and the campaign's
completion are the application's consequences and are written under the API
client — the Mentor Role reads leads but does not edit them (ruling 36).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.crm_upsert import CONTACT_TYPE_FIELD, PROSPECT_TYPE
from core.espo import EspoApi, EspoError

from . import config as cfg
from .audience import audience_result as _audience_result
from . import service
from .attribution import holds_relationship
from .conversion import ConversionRefused, Details, can_convert, convert_lead
from core.crm_upsert import CompanyConflict
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.calls")

_PAGE = 200

#: What a call campaign may select: leads at an open status (ruling 44) and
#: Contacts typed Prospect at a stage.
CALLABLE_STATUSES = cfg.LEAD_OPEN_STATUSES
CALLABLE_STAGES = cfg.STAGES
DEFAULT_RULE: dict[str, Any] = {"statuses": list(cfg.LEAD_OPEN_STATUSES), "stages": []}

CONTACT_SELECT = (
    f"id,name,firstName,lastName,phoneNumber,phoneNumberIsOptedOut,doNotCall,{CONTACT_TYPE_FIELD},"
    "cFunnelStage,accountName"
)

UNRECORDED_WARNING = ("Record every call you make. A call that is not recorded here reads as never "
                      "contacted, and the person may be called again.")


def _crm_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --- the selection rule -------------------------------------------------------------

def normalise_rule(rule: Optional[dict[str, Any]]) -> dict[str, Any]:
    rule = rule or {}
    statuses = [s for s in (rule.get("statuses") or []) if s in CALLABLE_STATUSES]
    stages = [s for s in (rule.get("stages") or []) if s in CALLABLE_STAGES]
    if not statuses and not stages:
        statuses = list(DEFAULT_RULE["statuses"])
    return {"statuses": statuses, "stages": stages}


def rule_summary(rule: dict[str, Any]) -> str:
    parts = []
    if rule["statuses"]:
        parts.append(f"leads at {' or '.join(rule['statuses'])}")
    if rule["stages"]:
        parts.append(f"Contacts typed Prospect at {' or '.join(rule['stages'])}")
    joined = ' and '.join(parts)
    return (f"{joined[:1].upper() + joined[1:]} holding a phone number — not opted out, "
            "not do-not-call, still being worked, and never Declined a call (ruling 20).")


def _target_key(t: dict[str, Any]) -> Optional[str]:
    if t.get("prospectId"):
        return f"prospect:{t['prospectId']}"
    if t.get("contactId"):
        return f"contact:{t['contactId']}"
    if t.get("companyId"):
        return f"company:{t['companyId']}"
    return None


async def declined_targets(client: EspoApi) -> set[str]:
    """Every target that has Declined a call from any campaign — "not Declined
    anywhere" (§ 3.4)."""
    out: set[str] = set()
    offset = 0
    while True:
        page = await client.list(
            cfg.TOUCH, select="id,prospectId,contactId,companyId", max_size=_PAGE, offset=offset,
            where=[{"type": "equals", "attribute": "outcome", "value": cfg.OUTCOME_DECLINED}],
        )
        batch = page.get("list", [])
        for t in batch:
            key = _target_key(t)
            if key:
                out.add(key)
        if len(batch) < _PAGE or offset >= 20000:
            break
        offset += _PAGE
    return out


def _callable_contact(c: dict[str, Any]) -> bool:
    types = c.get(CONTACT_TYPE_FIELD) or []
    return (PROSPECT_TYPE in types and not holds_relationship(c)
            and not c.get("doNotCall") and not c.get("phoneNumberIsOptedOut"))


async def select_targets(client: EspoApi, rule: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """The people a call campaign would ring, each as
    ``{key, kind, id, name, phone, stage}`` (``stage`` is what the touch
    records: the lead's status, or the Contact's stage)."""
    rule = normalise_rule(rule)
    declined = await declined_targets(client)
    contacts: dict[str, dict[str, Any]] = {}
    if rule["stages"]:
        try:
            for c in await service._page_all(
                client, cfg.CONTACT, select=CONTACT_SELECT,
                where=[{"type": "in", "attribute": "cFunnelStage", "value": rule["stages"]}],
                order_by="createdAt", order="asc", limit=10000,
            ):
                contacts[c["id"]] = c
        except EspoError as exc:
            # A CRM without the stage on Contact (or a refused list) selects
            # leads only — logged, never fatal.
            log.warning("call selection: Contacts typed Prospect unreadable: %s", exc)
    targets: list[dict[str, Any]] = []
    taken: set[str] = set()
    # A Contact whose lead stopped being worked (Do Not Contact, Declined…)
    # stopped with it, whatever stage the Contact holds.
    for p in await service._page_all(
        client, cfg.PROSPECT, select="id,sideExit,promotedContactId",
        where=[{"type": "isNotNull", "attribute": "sideExit"}], limit=20000,
    ):
        if p.get("sideExit") and p.get("promotedContactId"):
            taken.add(f"contact:{p['promotedContactId']}")

    if rule["statuses"]:
        leads = await service._page_all(
            client, cfg.PROSPECT, select=cfg.PROSPECT_SELECT,
            where=[{"type": "in", "attribute": "leadStatus", "value": rule["statuses"]},
                   {"type": "isNull", "attribute": "sideExit"}],
            order_by="createdAt", order="asc", limit=10000,
        )
    else:
        leads = []
    for p in leads:
        if p.get("sideExit") or p.get("leadStatus") not in rule["statuses"]:
            continue
        contact_id = p.get("promotedContactId")
        if contact_id:
            # Converted already (the status was not moved): the person is the
            # Contact, whose flags govern; the lead's phone is the fallback.
            key = f"contact:{contact_id}"
            if key in taken or key in declined or f"prospect:{p['id']}" in declined:
                continue
            try:
                contact = contacts.get(contact_id) or await client.get(cfg.CONTACT, contact_id, select=CONTACT_SELECT)
            except EspoError:
                contact = None
            if contact and contact.get("id") and _callable_contact(contact):
                phone = contact.get("phoneNumber") or p.get("phone")
                if phone:
                    targets.append({"key": key, "kind": "contact", "id": contact["id"],
                                    "name": contact.get("name") or p.get("businessName") or "",
                                    "phone": phone, "stage": contact.get("cFunnelStage")})
                    taken.add(key)
            continue
        key = f"prospect:{p['id']}"
        if not p.get("phone") or key in declined:
            continue
        targets.append({"key": key, "kind": "prospect", "id": p["id"],
                        "name": p.get("businessName") or p.get("name") or "",
                        "phone": p["phone"], "stage": p.get("leadStatus")})

    for c in contacts.values():
        key = f"contact:{c['id']}"
        if key in taken or key in declined or not _callable_contact(c):
            continue
        phone = c.get("phoneNumber") or c.get("_fallbackPhone")
        if not phone:
            continue
        targets.append({"key": key, "kind": "contact", "id": c["id"], "name": c.get("name") or "",
                        "phone": phone, "stage": c.get("cFunnelStage")})
        taken.add(key)
    return targets


# --- build the list and sign off ---------------------------------------------------------

async def build_list(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any],
                     rule: Optional[dict[str, Any]], audience: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Reconcile this campaign's Planned touches to the selection: a new target
    gains a Planned row, a dropped target's Planned row is Cancelled, a row
    already recorded is never touched. Draft moves to Awaiting sign-off."""
    if campaign.get("campaignKind") != cfg.KIND_CALL:
        raise CampaignError("This is not a call campaign.")
    status = campaign.get("campaignStatus") or cfg.STATUS_DRAFT
    if status not in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING):
        raise CampaignError(f"The list cannot be rebuilt once the campaign is {status}.")
    rule = normalise_rule(rule)
    # A campaign that names a list sends to it (build plan § 7c); else its rule.
    targets = audience["targets"] if audience else await select_targets(api_client, rule)
    planned: dict[str, dict[str, Any]] = {}
    for t in await service.campaign_touches(api_client, campaign["id"]):
        key = _target_key(t)
        if t.get("touchStatus") == cfg.TOUCH_PLANNED and key:
            planned[key] = t
    wanted = {t["key"]: t for t in targets}
    team_ids = campaign_team_ids(await api_client.get(cfg.CAMPAIGN, campaign["id"]))
    created = kept = cancelled = 0
    for key, touch in planned.items():
        if key not in wanted:
            await api_client.update(cfg.TOUCH, touch["id"], {"touchStatus": cfg.TOUCH_CANCELLED})
            cancelled += 1
    for key, target in wanted.items():
        if key in planned:
            kept += 1
            continue
        await api_client.create(cfg.TOUCH, _planned_payload(campaign, target, team_ids))
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


def _planned_payload(campaign: dict[str, Any], target: dict[str, Any],
                     team_ids: Optional[list[str]] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": f"{campaign.get('name') or 'Campaign'} — {target['name']}"[:255],
        "channel": cfg.KIND_CALL,
        "touchStatus": cfg.TOUCH_PLANNED,
        "plannedAt": _crm_now(),
        "outreachCampaignId": campaign["id"],
    }
    payload[f"{target['kind']}Id"] = target["id"]
    if team_ids:
        payload["teamsIds"] = list(team_ids)
    return payload


async def sign_off(api_client: EspoApi, user_client: EspoApi, campaign: dict[str, Any], *,
                   user_name: str) -> dict[str, Any]:
    """Ruling 13's gate for a call list: no piece count and no cost, one
    confirmation. The list starts at once — people run it, not the worker."""
    if campaign.get("campaignKind") != cfg.KIND_CALL:
        raise CampaignError("This is not a call campaign.")
    if campaign.get("campaignStatus") not in (cfg.STATUS_AWAITING, cfg.STATUS_DRAFT):
        raise CampaignError(f"A campaign at {campaign.get('campaignStatus')} cannot be signed off.")
    touches = await service.campaign_touches(api_client, campaign["id"])
    rows = sum(1 for t in touches if t.get("touchStatus") == cfg.TOUCH_PLANNED)
    if rows == 0:
        raise CampaignError("Build the list first — there is nobody on it to call.")
    now = _crm_now()
    return await service.stamp_campaign(user_client, api_client, campaign["id"], {
        "signedOffByName": user_name[:255], "signedOffAt": now,
        "campaignStatus": cfg.STATUS_RUNNING, "runStartedAt": now,
    })


# --- who may call (ruling 36) -------------------------------------------------------------

def campaign_team_ids(campaign: Optional[dict[str, Any]]) -> list[str]:
    """The campaign's own team ids (a whole record read carries them)."""
    return sorted(i for i in ((campaign or {}).get("teamsIds") or []) if i)


async def ensure_touch_teams(api_client: EspoApi, touch_id: str, team_ids: list[str]) -> bool:
    """Give a call record its campaign's teams before the caller writes it.

    A role at Assignment Permission *team* (the Mentor Role) may not save a
    record that has neither a team nor an assigned user — EspoCRM refuses it
    as an assignment failure even when the save changes no assignment
    (``Acl/AssignmentChecker/Helper::isPermittedTeamsEmpty``, read on crm-test
    10-18-26 after the Phase 3 pass hit it). Teams already on the record are
    not re-checked on an update, so a record carrying the campaign's teams
    saves for every caller the campaign admits. Merge-only, under the API
    client. Returns True when it wrote."""
    if not team_ids:
        return False
    whole = await api_client.get(cfg.TOUCH, touch_id)
    have = list((whole or {}).get("teamsIds") or [])
    if (whole or {}).get("assignedUserId") or set(team_ids) <= set(have):
        return False
    await api_client.update(cfg.TOUCH, touch_id, {"teamsIds": sorted(set(have) | set(team_ids))})
    return True


def campaign_team_names(campaign: dict[str, Any], default: list[str]) -> list[str]:
    names = campaign.get("teamsNames") or {}
    if isinstance(names, dict):
        teams = [n for n in names.values() if n]
    else:
        teams = [n for n in names if n]
    return sorted(teams) if teams else list(default)


def may_call(user: dict[str, Any], teams: list[str]) -> bool:
    if user.get("isAdmin"):
        return True
    return bool(set(user.get("teams") or []) & set(teams))


async def may_call_any(api_client: EspoApi, user: dict[str, Any], settings: Settings) -> bool:
    """Whether a Running call campaign names a team the user is in (ruling 36)
    — what decides the portal's *Campaign calls* tile for a caller outside the
    Marketing Admin Team (ruling 114). Best-effort: a CRM failure answers False,
    so a portal load never fails on it."""
    try:
        campaigns = await running_call_campaigns(api_client)
    except EspoError as exc:
        log.warning("campaign calls tile: could not read the running call campaigns: %s", exc)
        return False
    default = settings.campaigns_allowed_teams_list
    return any(may_call(user, campaign_team_names(c, default)) for c in campaigns)


async def running_call_campaigns(api_client: EspoApi) -> list[dict[str, Any]]:
    """Every Running call campaign, each read whole (its teams come with a
    record read)."""
    page = await api_client.list(
        cfg.CAMPAIGN, select="id,name", max_size=_PAGE,
        where=[{"type": "equals", "attribute": "campaignKind", "value": cfg.KIND_CALL},
               {"type": "equals", "attribute": "campaignStatus", "value": cfg.STATUS_RUNNING}],
    )
    out = []
    for row in page.get("list", []):
        try:
            full = await api_client.get(cfg.CAMPAIGN, row["id"])
        except EspoError as exc:
            log.warning("call campaign %s unreadable: %s", row.get("id"), exc)
            continue
        if full and full.get("id"):
            out.append(full)
    return out


async def _target_detail(client: EspoApi, touch: dict[str, Any]) -> dict[str, Any]:
    """Who to ring for one row, read as the caller. Unreadable reads as a
    message, never an error that empties the list."""
    try:
        if touch.get("prospectId"):
            p = await client.get(cfg.PROSPECT, touch["prospectId"], select=cfg.PROSPECT_SELECT)
            person = " ".join(x for x in (p.get("firstName"), p.get("lastName")) if x)
            return {"kind": "prospect", "name": p.get("businessName") or p.get("name") or "",
                    "person": person, "phone": p.get("phone") or "", "stage": p.get("leadStatus"),
                    "city": p.get("mailingAddressCity") or "",
                    # What the Interested form may prefill (ruling 47).
                    "firstName": p.get("firstName") or "", "lastName": p.get("lastName") or "",
                    "hasEmail": bool(p.get("email")), "hasWebsite": bool(p.get("website")),
                    # The caller reads the lead, so its own email and website
                    # prefill the Interested boxes (found on the lead model's
                    # live pass: a hint alone was missed).
                    "email": p.get("email") or "", "website": p.get("website") or "",
                    "business": bool((p.get("businessName") or "").strip())}
        if touch.get("contactId"):
            c = await client.get(cfg.CONTACT, touch["contactId"], select=CONTACT_SELECT)
            return {"kind": "contact", "name": c.get("accountName") or c.get("name") or "",
                    "person": c.get("name") or "", "phone": c.get("phoneNumber") or "",
                    "stage": c.get("cFunnelStage"), "city": "",
                    "doNotCall": bool(c.get("doNotCall") or c.get("phoneNumberIsOptedOut"))}
    except EspoError as exc:
        return {"kind": "unknown", "name": touch.get("name") or "", "person": "", "phone": "",
                "error": f"The record could not be read as you ({exc})."}
    return {"kind": "unknown", "name": touch.get("name") or "", "person": "", "phone": ""}


async def call_list(api_client: EspoApi, user_client: EspoApi, user: dict[str, Any],
                    settings: Settings) -> dict[str, Any]:
    """The Calls screen: every Planned touch of every Running call campaign the
    user may call for (ruling 36), with the number to ring."""
    default = settings.campaigns_allowed_teams_list
    campaigns = await running_call_campaigns(api_client)
    allowed, others = [], []
    for c in campaigns:
        teams = campaign_team_names(c, default)
        (allowed if may_call(user, teams) else others).append({**c, "_teams": teams})
    rows: list[dict[str, Any]] = []
    for c in allowed:
        touches = [t for t in await service.campaign_touches(user_client, c["id"])
                   if t.get("touchStatus") == cfg.TOUCH_PLANNED]
        if any(t.get("assignedUserId") for t in touches):
            touches = [t for t in touches if not t.get("assignedUserId")
                       or t.get("assignedUserId") == user.get("userId")]
        for t in touches:
            rows.append({"touchId": t["id"], "campaignId": c["id"], "campaignName": c.get("name") or "",
                         "plannedAt": t.get("plannedAt"), **await _target_detail(user_client, t)})
    message = ""
    if not allowed:
        if others:
            names = sorted({n for c in others for n in c["_teams"]})
            message = ("No running call campaign names a team you are in. The running call "
                       f"campaigns are for: {', '.join(names)}.")
        else:
            message = "No call campaign is running."
    return {
        "warning": UNRECORDED_WARNING,
        "message": message,
        "campaigns": [{"id": c["id"], "name": c.get("name"), "teams": c["_teams"],
                       "brief": c.get("description") or ""} for c in allowed],
        "rows": rows,
    }


# --- recording an outcome ------------------------------------------------------------------

async def record_outcome(api_client: EspoApi, user_client: EspoApi, user: dict[str, Any], touch_id: str, *,
                         outcome: str, notes: str, call_again: bool, settings: Settings,
                         details: Optional[Details] = None) -> dict[str, Any]:
    """One call's outcome. The touch is written as the caller first — a refused
    grant changes nothing — then the consequences under the API client, each
    best-effort and reported. ``details`` is what the caller typed for an
    Interested lead: email, website, the person's name (ruling 47)."""
    details = details or Details()
    if outcome not in cfg.CALL_OUTCOMES:
        raise CampaignError("The outcome is No answer, Interested or Declined.")
    if call_again and outcome == cfg.OUTCOME_DECLINED:
        raise CampaignError("Call again goes with No answer, or with Interested when the lead could not be converted.")
    touch = await user_client.get(cfg.TOUCH, touch_id, select=cfg.TOUCH_SELECT)
    if not touch or not touch.get("id"):
        raise LookupError("Call not found.")
    if touch.get("channel") != cfg.KIND_CALL:
        raise CampaignError("That row is not a call.")
    if touch.get("touchStatus") != cfg.TOUCH_PLANNED:
        raise CampaignError(f"That call was already recorded ({touch.get('outcome') or touch.get('touchStatus')}). "
                            "Reload the list.")
    if touch.get("assignedUserId") and touch["assignedUserId"] != user.get("userId") and not user.get("isAdmin"):
        raise PermissionError("That call is assigned to another caller.")
    campaign = await api_client.get(cfg.CAMPAIGN, touch.get("outreachCampaignId") or "")
    if not campaign or campaign.get("campaignStatus") != cfg.STATUS_RUNNING:
        raise CampaignError("That campaign is not running, so its calls cannot be recorded.")
    teams = campaign_team_names(campaign, settings.campaigns_allowed_teams_list)
    if not may_call(user, teams):
        raise PermissionError(f"This campaign's calls are made by the {', '.join(teams)} team.")

    target = await _target_detail(user_client, touch)
    now = _crm_now()
    team_ids = campaign_team_ids(campaign)
    await ensure_touch_teams(api_client, touch_id, team_ids)
    await user_client.update(cfg.TOUCH, touch_id, {
        "touchStatus": cfg.TOUCH_DONE, "outcome": outcome, "doneAt": now,
        "callNotes": (notes or "").strip() or None, "calledPhone": (target.get("phone") or "")[:100] or None,
        "stageAtTouch": target.get("stage") or None,
    })
    result: dict[str, Any] = {"touchId": touch_id, "outcome": outcome, "consequences": [], "warnings": []}

    async def best_effort(label: str, coro) -> None:
        try:
            await coro
            result["consequences"].append(label)
        except EspoError as exc:
            log.warning("call %s: %s failed: %s", touch_id, label, exc)
            result["warnings"].append(f"{label} could not be written ({exc}).")

    converted = False
    if touch.get("prospectId") and outcome in (cfg.OUTCOME_INTERESTED, cfg.OUTCOME_DECLINED):
        converted = await apply_outcome(
            api_client, touch["prospectId"], outcome,
            f"Declined on a call from the campaign {campaign.get('name') or ''}".strip(),
            details=details, touch_id=touch_id, campaign_id=touch.get("outreachCampaignId") or campaign.get("id"),
            result=result, now=now)
        if converted and call_again:
            call_again = False
            result["warnings"].append("The lead converted, so no second call was planned.")
    if call_again:
        fresh: dict[str, Any] = {
            "name": touch.get("name") or f"{campaign.get('name') or 'Campaign'} — {target.get('name') or ''}"[:255],
            "channel": cfg.KIND_CALL, "touchStatus": cfg.TOUCH_PLANNED, "plannedAt": now,
            "outreachCampaignId": campaign["id"],
        }
        for key in ("prospectId", "contactId", "companyId"):
            if touch.get(key):
                fresh[key] = touch[key]
        if touch.get("assignedUserId"):
            fresh["assignedUserId"] = touch["assignedUserId"]
        if team_ids:
            fresh["teamsIds"] = team_ids
        await best_effort("planned again", api_client.create(cfg.TOUCH, fresh))
    remaining = sum(1 for t in await service.campaign_touches(api_client, campaign["id"])
                    if t.get("touchStatus") == cfg.TOUCH_PLANNED)
    if remaining == 0:
        await best_effort("campaign complete", api_client.update(cfg.CAMPAIGN, campaign["id"], {
            "campaignStatus": cfg.STATUS_COMPLETE, "runCompletedAt": now}))
    result["remaining"] = remaining
    result["campaignName"] = campaign.get("name") or ""
    return result


async def apply_outcome(api_client: EspoApi, lead_id: str, outcome: str, note: str, *,
                        details: Optional[Details] = None, touch_id: str = "",
                        campaign_id: Optional[str] = None, result: Optional[dict[str, Any]] = None,
                        now: str = "") -> bool:
    """What an outcome does to the LEAD, shared by a campaign call and a
    personal call from the lead's page (build plan § 7e.5; ruling 115: one kind
    of call, one vocabulary): *Interested* converts under the API client
    (ruling 47 — an email or a website; otherwise the result says why in
    words and the lead stays a lead); *Declined* stops the lead by the
    Declined side exit with ``note``, never over another exit; anything else
    changes nothing. Then the ladder places the level again. Best-effort
    throughout — the caller has already written the touch. Returns True when
    the lead converted. ``result`` collects ``consequences``, ``warnings``,
    ``notConverted`` and ``converted`` for the caller's answer."""
    result = result if result is not None else {"consequences": [], "warnings": []}
    details = details or Details()
    now = now or _crm_now()
    converted = False
    if outcome == cfg.OUTCOME_INTERESTED:
        converted = await _convert_on_interest(api_client, lead_id, details, result,
                                               touch_id=touch_id, campaign_id=campaign_id)
    elif outcome == cfg.OUTCOME_DECLINED:
        try:
            prospect = await api_client.get(cfg.PROSPECT, lead_id, select="id,sideExit")
        except EspoError as exc:
            prospect = {}
            result["warnings"].append(f"The lead could not be read ({exc}); Declined is recorded on the call only.")
        if prospect.get("sideExit"):
            result["warnings"].append(
                f"The lead had already stopped being worked ({prospect['sideExit']}); "
                "Declined is recorded on the call only.")
        elif prospect.get("id"):
            try:
                await api_client.update(cfg.PROSPECT, lead_id, {
                    "sideExit": cfg.EXIT_DECLINED, "sideExitAt": now, "sideExitNote": (note or "").strip() or None})
                result["consequences"].append("stopped by Declined")
            except EspoError as exc:
                log.warning("lead %s: stopped by Declined failed: %s", lead_id, exc)
                result["warnings"].append(f"stopped by Declined could not be written ({exc}).")
    else:
        return False
    # The ladder (§ 7e.3): an email or website given on the call, or the
    # conversion it caused, changes what the level should be.
    from .ladder import after_write
    await after_write(lead_id, client=api_client)
    return converted


async def _convert_on_interest(api_client: EspoApi, lead_id: str, details: Details, result: dict[str, Any], *,
                               touch_id: str = "", campaign_id: Optional[str] = None) -> bool:
    """Interested on a lead (ruling 47): an email or a website converts it —
    under the API client, best-effort and reported. Returns True when it
    converted. Without either, the result says why and the lead stays a lead."""
    try:
        lead = await api_client.get(cfg.PROSPECT, lead_id, select=cfg.PROSPECT_SELECT)
    except EspoError as exc:
        result["warnings"].append(f"The lead could not be read to convert it ({exc}).")
        return False
    if not lead or not lead.get("id"):
        result["warnings"].append("The lead is gone, so it could not be converted.")
        return False
    if lead.get("leadStatus") == cfg.LEAD_CONVERTED:
        result["consequences"].append("already converted")
        return True
    if not can_convert(lead, details):
        result["notConverted"] = (
            "Interested is recorded, but the lead stays a lead: it converts only with an email"
            + (" or a website" if (lead.get("businessName") or "").strip() else "")
            + " (ruling 47). Call again to ask for one.")
        return False
    try:
        done = await convert_lead(api_client, lead, details, campaign_id=campaign_id)
    except CompanyConflict as exc:
        result["notConverted"] = (
            f"Interested is recorded, but the lead was not converted: a company named {exc.name} "
            f"already exists at a different web address ({exc.existing_website}). Settle which company "
            "this is in the CRM, then convert the lead there.")
        return False
    except (ConversionRefused, EspoError) as exc:
        result["warnings"].append(f"The lead could not be converted ({exc}).")
        return False
    result["consequences"].append("lead converted")
    result["converted"] = done.result()
    # The touch names what the call made, so the campaign's Converted count
    # can read it from the touch (campaigns/reporting.py).
    links = {k: v for k, v in (("contactId", done.contact_id), ("companyId", done.company_id)) if v}
    if links and touch_id:
        try:
            await api_client.update(cfg.TOUCH, touch_id, links)
        except EspoError as exc:
            result["warnings"].append(f"The call could not be linked to the new records ({exc}).")
    return True
