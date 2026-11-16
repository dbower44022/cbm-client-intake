"""The intake survey (Business Evaluation phase 6; rulings BE24 to BE27).

When a client intake is delivered, the client is emailed a link to the
business profile survey from the shared mailbox (BE24). After the profile
the page asks "Do you have time to provide more details?"; a yes opens the
area picker, and each area picked becomes a Business Evaluation record,
round 1, on the same link (BE25). Client Administration reads the profile
answers and the areas picked (BE26), and Assign moves the records to the
mentor (BE26, BE27).

Rules kept here:

* **Dark behind ``INTAKE_SURVEY``**, which needs ``BUSINESS_EVALUATION`` too.
  Off, a delivered intake sends nothing and Client Administration shows no
  new tab.
* **Best-effort**: nothing here ever fails an intake or an assignment. A
  failure is logged.
* **One intake link per engagement**: a re-driven delivery finds the link in
  the application database and sends nothing (``data["intake"]``).
* **A client whose business profile is already on file gets no email**
  (Doug, stopping point (a) 11-16-26): the short survey has nothing to ask.
* **The org-wide key writes**: there is no mentor yet. The records carry the
  engagement's ``assignedUsers`` (usually none until Assign).
* **Client Administration never sees a report** (BE17, BE26): the areas
  picked are read under the org-wide key after the staff member's own read
  of the engagement succeeds, and only area, round and status leave this
  module.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from core.espo import EspoError
from surveys import registry

from . import service
from .sending import (
    ADVISED_MAX, SendError, area_choices, choose_areas, entity_available,
    links_for_engagement, list_records, profile_answers_html, STATUS_SENT,
)
from .surveys import PROFILE_KEY, Survey, latest

log = logging.getLogger("cbm_intake.evaluation")

#: Who made an intake link (``survey_link.created_by``).
CREATED_BY = "client intake"

#: ``data["details"]``: the client's answer to "more details?".
DETAILS_YES = "yes"
DETAILS_DECLINED = "declined"

# --- the page's words for an intake link (approved by Doug 11-16-26) ------------

PAGE = registry.PageText(
    title="Tell us about your business",
    consent_intro=(
        "<p>Thank you for asking {{org}} for a mentor. While we find the right person for\n"
        "        you, tell us about your business. It is about 14 short questions, and you can\n"
        "        stop at any time and come back later: your answers are saved as you go.</p>\n"
        "      <p>Your answers are kept with your record at {{org}} and are seen by our staff\n"
        "        and the mentors who work with you. If you go on to answer questions about\n"
        "        particular areas of your business, an AI service processes those answers to\n"
        "        prepare a first summary for your mentor, who checks it before you see any of it.</p>"
    ),
    consent_label=(
        "I agree that my answers may be processed by an AI service and kept with my\n"
        "            record at {{org}}, as described above."
    ),
    list_intro=(
        "Start with the first survey. You can stop at any time and come back\n"
        "        to this page later; your answers are saved as you go."
    ),
    all_done=(
        "Thank you. You have submitted every survey. We will be in touch soon to\n"
        "        introduce your mentor."
    ),
    pending=("Your answers are submitted and safe with us. We will pass them on shortly; "
             "there is nothing more you need to do."),
)

OFFER_TEXT = registry.OfferText(
    question="Thank you. Do you have time to provide more details?",
    intro=("If you have a few more minutes, choose the areas of your business you would "
           "like help with. Each one is a short survey of about 15 questions. Your answers "
           "help us choose your mentor, and they give your mentor a head start."),
    yes_label="Yes, choose areas",
    no_label="No, that's all for now",
    pick_title="Which areas would you like help with?",
    pick_intro=("Most people choose two or three at a time. You can answer them now or "
                "come back to this link later."),
    continue_label="Continue",
    none_picked="Tick at least one area, or choose No, that's all for now.",
    advice=("You chose {count} areas. Most people finish two or three at a time. You can "
            "still go ahead with all of them."),
    declined=("Thank you. We have everything we need for now, and we will be in touch "
              "soon to introduce your mentor."),
    reopen_label="Choose areas after all",
)


def is_intake(link: dict[str, Any]) -> bool:
    return bool(service.link_data(link).get("intake"))


def page_for(link: dict[str, Any]) -> Optional[registry.PageText]:
    """The engine's ``page_for`` hook: an intake link's own words."""
    return PAGE if is_intake(link) else None


def _definitions() -> dict[str, Survey]:
    return registry.definitions(service.PURPOSE) or {}


def offer(link: dict[str, Any]) -> Optional[registry.Offer]:
    """The engine's ``offer`` hook: on an intake link, until the client has
    picked areas. A no stays changeable (Doug, stopping point (a))."""
    if not is_intake(link):
        return None
    details = service.link_data(link).get("details")
    if details == DETAILS_YES:
        return None
    choices = [(c["key"], c["title"]) for c in area_choices(_definitions())]
    return registry.Offer(
        state="declined" if details == DETAILS_DECLINED else "ask",
        choices=choices, text=OFFER_TEXT, advise_max=ADVISED_MAX)


async def answer_offer(ctx: registry.OfferContext) -> None:
    """The engine's ``answer_offer`` hook (BE25). No: recorded, nothing else.
    Yes: one Business Evaluation record per area, the link's round, under the
    org-wide key; a record already made for that area in that round (a
    repeated press) is reused. Then the surveys are added to the link."""
    data = dict(service.link_data(ctx.link))
    if not ctx.accept:
        data["details"] = DETAILS_DECLINED
        await ctx.store.extend_link(ctx.link["id"], data)
        return
    surveys = _definitions()
    try:
        chosen = choose_areas(surveys, ctx.keys)
    except SendError:
        raise registry.OfferRefused(OFFER_TEXT.none_picked) from None
    engagement_id = ctx.link["record_id"]
    round_no = int(data.get("round") or 1)
    eng = await ctx.client.get(service.ENGAGEMENT, engagement_id, select="assignedUsersIds")
    existing = {(r.get("evaluationArea") or ""): r["id"]
                for r in await list_records(ctx.client, engagement_id)
                if (r.get("evaluationRound") or 0) == round_no}
    company = ctx.link.get("display_name") or ""
    now = service.utcnow()
    rows = []
    for survey in chosen:
        record_id = existing.get(survey.area)
        if not record_id:
            rec = await ctx.client.create(service.ENTITY, {
                "name": f"{survey.area} — {company}" if company else survey.area,
                "engagementId": engagement_id,
                "clientProfileId": data.get("client_profile_id"),
                "evaluationArea": survey.area,
                "evaluationRound": round_no,
                "status": STATUS_SENT,
                "sentAt": service.crm_stamp(now),
                "surveyVersion": survey.ref,
                "assignedUsersIds": list(eng.get("assignedUsersIds") or []),
            })
            record_id = rec["id"]
        rows.append((survey.key, survey.ref, record_id))
    data["details"] = DETAILS_YES
    data["area_keys"] = [s.key for s in chosen]
    await ctx.store.extend_link(ctx.link["id"], data, rows)
    log.info("evaluation intake link %s: client picked %s on engagement %s",
             ctx.link["id"], ", ".join(s.area for s in chosen), engagement_id)


# --- sending, when a client intake is delivered (BE24) ---------------------------

def enabled(settings: Any) -> bool:
    return bool(getattr(settings, "intake_survey", False)
                and getattr(settings, "business_evaluation", False))


_STORE: Any = None


def _store(settings: Any) -> Any:
    """The survey store, made once per process (it borrows the shared pool)."""
    global _STORE
    if _STORE is None:
        from surveys.store import make_survey_store

        _STORE = make_survey_store(settings)
    return _STORE


async def _send_shared(settings: Any, to: str, subject: str, body_html: str) -> None:
    from comms import service as comms_service

    gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
    try:
        await comms_service.send_quick_message(
            gmail=gmail, to=[to], subject=subject, body_html=body_html,
            sender_name=settings.sender_display_name)
    finally:
        await gmail.aclose()


Sender = Callable[[Any, str, str, str], Awaitable[None]]


async def on_delivered(settings: Any, submission: Any, ids: dict[str, Any], client: Any, *,
                       store: Any = None, send: Optional[Sender] = None,
                       now: Optional[datetime] = None) -> str:
    """Make the intake link and email it. Returns what happened, one word
    (for the log and the tests). Never raises."""
    try:
        return await _on_delivered(settings, submission, ids, client, store=store,
                                   send=send or _send_shared, now=now)
    except Exception as exc:  # noqa: BLE001 — never fails the intake
        log.warning("intake survey for engagement %s not sent: %s",
                    (ids or {}).get("engagementId"), exc)
        return "failed"


async def _on_delivered(settings: Any, submission: Any, ids: dict[str, Any], client: Any, *,
                        store: Any, send: Sender, now: Optional[datetime]) -> str:
    if not enabled(settings):
        return "off"
    engagement_id = (ids or {}).get("engagementId")
    profile_id = (ids or {}).get("clientProfileId")
    to = str(getattr(submission, "email", "") or "").strip()
    if not (engagement_id and profile_id and to):
        return "incomplete"
    if not (settings.ops_mailbox or "").strip():
        log.info("intake survey for engagement %s: no shared mailbox, so no email",
                 engagement_id)
        return "no-mailbox"
    store = store if store is not None else _store(settings)
    if store is None:
        return "no-database"
    if any(is_intake(l) for l in await links_for_engagement(store, engagement_id)):
        return "already"
    if not await entity_available(client):
        log.info("intake survey for engagement %s: the CRM has no Business Evaluation "
                 "record type, so no email", engagement_id)
        return "no-entity"
    surveys = _definitions()
    profile = latest(surveys, PROFILE_KEY)
    if profile is None:
        return "no-survey"
    prof = await client.get(service.CLIENT_PROFILE, profile_id,
                            select="name,linkedCompanyName,evaluationProfile")
    if (prof.get("evaluationProfile") or "").strip():
        log.info("intake survey for engagement %s: business profile already on file",
                 engagement_id)
        return "profile-on-file"
    company = (getattr(submission, "business_name", "") or prof.get("linkedCompanyName")
               or prof.get("name") or "")
    now = now or service.utcnow()
    link = await store.create_link(
        purpose=service.PURPOSE, entity_type=service.ENGAGEMENT, record_id=engagement_id,
        data={"client_profile_id": profile_id, "round": 1, "area_keys": [],
              "profile_needed": True, "intake": True},
        display_name=company, created_by=CREATED_BY,
        days=int(settings.evaluation_link_days), surveys=[(PROFILE_KEY, profile.ref, None)],
        now=now)
    from . import email as eval_email
    from .sending import link_url

    filled = eval_email.intake_invitation(
        org=settings.organization_name, first_name=getattr(submission, "first_name", "") or "",
        link_url=link_url(settings.app_base_url, link["token"]), expires_at=link["expires_at"])
    await send(settings, to, filled["subject"], filled["bodyHtml"])
    log.info("intake survey sent for engagement %s (link %s, %s)", engagement_id, link["id"],
             filled["version"])
    return "sent"


# --- Client Administration's Business profile tab (BE26) -------------------------

async def business_profile_view(user_client: Any, key_client: Any, store: Any,
                                engagement_id: str) -> dict[str, Any]:
    """What the tab shows. The staff member's own read of the engagement
    gates it (an ``EspoError`` from that read is the caller's to answer); the
    client profile is read as them too; the areas are read under the org-wide
    key and only area, round and status are kept."""
    eng = await user_client.get(service.ENGAGEMENT, engagement_id, select="engagementClientId")
    out: dict[str, Any] = {"profileHtml": None, "profileAt": None, "profileNote": "",
                           "areas": [], "declined": False, "areasNote": ""}
    profile_id = eng.get("engagementClientId")
    if profile_id:
        try:
            prof = await user_client.get(service.CLIENT_PROFILE, profile_id,
                                         select="evaluationProfile,evaluationProfileAt")
            out["profileHtml"] = profile_answers_html(prof.get("evaluationProfile") or "",
                                              _definitions())
            out["profileAt"] = prof.get("evaluationProfileAt")
        except EspoError as exc:
            log.warning("business profile tab %s: profile not read: %s", engagement_id, exc)
            out["profileNote"] = "The business profile could not be read with your access."
    if out["profileHtml"] is None and not out["profileNote"]:
        out["profileNote"] = "The client has not answered the business profile yet."
    if key_client is not None:
        try:
            records = await list_records(key_client, engagement_id)
            out["areas"] = [{"area": r.get("evaluationArea") or "",
                             "round": r.get("evaluationRound") or 0,
                             "status": r.get("status") or ""}
                            for r in records]
        except EspoError as exc:
            log.warning("business profile tab %s: areas not read: %s", engagement_id, exc)
            out["areasNote"] = "The areas the client picked could not be read just now."
    if store is not None:
        try:
            links = await links_for_engagement(store, engagement_id)
            out["declined"] = any(is_intake(l) and service.link_data(l).get("details")
                                  == DETAILS_DECLINED for l in links)
        except Exception as exc:  # noqa: BLE001 — the CRM part still shows
            log.warning("business profile tab %s: links not read: %s", engagement_id, exc)
    return out


# --- Assign (BE26, BE27) -----------------------------------------------------------

async def after_assign(settings: Any, key_client: Any, engagement_id: str, *,
                       first: bool, notify: Optional[Callable[[dict[str, Any]], Any]] = None
                       ) -> dict[str, int]:
    """Move the engagement's Business Evaluation records to its people: each
    record's ``assignedUsers`` gains the engagement's (merge, never remove),
    under the org-wide key. On a first assignment (not a repair, not a
    reassign), a draft already written while the engagement had no mentor is
    announced to the mentor now (BE27). Never raises."""
    counts = {"moved": 0, "told": 0, "errors": 0}
    if not getattr(settings, "business_evaluation", False) or key_client is None:
        return counts
    try:
        if not await entity_available(key_client):
            return counts
        eng = await key_client.get(service.ENGAGEMENT, engagement_id, select="assignedUsersIds")
        people = list(eng.get("assignedUsersIds") or [])
        page = await key_client.list(service.ENTITY, where=[
            {"type": "equals", "attribute": "engagementId", "value": engagement_id}],
            select="id,name,evaluationArea,engagementId,status,assignedUsersIds",
            max_size=200)
        records = page.get("list", []) or []
    except Exception as exc:  # noqa: BLE001 — never fails the assignment
        log.warning("evaluation records of engagement %s not moved: %s", engagement_id, exc)
        counts["errors"] += 1
        return counts
    if notify is None and first:
        from .analysis import make_notifier

        notify = make_notifier(settings, key_client)
    for rec in records:
        have = list(rec.get("assignedUsersIds") or [])
        merged = have + [u for u in people if u not in have]
        if merged != have:
            try:
                await key_client.update(service.ENTITY, rec["id"], {"assignedUsersIds": merged})
                counts["moved"] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("evaluation %s not moved to the mentor: %s", rec.get("id"), exc)
                counts["errors"] += 1
        if first and notify is not None and rec.get("status") == "Draft Ready":
            try:
                await notify(rec)
                counts["told"] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("evaluation %s: the mentor was not told: %s", rec.get("id"), exc)
                counts["errors"] += 1
    if any(counts.values()):
        log.info("evaluation records after assigning engagement %s: %s", engagement_id, counts)
    return counts
