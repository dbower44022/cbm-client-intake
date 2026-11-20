"""The weekly Chapter News digest (prds/home-page-plan.md § 6.3 and § 8, phase 7).

Once a week, at ``NEWS_DIGEST_WEEKDAY`` and ``NEWS_DIGEST_HOUR`` in the
chapter's own time zone (``events.config.PUBLIC_TIMEZONE``; decision 10 of
the phases 5 to 7 prompt, default Monday 08:00), the worker emails each
member with unread news one list, from the shared mailbox (``OPS_MAILBOX``):

- **What**: the member's unread live items, exactly the home page's News
  section (``news/rules.unread``, the one rule), items to acknowledge first.
  An item to acknowledge is always in it while it waits; an expired one has
  stopped prompting and is not.
- **Who**: every news member (``news.service.members``) with at least one
  unread item and an address, who has not opted out (the preference
  ``news.digest`` = ``{"weekly": false}``, set from the News section).
  Nothing is sent to a member with nothing unread.
- **Training addresses are never mailed** (decision 11): an address on the
  sandbox domain is counted and logged, never sent and never an error.
- **Once a week**: each member's last sent week is recorded in the
  application database (the per-user store, key ``news.digest.sent``, which
  the preferences API never exposes), so a worker restart, or a second run in
  the same week, sends nothing twice.

``send_test`` is the Chapter News page's "Send me a test digest": the
publisher's own digest, at once, to the publisher's own address.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.branding import abbr
from core.config import Settings

from . import rules, service

log = logging.getLogger("cbm_intake.news.digest")

OPT_OUT_KEY = "news.digest"
SENT_KEY = "news.digest.sent"
#: A worker that starts this long after the weekly hour still sends that
#: week's digest (the record stops a second send).
CATCH_UP_HOURS = 12
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def enabled(settings: Settings) -> bool:
    """The digest needs its switch, Chapter News, the shared mailbox and the
    database that keeps the once-a-week record."""
    return bool(settings.news_digest and settings.chapter_news and
                str(settings.ops_mailbox or "").strip() and settings.database_url)


def _tz():
    from zoneinfo import ZoneInfo

    from events.config import PUBLIC_TIMEZONE

    return ZoneInfo(PUBLIC_TIMEZONE)


def week_key(when: datetime) -> str:
    """The chapter's ISO week of ``when``, e.g. ``2026-W47``."""
    year, week, _ = when.astimezone(_tz()).isocalendar()
    return f"{year}-W{week:02d}"


def _slot(settings: Settings, local: datetime) -> datetime:
    """This week's send time, as a local datetime, for the week holding ``local``."""
    weekday = max(0, min(6, int(settings.news_digest_weekday)))
    hour = max(0, min(23, int(settings.news_digest_hour)))
    monday = local - timedelta(days=local.weekday())
    return (monday + timedelta(days=weekday)).replace(hour=hour, minute=0, second=0, microsecond=0)


def next_run(settings: Settings, now: datetime) -> datetime:
    """The next UTC time the weekly run is due. A worker started within
    ``CATCH_UP_HOURS`` after this week's hour is due at once."""
    local = now.astimezone(_tz())
    slot = _slot(settings, local)
    if slot <= local:
        if local - slot <= timedelta(hours=CATCH_UP_HOURS):
            return now
        slot = _slot(settings, local + timedelta(days=7))
    return slot.astimezone(timezone.utc)


# --- one member's digest -----------------------------------------------------------

def render(member_name: str, items: list[dict[str, Any]], home_url: str,
           *, test: bool = False) -> tuple[str, str]:
    """(subject, HTML body) of one member's digest."""
    n = len(items)
    waiting = sum(1 for i in items if rules.must_acknowledge(i))
    subject = f"{abbr()} news: {n} unread {'item' if n == 1 else 'items'}"
    if waiting:
        subject += f", {waiting} to confirm"
    if test:
        subject = "[Test] " + subject
    esc = html.escape
    rows = []
    for it in items:
        tag = ""
        if rules.must_acknowledge(it):
            tag = ('<span style="background:#FFF0D6;color:#7A4A00;padding:1px 6px;'
                   'border-radius:4px;font-size:12px;font-weight:600">Please confirm you have read it</span> ')
        elif it.get("importance") == rules.PINNED:
            tag = ('<span style="background:#E8EEF6;color:#173B60;padding:1px 6px;'
                   'border-radius:4px;font-size:12px;font-weight:600">Pinned</span> ')
        summary = esc(it.get("summary") or "")
        rows.append(
            '<li style="margin:0 0 12px">' + tag
            + f'<strong style="color:#111827">{esc(it.get("name") or "")}</strong>'
            + (f'<br><span style="color:#4B5563">{summary}</span>' if summary else "")
            + "</li>")
    intro = ("This is a test of the weekly digest, sent at your request. "
             if test else "")
    body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#374151">'
        f"<p>Hello {esc(member_name)},</p>"
        f"<p>{intro}You have {n} unread {'item' if n == 1 else 'items'} of {esc(_org())} news:</p>"
        f'<ul style="padding-left:18px">{"".join(rows)}</ul>'
        f'<p><a href="{esc(home_url)}">Open your home page</a> to read '
        f"{'it' if n == 1 else 'them'}"
        + (" and confirm what asks you to." if waiting else ".") + "</p>"
        '<p style="color:#6B7280;font-size:12px">To stop this weekly email, untick '
        "<em>Email me a weekly digest</em> under Chapter News on your home page.</p>"
        "</div>")
    return subject, body


async def _send(settings: Settings, to: str, subject: str, body: str) -> None:
    from comms import service as comms_service

    gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
    try:
        await comms_service.send_quick_message(
            gmail=gmail, to=[to], subject=subject, body_html=body,
            sender_name=settings.sender_display_name)
    finally:
        await gmail.aclose()


def _org() -> str:
    from core.config import get_settings

    return get_settings().organization_name


def _home_url(settings: Settings) -> str:
    return (settings.app_base_url or "").rstrip("/") + "/"


async def run_weekly(settings: Settings, client, store, now: Optional[datetime] = None,
                     send=None) -> dict[str, int]:
    """One weekly run. Returns the counts it logs. Best-effort per member:
    one failure never stops the rest. ``send`` is for tests."""
    from core.sandbox_addresses import is_sandbox_address

    send = send or _send
    now = now or datetime.now(timezone.utc)
    counts = {"sent": 0, "nothingUnread": 0, "optedOut": 0, "alreadySent": 0,
              "trainingAddress": 0, "noAddress": 0, "failed": 0}
    if not enabled(settings) or store is None or client is None:
        return counts
    if not await service.available(client):
        return counts
    week = week_key(now)
    items = await service.all_items(client)
    for m in await service.members(client):
        try:
            receipts = await service.member_receipts(client, m["id"])
            unread = rules.unread(items, receipts, m, now)
            if not unread:
                counts["nothingUnread"] += 1
                continue
            pref = await store.get_user_preference(m["id"], OPT_OUT_KEY)
            if isinstance(pref, dict) and pref.get("weekly") is False:
                counts["optedOut"] += 1
                continue
            if await store.get_user_preference(m["id"], SENT_KEY) == week:
                counts["alreadySent"] += 1
                continue
            to = (m.get("email") or "").strip()
            if not to:
                counts["noAddress"] += 1
                continue
            if is_sandbox_address(to):
                counts["trainingAddress"] += 1
                log.info("news digest: %s not sent to a training address", m.get("userName"))
                continue
            subject, body = render(m["name"], unread, _home_url(settings))
            await send(settings, to, subject, body)
            await store.set_user_preference(m["id"], SENT_KEY, week)
            counts["sent"] += 1
        except Exception as exc:  # noqa: BLE001 — one member never stops the rest
            counts["failed"] += 1
            log.warning("news digest: %s failed: %s", m.get("userName"), exc)
    log.info("news digest %s: %s", week, ", ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


class DigestRefused(ValueError):
    """Why the test digest was not sent, in words for the publisher."""


async def send_test(settings: Settings, client, user: dict[str, Any], send=None) -> dict[str, Any]:
    """The publisher's own digest, sent to them at once. With nothing unread
    it lists every live item they may see, so the email is never empty."""
    from core.sandbox_addresses import is_sandbox_address

    send = send or _send
    if not str(settings.ops_mailbox or "").strip():
        raise DigestRefused("No shared mailbox is set (System Settings → Email → OPS_MAILBOX), "
                            "so there is nothing to send the digest from.")
    me = next((m for m in await service.members(client) if m["id"] == user.get("userId")), None)
    to = ((me or {}).get("email") or "").strip()
    if not to and user.get("userId"):
        # An administrator in no team is not a news member, but may publish:
        # read their own login's address.
        try:
            to = str((await client.get("User", user["userId"])).get("emailAddress") or "").strip()
        except Exception as exc:  # noqa: BLE001 — answered as "no address" below
            log.warning("news digest: could not read %s's address: %s", user.get("userName"), exc)
    if not to:
        raise DigestRefused("Your login has no email address in the CRM to send the test to.")
    if is_sandbox_address(to):
        raise DigestRefused(f"Your address {to} is a training address, which is never mailed.")
    now = datetime.now(timezone.utc)
    items = await service.all_items(client)
    member = me or {"id": user.get("userId"), "teams": user.get("teams") or []}
    receipts = await service.member_receipts(client, member["id"] or "")
    unread = rules.unread(items, receipts, member, now)
    listed = unread or rules.ordered(i for i in items if rules.is_live(i, member, now))
    if not listed:
        raise DigestRefused("There is no live news you may see, so the digest would be empty.")
    subject, body = render((me or {}).get("name") or user.get("name") or "", listed,
                           _home_url(settings), test=True)
    await send(settings, to, subject, body)
    return {"to": to, "items": len(listed), "unread": len(unread)}
