"""Near-duplicate hold (2026-07-27).

Driven by two real production incidents in which a client re-filled the whole
intake form a couple of minutes after submitting it — once to name the mentor
they wanted, once to reword their request. Each produced a second
CClientProfile + CEngagement, and because ``CClientProfile.linkedCompany`` is a
hasOne link, the second profile silently stripped the company and contact off
the first one.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from core import store as store_mod
from core.app import create_app
from core.receipts import R_HELD_DUPLICATE, R_RECEIVED, intake_message, receipt_status
from forms import client_intake

from test_store_wiring import FakeStore


def _body(**over):
    body = {
        "submission_token": "tok-dup-1",
        "first_name": "Valerie",
        "last_name": "Polunas",
        "email": "vpolunas@example.com",
        "confirm_email": "vpolunas@example.com",
        "phone": "2165551234",
        "zip_code": "44139",
        "mentoring_focus_areas": ["Business Strategy & Planning"],
        "mentoring_needs_description": "Help with financial management.",
        "business_stage": "Early Stage",
        "business_name": "Flowing River",
        "terms_accepted": True,
    }
    body.update(over)
    return body


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def client(store):
    with TestClient(create_app([client_intake.SPEC], store=store)) as c:
        yield c


def test_first_submission_is_not_held(client, store):
    """No prior submission => ordinary delivery, exactly as before."""
    r = client.post("/api/client-intake/intake", json=_body())
    assert r.status_code == 200
    assert store.captures[0][2] == store_mod.STATUS_PENDING


def test_second_submission_within_window_is_held(client, store):
    """A different token (a fresh form session) from the same email is CAPTURED
    but held — never delivered, so no duplicate CRM records."""
    store.duplicate = {"id": "sub-earlier", "received_at": None}
    r = client.post("/api/client-intake/intake", json=_body(submission_token="tok-dup-2"))

    assert r.status_code == 200
    body = r.json()
    # The visitor is acknowledged normally: from their side nothing is wrong.
    assert body["status"] == "received"
    assert body["reference"]
    assert store.captures[0][2] == store_mod.STATUS_HELD_DUPLICATE
    # ...and the row records WHICH submission it appears to duplicate.
    row = next(iter(store.rows.values()))
    assert row["duplicate_of"] == "sub-earlier"


def test_held_duplicate_is_not_delivered(client, store):
    """The whole point: the orchestrator must not run."""
    store.duplicate = {"id": "sub-earlier"}
    client.post("/api/client-intake/intake", json=_body(submission_token="tok-dup-3"))
    assert store.completed == []


def test_honeypot_beats_duplicate(client, store):
    """A spam hit stays spam — it must not be re-labelled as a duplicate."""
    store.duplicate = {"id": "sub-earlier"}
    client.post(
        "/api/client-intake/intake",
        json=_body(submission_token="tok-dup-4", company_url="http://spam.example"),
    )
    assert store.captures[0][2] == store_mod.STATUS_HELD


def test_duplicate_check_failure_delivers_anyway(client, store, caplog):
    """Fail OPEN. This guard saves staff cleanup; it must never cost a lead."""

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    store.find_recent_duplicate = boom
    with caplog.at_level(logging.WARNING):
        r = client.post("/api/client-intake/intake", json=_body(submission_token="tok-dup-5"))

    assert r.status_code == 200
    assert store.captures[0][2] == store_mod.STATUS_PENDING
    assert "duplicate check failed" in caplog.text


def test_window_of_zero_disables_the_check(store, monkeypatch):
    """The escape hatch: DUPLICATE_HOLD_SECONDS=0 restores the old behavior."""
    monkeypatch.setenv("DUPLICATE_HOLD_SECONDS", "0")
    from core.config import get_settings

    get_settings.cache_clear()
    try:
        with TestClient(create_app([client_intake.SPEC], store=store)) as c:
            store.duplicate = {"id": "sub-earlier"}
            c.post("/api/client-intake/intake", json=_body(submission_token="tok-dup-6"))
        assert store.captures[0][2] == store_mod.STATUS_PENDING
    finally:
        get_settings.cache_clear()


# --- the receipt side -------------------------------------------------------


def test_receipt_status_maps_the_new_hold():
    assert receipt_status(store_mod.STATUS_HELD_DUPLICATE) == R_HELD_DUPLICATE


def test_receipt_message_explains_the_decision():
    msg = intake_message(
        {"status": store_mod.STATUS_HELD_DUPLICATE, "duplicate_of": "sub-earlier"}
    )
    assert "Possible duplicate" in msg
    # The reviewer is told what each action does, and can find the original.
    assert "Approve" in msg and "Discard" in msg
    assert "sub-earlier" in msg


@pytest.mark.anyio
async def test_receipt_falls_back_until_the_crm_enum_exists():
    """The app may deploy before the CRM gains the Held-Duplicate option; an
    out-of-enum value would make EspoCRM reject the whole receipt write."""
    from core import receipts

    class OldCrm:
        async def metadata_enum_options(self, entity, field):
            return ["Received", "Completed", "Held-Spam", "Held-Email", "Error", "Discarded"]

    receipts._status_options_cache["options"] = None
    try:
        gated = await receipts._gate_status(OldCrm(), {"intakeStatus": R_HELD_DUPLICATE})
        assert gated["intakeStatus"] == R_RECEIVED
    finally:
        receipts._status_options_cache["options"] = None


@pytest.mark.anyio
async def test_receipt_uses_the_real_word_once_the_crm_has_it():
    from core import receipts

    class NewCrm:
        async def metadata_enum_options(self, entity, field):
            return ["Received", "Held-Duplicate", "Discarded"]

    receipts._status_options_cache["options"] = None
    try:
        gated = await receipts._gate_status(NewCrm(), {"intakeStatus": R_HELD_DUPLICATE})
        assert gated["intakeStatus"] == R_HELD_DUPLICATE
    finally:
        receipts._status_options_cache["options"] = None


@pytest.mark.anyio
async def test_receipt_gate_fails_open_when_metadata_unreadable():
    from core import receipts

    class BrokenCrm:
        async def metadata_enum_options(self, entity, field):
            raise RuntimeError("no metadata")

    receipts._status_options_cache["options"] = None
    try:
        gated = await receipts._gate_status(BrokenCrm(), {"intakeStatus": R_HELD_DUPLICATE})
        assert gated["intakeStatus"] == R_HELD_DUPLICATE
    finally:
        receipts._status_options_cache["options"] = None


def test_held_duplicate_is_redrivable_and_counts_as_open_work():
    """Approve in Submission Admin = redrive, so the guard must allow it, and
    the row must appear in the work queue rather than sitting invisible."""
    assert store_mod.STATUS_HELD_DUPLICATE in store_mod.OPEN_REVIEW_STATUSES
    # Never claimed by the worker while held.
    assert store_mod.STATUS_HELD_DUPLICATE not in store_mod.CLAIMABLE


# --- scoped per event (2026-09-13) -------------------------------------------


def _event_body(**over):
    body = {
        "submission_token": "tok-ev-1",
        "company_url": "",
        "first_name": "Bea",
        "last_name": "Nolan",
        "email": "bea@example.com",
        "phone": "",
        "zip_code": "",
        "consent": True,
        "event_slug": "grant-writing-basics",
    }
    body.update(over)
    return body


def test_event_registration_matches_on_the_event_as_well(monkeypatch):
    """The live defect (OPEN-ITEMS 19f): the guard matched form + email inside
    24 hours, so a person's SECOND webinar of the day was captured and held for
    staff review — never delivered, no registration created, and they saw a
    normal thank-you. The event now joins the match.

    Driven through the real public endpoint rather than the helper, because the
    value has to survive the URL, the pre-flight check and the schema before it
    can reach the guard at all."""
    from core.config import get_settings
    from forms import event_registration
    from tests.test_events_public import FakeEspo
    from tests.test_events_service import make_event

    store = FakeStore()
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("EVENTS_ENABLED", "true")
    monkeypatch.setenv("EVENTS_PUBLIC_API", "true")
    monkeypatch.setenv("ESPO_DRY_RUN", "false")
    monkeypatch.setenv("ESPO_BASE_URL", "https://crm.example.test")
    monkeypatch.setenv("ESPO_API_KEY", "k")
    monkeypatch.setattr(store_mod, "make_store", lambda *a, **k: store)
    get_settings.cache_clear()
    app = create_app([event_registration.SPEC])
    # The fixture event is fixed in the past, and the endpoint's pre-flight check
    # refuses a closed registration before capture ever runs. Build its date from
    # today so this test does not rot the way the full-event one did.
    from datetime import datetime, timedelta, timezone

    soon = datetime.now(timezone.utc) + timedelta(days=30)
    upcoming = make_event(
        dateStart=soon.strftime("%Y-%m-%d %H:%M:%S"),
        dateEnd=(soon + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    app.state.events_client_factory = lambda: FakeEspo(events=[upcoming])
    client = TestClient(app)

    resp = client.post(
        "/api/events/grant-writing-basics/register",
        json=_event_body(event_slug="grant-writing-basics"),
    )
    # 200 on capture, or 502 when the fake CRM cannot complete the delivery it
    # only knows how to LIST for. Either way the submission was captured, which
    # is the point — a 404 would mean the route never mounted and a 409 that the
    # pre-flight refused before the guard could run.
    assert resp.status_code in (200, 502), resp.text
    assert store.duplicate_calls, "no duplicate check ran at all"
    call = store.duplicate_calls[-1]
    assert call["scope_key"] == "event_slug"
    assert call["scope_value"] == "grant-writing-basics"
    get_settings.cache_clear()


def test_client_intake_still_matches_on_form_and_email_alone(monkeypatch):
    """Unchanged, and it must stay that way: re-filling that form is one person
    editing one application, and holding the second is what stopped a second
    client profile stripping the company off the first."""
    store = FakeStore()
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(store_mod, "make_store", lambda *a, **k: store)
    client = TestClient(create_app([client_intake.SPEC]))

    client.post("/api/client-intake/intake", json=_body())
    assert store.duplicate_calls
    call = store.duplicate_calls[-1]
    assert call["scope_key"] is None
    assert call["scope_value"] is None
