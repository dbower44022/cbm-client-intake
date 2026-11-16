"""Release of the client version, and action items as records (plan § 3
step 7; rulings BE19 and BE20). Phase 5.

Doug's choices at stopping point (a), 11-15-26, all as recommended:

* **Action items are `CActionItem` records** (open question 1, option A):
  linked to the engagement and to its Business Evaluation, an owner who is a
  Contact (the client's people and the mentors alike), a due date, a status
  (Open, Done, Dropped), the priority, the time horizon and the reason. They
  carry the engagement's ``assignedUsers`` like the evaluation itself.
* **The client version is a PDF** filed in the engagement's Documents, made
  by Google Drive from the HTML :func:`client_document` builds: the reviewed
  report without every ``data-internal`` section (BE19), under a header
  naming the organisation, the area, the company, the mentor and the review
  date, with the agreed action items and a closing note added.
* **One Release dialog per area**: the action items read from the reviewed
  report's table, each ticked as agreed, with an owner and a due date, plus
  any added by hand. Release writes the items, files the PDF, sets Reviewed
  with Client and ``releasedAt``, and returns the email for the composer
  with the PDF attached.
* **A released report is locked**: Reviewed with Client is not editable
  (``review.EDITABLE``), and a released area cannot be released again.

Rules kept here:

* **Made from ``reviewedReport``, never the draft** (BE17): this module
  does not name the draft.
* **Only the engagement's mentor releases**, as only the mentor approves.
* **Release is retry-safe**: an action item already on the evaluation with
  the same title is not made again, and the router reuses a document of the
  same file name, so a release interrupted after its first writes can simply
  be pressed again. The status is written last.
"""

from __future__ import annotations

import html as htmllib
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Optional

from bs4 import BeautifulSoup

from core.espo import EspoError, is_forbidden

from . import review, service
from .service import ENGAGEMENT

log = logging.getLogger("cbm_intake.evaluation")

STATUS_RELEASED = "Reviewed with Client"
ACTION_ITEM = "CActionItem"
#: The link on CEngagement to its action items (crm-plans/action-item.json).
ENGAGEMENT_ITEMS_LINK = "actionItems"
ITEM_OPEN = "Open"
ITEM_STATUSES = ("Open", "Done", "Dropped")
PRIORITIES = ("High", "Medium", "Low")
HORIZON_DAYS = {"Next 30 days": 30, "Next 90 days": 90, "Next 12 months": 365}
MAX_ITEMS = 30

ITEMS_UNAVAILABLE = (
    "Action items are not available yet: this CRM does not have the Action Item "
    "record type. An administrator applies action-item-crm-handoff.md to add it.")

ITEM_SELECT = ("id,name,status,dueDate,priority,timeHorizon,reason,ownerId,ownerName,"
               "businessEvaluationId,businessEvaluationName,engagementId")


class ReleaseError(review.ReviewError):
    """A release the application refuses, with the words to show (400)."""


# --- the client version (BE19) -------------------------------------------------------

def client_body(reviewed_html: str) -> str:
    """The reviewed report without every element marked ``data-internal``,
    and without its opening ``<h2>`` title, which the client document's
    header replaces."""
    soup = BeautifulSoup(reviewed_html or "", "html.parser")
    for el in soup.find_all(attrs={"data-internal": True}):
        el.decompose()
    first = next((c for c in soup.contents if getattr(c, "name", None)), None)
    if first is not None and first.name == "h2":
        first.decompose()
    return str(soup).strip()


def _cell_text(td: Any) -> str:
    return re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip() if td else ""


def parse_action_items(reviewed_html: str) -> list[dict[str, str]]:
    """The action items in the reviewed report's "Recommended action items"
    table: title (the bold text), reason (the rest), priority and when. A
    reviewer may have reworded or reshaped the table; whatever cannot be read
    is left out, and the mentor adds it in the dialog."""
    soup = BeautifulSoup(reviewed_html or "", "html.parser")
    heading = next((h for h in soup.find_all(re.compile(r"^h[1-6]$"))
                    if "action item" in h.get_text(" ", strip=True).lower()), None)
    table = heading.find_next("table") if heading else None
    if table is None:
        return []
    items: list[dict[str, str]] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        cell = tds[1]
        strong = cell.find(["strong", "b"])
        title = _cell_text(strong) if strong else ""
        full = _cell_text(cell)
        reason = full[len(title):].strip() if title and full.startswith(title) else ("" if title else "")
        if not title:
            title, reason = full, ""
        if not title:
            continue
        priority = _cell_text(tds[2]) if len(tds) > 2 else ""
        when = _cell_text(tds[3]) if len(tds) > 3 else ""
        items.append({"title": title[:255], "reason": reason,
                      "priority": priority if priority in PRIORITIES else "",
                      "timeHorizon": when if when in HORIZON_DAYS else ""})
    return items


def long_date(on: date) -> str:
    """"November 16, 2026"."""
    return f"{on:%B} {on.day}, {on.year}"


CLOSING_NOTE = (
    "This evaluation is based on the answers you gave in your survey. An AI service "
    "prepared a first draft, and your mentor reviewed and corrected every word before "
    "going through it with you. It is a starting point for our conversations, not an "
    "audit of your business.")

_DOC_STYLE = (
    "body{font-family:Georgia,'Times New Roman',serif;font-size:11pt;line-height:1.45;color:#1f2523}"
    "h1{font-size:20pt;margin:4pt 0}h3{font-size:13pt;margin:14pt 0 4pt}"
    ".org{font-family:Arial,sans-serif;font-size:9pt;letter-spacing:1px;text-transform:uppercase;color:#1d5b79}"
    ".by{font-family:Arial,sans-serif;font-size:10pt;color:#5d6762}"
    "table{border-collapse:collapse;width:100%}th,td{border:1px solid #cfd5d1;padding:4pt;"
    "vertical-align:top;text-align:left}th{font-family:Arial,sans-serif;font-size:9pt}"
    ".close{font-size:10pt;color:#5d6762}")


def client_document(*, org: str, area: str, company: str, mentor: str, reviewed_on: date,
                    body_html: str, agreed: list[dict[str, str]]) -> str:
    """The client version as one HTML document, ready for Drive to turn into
    a PDF. ``body_html`` is :func:`client_body`'s output; ``agreed`` holds
    each agreed item's ``title``, ``owner`` (a name) and ``due`` (a date)."""
    e = htmllib.escape
    title = f"{area} evaluation: {company}" if company else f"{area} evaluation"
    by = f"Prepared with you by {e(mentor)} · " if mentor else ""
    parts = [
        f'<p class="org">{e(org)}</p>',
        f"<h1>{e(title)}</h1>",
        f'<p class="by">{by}Reviewed together on {e(long_date(reviewed_on))}</p>',
        "<hr>",
        body_html,
    ]
    if agreed:
        rows = "".join(
            f"<tr><td>{n}</td><td>{e(a['title'])}</td><td>{e(a.get('owner') or '')}</td>"
            f"<td>{e(long_date(a['due'])) if a.get('due') else ''}</td></tr>"
            for n, a in enumerate(agreed, start=1))
        parts.append("<h3>Action items we agreed</h3><table><thead><tr><th>#</th><th>Action</th>"
                     f"<th>Who</th><th>By when</th></tr></thead><tbody>{rows}</tbody></table>")
    parts.append(f'<p class="close">{e(CLOSING_NOTE)}</p>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{e(title)}</title>'
            f"<style>{_DOC_STYLE}</style></head><body>{''.join(parts)}</body></html>")


def document_filename(company: str, area: str, on: date) -> str:
    """"Brightline Bakehouse - Marketing evaluation - 2026-11-16.pdf"; no
    character a file name cannot hold."""
    stem = " - ".join(p for p in (company.strip(), f"{area} evaluation", on.isoformat()) if p)
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", stem).strip() + ".pdf"


# --- reading what the dialog needs -------------------------------------------------

async def items_available(client: Any) -> bool:
    """True when the CRM has the Action Item record type."""
    try:
        meta = await client.metadata(f"entityDefs.{ACTION_ITEM}")
    except EspoError as exc:
        log.warning("evaluation: action item metadata read failed: %s", exc)
        return False
    return isinstance(meta, dict) and bool(meta.get("fields"))


async def _record(client: Any, engagement_id: str, record_id: str) -> dict[str, Any]:
    rec = await client.get(service.ENTITY, record_id, select=(
        "id,engagementId,evaluationArea,evaluationRound,status,reviewedReport,"
        "reviewSessionId,reviewSessionName,releasedAt"))
    if rec.get("engagementId") != engagement_id:
        raise ReleaseError("That evaluation is not on this engagement.")
    return rec


def _check_releasable(rec: dict[str, Any]) -> None:
    area = rec.get("evaluationArea") or "This evaluation"
    status = rec.get("status") or ""
    if status == STATUS_RELEASED:
        raise ReleaseError(f"{area} was already released to the client"
                           + (f" on {str(rec['releasedAt'])[:10]}." if rec.get("releasedAt") else ".")
                           + " A released report is final.")
    if status != review.STATUS_APPROVED:
        raise ReleaseError(f"Only an approved report can be released. {area} is "
                           f"{status or 'without a status'}.")
    if not rec.get("reviewSessionId"):
        raise ReleaseError(f"Schedule the review session for round {rec.get('evaluationRound')} "
                           "first: the report is released after you go through it with the client.")


async def _session_day(client: Any, session_id: str, today: date) -> date:
    """The review session's date, or today when it cannot be read."""
    try:
        sess = await client.get(review.SESSION, session_id, select="dateStart")
        stamp = (sess.get("dateStart") or "")[:10]
        return date.fromisoformat(stamp) if stamp else today
    except (EspoError, ValueError) as exc:
        log.warning("evaluation: review session %s not read: %s", session_id, exc)
        return today


async def owner_choices(client: Any, engagement_id: str,
                        reader: Optional[Any] = None) -> list[dict[str, str]]:
    """Who can own an action item: the engagement's client contacts, then its
    mentor and co-mentors, each as their Contact. A mentor without a linked
    Contact is left out. ``reader`` (the org-wide key) reads mentor profiles a
    co-mentor may not."""
    eng = await client.get(ENGAGEMENT, engagement_id, select=(
        "primaryEngagementContactId,primaryEngagementContactName,mentorProfileId"))
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(cid: Optional[str], name: Optional[str], kind: str) -> None:
        if cid and cid not in seen:
            seen.add(cid)
            out.append({"id": cid, "name": name or "", "kind": kind})

    add(eng.get("primaryEngagementContactId"), eng.get("primaryEngagementContactName"), "client")
    try:
        page = await client.list_related(ENGAGEMENT, engagement_id, "engagementContacts",
                                         select="id,name", max_size=200)
        for c in page.get("list", []) or []:
            add(c.get("id"), c.get("name"), "client")
    except EspoError as exc:
        log.warning("evaluation: contacts of %s not read: %s", engagement_id, exc)
    profiles: list[dict[str, Any]] = []
    if eng.get("mentorProfileId"):
        for who in (reader, client):
            if who is None:
                continue
            try:
                profiles.append(await who.get(review.MENTOR_PROFILE, eng["mentorProfileId"],
                                              select="name,contactRecordId,contactRecordName"))
                break
            except EspoError as exc:
                log.warning("evaluation: mentor profile not read: %s", exc)
    try:
        page = await client.list_related(ENGAGEMENT, engagement_id, "additionalMentors",
                                         select="name,contactRecordId,contactRecordName",
                                         max_size=200)
        profiles += page.get("list", []) or []
    except EspoError as exc:
        log.warning("evaluation: co-mentors of %s not read: %s", engagement_id, exc)
    for p in profiles:
        add(p.get("contactRecordId"), p.get("contactRecordName") or p.get("name"), "mentor")
    return out


def not_the_mentor_message(mentor: dict[str, Any]) -> str:
    name = mentor["name"] or "the engagement's mentor"
    return f"Only the engagement's mentor, {name}, can release a report to the client."


async def release_view(client: Any, engagement_id: str, record_id: str, *,
                       org: str, reader: Optional[Any] = None,
                       user_id: Optional[str] = None,
                       today: Optional[date] = None) -> dict[str, Any]:
    """What the Release dialog shows: whether the area can be released (and
    why not: someone other than the engagement's mentor, given ``user_id``,
    is told so here, before the dialog opens), the client version's text,
    the action items read from the report with their default due dates, and
    who can own one."""
    rec = await _record(client, engagement_id, record_id)
    blocked = ""
    if user_id is not None:
        mentor = await review.engagement_mentor(client, engagement_id, reader=reader)
        if not review.is_mentor(mentor, user_id):
            blocked = not_the_mentor_message(mentor)
    if not blocked:
        try:
            _check_releasable(rec)
        except ReleaseError as exc:
            blocked = str(exc)
    today = today or service.utcnow().date()
    day = (await _session_day(client, rec["reviewSessionId"], today)
           if rec.get("reviewSessionId") else today)
    items = parse_action_items(rec.get("reviewedReport") or "")
    for it in items:
        it["due"] = (day + timedelta(days=HORIZON_DAYS.get(it["timeHorizon"], 30))).isoformat()
    owners = await owner_choices(client, engagement_id, reader=reader)
    return {
        "id": record_id, "area": rec.get("evaluationArea") or "",
        "round": rec.get("evaluationRound"), "status": rec.get("status") or "",
        "blocked": blocked,
        "reviewSession": rec.get("reviewSessionName") or "",
        "reviewedOn": day.isoformat(),
        "clientHtml": client_body(rec.get("reviewedReport") or ""),
        "items": items, "owners": owners,
        "defaultOwner": owners[0]["id"] if owners else "",
        "itemsAvailable": await items_available(client),
    }


# --- Release ---------------------------------------------------------------------------

def check_items(items: list[dict[str, Any]], owners: list[dict[str, str]]) -> list[dict[str, Any]]:
    """The agreed items, checked: a title, an owner from the choices, a real
    due date. Raises ``ReleaseError`` naming the first problem by its number."""
    by_id = {o["id"]: o for o in owners}
    out: list[dict[str, Any]] = []
    if len(items) > MAX_ITEMS:
        raise ReleaseError(f"At most {MAX_ITEMS} action items can be agreed in one release.")
    for n, it in enumerate(items, start=1):
        title = re.sub(r"\s+", " ", str(it.get("title") or "")).strip()
        if not title:
            raise ReleaseError(f"Action item {n} has no wording. Type what was agreed, or untick it.")
        owner = by_id.get(str(it.get("ownerId") or ""))
        if owner is None:
            raise ReleaseError(f"Choose who owns action item {n}, \"{title[:60]}\".")
        try:
            due = date.fromisoformat(str(it.get("due") or ""))
        except ValueError:
            raise ReleaseError(f"Give action item {n}, \"{title[:60]}\", a due date.") from None
        priority = it.get("priority") if it.get("priority") in PRIORITIES else None
        horizon = it.get("timeHorizon") if it.get("timeHorizon") in HORIZON_DAYS else None
        out.append({"title": title[:255], "reason": str(it.get("reason") or "").strip(),
                    "ownerId": owner["id"], "owner": owner["name"], "due": due,
                    "priority": priority, "timeHorizon": horizon})
    return out


async def _write(client: Any, escalate: Optional[Callable[[], Any]], method: str,
                 *args: Any) -> dict[str, Any]:
    """Write as the user; retry under the org-wide key only on a refusal."""
    try:
        return await getattr(client, method)(*args) or {}
    except EspoError as exc:
        key = escalate() if escalate and is_forbidden(exc) else None
        if key is None:
            raise
        log.info("evaluation: %s %s refused as the user (%s); under the org-wide key",
                 method, args[0], exc)
        return await getattr(key, method)(*args) or {}


async def items_for(client: Any, engagement_id: str,
                    evaluation_id: Optional[str] = None) -> list[dict[str, Any]]:
    """The engagement's action items the user can read, optionally only those
    of one evaluation. Pages at 200."""
    where = [{"type": "equals", "attribute": "engagementId", "value": engagement_id}]
    if evaluation_id:
        where.append({"type": "equals", "attribute": "businessEvaluationId", "value": evaluation_id})
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await client.list(ACTION_ITEM, where=where, select=ITEM_SELECT, max_size=200,
                                 offset=offset, order_by="dueDate", order="asc")
        batch = page.get("list", []) or []
        rows += batch
        offset += len(batch)
        if not batch or offset >= (page.get("total") or 0):
            return rows


FileDocument = Callable[[str, str], Awaitable[dict[str, Any]]]


async def release(client: Any, engagement_id: str, record_id: str, *, user_id: str,
                  items: list[dict[str, Any]], org: str, file_document: FileDocument,
                  escalate: Optional[Callable[[], Any]] = None,
                  now: Optional[datetime] = None) -> dict[str, Any]:
    """Release one area: check it may be released by this user, write the
    agreed action items, file the client version through ``file_document``
    (``(html, filename) -> document row``), then set Reviewed with Client and
    ``releasedAt``. Returns what the router logs and the page needs."""
    rec = await _record(client, engagement_id, record_id)
    area = rec.get("evaluationArea") or ""
    reader = escalate() if escalate else None
    mentor = await review.engagement_mentor(client, engagement_id, reader=reader)
    if not review.is_mentor(mentor, user_id):
        raise review.NotTheMentor(not_the_mentor_message(mentor))
    _check_releasable(rec)
    owners = await owner_choices(client, engagement_id, reader=reader)
    agreed = check_items(items, owners)
    if agreed and not await items_available(client):
        raise ReleaseError(ITEMS_UNAVAILABLE)
    now = now or service.utcnow()
    eng = await client.get(ENGAGEMENT, engagement_id,
                           select="assignedUsersIds,clientOrganizationName,name")
    company = eng.get("clientOrganizationName") or ""
    day = await _session_day(client, rec["reviewSessionId"], now.date())

    # 1. The action items, skipping any already made by an earlier attempt.
    existing = {re.sub(r"\s+", " ", (r.get("name") or "")).strip().lower()
                for r in (await items_for(client, engagement_id, record_id) if agreed else [])}
    made: list[dict[str, Any]] = []
    for it in agreed:
        if it["title"].lower() in existing:
            continue
        payload = {"name": it["title"], "reason": it["reason"], "status": ITEM_OPEN,
                   "dueDate": it["due"].isoformat(), "ownerId": it["ownerId"],
                   "engagementId": engagement_id, "businessEvaluationId": record_id,
                   "assignedUsersIds": list(eng.get("assignedUsersIds") or [])}
        if it["priority"]:
            payload["priority"] = it["priority"]
        if it["timeHorizon"]:
            payload["timeHorizon"] = it["timeHorizon"]
        row = await _write(client, escalate, "create", ACTION_ITEM, payload)
        made.append({"id": row.get("id"), "title": it["title"], "owner": it["owner"],
                     "due": it["due"].isoformat()})

    # 2. The client version, filed in Documents (BE19).
    doc_html = client_document(
        org=org, area=area, company=company, mentor=mentor["name"], reviewed_on=day,
        body_html=client_body(rec.get("reviewedReport") or ""),
        agreed=[{"title": a["title"], "owner": a["owner"], "due": a["due"]} for a in agreed])
    filename = document_filename(company or eng.get("name") or "", area, day)
    document = await file_document(doc_html, filename)

    # 3. The status, last.
    await _write(client, escalate, "update", service.ENTITY, record_id,
                 {"status": STATUS_RELEASED, "releasedAt": service.crm_stamp(now)})
    return {
        "id": record_id, "area": area, "round": rec.get("evaluationRound"),
        "document": document, "items": made, "agreed": len(agreed),
        "releasedAt": service.crm_stamp(now),
        "fields": {"status": {"from": review.STATUS_APPROVED, "to": STATUS_RELEASED},
                   "released at": {"from": "", "to": service.crm_stamp(now)},
                   "action items": {"from": "", "to": f"{len(agreed)} agreed"}},
    }


# --- Tracking the action items ----------------------------------------------------------

async def set_item_status(client: Any, engagement_id: str, item_id: str, status: str,
                          escalate: Optional[Callable[[], Any]] = None) -> dict[str, Any]:
    """Mark an action item Open, Done or Dropped, as the user."""
    if status not in ITEM_STATUSES:
        raise ReleaseError(f"An action item is {', '.join(ITEM_STATUSES[:-1])} or {ITEM_STATUSES[-1]}.")
    item = await client.get(ACTION_ITEM, item_id, select="id,name,status,engagementId")
    if item.get("engagementId") != engagement_id:
        raise ReleaseError("That action item is not on this engagement.")
    before = item.get("status") or ""
    if before != status:
        await _write(client, escalate, "update", ACTION_ITEM, item_id, {"status": status})
    return {"id": item_id, "title": item.get("name") or "", "changed": before != status,
            "fields": {"status": {"from": before, "to": status}}}
