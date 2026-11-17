"""How an event's online part is hosted — the ONE rule for the hosting method.

Plan ``prds/events/event-hosting-plan.md`` (rulings EH1 to EH14); CRM field
``CEvent.hostedBy`` (``cevent-hosting-method-crm-handoff.md``). Four stored
values, and **code compares against the stored value, never the label**:

* ``CBM Zoom`` — shown as **Zoom Webinars**. The application creates the
  webinar and registers each person, who gets a personal join link.
* ``Zoom Meetings`` — the same, on a Zoom Meeting set up like a webinar (EH2,
  EH11). Also offered for a members-only (Internal) event (Doug, 11-17-26,
  option B): registration on when the event takes registrations, otherwise a
  meeting without registration whose one link every member sees.
* ``Other platform`` — staff type one shared join link; the application keeps
  the registrations and its confirmation carries the link (EH3, EH13). Behind
  ``EVENTS_OTHER_PLATFORM``: off, the link cannot be typed, so a public one is
  never shown (D3-1).
* ``Outside host`` — rulings D3-3 and D3-4 (``visibility.hosted_outside``).

The method counts only for an online event (Virtual or Hybrid; on a hybrid
event it covers the online half, EH14). On a members-only event only Zoom
Meetings is a method; anything else keeps the members' typed link (D2 of the
F2/F3 design: Zoom Webinars are for Public events only), returned here as
:data:`MEMBERS_LINK`. An empty or unknown stored value on a public event is
Zoom Webinars, which is how every event before the field behaves.

Pure functions, except the two that build a Zoom client.
"""

from __future__ import annotations

from typing import Any, Optional

from core.zoom import PRODUCT_MEETING, PRODUCT_WEBINAR

from . import config as cfg
from . import visibility

WEBINARS = cfg.HOSTED_CBM_ZOOM
MEETINGS = cfg.HOSTED_ZOOM_MEETINGS
OTHER = cfg.HOSTED_OTHER
OUTSIDE = cfg.HOSTED_OUTSIDE
#: Not a stored value: a members-only event whose link staff type (D2).
MEMBERS_LINK = "Members link"

#: What staff read for each stored value.
LABELS: dict[str, str] = {
    WEBINARS: "Zoom Webinars",
    MEETINGS: "Zoom Meetings",
    OTHER: "Other platform",
    OUTSIDE: "Outside host",
}

#: The confirmation's link, per :func:`confirmation_link`.
LINK_PERSONAL = "personal"
LINK_SHARED = "shared"
LINK_NONE = "none"

#: The words a confirmation adds under a shared Other-platform link (EH13).
SHARED_LINK_NOTE = ("This join link is the same for everyone attending. "
                    "Please keep it to yourself.")


def stored(event: dict[str, Any]) -> str:
    return str(event.get(cfg.HOSTED_BY_FIELD) or "").strip()


def label(value: str) -> str:
    return LABELS.get(value, value or LABELS[WEBINARS])


def is_online(event: dict[str, Any]) -> bool:
    return (event.get("format") or "") in cfg.ONLINE_FORMATS


def members_only(event: dict[str, Any]) -> bool:
    """An Internal event by an audience someone SET. An event from before the
    field has none and keeps behaving as the public programme's (the D2
    carry-over the Zoom sync has always used)."""
    return bool(str(event.get(cfg.AUDIENCE_FIELD) or "").strip()) and (
        visibility.effective_audience(event) == cfg.AUDIENCE_INTERNAL)


def method(event: dict[str, Any]) -> str:
    """The event's hosting method where it counts, or "" for an event with no
    online part."""
    if not is_online(event):
        return ""
    value = stored(event)
    if members_only(event):
        return MEETINGS if value == MEETINGS else MEMBERS_LINK
    if value in (MEETINGS, OTHER, OUTSIDE):
        return value
    return WEBINARS


def zoom_product(event: dict[str, Any]) -> str:
    """The Zoom product the application should host this event on, or ""."""
    m = method(event)
    if m == WEBINARS:
        return PRODUCT_WEBINAR
    if m == MEETINGS:
        return PRODUCT_MEETING
    return ""


def stored_product(event: dict[str, Any]) -> str:
    """The product an event's EXISTING Zoom id belongs to. The id field serves
    both products (handoff decision); the stored method says which, whatever
    the audience or format now — every id before Zoom Meetings is a webinar's."""
    return PRODUCT_MEETING if stored(event) == MEETINGS else PRODUCT_WEBINAR


def zoom_registration(event: dict[str, Any]) -> bool:
    """Whether the event's Zoom event takes registrations: always for a
    webinar and a public meeting; for a members-only meeting, when the event
    takes registrations."""
    if zoom_product(event) == PRODUCT_MEETING and members_only(event):
        return bool(event.get(cfg.TAKES_REGISTRATIONS_FIELD))
    return True


def zoom_owns_link(event: dict[str, Any]) -> bool:
    """The Join URL is Zoom's and never typed: an event on Zoom Meetings,
    members-only included. (A public webinar's is already never typed.)"""
    return method(event) == MEETINGS


def other_platform_on(settings: Any = None) -> bool:
    if settings is None:
        from core.config import get_settings

        settings = get_settings()
    return bool(getattr(settings, "events_other_platform", False))


def confirmation_link(event: dict[str, Any], settings: Any = None) -> str:
    """Which join link a confirmation carries.

    * :data:`LINK_PERSONAL` — the registrant's own Zoom link, and nothing
      else: without one the confirmation waits (D3-1, D3-2).
    * :data:`LINK_SHARED` — the event's Join URL: an Other-platform event
      while its switch is on (EH13), a members-only event's typed link, and
      a members-only meeting that takes no registrations.
    * :data:`LINK_NONE` — an event with no online part.

    An Other-platform event while its switch is off, and an Outside host
    event, keep the old rule for a public online event: personal or nothing.
    """
    m = method(event)
    if not m:
        return LINK_NONE
    if m in (WEBINARS, MEETINGS):
        return LINK_PERSONAL if zoom_registration(event) else LINK_SHARED
    if m == MEMBERS_LINK:
        return LINK_SHARED
    if m == OTHER and other_platform_on(settings):
        return LINK_SHARED
    return LINK_PERSONAL


def shared_link_note(event: dict[str, Any]) -> str:
    """EH13's line under a shared link, for an Other-platform event only."""
    return SHARED_LINK_NOTE if method(event) == OTHER else ""


def public_join_url(event: dict[str, Any]) -> str:
    """The Join URL a PUBLIC page may carry. An Other-platform link goes only
    in the confirmation and the calendar file (EH13), and a Zoom Meeting's
    general link would let someone register with Zoom behind our back, so
    neither is shown. The rest keep what they showed before."""
    if method(event) in (OTHER, MEETINGS):
        return ""
    return str(event.get("virtualMeetingUrl") or "")


# --- the Zoom side --------------------------------------------------------------

def zoom_client(settings: Any, product: str) -> Optional[Any]:
    """The client for ``product``, or None when that Zoom integration is off or
    not set up. A webinar never falls back to Meetings' client or the reverse,
    beyond the one credentials rule in ``core/zoom.webinars_account``."""
    from core.zoom import make_client, make_meetings_client

    if product == PRODUCT_MEETING:
        return make_meetings_client(settings)
    return make_client(settings)


def zoom_host(settings: Any, product: str) -> str:
    """The Zoom user the product's events are created under (EH8)."""
    from core.zoom import meetings_account, webinars_account

    if product == PRODUCT_MEETING:
        return meetings_account(settings).host
    return webinars_account(settings).host


def product_name(product: str) -> str:
    return "Zoom Meetings" if product == PRODUCT_MEETING else "Zoom Webinars"


def not_ready_reason(product: str) -> str:
    return f"{product_name(product)} is not switched on or not set up in System Settings"
