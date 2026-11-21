"""Follow-up alerts (ruling BE32; decision 4, A, 11-20-26).

A response that needs follow-up (a low score, a "contact me", or an event's
"talk with a mentor") emails every member of the responsible team at once,
from the shared mailbox: the Mentor Administration Team for mentoring and
evaluation feedback, the Marketing Admin Team for event feedback. The email
names the score, why it was flagged and what it is about, and links to the
response where staff mark the follow-up done.

* **Once per response**: ``feedback_alert`` is claimed before the send, so a
  retried submit never alerts twice; a failed send is retried by the sweep.
* **A team with no members** falls back to ``ALERT_EMAIL_TO``, logged.
* **The mentor is not emailed**: they see the response on their Feedback tab.
* Best-effort throughout: an alert never fails a submit.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.espo import EspoError

from . import config as cfg
from . import email as fb_email
from .sending import Sender, send_shared

log = logging.getLogger("cbm_intake.feedback")


def response_path(response: dict[str, Any]) -> str:
    """Where staff open the response and mark the follow-up done (decision 4):
    the mentor's Feedback tab in Mentor Administration, or the event's in
    Event Administration."""
    rid = response.get("id") or ""
    if response.get("surveyKey") == cfg.SURVEY_EVENT and response.get("eventId"):
        return f"/events/?event={response['eventId']}&tab=feedback&response={rid}"
    if response.get("mentorProfileId"):
        return f"/mentoradmin/?mentor={response['mentorProfileId']}&tab=feedback&response={rid}"
    return "/"


def response_url(settings: Any, response: dict[str, Any]) -> str:
    base = (getattr(settings, "app_base_url", "") or "").rstrip("/")
    return base + response_path(response)


async def team_addresses(client: Any, team_name: str) -> list[str]:
    """The email addresses of a team's active members, read under the
    org-wide key. Empty when the team is missing or cannot be read."""
    try:
        page = await client.list("Team", where=[{"type": "equals", "attribute": "name",
                                                 "value": team_name}],
                                 select="id,name", max_size=5)
        team = next((t for t in page.get("list", []) if t.get("name") == team_name), None)
        if team is None:
            return []
        users = await client.list_related("Team", team["id"], "users",
                                          select="id,name,emailAddress,isActive", max_size=200)
    except EspoError as exc:
        log.warning("feedback alert: team %r not read: %s", team_name, exc)
        return []
    out: list[str] = []
    for u in users.get("list", []):
        addr = (u.get("emailAddress") or "").strip()
        if addr and u.get("isActive", True) and addr.lower() not in {a.lower() for a in out}:
            out.append(addr)
    return out


def deliverable(settings: Any, addresses: list[str], rid: str = "") -> list[str]:
    """The addresses an alert may go to: an invented training address (the
    Sandbox address domain, ``core/sandbox_addresses``) is left out, logged,
    so one such team member never stops the alert reaching the real ones
    (found on the Association 11-21-26)."""
    from core.sandbox_addresses import is_sandbox_address, sandbox_domain

    domain = sandbox_domain(settings) if hasattr(settings, "sandbox_address_domain") else ""
    kept = [a for a in addresses if not is_sandbox_address(a, domain)]
    dropped = [a for a in addresses if a not in kept]
    if dropped:
        log.info("feedback alert %s: left out %d training address(es) on %s", rid,
                 len(dropped), domain)
    return kept


async def alert_once(settings: Any, client: Any, store: Any, response: dict[str, Any], *,
                     about: str, who: str, reasons: list[str],
                     sender: Optional[Sender] = None) -> str:
    """Email the responsible team about one response, once. Returns one word:
    ``sent``, ``already``, ``no-store``, ``no-mailbox``, ``no-recipients`` or
    ``failed``. Never raises."""
    rid = response.get("id") or ""
    if store is None:
        return "no-store"
    try:
        if not await store.claim_alert(rid):
            return "already"
    except Exception as exc:  # noqa: BLE001
        log.warning("feedback alert %s: not claimed: %s", rid, exc)
        return "failed"
    try:
        if not (getattr(settings, "ops_mailbox", "") or "").strip():
            await store.finish_alert(rid, "failed", "no shared mailbox")
            return "no-mailbox"
        team = cfg.alert_team(settings, response.get("surveyKey") or "")
        to = deliverable(settings, await team_addresses(client, team), rid)
        if not to:
            to = deliverable(settings, list(getattr(settings, "alert_email_to_list", None) or []), rid)
            log.warning("feedback alert %s: team %r has no members with an address; "
                        "sent to the alert address instead", rid, team)
        if not to:
            # Nothing a retry could change: recorded as skipped, not failed.
            await store.finish_alert(rid, "skipped", f"no recipients for {team}")
            return "no-recipients"
        filled = fb_email.alert(
            org=settings.organization_name,
            survey_title=cfg.survey_title(response.get("surveyKey") or ""),
            about=about, score=response.get("recommendScore"), reasons=reasons, who=who,
            link_url=response_url(settings, response))
        await (sender or send_shared)(settings, to, filled["subject"], filled["bodyHtml"])
    except Exception as exc:  # noqa: BLE001 — retried by the sweep
        log.warning("feedback alert %s failed: %s", rid, exc)
        try:
            await store.finish_alert(rid, "failed", str(exc)[:500])
        except Exception:  # noqa: BLE001
            pass
        return "failed"
    await store.finish_alert(rid, "sent")
    log.info("feedback alert %s sent to %s (%d)", rid, team, len(to))
    return "sent"
