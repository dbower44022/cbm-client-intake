"""The History engine — one record's changes, as staff read them.

Plan ``prds/mentor-login-integrity-plan.md`` § 4.5 (step 5). A History tab
merges two sources, newest first:

1. **The application's action history** (``CActionLog``), read under the
   application's key-based account — no mentor, partner or funder role reads
   it (check C8). It is the authority for every application action.
2. **The CRM's own record notes** (the record's stream), read as the
   signed-in person. Only the CRM's system notes (Create, Update, Status,
   Assign) are taken, **never a Post**: the applications write theirs as
   Post notes, and the ``CActionLog`` row already carries them.

The merge rule (build prompt v0.6): an application save of a tracked field
also produces a CRM Update note under the same person's name. That note is
**folded into** the ``CActionLog`` row with the same record, the same person
and the same fields within about a minute, so an application action shows
once and is never labelled "in the CRM directly". A change by the key-based
account is "System", and the job's name when a ``CActionLog`` row names it.

**The user's own read of the record gates the tab** — the first call here is
a read of the record as the signed-in person, and its refusal is the
caller's answer. Every list read is paged at 200 or below.

**Never shown:** record ids, raw data, who merely viewed, email contents,
passwords or keys. A line carries only a time, a person or "System", where,
one sentence, a kind, and field labels with displayable values.

Also here, for ruling Q5.4 (every History-tab application records old and new
values): :func:`same_value` and :func:`value_changes`, the one normalising
rule every mutating endpoint uses to say what moved.
"""

from __future__ import annotations

import asyncio
import copy
import html
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional

from . import action_log
from .config import Settings, get_settings
from .espo import EspoClient, EspoError

log = logging.getLogger("cbm_intake.history")

PAGE = 200          # the CRM refuses a larger page (root CLAUDE.md, maxSize)
MAX_ROWS = 1000     # per source; a record with more says so
FOLD_SECONDS = 90   # "within about a minute", with room for a slow save

CRM_DIRECT = "In the CRM directly"
SYSTEM = "System"
# The CRM's own note types taken from the stream. Post is never taken.
# (EspoCRM 9 writes a status change as an Update note carrying ``value``;
# "Status" is kept for an instance that still writes the older type.)
SYSTEM_NOTE_TYPES = ("Create", "Update", "Status", "Assign")

KIND_CREATED = "Created"
_NOTE_KIND = {
    "Create": KIND_CREATED,
    "Update": action_log.CAT_RECORD_EDIT,
    "Status": action_log.CAT_STATUS,
    "Assign": action_log.CAT_ASSIGNMENT,
}

# Action types shown only to some teams (plan § 4.5: Mentor Status-Admin
# entries are for the Mentor Administration and Client Administration teams).
# The hook is keyed on the action type; the staff-notes build writes the rows.
# Each value names the Settings properties holding the allowed team lists.
RESTRICTED_ACTIONS: dict[str, tuple[str, ...]] = {
    action_log.ACT_MENTOR_STATUS_ADMIN: (
        "mentor_admin_allowed_teams_list", "assign_allowed_teams_list"),
}

_ID_RE = re.compile(r"^[0-9a-f]{17}$")
_SECRET_RE = re.compile(r"pass(word|wd)|secret|token|api_?key|private_?key|credential",
                        re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_VALUE_MAX = 300


def history_on(settings: Optional[Settings] = None) -> bool:
    """``RECORD_HISTORY_TAB``, read per request."""
    return bool((settings or get_settings()).record_history_tab)


# --- Q5.4: what moved ---------------------------------------------------------


def same_value(a: Any, b: Any) -> bool:
    """A CRM value reads back normalised: an empty string as null, a list in
    any order, text with its surrounding white space trimmed (root CLAUDE.md,
    "A CRM text value does not read back byte-for-byte")."""
    def norm(v: Any) -> Any:
        if v in ("", None, []):
            return None
        if isinstance(v, list):
            return sorted(map(str, v))
        if isinstance(v, str):
            return v.replace("\r\n", "\n").strip()
        return v
    return norm(a) == norm(b)


def secret_field(name: str) -> bool:
    """A field whose value is never recorded or shown (a password or a key)."""
    return bool(_SECRET_RE.search(name or ""))


def value_changes(
    before: dict[str, Any], after: dict[str, Any], fields: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """``{field: {"from": old, "to": new}}`` for each of ``fields`` whose value
    moved between ``before`` and ``after``. A link field is recorded by its
    name attribute, never its id; a password or key is never recorded. An
    empty ``before`` (the record could not be read first) records the new
    value with no "from"."""
    out: dict[str, dict[str, Any]] = {}
    for name in fields:
        if secret_field(name):
            continue
        key = label = name
        if name.endswith("Id") and (name[:-2] + "Name") in after:
            key, label = name[:-2] + "Name", name[:-2]  # a link: its name, never the id
        elif name.endswith("Ids"):
            names_key = name[:-3] + "Names"
            if names_key in after:
                b = before.get(names_key) or {}
                a = after.get(names_key) or {}
                b_list = sorted(b.values()) if isinstance(b, dict) else []
                a_list = sorted(a.values()) if isinstance(a, dict) else []
                if not before or not same_value(b_list, a_list):
                    out[name[:-3]] = ({"to": a_list} if not before
                                      else {"from": b_list, "to": a_list})
            continue
        old, new = before.get(key), after.get(key)
        if before and same_value(old, new):
            continue
        out[label] = {"to": new} if not before else {"from": old, "to": new}
    return out


async def snapshot(client: Any, entity: str, record_id: str, attrs: Iterable[str]) -> dict[str, Any]:
    """The record's ``attrs`` as they stand, for a before-and-after record.
    Best-effort: an unreadable record returns ``{}`` and the action is still
    recorded, by field name only."""
    try:
        got = await client.get(entity, record_id, select=",".join(sorted(set(attrs))))
        # A copy: a client that hands back a live object (a cache, a fake)
        # must not let the write change what "before" says.
        return copy.deepcopy(got) if isinstance(got, dict) else {}
    except Exception as exc:  # noqa: BLE001 — history must never break the action
        log.warning("history: could not read %s/%s for its before-and-after: %s",
                    entity, record_id, exc)
        return {}


def link_attrs(fields: Iterable[str]) -> list[str]:
    """The attributes a snapshot reads for ``fields`` — a link field ``x``
    (or ``xId``) by its ``xId`` and ``xName``."""
    out: list[str] = []
    for f in fields:
        base = f[:-2] if f.endswith("Id") else f
        out += [f, base + "Id", base + "Name"] if f.endswith("Id") else [f]
    return out


def field_details(
    before: dict[str, Any], after: dict[str, Any], fields: Iterable[str],
) -> Any:
    """What ``CActionLog.details["fields"]`` holds for one save: the old and
    new values (ruling Q5.4) when the record was read after the write, else
    the field names alone — never a guess."""
    fields = [f for f in fields if not secret_field(f)]
    if not after:
        return sorted(f[:-2] if f.endswith("Id") else f for f in fields)
    return value_changes(before, after, fields)


# --- the engine ---------------------------------------------------------------

_key_user_cache: dict[str, tuple[float, str]] = {}


def _key_client(settings: Settings) -> Optional[EspoClient]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(settings.espo_base_url, settings.espo_api_key,
                      settings.request_timeout_seconds)


async def _key_user_id(key: EspoClient, settings: Settings) -> str:
    """The key-based account's user id (cached an hour), so its notes read
    as "System". A failed read is not cached: the next request tries again."""
    hit = _key_user_cache.get(settings.espo_base_url)
    if hit and time.monotonic() - hit[0] < 3600:
        return hit[1]
    try:
        data = await key.app_user()
        uid = str(((data or {}).get("user") or {}).get("id") or "")
    except Exception as exc:  # noqa: BLE001 — the tab still opens
        log.warning("history: could not read the key-based account: %s", exc)
        return ""
    if uid:
        _key_user_cache[settings.espo_base_url] = (time.monotonic(), uid)
    return uid


def _iso(stamp: Any) -> str:
    """A CRM stamp (UTC, ``YYYY-MM-DD HH:MM:SS``) as ISO 8601 with a Z."""
    s = str(stamp or "").strip()
    if not s:
        return ""
    return s.replace(" ", "T") + ("" if s.endswith("Z") else "Z")


def _epoch(stamp: Any) -> float:
    s = str(stamp or "").strip().replace("T", " ").rstrip("Z")
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def display_value(value: Any) -> str:
    """A value as a person reads it: never an id, never markup, clipped."""
    if value is None or value == "" or value == []:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        parts = [display_value(v) for v in value]
        return ", ".join(p for p in parts if p)
    if isinstance(value, dict):
        return ""  # raw data is never shown
    text = str(value)
    if _ID_RE.match(text):
        return ""
    if "<" in text and ">" in text:
        text = html.unescape(_TAG_RE.sub(" ", text))
    text = " ".join(text.split())
    return text if len(text) <= _VALUE_MAX else text[: _VALUE_MAX - 1] + "…"


async def _paged(fetch: Callable[[int], Awaitable[dict[str, Any]]]) -> tuple[list[dict], bool]:
    """Every row up to MAX_ROWS, a page of PAGE at a time; (rows, truncated)."""
    rows: list[dict] = []
    offset = 0
    while True:
        page = await fetch(offset)
        batch = list((page or {}).get("list") or [])
        rows.extend(batch)
        total = (page or {}).get("total")
        offset += len(batch)
        if len(batch) < PAGE or (isinstance(total, int) and offset >= total):
            return rows, False
        if len(rows) >= MAX_ROWS:
            return rows[:MAX_ROWS], True


async def _action_rows(key: EspoClient, entity: str, record_id: str) -> tuple[list[dict], bool]:
    where = [
        {"type": "equals", "attribute": "recordType", "value": entity},
        {"type": "equals", "attribute": "recordId", "value": record_id},
    ]
    return await _paged(lambda off: key.list(
        action_log.ACTION_LOG_ENTITY, where=where, max_size=PAGE, offset=off,
        order_by="createdAt", order="desc",
        select="name,app,category,actionType,actorName,actorId,summary,details,"
               "outcome,createdAt",
    ))


async def _stream_notes(user: EspoClient, entity: str, record_id: str) -> tuple[list[dict], bool]:
    from .espo import _encode_where_clause
    where = _encode_where_clause("where[0]", {
        "type": "in", "attribute": "type", "value": list(SYSTEM_NOTE_TYPES)})

    async def fetch(off: int) -> dict[str, Any]:
        resp = await user._request(  # noqa: SLF001 — the stream has no wrapper yet
            "GET", f"{user._base}/{entity}/{record_id}/stream",  # noqa: SLF001
            op=f"stream {entity}/{record_id}",
            params=[("maxSize", str(PAGE)), ("offset", str(off))] + where,
        )
        if resp.status_code >= 400:
            from .espo import http_error_detail
            raise EspoError(f"stream {entity}/{record_id} failed: {http_error_detail(resp)}")
        return resp.json()
    rows, truncated = await _paged(fetch)
    return [n for n in rows if n.get("type") in SYSTEM_NOTE_TYPES], truncated


async def tracked_fields(client: Any, entity: str) -> list[str]:
    """The record type's tracked ("Audited") fields, from the CRM's own
    definitions. Empty when none — the tab then says so and still shows the
    action history (production waits on the tracked-fields handoff)."""
    try:
        defs = await client.metadata(f"entityDefs.{entity}.fields")
    except Exception as exc:  # noqa: BLE001
        log.warning("history: field definitions of %s unreadable: %s", entity, exc)
        return []
    if not isinstance(defs, dict):
        return []
    return sorted(n for n, d in defs.items() if isinstance(d, dict) and d.get("audited"))


async def _scope(client: Any, entity: str) -> dict[str, Any]:
    """The record type's scope definition (stream on? its status field?)."""
    try:
        scope = await client.metadata(f"scopes.{entity}")
    except Exception:  # noqa: BLE001
        return {}
    return scope if isinstance(scope, dict) else {}


async def field_labels(client: Any, entity: str) -> dict[str, str]:
    try:
        data = await client.i18n(entity)
    except Exception:  # noqa: BLE001 — a humanised name is the fallback
        return {}
    fields = ((data or {}).get(entity) or {}).get("fields") or {}
    return {k: str(v) for k, v in fields.items()} if isinstance(fields, dict) else {}


def _humanize(name: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name or "").strip()
    return words[:1].upper() + words[1:] if words else ""


def _label(labels: dict[str, str], name: str) -> str:
    return labels.get(name) or _humanize(name)


def _details(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("details")
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def _row_changes(row: dict[str, Any], labels: dict[str, str]) -> tuple[list[dict], bool, set[str]]:
    """(changes, values recorded, field names) from a CActionLog row's details."""
    d = _details(row)
    fields = d.get("fields")
    changes: list[dict] = []
    names: set[str] = set()
    if isinstance(fields, dict):
        for name, v in fields.items():
            if secret_field(name) or not isinstance(v, dict):
                continue
            names.add(name)
            changes.append({"name": name, "field": _label(labels, name),
                            "from": display_value(v.get("from")),
                            "to": display_value(v.get("to")),
                            "hasFrom": "from" in v})
        return changes, True, names
    if isinstance(fields, list):
        for name in fields:
            if not isinstance(name, str) or secret_field(name):
                continue
            names.add(name)
            changes.append({"name": name, "field": _label(labels, name)})
        return changes, False, names
    if "from" in d and "to" in d and isinstance(d.get("to"), list):  # teams
        changes.append({"name": "teams", "field": "Teams",
                        "from": display_value(d.get("from")), "to": display_value(d.get("to")),
                        "hasFrom": True})
        return changes, True, {"teams"}
    return [], False, names


def _note_data(note: dict[str, Any]) -> dict[str, Any]:
    data = note.get("data") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    return data if isinstance(data, dict) else {}


def _note_fields(
    note: dict[str, Any], status_field: str = "",
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """(field names, was, became) carried by a CRM note.

    Shapes read on crm-test 11-06-26 (EspoCRM 9): a tracked-field change is
    an Update note with ``fields`` and ``attributes.was/became``; a change of
    the record type's status field is an Update note with ``value`` (the new
    status only — the old one is not kept), alone or beside ``fields``; an
    Assign note lists ``addedAssignedUsers`` / ``removedAssignedUsers`` (or,
    before multiple assigned users, ``assignedUserName``)."""
    data = _note_data(note)
    kind = note.get("type")
    if kind in ("Update", "Status"):
        attrs = data.get("attributes") or {}
        names = list(data.get("fields") or [])
        was = dict(attrs.get("was") or {}) if isinstance(attrs.get("was"), dict) else {}
        became = dict(attrs.get("became") or {}) if isinstance(attrs.get("became"), dict) else {}
        field = data.get("field") or status_field
        if data.get("value") is not None and field:
            if field not in names:
                names.append(field)
            became.setdefault(field, data.get("value"))
        return names, was, became
    if kind == "Assign":
        return ["assignedUsers"], {}, {}
    return [], {}, {}


def _note_kind(note: dict[str, Any]) -> str:
    """A status change is a Status Change, however the CRM wrote it (review 5a)."""
    if note.get("type") == "Update" and _note_data(note).get("value") is not None:
        return action_log.CAT_STATUS
    return _NOTE_KIND.get(str(note.get("type")), action_log.CAT_RECORD_EDIT)


def _note_value(attrs: dict[str, Any], name: str) -> Any:
    """A field's value inside a note's was/became, by its displayable attribute."""
    if name + "Name" in attrs:
        return attrs.get(name + "Name")
    if name + "Names" in attrs:
        names = attrs.get(name + "Names")
        return sorted(names.values()) if isinstance(names, dict) else names
    return attrs.get(name)


def _note_changes(note: dict[str, Any], labels: dict[str, str], status_field: str = "") -> list[dict]:
    if note.get("type") == "Assign":
        return []  # who was added and removed is the sentence itself
    names, was, became = _note_fields(note, status_field)
    out = []
    for name in names:
        if secret_field(name):
            continue
        ch: dict[str, Any] = {"name": name, "field": _label(labels, name)}
        if note.get("type") in ("Update", "Status"):
            ch["to"] = display_value(_note_value(became, name))
            if name in was or (name + "Name") in was or (name + "Names") in was:
                ch["from"] = display_value(_note_value(was, name))
                ch["hasFrom"] = True
        out.append(ch)
    return out


def _people(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return sorted(str(i.get("name")) for i in items if isinstance(i, dict) and i.get("name"))


def _note_sentence(note: dict[str, Any], changes: list[dict]) -> str:
    kind = note.get("type")
    if kind == "Create":
        return "Created the record."
    if kind == "Assign":
        data = _note_data(note)
        added, removed = _people(data.get("addedAssignedUsers")), _people(
            data.get("removedAssignedUsers"))
        if data.get("assignedUserName"):
            added = [str(data["assignedUserName"])]
        parts = ([f"assigned to {', '.join(added)}"] if added else []) + (
            [f"{', '.join(removed)} removed"] if removed else [])
        if not parts:
            return "Changed who the record is assigned to."
        text = "; ".join(parts)
        return text[:1].upper() + text[1:] + "."
    if len(changes) == 1 and "to" in changes[0] and not changes[0].get("hasFrom"):
        c = changes[0]
        return f"{c['field']} set to {c.get('to') or 'blank'}."
    if changes:
        return "Changed " + ", ".join(c["field"] for c in changes) + "."
    return "Changed the record."


def _who(actor_name: str) -> tuple[str, Optional[str]]:
    if actor_name.startswith(action_log.SYSTEM_ACTOR_PREFIX):
        return SYSTEM, actor_name[len(action_log.SYSTEM_ACTOR_PREFIX):]
    return actor_name or "Unknown", None


def _visible(row: dict[str, Any], viewer: dict[str, Any], settings: Settings) -> bool:
    lists = RESTRICTED_ACTIONS.get(str(row.get("actionType") or ""))
    if not lists:
        return True
    if viewer.get("isAdmin"):
        return True
    allowed: set[str] = set()
    for attr in lists:
        allowed.update(getattr(settings, attr, []) or [])
    return bool(set(viewer.get("teams") or []) & allowed)


_RAW_RE = re.compile(r"[\[{].*$", re.DOTALL)
_ID_ANYWHERE = re.compile(r"\b[0-9a-f]{17}\b")


def clean_sentence(text: str) -> str:
    """A recorded sentence as staff may read it: no record id, no raw data
    (a CRM error body quoted after "did not complete"), clipped."""
    text = _ID_ANYWHERE.sub("…", str(text or ""))
    text = _RAW_RE.sub("…", text).strip()
    return text if len(text) <= _VALUE_MAX else text[: _VALUE_MAX - 1] + "…"


def _app_line(row: dict[str, Any], labels: dict[str, str]) -> dict[str, Any]:
    who, job = _who(str(row.get("actorName") or ""))
    changes, recorded, _ = _row_changes(row, labels)
    return {
        "at": _iso(row.get("createdAt")),
        "who": who, "job": job,
        "where": str(row.get("app") or "") or "The application",
        "what": clean_sentence(str(row.get("summary") or row.get("name") or "")),
        "kind": str(row.get("category") or ""),
        "outcome": str(row.get("outcome") or "Success"),
        "changes": changes,
        "valuesRecorded": recorded,
        "source": "app",
    }


def _same_person(a: Any, b: Any) -> bool:
    a, b = " ".join(str(a or "").split()).casefold(), " ".join(str(b or "").split()).casefold()
    return bool(a) and a == b


def _fold_target(
    note: dict[str, Any], rows: list[dict[str, Any]], key_user: str, status_field: str = "",
) -> Optional[int]:
    """The index of the CActionLog row this CRM note belongs to, or None.

    ``CActionLog`` keeps the actor's NAME only (it has no actor id field;
    read on crm-test 11-06-26), so the person is matched by name — the
    session's name is the CRM user's name, which is what the note carries."""
    t = _epoch(note.get("createdAt"))
    by = str(note.get("createdById") or "")
    note_names, _, _ = _note_fields(note, status_field)
    kind = note.get("type")
    best: Optional[tuple[float, int]] = None
    for i, row in enumerate(rows):
        dt = abs(_epoch(row.get("createdAt")) - t)
        if dt > FOLD_SECONDS:
            continue
        actor = str(row.get("actorName") or "")
        system_row = actor.startswith(action_log.SYSTEM_ACTOR_PREFIX)
        if key_user and by == key_user:
            if not system_row:
                continue
        elif system_row or not _same_person(actor, note.get("createdByName")):
            continue
        _, _, row_names = _row_changes(row, {})
        category = row.get("category")
        details = _details(row)
        # A row that moved a login link (a save's reconcile, the status
        # sweep) explains an Assign note; provisioning explains any note it
        # caused — the status, the CBM email and the login link (review 5a).
        moves_login = bool(details.get("loginLinks")) or any(
            k in details for k in ("profileLogin", "contactLoginAdded"))
        if kind == "Create":
            ok = "creat" in str(row.get("actionType") or "").lower()
        elif category == action_log.CAT_PROVISIONING and kind in ("Update", "Status", "Assign"):
            ok = True
        elif kind == "Assign":
            ok = category == action_log.CAT_ASSIGNMENT or moves_login
        elif row_names:
            # Every field the note carries must be one the row says it moved:
            # sharing one field is not enough, or a direct edit made in the
            # same minute would hide inside the application's line.
            ok = bool(note_names) and set(note_names) <= row_names
        else:
            ok = category in (action_log.CAT_RECORD_EDIT, action_log.CAT_STATUS)
        if ok and (best is None or dt < best[0]):
            best = (dt, i)
    return best[1] if best else None


def _fold(line: dict[str, Any], note_changes: list[dict]) -> None:
    """Fill a line's missing values from a folded CRM note."""
    by_name = {c["name"]: c for c in line["changes"]}
    for nc in note_changes:
        have = by_name.get(nc["name"])
        if have is None:
            line["changes"].append(nc)
            by_name[nc["name"]] = nc
        elif "to" not in have and "to" in nc:
            have.update({k: nc[k] for k in ("from", "to", "hasFrom") if k in nc})
    if line["changes"] and all("to" in c for c in line["changes"]):
        line["valuesRecorded"] = True


def merge(
    rows: list[dict[str, Any]], notes: list[dict[str, Any]], *,
    labels: dict[str, str], key_user: str, status_field: str = "",
) -> list[dict[str, Any]]:
    """The merge rule, pure: CActionLog rows are the authority; each CRM note
    folds into its row or becomes a line of its own; newest first."""
    lines = [_app_line(r, labels) for r in rows]
    for note in notes:
        if note.get("type") not in SYSTEM_NOTE_TYPES:
            continue  # never a Post: the applications write theirs as Post
        changes = _note_changes(note, labels, status_field)
        i = _fold_target(note, rows, key_user, status_field)
        if i is not None:
            _fold(lines[i], changes)
            continue
        by = str(note.get("createdById") or "")
        system = bool(key_user) and by == key_user
        lines.append({
            "at": _iso(note.get("createdAt")),
            "who": SYSTEM if system else (str(note.get("createdByName") or "") or "Unknown"),
            "job": None,
            "where": "The application" if system else CRM_DIRECT,
            "what": _note_sentence(note, changes),
            "kind": _note_kind(note),
            "outcome": "Success",
            "changes": changes,
            "valuesRecorded": all("to" in c for c in changes),
            "source": "crm",
        })
    for line in lines:
        for c in line["changes"]:
            c.pop("name", None)
    lines.sort(key=lambda ln: ln["at"], reverse=True)
    return lines


async def record_history(
    user_client: Any, entity: str, record_id: str, *, viewer: dict[str, Any],
    settings: Optional[Settings] = None, key_client: Any = None,
) -> dict[str, Any]:
    """One record's History tab. Raises ``EspoError`` when the signed-in
    person cannot read the record — that read is the gate."""
    settings = settings or get_settings()
    await user_client.get(entity, record_id, select="id")
    key = key_client if key_client is not None else _key_client(settings)

    async def actions() -> tuple[list[dict], bool, bool]:
        if key is None or not await action_log._entity_available(key):  # noqa: SLF001
            return [], False, False
        try:
            rows, trunc = await _action_rows(key, entity, record_id)
            return rows, trunc, True
        except Exception as exc:  # noqa: BLE001 — a bad body (200, not JSON) too
            log.warning("history: action history of %s/%s unreadable: %s", entity, record_id, exc)
            return [], False, False

    scope = await _scope(key or user_client, entity)

    async def notes() -> tuple[list[dict], bool, bool]:
        if not scope.get("stream"):
            return [], False, True
        try:
            got, trunc = await _stream_notes(user_client, entity, record_id)
            return got, trunc, True
        except Exception as exc:  # noqa: BLE001 — a bad body (200, not JSON) too
            log.warning("history: CRM notes of %s/%s unreadable: %s", entity, record_id, exc)
            return [], False, False

    meta = key or user_client
    (rows, rows_trunc, rows_ok), (crm, crm_trunc, crm_ok), tracked, labels, key_user = (
        await asyncio.gather(
            actions(), notes(), tracked_fields(meta, entity), field_labels(meta, entity),
            _key_user_id(key, settings) if key is not None else _empty(),
        ))
    rows = [r for r in rows if _visible(r, viewer, settings)]
    lines = merge(rows, crm, labels=labels, key_user=key_user,
                  status_field=str(scope.get("statusField") or ""))
    return {
        "lines": lines,
        "tracked": bool(tracked),
        "actionHistory": rows_ok,
        "crmNotes": crm_ok,
        "truncated": rows_trunc or crm_trunc,
    }


async def _empty() -> str:
    return ""
