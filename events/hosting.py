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


# --- the event form (plan § 7 step 5: EH4 to EH6, EH14) -------------------------

#: The order the form offers them in.
METHOD_ORDER = (WEBINARS, MEETINGS, OTHER, OUTSIDE)

NOT_SET_UP = "Not set up — set it up in System Settings."

#: Hosts open a meeting early: a Zoom event's busy window starts this long
#: before its start (plan § 6 point 5).
OVERLAP_LEAD_MINUTES = 30


def _settings(settings: Any) -> Any:
    if settings is None:
        from core.config import get_settings

        return get_settings()
    return settings


def meetings_capacity(settings: Any = None) -> int:
    try:
        return int(getattr(_settings(settings), "zoom_meetings_capacity", 100) or 0)
    except (TypeError, ValueError):
        return 100


def ready(value: str, settings: Any = None) -> bool:
    """Whether a method's integration or switch is set up (EH4's reason)."""
    s = _settings(settings)
    if value == MEETINGS:
        return bool(getattr(s, "zoom_meetings_active", False))
    if value == OTHER:
        return other_platform_on(s)
    if value == OUTSIDE:
        return True
    return bool(getattr(s, "zoom_active", False))


def explain(value: str, *, members: bool, capacity: int = 100) -> str:
    """EH4: one line on what the method means for attendees. A members-only
    event is hosted by the application only on Zoom Meetings; on any other
    choice members join by the link staff paste."""
    if members and value != MEETINGS:
        if value == WEBINARS:
            return ("Zoom Webinars are for public events. On a members-only event, "
                    "members join by the link you paste below.")
        return "Members join by the link you paste below."
    if value == MEETINGS:
        line = ("Attendees register with us and each gets their own Zoom link. They "
                "join muted with cameras off, and may unmute. "
                f"Up to {capacity} can join.")
        if members:
            line += (" If the event takes no registrations, every member sees one "
                     "link instead.")
        return line
    if value == OTHER:
        return ("Attendees register with us and get one shared link, which you paste "
                "below (Teams, Google Meet, another Zoom account). Attendance is "
                "marked by hand.")
    if value == OUTSIDE:
        return ("A partner runs it on their own platform. Visitors register on the "
                "host's site; we take no registrations and record no attendance.")
    return ("Attendees register with us and each gets their own Zoom link. Only "
            "presenters are seen and heard.")


def methods_payload(settings: Any = None) -> dict[str, Any]:
    """What the event form needs to offer the methods: each one's label,
    readiness and explanations, and the two defaults per audience (EH5)."""
    s = _settings(settings)
    cap = meetings_capacity(s)
    methods = []
    for value in METHOD_ORDER:
        is_ready = ready(value, s)
        methods.append({
            "value": value,
            "label": LABELS[value],
            "ready": is_ready,
            "reason": "" if is_ready else NOT_SET_UP,
            "explain": explain(value, members=False, capacity=cap),
            "explainMembers": explain(value, members=True, capacity=cap),
        })
    return {
        "methods": methods,
        "defaults": {
            cfg.AUDIENCE_PUBLIC: getattr(s, "events_default_method_public", WEBINARS) or WEBINARS,
            cfg.AUDIENCE_INTERNAL: getattr(s, "events_default_method_members", WEBINARS) or WEBINARS,
        },
        "meetingsCapacity": cap,
        # The stored value that means Zoom Webinars, so the form never types
        # it (the branding guard refuses the acronym in served files).
        "webinars": WEBINARS,
    }


def option_labels(settings: Any = None) -> dict[str, str]:
    """The select's labels: the method's name, and the not-set-up reason."""
    s = _settings(settings)
    return {
        value: LABELS[value] + ("" if ready(value, s) else " (not set up)")
        for value in METHOD_ORDER
    }


def default_for(audience: str, settings: Any = None) -> str:
    s = _settings(settings)
    if audience == cfg.AUDIENCE_INTERNAL:
        return getattr(s, "events_default_method_members", WEBINARS) or WEBINARS
    return getattr(s, "events_default_method_public", WEBINARS) or WEBINARS


def capacity_check(event: dict[str, Any], settings: Any = None) -> tuple[str, str]:
    """EH6 and EH14: ``("refuse"|"warn"|"", message)``.

    A fully online event on Zoom Meetings whose capacity is above the plan's
    limit is refused; a hybrid one is warned, since its one capacity counts
    the room too."""
    if method(event) != MEETINGS:
        return "", ""
    try:
        capacity = int(event.get("venueCapacity") or 0)
    except (TypeError, ValueError):
        return "", ""
    limit = meetings_capacity(settings)
    if not limit or capacity <= limit:
        return "", ""
    if (event.get("format") or "") == cfg.FORMAT_HYBRID:
        return "warn", (f"Capacity {capacity} is above Zoom Meetings' {limit}. If more "
                        f"than {limit} join online, the rest cannot get in.")
    return "refuse", (f"Capacity {capacity} is above Zoom Meetings' {limit} on this "
                      "chapter's Zoom plan. Lower the capacity, or host the event on "
                      "Zoom Webinars.")


def warnings(event: dict[str, Any], settings: Any = None) -> list[str]:
    """Hosting warnings after a save or in the check before one: the method's
    integration not set up, and the hybrid capacity warning. Never blocking."""
    out: list[str] = []
    m = method(event)
    if m and m not in (MEMBERS_LINK,) and not ready(m, settings):
        what = {WEBINARS: "no webinar is created", MEETINGS: "no meeting is created",
                OTHER: "its shared link cannot be filled in"}.get(m, "")
        out.append(f"{LABELS[m]} is not set up in System Settings, so {what} "
                   "until it is.")
    kind, message = capacity_check(event, settings)
    if kind == "warn":
        out.append(message)
    return out


def busy_window(event: dict[str, Any]) -> Optional[tuple[Any, Any]]:
    """The time a Zoom event occupies its host: from 30 minutes before the
    start to the end (plan § 6 point 5). None without a start."""
    from datetime import timedelta

    from .service import parse_crm_datetime

    start = parse_crm_datetime(event.get("dateStart"))
    if start is None:
        return None
    end = parse_crm_datetime(event.get("dateEnd")) or start + timedelta(hours=1)
    return start - timedelta(minutes=OVERLAP_LEAD_MINUTES), end


def host_of(event: dict[str, Any], settings: Any = None) -> str:
    """The Zoom user the event's Zoom event runs under, lower-cased, or ""."""
    product = zoom_product(event)
    if not product:
        return ""
    return (zoom_host(_settings(settings), product) or "").strip().lower()


def overlaps(event: dict[str, Any], others: list[dict[str, Any]],
             settings: Any = None) -> list[dict[str, Any]]:
    """The other Zoom events under the same event host user whose busy windows
    meet this one's. Webinars and meetings alike: one Zoom user hosts one at a
    time (Zoom's documentation, not tried). Cancelled events never count."""
    host = host_of(event, settings)
    window = busy_window(event)
    if not host or window is None or event.get("status") == cfg.STATUS_CANCELLED:
        return []
    found = []
    for other in others:
        if other.get("id") and other.get("id") == event.get("id"):
            continue
        if other.get("status") == cfg.STATUS_CANCELLED:
            continue
        if host_of(other, settings) != host:
            continue
        theirs = busy_window(other)
        if theirs and theirs[0] < window[1] and window[0] < theirs[1]:
            found.append(other)
    return found


def overlap_warning(event: dict[str, Any], clashes: list[dict[str, Any]],
                    settings: Any = None) -> str:
    if not clashes:
        return ""
    from .service import parse_crm_datetime, to_local

    def name(e: dict[str, Any]) -> str:
        start = parse_crm_datetime(e.get("dateStart"))
        when = to_local(start).strftime("%a %b %-d, %-I:%M %p") if start else ""
        return f"“{e.get('name') or 'an event'}” ({when})" if when else f"“{e.get('name')}”"

    listed = ", ".join(name(e) for e in clashes[:3])
    more = f" and {len(clashes) - 3} more" if len(clashes) > 3 else ""
    return (f"This overlaps {listed}{more}, also run by the Zoom user "
            f"{host_of(event, settings)}. One Zoom user can host only one meeting or "
            "webinar at a time, counting from 30 minutes before each start.")


def publish_words(action: str, product: str, had: str = "") -> str:
    """EH6: the platform in words, before a save that makes or ends a Zoom event."""
    if action == "create":
        return ("This creates a Zoom Meeting, not a webinar." if product == PRODUCT_MEETING
                else "This creates a Zoom webinar.")
    if action == "replace":
        return (f"This cancels the {'Zoom Meeting' if had == PRODUCT_MEETING else 'Zoom webinar'} "
                f"and creates a {'Zoom Meeting' if product == PRODUCT_MEETING else 'Zoom webinar'} "
                "in its place.")
    if action == "cancel":
        return ("This cancels the event's "
                f"{'Zoom Meeting' if had == PRODUCT_MEETING else 'Zoom webinar'}.")
    return ""
