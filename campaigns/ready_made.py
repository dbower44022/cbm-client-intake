"""The ready-made lists (build plan § 7e.9 second half and § 7e.12 Draft 9;
ruling 99, step M8).

With ``CAMPAIGN_LISTS_ONLY`` on, every campaign sends to a list. Each kind's
old selection rule lives on as one of these five dynamic lists, marked
``system``: they cannot be deleted, renamed, changed or retired, and Copy
makes an ordinary static list of their members.

Four are written in the Include and Leave out conditions staff already read.
The fifth, *Dormant clients (a year)*, needs "every engagement closed, the
latest more than a year ago", which no single-record condition can say, so it
is a built-in selection (``audience.GROUP_BUILTIN``, Doug's ruling at the M8
plan, 10-27-26). The per-channel send checks — consent, exits, dead addresses,
one card per business — are not list conditions: ``audience.resolve_targets``
applies them at every build, whatever the list.

The ids are fixed so a campaign's choice survives a re-create. Migration 0039
creates the five rows; ``ensure`` re-creates any that are missing — the
sandbox reset empties ``audience_list`` every night, and a chapter's database
may predate the migration. ``ensure`` never touches a row that exists.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.config import Settings
from core.crm_upsert import CONTACT_TYPE_FIELD, PROSPECT_TYPE, RELATIONSHIP_TYPES

from . import config as cfg

log = logging.getLogger("cbm_intake.campaigns.ready_made")

ACTOR = "ready-made"

ID_POSTCARD = "ready-made-postcard-leads"
ID_EMAIL = "ready-made-opted-in-prospects"
ID_SMS = "ready-made-text-consent"
ID_CALL = "ready-made-leads-with-phone"
ID_DORMANT = "ready-made-dormant-clients"


def _match(type_: str, *conds: tuple[str, str, Any]) -> dict[str, Any]:
    return {"kind": "match", "type": type_,
            "conditions": [{"field": f, "op": o, "value": v} for f, o, v in conds]}


#: A contact who already holds a relationship is not marketed to as a
#: prospect (the information request and registration rule, kept by every
#: kind's old selection).
_HOLDS_RELATIONSHIP = _match("contact", (CONTACT_TYPE_FIELD, "anyOf", sorted(RELATIONSHIP_TYPES)))
_PROSPECT = (CONTACT_TYPE_FIELD, "anyOf", [PROSPECT_TYPE])

#: The five lists, in the order the picker shows them.
LISTS: tuple[dict[str, Any], ...] = (
    {"id": ID_POSTCARD, "name": "All leads for postcards", "kinds": (cfg.KIND_POSTCARD,),
     "notes": ("Every lead still being worked, Unqualified or Qualified. A postcard goes only to a lead "
               "with a usable, complete address, and never to a business that already had a card."),
     "recipe": {"include": [_match("lead", ("leadStatus", "in", list(cfg.LEAD_OPEN_STATUSES)))],
                "exclude": []}},
    {"id": ID_EMAIL, "name": "Opted-in prospects (Engaged and later)", "kinds": (cfg.KIND_EMAIL,),
     "notes": ("Contacts typed Prospect at Engaged or Opportunity who ticked the marketing email box. "
               "Anyone who is already a client, partner, funder or mentor is left out."),
     "recipe": {"include": [_match("contact", _PROSPECT,
                                   ("cFunnelStage", "in", [cfg.STAGE_ENGAGED, cfg.STAGE_OPPORTUNITY]),
                                   ("cMarketingOptIn", "isTrue", None))],
                "exclude": [_HOLDS_RELATIONSHIP]}},
    {"id": ID_SMS, "name": "Prospects with text consent", "kinds": (cfg.KIND_SMS,),
     "notes": ("Contacts typed Prospect, at any stage, who ticked the text-message box. A text goes only "
               "to a number not opted out. Anyone who already holds a relationship is left out."),
     "recipe": {"include": [_match("contact", _PROSPECT, ("cFunnelStage", "in", list(cfg.STAGES)),
                                   ("cSmsOptIn", "isTrue", None))],
                "exclude": [_HOLDS_RELATIONSHIP]}},
    {"id": ID_CALL, "name": "Leads and prospects with a phone", "kinds": (cfg.KIND_CALL,),
     "notes": ("Leads still being worked and contacts typed Prospect at any stage. A call goes only to "
               "someone with a phone number who has not asked not to be called or declined before."),
     "recipe": {"include": [_match("lead", ("leadStatus", "in", list(cfg.LEAD_OPEN_STATUSES))),
                            _match("contact", _PROSPECT, ("cFunnelStage", "in", list(cfg.STAGES)))],
                "exclude": [_HOLDS_RELATIONSHIP]}},
    {"id": ID_DORMANT, "name": "Dormant clients (a year)", "kinds": (cfg.KIND_EMAIL,),
     "notes": ("Clients whose engagements are all closed, the latest more than a year ago. An email goes "
               "only to those who ticked the marketing email box."),
     "recipe": {"include": [{"kind": "builtin", "type": "contact", "builtin": "dormant_clients", "days": 365}],
                "exclude": []}},
)

BY_ID = {d["id"]: d for d in LISTS}
#: The list a campaign built by its kind's old rule carries on with.
FOR_KIND = {cfg.KIND_POSTCARD: ID_POSTCARD, cfg.KIND_EMAIL: ID_EMAIL, cfg.KIND_SMS: ID_SMS,
            cfg.KIND_CALL: ID_CALL}

REFUSED = ("\"{name}\" is a ready-made list: it cannot be {what}. Copy it to make a list of your own, "
           "or build a new dynamic list.")


def is_system(row: Optional[dict[str, Any]]) -> bool:
    return bool((row or {}).get("system"))


def lists_only(settings: Settings) -> bool:
    """Every campaign sends to a list: the switch, which needs the lists."""
    return bool(getattr(settings, "campaign_lists_only", False) and settings.campaign_lists)


async def ensure(store) -> int:
    """Create every ready-made list that is missing. Returns how many were
    created. Idempotent; a row that exists is left exactly as it is."""
    created = 0
    for d in LISTS:
        if await store.get_list(d["id"]):
            continue
        await store.create_system_list(list_id=d["id"], name=d["name"], notes=d["notes"],
                                       recipe=d["recipe"], actor=ACTOR)
        created += 1
    if created:
        log.info("ready-made lists: %d created", created)
    return created


def built_by_rule(campaign: dict[str, Any]) -> bool:
    """A campaign whose last build came from its kind's rule box rather than a
    list (its stored selection is a rule, not ``{"list": …}``)."""
    import json

    text = campaign.get("selectionRule") or ""
    if not text:
        return False
    try:
        saved = json.loads(text)
    except (TypeError, ValueError):
        return False
    return isinstance(saved, dict) and "list" not in saved


async def adopt(store, campaign: dict[str, Any], *, actor: str) -> Optional[str]:
    """Decision 1 at the M8 plan (10-27-26): a Draft or Awaiting sign-off
    campaign built by a rule box, with no list, gets its kind's ready-made
    list and carries on. Returns the list id given, or None."""
    if store is None or (campaign.get("campaignStatus") or cfg.STATUS_DRAFT) not in (
            cfg.STATUS_DRAFT, cfg.STATUS_AWAITING):
        return None
    list_id = FOR_KIND.get(campaign.get("campaignKind") or "")
    if not list_id or not built_by_rule(campaign):
        return None
    if await store.get_campaign_audience(campaign["id"]):
        return None
    await ensure(store)
    await store.set_campaign_audience(campaign["id"], list_id, include_every_contact=False, actor=actor)
    log.info("campaign %s built by a rule: given the ready-made list %s", campaign["id"], list_id)
    return list_id
