"""The review of a lead (build plan § 2.3, § 3.8, reworked for the lead model
§ 7a; rulings 42, 50).

* **Qualify** — an Unqualified lead becomes Qualified, with the reviewer's name
  in ``qualifiedBy`` and the time in ``qualifiedAt``. **Only a lead holding a
  website or an email** may be qualified (ruling 42); without one the action is
  refused and says why.
* **Disqualify** — the lead will never be a client, partner or funder: the
  status Disqualified, a note required, the reviewer named in it. Disqualified
  is a status, not a reason (ruling 50).
* **Do Not Contact** — a reason on any lead not yet converted.
* **Not the same company** — the one reversal: it clears the *Duplicate*
  reason and the ``alreadyKnownCompany`` link (*Duplicate of company*), and the
  lead is worked again at the status it holds.

**A reason is never written over another reason** (the arc's guardrail): every
action that sets one refuses, naming the reason already there. A Converted lead
is not reviewed — its Company or Contact is the record from then on.

Who acts: the lead's own fields are written as the signed-in user (the
Marketing Admin Role edits ``CProspect``); the ``alreadyKnownCompany`` link is
cleared under the org-wide API client, because EspoCRM checks read access on the
linked Company and that role reads none (the import's finding of 10-15-26,
ruling 33).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from core.espo import EspoApi

from . import config as cfg
from .service import CampaignError

ACTION_QUALIFY = "qualify"
ACTION_DISQUALIFY = "disqualify"
ACTION_DO_NOT_CONTACT = "do-not-contact"
ACTION_NOT_SAME_COMPANY = "not-same-company"
ACTIONS = (ACTION_QUALIFY, ACTION_DISQUALIFY, ACTION_DO_NOT_CONTACT, ACTION_NOT_SAME_COMPANY)

#: What each action is called in the action log and on the screen.
ACTION_LABELS = {
    ACTION_QUALIFY: "Lead Qualified",
    ACTION_DISQUALIFY: "Lead Disqualified",
    ACTION_DO_NOT_CONTACT: "Lead Do Not Contact",
    ACTION_NOT_SAME_COMPANY: "Lead Not The Same Company",
}


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _refuse_if_exited(lead: dict[str, Any], doing: str) -> None:
    if lead.get("sideExit"):
        raise CampaignError(
            f"This lead has already stopped being worked ({lead['sideExit']}), so it cannot be "
            f"{doing}. A reason is never written over another one.")


def _refuse_if_converted(lead: dict[str, Any], doing: str) -> None:
    if lead.get("leadStatus") == cfg.LEAD_CONVERTED:
        raise CampaignError(
            f"This lead is Converted, so it cannot be {doing}. Its Company or Contact is the record now.")


def _append_note(description: Optional[str], line: str) -> str:
    current = (description or "").rstrip()
    return f"{current}\n{line}" if current else line


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def contact_changes(lead: dict[str, Any], website: Optional[str], email: Optional[str]) -> dict[str, Any]:
    """The website and email the reviewer typed into the Review row (§ 7b
    answer 2), as the fields to write: only a value that is new, an email
    that looks like one, a website given its ``https://`` when it has none.
    Raises :class:`CampaignError` naming what is wrong."""
    out: dict[str, Any] = {}
    website = (website or "").strip()
    email = (email or "").strip()
    if website:
        if " " in website or "." not in website:
            raise CampaignError(f"\"{website}\" is not a web address.")
        if not re.match(r"^https?://", website, re.I):
            website = "https://" + website
        if website != (lead.get("website") or ""):
            out["website"] = website[:255]
    if email:
        if not _EMAIL.match(email):
            raise CampaignError(f"\"{email}\" is not an email address.")
        if email.lower() != (lead.get("email") or "").lower():
            out["email"] = email[:255]
    return out


def plan_action(lead: dict[str, Any], action: str, *, reviewer: str,
                note: str = "", website: Optional[str] = None,
                email: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two writes an action makes: ``(user_payload, api_payload)``. Pure, so
    the rules are tested without a CRM. Raises :class:`CampaignError` when the
    action does not apply to this lead. A website or email typed into the
    Review row rides with *Qualify* (and is kept with any other action)."""
    typed = contact_changes(lead, website, email)
    lead = {**lead, **typed}
    note = (note or "").strip()
    reviewer = (reviewer or "").strip() or "a reviewer"
    now = _now_crm()
    status = lead.get("leadStatus") or cfg.LEAD_UNQUALIFIED
    if action == ACTION_QUALIFY:
        _refuse_if_exited(lead, "qualified")
        if status != cfg.LEAD_UNQUALIFIED:
            raise CampaignError(f"Only an Unqualified lead is qualified by review; this one is {status}.")
        if not (lead.get("website") or lead.get("email")):
            raise CampaignError(
                "A lead without a website or an email can never be Qualified (ruling 42). "
                "Type the one you found into the row's Website or Email box, or leave it Unqualified — "
                "campaigns may still reach it.")
        payload: dict[str, Any] = {
            "leadStatus": cfg.LEAD_QUALIFIED, "leadStatusChangedAt": now,
            "qualifiedBy": reviewer[:255], "qualifiedAt": now,
        }
        if note:
            payload["description"] = _append_note(
                lead.get("description"), f"Qualified by {reviewer} on {now[:10]}: {note}")
        return payload, {}
    if action == ACTION_DISQUALIFY:
        _refuse_if_exited(lead, "disqualified")
        if status not in cfg.LEAD_OPEN_STATUSES:
            raise CampaignError(f"Only an Unqualified or Qualified lead can be disqualified; this one is {status}.")
        if not note:
            raise CampaignError("Say why the lead will never be a client, partner or funder — the note is required.")
        return {"leadStatus": cfg.LEAD_DISQUALIFIED, "leadStatusChangedAt": now,
                "description": _append_note(lead.get("description"),
                                            f"Disqualified by {reviewer} on {now[:10]}: {note}")}, {}
    if action == ACTION_DO_NOT_CONTACT:
        _refuse_if_exited(lead, "marked Do Not Contact")
        _refuse_if_converted(lead, "marked Do Not Contact")
        text = f"Do Not Contact, set by {reviewer}" + (f": {note}" if note else "")
        return {"sideExit": cfg.EXIT_DO_NOT_CONTACT, "sideExitAt": now, "sideExitNote": text}, {}
    if action == ACTION_NOT_SAME_COMPANY:
        if lead.get("sideExit") != cfg.EXIT_DUPLICATE:
            raise CampaignError("Only a lead marked Duplicate can be told it is not the same company.")
        matched = lead.get("alreadyKnownCompanyName") or lead.get("alreadyKnownCompanyId") or "the matched record"
        line = (f"Not the same company as {matched}, said {reviewer} on {now[:10]}"
                + (f": {note}" if note else "") + f" (was: {lead.get('sideExitNote') or 'Duplicate'})")
        user_payload = {"sideExit": None, "sideExitAt": None, "sideExitNote": None,
                        "description": _append_note(lead.get("description"), line)}
        api_payload = {"alreadyKnownCompanyId": None} if lead.get("alreadyKnownCompanyId") else {}
        return user_payload, api_payload
    raise CampaignError("Unknown review action.")


def _with_typed(plan: tuple[dict[str, Any], dict[str, Any]], typed: dict[str, Any]):
    user_payload, api_payload = plan
    return {**typed, **user_payload}, api_payload


async def apply_action(user_client: EspoApi, api_client: Optional[EspoApi], lead: dict[str, Any],
                       action: str, *, reviewer: str, note: str = "", website: Optional[str] = None,
                       email: Optional[str] = None) -> dict[str, Any]:
    """Write one review action. The user's write goes first, so a refused grant
    changes nothing; the link clear follows under the API client."""
    user_payload, api_payload = _with_typed(
        plan_action(lead, action, reviewer=reviewer, note=note, website=website, email=email),
        contact_changes(lead, website, email))
    updated = await user_client.update(cfg.PROSPECT, lead["id"], user_payload)
    if api_payload and api_client is not None:
        updated = await api_client.update(cfg.PROSPECT, lead["id"], api_payload)
    return {"prospect": updated, "written": sorted(set(user_payload) | set(api_payload))}
