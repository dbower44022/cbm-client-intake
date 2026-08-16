"""Phase 6c — event reporting (EV-71…EV-74).

The judgement calls are what these guard: the engagement rollup deduplicates by
EVENT (three colleagues at one webinar is one row), and conversion requires the
engagement to postdate the first attended event.
"""

from __future__ import annotations

import pytest

from events import config as cfg
from events import reporting
from tests.test_events_service import make_event


class FakeCrm:
    def __init__(self, events=None, registrations=None, engagements=None):
        self.data = {
            cfg.EVENT: events or [],
            cfg.REGISTRATION: registrations or [],
            "CEngagement": engagements or [],
        }

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        rows = list(self.data.get(entity, []))
        for clause in where or []:
            attr, kind, val = clause.get("attribute"), clause.get("type"), clause.get("value")
            if kind == "in":
                rows = [r for r in rows if r.get(attr) in set(val)]
            elif kind == "equals":
                rows = [r for r in rows if r.get(attr) == val]
        return {"total": len(rows), "list": rows[offset:offset + max_size]}


def _reg(rid, event_id, contact_id=None, status=cfg.REG_ATTENDED, **over):
    row = {"id": rid, "eventId": event_id, "contactId": contact_id,
           "attendanceStatus": status, "email": over.pop("email", None),
           "firstName": "", "lastName": ""}
    row.update(over)
    return row


# --- EV-71 -------------------------------------------------------------------

async def test_contact_history_is_newest_first_with_status():
    events = [
        make_event(id="e1", name="Older", dateStart="2026-01-10 16:00:00", slug="older"),
        make_event(id="e2", name="Newer", dateStart="2026-06-10 16:00:00", slug="newer"),
    ]
    regs = [_reg("r1", "e1", "c1"), _reg("r2", "e2", "c1", status=cfg.REG_NO_SHOW)]
    out = await reporting.contact_history(FakeCrm(events, regs), "c1")
    assert [r["title"] for r in out] == ["Newer", "Older"]
    assert out[0]["attended"] is False and out[1]["attended"] is True


async def test_contact_history_is_empty_without_a_contact():
    assert await reporting.contact_history(FakeCrm(), "") == []


# --- EV-72 (Doug's explicit requirement) -------------------------------------

async def test_rollup_deduplicates_by_event_and_names_who_attended():
    """Three colleagues at one webinar is ONE row — the question is whether the
    CLIENT engaged, not how many seats were filled."""
    events = [make_event(id="e1", name="Grant Writing", dateStart="2026-05-01 16:00:00")]
    regs = [_reg("r1", "e1", "c1"), _reg("r2", "e1", "c2"), _reg("r3", "e1", "c3")]
    contacts = [{"id": "c1", "name": "Ann"}, {"id": "c2", "name": "Bob"},
                {"id": "c3", "name": "Cy"}]
    out = await reporting.engagement_rollup(FakeCrm(events, regs), contacts)
    assert len(out) == 1
    assert sorted(out[0]["attendees"]) == ["Ann", "Bob", "Cy"]


async def test_rollup_counts_only_actual_attendance():
    events = [make_event(id="e1", dateStart="2026-05-01 16:00:00")]
    regs = [_reg("r1", "e1", "c1", status=cfg.REG_NO_SHOW),
            _reg("r2", "e1", "c2", status=cfg.REG_REGISTERED)]
    contacts = [{"id": "c1", "name": "Ann"}, {"id": "c2", "name": "Bob"}]
    assert await reporting.engagement_rollup(FakeCrm(events, regs), contacts) == []


async def test_rollup_is_empty_for_an_engagement_with_no_contacts():
    assert await reporting.engagement_rollup(FakeCrm(), []) == []


# --- EV-74 -------------------------------------------------------------------

async def test_program_totals_repeat_rate():
    events = [
        make_event(id="e1", dateStart="2026-03-01 16:00:00"),
        make_event(id="e2", dateStart="2026-04-01 16:00:00"),
    ]
    regs = [_reg("r1", "e1", "c1"), _reg("r2", "e2", "c1"), _reg("r3", "e1", "c2")]
    out = await reporting.program_totals(FakeCrm(events, regs), start="2026-01-01",
                                         end="2026-12-31")
    assert out["eventsHeld"] == 2
    assert out["uniqueAttendees"] == 2      # c1 and c2
    assert out["repeatAttendees"] == 1      # c1 came twice
    assert out["repeatRate"] == 0.5
    assert out["totalAttendances"] == 3


async def test_program_totals_excludes_cancelled_events_and_other_periods():
    events = [
        make_event(id="e1", dateStart="2026-03-01 16:00:00", status=cfg.STATUS_CANCELLED),
        make_event(id="e2", dateStart="2025-03-01 16:00:00"),
    ]
    out = await reporting.program_totals(FakeCrm(events, []), start="2026-01-01",
                                         end="2026-12-31")
    assert out["eventsHeld"] == 0


async def test_an_unmatched_attendee_still_counts_as_a_person():
    events = [make_event(id="e1", dateStart="2026-03-01 16:00:00")]
    regs = [_reg("r1", "e1", None, email="Gate@Crasher.org")]
    out = await reporting.program_totals(FakeCrm(events, regs), start="2026-01-01",
                                         end="2026-12-31")
    assert out["uniqueAttendees"] == 1


# --- EV-73 -------------------------------------------------------------------

async def test_conversion_requires_the_engagement_to_postdate_the_event():
    """A client who happens to attend a webinar is NOT a conversion; counting
    them would flatter the programme."""
    events = [make_event(id="e1", dateStart="2026-03-01 16:00:00")]
    regs = [_reg("r1", "e1", "c1"), _reg("r2", "e1", "c2")]
    engagements = [
        # c1 became a client AFTER attending — a conversion.
        {"id": "g1", "name": "New Co", "contactId": "c1", "createdAt": "2026-04-01 10:00:00"},
        # c2 was already a client BEFORE the event — not a conversion.
        {"id": "g2", "name": "Old Co", "contactId": "c2", "createdAt": "2025-04-01 10:00:00"},
    ]
    out = await reporting.conversion_report(
        FakeCrm(events, regs, engagements), start="2026-01-01", end="2026-12-31"
    )
    assert out["attendees"] == 2
    assert out["converted"] == 1
    assert out["conversionRate"] == 0.5
    assert out["rows"][0]["engagement"] == "New Co"


async def test_conversion_ignores_attendees_with_no_contact():
    events = [make_event(id="e1", dateStart="2026-03-01 16:00:00")]
    regs = [_reg("r1", "e1", None, email="anon@example.org")]
    out = await reporting.conversion_report(FakeCrm(events, regs), start="2026-01-01",
                                            end="2026-12-31")
    assert out["attendees"] == 0


# --- wiring ------------------------------------------------------------------

def test_the_events_tab_is_mentor_domain_only():
    from sessions.config import DOMAINS

    assert DOMAINS["mentorsessions"].events_tab is True
    assert DOMAINS["partnersessions"].events_tab is False
    assert DOMAINS["sponsorsessions"].events_tab is False


# --- frontend wiring ----------------------------------------------------------


def test_the_events_tab_panel_and_renderer_exist():
    """The endpoint and the advertised tab are useless without something that
    paints them — v0.194.0 shipped the tab with no renderer, so it opened
    empty."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    html = (root / "sessions" / "frontend" / "index.html").read_text()
    js = (root / "sessions" / "frontend" / "app.js").read_text()
    assert 'data-dpanel="events"' in html
    assert 'tab === "events"' in js
    assert "function renderEvents(" in js
    assert "/records/" in js and "/events\"" in js


def test_the_events_reports_view_exists():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    html = (root / "events" / "frontend" / "index.html").read_text()
    js = (root / "events" / "frontend" / "app.js").read_text()
    assert 'id="reportsPanel"' in html
    assert "/reports/program" in js
    assert "/reports/conversion" in js
