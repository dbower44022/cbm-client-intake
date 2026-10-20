"""Campaign audiences — the Lists API at ``/campaigns/api/lists`` and a
campaign's choice of list (build plan § 7c; rulings 58–68).

Behind ``CAMPAIGNS_ENABLED`` and ``CAMPAIGN_LISTS`` (both read per request,
404 while off) and the campaigns team gate. Every run is under the org-wide
API client, like every campaign selection; what a marketing user is shown of a
member is its name and the curated fields the recipe used (ruling 63). Every
change is recorded through ``record_action``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.action_log import CAT_RECORD_EDIT, CAT_STATUS, record_action
from core.config import Settings, get_settings
from core.espo import EspoError

from . import audience
from . import config as cfg
from .audience import AudienceError
from .audience_store import (
    KIND_DYNAMIC, KIND_STATIC, KINDS, MODE_EXCLUDE, MODE_INCLUDE, STATE_IN, STATE_OUT,
    STATUS_ACTIVE, STATUS_RETIRED,
)
from .router import APP_CAMPAIGNS, _actor, _api_client, _campaign_or_404, _crm_failure, _store

log = logging.getLogger("cbm_intake.campaigns.lists")

lists_router = APIRouter(prefix="/campaigns/api", tags=["campaign-lists"])

_MEMBERS_PAGE = 50


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


def _public(row: dict[str, Any], used: int = 0) -> dict[str, Any]:
    last = row.get("last_run") or {}
    return {
        "id": row["id"], "name": row["name"], "notes": row.get("notes") or "", "kind": row["kind"],
        "status": row["status"], "version": row["version"], "recipe": row["recipe"],
        "lastRunAt": row["last_run_at"].isoformat() if row.get("last_run_at") else None,
        "lastRunBy": row.get("last_run_by") or "", "lastRun": last,
        "members": last.get("total"), "usedBy": used,
        "createdBy": row.get("created_by") or "", "updatedBy": row.get("updated_by") or "",
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


async def _list_or_404(store, list_id: str) -> dict[str, Any]:
    row = await store.get_list(list_id)
    if not row:
        raise HTTPException(status_code=404, detail="List not found.")
    return row


async def _catalogue(request: Request, settings: Settings) -> dict[str, Any]:
    client = _api_client(settings, request)
    try:
        return await audience.catalogue(client, settings)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the CRM's fields")


# --- the field catalogue ------------------------------------------------------------------

@lists_router.get("/lists/catalogue")
async def list_catalogue(request: Request) -> dict[str, Any]:
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    cat = await _catalogue(request, settings)
    return {"types": cat, "actions": [{"action": a, "label": audience.ACTION_LABELS[a]} for a in audience.ACTIONS],
            "stepCap": audience.STEP_CAP}


# --- lists --------------------------------------------------------------------------------

class ListIn(BaseModel):
    name: str = Field("", max_length=200)
    notes: str = Field("", max_length=4000)
    kind: str = KIND_STATIC
    recipe: dict[str, Any] = Field(default_factory=lambda: {"steps": []})


def _validated(body: ListIn) -> tuple[str, str, str, dict[str, Any]]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the list a name.")
    if body.kind not in KINDS:
        raise HTTPException(status_code=400, detail="A list is static or dynamic.")
    return name, body.notes.strip(), body.kind, audience.normalise_recipe(body.recipe)


@lists_router.get("/lists")
async def all_lists(request: Request) -> dict[str, Any]:
    _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    used = await store.usage_counts()
    return {"lists": [_public(r, used.get(r["id"], 0)) for r in await store.all_lists()]}


@lists_router.post("/lists")
async def create_list(body: ListIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    name, notes, kind, recipe = _validated(body)
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
    cat = await _catalogue(request, settings)
    recipe = audience.normalise_recipe(row["recipe"])
    using = await store.campaigns_using(list_id)
    entries = await store.entries(list_id) if row["kind"] == KIND_DYNAMIC else []
    hand = [m for m in await store.member_rows(list_id) if m.get("source") == "hand"] \
        if row["kind"] == KIND_STATIC else []
    client = _api_client(settings, request)
    named = await audience.describe_members(client, [e["target_key"] for e in entries] +
                                            [h["target_key"] for h in hand], recipe, cat)
    names = {n["key"]: n["name"] for n in named}
    return {
        "list": _public(row, len(using)),
        "problems": audience.check_recipe(recipe, cat),
        "steps": [audience.describe_step(s, cat) for s in recipe["steps"] if s["type"] in audience.TYPES],
        "versions": [{"version": v["version"], "kind": v["kind"], "savedBy": v.get("saved_by") or "",
                      "savedAt": v["saved_at"].isoformat()} for v in await store.list_versions(list_id)],
        "usedBy": [{"campaignId": u["campaign_id"], "builtVersion": u.get("built_version"),
                    "builtAt": u["built_at"].isoformat() if u.get("built_at") else None} for u in using],
        "entries": [{"key": e["target_key"], "mode": e["mode"], "note": e.get("note") or "",
                     "name": names.get(e["target_key"], ""), "by": e.get("created_by") or "",
                     "at": e["created_at"].isoformat()} for e in entries],
        "hand": [{"key": h["target_key"], "state": h["state"], "name": names.get(h["target_key"], ""),
                  "by": h.get("added_by") or "", "at": h["added_at"].isoformat()} for h in hand],
    }


@lists_router.put("/lists/{list_id}")
async def save_list(list_id: str, body: ListIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if row["status"] == STATUS_RETIRED:
        raise HTTPException(status_code=400, detail="A retired list cannot be changed — reactivate it first.")
    name, notes, kind, recipe = _validated(body)
    saved = await store.save_list(list_id, name=name, notes=notes, kind=kind, recipe=recipe, actor=_who(user))
    if saved["version"] != row["version"]:
        await _log(client, user, "Campaign List Changed",
                   f"Changed the list \"{name}\" — now version {saved['version']} ({kind})",
                   details={"list": list_id, "version": saved["version"]})
    return {"list": _public(saved)}


class PreviewIn(BaseModel):
    recipe: dict[str, Any] = Field(default_factory=lambda: {"steps": []})
    upTo: Optional[int] = None


@lists_router.post("/lists/preview")
async def preview(body: PreviewIn, request: Request) -> dict[str, Any]:
    """A recipe's counts, step by step, without saving — the step editor's
    Preview (§ 7c.6)."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    cat = await _catalogue(request, settings)
    recipe = audience.normalise_recipe(body.recipe)
    if body.upTo:
        recipe = {"steps": recipe["steps"][: max(body.upTo, 1)]}
    try:
        result = await audience.run_recipe(_api_client(settings, request), recipe, cat)
    except AudienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not count the step")
    return {"steps": result["steps"], "total": result["total"]}


@lists_router.post("/lists/{list_id}/run")
async def run_list(list_id: str, request: Request) -> dict[str, Any]:
    """Static: run and freeze (hand ticks kept). Dynamic: run now to show who
    it holds today — a campaign build runs it again (ruling 62)."""
    user, client = _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if row["status"] == STATUS_RETIRED:
        raise HTTPException(status_code=400, detail="A retired list does not run — reactivate it first.")
    cat = await _catalogue(request, settings)
    try:
        result = await audience.run_recipe(_api_client(settings, request), audience.normalise_recipe(row["recipe"]), cat)
    except AudienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not run the list")
    hand_rows = await store.member_rows(list_id)
    if row["kind"] == KIND_STATIC:
        final = audience.apply_hand(result["keys"], hand_rows)
    else:
        final = audience.apply_entries(result["keys"], await store.entries(list_id))
    run = {"steps": result["steps"], "recipeTotal": result["total"], "total": len(final),
           "version": row["version"]}
    await store.replace_recipe_members(list_id, result["keys"], run=run, actor=_who(user))
    await _log(client, user, "Campaign List Run",
               f"Ran the {row['kind']} list \"{row['name']}\": {len(final)} members"
               + (" (frozen)" if row["kind"] == KIND_STATIC else " (as of now)"),
               details={"list": list_id, "version": row["version"], "steps": result["steps"]})
    return {"run": run}


@lists_router.get("/lists/{list_id}/members")
async def members(list_id: str, request: Request, offset: int = 0, limit: int = _MEMBERS_PAGE) -> dict[str, Any]:
    """The list's members, a page at a time: a static list's frozen membership,
    a dynamic list's last run with its standing entries."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    store = _store(request)
    row = await _list_or_404(store, list_id)
    rows = await store.member_rows(list_id)
    if row["kind"] == KIND_STATIC:
        keys = [r["target_key"] for r in rows if r.get("state") == STATE_IN]
    else:
        recipe_keys = {r["target_key"]: 0 for r in rows if r.get("source") == "recipe"}
        keys = list(audience.apply_entries(recipe_keys, await store.entries(list_id)))
    keys.sort()
    limit = max(1, min(limit, 200))
    page = keys[offset: offset + limit]
    cat = await _catalogue(request, settings)
    described = await audience.describe_members(_api_client(settings, request), page,
                                                audience.normalise_recipe(row["recipe"]), cat)
    hand = {r["target_key"]: r for r in rows if r.get("source") == "hand"}
    entries = {e["target_key"]: e for e in (await store.entries(list_id) if row["kind"] == KIND_DYNAMIC else [])}
    for m in described:
        m["hand"] = bool(hand.get(m["key"]))
        m["entry"] = (entries.get(m["key"]) or {}).get("mode")
    return {"members": described, "total": len(keys), "offset": offset, "limit": limit,
            "neverRun": row.get("last_run_at") is None}


class MarkIn(BaseModel):
    key: str = Field(..., max_length=64)
    state: str = STATE_IN
    note: str = Field("", max_length=500)


def _valid_key(key: str) -> str:
    t, _, rid = key.partition(":")
    if t not in audience.TYPES_BUILT or not rid or len(rid) > 40:
        raise HTTPException(status_code=400, detail="That is not a lead or a contact.")
    return key


@lists_router.post("/lists/{list_id}/mark")
async def mark(list_id: str, body: MarkIn, request: Request) -> dict[str, Any]:
    """A hand edit. On a static list it changes the frozen membership; on a
    dynamic list it is a standing entry, always include / always exclude,
    with who, when and an optional note (ruling 65)."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if row["status"] == STATUS_RETIRED:
        raise HTTPException(status_code=400, detail="A retired list cannot be changed — reactivate it first.")
    key = _valid_key(body.key)
    if body.state not in (STATE_IN, STATE_OUT):
        raise HTTPException(status_code=400, detail="Tick in or out.")
    if row["kind"] == KIND_STATIC:
        await store.hand_mark(list_id, key, body.state, _who(user))
        what = "added by hand to" if body.state == STATE_IN else "removed by hand from"
    else:
        mode = MODE_INCLUDE if body.state == STATE_IN else MODE_EXCLUDE
        await store.set_entry(list_id, key, mode, body.note.strip(), _who(user))
        what = "always included in" if mode == MODE_INCLUDE else "always excluded from"
    await _log(client, user, "Campaign List Edited", f"{key} {what} the list \"{row['name']}\"",
               details={"list": list_id, "key": key, "state": body.state, "note": body.note.strip()})
    return {"ok": True}


class UnmarkIn(BaseModel):
    key: str = Field(..., max_length=64)


@lists_router.post("/lists/{list_id}/unmark")
async def unmark(list_id: str, body: UnmarkIn, request: Request) -> dict[str, Any]:
    """Undo a hand edit or remove a standing entry — the recipe decides again."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    key = _valid_key(body.key)
    if row["kind"] == KIND_STATIC:
        await store.hand_clear(list_id, key)
    else:
        await store.remove_entry(list_id, key)
    await _log(client, user, "Campaign List Edited",
               f"Removed the hand edit for {key} on the list \"{row['name']}\"", details={"list": list_id, "key": key})
    return {"ok": True}


@lists_router.get("/lists/search/records")
async def search_records(request: Request, type: str = "lead", q: str = "") -> dict[str, Any]:
    """Find a lead or contact by name to tick it in by hand."""
    _actor(request)
    settings = get_settings()
    _require_lists(settings)
    if type not in audience.TYPES_BUILT:
        raise HTTPException(status_code=400, detail="Search leads or contacts.")
    q = q.strip()
    if len(q) < 2:
        return {"records": []}
    client = _api_client(settings, request)
    attrs = ["businessName", "name", "email"] if type == "lead" else ["name", "emailAddress"]
    try:
        page = await client.list(audience.TYPES[type]["entity"], select="id," + audience.NAME_FIELDS[type],
                                 max_size=20, where=[{"type": "or", "value": [
                                     {"type": "contains", "attribute": a, "value": q} for a in attrs]}])
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not search")
    return {"records": [{"key": f"{type}:{r['id']}",
                         "name": (r.get("businessName") or r.get("name") or "") if type == "lead" else r.get("name") or ""}
                        for r in page.get("list", [])]}


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
    """Only a list no campaign has ever used; one in use is retired (ruling 64)."""
    user, client = _actor(request)
    _require_lists(get_settings())
    store = _store(request)
    row = await _list_or_404(store, list_id)
    if await store.campaigns_using(list_id):
        raise HTTPException(status_code=400,
                            detail="A campaign uses this list, so it cannot be deleted — retire it instead.")
    await store.delete_list(list_id)
    await _log(client, user, "Campaign List Deleted", f"Deleted the unused list \"{row['name']}\"",
               details={"list": list_id})
    return {"ok": True}


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
