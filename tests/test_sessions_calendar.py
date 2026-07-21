"""sessions/gcal.py — the Google Calendar sync hook on session create/update.

Drives the real service.create_session / update_session with the Fake CRM
client; the Google side is a FakeCalendar injected by monkeypatching the
CalendarClient factory in sessions.gcal (so organizer resolution via
CMentorProfile.cbmEmail is exercised too)."""

from __future__ import annotations

import types

import pytest

import comms.service as comms_service
from sessions import gcal, service
from sessions.config import MENTOR

from tests.test_sessions import Fake

SETTINGS_ON = types.SimpleNamespace(gcal_events=True, request_timeout_seconds=5)
SETTINGS_OFF = types.SimpleNamespace(gcal_events=False)

# The feature-detected CRM field exists in these tests unless stated otherwise.
META = {"googleCalendarEventId": {"type": "varchar"}, "dateStart": {"required": True}}

MEET = "https://meet.google.com/abc-defg-hij"


@pytest.fixture(autouse=True)
def _service_account(monkeypatch):
    """comms.service.get_service_account returns a canned key (no DB/env)."""
    monkeypatch.setattr(comms_service, "_sa_info", {"client_email": "sa@x"})


class FakeCalendar:
    def __init__(self, create_result=None, fail=False):
        self.mailbox = "mgr@cbmentors.org"
        self.created, self.patched, self.deleted, self.gets = [], [], [], []
        self.create_result = create_result or {"id": "ev1", "hangoutLink": MEET}
        self.fail = fail

    async def create_event(self, body, *, send_updates="all"):
        if self.fail:
            raise RuntimeError("google is down")
        self.created.append((body, send_updates))
        return dict(self.create_result)

    async def get_event(self, event_id):
        self.gets.append(event_id)
        return dict(self.create_result, id=event_id)

    async def patch_event(self, event_id, body, *, send_updates="all"):
        if self.fail:
            raise RuntimeError("google is down")
        self.patched.append((event_id, body, send_updates))
        return {"id": event_id}

    async def delete_event(self, event_id, *, send_updates="all"):
        self.deleted.append((event_id, send_updates))


def _wire(monkeypatch, fake):
    """Route sessions.gcal's CalendarClient construction to the fake (capturing
    the impersonated mailbox it would have used)."""
    def factory(sa_info, mailbox, timeout=20):
        fake.mailbox = mailbox
        return fake
    monkeypatch.setattr(gcal, "CalendarClient", factory)


def _fake_crm(**kw):
    """A Fake CRM whose signed-in user u1 owns mentor profile mp1 with a CBM
    mailbox, one attendee contact, and the parent engagement E1."""
    fake = Fake(
        mentors=[{"id": "mp1", "assignedUserId": "u1"}],
        related={"sessionAttendees": kw.pop("attendee_rows", [
            {"id": "c1", "name": "Pat Koran", "emailAddress": "pat@x.com"},
            {"id": "c2", "name": "Mgr Self", "emailAddress": "MGR@cbmentors.org"},
            {"id": "c3", "name": "No Email"},
        ])},
        meta_fields=kw.pop("meta_fields", dict(META)),
        records=dict({
            ("CMentorProfile", "mp1"): {"cbmEmail": " Mgr@CBMentors.org "},
            ("CEngagement", "E1"): {"name": "Agape W8 Loss"},
        }, **kw.pop("records", {})),
        **kw,
    )
    return fake


NEW_CHANGES = {"name": "Kickoff", "dateStart": "2026-07-20 19:30:00", "dateEnd": "2026-07-20 20:30:00"}


# --- create -------------------------------------------------------------------

async def test_create_scheduled_creates_event_and_stores_link(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), ["c1"], owner_user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"] == {"ok": True, "eventId": "ev1", "meetLink": MEET}
    assert len(cal.created) == 1
    body, send = cal.created[0]
    assert body["summary"] == "Kickoff"
    assert "Agape W8 Loss" in body["description"]
    assert body["start"] == {"dateTime": "2026-07-20T19:30:00Z"}
    # Id-before-invite: the create is QUIET (no attendees, sendUpdates=none);
    # the invitations go out via a patch AFTER the event id is stored.
    assert send == "none"
    assert body["attendees"] == []
    # attendee emails: deduped, organizer (mgr@cbmentors.org) + blanks excluded
    assert cal.patched == [("ev1", {"attendees": [{"email": "pat@x.com"}]}, "all")]
    assert body["conferenceData"]["createRequest"]["conferenceSolutionKey"] == {"type": "hangoutsMeet"}
    assert cal.mailbox == "mgr@cbmentors.org"  # cbmEmail, trimmed + lowercased
    # eventId + Meet link written back to the CSession, and onto the response
    write_back = [u for u in crm.updates if u[2].get("googleCalendarEventId")]
    assert write_back and write_back[0][2]["videoMeetingLink"] == MEET
    assert session["videoMeetingLink"] == MEET
    assert session["googleCalendarEventId"] == "ev1"


async def test_create_flag_off_is_inert(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), owner_user_id="u1", settings=SETTINGS_OFF)
    assert session["calendar"] == {"ok": False, "disabled": True}
    assert cal.created == []


async def test_create_skip_calendar_user_declined(monkeypatch):
    """skip_calendar=True (the user chose 'Save without invite' in the pre-save
    prompt): the session saves, the hook is never called, and the response says
    the invite was declined."""
    crm, cal = _fake_crm(), FakeCalendar()
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), ["c1"],
        owner_user_id="u1", settings=SETTINGS_ON, skip_calendar=True)
    assert session["calendar"] == {"ok": True, "skipped": True, "declined": True}
    assert cal.created == []
    assert session["id"]  # the session itself still saved


async def test_create_no_settings_no_calendar_key(monkeypatch):
    """Direct service calls without settings (existing tests, non-router callers)
    skip the hook entirely — no 'calendar' key at all."""
    crm = _fake_crm()
    session = await service.create_session(MENTOR, crm, "E1", dict(NEW_CHANGES), owner_user_id="u1")
    assert "calendar" not in session


async def test_create_crm_field_missing_is_inert(monkeypatch):
    crm, cal = _fake_crm(meta_fields={}), FakeCalendar()
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), owner_user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"]["disabled"] is True
    assert "googleCalendarEventId" in session["calendar"]["error"]
    assert cal.created == []


async def test_completed_session_never_creates_event(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES, status="Completed"),
        owner_user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"] == {"ok": True, "skipped": True}
    assert cal.created == []


async def test_hand_typed_link_no_meet_and_not_overwritten(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _wire(monkeypatch, cal)
    zoom = "https://zoom.us/j/123"
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES, videoMeetingLink=zoom),
        owner_user_id="u1", settings=SETTINGS_ON)
    body, _ = cal.created[0]
    assert "conferenceData" not in body
    assert body["location"] == zoom
    assert session["videoMeetingLink"] == zoom  # never replaced by a Meet link
    write_back = [u for u in crm.updates if u[2].get("googleCalendarEventId")]
    assert "videoMeetingLink" not in write_back[0][2]


async def test_meet_link_pending_retries_get_event(monkeypatch):
    crm = _fake_crm()
    cal = FakeCalendar(create_result={"id": "ev1"})  # no hangoutLink yet

    async def _later_get(event_id):
        cal.gets.append(event_id)
        return {"id": event_id, "hangoutLink": MEET}
    cal.get_event = _later_get

    async def _no_sleep(_):
        return None
    monkeypatch.setattr(gcal.asyncio, "sleep", _no_sleep)
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), owner_user_id="u1", settings=SETTINGS_ON)
    assert cal.gets == ["ev1"]
    assert session["calendar"]["meetLink"] == MEET


async def test_no_cbm_email_skips_with_message(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    crm.records[("CMentorProfile", "mp1")] = {}  # no cbmEmail
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), owner_user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"]["ok"] is False
    assert "CBM email" in session["calendar"]["error"]
    assert cal.created == []
    assert session["id"]  # the session itself saved


async def test_event_id_writeback_failure_deletes_uninvited_event(monkeypatch):
    """P2 id-before-invite: if the event id can't be stored on the session, the
    (quietly created, never-invited) event is deleted — no orphan, no
    double-invite on the next save."""
    from core.espo import EspoError

    crm, cal = _fake_crm(), FakeCalendar()
    _wire(monkeypatch, cal)
    orig_update = crm.update

    async def failing_update(entity, record_id, payload):
        if entity == "CSession" and "googleCalendarEventId" in payload:
            raise EspoError("update CSession failed: HTTP 500 down")
        return await orig_update(entity, record_id, payload)

    crm.update = failing_update
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), ["c1"], owner_user_id="u1", settings=SETTINGS_ON)
    assert session["id"]  # the session itself saved
    assert session["calendar"]["ok"] is False
    assert "before any invitations" in session["calendar"]["error"]
    # The rollback delete is QUIET (nobody was invited) and no invite patch ran.
    assert cal.deleted == [("ev1", "none")]
    assert cal.patched == []


async def test_invite_patch_failure_reports_invite_error(monkeypatch):
    """Event + stored id are safe; only the invitations failed — the save
    succeeds with an inviteError the UI shows (re-save retries the invites)."""

    class PatchFail(FakeCalendar):
        async def patch_event(self, event_id, body, *, send_updates="all"):
            raise RuntimeError("quota exceeded")

    crm, cal = _fake_crm(), PatchFail()
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), ["c1"], owner_user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"]["ok"] is True
    assert session["calendar"]["eventId"] == "ev1"
    assert "invitations could not be sent" in session["calendar"]["inviteError"]
    assert session["googleCalendarEventId"] == "ev1"  # the id still stored


async def test_calendar_failure_never_fails_save(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar(fail=True)
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), owner_user_id="u1", settings=SETTINGS_ON)
    assert session["id"]
    assert session["calendar"]["ok"] is False
    assert "google is down" in session["calendar"]["error"]


# --- update -------------------------------------------------------------------

def _seed_session(crm, **fields):
    crm.records[("CSession", "s1")] = dict({
        "id": "s1", "name": "Kickoff", "status": "Scheduled",
        "dateStart": "2026-07-20 19:30:00", "dateEnd": "2026-07-20 20:30:00",
    }, **fields)


async def test_update_time_change_patches_event(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _seed_session(crm, googleCalendarEventId="ev1", videoMeetingLink=MEET)
    _wire(monkeypatch, cal)
    session = await service.update_session(
        MENTOR, crm, "s1", {"dateStart": "2026-07-21 18:00:00"},
        user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"] == {"ok": True, "eventId": "ev1", "updated": True}
    (event_id, body, _send), = cal.patched
    assert event_id == "ev1"
    assert body["start"] == {"dateTime": "2026-07-21T18:00:00Z"}
    assert body["attendees"] == [{"email": "pat@x.com"}]
    assert cal.created == []


async def test_update_notes_only_no_calendar_call(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _seed_session(crm, googleCalendarEventId="ev1")
    _wire(monkeypatch, cal)
    session = await service.update_session(
        MENTOR, crm, "s1", {"sessionNotes": "<p>notes</p>"},
        user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"] == {"ok": True, "skipped": True}
    assert cal.patched == [] and cal.created == []


async def test_update_attendee_change_patches_event(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _seed_session(crm, googleCalendarEventId="ev1")
    _wire(monkeypatch, cal)
    session = await service.update_session(
        MENTOR, crm, "s1", {}, attendees=["c1"], user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"]["updated"] is True
    assert len(cal.patched) == 1


async def test_update_backfills_event_when_missing(monkeypatch):
    """A Scheduled session created while the flag was off gets its event on the
    next relevant edit."""
    crm, cal = _fake_crm(), FakeCalendar()
    _seed_session(crm)  # no eventId
    _wire(monkeypatch, cal)
    session = await service.update_session(
        MENTOR, crm, "s1", {"dateStart": "2026-07-21 18:00:00"},
        user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"]["ok"] is True and session["calendar"]["eventId"] == "ev1"
    assert len(cal.created) == 1


# --- CBM member addressing (Doug's ruling 2026-07-20: cbmEmail ONLY) ----------

async def test_member_attendees_invited_at_cbm_email_only(monkeypatch):
    """A co-mentor on the attendee list is invited at their cbmEmail, never the
    personal address on their Contact; the acting organizer's own Contact
    resolves to the organizer mailbox and is excluded entirely (the
    self-invite duplicate-event fix, customer report 2026-07-20)."""
    crm, cal = _fake_crm(
        attendee_rows=[
            {"id": "c1", "name": "Pat Koran", "emailAddress": "pat@x.com"},
            {"id": "c8", "name": "Robert Cohen", "emailAddress": "rob@gmail.com"},
            {"id": "c9", "name": "Mgr Self", "emailAddress": "mgr.personal@gmail.com"},
        ],
    ), FakeCalendar()
    crm.records[("CEngagement", "E1")] = {
        "name": "Agape W8 Loss", "mentorProfileId": "mp1",
    }
    crm.records[("CMentorProfile", "mp1")] = {
        "cbmEmail": " Mgr@CBMentors.org ", "contactRecordId": "c9",
    }
    crm.related["additionalMentors"] = [
        {"id": "mpC", "name": "Robert Cohen",
         "cbmEmail": "Robert.Cohen@cbmentors.org", "contactRecordId": "c8"},
    ]
    _wire(monkeypatch, cal)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), ["c1", "c8", "c9"],
        owner_user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"]["ok"] is True
    (_eid, body, _send), = cal.patched
    assert body == {"attendees": [
        {"email": "pat@x.com"}, {"email": "robert.cohen@cbmentors.org"},
    ]}


async def test_member_without_cbm_email_never_invited_personally(monkeypatch):
    """A CBM member whose profile has no cbmEmail is skipped — the personal
    Contact address is never used as a fallback."""
    crm, cal = _fake_crm(
        attendee_rows=[
            {"id": "c1", "name": "Pat Koran", "emailAddress": "pat@x.com"},
            {"id": "c8", "name": "New Mentor", "emailAddress": "new@gmail.com"},
        ],
    ), FakeCalendar()
    crm.related["additionalMentors"] = [
        {"id": "mpC", "name": "New Mentor", "cbmEmail": "", "contactRecordId": "c8"},
    ]
    _wire(monkeypatch, cal)
    await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), ["c1", "c8"],
        owner_user_id="u1", settings=SETTINGS_ON)
    (_eid, body, _send), = cal.patched
    assert body == {"attendees": [{"email": "pat@x.com"}]}


async def test_acting_user_classified_even_when_not_record_manager(monkeypatch):
    """The acting organizer's own profile is always classified — if their
    Contact reached the record as a plain CLIENT contact (no mentorProfile /
    co-mentor link on the engagement), the self-invitation is still
    suppressed."""
    crm, cal = _fake_crm(
        attendee_rows=[
            {"id": "c1", "name": "Pat Koran", "emailAddress": "pat@x.com"},
            {"id": "c9", "name": "Mgr Self", "emailAddress": "mgr.personal@gmail.com"},
        ],
    ), FakeCalendar()
    # E1 keeps its default record (NO mentorProfileId); mp1 is only reachable
    # as the acting user's own profile (crm.mentors links it to u1).
    crm.records[("CMentorProfile", "mp1")] = {
        "cbmEmail": " Mgr@CBMentors.org ", "contactRecordId": "c9",
    }
    _wire(monkeypatch, cal)
    await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES), ["c1", "c9"],
        owner_user_id="u1", settings=SETTINGS_ON)
    (_eid, body, _send), = cal.patched
    assert body == {"attendees": [{"email": "pat@x.com"}]}


async def test_update_patch_substitutes_member_emails(monkeypatch):
    """The update path has no parent id in hand — the hook reads it off the
    session record and still classifies CBM members on the re-patch."""
    crm, cal = _fake_crm(
        attendee_rows=[
            {"id": "c1", "name": "Pat Koran", "emailAddress": "pat@x.com"},
            {"id": "c9", "name": "Mgr Self", "emailAddress": "mgr.personal@gmail.com"},
        ],
    ), FakeCalendar()
    crm.records[("CEngagement", "E1")] = {
        "name": "Agape W8 Loss", "mentorProfileId": "mp1",
    }
    crm.records[("CMentorProfile", "mp1")] = {
        "cbmEmail": " Mgr@CBMentors.org ", "contactRecordId": "c9",
    }
    _seed_session(crm, googleCalendarEventId="ev1", engagementId="E1")
    _wire(monkeypatch, cal)
    await service.update_session(
        MENTOR, crm, "s1", {"dateStart": "2026-07-21 18:00:00"},
        user_id="u1", settings=SETTINGS_ON)
    (_eid, body, _send), = cal.patched
    # Without the substitution, mgr.personal@gmail.com would be re-invited here.
    assert body["attendees"] == [{"email": "pat@x.com"}]


# --- cancel -------------------------------------------------------------------

async def test_cancel_deletes_event_and_clears_meet_link(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _seed_session(crm, googleCalendarEventId="ev1", videoMeetingLink=MEET)
    _wire(monkeypatch, cal)
    session = await service.update_session(
        MENTOR, crm, "s1", {"status": "Cancelled"}, user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"] == {"ok": True, "cancelled": True}
    assert cal.deleted == [("ev1", "all")]  # real cancellation emails attendees
    assert session["googleCalendarEventId"] is None
    assert session["videoMeetingLink"] is None


async def test_cancel_keeps_hand_typed_link(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    zoom = "https://zoom.us/j/123"
    _seed_session(crm, googleCalendarEventId="ev1", videoMeetingLink=zoom)
    _wire(monkeypatch, cal)
    session = await service.update_session(
        MENTOR, crm, "s1", {"status": "Cancelled"}, user_id="u1", settings=SETTINGS_ON)
    assert cal.deleted == [("ev1", "all")]
    assert session["videoMeetingLink"] == zoom
    assert session["googleCalendarEventId"] is None


async def test_cancel_without_event_skips(monkeypatch):
    crm, cal = _fake_crm(), FakeCalendar()
    _seed_session(crm)
    _wire(monkeypatch, cal)
    session = await service.update_session(
        MENTOR, crm, "s1", {"status": "Cancelled"}, user_id="u1", settings=SETTINGS_ON)
    assert session["calendar"] == {"ok": True, "skipped": True}
    assert cal.deleted == []


# --- Meet auto-transcription (MEET_TRANSCRIPTS) -------------------------------

SETTINGS_TRANSCRIPTS = types.SimpleNamespace(
    gcal_events=True, meet_transcripts=True, request_timeout_seconds=5)


class FakeMeet:
    def __init__(self, fail=False):
        self.enabled, self.fail = [], fail

    async def get_space(self, code):
        if self.fail:
            raise RuntimeError("meet api down")
        return {"name": "spaces/xyz123", "meetingCode": code}

    async def enable_auto_transcription(self, space_name):
        self.enabled.append(space_name)


def _wire_meet(monkeypatch, fake):
    monkeypatch.setattr(gcal, "MeetClient", lambda sa, mailbox, timeout=20: fake)


async def test_create_enables_meet_transcription(monkeypatch):
    crm, cal, meet = _fake_crm(), FakeCalendar(), FakeMeet()
    _wire(monkeypatch, cal)
    _wire_meet(monkeypatch, meet)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES),
        owner_user_id="u1", settings=SETTINGS_TRANSCRIPTS)
    assert session["calendar"]["transcription"] == {"ok": True, "enabled": True}
    assert meet.enabled == ["spaces/xyz123"]


async def test_transcription_flag_off_no_meet_call(monkeypatch):
    crm, cal, meet = _fake_crm(), FakeCalendar(), FakeMeet()
    _wire(monkeypatch, cal)
    _wire_meet(monkeypatch, meet)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES),
        owner_user_id="u1", settings=SETTINGS_ON)
    assert "transcription" not in session["calendar"]
    assert meet.enabled == []


async def test_transcription_failure_never_fails_event(monkeypatch):
    """Best-effort: a Meet API failure means the meeting simply isn't
    auto-transcribed — the event + link write-back stand."""
    crm, cal, meet = _fake_crm(), FakeCalendar(), FakeMeet(fail=True)
    _wire(monkeypatch, cal)
    _wire_meet(monkeypatch, meet)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES),
        owner_user_id="u1", settings=SETTINGS_TRANSCRIPTS)
    assert session["calendar"]["ok"] is True
    assert session["calendar"]["eventId"] == "ev1"
    assert session["calendar"]["transcription"]["ok"] is False
    assert "meet api down" in session["calendar"]["transcription"]["error"]


async def test_hand_typed_link_never_configures_transcription(monkeypatch):
    crm, cal, meet = _fake_crm(), FakeCalendar(), FakeMeet()
    _wire(monkeypatch, cal)
    _wire_meet(monkeypatch, meet)
    session = await service.create_session(
        MENTOR, crm, "E1", dict(NEW_CHANGES, videoMeetingLink="https://zoom.us/j/123"),
        owner_user_id="u1", settings=SETTINGS_TRANSCRIPTS)
    assert "transcription" not in session["calendar"]
    assert meet.enabled == []
