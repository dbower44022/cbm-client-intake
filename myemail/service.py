"""My Email inbox assembly — every conversation on the records this manager
handles, across all three session-tool domains, in one list.

Scope mirrors the Gmail sync's own semantics: the records reached through the
manager's ``CMentorProfile`` reverse links (owned + co-mentored, the same links
the session tools' grids use), NOT "every conversation the CRM ACL can read" —
the manager roles read CConversation at *all*, so ACL alone would show other
people's mail. All CRM reads run as the signed-in user.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from comms import crm as comms_crm
from comms import service as comms_service
from sessions.config import DOMAINS, DomainConfig
from sessions.service import MENTOR_PROFILE, resolve_manager_profile

log = logging.getLogger("cbm_intake.myemail")

_PAGE = 200
# Bounds: an inbox is "recent mail", not an archive. More records than this on
# one manager would be a data problem; conversations cap keeps the page fast.
MAX_RECORDS = 80
MAX_CONVERSATIONS = 100


def _domain_allowed(cfg: DomainConfig, user: dict[str, Any], settings: Any) -> bool:
    from assignments.auth import is_member

    return is_member(user, getattr(settings, cfg.allowed_teams_attr))


async def _owned_records(
    cfg: DomainConfig, client: Any, profile_id: str
) -> list[dict[str, Any]]:
    """The manager's records in one domain — reverse links off their profile
    (owned + co-mentored), status-filtered like the domain's own grid. A
    forbidden read (no role in this domain despite team membership) just
    yields nothing."""
    links = [cfg.manager_owned_link]
    if cfg.manager_comentor_link:
        links.append(cfg.manager_comentor_link)
    select = "name" + (f",{cfg.status_attr}" if cfg.status_attr else "")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in links:
        try:
            data = await client.list_related(
                MENTOR_PROFILE, profile_id, link, select=select, max_size=_PAGE
            )
        except Exception as exc:  # noqa: BLE001 — domain simply contributes nothing
            log.debug("myemail: %s/%s read failed: %s", cfg.slug, link, exc)
            continue
        for r in data.get("list", []):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            rows.append(r)
    if cfg.status_attr and cfg.status_values:
        rows = [r for r in rows if r.get(cfg.status_attr) in cfg.status_values]
    return rows


async def build_inbox(
    settings: Any, client: Any, store: Any, user: dict[str, Any]
) -> dict[str, Any]:
    """``{conversations: [...], profileFound: bool}`` — newest first, each row
    carrying the record(s) it belongs to plus unread/awaitingReply flags."""
    profile_id = await resolve_manager_profile(client, user["userId"])
    if not profile_id:
        return {"conversations": [], "profileFound": False}

    # (cfg, record) pairs across the domains this user's teams allow.
    records: list[tuple[DomainConfig, dict[str, Any]]] = []
    for cfg in DOMAINS.values():
        if not _domain_allowed(cfg, user, settings) and not user.get("isAdmin"):
            continue
        for r in await _owned_records(cfg, client, profile_id):
            records.append((cfg, r))
    records = records[:MAX_RECORDS]

    async def _convs(cfg: DomainConfig, rec: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            rows = await comms_service.list_conversations(
                client, cfg.parent_entity, rec["id"]
            )
        except Exception as exc:  # noqa: BLE001 — one record never sinks the inbox
            log.warning("myemail: conversations read failed for %s/%s: %s",
                        cfg.parent_entity, rec["id"], exc)
            return []
        for row in rows:
            row["_record"] = {
                "entity": cfg.parent_entity,
                "id": rec["id"],
                "name": rec.get("name") or "",
                "slug": cfg.slug,
            }
        return rows

    results = await asyncio.gather(*(_convs(cfg, rec) for cfg, rec in records))

    # Merge: a conversation linked to several records keeps them all.
    by_id: dict[str, dict[str, Any]] = {}
    for rows in results:
        for row in rows:
            rec = row.pop("_record")
            existing = by_id.get(row["id"])
            if existing is None:
                row["records"] = [rec]
                by_id[row["id"]] = row
            elif all(r["id"] != rec["id"] for r in existing["records"]):
                existing["records"].append(rec)
    conversations = sorted(
        by_id.values(), key=lambda r: r.get("lastMessageAt") or "", reverse=True
    )[:MAX_CONVERSATIONS]

    await comms_service.enrich_conversation_rows(
        client, store, user["userName"], conversations
    )
    return {"conversations": conversations, "profileFound": True}


async def conversation_records(
    client: Any, conversation_id: str
) -> list[dict[str, Any]]:
    """The records a conversation is linked to (for "Open in record" links),
    read via the three parent links. Best-effort — a forbidden link read just
    drops that domain's chip."""
    slug_by_entity = {cfg.parent_entity: cfg.slug for cfg in DOMAINS.values()}
    out: list[dict[str, Any]] = []
    for entity, link in comms_crm.PARENT_LINKS.items():
        try:
            data = await client.list_related(
                comms_crm.CONVERSATION, conversation_id, link,
                select="name", max_size=20,
            )
        except Exception:  # noqa: BLE001
            continue
        for r in data.get("list", []):
            out.append({
                "entity": entity,
                "id": r["id"],
                "name": r.get("name") or "",
                "slug": slug_by_entity.get(entity, ""),
            })
    return out
