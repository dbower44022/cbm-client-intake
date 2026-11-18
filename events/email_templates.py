"""The event email templates: their default wording, and creating the missing
ones (EV-60; Track D, D1).

The application sends every event email from an EspoCRM email template, so the
wording is the staff's, not the code's, but a template that does not exist is
a send that refuses. :func:`create_missing` writes each missing one ONCE, by its
exact name, with plain default wording. A template that already exists is never
touched, so staff edits survive every run.

Used by ``scripts/seed_event_templates.py`` (``scripts/seed_templates.sh``) and
by the Event hosting card's fix button on Feature readiness
(prds/events/event-hosting-plan.md § 8 item 3, ruling R2). Creating an email
template needs a CRM administrator: callers pass the provisioning admin.

Placeholders: EspoCRM's own ``{Contact.firstName}`` style resolves at render;
the ``{{token}}`` style is this application's (``events/confirm.py``,
``TOKEN_NAMES``).
"""

from __future__ import annotations

from typing import Any


def _p(text: str) -> str:
    return f"<p>{text}</p>"


SIGN_OFF = _p("Warm regards,<br>{{orgName}}")

TEMPLATES: list[dict[str, str]] = [
    {
        "name": "EventConfirmation",
        "subject": "You're registered: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("You are registered for <strong>{{eventName}}</strong>."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            "{{joinBlock}}",
            _p("A calendar entry is attached. Details: <a href=\"{{eventUrl}}\">{{eventUrl}}</a>"),
            _p("Can't make it? <a href=\"{{cancelUrl}}\">Cancel your registration</a> so the place can go to someone else."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventWaitlisted",
        "subject": "You're on the waiting list: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("<strong>{{eventName}}</strong> is full, and you are on the waiting list."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            _p("If a place opens up we will email you straight away with everything you need."),
            _p("No longer interested? <a href=\"{{cancelUrl}}\">Leave the waiting list</a>."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventSeatOffered",
        "subject": "A place opened up: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("Good news: a place has opened up and you are now registered for <strong>{{eventName}}</strong>."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            "{{joinBlock}}",
            _p("A calendar entry is attached. Details: <a href=\"{{eventUrl}}\">{{eventUrl}}</a>"),
            _p("Can't make it after all? <a href=\"{{cancelUrl}}\">Cancel your registration</a>."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventReminder",
        "subject": "Tomorrow: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("A reminder that <strong>{{eventName}}</strong> is tomorrow."),
            _p("<strong>When:</strong> {{when}}<br><strong>Where:</strong> {{where}}"),
            "{{joinBlock}}",
            _p("Can't make it? <a href=\"{{cancelUrl}}\">Cancel your registration</a> so the place can go to someone else."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventRecordingAvailable",
        "subject": "Recording available: {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("The recording of <strong>{{eventName}}</strong> is now available:"),
            _p("<a href=\"{{recordingUrl}}\">{{recordingUrl}}</a>"),
            _p("You can find every recorded webinar at <a href=\"{{eventUrl}}\">{{eventUrl}}</a>."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventNoShow",
        "subject": "We missed you at {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("We missed you at <strong>{{eventName}}</strong>. Things come up — the recording, when there is one, will be on our site, and the next session is never far away."),
            _p("If you would like a hand with your business in the meantime, our mentors are free and happy to help."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventMentorCTA",
        "subject": "Thank you for joining {{eventName}}",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("Thank you for joining <strong>{{eventName}}</strong>."),
            _p("{{orgName}} offers free, confidential mentoring to small business owners and nonprofit leaders. If you would like to work one-to-one with an experienced mentor, request one on our website and we will match you within a few days."),
            SIGN_OFF,
        ]),
    },
    {
        "name": "EventSurvey",
        "subject": "Two minutes on {{eventName}}?",
        "body": "".join([
            _p("Hello {{firstName}},"),
            _p("Thank you for attending <strong>{{eventName}}</strong>. Would you give us two minutes of feedback? Reply to this email with what worked and what we should change — every reply is read by the people who plan the next session."),
            SIGN_OFF,
        ]),
    },
]


#: The eight names, in the order above.
NAMES: tuple[str, ...] = tuple(t["name"] for t in TEMPLATES)


async def existing(client: Any) -> dict[str, dict[str, Any]]:
    """The CRM's email templates by name (every page of up to 200)."""
    found: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        page = await client.list("EmailTemplate", select="id,name", max_size=200, offset=offset)
        rows = page.get("list", []) if page else []
        for row in rows:
            found[(row.get("name") or "").strip()] = row
        offset += len(rows)
        if len(rows) < 200 or offset >= int((page or {}).get("total") or 0):
            return found


async def create_missing(client: Any, *, apply: bool = True) -> dict[str, list[str]]:
    """Create every template the CRM lacks. ``{"created": [...], "existing":
    [...]}``; with ``apply`` False, ``created`` lists what would be created."""
    have = await existing(client)
    created: list[str] = []
    kept: list[str] = []
    for spec in TEMPLATES:
        if spec["name"] in have:
            kept.append(spec["name"])
            continue
        if apply:
            await client.create("EmailTemplate", {
                "name": spec["name"], "subject": spec["subject"],
                "body": spec["body"], "isHtml": True, "oneOff": False,
            })
        created.append(spec["name"])
    return {"created": created, "existing": kept}
