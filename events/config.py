"""Configuration for the Events & Webinars feature.

One place for the CRM entity/field names, the enum values the code branches on,
and the field spec that will drive both the staff editor layout and the
server-side write whitelist (the ``SESSION_FIELDS`` / ``CONTRIBUTION_FIELDS``
pattern).

Field names verified live against crm-test 2026-07-25 — see
``cevent-entities-crm-handoff.md``, which records the as-built schema and the
change list applied to it.

**Vocabulary trap, read before touching the public payload.** The website's
current data source (a Google Apps Script) speaks *Zoom's* vocabulary, in which
``topic`` means the meeting **title**. The CRM's ``CEvent.topic`` is something
else entirely: the 10-value subject **category** (D-18). The public payload
therefore keeps ``topic`` = the event title, for drop-in compatibility with the
page's existing rendering code, and exposes the category as ``category``. Do not
"fix" this by aligning the names — it would silently blank every title on the
live site.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- Entities --------------------------------------------------------------

EVENT = "CEvent"
REGISTRATION = "CEventRegistration"

# --- Enum values the code branches on --------------------------------------
# (Option lists for the UI are read live from CRM metadata; these are only the
# values that carry behaviour.)

# CEvent.status
STATUS_PLANNED = "Planned"
STATUS_HELD = "Held"
STATUS_NOT_HELD = "Not Held"
STATUS_CANCELLED = "Cancelled"

# CEvent.format - THIS is what the Zoom logic keys on, not eventType.
FORMAT_IN_PERSON = "In-Person"
FORMAT_VIRTUAL = "Virtual"
FORMAT_HYBRID = "Hybrid"
#: Formats that get a Zoom webinar provisioned (Phase 2).
ONLINE_FORMATS = (FORMAT_VIRTUAL, FORMAT_HYBRID)

# CEventRegistration.attendanceStatus - one field, each state a value (the
# Submission-Admin request-status precedent).
REG_REGISTERED = "Registered"
REG_WAITLISTED = "Waitlisted"
REG_CANCELLED = "Cancelled"
REG_ATTENDED = "Attended"
REG_NO_SHOW = "No-Show"
# CEventRegistration.registrationSource — the LIVE CRM options. "Website" is
# NOT one of them (the public channel is "Online"); inventing a value makes
# EspoCRM 400 the whole create, which is how this was found.
SOURCE_ONLINE = "Online"
SOURCE_WALK_IN = "Walk-In"
SOURCE_STAFF = "Staff"
SOURCE_IMPORT = "Import"
#: A member registering for an Internal event from the portal (F3-7). A CRM
#: option to be added — the portal Register action checks for it live and
#: refuses plainly until it exists, because an unknown value 400s the create.
SOURCE_PORTAL = "Portal"

# --- Audience and display time (F2 + F3) -----------------------------------
# Design: prds/events/CBM_Events_Audience_and_Display_Design.md. Every rule
# that reads these lives in events/visibility.py.

#: "Show this event" — relabelled, but the CRM field keeps its name (F3-4).
SHOW_FIELD = "publishToWebsite"
AUDIENCE_FIELD = "audience"
AUDIENCE_INTERNAL = "Internal"
AUDIENCE_PUBLIC = "Public"
REACH_FIELD = "publicReach"
REACH_THIS = "This chapter"
REACH_ALL = "All chapters"
REACH_SELECTED = "Selected chapters"
#: The chapters' short labels (cleveland, boston), from the CRM standard.
REACH_CHAPTERS_FIELD = "reachChapters"
INTERNAL_TEAMS_FIELD = "internalTeams"
TAKES_REGISTRATIONS_FIELD = "takesRegistrations"
#: The display time. An existing, never-used field reused by Doug's ruling D1.
DISPLAY_FROM_FIELD = "eventReleaseDate"

#: The F2/F3 fields, each feature-detected from live CRM metadata: a field the
#: CRM lacks drops out of the editor, the write whitelist and the CRM filters.
AUDIENCE_FIELDS: tuple[str, ...] = (
    AUDIENCE_FIELD, REACH_FIELD, REACH_CHAPTERS_FIELD, INTERNAL_TEAMS_FIELD,
    TAKES_REGISTRATIONS_FIELD, DISPLAY_FROM_FIELD,
)

#: Statuses that occupy a seat.
SEAT_TAKING = (REG_REGISTERED, REG_ATTENDED, REG_NO_SHOW)
#: Statuses that count as "did not attend but was expected".
COUNTS_AS_EXPECTED = (REG_REGISTERED, REG_ATTENDED, REG_NO_SHOW)

# --- Timezone --------------------------------------------------------------
#: Events are authored and displayed in Cleveland time; the CRM stores UTC.
#: (The API-treats-datetimes-as-UTC gotcha - see CLAUDE.md v0.39.2.)
PUBLIC_TIMEZONE = "America/New_York"

# --- Select lists ----------------------------------------------------------

#: Attributes read for a public listing. Keep tight - these responses are cached
#: and served to the world.
PUBLIC_SELECT = ",".join([
    "id", "name", "slug", "description", "eventOverview", "eventSyllabus",
    "dateStart", "dateEnd", "duration", "status", "format", "eventType",
    "topic", "location", "venueCapacity", "publishToWebsite",
    "registrationCloses", "recordingUrl", "virtualMeetingUrl", "zoomWebinarId",
    # The staff Overview shows every spec field, so the record must carry it.
    "registrationUrl",
    "eventGraphicId",
    # F2/F3. Selecting an attribute the CRM does not have is silently ignored
    # (verified on crm-test 2026-09-29), so these ride every read safely; the
    # public payload never exposes them.
    "audience", "publicReach", "reachChapters", "internalTeams",
    "takesRegistrations", "eventReleaseDate",
])

# --- event graphic (EV-05b) -------------------------------------------------
# `CEvent.eventGraphic` is an EspoCRM file field: the value is an Attachment id
# in `eventGraphicId`. It is uploaded and served through dedicated endpoints
# rather than the generic field editor, because the browser cannot reach
# EspoCRM directly — every image is proxied by this app.
GRAPHIC_FIELD = "eventGraphic"
ALLOWED_IMAGE_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/gif",
})
#: ~5 MB of raw bytes once base64 expansion is accounted for.
MAX_IMAGE_B64_CHARS = 7_000_000

#: Attributes read when summarising registrations for an event.
REGISTRATION_SELECT = ",".join([
    "id", "eventId", "contactId", "email", "firstName", "lastName",
    "attendanceStatus", "attendanceSource", "registrationDate",
    "registrationSource", "minutesAttended", "joinTime", "leaveTime",
    "marketingOptIn", "zoomRegistrantId", "unmatchedParticipant",
])


# --- Field spec ------------------------------------------------------------


@dataclass(frozen=True)
class EventField:
    """One editable field on the event form.

    ``name`` is the CRM api-name. ``group`` drives the editor layout; ``type``
    is a hint for the renderer (options for enums are fetched live from CRM
    metadata, never hard-coded here). The set of names is ALSO the server-side
    write whitelist - anything not listed is dropped from an update.
    """

    name: str
    label: str
    type: str = "varchar"
    group: str = "Event"
    big: bool = False
    help: str = ""
    #: Fields the app computes/owns; never offered in the editor AND not
    #: writable through the ordinary update path.
    app_managed: bool = False
    #: Writable like any other field, but not rendered as a control — the app
    #: derives it from another input. ``dateEnd`` is the case: EspoCRM's
    #: ``duration`` is virtual (dateEnd - dateStart), so the editor shows a
    #: Duration select and sends the recomputed dateEnd.
    hidden: bool = False
    #: Show the control only while another field holds one of these values —
    #: ``("audience", ("Public",))``. The value is still posted when hidden.
    show_when: Optional[tuple[str, tuple[str, ...]]] = None


#: The curated subject categories, in the order the CRM lists them. Used to
#: order the public recorded-library filter so it reads the way the dropdown in
#: Event Administration does. Only the ones that actually have a recording are
#: offered, and a value that has drifted out of this list still appears rather
#: than disappearing from the filter — the CRM stays the source of truth, this
#: is only an ordering.
TOPIC_ORDER: tuple[str, ...] = (
    "Business Fundamentals",
    "Marketing & Sales",
    "Finance & Accounting",
    "Legal & Compliance",
    "Operations",
    "Technology & Digital",
    "Leadership & People",
    "Industry-Specific",
    "Networking",
    "Other",
)


EVENT_FIELDS: list[EventField] = [
    # Event
    EventField("name", "Title", "varchar", "Event"),
    EventField("description", "Summary", "text", "Event", big=True,
               help="The short blurb shown on the website calendar card."),
    EventField("eventType", "Event type", "enum", "Event"),
    EventField("format", "Format", "enum", "Event",
               help="Virtual or Hybrid events get a Zoom webinar."),
    EventField("topic", "Topic", "enum", "Event",
               help="Subject category used by the website's recorded-webinar search."),

    # Schedule
    EventField("dateStart", "Starts", "datetime", "Schedule"),
    EventField("duration", "Duration", "duration", "Schedule"),
    EventField("registrationCloses", "Registration closes", "datetime", "Schedule",
               help="Leave empty to close registration when the event starts."),
    # Not rendered: the Duration select above is translated into this on save,
    # because EspoCRM's `duration` is virtual and storing it does nothing.
    EventField("dateEnd", "Ends", "datetime", "Schedule", hidden=True),

    # Place & capacity
    EventField("location", "Location", "text", "Place & capacity",
               help="Venue for in-person and hybrid events."),
    EventField("venueCapacity", "Capacity", "int", "Place & capacity",
               help="Seat cap. Leave empty or 0 for unlimited."),

    # Content
    EventField("eventOverview", "Full description", "wysiwyg", "Content", big=True),
    EventField("eventSyllabus", "Syllabus", "wysiwyg", "Content", big=True),
    # Uploaded through its own endpoint (a file field can't ride the generic
    # PUT), so app_managed keeps it out of the update whitelist while still
    # declaring it to the editor, which renders the upload control.
    EventField("eventGraphic", "Event graphic", "image", "Content",
               app_managed=True,
               help="Shown on the website card and the event page. Without one "
                    "the card falls back to the recording's YouTube thumbnail, "
                    "which an upcoming event doesn't have yet."),

    # Publishing — "whether" first, then "where", then "when" (F2/F3).
    EventField("publishToWebsite", "Show this event", "bool", "Publishing",
               help="Nothing is shown anywhere until this is ticked. The audience "
                    "below decides where it is shown."),
    EventField("audience", "Audience", "enum", "Publishing",
               help="Internal: the portal calendar only. Public: the public pages "
                    "and the portal calendar."),
    EventField("publicReach", "Reach", "enum", "Publishing",
               show_when=("audience", ("Public",)),
               help="Other chapters do not show this event yet. The reach is "
                    "recorded now so the shared list can use it later."),
    EventField("reachChapters", "Chapters", "multiEnum", "Publishing",
               show_when=("publicReach", ("Selected chapters",)),
               help="This chapter is always included."),
    EventField("internalTeams", "Limit to teams", "multiEnum", "Publishing",
               show_when=("audience", ("Internal",)),
               help="Empty: every signed-in member sees it. This hides the event "
                    "on the portal only. It does not make it private: anyone who "
                    "can read events in the CRM can still find it."),
    EventField("takesRegistrations", "Takes registrations", "bool", "Publishing",
               show_when=("audience", ("Internal",)),
               help="Shows a Register button to members on the portal."),
    EventField("eventReleaseDate", "Display from", "datetime", "Publishing",
               help="Leave empty to show the event as soon as it is ticked. "
                    "Registration opens at this time too."),
    EventField("slug", "URL slug", "varchar", "Publishing", app_managed=True),
    EventField("recordingUrl", "Recording URL", "url", "Publishing",
               help="Paste the YouTube link once the recording is published."),

    # Zoom (app-managed)
    EventField("zoomWebinarId", "Zoom webinar ID", "varchar", "Zoom", app_managed=True),
    EventField("virtualMeetingUrl", "Join URL", "url", "Zoom", app_managed=True),
    EventField("registrationUrl", "Zoom registration URL", "url", "Zoom",
               app_managed=True),
]

# --- Sponsorship links (Phase B of prds/mailing-list-and-event-sponsorship-plan.md)
# An event's partners and funders are RELATIONSHIPS on CEvent, not fields:
# read through ``list_related``, written with relate/unrelate (a ``*Ids`` write
# is silently ignored — see CLAUDE.md § Gotchas). The partner link is a CRM
# build (``cevent-partner-sponsorship-crm-handoff.md``); the funder link has
# existed since the first events handoff. Each is feature-detected per load,
# so a CRM without the partner link simply shows no Partners picker.


@dataclass(frozen=True)
class EventLink:
    """One many-to-many link the editor offers as a picker."""

    name: str          #: the link on CEvent
    label: str         #: what staff see
    entity: str        #: the far entity
    foreign: str       #: the link on the far entity (its reverse)


SPONSOR_LINKS: tuple[EventLink, ...] = (
    EventLink("partnerProfiles", "Partners", "CPartnerProfile", "sponsoredEvents"),
    EventLink("sponsorProfiles", "Funders", "CSponsorProfile", "sponsoredEvents"),
)
SPONSOR_LINK_NAMES: frozenset[str] = frozenset(l.name for l in SPONSOR_LINKS)
#: The editor group the pickers sit in, and the Overview facts group.
SPONSOR_GROUP = "Sponsorship"

#: Server-side write whitelist for the staff editor (Phase 5).
EVENT_EDIT_NAMES: frozenset[str] = frozenset(
    f.name for f in EVENT_FIELDS if not f.app_managed
)

#: Everything the app may write, including the fields it manages itself.
EVENT_WRITABLE_NAMES: frozenset[str] = frozenset(f.name for f in EVENT_FIELDS)
