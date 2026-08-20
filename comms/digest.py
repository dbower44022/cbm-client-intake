"""Daily email digest (email-quality plan §4.2.4).

Once a day the worker emails each manager a summary of the records they handle
that have **unread** or **awaiting-reply** conversations — each a deep link to
the record page. Sent from the shared identity (``ops_mailbox`` /
``ops_mailbox_name``) to the manager's ``cbmEmail``. Nothing pending for a
manager => no email (no empty digests). Best-effort per manager: one manager's
failure never stops the rest, and the whole cycle never crashes the worker.

Runs under the worker's API-key client (the same identity the Gmail sync reads
conversations with). Unread state is per-person, so each manager's summary is
computed with THEIR login ``userName`` (the key ``conversation_seen`` uses).
"""

from __future__ import annotations

import html as _html
import logging
from typing import Any

from comms import service as comms_service
from core.config import Settings
from sessions.config import DOMAINS
from sessions.service import MENTOR_PROFILE

log = logging.getLogger("cbm_intake.comms.digest")

_PAGE = 200


def digest_enabled(settings: Settings) -> bool:
    """The digest needs the integration, a shared send identity, and the DB
    (unread state lives there)."""
    return bool(
        settings.comms_digest
        and settings.gmail_sync
        and settings.ops_mailbox
        and settings.database_url
    )


async def _managers(api_client: Any) -> list[dict[str, Any]]:
    """Every CMentorProfile with a CBM email + a linked, active login user —
    the digest recipients. Each: ``{profileId, name, cbmEmail, userName}``."""
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await api_client.list(
            MENTOR_PROFILE,
            select="id,name,cbmEmail,assignedUserId,assignedUsersIds",
            max_size=_PAGE,
            offset=offset,
        )
        rows = data.get("list", [])
        for r in rows:
            email = (r.get("cbmEmail") or "").strip()
            if not email:
                continue
            user_id = r.get("assignedUserId") or (r.get("assignedUsersIds") or [None])[0]
            if not user_id:
                continue
            try:
                user = await api_client.get("User", user_id, select="userName,isActive")
            except Exception as exc:  # noqa: BLE001 — skip an unreadable user
                log.debug("digest: user %s read failed: %s", user_id, exc)
                continue
            if not user.get("isActive", True) or not user.get("userName"):
                continue
            out.append({
                "profileId": r["id"],
                "name": r.get("name") or "",
                "cbmEmail": email,
                "userName": user["userName"],
            })
        if len(rows) < _PAGE:
            break
        offset += _PAGE
    return out


async def _manager_records(api_client: Any, profile_id: str) -> list[dict[str, Any]]:
    """The manager's records across all three domains (owned + co-mentored),
    as ``{entity, id, name, slug}`` — the same reverse-link scope My Email
    uses. Best-effort per domain."""
    from myemail.service import _owned_records  # same profile-scoped resolver

    recs: list[dict[str, Any]] = []
    for cfg in DOMAINS.values():
        for r in await _owned_records(cfg, api_client, profile_id):
            recs.append({
                "entity": cfg.parent_entity,
                "id": r["id"],
                "name": r.get("name") or "",
                "slug": cfg.slug,
            })
    return recs


def _render_digest(
    manager_name: str, items: list[dict[str, Any]], base_url: str
) -> str:
    """The digest HTML. ``items`` = records with pending mail, each
    ``{name, slug, id, unread, awaiting}``. ``base_url`` empty => plain names,
    no hyperlinks."""
    base = (base_url or "").rstrip("/")
    lines = []
    for it in items:
        label = _html.escape(it["name"] or "(unnamed record)")
        bits = []
        if it["unread"]:
            bits.append(f"{it['unread']} unread")
        if it["awaiting"]:
            bits.append("awaiting your reply")
        tag = " — " + ", ".join(bits) if bits else ""
        if base:
            url = f"{base}/{it['slug']}/record/{it['id']}"
            lines.append(
                f'<li><a href="{_html.escape(url)}" '
                f'style="color:#1a5fb4;text-decoration:none;font-weight:600">'
                f"{label}</a>{_html.escape(tag)}</li>"
            )
        else:
            lines.append(f"<li><strong>{label}</strong>{_html.escape(tag)}</li>")
    total_unread = sum(it["unread"] for it in items)
    intro = (
        f"You have {total_unread} unread "
        + ("message" if total_unread == 1 else "messages")
        + f" across {len(items)} "
        + ("record" if len(items) == 1 else "records")
        + " this morning:"
    )
    email_link = f"{base}/myemail/" if base else ""
    footer = (
        f'<p style="margin-top:16px"><a href="{_html.escape(email_link)}" '
        'style="color:#1a5fb4">Open My Email</a> to read and reply.</p>'
        if email_link else ""
    )
    return (
        '<div style="font-family:Arial,sans-serif;color:#223;line-height:1.5">'
        f"<p>Good morning{(' ' + _html.escape(manager_name.split()[0])) if manager_name else ''},</p>"
        f"<p>{_html.escape(intro)}</p>"
        f'<ul style="padding-left:20px">{"".join(lines)}</ul>'
        f"{footer}"
        '<p style="color:#889;font-size:12px;margin-top:20px">'
        "You're receiving this because you manage these records in the CBM apps."
        "</p></div>"
    )


async def run_digest_cycle(settings: Settings, api_client: Any, store: Any) -> int:
    """Send each manager their digest of records with unread/awaiting mail.
    Returns the number of digests sent. Best-effort throughout — never raises."""
    if not digest_enabled(settings):
        return 0
    try:
        managers = await _managers(api_client)
    except Exception as exc:  # noqa: BLE001
        log.warning("digest: manager enumeration failed: %s", exc)
        return 0
    sent = 0
    for m in managers:
        try:
            records = await _manager_records(api_client, m["profileId"])
            if not records:
                continue
            summary = await comms_service.record_unread_map(
                api_client, store, m["userName"],
                [(r["entity"], r["id"]) for r in records],
            )
            items = []
            for r in records:
                s = summary.get(r["id"]) or {}
                if s.get("unread") or s.get("awaiting"):
                    items.append({
                        "name": r["name"], "slug": r["slug"], "id": r["id"],
                        "unread": s.get("unread", 0), "awaiting": bool(s.get("awaiting")),
                    })
            if not items:
                continue  # no empty digests
            items.sort(key=lambda x: (-x["unread"], x["name"].lower()))
            body = _render_digest(m["name"], items, settings.app_base_url)
            n_unread = sum(i["unread"] for i in items)
            subject = (
                f"CBM: {n_unread} unread "
                + ("message" if n_unread == 1 else "messages")
                + f" across {len(items)} "
                + ("record" if len(items) == 1 else "records")
            )
            gmail = await comms_service.gmail_for_shared_mailbox(
                settings, settings.ops_mailbox
            )
            try:
                await comms_service.send_quick_message(
                    gmail=gmail, to=[m["cbmEmail"]], subject=subject,
                    body_html=body, sender_name=settings.sender_display_name,
                )
            finally:
                await gmail.aclose()
            sent += 1
        except Exception as exc:  # noqa: BLE001 — one manager never stops the rest
            log.warning("digest: send failed for %s: %s", m.get("cbmEmail"), exc)
    log.info("digest cycle complete: %d digest(s) sent", sent)
    return sent
