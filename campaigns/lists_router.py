"""Campaign audiences — the Lists API at ``/campaigns/api/lists`` and a
campaign's choice of list (build plan § 7c, reshaped by § 7e.8; rulings
58–68 and 90–98).

A dynamic list is a search: Include groups minus Leave out groups, run now or
at every campaign build, never edited by hand — a person kept off it goes onto
a static exclusion list through *Exclude*. A static list is people added by
hand: *Add people* (a condition panel or a name or email box), *Remove*, never
run. A list's kind is fixed; *Copy* makes a static list of the current members.

Behind ``CAMPAIGNS_ENABLED`` and ``CAMPAIGN_LISTS`` (both read per request,
404 while off) and the campaigns team gate. Every run and search is under the
org-wide API client, like every campaign selection; what a marketing user is
shown of a member is its name and the curated fields the recipe used (ruling
63). Every change is recorded through ``record_action``.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.action_log import CAT_RECORD_EDIT, CAT_STATUS, record_action
from core.config import Settings, get_settings
from core.espo import EspoError

import asyncio

from . import audience, list_sync
from . import config as cfg
from .audience import AudienceError
from .audience_store import (
    KIND_DYNAMIC, KIND_STATIC, KINDS, SOURCE_HAND, STATE_IN, STATUS_ACTIVE, STATUS_RETIRED,
)
from .router import APP_CAMPAIGNS, _actor, _api_client, _campaign_or_404, _crm_failure, _store

log = logging.getLogger("cbm_intake.campaigns.lists")

lists_router = APIRouter(prefix="/campaigns/api", tags=["campaign-lists"])

_MEMBERS_PAGE = 50
#: Searching or sorting the member grid by name reads every member's name
#: from the CRM; above this many it is refused in words (export instead).
MEMBER_SEARCH_CAP = 2000
#: Rows an export may hold.
EXPORT_CAP = 10000
#: People one *Add people* may add, and records its search may find.
ADD_CAP = 2000
#: Records the *Add people* search shows to tick (select all takes them all).
FIND_SHOWN = 200

KIND_FIXED = ("A list's kind is fixed when it is created. For a frozen copy of a dynamic list, "
              "use Copy to a new static list.")


def _require_lists(settings: Settings) -> None:
    if not settings.campaign_lists:
        raise HTTPException(status_code=404, detail="Campaign lists are switched off (Campaign lists at /setup).")


def _who(user: dict) -> str:
    return user.get("name") or user.get("userName") or ""


async def _log(client, user: dict, action: str, summary: str, *, category: str = CAT_RECORD_EDIT,
               details: Optional[dict] = None, parent_type: str = "", parent_id: str = "") -> None:
    await record_action(client, app=APP_CAMPAIGNS, category=category, action=action,
                        parent_type=parent_type, parent_id=parent_id, summary=summary,
                        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
                        details=details or {})


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else None


def _public(row: dict[str, Any], *, used: int = 0, members: Optional[int] = None,
            last_used: Optional[datetime] = None) -> dict[str, Any]:
    last = row.get("last_run") or {}
    if members is None and row["kind"] == KIND_DYNAMIC:
        members = last.get("total")
    return {
        "id": row["id"], "name": row["name"], "notes": row.get("notes") or "", "kind": row["kind"],
        "status": row["status"], "version": row["version"],
        "recipe": row["recipe"] if row["kind"] == KIND_DYNAMIC else audience.empty_recipe(),
        "needsRebuild": bool(row.get("needs_rebuild")),
        "lastRunAt": _iso(row.get("last_run_at")), "lastRunBy": row.get("last_run_by") or "",
        "lastRun": last if row["kind"] == KIND_DYNAMIC else {},
        "members": members, "usedBy": used, "lastUsed": _iso(last_used),
        "createdBy": row.get("created_by") or "", "updatedBy": row.get("updated_by") or "",
        "updatedAt": _iso(row.get("updated_at")),
        # The copy in Constant Contact (§ 7e.9); the page shows it when the
        # session says listSyncOn.
        "ccSync": bool(row.get("cc_sync")), "ccHasCopy": bool(row.get("cc_list_id")),
        "ccLastSyncAt": _iso(row.get("cc_last_sync_at")), "ccLastSync": row.get("cc_last_sync") or {},
        "ccStatus": list_sync.status_words(row),
    }


async def _list_or_404(store, list_id: str) -> dict[str, Any]:
    row = await store.get_list(list_id)
    if not row:
        raise HTTPException(status_code=404, detail="List not found.")
    return row


def _not_retired(row: dict[str, Any]) -> None:
    if row["status"] == STATUS_RETIRED:
        raise HTTPException(status_code=400, detail="A retired list cannot be changed — reactivate it first.")


def _static_only(row: dict[str, Any], what: str) -> None:
    if row["kind"] != KIND_STATIC:
        raise HTTPException(status_code=400, detail=(
            f"{what} is for static lists. A dynamic list is a search: change who is on it with Edit, "
            "or keep one person off it with Exclude."))


def _dynamic_only(row: dict[str, Any], what: str) -> None:
    if row["kind"] != KIND_DYNAMIC:
        raise HTTPException(status_code=400, detail=(
            f"{what} is for dynamic lists. A static list holds the people added to it: use Add people "
            "and Remove."))


async def _catalogue(request: Request, settings: Settings) -> dict[str, Any]:
    client = _api_client(settings, request)
    try:
        return await audience.catalogue(client, settings)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the CRM's fields")


async def _list_names(store) -> dict[str, str]:
    return {r["id"]: r["name"] for r in await store.all_lists()}


# --- the field catalogue ------------------------------------------------------------------

@lists_router.get("/lists/catalogue")
async def list_catalogue(request: Request) -> dict[str, Any]:
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    cat = await _catalogue(request, settings)
    return {"types": cat,
            "groupKinds": [{"kind": k, "label": audience.GROUP_LABELS[k]} for k in audience.GROUP_KINDS],
            "sides": [{"side": s, "label": audience.SIDE_LABELS[s]} for s in audience.SIDES],
            "stepCap": audience.STEP_CAP, "addCap": ADD_CAP, "findShown": FIND_SHOWN}


# --- finding records by name or email, across the five types ---------------------------------

_SEARCH_ATTRS = {"lead": ["businessName", "name", "email"], "contact": ["name", "emailAddress"]}


@lists_router.get("/lists/search/records")
async def search_records(request: Request, type: str = "all", q: str = "") -> dict[str, Any]:
    """Find records by name or email — every type at once (``type=all``) or
    one. The static list's *Add people* name-or-email box."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    if type != "all" and type not in audience.TYPES_BUILT:
        raise HTTPException(status_code=400, detail="Search leads, contacts, clients, partners or funders.")
    q = q.strip()
    if len(q) < 2:
        return {"records": []}
    client = _api_client(settings, request)
    out = []
    for t in (audience.TYPES_BUILT if type == "all" else (type,)):
        attrs = _SEARCH_ATTRS.get(t, ["name"])
        try:
            page = await client.list(audience.TYPES[t]["entity"], select="id," + audience.NAME_FIELDS[t],
                                     max_size=10 if type == "all" else 20, where=[{"type": "or", "value": [
                                         {"type": "contains", "attribute": a, "value": q} for a in attrs]}])
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not search")
        out += [{"key": f"{t}:{r['id']}", "type": t,
                 "name": (r.get("businessName") or r.get("name") or "") if t == "lead" else r.get("name") or ""}
                for r in page.get("list", [])]
    return {"records": out}


# --- lists --------------------------------------------------------------------------------

class ListIn(BaseModel):
    name: str = Field("", max_length=200)
    notes: str = Field("", max_length=4000)
    kind: str = KIND_STATIC
    recipe: dict[str, Any] = Field(default_factory=audience.empty_recipe)


def _validated(body: ListIn) -> tuple[str, str, str, dict[str, Any]]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the list a name.")
    if body.kind not in KINDS:
        raise HTTPException(status_code=400, detail="A list is static or dynamic.")
    # A static list has no search (ruling 91): whatever was sent, it is empty.
    recipe = audience.normalise_recipe(body.recipe) if body.kind == KIND_DYNAMIC else audience.empty_recipe()
    return name, body.notes.strip(), body.kind, recipe


async def _refuse_cycle(store, recipe: dict[str, Any], list_id: str) -> None:
    if await audience.reaches(store, audience.referenced_lists(recipe), list_id):
        raise HTTPException(status_code=400,
                            detail="A list cannot include itself, directly or through another list — "
                                   "choose a different list in that group.")


@lists_router.get("/lists")
async def all_lists(request: Request) -> dict[str, Any]:
    _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    used = await store.usage_counts()
    counts = await store.member_counts()
    last = await store.last_used()
    # The members the grid shows: a static list's people, a dynamic list's
    # last run (less anyone Exclude has taken off since); None = never run.
    return {"lists": [_public(r, used=used.get(r["id"], 0),
                              members=None if r["kind"] == KIND_DYNAMIC and r.get("last_run_at") is None
                              else counts.get(r["id"], 0),
                              last_used=last.get(r["id"]))
                      for r in await store.all_lists()]}


@lists_router.post("/lists")
async def create_list(body: ListIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    name, notes, kind, recipe = _validated(body)
    for lid in audience.referenced_lists(recipe):
        if not await store.get_list(lid):
            raise HTTPException(status_code=400, detail="A group names a list that no longer exists — choose another.")
    row = await store.create_list(name=name, notes=notes, kind=kind, recipe=recipe, actor=_who(user))
    await _log(client, user, "Campaign List Created", f"Created the {kind} list \"{name}\"",
               details={"list": row["id"]})
    return {"list": _public(row)}


@lists_router.get("/lists/{list_id}")
async def get_list(list_id: str, request: Request) -> dict[str, Any]:
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    using = await store.campaigns_using(list_id)
    members = None
    if row["kind"] == KIND_STATIC:
        members = sum(1 for m in await store.member_rows(list_id) if m.get("state") == STATE_IN)
    out: dict[str, Any] = {
        "list": _public(row, used=len(using), members=members),
        "problems": [], "sentences": audience.empty_recipe(),
        "versions": [{"version": v["version"], "kind": v["kind"], "savedBy": v.get("saved_by") or "",
                      "savedAt": v["saved_at"].isoformat()} for v in await store.list_versions(list_id)],
    }
    if row["kind"] == KIND_DYNAMIC:
        cat = await _catalogue(request, settings)
        recipe = audience.normalise_recipe(row["recipe"])
        out["problems"] = audience.check_recipe(recipe, cat)
        out["sentences"] = audience.describe_recipe(recipe, cat, await _list_names(store))
    return out


@lists_router.put("/lists/{list_id}")
async def save_list(list_id: str, body: ListIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    _not_retired(row)
    if body.kind != row["kind"]:
        raise HTTPException(status_code=400, detail=KIND_FIXED)
    name, notes, kind, recipe = _validated(body)
    await _refuse_cycle(store, recipe, list_id)
    settings = get_settings()
    if name != row["name"] and row.get("cc_sync") and settings.campaign_list_sync:
        _refuse_copy_name(settings, name)
        await _refuse_twin(store, name, list_id)
    saved = await store.save_list(list_id, name=name, notes=notes, kind=kind, recipe=recipe, actor=_who(user))
    if saved["version"] != row["version"]:
        await _log(client, user, "Campaign List Changed",
                   f"Changed the list \"{name}\" — now version {saved['version']}",
                   details={"list": list_id, "version": saved["version"]})
    out: dict[str, Any] = {"list": _public(saved)}
    if name != row["name"] and saved.get("cc_list_id") and settings.campaign_list_sync:
        # The copy follows the rename now; if the vendor refuses, the next
        # sync renames it (it finds the copy by its id).
        problem = await list_sync.rename_copy(settings, saved["cc_list_id"], name)
        out["copyNote"] = (f"The copy in Constant Contact is renamed \"{name}\"." if not problem else
                           f"The copy in Constant Contact keeps its old name for now — the next sync renames "
                           f"it ({problem}).")
    return out


class PreviewIn(BaseModel):
    recipe: dict[str, Any] = Field(default_factory=audience.empty_recipe)
    listId: Optional[str] = None


@lists_router.post("/lists/preview")
async def preview(body: PreviewIn, request: Request) -> dict[str, Any]:
    """A dynamic recipe's counts, one per group, without saving — the
    builder's *Count*."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    cat = await _catalogue(request, settings)
    recipe = audience.normalise_recipe(body.recipe)
    store = getattr(request.app.state, "campaign_store", None)
    try:
        result = await audience.run_recipe(_api_client(settings, request), recipe, cat, store=store,
                                           _seen=(body.listId,) if body.listId else ())
    except AudienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not count the list")
    return {"groups": result["groups"], "included": result["included"], "leftOut": result["leftOut"],
            "total": result["total"]}


@lists_router.post("/lists/{list_id}/run")
async def run_list(list_id: str, request: Request) -> dict[str, Any]:
    """A dynamic list run now, to show who it holds today — a campaign build
    runs it again (ruling 62). A static list is never run (ruling 91)."""
    user, client = _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if row["kind"] == KIND_STATIC:
        raise HTTPException(status_code=400, detail=(
            "A static list is never run — it holds exactly the people added to it."))
    if row["status"] == STATUS_RETIRED:
        raise HTTPException(status_code=400, detail="A retired list does not run — reactivate it first.")
    cat = await _catalogue(request, settings)
    try:
        result = await audience.run_recipe(_api_client(settings, request), audience.normalise_recipe(row["recipe"]),
                                           cat, store=store, _seen=(list_id,))
    except AudienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not run the list")
    recipe = audience.normalise_recipe(row["recipe"])
    run = {"groups": result["groups"], "included": result["included"], "leftOut": result["leftOut"],
           "total": result["total"], "version": row["version"], "include": recipe["include"]}
    await store.replace_recipe_members(list_id, result["keys"], run=run, actor=_who(user))
    await _log(client, user, "Campaign List Run",
               f"Ran the list \"{row['name']}\": {result['total']} members as of now",
               details={"list": list_id, "version": row["version"], "groups": result["groups"]})
    return {"run": run}


# --- members --------------------------------------------------------------------------

def _member_keys(row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Optional[int]]:
    """key → the Include group that brought it in (None on a static list)."""
    if row["kind"] == KIND_STATIC:
        return {r["target_key"]: None for r in rows if r.get("state") == STATE_IN and r.get("source") == SOURCE_HAND}
    return {r["target_key"]: r.get("group_index") for r in rows if r.get("state") == STATE_IN}


def _brought_in_by(row: dict[str, Any], cat: Optional[dict[str, Any]], names: dict[str, str]):
    """group index → its sentence, while the Include groups are the ones the
    last run used (a changed Leave out, such as Exclude's, keeps the
    numbering); and whether the list has changed since that run."""
    if row["kind"] != KIND_DYNAMIC or cat is None:
        return lambda gi: None, False
    last = row.get("last_run") or {}
    include = audience.normalise_recipe(row["recipe"])["include"]
    same_groups = audience.normalise_recipe({"include": last.get("include") or [], "exclude": []})["include"] == include \
        if "include" in last else last.get("version") == row["version"]

    def label(gi: Optional[int]) -> Optional[str]:
        if not same_groups or not gi or gi > len(include):
            return None
        return audience.describe_group(include[gi - 1], cat, names)
    return label, last.get("version") != row["version"]


@lists_router.get("/lists/{list_id}/members")
async def members(list_id: str, request: Request, offset: int = 0, limit: int = _MEMBERS_PAGE,
                  q: str = "", sort: str = "", dir: str = "asc") -> dict[str, Any]:
    """The list's members, a page at a time: a static list's people, a
    dynamic list's last run. Search (``q``, by name) and sort by ``name``,
    ``type`` or ``broughtInBy``."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    keyed = _member_keys(row, await store.member_rows(list_id))
    cat = await _catalogue(request, settings)
    recipe = audience.normalise_recipe(row["recipe"]) if row["kind"] == KIND_DYNAMIC else audience.empty_recipe()
    client = _api_client(settings, request)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = q.strip().lower()
    reverse = dir == "desc"
    if q or sort == "name":
        if len(keyed) > MEMBER_SEARCH_CAP:
            raise HTTPException(status_code=400, detail=(
                f"This list has more than {MEMBER_SEARCH_CAP:,} members, too many to search or sort by name "
                "here — export it and search the file."))
        try:
            described = await audience.describe_members(client, list(keyed), recipe, cat)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not read the members")
        if q:
            described = [m for m in described if q in (m["name"] or "").lower()]
        if sort == "name":
            described.sort(key=lambda m: (m["name"] or "").lower(), reverse=reverse)
        elif sort == "type":
            described.sort(key=lambda m: m["type"], reverse=reverse)
        elif sort == "broughtInBy":
            described.sort(key=lambda m: keyed.get(m["key"]) or 0, reverse=reverse)
        total = len(described)
        page = described[offset: offset + limit]
    else:
        keys = sorted(keyed)
        if sort == "type":
            keys.sort(key=lambda k: audience.split_key(k)[0], reverse=reverse)
        elif sort == "broughtInBy":
            keys.sort(key=lambda k: keyed.get(k) or 0, reverse=reverse)
        total = len(keys)
        try:
            page = await audience.describe_members(client, keys[offset: offset + limit], recipe, cat)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not read the members")
    label, stale = _brought_in_by(row, cat, await _list_names(store))
    for m in page:
        m["broughtInBy"] = label(keyed.get(m["key"]))
    return {"members": page, "total": total, "offset": offset, "limit": limit,
            "neverRun": row["kind"] == KIND_DYNAMIC and row.get("last_run_at") is None,
            "changedSinceRun": stale and row.get("last_run_at") is not None}


def _csv_line(values: list[Any]) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerow(["" if v is None else v for v in values])
    return buf.getvalue()


@lists_router.get("/lists/{list_id}/export")
async def export_members(list_id: str, request: Request) -> StreamingResponse:
    """The members as a CSV file: type, name, brought in by (dynamic), the
    curated fields the recipe used, the CRM id — the leads export's shape."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    keyed = _member_keys(row, await store.member_rows(list_id))
    if len(keyed) > EXPORT_CAP:
        raise HTTPException(status_code=400, detail=f"An export holds at most {EXPORT_CAP:,} members.")
    cat = await _catalogue(request, settings)
    recipe = audience.normalise_recipe(row["recipe"]) if row["kind"] == KIND_DYNAMIC else audience.empty_recipe()
    try:
        described = await audience.describe_members(_api_client(settings, request), sorted(keyed), recipe, cat)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not export the list")
    described.sort(key=lambda m: (m["type"], (m["name"] or "").lower()))
    label, _stale = _brought_in_by(row, cat, await _list_names(store))
    cols: list[str] = []
    for m in described:
        cols += [c for c in m["values"] if c not in cols]
    dynamic = row["kind"] == KIND_DYNAMIC
    header = ["Type", "Name"] + (["Brought in by"] if dynamic else []) + cols + ["CRM id"]

    async def gen() -> AsyncIterator[str]:
        yield "﻿" + _csv_line(header)
        for m in described:
            yield _csv_line([audience.TYPES.get(m["type"], {}).get("one", m["type"]), m["name"]]
                            + ([label(keyed.get(m["key"])) or ""] if dynamic else [])
                            + [m["values"].get(c) for c in cols] + [m["id"]])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe = "".join(ch if ch.isalnum() else "-" for ch in row["name"]).strip("-")[:60] or "list"
    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{safe}-{stamp}.csv"'})


@lists_router.get("/lists/{list_id}/counts")
async def counts(list_id: str, request: Request) -> dict[str, Any]:
    """How many the members reach per channel — Email, Text, Postcard — each
    count ``resolve_targets`` for that kind, read as its count only (ruling
    98). Computed on demand from the members the grid shows, never stored."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if row["kind"] == KIND_DYNAMIC and row.get("last_run_at") is None:
        return {"counts": None, "members": None, "neverRun": True}
    keyed = _member_keys(row, await store.member_rows(list_id))
    try:
        result = await audience.channel_counts(_api_client(settings, request), list(keyed))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not count the list per channel")
    return {"counts": result, "members": len(keyed), "neverRun": False}


# --- a static list: Add people and Remove (ruling 94) -------------------------------------

class MarkIn(BaseModel):
    key: str = Field(..., max_length=64)
    state: str = STATE_IN
    note: str = Field("", max_length=500)


def _valid_key(key: str) -> str:
    t, _, rid = key.partition(":")
    if t not in audience.TYPES_BUILT or not rid or len(rid) > 40:
        raise HTTPException(status_code=400, detail="That is not a lead, contact, client, partner or funder.")
    return key


@lists_router.post("/lists/{list_id}/mark")
async def mark(list_id: str, body: MarkIn, request: Request) -> dict[str, Any]:
    """Add one person to a static list by hand."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    _static_only(row, "Adding a person by hand")
    _not_retired(row)
    key = _valid_key(body.key)
    if body.state != STATE_IN:
        raise HTTPException(status_code=400, detail="To take someone off a static list, press Remove.")
    await store.hand_mark(list_id, key, STATE_IN, _who(user))
    await _log(client, user, "Campaign List Edited", f"{key} added by hand to the list \"{row['name']}\"",
               details={"list": list_id, "key": key})
    return {"ok": True}


class UnmarkIn(BaseModel):
    key: str = Field(..., max_length=64)


@lists_router.post("/lists/{list_id}/unmark")
async def unmark(list_id: str, body: UnmarkIn, request: Request) -> dict[str, Any]:
    """*Remove*: take a person off a static list."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    _static_only(row, "Remove")
    _not_retired(row)
    key = _valid_key(body.key)
    await store.hand_clear(list_id, key)
    await _log(client, user, "Campaign List Edited", f"{key} removed from the list \"{row['name']}\"",
               details={"list": list_id, "key": key})
    return {"ok": True}


class AddPeopleIn(BaseModel):
    keys: list[str] = Field(default_factory=list)


@lists_router.post("/lists/{list_id}/add-people")
async def add_people(list_id: str, body: AddPeopleIn, request: Request) -> dict[str, Any]:
    """The ticked records join a static list, copied once — no search is saved
    (ruling 94)."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    _static_only(row, "Add people")
    _not_retired(row)
    keys = list(dict.fromkeys(_valid_key(k) for k in body.keys))
    if not keys:
        raise HTTPException(status_code=400, detail="Tick at least one person to add.")
    if len(keys) > ADD_CAP:
        raise HTTPException(status_code=400, detail=f"Add at most {ADD_CAP:,} people at a time.")
    added = await store.hand_add_many(list_id, keys, _who(user))
    await _log(client, user, "Campaign List Edited",
               f"Added {added} {'person' if added == 1 else 'people'} to the list \"{row['name']}\"",
               details={"list": list_id, "added": added, "ticked": len(keys)})
    return {"added": added, "alreadyOn": len(keys) - added}


class FindIn(BaseModel):
    group: dict[str, Any] = Field(default_factory=dict)


@lists_router.post("/lists/{list_id}/find")
async def find_people(list_id: str, body: FindIn, request: Request) -> dict[str, Any]:
    """The *Add people* condition panel: one record type and its conditions,
    run once. Answers every matching key (for *Select all*) and the first
    ``FIND_SHOWN`` described to tick."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    _static_only(row, "Add people")
    cat = await _catalogue(request, settings)
    group = audience.normalise_group({**body.group, "kind": audience.GROUP_MATCH})
    if group["type"] not in audience.TYPES_BUILT:
        raise HTTPException(status_code=400, detail="Choose what to search: leads, contacts, clients, partners or funders.")
    problems = audience.condition_problems(group, audience.field_map(cat))
    if problems:
        raise HTTPException(status_code=400, detail=problems[0][:1].upper() + problems[0][1:])
    client = _api_client(settings, request)
    try:
        keys = await audience.match_keys(client, group, cat)
        if len(keys) > ADD_CAP:
            raise HTTPException(status_code=400, detail=(
                f"More than {ADD_CAP:,} records match — add a condition to narrow the search."))
        shown = await audience.describe_members(client, keys[:FIND_SHOWN], {"include": [group], "exclude": []}, cat)
    except AudienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not search")
    on = set(_member_keys(row, await store.member_rows(list_id)))
    for m in shown:
        m["onList"] = m["key"] in on
    return {"records": shown, "keys": keys, "total": len(keys), "alreadyOn": sum(1 for k in keys if k in on)}


# --- a dynamic list: Exclude (ruling 92) --------------------------------------------------

class ExcludeIn(BaseModel):
    key: str = Field(..., max_length=64)
    targetListId: Optional[str] = None
    newName: str = Field("", max_length=200)


@lists_router.post("/lists/{list_id}/exclude")
async def exclude(list_id: str, body: ExcludeIn, request: Request) -> dict[str, Any]:
    """Keep one person off a dynamic list: add them to a static exclusion list
    (an existing one, or a new one named here) and make sure this list leaves
    that list out. The dynamic list itself stays a pure search."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    _dynamic_only(row, "Exclude")
    _not_retired(row)
    key = _valid_key(body.key)
    who = _who(user)
    if body.targetListId:
        target = await _list_or_404(store, body.targetListId)
        if target["kind"] != KIND_STATIC:
            raise HTTPException(status_code=400, detail="Choose a static list to add the person to.")
        if target["status"] == STATUS_RETIRED:
            raise HTTPException(status_code=400, detail=f"The list \"{target['name']}\" is retired — choose an active one.")
        created = False
    else:
        name = body.newName.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Choose a static list, or name a new one.")
        target = await store.create_list(name=name, notes=f"People kept off \"{row['name']}\".", kind=KIND_STATIC,
                                         recipe=audience.empty_recipe(), actor=who)
        created = True
    await store.hand_add_many(target["id"], [key], who)
    recipe = audience.normalise_recipe(row["recipe"])
    linked = False
    if target["id"] not in {g.get("listId") for g in recipe["exclude"] if g["kind"] == audience.GROUP_LIST}:
        recipe["exclude"].append({"kind": audience.GROUP_LIST, "listId": target["id"]})
        await store.save_list(list_id, name=row["name"], notes=row.get("notes") or "", kind=row["kind"],
                              recipe=recipe, actor=who)
        linked = True
    await store.drop_member(list_id, key)
    await _log(client, user, "Campaign List Edited",
               f"{key} kept off the list \"{row['name']}\" by adding them to \"{target['name']}\""
               + (", which it now leaves out" if linked else ""),
               details={"list": list_id, "key": key, "exclusionList": target["id"], "created": created,
                        "linked": linked})
    return {"exclusionList": {"id": target["id"], "name": target["name"]}, "created": created, "linked": linked}


# --- copy, used by ------------------------------------------------------------------------

class CopyIn(BaseModel):
    name: str = Field("", max_length=200)


@lists_router.post("/lists/{list_id}/copy")
async def copy_list(list_id: str, body: CopyIn, request: Request) -> dict[str, Any]:
    """*Copy current members to a new static list* (ruling 93). A dynamic list
    is run for it; the campaigns stay on the original."""
    user, client = _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the new static list a name.")
    cat = await _catalogue(request, settings)
    try:
        new, total = await audience.copy_to_static(_api_client(settings, request), store, row, cat,
                                                   name=name, actor=_who(user))
    except AudienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not copy the list")
    await _log(client, user, "Campaign List Created",
               f"Copied the {total} members of \"{row['name']}\" to the new static list \"{name}\"",
               details={"list": new["id"], "from": list_id, "members": total})
    return {"list": _public(new, members=total), "members": total}


@lists_router.get("/lists/{list_id}/used-by")
async def used_by(list_id: str, request: Request) -> dict[str, Any]:
    """Each campaign that names the list, with its date and reach (ruling 98)."""
    _user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    await _list_or_404(store, list_id)
    using = await store.campaigns_using(list_id)
    ids = [u["campaign_id"] for u in using]
    found: dict[str, dict[str, Any]] = {}
    if ids:
        try:
            page = await client.list(cfg.CAMPAIGN, select="id,name,campaignKind,campaignStatus,pieceCount,"
                                                          "startDate,signedOffAt",
                                     max_size=200, where=[{"type": "in", "attribute": "id", "value": ids}])
            found = {r["id"]: r for r in page.get("list", [])}
        except EspoError as exc:
            log.warning("lists: campaigns using %s unreadable: %s", list_id, exc)
    out = []
    for u in using:
        c = found.get(u["campaign_id"]) or {}
        build = u.get("build") or {}
        out.append({
            "campaignId": u["campaign_id"], "name": c.get("name") or "(not readable)",
            "kind": c.get("campaignKind") or "", "status": c.get("campaignStatus") or "",
            "date": c.get("startDate") or c.get("signedOffAt") or _iso(u.get("built_at")) or _iso(u.get("set_at")),
            "reach": build.get("reached") if build else c.get("pieceCount"),
            "builtVersion": u.get("built_version"), "builtAt": _iso(u.get("built_at")),
        })
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return {"usedBy": out}


# --- retire, reactivate, delete -------------------------------------------------------------

@lists_router.post("/lists/{list_id}/retire")
async def retire(list_id: str, request: Request) -> dict[str, Any]:
    return await _set_status(list_id, request, STATUS_RETIRED)


@lists_router.post("/lists/{list_id}/reactivate")
async def reactivate(list_id: str, request: Request) -> dict[str, Any]:
    return await _set_status(list_id, request, STATUS_ACTIVE)


async def _set_status(list_id: str, request: Request, status: str) -> dict[str, Any]:
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    updated = await store.set_list_status(list_id, status, _who(user))
    await _log(client, user, "Campaign List Retired" if status == STATUS_RETIRED else "Campaign List Reactivated",
               f"{'Retired' if status == STATUS_RETIRED else 'Reactivated'} the list \"{row['name']}\"",
               category=CAT_STATUS, details={"list": list_id})
    return {"list": _public(updated)}


@lists_router.delete("/lists/{list_id}")
async def delete_list(list_id: str, request: Request) -> dict[str, Any]:
    """Only a list no campaign has ever used and no other list names; one in
    use is retired (ruling 64)."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if await store.campaigns_using(list_id):
        raise HTTPException(status_code=400,
                            detail="A campaign uses this list, so it cannot be deleted — retire it instead.")
    for other in await store.all_lists():
        if other["id"] != list_id and list_id in audience.referenced_lists(audience.normalise_recipe(other["recipe"])):
            raise HTTPException(status_code=400, detail=(
                f"The list \"{other['name']}\" uses this list in a group — take it out there first, "
                "or retire this list instead."))
    await store.delete_list(list_id)
    await _log(client, user, "Campaign List Deleted", f"Deleted the unused list \"{row['name']}\"",
               details={"list": list_id})
    return {"ok": True}


# --- the copy in Constant Contact (§ 7e.9, ruling 95) -----------------------------------

def _require_sync(settings: Settings) -> None:
    if not settings.campaign_list_sync:
        raise HTTPException(status_code=404, detail=(
            "Copies in Constant Contact are switched off (Campaign list copies at /setup)."))


def _refuse_copy_name(settings: Settings, name: str) -> None:
    if name.strip().casefold() == (settings.mailing_list_name or "").strip().casefold():
        raise HTTPException(status_code=400, detail=(
            f"\"{name}\" is the name of the standing mailing list at Constant Contact — a list with "
            "its copy on needs a name of its own."))


async def _refuse_twin(store, name: str, list_id: str) -> None:
    for other in await store.all_lists():
        if (other["id"] != list_id and other.get("cc_sync")
                and other["name"].strip().casefold() == name.strip().casefold()):
            raise HTTPException(status_code=400, detail=(
                f"The list \"{other['name']}\" already keeps a copy under that name — two copies "
                "cannot share a name at Constant Contact. Rename one of them."))


class CopyOnIn(BaseModel):
    on: bool


@lists_router.put("/lists/{list_id}/cc-copy")
async def set_copy(list_id: str, body: CopyOnIn, request: Request) -> dict[str, Any]:
    """The *Keep a copy in Constant Contact* tick. Unticking stops the sync and
    keeps the copy; the next mailing pass, or *Sync now*, makes or updates it."""
    user, client = _actor(request)
    settings = get_settings()
    _require_lists(settings)
    _require_sync(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if body.on:
        _not_retired(row)
        _refuse_copy_name(settings, row["name"])
        await _refuse_twin(store, row["name"], list_id)
    updated = await store.set_cc_sync(list_id, body.on, _who(user))
    await _log(client, user, "Campaign List Copy " + ("On" if body.on else "Off"),
               (f"The list \"{row['name']}\" now keeps a copy in Constant Contact" if body.on else
                f"The list \"{row['name']}\" no longer keeps a copy in Constant Contact (the copy is kept)"),
               details={"list": list_id})
    return {"list": _public(updated)}


async def run_sync_now(settings: Settings, request: Request, store, row: dict[str, Any]):
    """One list's sync from a web request, bounded in time. Raises 400/504
    with the reason in words."""
    if not row.get("cc_sync"):
        raise HTTPException(status_code=400, detail=(
            f"The list \"{row['name']}\" keeps no copy in Constant Contact — tick Keep a copy in "
            "Constant Contact first."))
    _not_retired(row)
    try:
        result = await asyncio.wait_for(
            list_sync.sync_now(settings, row, campaign_store=store, crm=_api_client(settings, request)),
            timeout=list_sync.SYNC_NOW_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=(
            "The sync is taking longer than a page can wait. What it finished is kept, and the next "
            "mailing pass completes the rest — look again in a few minutes."))
    if not result.ok:
        raise HTTPException(status_code=400, detail=f"The copy could not be synced: {result.error}")
    return result


@lists_router.post("/lists/{list_id}/sync-now")
async def sync_now(list_id: str, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    _require_lists(settings)
    _require_sync(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    result = await run_sync_now(settings, request, store, row)
    summary = result.summary
    await _log(client, user, "Campaign List Synced",
               (f"Synced the copy of \"{row['name']}\" in Constant Contact: {summary.get('audience', 0)} on it, "
                f"{summary.get('added', 0)} added, {summary.get('removed', 0)} removed"),
               details={"list": list_id, "summary": summary})
    return {"list": _public(await store.get_list(list_id)), "summary": summary}


# --- a campaign's list ----------------------------------------------------------------

class AudienceIn(BaseModel):
    listId: Optional[str] = None
    includeEveryContact: bool = False


@lists_router.get("/campaigns/{campaign_id}/audience")
async def get_audience(campaign_id: str, request: Request) -> dict[str, Any]:
    _user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    await _campaign_or_404(request, client, campaign_id)
    chosen = await store.get_campaign_audience(campaign_id)
    if not chosen:
        return {"audience": None}
    row = await store.get_list(chosen["list_id"])
    return {"audience": {
        "listId": chosen["list_id"], "listName": (row or {}).get("name") or "(deleted)",
        "listKind": (row or {}).get("kind"), "listVersion": (row or {}).get("version"),
        "listStatus": (row or {}).get("status"),
        "includeEveryContact": bool(chosen.get("include_every_contact")),
        "builtVersion": chosen.get("built_version"),
        "builtAt": chosen["built_at"].isoformat() if chosen.get("built_at") else None,
        "build": chosen.get("build") or None,
    }}


@lists_router.put("/campaigns/{campaign_id}/audience")
async def set_audience(campaign_id: str, body: AudienceIn, request: Request) -> dict[str, Any]:
    """Choose the list a campaign sends to, or clear it (the kind's own rule
    then applies). Only before sign-off."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    campaign = await _campaign_or_404(request, client, campaign_id)
    if campaign.get("campaignKind") not in (cfg.KIND_POSTCARD, cfg.KIND_EMAIL, cfg.KIND_SMS, cfg.KIND_CALL):
        raise HTTPException(status_code=400, detail="This kind of campaign does not send to a list.")
    if (campaign.get("campaignStatus") or cfg.STATUS_DRAFT) not in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING):
        raise HTTPException(status_code=400, detail="The list cannot be changed once the campaign is signed off.")
    name = ""
    if body.listId:
        row = await _list_or_404(store, body.listId)
        if row["status"] == STATUS_RETIRED:
            raise HTTPException(status_code=400, detail="That list is retired — choose an active one.")
        name = row["name"]
    await store.set_campaign_audience(campaign_id, body.listId, include_every_contact=body.includeEveryContact,
                                      actor=_who(user))
    await _log(client, user, "Campaign List Chosen",
               f"\"{campaign.get('name')}\" now sends to the list \"{name}\"" if name
               else f"\"{campaign.get('name')}\" no longer sends to a list — its kind's own rule applies",
               parent_type=cfg.CAMPAIGN, parent_id=campaign_id, details={"list": body.listId})
    return await get_audience(campaign_id, request)
