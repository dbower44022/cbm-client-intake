"""Personal outreach from the lead's page — the rules (build plan § 7e.5;
prospect marketing rulings 107, 108, 109, 115, 118, 119, 120, 122, 128).

*Email*: one message from the assignee's own chapter mailbox to the lead's
own address, through the shared composer; the server, not the screen, holds
the guardrails (ruling 107): the lead is Qualified at Contactable or Referred,
has no side exit, is assigned to the sender, has an email, and the message
has exactly one recipient — the lead. Every message ends with the opt-out
sentence AND the chapter's postal address (ruling 122); the server appends
either when the message lacks it, and refuses the send while the address
setting is empty. One ``COutreachTouch`` per send, channel *Personal email*,
no campaign (ruling 119).

*Log a call*: one campaign-less *Personal call* touch with one of three
outcomes in the screen's words — Interested, Not interested, No reply yet —
stored as the campaign calls' words (``cfg.PERSONAL_OUTCOME_STORED``); the
consequences are the campaign calls' own code, ``calls.apply_outcome``.

Pure where it can be (the guardrails, the footer, the payloads), so the rules
are tested without a CRM; the two CRM reads here are the team ids a touch is
stamped with and the template list.
"""

from __future__ import annotations

import html as html_mod
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from core.espo import EspoApi, EspoError

from . import config as cfg
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.outreach")

#: Ruling 122's sentence, word for word.
OPT_OUT_SENTENCE = "If you'd rather not hear from us, reply and say so and we won't write again."
#: The levels a lead may be emailed personally at (ruling 107).
MAILABLE_LEVELS = (cfg.LEVEL_CONTACTABLE, cfg.LEVEL_REFERRED)
#: The template category that narrows the lead page's picker when any template
#: carries it (routine choice announced in the M5 kickoff).
TEMPLATE_CATEGORY = "Marketing"
ASSIGN_FIRST = "Assign the lead to yourself first."

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def lead_name(lead: dict[str, Any]) -> str:
    return (lead.get("businessName") or lead.get("name") or lead.get("id") or "").strip()


def level_word(lead: dict[str, Any]) -> str:
    status = lead.get("leadStatus") or cfg.LEAD_UNQUALIFIED
    if status == cfg.LEAD_QUALIFIED:
        return lead.get("qualificationLevel") or cfg.LEAD_QUALIFIED
    return status


def _assigned_to_user(lead: dict[str, Any], user: dict[str, Any]) -> str:
    """'' when the lead is assigned to ``user``; else the refusal (ruling 108:
    personal outreach is the assignee's)."""
    assignee = lead.get("assignedUserId") or ""
    if assignee and assignee == (user.get("userId") or ""):
        return ""
    if assignee:
        return f"This lead is assigned to {lead.get('assignedUserName') or 'someone else'}. {ASSIGN_FIRST}"
    return ASSIGN_FIRST


def why_not_email(lead: dict[str, Any], user: dict[str, Any]) -> str:
    """'' when the lead may be emailed by ``user``; else the reason in words.
    The screen asks the same question before opening the composer; the server
    asks it again before sending."""
    if lead.get("leadStatus") != cfg.LEAD_QUALIFIED or lead.get("qualificationLevel") not in MAILABLE_LEVELS:
        return ("Only a Contactable or Referred lead may be emailed personally; this one is "
                f"{level_word(lead)}. A named person and a phone or an email make a lead Contactable.")
    if lead.get("sideExit"):
        return f"This lead stopped being worked ({lead['sideExit']}), so it is not emailed."
    if not (lead.get("email") or "").strip():
        return "This lead has no email address. Add one under What we know first."
    return _assigned_to_user(lead, user)


def why_not_call(lead: dict[str, Any], user: dict[str, Any]) -> str:
    """'' when ``user`` may log a call on the lead; else the reason in words."""
    if lead.get("leadStatus") == cfg.LEAD_DISQUALIFIED:
        return "A Disqualified lead is not worked, so a call on it is not logged."
    return _assigned_to_user(lead, user)


def check_recipients(lead: dict[str, Any], to: list[str], cc: Optional[list[str]] = None,
                     bcc: Optional[list[str]] = None) -> str:
    """Exactly one recipient, the lead's own address (ruling 107: one person
    to one person). Returns the address, lowercased; raises otherwise."""
    email = (lead.get("email") or "").strip().lower()
    wanted = [a.strip().lower() for a in (to or []) if a and a.strip()]
    extra = [a for a in (cc or []) + (bcc or []) if a and a.strip()]
    if extra:
        raise CampaignError("A personal email goes to the lead alone — no Cc or Bcc.")
    if not wanted:
        raise CampaignError("The message has no recipient; the lead's own address is the only one allowed.")
    if len(wanted) != 1 or wanted[0] != email:
        raise CampaignError(f"A personal email goes to the lead's own address only ({email}).")
    return email


def _text_of(html: str) -> str:
    """What a reader sees of ``html``: tags gone, entities decoded, whitespace
    folded, lowercased — the footer check must not be fooled by markup."""
    text = _TAGS.sub(" ", html or "")
    text = html_mod.unescape(text)
    return _SPACE.sub(" ", text).strip().lower()


def _address_lines(postal_address: str) -> list[str]:
    return [line.strip() for line in (postal_address or "").replace("\r", "").split("\n") if line.strip()]


def append_footer(body_html: str, postal_address: str) -> str:
    """Ruling 122: the body ends with the opt-out sentence and the chapter's
    postal address; each is appended only when the message lacks it. An empty
    address refuses — the refusal names the setting to fill in."""
    lines = _address_lines(postal_address)
    if not lines:
        raise CampaignError(
            "The chapter's postal address is not set, and every personal email must carry it. "
            "Fill in Chapter postal address under Presentation at /setup (CHAPTER_POSTAL_ADDRESS), then send again.")
    seen = _text_of(body_html)
    out = body_html or ""
    if _text_of(OPT_OUT_SENTENCE) not in seen:
        out += "<p>" + html_mod.escape(OPT_OUT_SENTENCE) + "</p>"
    if _text_of(" ".join(lines)) not in seen:
        out += "<p>" + "<br>".join(html_mod.escape(l) for l in lines) + "</p>"
    return out


def email_touch_payload(lead: dict[str, Any], subject: str, *, user_id: str,
                        team_ids: list[str], now: str = "") -> dict[str, Any]:
    """The *Personal email* touch: Sent now, the subject as its name, no
    campaign, owned by the sender and the team (the stamp that makes the
    Marketing Admin Role's own write pass)."""
    payload: dict[str, Any] = {
        "name": ((subject or "").strip() or f"Email to {lead_name(lead)}")[:255],
        "channel": cfg.KIND_PERSONAL_EMAIL, "touchStatus": cfg.TOUCH_SENT, "sentAt": now or _now(),
        "prospectId": lead["id"], "stageAtTouch": lead.get("leadStatus") or None,
    }
    if user_id:
        payload["assignedUserId"] = user_id
    if team_ids:
        payload["teamsIds"] = list(team_ids)
    return payload


def call_touch_payload(lead: dict[str, Any], outcome: str, notes: str, called_phone: str, *,
                       user_id: str, team_ids: list[str], now: str = "") -> dict[str, Any]:
    """The *Personal call* touch: Done now, the outcome stored in the campaign
    calls' words, the number called, the notes."""
    if outcome not in cfg.PERSONAL_CALL_OUTCOMES:
        raise CampaignError("The outcome is Interested, Not interested or No reply yet.")
    if outcome == cfg.OUTCOME_NOT_INTERESTED and not (notes or "").strip():
        raise CampaignError("Say why the lead is not interested — the note is required for Not interested.")
    payload: dict[str, Any] = {
        "name": f"Personal call — {lead_name(lead)}"[:255],
        "channel": cfg.KIND_PERSONAL_CALL, "touchStatus": cfg.TOUCH_DONE, "doneAt": now or _now(),
        "outcome": cfg.PERSONAL_OUTCOME_STORED[outcome],
        "callNotes": (notes or "").strip() or None,
        "calledPhone": ((called_phone or "").strip() or (lead.get("phone") or "").strip())[:100] or None,
        "prospectId": lead["id"], "stageAtTouch": lead.get("leadStatus") or None,
    }
    if user_id:
        payload["assignedUserId"] = user_id
    if team_ids:
        payload["teamsIds"] = list(team_ids)
    return payload


async def team_ids(api_client: Optional[EspoApi], names: list[str]) -> list[str]:
    """The ids of the named teams (the Marketing Admin Team by default) — a
    personal touch has no campaign to take them from. Best-effort: a team the
    CRM cannot find, or no API client, contributes nothing."""
    out: list[str] = []
    if api_client is None:
        return out
    for name in names:
        try:
            team = await api_client.find_one("Team", "name", name, select="id,name")
        except EspoError as exc:
            log.warning("team %s not read: %s", name, exc)
            continue
        if team and team.get("id"):
            out.append(team["id"])
    return out


async def marketing_templates(user_client: Any) -> dict[str, Any]:
    """The lead page's template picker: the templates whose native category is
    *Marketing* when any has it, else every template the user may see."""
    data = await user_client.list(
        "EmailTemplate", select="id,name,categoryId,categoryName",
        order_by="name", order="asc", max_size=100,
    )
    rows = data.get("list", []) or []
    marketing = [r for r in rows if (r.get("categoryName") or "").strip().lower() == TEMPLATE_CATEGORY.lower()]
    chosen = marketing or rows
    return {"templates": [{"id": r.get("id"), "name": r.get("name")} for r in chosen],
            "contextFiltered": bool(marketing)}


def attachments_for_lead(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A lead has no Drive folder and no thread to forward from: only template
    attachments (``espoId``) and the sender's own files (``dataBase64``) ride a
    personal email. Anything else is refused in words."""
    out: list[dict[str, Any]] = []
    for item in items or []:
        if item.get("espoId") or item.get("dataBase64"):
            out.append(item)
        elif item.get("documentId"):
            raise CampaignError("A lead has no Documents folder, so a document cannot be attached from one — attach the file from your computer instead.")
        elif item.get("forwardCommunicationId"):
            raise CampaignError("A personal email to a lead cannot forward another message's attachments.")
    return out
