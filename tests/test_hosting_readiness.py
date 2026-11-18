"""The Event hosting card and the worker's switches on Feature readiness
(prds/events/event-hosting-plan.md § 8, items 1 and 2; ruling R1).

Each test is a failure the step 6 live check met on the Business Mentors
Association's system (11-17/18-26), read before anyone registers.
"""

from __future__ import annotations

import pytest

from core import worker_switches
from core.config import Settings, get_settings
from events import readiness as hosting_readiness
from setup import readiness as setup_readiness


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- item 1: the worker's switches ---------------------------------------------


def test_the_snapshot_reports_booleans_never_the_mailbox():
    s = Settings(events_enabled=True, ops_mailbox="info@example.org",
                 events_attendance_seconds=0)
    snap = worker_switches.snapshot(s)
    assert snap["events_enabled"] is True
    assert snap["ops_mailbox"] is True          # set, not the address
    assert snap["events_attendance"] is False
    assert "info@example.org" not in str(snap)


def test_a_switch_on_for_the_web_part_and_off_for_the_worker_is_named():
    web = Settings(events_enabled=True, gmail_sync=True)
    worker = {**worker_switches.snapshot(web), "events_enabled": False}
    [row] = worker_switches.mismatches(web, worker)
    assert worker_switches.words(row) == (
        "Events & Webinars is on for the web part and off for the worker.")


def test_no_report_or_an_older_worker_names_nothing():
    web = Settings(events_enabled=True)
    assert worker_switches.mismatches(web, None) == []
    # An older worker reports no events_enabled key: nothing is claimed about it.
    assert worker_switches.mismatches(web, {"gmail_sync": False}) == []


# --- item 2: the checks ---------------------------------------------------------------


def _switches(**over):
    base = {"events_enabled": True, "events_confirmations": True, "gmail_sync": True,
            "ops_mailbox": True, "espo_dry_run": False}
    base.update(over)
    return {"switches": base}


def test_the_worker_without_events_is_not_ready():
    """The Association's worker, 11-18-26."""
    rows = hosting_readiness.worker_rows(_switches(events_enabled=False))
    assert rows[0]["ok"] is False and "EVENTS_ENABLED" in rows[0]["detail"]


def test_the_confirmation_names_what_the_worker_lacks():
    rows = hosting_readiness.worker_rows(_switches(events_confirmations=False, ops_mailbox=False))
    detail = rows[1]["detail"]
    assert rows[1]["ok"] is False
    assert "Registration confirmation emails" in detail and "the shared mailbox" in detail


def test_a_worker_that_has_not_reported_is_unknown():
    rows = hosting_readiness.worker_rows(None)
    assert [r["ok"] for r in rows] == [None, None]


def test_a_ready_worker():
    assert [r["ok"] for r in hosting_readiness.worker_rows(_switches())] == [True, True]


class Crm:
    def __init__(self, templates=(), methods=None, sources=None, fail=False):
        self.templates = templates
        self.methods = methods
        self.sources = sources
        self.fail = fail

    async def list(self, entity, **kw):
        if self.fail:
            raise RuntimeError("down")
        assert entity == "EmailTemplate"
        return {"list": [{"name": n} for n in self.templates]}

    async def metadata_enum_options(self, entity, field):
        if self.fail:
            raise RuntimeError("down")
        return self.methods if field == "hostedBy" else self.sources


async def test_missing_templates_are_named():
    """The Association had none of the eight, 11-18-26."""
    row = await hosting_readiness.template_row(Crm(templates=("EventConfirmation",)))
    assert row["ok"] is False and row["detail"].startswith("7 of 8 missing")
    assert "scripts/seed_templates.sh" in row["detail"]
    ok = await hosting_readiness.template_row(Crm(templates=hosting_readiness.TEMPLATE_NAMES))
    assert ok["ok"] is True
    assert (await hosting_readiness.template_row(Crm(fail=True)))["ok"] is None
    assert (await hosting_readiness.template_row(None))["ok"] is None


async def test_the_crm_options():
    rows = await hosting_readiness.option_rows(
        Crm(methods=["CBM Zoom", "Outside host"], sources=["Online"]))
    assert rows[0]["ok"] is False and "Zoom Meetings or Other platform" in rows[0]["detail"]
    assert rows[1]["ok"] is False and "Portal" in rows[1]["detail"]
    rows = await hosting_readiness.option_rows(Crm(
        methods=["CBM Zoom", "Outside host", "Zoom Meetings", "Other platform"],
        sources=["Online", "Portal"]))
    assert [r["ok"] for r in rows] == [True, True]
    assert "Zoom Webinars" in rows[0]["detail"]          # labels, never the stored value
    rows = await hosting_readiness.option_rows(Crm(methods=None, sources=["Portal"]))
    assert rows[0]["ok"] is False and "no Hosted by field" in rows[0]["detail"]


class Zoom:
    def __init__(self, in_meeting=None, fail=False):
        self.in_meeting = in_meeting or {}
        self.fail = fail

    async def get_user_settings(self, user):
        if self.fail:
            raise RuntimeError("down")
        return {"in_meeting": self.in_meeting}


class ZoomOn:
    zoom_meetings_events = True
    zoom_meetings_account_id = zoom_meetings_client_id = zoom_meetings_client_secret = "x"
    zoom_event_host_email = "events@example.org"


async def _zoom_rows(**in_meeting):
    rows = await hosting_readiness.zoom_rows(ZoomOn(), Zoom(in_meeting))
    return {r["label"]: r for r in rows}


async def test_any_attendee_can_share_is_not_ready():
    """The Association's host user, 11-18-26: an attendee could share."""
    rows = await _zoom_rows(screen_sharing=True, who_can_share_screen="all", co_host=True)
    assert rows["Screen sharing"]["ok"] is False
    assert "any attendee can share" in rows["Screen sharing"]["detail"]
    assert rows["Co-host"]["ok"] is True


async def test_host_only_sharing_and_co_host_are_ready():
    rows = await _zoom_rows(screen_sharing=True, who_can_share_screen="host", co_host=True)
    assert rows["Screen sharing"]["ok"] is True and rows["Co-host"]["ok"] is True


async def test_an_unrecognised_sharing_value_is_unknown_never_ready():
    rows = await _zoom_rows(screen_sharing=True, who_can_share_screen="internal", co_host=False)
    assert rows["Screen sharing"]["ok"] is None
    assert rows["Co-host"]["ok"] is False


async def test_sharing_off_altogether_is_not_ready():
    rows = await _zoom_rows(screen_sharing=False, co_host=True)
    assert rows["Screen sharing"]["ok"] is False


async def test_zoom_meetings_off_is_not_checked_and_unreadable_is_unknown():
    class Off:
        zoom_meetings_events = False
    [row] = await hosting_readiness.zoom_rows(Off())
    assert row["ok"] is None
    [row] = await hosting_readiness.zoom_rows(ZoomOn(), Zoom(fail=True))
    assert row["ok"] is None and "events@example.org" in row["detail"]


# --- the card on Feature readiness ------------------------------------------------------


class Store:
    def __init__(self, switches):
        self.switches = switches

    async def metrics(self):
        return {"workerHeartbeatAgeSeconds": 5}

    async def worker_report(self):
        return {"beatAt": None, "ageSeconds": 5, "switches": self.switches}


async def _none(settings):
    return None


async def test_the_card_comes_first_and_the_worker_mismatch_is_shown(monkeypatch):
    monkeypatch.setattr(setup_readiness, "_crm_snapshot", _none)
    settings = Settings(events_enabled=True, gmail_sync=True, ops_mailbox="info@example.org",
                        events_confirmations=True)
    worker = {**worker_switches.snapshot(settings), "events_enabled": False}
    payload = await setup_readiness.readiness_payload(settings, Store(worker), None)
    card = payload["features"][0]
    assert card["key"] == "event_hosting" and card["status"] == "blocked"
    assert card["checks"][0]["ok"] is False
    events = next(f for f in payload["features"] if f["key"] == "events")
    assert any(c["kind"] == "worker" and "off for the worker" in c["detail"]
               for c in events["checks"])
    assert payload["workerSwitchMismatches"] == [
        "Events & Webinars is on for the web part and off for the worker."]


async def test_with_events_off_the_card_reads_off(monkeypatch):
    monkeypatch.setattr(setup_readiness, "_crm_snapshot", _none)
    payload = await setup_readiness.readiness_payload(Settings(events_enabled=False), None, None)
    assert payload["features"][0]["status"] == "off"
