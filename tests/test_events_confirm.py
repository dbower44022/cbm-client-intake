"""D3 — the registration confirmation, CBM's own and the only email (rulings
D3-1 and D3-2, 10-22-26).

What must not slip: a public online event without its webinar is on no page
and takes no registrations; a public online registrant without a personal
join link is NOT confirmed (a ticket without a way in); once per registration;
cancelled gets nothing; nothing without the template; the calendar file is a
valid one-event file; the ledger is written after the send.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import Settings, get_settings
from events import config as cfg
from events import confirm, ics, visibility
from tests.test_events_service import make_event


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def settings_on(**over) -> Settings:
    base = dict(
        espo_dry_run=False, events_enabled=True, assignments_enabled=True,
        espo_base_url="https://crm.example.org", espo_api_key="k",
        gmail_sync=True, ops_mailbox="info@example.org",
        events_confirmations=True, session_secret="secret",
        app_base_url="https://apps.example.org",
    )
    base.update(over)
    return Settings(**base)


def reg(**over):
    row = {"id": "reg1", "email": "ada@example.com", "firstName": "Ada",
           "lastName": "Lovelace", "attendanceStatus": cfg.REG_REGISTERED,
           "followUpsSent": []}
    row.update(over)
    return row


class FakeCrm:
    def __init__(self, registration=None):
        self.registration = registration
        self.updated: list[tuple[str, str, dict]] = []

    async def get(self, entity, record_id, select=None):
        return self.registration if self.registration and self.registration["id"] == record_id else {}

    async def update(self, entity, record_id, payload):
        self.updated.append((entity, record_id, payload))
        if self.registration and self.registration["id"] == record_id:
            self.registration.update(payload)
        return {"id": record_id}

    async def metadata_enum_options(self, entity, field):
        return ["Reminder", "Recording", "No Show", "Mentor CTA", "Survey", "Seat Offered"]


# --- D3-1: no public online event without its webinar -------------------------

def test_public_online_event_without_a_link_is_hidden_on_every_surface():
    event = make_event(format=cfg.FORMAT_VIRTUAL, audience="Public", virtualMeetingUrl="")
    assert visibility.needs_join_link(event)
    assert not visibility.is_shown(event, visibility.SURFACE_PUBLIC)
    assert not visibility.is_shown(event, visibility.SURFACE_PORTAL)


def test_public_online_event_with_a_link_is_shown():
    event = make_event(format=cfg.FORMAT_VIRTUAL, audience="Public",
                       virtualMeetingUrl="https://zoom.us/j/1")
    assert visibility.is_shown(event, visibility.SURFACE_PUBLIC)


def test_in_person_public_event_needs_no_link():
    event = make_event(format=cfg.FORMAT_IN_PERSON, audience="Public", virtualMeetingUrl="")
    assert not visibility.needs_join_link(event)
    assert visibility.is_shown(event, visibility.SURFACE_PUBLIC)


def test_internal_online_event_without_a_link_still_shows_on_the_portal():
    event = make_event(format=cfg.FORMAT_VIRTUAL, audience="Internal", virtualMeetingUrl="")
    assert not visibility.needs_join_link(event)
    assert visibility.is_shown(event, visibility.SURFACE_PORTAL)


def test_the_public_where_clause_names_the_link_only_when_the_crm_has_it():
    bare = visibility.public_where_clauses([])
    assert all(c.get("attribute") != "format" for c in bare)
    withit = visibility.public_where_clauses(["virtualMeetingUrl"])
    clause = withit[-1]
    assert clause["type"] == "or"
    assert {c["attribute"] for c in clause["value"]} == {"format", "virtualMeetingUrl"}
    # The portal lists both audiences: no such clause there.
    portal = visibility.public_where_clauses(["virtualMeetingUrl"], surface=visibility.SURFACE_PORTAL)
    assert all(c.get("type") != "or" or "format" not in str(c) for c in portal)


def test_staff_see_why_a_webinar_is_not_shown():
    event = make_event(format=cfg.FORMAT_VIRTUAL, audience="Public", virtualMeetingUrl="")
    assert visibility.staff_state(event)["key"] == "awaiting_link"
    assert any("join link" in w for w in visibility.save_warnings(event))


# --- tokens and the calendar file ---------------------------------------------

def test_app_tokens_carry_the_personal_link_and_the_chapter_time():
    s = settings_on()
    event = make_event(slug="grant-writing-basics", location="")
    tokens = confirm.app_tokens(s, event, reg(zoomJoinUrl="https://zoom.us/w/9"), kind=confirm.KIND_CONFIRMATION)
    assert tokens["joinUrl"] == "https://zoom.us/w/9"
    assert "zoom.us/w/9" in tokens["joinBlock"]
    assert tokens["when"].startswith("Tuesday, July 28, 2026, 2:00 PM")
    assert tokens["where"] == "Online"
    assert tokens["eventUrl"] == "https://apps.example.org/webinars/grant-writing-basics"
    assert tokens["cancelUrl"].startswith("https://apps.example.org/")


def test_a_waitlisted_person_gets_no_join_link():
    s = settings_on()
    tokens = confirm.app_tokens(s, make_event(), reg(zoomJoinUrl="https://zoom.us/w/9"),
                                kind=confirm.KIND_WAITLISTED)
    assert tokens["joinUrl"] == "" and tokens["joinBlock"] == ""


def test_an_internal_event_lends_its_shared_link_a_public_one_does_not():
    internal = make_event(audience="Internal", virtualMeetingUrl="https://meet.google.com/x")
    public = make_event(audience="Public", virtualMeetingUrl="https://zoom.us/j/1")
    assert confirm.join_url_for(internal, reg()) == "https://meet.google.com/x"
    assert confirm.join_url_for(public, reg()) == ""


def test_tokens_are_escaped_in_html_but_the_join_block_is_placed_as_is():
    tokens = {"eventName": "Fish & Chips <b>", "joinBlock": "<p>ok</p>"}
    out = confirm.apply_app_tokens("{{eventName}} {{joinBlock}} {{unknown}}", tokens, as_html=True)
    assert "Fish &amp; Chips &lt;b&gt;" in out and "<p>ok</p>" in out and "{{unknown}}" in out
    assert confirm.apply_app_tokens("Re: {{eventName}}", tokens, as_html=False) == "Re: Fish & Chips <b>"


def test_the_calendar_file_is_one_utc_event():
    text = ics.build_ics(
        uid="ev1-reg1@test", summary="Grant Writing, Basics; part 1",
        start=datetime(2026, 7, 28, 18, 0, tzinfo=timezone.utc), end=None,
        location="Online", url="https://apps.example.org/webinars/x",
        now=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    assert "BEGIN:VCALENDAR" in text and text.endswith("END:VCALENDAR\r\n")
    assert "DTSTART:20260728T180000Z" in text
    assert "DTEND:20260728T190000Z" in text          # one hour when no end is known
    assert "SUMMARY:Grant Writing\\, Basics\\; part 1" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    att = ics.attachment(text)
    assert att["contentType"] == "text/calendar" and att["filename"] == "event.ics"


# --- skip rules ---------------------------------------------------------------

def test_off_switch_skips_everything():
    s = settings_on(events_confirmations=False)
    assert confirm.skip_reason(s, make_event(), reg(), confirm.KIND_CONFIRMATION)


def test_a_public_online_registrant_without_a_personal_link_is_not_confirmed():
    s = settings_on()
    event = make_event(format=cfg.FORMAT_VIRTUAL, audience="Public", virtualMeetingUrl="https://zoom.us/j/1")
    assert confirm.skip_reason(s, event, reg(), confirm.KIND_CONFIRMATION) == "no personal join link yet"
    assert confirm.skip_reason(s, event, reg(zoomJoinUrl="https://zoom.us/w/9"), confirm.KIND_CONFIRMATION) is None
    # The waiting-list note needs no link; an in-person event needs none either.
    assert confirm.skip_reason(s, event, reg(attendanceStatus=cfg.REG_WAITLISTED), confirm.KIND_WAITLISTED) is None
    assert confirm.skip_reason(s, make_event(format=cfg.FORMAT_IN_PERSON), reg(), confirm.KIND_CONFIRMATION) is None


def test_cancelled_and_already_sent_get_nothing():
    s = settings_on()
    event = make_event(format=cfg.FORMAT_IN_PERSON)
    assert confirm.skip_reason(s, event, reg(attendanceStatus=cfg.REG_CANCELLED), confirm.KIND_CONFIRMATION) == "registration cancelled"
    assert confirm.skip_reason(s, event, reg(confirmationSentAt="2026-07-01 10:00:00"), confirm.KIND_CONFIRMATION) == "already sent"
    assert confirm.skip_reason(s, event, reg(followUpsSent=["Seat Offered"]), confirm.KIND_SEAT_OFFERED) == "already sent"


def test_kind_follows_the_seat():
    assert confirm.kind_for_status(cfg.REG_REGISTERED) == confirm.KIND_CONFIRMATION
    assert confirm.kind_for_status(cfg.REG_WAITLISTED) == confirm.KIND_WAITLISTED
    assert confirm.kind_for_status(cfg.REG_CANCELLED) is None


# --- the send, with the stack stubbed -------------------------------------------

@pytest.mark.asyncio
async def test_a_confirmation_sends_once_and_is_ledgered_after(monkeypatch):
    s = settings_on()
    event = make_event(format=cfg.FORMAT_IN_PERSON, location="Westlake Porter Public Library")
    crm = FakeCrm(reg())
    sent: list[dict] = []

    async def find_template(client, name):
        return {"id": "t1", "name": name}

    async def render(client, template_id, event, email):
        return {"subject": "You're registered: {{eventName}}",
                "bodyHtml": "<p>Hello {{firstName}}</p>{{joinBlock}}<a href=\"{{cancelUrl}}\">cancel</a>"}

    async def send(settings, *, to, subject, body_html, attachments):
        sent.append({"to": to, "subject": subject, "body": body_html, "attachments": attachments})

    monkeypatch.setattr(confirm, "_find_template", find_template)
    monkeypatch.setattr(confirm, "_render", render)
    monkeypatch.setattr(confirm, "_send", send)

    out = await confirm.after_registration(s, crm, event, "reg1", cfg.REG_REGISTERED,
                                           now=datetime(2026, 7, 1, tzinfo=timezone.utc))
    assert out["ok"] and out["kind"] == confirm.KIND_CONFIRMATION
    assert sent[0]["to"] == "ada@example.com"
    assert sent[0]["subject"] == "You're registered: Grant Writing Basics"
    assert "Hello Ada" in sent[0]["body"] and "cancel" in sent[0]["body"]
    assert sent[0]["attachments"][0]["filename"] == "event.ics"
    assert crm.updated[-1][2] == {"confirmationSentAt": "2026-07-01 00:00:00"}
    # A second delivery of the same registration (a redrive) sends nothing more.
    again = await confirm.after_registration(s, crm, event, "reg1", cfg.REG_REGISTERED)
    assert again["skipped"] == "already sent" and len(sent) == 1


@pytest.mark.asyncio
async def test_no_template_means_no_email_and_a_named_reason(monkeypatch):
    s = settings_on()
    crm = FakeCrm(reg())

    async def find_template(client, name):
        return None

    monkeypatch.setattr(confirm, "_find_template", find_template)
    out = await confirm.after_registration(s, crm, make_event(format=cfg.FORMAT_IN_PERSON), "reg1", cfg.REG_REGISTERED)
    assert not out["ok"] and "EventConfirmation" in out["error"]
    assert crm.updated == []


@pytest.mark.asyncio
async def test_a_failed_send_leaves_no_ledger(monkeypatch):
    s = settings_on()
    crm = FakeCrm(reg())

    async def find_template(client, name):
        return {"id": "t1", "name": name}

    async def render(client, template_id, event, email):
        return {"subject": "x", "bodyHtml": "y"}

    async def send(settings, **kw):
        raise RuntimeError("mailbox down")

    monkeypatch.setattr(confirm, "_find_template", find_template)
    monkeypatch.setattr(confirm, "_render", render)
    monkeypatch.setattr(confirm, "_send", send)
    out = await confirm.after_registration(s, crm, make_event(format=cfg.FORMAT_IN_PERSON), "reg1", cfg.REG_REGISTERED)
    assert not out["ok"] and "mailbox down" in out["error"]
    assert crm.updated == []


@pytest.mark.asyncio
async def test_seat_offered_is_ledgered_on_follow_ups_sent(monkeypatch):
    s = settings_on()
    row = reg(zoomJoinUrl="https://zoom.us/w/9")
    crm = FakeCrm(row)

    async def find_template(client, name):
        assert name == "EventSeatOffered"
        return {"id": "t3", "name": name}

    async def render(client, template_id, event, email):
        return {"subject": "A place opened up", "bodyHtml": "{{joinBlock}}"}

    async def send(settings, **kw):
        assert "zoom.us/w/9" in kw["body_html"]

    monkeypatch.setattr(confirm, "_find_template", find_template)
    monkeypatch.setattr(confirm, "_render", render)
    monkeypatch.setattr(confirm, "_send", send)
    event = make_event(format=cfg.FORMAT_VIRTUAL, audience="Public", virtualMeetingUrl="https://zoom.us/j/1")
    out = await confirm.after_promotion(s, crm, event, row)
    assert out["ok"]
    assert crm.updated[-1][2]["followUpsSent"] == ["Seat Offered"]


def test_every_template_name_is_unique_and_catalogued():
    names = [c["template"] for c in confirm.catalogue()]
    assert len(names) == len(set(names)) == 3
