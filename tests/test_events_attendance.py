"""Phase 6a — attendance from the Zoom participant report.

The rules with teeth: an empty report must never be read as "nobody came", a
human correction must survive every later pull, and an attendee who matches no
registration must be recorded rather than dropped.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.config import Settings
from events import attendance, config as cfg
from tests.test_events_service import make_event


def _reg(rid, email, **over):
    row = {
        "id": rid, "email": email, "firstName": "A", "lastName": "B",
        "attendanceStatus": cfg.REG_REGISTERED, "attendanceSource": None,
    }
    row.update(over)
    return row


def _part(email, name="Someone", join="2026-08-20T16:00:00Z",
          leave="2026-08-20T17:00:00Z", duration=3600):
    return {"user_email": email, "name": name, "join_time": join,
            "leave_time": leave, "duration": duration}


class FakeCrm:
    def __init__(self, registrations=None):
        self.registrations = registrations or []
        self.updates = []
        self.creates = []

    async def update(self, entity, rid, payload):
        self.updates.append((rid, payload))
        return {"id": rid}

    async def create(self, entity, payload):
        self.creates.append(payload)
        return {"id": "new"}


class FakeZoom:
    def __init__(self, participants):
        self.participants = participants
        self.calls = 0

    async def list_participants(self, webinar_id):
        self.calls += 1
        return self.participants


# --- matching ----------------------------------------------------------------

def test_matching_is_by_email_case_insensitively():
    regs = [_reg("r1", "Ada@Example.org")]
    matched, unmatched = attendance.match_participants(regs, [_part("ada@example.org")])
    assert list(matched) == ["r1"]
    assert unmatched == []


def test_rejoins_fold_into_earliest_join_latest_leave_and_summed_minutes():
    regs = [_reg("r1", "ada@example.org")]
    parts = [
        _part("ada@example.org", join="2026-08-20T16:00:00Z",
              leave="2026-08-20T16:20:00Z", duration=1200),
        _part("ada@example.org", join="2026-08-20T16:30:00Z",
              leave="2026-08-20T17:00:00Z", duration=1800),
    ]
    matched, _ = attendance.match_participants(regs, parts)
    facts = matched["r1"]
    assert facts["join"].hour == 16 and facts["join"].minute == 0
    assert facts["leave"].hour == 17
    assert facts["seconds"] == 3000


def test_an_attendee_with_no_registration_is_unmatched_not_dropped():
    matched, unmatched = attendance.match_participants([], [_part("gate@crasher.org")])
    assert matched == {}
    assert unmatched[0]["email"] == "gate@crasher.org"


# --- applying ----------------------------------------------------------------

async def test_attended_and_no_show_are_written():
    regs = [_reg("r1", "there@example.org"), _reg("r2", "absent@example.org")]
    crm = FakeCrm()
    summary = await attendance.apply_attendance(
        crm, make_event(), regs, [_part("there@example.org")]
    )
    assert summary["attended"] == 1 and summary["noShow"] == 1
    by_id = dict(crm.updates)
    assert by_id["r1"]["attendanceStatus"] == cfg.REG_ATTENDED
    assert by_id["r1"]["minutesAttended"] == 60
    assert by_id["r1"]["attendanceSource"] == attendance.SOURCE_ZOOM
    assert by_id["r2"]["attendanceStatus"] == cfg.REG_NO_SHOW


@pytest.mark.parametrize("source", ["Manual", "Check-in"])
async def test_a_human_correction_is_never_overwritten(source):
    """EV-34. Staff win over the machine, every time."""
    regs = [_reg("r1", "there@example.org", attendanceSource=source,
                 attendanceStatus=cfg.REG_ATTENDED)]
    crm = FakeCrm()
    summary = await attendance.apply_attendance(crm, make_event(), regs, [])
    assert crm.updates == []
    assert summary["skippedManual"] == 1


async def test_a_cancelled_registration_is_not_marked_no_show():
    regs = [_reg("r1", "gone@example.org", attendanceStatus=cfg.REG_CANCELLED)]
    crm = FakeCrm()
    await attendance.apply_attendance(crm, make_event(), regs, [])
    assert crm.updates == []


async def test_unmatched_participants_are_recorded_for_review():
    crm = FakeCrm()
    summary = await attendance.apply_attendance(
        crm, make_event(), [], [_part("gate@crasher.org", name="Gate Crasher")]
    )
    assert summary["unmatched"] == 1
    created = crm.creates[0]
    assert created["unmatchedParticipant"] is True
    assert created["attendanceStatus"] == cfg.REG_ATTENDED
    assert created["registrationSource"] == cfg.SOURCE_IMPORT
    assert created["firstName"] == "Gate" and created["lastName"] == "Crasher"
    # No Contact is invented — staff decide who this person is.
    assert "contactId" not in created


# --- the pull ----------------------------------------------------------------

async def test_an_empty_report_leaves_the_event_unresolved(monkeypatch):
    """EV-31: empty means 'Zoom hasn't published it yet', NOT 'nobody came'.
    Reading it as zero attendance would mark a whole roster No-Show."""
    crm = FakeCrm()
    monkeypatch.setattr(
        attendance.service, "list_registrations",
        lambda c, eid: _async([_reg("r1", "a@b.org")]),
    )
    result = await attendance.resolve_event(
        crm, FakeZoom([]), {"id": "ev1", "zoomWebinarId": "w1", "name": "X"}
    )
    assert result is None
    assert crm.updates == []       # nothing written


async def test_an_already_resolved_event_is_not_pulled_again(monkeypatch):
    zoom = FakeZoom([_part("a@b.org")])
    monkeypatch.setattr(
        attendance.service, "list_registrations",
        lambda c, eid: _async([_reg("r1", "a@b.org",
                                    attendanceSource=attendance.SOURCE_ZOOM)]),
    )
    result = await attendance.resolve_event(
        FakeCrm(), zoom, {"id": "ev1", "zoomWebinarId": "w1", "name": "X"}
    )
    assert result is None
    assert zoom.calls == 0         # never even asked Zoom


def _async(value):
    async def run():
        return value
    return run()


# --- candidates + the cycle ---------------------------------------------------

def test_candidate_window_is_bounded_at_both_ends():
    s = Settings()
    assert s.events_attendance_grace_minutes > 0
    assert s.events_attendance_give_up_hours > 0


async def test_cycle_is_inert_without_zoom(monkeypatch):
    """Zoom off => nothing to pull, and no CRM traffic at all."""
    monkeypatch.setenv("EVENTS_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ESPO_DRY_RUN", "false")
    from core.config import get_settings

    get_settings.cache_clear()
    totals = await attendance.run_attendance_cycle(get_settings(), zoom=None)
    get_settings.cache_clear()
    assert totals["events"] == 0
