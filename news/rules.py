"""Who may see a Chapter News item, and in what order — the one rule.

prds/home-page-plan.md § 6.1 and § 6.3. Every surface asks this module (the
News section, past news, an item's images, a dismiss or an acknowledge, the
read report, the weekly digest), as ``events/visibility.py`` is for events;
nothing re-filters news anywhere else.

- **Seen at all** (``may_see``): the item is Published, its publish time has
  come, and the member is in its audience. An empty audience is every
  member. Being an administrator does not widen an audience: a member outside
  it never sees the item, anywhere (§ 6.1). The publisher sees every item on
  the Chapter News page, which is not a member surface.
- **Live** (``is_live``): seen, and not expired. Only live items are on the
  home page and in the digest; past news shows every item the member may
  see, expired ones included.
- **Unread**: live, with no receipt from the member. A receipt is a dismiss or
  an acknowledge (§ 6.3: being shown is not recorded).
- **Order** (§ 6.1): items to acknowledge first, then pinned, then the rest;
  newest first within each.

A member who joins a team later sees that team's items while they have not
expired: the rule reads the member's teams now, never at publish time.
Stamps are the CRM's, UTC with no offset ("YYYY-MM-DD HH:MM:SS").
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

DRAFT = "Draft"
PUBLISHED = "Published"
WITHDRAWN = "Withdrawn"
STATUSES = (DRAFT, PUBLISHED, WITHDRAWN)

NORMAL = "Normal"
PINNED = "Pinned"
ACKNOWLEDGE = "Must acknowledge"
IMPORTANCES = (NORMAL, PINNED, ACKNOWLEDGE)

DISMISSED = "Dismissed"
ACKNOWLEDGED = "Acknowledged"

_RANK = {ACKNOWLEDGE: 0, PINNED: 1, NORMAL: 2}


def parse(stamp: Any) -> Optional[datetime]:
    """A CRM stamp as an aware UTC datetime; None when empty or unreadable."""
    if not stamp:
        return None
    text = str(stamp).strip().replace("T", " ")
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def audience(item: dict[str, Any]) -> list[str]:
    teams = item.get("audienceTeams") or []
    return [t for t in teams if isinstance(t, str) and t.strip()]


def in_audience(item: dict[str, Any], user: dict[str, Any]) -> bool:
    teams = audience(item)
    return not teams or bool(set(user.get("teams") or []) & set(teams))


def published(item: dict[str, Any], now: datetime) -> bool:
    if item.get("status") != PUBLISHED:
        return False
    at = parse(item.get("publishAt"))
    return at is None or at <= now


def expired(item: dict[str, Any], now: datetime) -> bool:
    at = parse(item.get("expiresAt"))
    return at is not None and at <= now


def may_see(item: dict[str, Any], user: dict[str, Any], now: datetime) -> bool:
    return published(item, now) and in_audience(item, user)


def is_live(item: dict[str, Any], user: dict[str, Any], now: datetime) -> bool:
    return may_see(item, user, now) and not expired(item, now)


def must_acknowledge(item: dict[str, Any]) -> bool:
    return item.get("importance") == ACKNOWLEDGE


def _newest(item: dict[str, Any]) -> str:
    return str(item.get("publishAt") or item.get("createdAt") or "")


def ordered(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Acknowledge, pinned, the rest; newest first within each."""
    out = sorted(items, key=_newest, reverse=True)
    return sorted(out, key=lambda i: _RANK.get(i.get("importance"), 2))


def unread(items: Iterable[dict[str, Any]], receipts: dict[str, dict[str, Any]],
           user: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """The News section: the member's live items with no receipt, in order."""
    return ordered(i for i in items if is_live(i, user, now) and i.get("id") not in receipts)


def state(item: dict[str, Any], receipt: Optional[dict[str, Any]], now: datetime) -> str:
    """How an item stands for one member, in the words past news shows."""
    if receipt:
        return ACKNOWLEDGED if receipt.get("action") == ACKNOWLEDGED else DISMISSED
    if expired(item, now):
        return "Not acknowledged" if must_acknowledge(item) else "Expired"
    return "Unread"


def past(items: Iterable[dict[str, Any]], receipts: dict[str, dict[str, Any]],
         user: dict[str, Any], now: datetime) -> list[tuple[dict[str, Any], str]]:
    """Past news: every item the member may see, newest first, with its state."""
    seen = sorted((i for i in items if may_see(i, user, now)), key=_newest, reverse=True)
    return [(i, state(i, receipts.get(i.get("id") or ""), now)) for i in seen]


def blocks_hiding(items: Iterable[dict[str, Any]], receipts: dict[str, dict[str, Any]],
                  user: dict[str, Any], now: datetime) -> bool:
    """§ 4.3: the section cannot be hidden while an unread item to
    acknowledge is waiting."""
    return any(must_acknowledge(i) for i in unread(items, receipts, user, now))


def audience_members(item: dict[str, Any], members: Iterable[dict[str, Any]],
                     now: datetime) -> list[dict[str, Any]]:
    """The members an item reaches (the read report's "out of how many", and
    the digest's recipients): every active member in its audience. Each
    member is ``{"id", "name", "teams": [...]}``."""
    return [m for m in members if in_audience(item, m)]
