"""The lead code: one code per person, for life, at the end of every personal
link (build plan § 7d.1–7d.3; rulings 71–74, 77).

A person is one of three things, and the code follows them:

* **an unpromoted lead** holds it on ``CProspect.leadCode``;
* **a lead converted to a Contact** keeps the one code — the conversion copies
  it to ``Contact.cLeadCode`` (:func:`sync_on_conversion`) and never mints a
  second;
* **a Contact with no lead** holds it on ``Contact.cLeadCode`` alone.

Rules kept here:

* **Every write goes under the org-wide (or intake) API key.** The Marketing
  Admin Role holds a field rule of read-only on both fields (ruling 77), so a
  write under a marketer's own login is dropped silently with HTTP 200.
* **Feature-detected and fail-closed** (:func:`available`): a CRM without the
  two fields gets no code minted, no code read, and no select naming either
  field — EspoCRM refuses a select of an unknown attribute.
* **Never a record id.** The code is twelve characters from the scan token's
  alphabet (no 0/O, 1/l/I), so a person can read it back from a card or a text.
* **Resolution is Contact first, then lead** (§ 7d.3), and a code that matches
  nothing is simply None — the caller answers it in the same words as a
  malformed one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from core.espo import EspoApi, EspoError

from . import config as cfg
from .tokens import SCAN_TOKEN_LENGTH, looks_like_token, new_token

log = logging.getLogger("cbm_intake.campaigns.leadcode")

LEAD_FIELD = "leadCode"          # on CProspect, stored as typed (custom entity)
CONTACT_FIELD = "cLeadCode"      # on Contact (typed leadCode; native entity ⇒ c prefix)
CODE_LENGTH = SCAN_TOKEN_LENGTH  # twelve, the card's length (§ 7d.1)
#: Minting retries before giving up — a collision in 31^12 is not expected; the
#: loop exists so one never silently gives two people the same code.
_MINT_TRIES = 5

#: What a resolve reads of each record. Kept small: the per-form lookup reads
#: its own allowlist separately.
LEAD_SELECT = f"id,name,businessName,leadStatus,promotedCompanyId,promotedContactId,{LEAD_FIELD}"
CONTACT_SELECT = f"id,name,accountId,{CONTACT_FIELD}"


def new_code() -> str:
    """A fresh person code. The postcard's card token is this same shape."""
    return new_token(CODE_LENGTH)


def looks_like_code(value: Optional[str]) -> bool:
    return bool(value) and looks_like_token(value or "")


async def available(client: EspoApi) -> bool:
    """Whether this CRM carries BOTH code fields (lead-code-crm-handoff.md).
    Fails closed. The metadata read is cached process-wide by ``EspoClient``."""
    try:
        lead = await client.metadata(f"entityDefs.{cfg.PROSPECT}.fields")
        contact = await client.metadata(f"entityDefs.{cfg.CONTACT}.fields")
    except Exception as exc:  # noqa: BLE001 — unreadable is "not available"
        log.warning("could not read the lead code fields (%s) — no code used", exc)
        return False
    return (isinstance(lead, dict) and isinstance(lead.get(LEAD_FIELD), dict)
            and isinstance(contact, dict) and isinstance(contact.get(CONTACT_FIELD), dict))


async def click_fields_available(client: EspoApi) -> bool:
    """Whether the touch carries ``firstClickedAt`` and ``clickCount``."""
    try:
        fields = await client.metadata(f"entityDefs.{cfg.TOUCH}.fields")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read the touch fields (%s) — no click recorded", exc)
        return False
    return isinstance(fields, dict) and "firstClickedAt" in fields and "clickCount" in fields


@dataclass
class Person:
    """Who a code names: the lead, the Contact, or both (a converted lead)."""

    code: str
    lead: Optional[dict[str, Any]] = None       # a LEAD_SELECT read
    contact: Optional[dict[str, Any]] = None    # a CONTACT_SELECT read

    @property
    def lead_id(self) -> Optional[str]:
        return (self.lead or {}).get("id") or None

    @property
    def contact_id(self) -> Optional[str]:
        return (self.contact or {}).get("id") or (self.lead or {}).get("promotedContactId") or None


async def _taken(client: EspoApi, code: str) -> bool:
    if await client.find_one(cfg.CONTACT, CONTACT_FIELD, code):
        return True
    return bool(await client.find_one(cfg.PROSPECT, LEAD_FIELD, code))


async def _fresh_code(client: EspoApi) -> str:
    for _ in range(_MINT_TRIES):
        code = new_code()
        if not await _taken(client, code):
            return code
    raise RuntimeError("could not mint an unused lead code")


async def resolve(client: EspoApi, code: Optional[str]) -> Optional[Person]:
    """The person ``code`` names, or None (malformed, unknown, or a CRM without
    the fields). Contact first, then the lead; a converted lead found by its
    code brings its Contact, and a Contact found alone brings the lead that
    converted to it, when there is one. Under the API key. Never raises."""
    code = (code or "").strip().lower()
    if not looks_like_code(code):
        return None
    try:
        if not await available(client):
            return None
        contact = await client.find_one(cfg.CONTACT, CONTACT_FIELD, code, select=CONTACT_SELECT)
        lead = await client.find_one(cfg.PROSPECT, LEAD_FIELD, code, select=LEAD_SELECT)
        if contact and not lead:
            lead = await client.find_one(cfg.PROSPECT, "promotedContactId", contact["id"], select=LEAD_SELECT)
        if lead and not contact and lead.get("promotedContactId"):
            try:
                contact = await client.get(cfg.CONTACT, lead["promotedContactId"], select=CONTACT_SELECT)
            except EspoError:
                contact = None
    except Exception as exc:  # noqa: BLE001 — a code is an optional extra, never a failure
        log.warning("lead code lookup failed (%s) — treated as unknown", exc)
        return None
    if not (contact and contact.get("id")) and not (lead and lead.get("id")):
        return None
    return Person(code=code, lead=lead if lead and lead.get("id") else None,
                  contact=contact if contact and contact.get("id") else None)


async def ensure_for_lead(client: EspoApi, lead_id: str) -> Optional[str]:
    """The lead's code, minted now if it has none (§ 7d.1: "the first time a
    campaign needs it"). A converted lead whose Contact already holds a code
    adopts that one; a newly minted code is written to the converted Contact
    too, so the two stay equal. None on a CRM without the fields. Under the
    API key; raises :class:`EspoError` on a failed write so a caller that must
    not proceed without a code (the postcard run) can stop."""
    if not await available(client):
        return None
    lead = await client.get(cfg.PROSPECT, lead_id, select=LEAD_SELECT)
    if lead.get(LEAD_FIELD):
        return lead[LEAD_FIELD]
    contact = None
    if lead.get("promotedContactId"):
        try:
            contact = await client.get(cfg.CONTACT, lead["promotedContactId"], select=CONTACT_SELECT)
        except EspoError:
            contact = None
    code = (contact or {}).get(CONTACT_FIELD) or await _fresh_code(client)
    await client.update(cfg.PROSPECT, lead_id, {LEAD_FIELD: code})
    if contact and not contact.get(CONTACT_FIELD):
        await client.update(cfg.CONTACT, contact["id"], {CONTACT_FIELD: code})
    return code


async def ensure_for_contact(client: EspoApi, contact_id: str) -> Optional[str]:
    """The Contact's code, minted now if it has none. A Contact that a lead
    converted to takes the lead's code when the lead has one."""
    if not await available(client):
        return None
    contact = await client.get(cfg.CONTACT, contact_id, select=CONTACT_SELECT)
    if contact.get(CONTACT_FIELD):
        return contact[CONTACT_FIELD]
    lead = await client.find_one(cfg.PROSPECT, "promotedContactId", contact_id, select=LEAD_SELECT)
    code = (lead or {}).get(LEAD_FIELD) or await _fresh_code(client)
    await client.update(cfg.CONTACT, contact_id, {CONTACT_FIELD: code})
    if lead and not lead.get(LEAD_FIELD):
        await client.update(cfg.PROSPECT, lead["id"], {LEAD_FIELD: code})
    return code


async def sync_on_conversion(client: EspoApi, lead_id: str, contact_id: Optional[str]) -> Optional[str]:
    """§ 7d.1: conversion copies the lead's code to its Contact, never mints a
    second. Null-fill in either direction — a lead with no code adopts the
    Contact's. When both already hold DIFFERENT codes, both are left (each
    still resolves to the same person) and the difference is logged.
    Best-effort: never raises. Returns the code now on both, if one."""
    if not contact_id:
        return None
    try:
        if not await available(client):
            return None
        lead = await client.get(cfg.PROSPECT, lead_id, select=LEAD_SELECT)
        contact = await client.get(cfg.CONTACT, contact_id, select=CONTACT_SELECT)
        lc, cc = lead.get(LEAD_FIELD), contact.get(CONTACT_FIELD)
        if lc and not cc:
            await client.update(cfg.CONTACT, contact_id, {CONTACT_FIELD: lc})
            return lc
        if cc and not lc:
            await client.update(cfg.PROSPECT, lead_id, {LEAD_FIELD: cc})
            return cc
        if lc and cc and lc != cc:
            log.warning("lead %s and contact %s hold different codes — both kept", lead_id, contact_id)
            return None
        return lc or None
    except Exception as exc:  # noqa: BLE001
        log.warning("lead code not copied from lead %s to contact %s: %s", lead_id, contact_id, exc)
        return None


# --- the click (§ 7d.3 step 3) ---------------------------------------------------------

async def find_touch(client: EspoApi, campaign_id: str, person: Person) -> Optional[dict[str, Any]]:
    """The person's touch on this campaign: campaign + lead, else campaign +
    contact. A Cancelled or Planned touch is not one (Planned is a preview:
    nothing was sent). The most recent sent one wins."""
    candidates: list[dict[str, Any]] = []
    for attr, value in (("prospectId", person.lead_id), ("contactId", person.contact_id)):
        if not value:
            continue
        page = await client.list(cfg.TOUCH, select=cfg.TOUCH_SELECT + ",firstClickedAt,clickCount", max_size=20,
                                 where=[{"type": "equals", "attribute": "outreachCampaignId", "value": campaign_id},
                                        {"type": "equals", "attribute": attr, "value": value}])
        candidates.extend(page.get("list", []))
    live = [t for t in candidates if t.get("touchStatus") not in (cfg.TOUCH_CANCELLED, cfg.TOUCH_PLANNED)]
    if not live:
        return None
    live.sort(key=lambda t: t.get("sentAt") or "", reverse=True)
    return live[0]


def click_stamps(touch: dict[str, Any], now: str) -> dict[str, Any]:
    """What one click writes: ``clickCount`` every time, ``firstClickedAt`` once,
    outcome *Clicked* only when the touch has no outcome yet — a call's
    Interested or a card's Scanned says more and is never overwritten. A click
    changes no status (ruling 51)."""
    stamps: dict[str, Any] = {"clickCount": int(touch.get("clickCount") or 0) + 1}
    if not touch.get("firstClickedAt"):
        stamps["firstClickedAt"] = now
    if not touch.get("outcome"):
        stamps["outcome"] = cfg.OUTCOME_CLICKED
    return stamps


async def record_click(client: EspoApi, campaign_id: str, code: str, now: str) -> dict[str, Any]:
    """Record one click of ``/c/{link}/{code}`` on the person's touch. Runs
    AFTER the redirect has been answered (ruling 31: the resolve never waits
    on the CRM). Best-effort; returns what happened, never raises."""
    try:
        if not await click_fields_available(client):
            return {"recorded": False, "reason": "no click fields"}
        person = await resolve(client, code)
        if person is None:
            return {"recorded": False, "reason": "unknown code"}
        touch = await find_touch(client, campaign_id, person)
        if touch is None:
            # Forwarded, or clicked after the list was rebuilt: the lead still
            # rides to the form; nothing is written on a touch.
            return {"recorded": False, "reason": "no touch"}
        await client.update(cfg.TOUCH, touch["id"], click_stamps(touch, now))
        return {"recorded": True, "touchId": touch["id"]}
    except Exception as exc:  # noqa: BLE001
        log.warning("click on campaign %s not recorded: %s", campaign_id, exc)
        return {"recorded": False, "reason": str(exc)}
