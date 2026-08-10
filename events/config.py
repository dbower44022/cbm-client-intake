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
    "eventGraphicId",
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

    # Publishing
    EventField("publishToWebsite", "Publish to website", "bool", "Publishing",
               help="Off for internal calendar entries. This is what keeps "
                    "team meetings off the public site."),
    EventField("slug", "URL slug", "varchar", "Publishing", app_managed=True),
    EventField("recordingUrl", "Recording URL", "url", "Publishing",
               help="Paste the YouTube link once the recording is published."),

    # Zoom (app-managed)
    EventField("zoomWebinarId", "Zoom webinar ID", "varchar", "Zoom", app_managed=True),
    EventField("virtualMeetingUrl", "Join URL", "url", "Zoom", app_managed=True),
    EventField("registrationUrl", "Zoom registration URL", "url", "Zoom",
               app_managed=True),
]

#: Server-side write whitelist for the staff editor (Phase 5).
EVENT_EDIT_NAMES: frozenset[str] = frozenset(
    f.name for f in EVENT_FIELDS if not f.app_managed
)

#: Everything the app may write, including the fields it manages itself.
EVENT_WRITABLE_NAMES: frozenset[str] = frozenset(f.name for f in EVENT_FIELDS)
