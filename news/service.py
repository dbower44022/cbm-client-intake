"""Chapter News in the CRM: items, receipts, images (prds/home-page-plan.md § 6).

Every read and write runs under the org-wide CRM key (decision 3 of the
phases 5 to 7 prompt, 11-20-26): members read news and write their own
receipts under it, so they need no CRM permission, and publishers write items
under it, gated by ``NEWS_PUBLISH_ALLOWED_TEAMS`` in this application, with
every publisher action recorded through ``core/action_log.py`` naming the
publisher. The CRM's own history therefore names the API user.

**Who sees what is never decided here**: ``news/rules.py`` is the one rule.

The items are the same for everyone, so they are kept for the whole process
for ``ITEMS_SECONDS`` and dropped at once when a publisher saves or withdraws
(decision 8): another web process can show a withdrawn item for up to that
long. A member's receipts are read per request.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings

from . import rules

log = logging.getLogger("cbm_intake.news")

NEWS = "CChapterNews"
RECEIPT = "CChapterNewsReceipt"
ITEM_FIELDS = ("id,name,summary,body,status,publishAt,expiresAt,importance,"
               "audienceTeams,ctaLabel,ctaUrl,createdAt,modifiedAt,createdByName,modifiedByName")
RECEIPT_FIELDS = "id,newsId,memberId,memberName,action,actedAt"
#: How long the items are kept for every member of this process.
ITEMS_SECONDS = 60
#: How long a "the CRM has no Chapter News" answer is believed.
ABSENT_SECONDS = 60
PAGE = 200            # the CRM refuses a list page over 200 (a 403)
MAX_ITEMS = 5000
TITLE_MAX = 150
SUMMARY_MAX = 500
CTA_LABEL_MAX = 60

_ATTACH_RE = re.compile(r"\?entryPoint=attachment&(?:amp;)?id=([A-Za-z0-9_-]+)")


class NewsError(ValueError):
    """A readable refusal of a publisher's input; the router answers 400."""


def key_client(settings: Settings):
    """The org-wide key's client, or None where there is no CRM."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient

    return EspoClient(settings.espo_base_url, settings.espo_api_key,
                      settings.request_timeout_seconds)


# --- feature detection ----------------------------------------------------------

_available: dict[str, Any] = {"ok": None, "at": 0.0}


async def available(client) -> bool:
    """Whether the CRM holds both record types (§ 6.4: the feature stays dark
    until they exist). A yes is kept for the process; a no is re-asked after
    ``ABSENT_SECONDS``, so the feature comes on without a restart."""
    if _available["ok"]:
        return True
    if _available["ok"] is False and time.monotonic() - _available["at"] < ABSENT_SECONDS:
        return False
    ok = True
    for entity in (NEWS, RECEIPT):
        try:
            defs = await client.metadata(f"entityDefs.{entity}.fields")
        except Exception as exc:  # noqa: BLE001 — unknown is not present
            log.warning("chapter news: could not read %s metadata: %s", entity, exc)
            defs = None
        ok = ok and isinstance(defs, dict) and bool(defs)
    _available.update(ok=ok, at=time.monotonic())
    return ok


async def audience_options(client) -> list[str]:
    """The team names ``audienceTeams`` offers (kept in step with the CRM's
    teams by scripts/migrate_chapter_news_schema.py)."""
    defs = await client.metadata(f"entityDefs.{NEWS}.fields") or {}
    field = defs.get("audienceTeams") if isinstance(defs, dict) else None
    return [o for o in (field or {}).get("options") or [] if o]


# --- the items, kept for the process ---------------------------------------------

_items: dict[str, Any] = {"at": 0.0, "task": None}


def invalidate() -> None:
    """Drop the kept items: a publisher saved or withdrew one."""
    _items.update(at=0.0, task=None)


async def _paged(client, entity: str, select: str, where: list, order_by: str,
                 limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(entity, select=select, where=where, order_by=order_by,
                                 order="desc", max_size=PAGE, offset=offset)
        page = data.get("list") or []
        rows.extend(page)
        if len(page) < PAGE or len(rows) >= limit:
            return rows
        offset += PAGE


async def all_items(client) -> list[dict[str, Any]]:
    """Every item, any status, newest first; kept ``ITEMS_SECONDS``.
    Concurrent first reads share one load; a failed load is never kept."""
    now = time.monotonic()
    task = _items["task"]
    if task is None or now - _items["at"] > ITEMS_SECONDS:
        task = asyncio.ensure_future(
            _paged(client, NEWS, ITEM_FIELDS, [], "createdAt", MAX_ITEMS))
        _items.update(at=now, task=task)
    try:
        return await asyncio.shield(task)
    except Exception:
        if _items["task"] is task:
            invalidate()
        raise


def find(items: list[dict[str, Any]], news_id: str) -> Optional[dict[str, Any]]:
    return next((i for i in items if i.get("id") == news_id), None)


# --- receipts ----------------------------------------------------------------------

async def member_receipts(client, user_id: str) -> dict[str, dict[str, Any]]:
    """The member's receipts by item id (per request, never kept)."""
    if not user_id:
        return {}
    rows = await _paged(client, RECEIPT, RECEIPT_FIELDS,
                        [{"type": "equals", "attribute": "memberId", "value": user_id}],
                        "actedAt", MAX_ITEMS)
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        nid = r.get("newsId")
        # Two receipts for one pair (a race): an acknowledgement wins.
        if nid and (nid not in out or r.get("action") == rules.ACKNOWLEDGED):
            out[nid] = r
    return out


async def item_receipts(client, news_id: str) -> list[dict[str, Any]]:
    """Every receipt on one item (the read report)."""
    return await _paged(client, RECEIPT, RECEIPT_FIELDS,
                        [{"type": "equals", "attribute": "newsId", "value": news_id}],
                        "actedAt", MAX_ITEMS)


async def record_receipt(client, item: dict[str, Any], user: dict[str, Any], action: str,
                         now: Optional[datetime] = None) -> tuple[dict[str, Any], bool]:
    """The member's receipt for the item, made if there is none.

    The pair of item and member is unique (§ 6.4): a second click finds the
    existing receipt and changes nothing. Returns (receipt, created)."""
    user_id = user.get("userId") or ""
    existing = await client.list(
        RECEIPT, select=RECEIPT_FIELDS, max_size=5,
        where=[{"type": "equals", "attribute": "newsId", "value": item["id"]},
               {"type": "equals", "attribute": "memberId", "value": user_id}])
    rows = existing.get("list") or []
    if rows:
        return rows[0], False
    when = rules.stamp(now or datetime.now(timezone.utc))
    who = user.get("name") or user.get("userName") or user_id
    created = await client.create(RECEIPT, {
        "name": f"{action}: {item.get('name') or ''} — {who}"[:255],
        "newsId": item["id"], "memberId": user_id,
        "action": action, "actedAt": when,
    })
    return {**created, "newsId": item["id"], "memberId": user_id, "action": action,
            "actedAt": when}, True


# --- members and the read report (phase 6) ----------------------------------------------

#: How long the member list (for "out of how many") is kept for the process.
MEMBERS_SECONDS = 300
_members: dict[str, Any] = {"at": 0.0, "task": None}


def _member_row(u: dict[str, Any]) -> Optional[dict[str, Any]]:
    """A CRM user as a news member, or None for an account that is not one.

    A member is an active login of type regular, or an administrator in at
    least one team: the service accounts (the CRM configuration and
    provisioning administrators, the API user) are in no team and are left
    out, as are portal users."""
    names = u.get("teamsNames") or {}
    teams = [n for n in (names.values() if isinstance(names, dict) else names) if n]
    kind = u.get("type")
    if kind not in ("regular", "admin") or (kind == "admin" and not teams):
        return None
    return {"id": u.get("id"), "name": u.get("name") or u.get("userName") or "",
            "userName": u.get("userName") or "", "teams": sorted(teams),
            "email": u.get("emailAddress") or ""}


async def members(client) -> list[dict[str, Any]]:
    """Every news member, kept ``MEMBERS_SECONDS`` for the process."""
    now = time.monotonic()
    task = _members["task"]
    if task is None or now - _members["at"] > MEMBERS_SECONDS:
        async def load() -> list[dict[str, Any]]:
            rows = await _paged(client, "User",
                                "id,name,userName,type,isActive,teamsIds,teamsNames,emailAddress",
                                [{"type": "isTrue", "attribute": "isActive"}], "userName", 5000)
            return [m for m in (_member_row(u) for u in rows) if m]
        task = asyncio.ensure_future(load())
        _members.update(at=now, task=task)
    try:
        return await asyncio.shield(task)
    except Exception:
        if _members["task"] is task:
            _members.update(at=0.0, task=None)
        raise


async def all_receipts(client) -> list[dict[str, Any]]:
    """Every receipt (the list's read counts), read per request."""
    return await _paged(client, RECEIPT, RECEIPT_FIELDS, [], "actedAt", 50000)


def read_count(item: dict[str, Any], audience: list[dict[str, Any]],
               receipts: list[dict[str, Any]]) -> dict[str, int]:
    """How many of the item's audience have read it, out of how many."""
    ids = {m["id"] for m in audience}
    read = {r.get("memberId") for r in receipts
            if r.get("newsId") == item.get("id") and r.get("memberId") in ids}
    return {"read": len(read), "of": len(ids)}


def report(item: dict[str, Any], audience: list[dict[str, Any]],
           receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """§ 6.2: how many of the audience have read the item, out of how many,
    and who has not; for an item to acknowledge, who acknowledged and when.
    A receipt from someone no longer in the audience is not counted."""
    by_member: dict[str, dict[str, Any]] = {}
    for r in receipts:
        mid = r.get("memberId")
        if r.get("newsId") != item.get("id") or not mid:
            continue
        if mid not in by_member or r.get("action") == rules.ACKNOWLEDGED:
            by_member[mid] = r
    read, not_read = [], []
    for m in sorted(audience, key=lambda m: m["name"].lower()):
        r = by_member.get(m["id"])
        if r:
            read.append({"name": m["name"], "action": r.get("action"), "at": r.get("actedAt")})
        else:
            not_read.append({"name": m["name"]})
    return {
        "of": len(audience), "read": len(read),
        "mustAcknowledge": rules.must_acknowledge(item),
        "acknowledged": [x for x in read if x["action"] == rules.ACKNOWLEDGED],
        "dismissed": [x for x in read if x["action"] != rules.ACKNOWLEDGED],
        "notRead": not_read,
    }


# --- what a member is shown ----------------------------------------------------------

def image_ids(body: Any) -> set[str]:
    """The inline images an item's body references."""
    return set(_ATTACH_RE.findall(str(body or "")))


def member_body(item: dict[str, Any]) -> str:
    """The body as a member's browser may show it: made safe (no scripts,
    handlers or javascript: links) and each inline image pointed at the
    member image proxy, which the browser can reach and the CRM is not."""
    from core.email_clean import sanitize_original_html

    html = sanitize_original_html(str(item.get("body") or ""))
    base = f"/api/portal/home/news/{item['id']}/images/"
    return _ATTACH_RE.sub(lambda m: base + m.group(1), html)


def member_view(item: dict[str, Any], state: str = "Unread") -> dict[str, Any]:
    cta = None
    if item.get("ctaLabel") and item.get("ctaUrl"):
        cta = {"label": item["ctaLabel"], "url": item["ctaUrl"]}
    return {
        "id": item["id"],
        "title": item.get("name") or "",
        "summary": item.get("summary") or "",
        "body": member_body(item),
        "importance": item.get("importance") or rules.NORMAL,
        "publishAt": item.get("publishAt"),
        "expiresAt": item.get("expiresAt"),
        "cta": cta,
        "state": state,
    }


# --- what a publisher writes -----------------------------------------------------------

def _url_ok(url: str) -> bool:
    return url.startswith(("https://", "http://", "/")) and not url.startswith("//")


def clean_item(data: dict[str, Any], teams: list[str], base_url: str = "") -> dict[str, Any]:
    """A publisher's item, checked: the fields the CRM is sent, or a
    :class:`NewsError` naming what is wrong. The body is kept as written
    (the editor sanitizes it); members get it through ``member_body``."""
    title = str(data.get("title") or "").strip()
    if not title:
        raise NewsError("Give the item a title.")
    if len(title) > TITLE_MAX:
        raise NewsError(f"The title is longer than {TITLE_MAX} characters.")
    summary = str(data.get("summary") or "").strip()
    if len(summary) > SUMMARY_MAX:
        raise NewsError(f"The summary is longer than {SUMMARY_MAX} characters.")
    importance = data.get("importance") or rules.NORMAL
    if importance not in rules.IMPORTANCES:
        raise NewsError("Choose Normal, Pinned or Must acknowledge.")
    status = data.get("status") or rules.DRAFT
    if status not in (rules.DRAFT, rules.PUBLISHED):
        raise NewsError("An item is saved as a draft or published; withdraw it with Withdraw.")
    audience = [t for t in (data.get("audienceTeams") or []) if isinstance(t, str)]
    unknown = [t for t in audience if t not in teams]
    if unknown:
        raise NewsError(f"Not a team the CRM knows: {', '.join(unknown)}.")
    publish_at = rules.parse(data.get("publishAt"))
    expires_at = rules.parse(data.get("expiresAt"))
    if status == rules.PUBLISHED and publish_at is None:
        publish_at = datetime.now(timezone.utc).replace(microsecond=0)
    if publish_at and expires_at and expires_at <= publish_at:
        raise NewsError("The expiry time must be after the publish time.")
    label = str(data.get("ctaLabel") or "").strip()
    url = str(data.get("ctaUrl") or "").strip()
    if bool(label) != bool(url):
        raise NewsError("A button needs both its words and its address.")
    if len(label) > CTA_LABEL_MAX:
        raise NewsError(f"The button's words are longer than {CTA_LABEL_MAX} characters.")
    if url and not _url_ok(url):
        raise NewsError("The button's address must start with https://, http:// or /.")
    if url.startswith("/"):
        # The CRM's address field takes only a full address (it refused
        # "/mentorsessions/" with HTTP 400, 11-20-26): an address on this
        # application is stored in full, from APP_BASE_URL.
        root = (base_url or "").strip().rstrip("/")
        if not root:
            raise NewsError("Give the button's full address, starting with https://.")
        url = root + url
    return {
        "name": title,
        "summary": summary or None,
        "body": str(data.get("body") or "") or None,
        "status": status,
        "importance": importance,
        "audienceTeams": audience,
        "publishAt": rules.stamp(publish_at) if publish_at else None,
        "expiresAt": rules.stamp(expires_at) if expires_at else None,
        "ctaLabel": label or None,
        "ctaUrl": url or None,
    }


async def save_item(client, news_id: Optional[str], fields: dict[str, Any]) -> dict[str, Any]:
    """Create (no id) or update an item; the kept items are dropped."""
    try:
        if news_id:
            await client.update(NEWS, news_id, fields)
            saved = await client.get(NEWS, news_id)
        else:
            saved = await client.create(NEWS, fields)
            saved = await client.get(NEWS, saved["id"])
    finally:
        invalidate()
    return saved


async def withdraw(client, news_id: str) -> dict[str, Any]:
    try:
        await client.update(NEWS, news_id, {"status": rules.WITHDRAWN})
        return await client.get(NEWS, news_id)
    finally:
        invalidate()
