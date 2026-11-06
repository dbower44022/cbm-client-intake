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
from core.espo import EspoClient

log = logging.getLogger("cbm_intake.activity")

SYSTEM_PERSON = "__system__"
NOTE_READ_SECONDS = 12.0
# Record types whose notes are never a person's change to a record.
_SKIP_PARENTS = {action_log.ACTION_LOG_ENTITY, "User", "Note"}
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


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


async def _person(key: Any, person_id: str) -> tuple[str, str]:
    """(user id, name) for the person asked about; ("", "") for none."""
    if not person_id:
        return "", ""
    if person_id == SYSTEM_PERSON:
        return SYSTEM_PERSON, ""
    rec = await key.get("User", person_id, select="id,name,userName")
    return str(rec.get("id") or ""), str(rec.get("name") or rec.get("userName") or "")


async def _action_rows(key: Any, uid: str, name: str, since: str, until: str):
    where: list[dict[str, Any]] = []
    if uid == SYSTEM_PERSON:
        where.append({"type": "startsWith", "attribute": "actorName",
                      "value": action_log.SYSTEM_ACTOR_PREFIX})
    elif name:
        where.append({"type": "equals", "attribute": "actorName", "value": name})
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


async def _note_rows(key: Any, uid: str, key_user: str, since: str, until: str):
    where: list[dict[str, Any]] = [
        {"type": "in", "attribute": "type", "value": ["Create", "Update", "Assign"]},
        {"type": "isNotNull", "attribute": "parentId"},
    ]
    author = key_user if uid == SYSTEM_PERSON else uid
    if author:
        where.append({"type": "equals", "attribute": "createdById", "value": author})
    if since:
        where.append({"type": "after", "attribute": "createdAt", "value": since})
    if until:
        where.append({"type": "before", "attribute": "createdAt", "value": until})
    rows, trunc = await history._paged(lambda off: key.list(  # noqa: SLF001
        "Note", where=where, max_size=history.PAGE, offset=off,
        order_by="createdAt", order="desc",
        select="type,data,createdAt,createdById,createdByName,parentType,parentId",
    ))
    return [r for r in rows if r.get("parentType") not in _SKIP_PARENTS], trunc


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
    uid, name = await _person(key, person_id)
    key_user = await history._key_user_id(key, settings)  # noqa: SLF001

    async def actions():
        try:
            rows, trunc = await _action_rows(key, uid, name, since, until)
            return rows, trunc, True
        except Exception as exc:  # noqa: BLE001
            log.warning("activity: action history unreadable: %s", exc)
            return [], False, False

    async def notes():
        try:
            got, trunc = await asyncio.wait_for(
                _note_rows(key, uid, key_user, since, until), NOTE_READ_SECONDS)
            return got, trunc, True, None
        except asyncio.TimeoutError:
            log.warning("activity: the CRM notes read took over %ss", NOTE_READ_SECONDS)
            return [], False, False, "slow"
        except Exception as exc:  # noqa: BLE001
            log.warning("activity: CRM notes unreadable: %s", exc)
            return [], False, False, "failed"

    (rows, rows_trunc, rows_ok), (crm, crm_trunc, crm_ok, why) = await asyncio.gather(
        actions(), notes())
    rows = [r for r in rows if history._visible(r, viewer, settings)]  # noqa: SLF001

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
    lines.sort(key=lambda ln: ln["at"], reverse=True)
    notice = None
    if why == "slow":
        notice = ("Changes made in the CRM's own screens could not be read in time on this "
                  "server, so only the applications' history is listed. This lifts once the "
                  "CRM's history settings are applied here (open item 66).")
    return {"lines": lines, "actionHistory": rows_ok, "crmNotes": crm_ok,
            "truncated": rows_trunc or crm_trunc, "notice": notice}
