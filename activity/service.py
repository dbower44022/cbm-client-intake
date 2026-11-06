"""The activity page — every change by one person, or in a date range, across
every record (mentor login integrity plan § 4.5, step 6).

Same line format as the History tab (``core/history.py``), one more column:
the record the change was made on, by its type and name — never its id.
Every read here runs under the application's key-based account: the page is
gated to the System Management Team (and Administrator-type logins), whose
whole job is to see across records.

Two sources, as on the History tab: the application's action history
(``CActionLog``) and the CRM's own Create, Update and Assign notes, listed
across record types by author and date (check before step 6, crm-test
11-06-26: the key may list ``Note`` by type, author and date; 120-160 ms).
The CRM-notes read is bounded by ``NOTE_READ_SECONDS``: where it is too slow
— production, until step 0's production half lands — the page lists the
application history alone and says so.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from typing import Any, Optional

from core import action_log, history
from core.config import Settings, get_settings
from core.espo import EspoClient, is_not_found

log = logging.getLogger("cbm_intake.activity")

SYSTEM_PERSON = "__system__"
NOTE_READ_SECONDS = 12.0
# Record types whose notes are never a person's change to a record, or whose
# record name is an email subject or a submitter (review 6): left out in the
# query itself, so they never use up the row cap.
_SKIP_PARENTS = [action_log.ACTION_LOG_ENTITY, "User", "Note", "Email", "CConversation",
                 "CCommunication", "CIntakeSubmission"]
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_USER_ID_RE = re.compile(r"^[0-9a-f]{17}$")
_SLOW_NOTICE = ("The CRM took too long to list its own record changes, so the oldest of "
                "them may be missing. Narrow the dates to see them all.")
_NO_KEY_NOTICE = ("The application's own account could not be identified just now, so "
                  "changes it made in the CRM are not listed. Try again in a minute.")


class ActivityError(Exception):
    """A request the page can answer in words (400)."""


def key_client(settings: Settings) -> Optional[EspoClient]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(settings.espo_base_url, settings.espo_api_key,
                      settings.request_timeout_seconds)


async def people(key: Any) -> list[dict[str, str]]:
    """Every person with a login (active or not — history outlives a login),
    by name, plus "System". Ids stay server-side; the page sends one back
    only as the person it asks about."""
    rows, _ = await history._paged(lambda off: key.list(  # noqa: SLF001
        "User", select="id,name,userName,type,isActive", max_size=history.PAGE, offset=off,
        where=[{"type": "in", "attribute": "type", "value": ["regular", "admin"]}],
        order_by="name", order="asc",
    ))
    out = [{"id": r["id"], "name": str(r.get("name") or r.get("userName") or ""),
            "active": bool(r.get("isActive", True))}
           for r in rows if r.get("id")]
    out.sort(key=lambda p: p["name"].casefold())
    return [{"id": SYSTEM_PERSON, "name": "System (the application's own jobs)", "active": True}] + out


def _stamp(value: str, label: str) -> str:
    v = (value or "").strip().replace("T", " ").rstrip("Z")[:19]
    if v and not _STAMP_RE.match(v):
        raise ActivityError(f"The {label} date could not be read.")
    return v


async def _person(key: Any, person_id: str) -> tuple[str, list[str]]:
    """(user id, the names the action history may hold for them) for the
    person asked about; ("", []) for none. ``CActionLog`` keeps a name, not
    an id, and System Settings writes the login name — so both are asked."""
    if not person_id:
        return "", []
    if person_id == SYSTEM_PERSON:
        return SYSTEM_PERSON, []
    if not _USER_ID_RE.match(person_id):
        raise ActivityError("That person was not found.")
    try:
        rec = await key.get("User", person_id, select="id,name,userName,emailAddress")
    except Exception as exc:  # noqa: BLE001
        if is_not_found(exc):
            raise ActivityError("That person was not found.") from exc
        raise
    names = [str(rec.get(k) or "").strip() for k in ("name", "userName", "emailAddress")]
    return str(rec.get("id") or ""), sorted({n for n in names if n})


async def _action_rows(key: Any, uid: str, names: list[str], since: str, until: str):
    where: list[dict[str, Any]] = []
    if uid == SYSTEM_PERSON:
        where.append({"type": "startsWith", "attribute": "actorName",
                      "value": action_log.SYSTEM_ACTOR_PREFIX})
    elif names:
        where.append({"type": "in", "attribute": "actorName", "value": names})
    if since:
        where.append({"type": "after", "attribute": "createdAt", "value": since})
    if until:
        where.append({"type": "before", "attribute": "createdAt", "value": until})
    return await history._paged(lambda off: key.list(  # noqa: SLF001
        action_log.ACTION_LOG_ENTITY, where=where, max_size=history.PAGE, offset=off,
        order_by="createdAt", order="desc",
        select="name,app,category,actionType,actorName,summary,details,outcome,"
               "createdAt,recordType,recordId",
    ))


async def _note_rows(
    key: Any, uid: str, key_user: str, since: str, until: str,
    budget: Optional[float] = None,
) -> tuple[list[dict], bool, bool]:
    """(notes, truncated, too slow). The read stops when ``budget`` runs out
    and keeps the pages it already has (review 6)."""
    where: list[dict[str, Any]] = [
        {"type": "in", "attribute": "type", "value": list(history.SYSTEM_NOTE_TYPES)},
        {"type": "isNotNull", "attribute": "parentId"},
        {"type": "notIn", "attribute": "parentType", "value": _SKIP_PARENTS},
    ]
    author = key_user if uid == SYSTEM_PERSON else uid
    if author:
        where.append({"type": "equals", "attribute": "createdById", "value": author})
    if since:
        where.append({"type": "after", "attribute": "createdAt", "value": since})
    if until:
        where.append({"type": "before", "attribute": "createdAt", "value": until})
    budget = NOTE_READ_SECONDS if budget is None else budget
    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget
    rows: list[dict] = []
    while True:
        left = deadline - loop.time()
        if left <= 0:
            return rows, True, True
        try:
            page = await asyncio.wait_for(key.list(
                "Note", where=where, max_size=history.PAGE, offset=len(rows),
                order_by="createdAt", order="desc",
                select="type,data,createdAt,createdById,createdByName,parentType,parentId",
            ), left)
        except asyncio.TimeoutError:
            log.warning("activity: the CRM notes read passed %ss after %d rows", budget, len(rows))
            return rows, True, True
        batch = list((page or {}).get("list") or [])
        rows.extend(r for r in batch if r.get("parentType") not in _SKIP_PARENTS)
        total = (page or {}).get("total")
        if len(batch) < history.PAGE or (isinstance(total, int) and len(rows) >= total):
            return rows, False, False
        if len(rows) >= history.MAX_ROWS:
            return rows[:history.MAX_ROWS], True, False


async def _names(key: Any, refs: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Each record's name, read in batches per type; an unreadable one is
    simply unnamed (never its id)."""
    by_type: dict[str, list[str]] = defaultdict(list)
    for etype, rid in refs:
        by_type[etype].append(rid)
    out: dict[tuple[str, str], str] = {}
    for etype, ids in by_type.items():
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            try:
                page = await key.list(etype, select="id,name", max_size=len(chunk),
                                      where=[{"type": "in", "attribute": "id", "value": chunk}])
            except Exception as exc:  # noqa: BLE001 — the line still shows
                log.info("activity: names of %s unreadable: %s", etype, exc)
                continue
            for r in (page or {}).get("list") or []:
                out[(etype, str(r.get("id")))] = history.display_value(r.get("name"))
    return out


async def _type_labels(key: Any) -> dict[str, str]:
    try:
        data = await key.i18n("Global")
    except Exception:  # noqa: BLE001
        return {}
    names = ((data or {}).get("Global") or {}).get("scopeNames") or {}
    return {k: str(v) for k, v in names.items()} if isinstance(names, dict) else {}


def _same_window(
    rows: list[dict], rows_trunc: bool, notes: list[dict], notes_trunc: bool,
) -> tuple[list[dict], list[dict]]:
    """When a source stopped at its row cap, the two sources reach back to
    different times; keep only the span both cover, or a note loses the row
    it folds into and reads as a direct edit (review 6)."""
    oldest = []
    if rows_trunc and rows:
        oldest.append(min(history._epoch(r.get("createdAt")) for r in rows))  # noqa: SLF001
    if notes_trunc and notes:
        oldest.append(min(history._epoch(n.get("createdAt")) for n in notes))  # noqa: SLF001
    if not oldest:
        return rows, notes
    cut = max(oldest) + history.FOLD_SECONDS
    keep = lambda x: history._epoch(x.get("createdAt")) >= cut  # noqa: E731,SLF001
    return [r for r in rows if keep(r)], [n for n in notes if keep(n)]


def _credit_linked_records(lines: list[dict], rows: list[dict]) -> None:
    """A CRM note on ANOTHER record, by the same person within the minute of
    an application action, is that action's work: an Assign re-homes the
    engagement's contacts, client profile and company as the signed-in
    person (review 6). The line keeps its own record and is credited to the
    application instead of "In the CRM directly"."""
    acts = [(history._epoch(r.get("createdAt")), str(r.get("actorName") or ""),  # noqa: SLF001
             str(r.get("app") or "")) for r in rows]
    for ln in lines:
        if ln.get("source") != "crm" or ln.get("where") != history.CRM_DIRECT:
            continue
        t = history._epoch(ln["at"])  # noqa: SLF001
        near = [(abs(t - at), app) for at, actor, app in acts
                if app and abs(t - at) <= history.FOLD_SECONDS
                and history._same_person(actor, ln.get("who"))]  # noqa: SLF001
        if near:
            ln["where"] = min(near)[1]


async def activity(
    *, person_id: str, since: str, until: str, viewer: dict[str, Any],
    settings: Optional[Settings] = None, key: Any = None,
) -> dict[str, Any]:
    """The activity page's lines, newest first, each naming its record."""
    settings = settings or get_settings()
    since, until = _stamp(since, "From"), _stamp(until, "To")
    if not person_id and not (since and until):
        raise ActivityError("Choose a person, or both a From and a To date.")
    key = key if key is not None else key_client(settings)
    if key is None:
        return {"lines": [], "actionHistory": False, "crmNotes": False, "truncated": False,
                "notice": "The CRM is not connected on this server."}
    uid, names = await _person(key, person_id)
    key_user = await history._key_user_id(key, settings)  # noqa: SLF001

    async def actions():
        try:
            rows, trunc = await _action_rows(key, uid, names, since, until)
            return rows, trunc, True
        except Exception as exc:  # noqa: BLE001
            log.warning("activity: action history unreadable: %s", exc)
            return [], False, False

    async def notes():
        if uid == SYSTEM_PERSON and not key_user:
            # Without the account's id the author filter would vanish and
            # list everybody's changes under "System" (review 6).
            return [], False, False, _NO_KEY_NOTICE
        try:
            got, trunc, slow = await _note_rows(key, uid, key_user, since, until)
            return got, trunc, True, _SLOW_NOTICE if slow else None
        except Exception as exc:  # noqa: BLE001
            log.warning("activity: CRM notes unreadable: %s", exc)
            return [], False, False, None

    (rows, rows_trunc, rows_ok), (crm, crm_trunc, crm_ok, notice) = await asyncio.gather(
        actions(), notes())
    rows = [r for r in rows if history._visible(r, viewer, settings)]  # noqa: SLF001
    rows, crm = _same_window(rows, rows_trunc, crm, crm_trunc)

    groups: dict[tuple[str, str], tuple[list, list]] = defaultdict(lambda: ([], []))
    for r in rows:
        groups[(str(r.get("recordType") or ""), str(r.get("recordId") or ""))][0].append(r)
    for n in crm:
        groups[(str(n.get("parentType") or ""), str(n.get("parentId") or ""))][1].append(n)
    refs = {k for k in groups if k[0] and k[1]}
    types = {k[0] for k in refs}
    names, type_labels = await asyncio.gather(_names(key, refs), _type_labels(key))
    labels = dict(zip(types, await asyncio.gather(*(history.field_labels(key, t) for t in types))))
    scopes = dict(zip(types, await asyncio.gather(*(history._scope(key, t) for t in types))))  # noqa: SLF001

    lines: list[dict[str, Any]] = []
    for (etype, rid), (g_rows, g_notes) in groups.items():
        merged = history.merge(
            g_rows, g_notes, labels=labels.get(etype, {}), key_user=key_user,
            status_field=str((scopes.get(etype) or {}).get("statusField") or ""))
        record = ""
        if etype:
            tlabel = type_labels.get(etype) or history._humanize(etype)  # noqa: SLF001
            record = f"{tlabel}: {names.get((etype, rid)) or '(name not readable)'}"
        for ln in merged:
            ln["record"] = record
        lines.extend(merged)
    _credit_linked_records(lines, rows)
    lines.sort(key=lambda ln: ln["at"], reverse=True)
    return {"lines": lines, "actionHistory": rows_ok, "crmNotes": crm_ok,
            "truncated": rows_trunc or crm_trunc, "notice": notice}
