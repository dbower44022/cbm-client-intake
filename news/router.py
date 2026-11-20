"""Chapter News routes (prds/home-page-plan.md § 6; phase 5).

Two audiences, two routers:

- ``member_router`` (``/api/portal/home/news``): the home page's News
  section, past news, Dismiss and I have read this, and an item's images.
  Behind ``HOME_V2`` and ``CHAPTER_NEWS``. Every signed-in member.
- ``router`` (``/news/api``): the Chapter News page for publishers, gated per
  request to ``NEWS_PUBLISH_ALLOWED_TEAMS`` (administrators always pass).

Every CRM call runs under the org-wide key (``news/service.py``); who sees an
item is ``news/rules.py`` alone. An item a member may not see answers 404 in
the same words as an unknown id, on every member route.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from assignments.auth import clear_session, current_user, is_member
from core.config import Settings, get_settings

from . import rules, service

log = logging.getLogger("cbm_intake.news")

member_router = APIRouter(prefix="/api/portal/home/news", tags=["news"])
router = APIRouter(prefix="/news/api", tags=["news"])

APP = "Chapter News"
NOT_FOUND = "That news item was not found."


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _crm_failure(what: str, exc: Exception) -> HTTPException:
    log.warning("chapter news: %s failed: %s", what, exc)
    return HTTPException(status_code=502, detail=f"Chapter News could not {what} just now.")


# --- the member's routes ------------------------------------------------------------

async def _member(request: Request) -> tuple[dict[str, Any], Settings, Any]:
    settings = get_settings()
    if not (settings.home_v2 and settings.chapter_news):
        raise HTTPException(status_code=404, detail="Not found.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user, settings, service.key_client(settings)


async def _member_state(client, user: dict[str, Any]):
    items = await service.all_items(client)
    receipts = await service.member_receipts(client, user.get("userId") or "")
    return items, receipts


@member_router.get("")
async def news_section(request: Request) -> dict:
    """The News section (§ 6.1): the member's unread live items, in order.
    ``blocksHiding`` says an item to acknowledge waits (§ 4.3).
    ``available`` is false where the CRM has no Chapter News yet."""
    user, settings, client = await _member(request)
    if client is None or not await service.available(client):
        return {"available": False, "items": [], "blocksHiding": False}
    try:
        items, receipts = await _member_state(client, user)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read the news", exc)
    now = _now()
    unread = rules.unread(items, receipts, user, now)
    return {
        "available": True,
        "items": [service.member_view(i) for i in unread],
        "blocksHiding": rules.blocks_hiding(items, receipts, user, now),
    }


@member_router.get("/past")
async def past_news(request: Request) -> dict:
    """Past news (§ 6.1): every item the member may see, newest first,
    dismissed, acknowledged and expired ones included."""
    user, settings, client = await _member(request)
    if client is None or not await service.available(client):
        return {"available": False, "items": []}
    try:
        items, receipts = await _member_state(client, user)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read past news", exc)
    rows = rules.past(items, receipts, user, _now())
    return {"available": True, "items": [service.member_view(i, s) for i, s in rows]}


async def _seen_item(request: Request, news_id: str):
    user, settings, client = await _member(request)
    if client is None or not await service.available(client):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    try:
        items = await service.all_items(client)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read the news", exc)
    item = service.find(items, news_id)
    if item is None or not rules.may_see(item, user, _now()):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return user, client, item


async def _act(request: Request, news_id: str, action: str) -> dict:
    user, client, item = await _seen_item(request, news_id)
    if action == rules.DISMISSED and rules.must_acknowledge(item):
        raise HTTPException(status_code=400, detail=(
            "This item asks you to confirm you have read it: use I have read this."))
    if action == rules.ACKNOWLEDGED and not rules.must_acknowledge(item):
        raise HTTPException(status_code=400, detail="This item needs no acknowledgment: use Dismiss.")
    try:
        receipt, created = await service.record_receipt(client, item, user, action)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("record that just now", exc)
    return {"id": news_id, "action": receipt.get("action"), "actedAt": receipt.get("actedAt"),
            "created": created}


@member_router.post("/{news_id}/dismiss")
async def dismiss(news_id: str, request: Request) -> dict:
    return await _act(request, news_id, rules.DISMISSED)


@member_router.post("/{news_id}/acknowledge")
async def acknowledge(news_id: str, request: Request) -> dict:
    return await _act(request, news_id, rules.ACKNOWLEDGED)


@member_router.get("/{news_id}/images/{attachment_id}")
async def member_image(news_id: str, attachment_id: str, request: Request) -> Response:
    """An image in an item the member may see, and only one its body
    references: the key can read any attachment, so the item is the gate."""
    user, client, item = await _seen_item(request, news_id)
    if attachment_id not in service.image_ids(item.get("body")):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return await _image(client, attachment_id)


async def _image(client, attachment_id: str) -> Response:
    from core.inline_images import fetch_inline_image

    try:
        content, content_type = await fetch_inline_image(client, attachment_id)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read that image", exc)
    return Response(content=content, media_type=content_type or "application/octet-stream",
                    headers={"Cache-Control": "private, max-age=300"})


# --- the publisher's routes -----------------------------------------------------------

def _publisher(request: Request) -> tuple[dict[str, Any], Settings]:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    if not settings.chapter_news:
        raise HTTPException(status_code=404, detail="Chapter News is not switched on.")
    teams = settings.news_publish_allowed_teams_list
    if not is_member(user, teams):
        raise HTTPException(status_code=403, detail=(
            "Your account is not authorized to publish Chapter News "
            f"(requires the {', '.join(teams) or 'admin'} team)."))
    return user, settings


async def _publisher_client(request: Request):
    user, settings = _publisher(request)
    client = service.key_client(settings)
    if client is None:
        raise HTTPException(status_code=503, detail="The CRM is not connected on this server.")
    if not await service.available(client):
        raise HTTPException(status_code=503, detail=(
            "The CRM does not have the Chapter News record types yet "
            "(cchapternews-entities-crm-handoff.md)."))
    return user, settings, client


#: Images a publisher uploaded in this process, not yet in a saved body:
#: the editor shows them before the item is saved. id -> when.
_uploads: dict[str, float] = {}
UPLOAD_SECONDS = 24 * 3600


def _remember_upload(attachment_id: str) -> None:
    now = time.monotonic()
    for k in [k for k, at in _uploads.items() if now - at > UPLOAD_SECONDS]:
        _uploads.pop(k, None)
    _uploads[attachment_id] = now


def _listing(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item.get(k) for k in ("id", "status", "importance", "publishAt", "expiresAt",
                                     "audienceTeams", "createdAt", "modifiedAt")} | {
        "title": item.get("name") or ""}


def _full(item: dict[str, Any]) -> dict[str, Any]:
    return _listing(item) | {k: item.get(k) or "" for k in ("summary", "body", "ctaLabel", "ctaUrl")}


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    """Who is signed in, and whether the CRM holds Chapter News yet."""
    user, settings = _publisher(request)
    client = service.key_client(settings)
    built = bool(client is not None and await service.available(client))
    teams: list[str] = []
    if built:
        try:
            teams = await service.audience_options(client)
        except Exception as exc:  # noqa: BLE001
            log.warning("chapter news: audience options unreadable: %s", exc)
    return {"name": user.get("name") or user.get("userName"), "isAdmin": bool(user.get("isAdmin")),
            "built": built, "teams": teams, "importances": list(rules.IMPORTANCES)}


@router.get("/items")
async def items(request: Request) -> dict:
    """Every item, with its read count (phase 6) where it has gone out. The
    counts fail on their own: the list still comes, with ``readUnavailable``."""
    user, settings, client = await _publisher_client(request)
    try:
        rows = await service.all_items(client)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read the news", exc)
    out = [_listing(i) for i in rows]
    try:
        members = await service.members(client)
        receipts = await service.all_receipts(client)
    except Exception as exc:  # noqa: BLE001 — the counts only
        log.warning("chapter news: read counts unavailable: %s", exc)
        return {"items": out, "readUnavailable": True}
    for row, it in zip(out, rows):
        if it.get("status") != rules.DRAFT:
            row["readCount"] = service.read_count(it, rules.audience_members(it, members, _now()),
                                                  receipts)
    return {"items": out, "readUnavailable": False}


@router.get("/items/{news_id}/report")
async def read_report(news_id: str, request: Request) -> dict:
    """The read report for one item (§ 6.2; phase 6)."""
    user, settings, client = await _publisher_client(request)
    try:
        found = service.find(await service.all_items(client), news_id)
        if found is None:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        members = await service.members(client)
        receipts = await service.item_receipts(client, news_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read who has read it", exc)
    return service.report(found, rules.audience_members(found, members, _now()), receipts)


@router.get("/items/{news_id}")
async def item(news_id: str, request: Request) -> dict:
    user, settings, client = await _publisher_client(request)
    try:
        found = service.find(await service.all_items(client), news_id)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read the news", exc)
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return _full(found)


class ItemIn(BaseModel):
    title: str = ""
    summary: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    importance: Optional[str] = None
    audienceTeams: list[str] = []
    publishAt: Optional[str] = None
    expiresAt: Optional[str] = None
    ctaLabel: Optional[str] = None
    ctaUrl: Optional[str] = None


async def _log(user: dict[str, Any], action: str, item: dict[str, Any], summary: str,
               details: Optional[dict[str, Any]] = None) -> None:
    from core.action_log import log_action

    await log_action(
        app=APP, category="Chapter News", action=action,
        parent_type=service.NEWS, parent_id=item.get("id") or "",
        summary=summary, actor_id=user.get("userId") or "",
        actor_name=user.get("name") or user.get("userName") or "",
        details=details)


def _changed(before: Optional[dict[str, Any]], after: dict[str, Any]) -> dict[str, Any]:
    """Old and new values of what a save changed (the History convention);
    the body is named, never copied."""
    fields = {}
    for k, v in after.items():
        old = (before or {}).get(k)
        if (old or None) != (v or None):
            fields[k] = {"old": None if k == "body" else old,
                         "new": "(changed)" if k == "body" else v}
    return {"fields": fields}


async def _save(request: Request, news_id: Optional[str], body: ItemIn) -> dict:
    user, settings, client = await _publisher_client(request)
    try:
        before = service.find(await service.all_items(client), news_id) if news_id else None
        if news_id and before is None:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        teams = await service.audience_options(client)
        fields = service.clean_item(body.model_dump(), teams)
    except service.NewsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read the news", exc)
    try:
        saved = await service.save_item(client, news_id, fields)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("save the item", exc)
    was = (before or {}).get("status")
    if fields["status"] == rules.PUBLISHED and was != rules.PUBLISHED:
        action, verb = "Published", "published"
    elif news_id:
        action, verb = "Edited", "edited"
    else:
        action, verb = "Saved draft", "saved a draft of"
    await _log(user, action, saved, f"{user.get('name') or user.get('userName')} {verb} "
               f"Chapter News \"{fields['name']}\"", _changed(before, fields))
    return _full(saved)


@router.post("/items")
async def create_item(body: ItemIn, request: Request) -> dict:
    return await _save(request, None, body)


@router.put("/items/{news_id}")
async def update_item(news_id: str, body: ItemIn, request: Request) -> dict:
    return await _save(request, news_id, body)


@router.post("/items/{news_id}/withdraw")
async def withdraw_item(news_id: str, request: Request) -> dict:
    """§ 6.2: a withdrawn item disappears for every member, past news
    included (the rule shows Published items only)."""
    user, settings, client = await _publisher_client(request)
    try:
        before = service.find(await service.all_items(client), news_id)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("read the news", exc)
    if before is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    try:
        saved = await service.withdraw(client, news_id)
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("withdraw the item", exc)
    await _log(user, "Withdrew", saved,
               f"{user.get('name') or user.get('userName')} withdrew Chapter News "
               f"\"{before.get('name')}\"",
               {"fields": {"status": {"old": before.get("status"), "new": rules.WITHDRAWN}}})
    return _full(saved)


class ImageIn(BaseModel):
    filename: str = "pasted-image"
    contentType: str
    dataBase64: str


@router.post("/inlineimages")
async def upload_image(body: ImageIn, request: Request) -> dict:
    """An image pasted, dropped or picked into the body: an Inline Attachment
    on ``CChapterNews.body``, bound to the item when it is saved."""
    from core.inline_images import InlineImageError, upload_inline_image

    user, settings, client = await _publisher_client(request)
    try:
        result = await upload_inline_image(
            client, filename=body.filename, content_type=body.contentType,
            data_base64=body.dataBase64, related_type=service.NEWS, field="body",
            allowed_fields={"body"})
    except InlineImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise await _crm_failure("store that image", exc)
    _remember_upload(result["id"])
    return result


@router.get("/attachments/{attachment_id}")
async def publisher_image(attachment_id: str, request: Request) -> Response:
    """An image in the editor: one a saved item's body references, or one
    uploaded here and not saved yet. Nothing else is read under the key."""
    user, settings, client = await _publisher_client(request)
    known = attachment_id in _uploads
    if not known:
        try:
            known = any(attachment_id in service.image_ids(i.get("body"))
                        for i in await service.all_items(client))
        except Exception as exc:  # noqa: BLE001
            raise await _crm_failure("read the news", exc)
    if not known:
        raise HTTPException(status_code=404, detail="That image was not found.")
    return await _image(client, attachment_id)
