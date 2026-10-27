"""The campaign page's stage strip (build plan § 7e.9 second half, ruling
100; M8). Five stages read from today's ``campaignStatus`` — no CRM change —
plus the one next action, in words, naming the tab where it is done.

- Draft is Draft while the list or the content is missing (and until built).
- Ready is Awaiting sign-off.
- Signed off is Signed off.
- Sent is Running, for every kind (an email reaches Running when its email is
  picked).
- Results is Complete.

A Cancelled campaign shows no current stage. The social kind has no strip.
"""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg

STAGES = ("Draft", "Ready", "Signed off", "Sent", "Results")
KINDS = (cfg.KIND_POSTCARD, cfg.KIND_EMAIL, cfg.KIND_SMS, cfg.KIND_CALL)
AUDIENCE_TAB = "Audience and content"

_BY_STATUS = {
    cfg.STATUS_DRAFT: "Draft", cfg.STATUS_AWAITING: "Ready", cfg.STATUS_SIGNED_OFF: "Signed off",
    cfg.STATUS_RUNNING: "Sent", cfg.STATUS_COMPLETE: "Results",
}


def stage_of(status: Optional[str]) -> Optional[str]:
    """The strip's word for a status; None for Cancelled."""
    return _BY_STATUS.get(status or cfg.STATUS_DRAFT)


def strip(campaign: dict[str, Any], *, list_name: str = "", content_problem: str = "") -> Optional[dict[str, Any]]:
    """``{stages, current, next, tab}`` for the four kinds that send, else
    None. ``list_name`` is the campaign's list ("" when it has none);
    ``content_problem`` is what the kind's content still lacks, in words."""
    kind = campaign.get("campaignKind") or ""
    if kind not in KINDS:
        return None
    status = campaign.get("campaignStatus") or cfg.STATUS_DRAFT
    current = stage_of(status)
    nxt, tab = _next(kind, status, list_name, content_problem)
    return {"stages": list(STAGES), "current": current, "next": nxt, "tab": tab,
            "cancelled": status == cfg.STATUS_CANCELLED}


def _action(problem: str) -> str:
    """A content problem as the next action: lower-case first word, no full
    stop, and no bracket of its own (the strip adds the tab's)."""
    import re

    text = re.sub(r"\s*\([^)]*\)\s*\.?$", "", problem.strip()).rstrip(".")
    return text[:1].lower() + text[1:]


def _next(kind: str, status: str, list_name: str, content_problem: str) -> tuple[str, str]:
    if status == cfg.STATUS_CANCELLED:
        return "This campaign is cancelled. Reopen it as a draft to use it again.", "Overview"
    if status == cfg.STATUS_DRAFT:
        if not list_name:
            return f"Next: choose a list ({AUDIENCE_TAB}).", AUDIENCE_TAB
        if content_problem:
            return f"Next: {_action(content_problem)} — press Edit to change it ({AUDIENCE_TAB}).", AUDIENCE_TAB
        return f"Next: build the list from \"{list_name}\" ({AUDIENCE_TAB}).", AUDIENCE_TAB
    if status == cfg.STATUS_AWAITING:
        if content_problem:
            return f"Next: {_action(content_problem)} — press Edit to change it ({AUDIENCE_TAB}).", AUDIENCE_TAB
        return f"Next: check the counts and sign off ({AUDIENCE_TAB}).", AUDIENCE_TAB
    if status == cfg.STATUS_SIGNED_OFF:
        if kind == cfg.KIND_EMAIL:
            return (f"Next: send it in Constant Contact to \"{list_name or 'the list'}\", then pick that email "
                    f"here ({AUDIENCE_TAB})."), AUDIENCE_TAB
        if kind == cfg.KIND_POSTCARD:
            return "Next: nothing to do — the cards are being mailed.", "Responses"
        if kind == cfg.KIND_SMS:
            return "Next: nothing to do — the texts go out within the sending hours.", "Responses"
        return "Next: callers work the list on the Calls tab.", "Responses"
    if status == cfg.STATUS_RUNNING:
        if kind == cfg.KIND_CALL:
            return "Next: callers record each call on the Calls tab; it completes with the last one.", "Responses"
        return "Next: watch the responses as they arrive (Responses).", "Responses"
    return "Next: read the results (Results).", "Results"
