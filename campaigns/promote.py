"""Promote this event, and the event's Campaigns tab (build plan § 7e.9,
ruling 97; step M10).

*Promote this event* makes one Draft campaign per ticked channel, through the
same create path as + New campaign, each linked to the event
(``COutreachCampaign.events``), carrying a link that opens the event's page and
sending to the list chosen for it. Building and signing off stay manual,
campaign by campaign.

The roll-up is one row per campaign — the ones linked to the event, plus any
other campaign a registration for this event is credited to ("not linked") —
with Reached, Registered and Attended, and a *No campaign* row. A registration
is credited to the campaign that first brought it: the public forms write
``CEventRegistration.outreachCampaignId`` on the create only (ruling 27), so
nothing here decides that again.

Dark behind ``EVENT_PROMOTE`` (read per request), which needs Marketing
Management and Campaign lists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoError

from . import config as cfg
from . import service
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.promote")

#: The channels the form offers, in its order, and which are ticked at first
#: (ruling 97 names the email, text and postcard campaigns; a call is offered).
CHANNELS: tuple[str, ...] = (cfg.KIND_EMAIL, cfg.KIND_SMS, cfg.KIND_POSTCARD, cfg.KIND_CALL)
TICKED: tuple[str, ...] = (cfg.KIND_EMAIL, cfg.KIND_SMS, cfg.KIND_POSTCARD)

#: The words each channel goes by on the screen and in a default name.
CHANNEL_WORDS = {cfg.KIND_EMAIL: "Email", cfg.KIND_SMS: "Text", cfg.KIND_POSTCARD: "Postcard",
                 cfg.KIND_CALL: "Calls"}

#: A touch that reached its person: sent, delivered, returned, or a call made.
REACHED_STATUSES = (cfg.TOUCH_SENT, cfg.TOUCH_DELIVERED, cfg.TOUCH_RETURNED, cfg.TOUCH_DONE)

ATTENDED = "Attended"
NO_CAMPAIGN = "none"
MEASURES = ("reached", "registered", "attended")

#: The registration fields the roll-up reads. The campaign's is added only
#: when the CRM carries it.
_REG_SELECT = "id,name,contactId,contactName,email,firstName,lastName,attendanceStatus"
_REG_CAMPAIGN = "outreachCampaignId"
_CAMPAIGN_SELECT = "id,name,campaignKind,campaignStatus,pieceCount"


def is_on(settings: Settings) -> bool:
    """The one test for M10's event half."""
    return bool(getattr(settings, "event_promote", False) and settings.campaigns_enabled
                and settings.campaign_lists)


def why_off(settings: Settings) -> str:
    """In words, why Promote this event is not available; empty when it is."""
    if not getattr(settings, "event_promote", False):
        return "Promote this event is switched off (EVENT_PROMOTE at /setup)."
    if not settings.campaigns_enabled:
        return "Marketing Management is switched off, so no campaign can be made."
    if not settings.campaign_lists:
        return "Campaign lists are switched off, so a campaign has no list to send to."
    return ""


def channel_switch(settings: Settings, kind: str) -> str:
    """Why this deployment cannot make a campaign of this channel; empty when it can."""
    if kind in cfg.kinds_built(settings.campaigns_calls, settings.campaigns_sms, settings.campaigns_email):
        return ""
    switch = {cfg.KIND_CALL: "CAMPAIGNS_CALLS", cfg.KIND_SMS: "CAMPAIGNS_SMS",
              cfg.KIND_EMAIL: "CAMPAIGNS_EMAIL"}.get(kind, "")
    return (f"{CHANNEL_WORDS.get(kind, kind)} campaigns are switched off on this deployment"
            + (f" ({switch} at /setup)." if switch else "."))


def default_name(event_name: str, kind: str) -> str:
    return f"{(event_name or 'Event').strip()} — {CHANNEL_WORDS.get(kind, kind)}"[:150]


def link_name(event_name: str) -> str:
    return f"{(event_name or 'Event').strip()} — the event's page"[:200]


@dataclass
class Channel:
    kind: str
    name: str
    list_id: str


def check_channels(settings: Settings, channels: list[Channel], lists: dict[str, Optional[dict[str, Any]]]
                   ) -> list[Channel]:
    """Every refusal before anything is written: a promotion makes all its
    campaigns or none. ``lists`` maps each chosen list id to its row."""
    if not channels:
        raise CampaignError("Tick at least one channel.")
    seen: set[str] = set()
    out: list[Channel] = []
    for ch in channels:
        words = CHANNEL_WORDS.get(ch.kind)
        if not words:
            raise CampaignError(f"\"{ch.kind}\" is not a channel an event can be promoted by.")
        if ch.kind in seen:
            raise CampaignError(f"{words} is ticked twice.")
        seen.add(ch.kind)
        refusal = channel_switch(settings, ch.kind)
        if refusal:
            raise CampaignError(refusal)
        name = (ch.name or "").strip()
        if not name:
            raise CampaignError(f"The {words.lower()} campaign needs a name.")
        if not ch.list_id:
            raise CampaignError(f"Choose the list the {words.lower()} campaign sends to.")
        row = lists.get(ch.list_id)
        if not row:
            raise CampaignError(f"The list chosen for the {words.lower()} campaign no longer exists. "
                                "Choose another.")
        if row.get("status") != "active":
            raise CampaignError(f"\"{row.get('name')}\" is retired — choose an active list for the "
                                f"{words.lower()} campaign.")
        out.append(Channel(kind=ch.kind, name=name[:150], list_id=ch.list_id))
    return out


async def create_all(client, store, *, event: dict[str, Any], channels: list[Channel], user_id: str,
                     actor: str, settings: Settings, admin_factory=None) -> list[dict[str, Any]]:
    """Make each campaign as the signed-in user. Checked first by
    ``check_channels``; a CRM failure part-way leaves the campaigns already
    made (each a Draft, which staff may cancel) and reports them."""
    made: list[dict[str, Any]] = []
    for ch in channels:
        try:
            created = await service.create_campaign(
                client, {"name": ch.name, "campaignKind": ch.kind}, user_id=user_id,
                calls_on=settings.campaigns_calls, sms_on=settings.campaigns_sms,
                email_on=settings.campaigns_email)
        except (CampaignError, EspoError) as exc:
            if made:
                exc.args = (f"{exc} — made before it stopped: "
                            + ", ".join(f"\"{m['name']}\"" for m in made) + ".",)
            raise
        row = {"id": created["id"], "name": created.get("name") or ch.name, "kind": ch.kind,
               "listId": ch.list_id, "warnings": []}
        try:
            await service.set_relations(client, created["id"], {cfg.LINK_EVENTS: [event["id"]]},
                                        admin_factory=admin_factory)
        except (CampaignError, EspoError) as exc:
            log.warning("promote: %s not linked to event %s: %s", created["id"], event["id"], exc)
            row["warnings"].append(f"It could not be linked to the event ({exc}); link it on its Overview.")
        try:
            link = await store.create_link(campaign_id=created["id"], name=link_name(event.get("name") or ""),
                                           destination_kind=cfg.DEST_EVENT, destination_target=event["id"],
                                           destination_slug=event.get("slug"), created_by=actor)
            row["linkToken"] = link["token"]
        except Exception as exc:  # noqa: BLE001 — the campaign stands; the link can be made by hand
            log.warning("promote: link for %s not made: %s", created["id"], exc)
            row["warnings"].append("Its link to the event's page could not be made; add it on the Links tab.")
        try:
            await store.set_campaign_audience(created["id"], ch.list_id, include_every_contact=False, actor=actor)
        except Exception as exc:  # noqa: BLE001
            log.warning("promote: list for %s not set: %s", created["id"], exc)
            row["warnings"].append("Its list could not be set; choose it on the Audience and content tab.")
        made.append(row)
    return made


# --- the roll-up ---------------------------------------------------------------------

async def _registration_campaign_field(api) -> bool:
    try:
        fields = await api.metadata(f"entityDefs.{cfg.EVENT_REGISTRATION}.fields")
    except EspoError as exc:
        log.warning("registration fields unreadable: %s", exc)
        return False
    return isinstance(fields, dict) and "outreachCampaign" in fields


async def _registrations(api, event_id: str, with_campaign: bool) -> list[dict[str, Any]]:
    select = _REG_SELECT + ("," + _REG_CAMPAIGN if with_campaign else "")
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await api.list(cfg.EVENT_REGISTRATION, select=select, max_size=200, offset=offset,
                              where=[{"type": "equals", "attribute": "eventId", "value": event_id}],
                              order_by="createdAt", order="asc")
        batch = page.get("list", [])
        rows.extend(batch)
        if len(batch) < 200 or len(rows) >= 10000:
            break
        offset += 200
    if not with_campaign:
        # A CRM without the credit field: nobody is credited, whatever comes back.
        rows = [{k: v for k, v in r.items() if k != _REG_CAMPAIGN} for r in rows]
    return rows


async def _linked(api, event_id: str) -> list[dict[str, Any]]:
    """The campaigns linked to the event: one page of 200, which no event
    approaches (a related read takes no offset)."""
    page = await api.list_related(cfg.EVENT, event_id, cfg.EVENT_CAMPAIGNS_LINK, select=_CAMPAIGN_SELECT,
                                  max_size=200)
    return [r for r in page.get("list", []) if r.get("id")]


def _person(reg: dict[str, Any]) -> str:
    name = " ".join(x for x in ((reg.get("firstName") or "").strip(), (reg.get("lastName") or "").strip()) if x)
    return name or reg.get("contactName") or reg.get("name") or reg.get("email") or "(no name)"


def _target(t: dict[str, Any]) -> str:
    return t.get("contactName") or t.get("prospectName") or t.get("companyName") or t.get("name") or "(no name)"


def _reached(touches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in touches if t.get("touchStatus") in REACHED_STATUSES]


async def rollup(api, event_id: str) -> dict[str, Any]:
    """The Campaigns tab: read under the org-wide key, after the caller's own
    read of the event has gated the tab (the events Registrants rule — no team
    role reads registrations)."""
    credit = await _registration_campaign_field(api)
    regs = await _registrations(api, event_id, credit)
    linked = await _linked(api, event_id)
    campaigns: dict[str, dict[str, Any]] = {c["id"]: {**c, "_linked": True} for c in linked if c.get("id")}
    for r in regs:
        cid = r.get(_REG_CAMPAIGN)
        if cid and cid not in campaigns:
            try:
                row = await api.get(cfg.CAMPAIGN, cid, select=_CAMPAIGN_SELECT)
            except EspoError as exc:
                log.warning("credited campaign %s unreadable: %s", cid, exc)
                row = None
            campaigns[cid] = {**(row or {"id": cid, "name": "(a campaign since deleted)"}), "_linked": False}
    rows: list[dict[str, Any]] = []
    for cid, c in campaigns.items():
        mine = [r for r in regs if r.get(_REG_CAMPAIGN) == cid]
        try:
            reached = len(_reached(await service.campaign_touches(api, cid)))
        except EspoError as exc:
            log.warning("touches of %s unreadable: %s", cid, exc)
            reached = None
        rows.append({
            "campaignId": cid, "name": c.get("name") or "(unnamed)", "kind": c.get("campaignKind") or "",
            "channel": CHANNEL_WORDS.get(c.get("campaignKind") or "", c.get("campaignKind") or ""),
            "status": c.get("campaignStatus") or "", "linked": c["_linked"], "reached": reached,
            "registered": len(mine), "attended": sum(1 for r in mine if r.get("attendanceStatus") == ATTENDED),
        })
    rows.sort(key=lambda r: (not r["linked"], r["name"].lower()))
    none = [r for r in regs if not r.get(_REG_CAMPAIGN)]
    return {
        "creditAvailable": credit,
        "rows": rows,
        "noCampaign": {"registered": len(none),
                       "attended": sum(1 for r in none if r.get("attendanceStatus") == ATTENDED)},
        "totals": {"registered": len(regs), "attended": sum(1 for r in regs if r.get("attendanceStatus") == ATTENDED)},
    }


async def people(api, event_id: str, campaign_id: str, measure: str) -> dict[str, Any]:
    """The people behind one number on the Campaigns tab."""
    if measure not in MEASURES:
        raise CampaignError("Choose reached, registered or attended.")
    if measure == "reached":
        if campaign_id == NO_CAMPAIGN:
            raise CampaignError("Nobody is reached without a campaign.")
        touches = _reached(await service.campaign_touches(api, campaign_id))
        out = [{"name": _target(t), "detail": t.get("touchStatus") or "",
                "at": t.get("doneAt") or t.get("sentAt") or ""} for t in touches]
        return {"people": sorted(out, key=lambda p: p["name"].lower())}
    credit = await _registration_campaign_field(api)
    regs = await _registrations(api, event_id, credit)
    want = None if campaign_id == NO_CAMPAIGN else campaign_id
    if not credit and want:
        return {"people": []}
    mine = [r for r in regs if (r.get(_REG_CAMPAIGN) or None) == want]
    if measure == "attended":
        mine = [r for r in mine if r.get("attendanceStatus") == ATTENDED]
    out = [{"name": _person(r), "detail": r.get("attendanceStatus") or "", "email": r.get("email") or ""}
           for r in mine]
    return {"people": sorted(out, key=lambda p: p["name"].lower())}
