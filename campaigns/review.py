"""The review of a prospect record (build plan § 2.3, § 3.8; rulings 18 and 29).

* **Qualify** — an Unverified record on the ladder moves to Qualified, with the
  reviewer's name in ``qualifiedBy`` and the time in ``qualifiedAt`` (ruling 18).
* **Unqualified** — the review's side exit, a note required, the reviewer named
  in the note. ``Unqualified`` is a side exit and ``Unverified`` a rung (ruling
  29); the two words are never used for one another.
* **Do Not Contact** — a side exit on any record still on the ladder.
* **Not the same company** — the one reversal: it clears the *Already known*
  side exit and the ``alreadyKnownCompany`` link, and the record is back on its
  entry rung (§ 2.2).

**A side exit is never written over another side exit** (the arc's guardrail):
every action that sets one refuses, naming the exit already there.

Who acts: the record's own fields are written as the signed-in user (the
Marketing Admin Role edits ``CProspect``); the ``alreadyKnownCompany`` link is
cleared under the org-wide API client, because EspoCRM checks read access on the
linked Company and that role reads none (the import's finding of 10-15-26,
ruling 33).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from core.espo import EspoApi

from . import config as cfg
from .service import CampaignError

ACTION_QUALIFY = "qualify"
ACTION_UNQUALIFY = "unqualify"
ACTION_DO_NOT_CONTACT = "do-not-contact"
ACTION_NOT_SAME_COMPANY = "not-same-company"
ACTIONS = (ACTION_QUALIFY, ACTION_UNQUALIFY, ACTION_DO_NOT_CONTACT, ACTION_NOT_SAME_COMPANY)

#: What each action is called in the action log and on the screen.
ACTION_LABELS = {
    ACTION_QUALIFY: "Prospect Qualified",
    ACTION_UNQUALIFY: "Prospect Unqualified",
    ACTION_DO_NOT_CONTACT: "Prospect Do Not Contact",
    ACTION_NOT_SAME_COMPANY: "Prospect Not The Same Company",
}


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _refuse_if_exited(prospect: dict[str, Any], doing: str) -> None:
    if prospect.get("sideExit"):
        raise CampaignError(
            f"This record has already left the ladder by {prospect['sideExit']}, so it cannot be "
            f"{doing}. A side exit is never written over another one.")


def _append_note(description: Optional[str], line: str) -> str:
    current = (description or "").rstrip()
    return f"{current}\n{line}" if current else line


def plan_action(prospect: dict[str, Any], action: str, *, reviewer: str,
                note: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """The two writes an action makes: ``(user_payload, api_payload)``. Pure, so
    the rules are tested without a CRM. Raises :class:`CampaignError` when the
    action does not apply to this record."""
    note = (note or "").strip()
    reviewer = (reviewer or "").strip() or "a reviewer"
    now = _now_crm()
    if action == ACTION_QUALIFY:
        _refuse_if_exited(prospect, "qualified")
        if prospect.get("funnelStage") != cfg.STAGE_UNVERIFIED:
            raise CampaignError(
                f"Only an Unverified record is qualified by review; this one is at "
                f"{prospect.get('funnelStage') or 'no rung'}.")
        payload: dict[str, Any] = {
            "funnelStage": cfg.STAGE_QUALIFIED, "stageChangedAt": now,
            "qualifiedBy": reviewer[:255], "qualifiedAt": now,
        }
        if note:
            payload["description"] = _append_note(
                prospect.get("description"), f"Qualified by {reviewer} on {now[:10]}: {note}")
        return payload, {}
    if action == ACTION_UNQUALIFY:
        _refuse_if_exited(prospect, "marked Unqualified")
        if prospect.get("funnelStage") != cfg.STAGE_UNVERIFIED:
            raise CampaignError(
                "Unqualified is the review's exit for an Unverified record; this one is at "
                f"{prospect.get('funnelStage') or 'no rung'}.")
        if not note:
            raise CampaignError("Say why the record is unqualified — the note is required.")
        return {"sideExit": cfg.EXIT_UNQUALIFIED, "sideExitAt": now,
                "sideExitNote": f"{note} — reviewed by {reviewer}"}, {}
    if action == ACTION_DO_NOT_CONTACT:
        _refuse_if_exited(prospect, "marked Do Not Contact")
        text = f"Do Not Contact, set by {reviewer}" + (f": {note}" if note else "")
        return {"sideExit": cfg.EXIT_DO_NOT_CONTACT, "sideExitAt": now, "sideExitNote": text}, {}
    if action == ACTION_NOT_SAME_COMPANY:
        if prospect.get("sideExit") != cfg.EXIT_ALREADY_KNOWN:
            raise CampaignError("Only a record that left as Already known can be told it is not the same company.")
        matched = prospect.get("alreadyKnownCompanyName") or prospect.get("alreadyKnownCompanyId") or "the matched record"
        line = (f"Not the same company as {matched}, said {reviewer} on {now[:10]}"
                + (f": {note}" if note else "") + f" (was: {prospect.get('sideExitNote') or 'Already known'})")
        user_payload = {"sideExit": None, "sideExitAt": None, "sideExitNote": None,
                        "description": _append_note(prospect.get("description"), line)}
        if prospect.get("entryStage") and prospect.get("funnelStage") != prospect.get("entryStage"):
            user_payload["funnelStage"] = prospect["entryStage"]
            user_payload["stageChangedAt"] = now
        api_payload = {"alreadyKnownCompanyId": None} if prospect.get("alreadyKnownCompanyId") else {}
        return user_payload, api_payload
    raise CampaignError("Unknown review action.")


async def apply_action(user_client: EspoApi, api_client: Optional[EspoApi], prospect: dict[str, Any],
                       action: str, *, reviewer: str, note: str = "") -> dict[str, Any]:
    """Write one review action. The user's write goes first, so a refused grant
    changes nothing; the link clear follows under the API client."""
    user_payload, api_payload = plan_action(prospect, action, reviewer=reviewer, note=note)
    updated = await user_client.update(cfg.PROSPECT, prospect["id"], user_payload)
    if api_payload and api_client is not None:
        updated = await api_client.update(cfg.PROSPECT, prospect["id"], api_payload)
    return {"prospect": updated, "written": sorted(set(user_payload) | set(api_payload))}
