"""Who may see an event, where, and when — the ONE visibility rule (F2 + F3).

Design: ``prds/events/CBM_Events_Audience_and_Display_Design.md``. Every public
read, the public registration form, the Zoom provisioning check and the portal
calendar decide visibility here. ``tests/test_events_visibility.py`` fails if
any of them reads ``publishToWebsite`` for themselves.

The rule, in Doug's rulings (Finalization Plan F2/F3):

* **Nothing is shown unless "Show this event" is ticked** (the CRM field is
  still ``publishToWebsite``). The audience decides *where*, never *whether*.
* **Nothing is shown before its display time** (``eventReleaseDate``), on any
  page, whatever its audience. Empty means "as soon as it is ticked".
* **Public** events show on the public pages and the portal. **Internal**
  events show on the portal only, to every signed-in member unless the event
  is limited to named teams — a DISPLAY filter, not confidentiality: every role
  that reads events reads all of them in the CRM itself (design D4).
* **An empty audience is the carry-over rule**: empty and ticked reads as
  Public, empty and unticked as Internal — exactly how Doug ruled existing
  events carry over, so no back-fill is needed and a CRM without the field
  behaves exactly as before. A value the code does not recognise is read as
  Internal: an unknown audience must never make an event public.

The reach (which chapters) needs no check on this chapter's own pages: the
creating chapter is always in its own reach (F3-6), and every event in this CRM
was created by this chapter. The future list shared across chapters is where a
reach check belongs.

Pure functions only — no CRM calls — so every rule here is testable directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from . import config as cfg

SURFACE_PUBLIC = "public"
SURFACE_PORTAL = "portal"


def _parse(value: Any) -> Optional[datetime]:
    # Local import: service imports this module.
    from .service import parse_crm_datetime

    return parse_crm_datetime(value) if value else None


def is_ticked(event: dict[str, Any]) -> bool:
    """"Show this event" — the one switch that decides whether anything shows."""
    return bool(event.get(cfg.SHOW_FIELD))


def effective_audience(event: dict[str, Any]) -> str:
    """Internal or Public, with the carry-over rule for an empty value."""
    value = (event.get(cfg.AUDIENCE_FIELD) or "").strip()
    if value in (cfg.AUDIENCE_INTERNAL, cfg.AUDIENCE_PUBLIC):
        return value
    if value:
        # Drifted or unknown: never public by accident.
        return cfg.AUDIENCE_INTERNAL
    return cfg.AUDIENCE_PUBLIC if is_ticked(event) else cfg.AUDIENCE_INTERNAL


def display_time(event: dict[str, Any]) -> Optional[datetime]:
    return _parse(event.get(cfg.DISPLAY_FROM_FIELD))


def display_time_passed(event: dict[str, Any], now: Optional[datetime] = None) -> bool:
    when = display_time(event)
    return when is None or when <= (now or datetime.now(timezone.utc))


def team_limit(event: dict[str, Any]) -> list[str]:
    teams = event.get(cfg.INTERNAL_TEAMS_FIELD) or []
    return [t for t in teams if isinstance(t, str) and t.strip()]


def is_shown(
    event: dict[str, Any],
    surface: str,
    *,
    now: Optional[datetime] = None,
    user: Optional[dict[str, Any]] = None,
    ignore_cancelled: bool = False,
) -> bool:
    """May ``event`` be shown on ``surface`` (``public`` or ``portal``) now?

    ``user`` is the portal session user (``teams``, ``isAdmin``); it matters
    only for an Internal event limited to teams, and administrators pass, as
    they do every other team gate. ``ignore_cancelled`` lets the registration
    form tell a visitor "that event has been cancelled" about an event they
    could otherwise see, instead of "not found".
    """
    if not is_ticked(event):
        return False
    if event.get("status") == cfg.STATUS_CANCELLED and not ignore_cancelled:
        return False
    if not display_time_passed(event, now):
        return False
    audience = effective_audience(event)
    if surface == SURFACE_PUBLIC:
        return audience == cfg.AUDIENCE_PUBLIC
    if surface != SURFACE_PORTAL:
        return False
    if audience == cfg.AUDIENCE_PUBLIC:
        return True
    limit = team_limit(event)
    if not limit:
        return True
    user = user or {}
    if user.get("isAdmin"):
        return True
    return bool(set(user.get("teams") or []) & set(limit))


def public_where_clauses(
    fields: Iterable[str], now: Optional[datetime] = None, *, surface: str = SURFACE_PUBLIC
) -> list[dict[str, Any]]:
    """The same rule as :func:`is_shown` for the public surface, as CRM
    ``where`` clauses — so a list read does not fetch what it must not show.

    A clause is only added for a field the live CRM has: EspoCRM refuses a
    ``where`` on an attribute it does not know (HTTP 400, verified on crm-test
    2026-09-29), whereas an unknown ``select`` attribute is silently ignored.
    Callers still apply :func:`is_shown` to what comes back; the filter is the
    efficiency, the predicate is the rule.
    """
    from .service import to_crm_datetime

    present = set(fields)
    where: list[dict[str, Any]] = [
        {"type": "isTrue", "attribute": cfg.SHOW_FIELD},
        {"type": "notEquals", "attribute": "status", "value": cfg.STATUS_CANCELLED},
    ]
    # The portal shows both audiences; only the public pages filter on it.
    if surface == SURFACE_PUBLIC and cfg.AUDIENCE_FIELD in present:
        where.append({"type": "or", "value": [
            {"type": "equals", "attribute": cfg.AUDIENCE_FIELD, "value": cfg.AUDIENCE_PUBLIC},
            {"type": "isNull", "attribute": cfg.AUDIENCE_FIELD},
            {"type": "equals", "attribute": cfg.AUDIENCE_FIELD, "value": ""},
        ]})
    if cfg.DISPLAY_FROM_FIELD in present:
        moment = now or datetime.now(timezone.utc)
        where.append({"type": "or", "value": [
            {"type": "isNull", "attribute": cfg.DISPLAY_FROM_FIELD},
            {"type": "before", "attribute": cfg.DISPLAY_FROM_FIELD,
             "value": to_crm_datetime(moment)},
        ]})
    return where


def staff_state(event: dict[str, Any], now: Optional[datetime] = None) -> dict[str, str]:
    """What Event Administration's grid shows for an event.

    ``key`` is stable (for filtering and sorting); ``label`` is what staff read.
    "Appears" is the scheduled state F2 recorded: ticked, but its display time
    has not come yet.
    """
    if not is_ticked(event):
        return {"key": "hidden", "label": "Hidden"}
    if not display_time_passed(event, now):
        when = display_time(event)
        return {"key": "scheduled",
                "label": "Appears " + (when.strftime("%Y-%m-%d") if when else "")}
    if effective_audience(event) == cfg.AUDIENCE_PUBLIC:
        return {"key": "public", "label": "Public"}
    if team_limit(event):
        return {"key": "internal", "label": "Internal, limited"}
    return {"key": "internal", "label": "Internal"}


def save_warnings(event: dict[str, Any], now: Optional[datetime] = None) -> list[str]:
    """Warnings shown after a save — never blocking (F2-2, F2-5). The team
    limit's "not private" note (D4) is the field's own help text, not a warning
    repeated on every save."""
    moment = now or datetime.now(timezone.utc)
    warnings: list[str] = []
    when = display_time(event)
    start = _parse(event.get("dateStart"))
    if when and not is_ticked(event):
        warnings.append(
            "A display time is set, but “Show this event” is not ticked, "
            "so the event will not appear at that time."
        )
    if when and start and when > start and start > moment:
        warnings.append(
            "The display time is after the event starts, so nobody will see it "
            "or be able to register before it begins."
        )
    return warnings
