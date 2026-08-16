"""Events Phase 3 — public registration into the CRM.

The rules here are the ones that would quietly damage real data: relabelling an
existing client as a Prospect, flipping someone's marketing opt-out back on,
duplicating registrations, handing a join link to a waitlisted person, or losing
a registration because Zoom had a bad minute.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from events import config as cfg
from events import service
from events.tokens import TokenError, make_cancel_token, read_cancel_token
from forms.event_registration.orchestrator import (
    RegistrationRefused,
    check_open,
    deliver,
)
from forms.event_registration import EventRegistration

from tests.test_events_service import make_event


def submission(**over):
    data = {
        "submission_token": "tok-12345678",
        "event_slug": "grant-writing-basics",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "phone": "216-555-1234",
        "zip_code": "44122",
        "consent": True,
    }
    data.update(over)
    return EventRegistration(**data)


class FakeCrm:
    """Enough EspoCRM to exercise the orchestrator, recording every write."""

    def __init__(self, *, events=None, contacts=None, registrations=None):
        # `is None`, not truthiness: passing events=[] must mean "no events",
        # not "give me the default one" — otherwise a test that believes it has
        # an empty CRM quietly has a record in it.
        self.events = list([make_event()] if events is None else events)
        self.contacts = list(contacts or [])
        self.registrations = list(registrations or [])
        self.created: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, str, dict]] = []
        self._seq = 0

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        rows = {cfg.EVENT: self.events, cfg.REGISTRATION: self.registrations}.get(
            entity, [])
        for clause in where or []:
            attr, value = clause.get("attribute"), clause.get("value")
            if clause.get("type") == "equals":
                rows = [r for r in rows if r.get(attr) == value]
        return {"total": len(rows), "list": rows[offset: offset + max_size]}

    async def find_one(self, entity, attr, value, select=None):
        rows = self.contacts if entity == "Contact" else []
        for row in rows:
            if row.get(attr) == value:
                return row
        return None

    async def create(self, entity, payload):
        self._seq += 1
        record = {"id": f"{entity.lower()}-{self._seq}", **payload}
        self.created.append((entity, payload))
        if entity == "Contact":
            self.contacts.append(record)
        elif entity == cfg.REGISTRATION:
            self.registrations.append(record)
        elif entity == cfg.EVENT:
            self.events.append(record)
        return record

    async def update(self, entity, record_id, payload):
        self.updated.append((entity, record_id, payload))
        for row in (self.contacts + self.registrations + self.events):
            if row.get("id") == record_id:
                row.update(payload)
        return {"id": record_id}

    async def get(self, entity, record_id, select=None):
        pool = {cfg.EVENT: self.events, cfg.REGISTRATION: self.registrations}.get(
            entity, [])
        for row in pool:
            if row.get("id") == record_id:
                return row
        return {}


class NoZoom:
    zoom_events = False
    zoom_host_email = ""
    session_secret = "test-secret"


# --- pre-flight refusals (EV-14) ------------------------------------------


async def test_unknown_event_is_refused():
    with pytest.raises(RegistrationRefused, match="could not be found"):
        await check_open(FakeCrm(events=[]), "nope")


async def test_unpublished_event_is_refused():
    crm = FakeCrm(events=[make_event(publishToWebsite=False)])
    with pytest.raises(RegistrationRefused, match="could not be found"):
        await check_open(crm, "grant-writing-basics")


async def test_cancelled_event_is_refused():
    crm = FakeCrm(events=[make_event(status=cfg.STATUS_CANCELLED)])
    with pytest.raises(RegistrationRefused, match="cancelled"):
        await check_open(crm, "grant-writing-basics")


async def test_closed_registration_is_refused_readably():
    crm = FakeCrm(events=[make_event(registrationCloses="2020-01-01 00:00:00")])
    with pytest.raises(RegistrationRefused, match="closed"):
        await check_open(crm, "grant-writing-basics")


async def test_a_full_event_is_NOT_refused():
    """Being full means waitlisted, not turned away (EV-15).

    The date is relative on purpose: registration closes at ``dateStart``, so
    the shared fixture's fixed 2026-07-28 made this test start failing the day
    it passed rather than testing capacity at all.
    """
    upcoming = (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    crm = FakeCrm(events=[make_event(venueCapacity=1, dateStart=upcoming)])
    assert await check_open(crm, "grant-writing-basics")  # no raise


# --- the Contact (D-09, EV-12) --------------------------------------------


async def test_new_registrant_becomes_a_prospect():
    crm = FakeCrm()
    await deliver(submission(), crm, settings=NoZoom())
    entity, payload = crm.created[0]
    assert entity == "Contact"
    assert payload["cContactType"] == ["Prospect"]


async def test_an_existing_contact_is_never_relabelled():
    """A client or mentor who attends a webinar must not become a Prospect."""
    crm = FakeCrm(contacts=[{
        "id": "c1", "emailAddress": "ada@example.com",
        "cContactType": ["Client"], "firstName": "Ada", "lastName": "Lovelace",
    }])
    await deliver(submission(), crm, settings=NoZoom())
    assert not any(e == "Contact" for e, _ in crm.created), "should reuse, not create"
    for entity, _, payload in crm.updated:
        if entity == "Contact":
            assert "cContactType" not in payload, "contact type must not be touched"


async def test_consent_is_recorded_on_a_new_contact():
    crm = FakeCrm()
    await deliver(submission(consent=True), crm, settings=NoZoom())
    _, payload = crm.created[0]
    for field in ("cMarketingOptIn", "cTermsOfUseAccepted",
                  "cPrivacyPolicyAccepted", "cCodeOfConductAccepted"):
        assert payload[field] is True


async def test_without_consent_no_opt_in_field_is_written():
    """A previous opt-OUT must never be flipped by a registration (EV-12)."""
    crm = FakeCrm()
    await deliver(submission(consent=False), crm, settings=NoZoom())
    _, payload = crm.created[0]
    assert "cMarketingOptIn" not in payload
    assert "cTermsOfUseAccepted" not in payload


async def test_zip_and_phone_land_on_the_contact():
    crm = FakeCrm()
    await deliver(submission(), crm, settings=NoZoom())
    _, payload = crm.created[0]
    assert payload["addressPostalCode"] == "44122"
    assert payload["phoneNumber"].startswith("+1")


async def test_an_implausible_phone_is_dropped_not_fatal():
    crm = FakeCrm()
    await deliver(submission(phone="12345"), crm, settings=NoZoom())
    _, payload = crm.created[0]
    assert "phoneNumber" not in payload


# --- the registration record ----------------------------------------------


async def test_registration_is_linked_to_event_and_contact():
    crm = FakeCrm()
    ids = await deliver(submission(), crm, settings=NoZoom())
    registration = [p for e, p in crm.created if e == cfg.REGISTRATION][0]
    assert registration["eventId"] == "ev1"
    assert registration["contactId"] == ids["contactId"]
    assert registration["email"] == "ada@example.com"
    assert registration["attendanceStatus"] == cfg.REG_REGISTERED
    assert registration["registrationSource"] == cfg.SOURCE_ONLINE
    # registrationDate was required AND readOnly until the schema fix - if that
    # regressed, this is where it shows.
    assert registration["registrationDate"]


async def test_repeat_registration_updates_instead_of_duplicating():
    """EV-13: one registration per email per event."""
    crm = FakeCrm(registrations=[{
        "id": "reg1", "eventId": "ev1", "email": "ada@example.com",
        "attendanceStatus": cfg.REG_REGISTERED,
    }])
    ids = await deliver(submission(), crm, settings=NoZoom())
    assert ids["outcome"] == "updated"
    assert ids["eventRegistrationId"] == "reg1"
    assert not [p for e, p in crm.created if e == cfg.REGISTRATION]


async def test_a_cancelled_registrant_can_sign_up_again():
    crm = FakeCrm(registrations=[{
        "id": "reg1", "eventId": "ev1", "email": "ada@example.com",
        "attendanceStatus": cfg.REG_CANCELLED,
    }])
    ids = await deliver(submission(), crm, settings=NoZoom())
    assert ids["registrationStatus"] == cfg.REG_REGISTERED
    update = [p for e, _, p in crm.updated if e == cfg.REGISTRATION][0]
    assert update["attendanceStatus"] == cfg.REG_REGISTERED


async def test_attendance_history_is_not_overwritten_by_a_repeat_submit():
    """Someone who already attended must not be reset to Registered."""
    crm = FakeCrm(registrations=[{
        "id": "reg1", "eventId": "ev1", "email": "ada@example.com",
        "attendanceStatus": cfg.REG_ATTENDED,
    }])
    await deliver(submission(), crm, settings=NoZoom())
    update = [p for e, _, p in crm.updated if e == cfg.REGISTRATION][0]
    assert "attendanceStatus" not in update


# --- capacity and the waitlist (EV-15) ------------------------------------


async def test_over_capacity_registrations_are_waitlisted():
    crm = FakeCrm(
        events=[make_event(venueCapacity=1)],
        registrations=[{"id": "r0", "eventId": "ev1", "email": "x@example.com",
                        "attendanceStatus": cfg.REG_REGISTERED}],
    )
    ids = await deliver(submission(), crm, settings=NoZoom())
    assert ids["registrationStatus"] == cfg.REG_WAITLISTED


async def test_a_waitlisted_person_is_never_pushed_to_zoom():
    """They have no seat — a join link would be a lie."""
    crm = FakeCrm(
        events=[make_event(venueCapacity=1)],
        registrations=[{"id": "r0", "eventId": "ev1", "email": "x@example.com",
                        "attendanceStatus": cfg.REG_REGISTERED}],
    )
    ids = await deliver(submission(), crm, settings=NoZoom())
    assert ids["zoom"]["ok"] is False
    assert ids["zoom"]["reason"] == "waitlisted"


async def test_cancelled_rows_do_not_hold_seats():
    crm = FakeCrm(
        events=[make_event(venueCapacity=1)],
        registrations=[{"id": "r0", "eventId": "ev1", "email": "x@example.com",
                        "attendanceStatus": cfg.REG_CANCELLED}],
    )
    ids = await deliver(submission(), crm, settings=NoZoom())
    assert ids["registrationStatus"] == cfg.REG_REGISTERED


async def test_unlimited_capacity_never_waitlists():
    crm = FakeCrm(
        events=[make_event(venueCapacity=None)],
        registrations=[{"id": f"r{i}", "eventId": "ev1",
                        "email": f"{i}@example.com",
                        "attendanceStatus": cfg.REG_REGISTERED} for i in range(50)],
    )
    ids = await deliver(submission(), crm, settings=NoZoom())
    assert ids["registrationStatus"] == cfg.REG_REGISTERED


# --- Zoom is best-effort ---------------------------------------------------


async def test_zoom_failure_still_leaves_a_complete_registration():
    class BoomZoom:
        zoom_events = True
        zoom_account_id = zoom_client_id = zoom_client_secret = "x"
        zoom_host_email = "h@cbmentors.org"
        zoom_base_url = "https://api.zoom.us/v2"

    crm = FakeCrm(events=[make_event(zoomWebinarId="123")])
    ids = await deliver(submission(), crm, settings=BoomZoom())
    assert ids["eventRegistrationId"]           # the record exists
    assert ids["zoom"]["ok"] is False           # and Zoom is merely reported


async def test_no_webinar_means_no_zoom_attempt():
    crm = FakeCrm(events=[make_event(zoomWebinarId="")])
    ids = await deliver(submission(), crm, settings=NoZoom())
    assert ids["zoom"]["reason"] == "the event has no Zoom webinar"


# --- cancellation tokens (EV-16, EV-83) -----------------------------------


def test_cancel_token_round_trips():
    token = make_cancel_token("reg-123", "s3cret")
    assert read_cancel_token(token, "s3cret") == "reg-123"


def test_a_tampered_token_is_rejected():
    token = make_cancel_token("reg-123", "s3cret")
    forged = token.replace("reg-123", "reg-999")
    with pytest.raises(TokenError):
        read_cancel_token(forged, "s3cret")


def test_a_token_from_another_secret_is_rejected():
    token = make_cancel_token("reg-123", "old-secret")
    with pytest.raises(TokenError):
        read_cancel_token(token, "new-secret")


@pytest.mark.parametrize("bad", ["", "nodot", ".", "reg-123.", ".sig"])
def test_malformed_tokens_are_rejected(bad):
    with pytest.raises(TokenError):
        read_cancel_token(bad, "s3cret")


def test_signing_without_a_secret_fails_loudly():
    with pytest.raises(TokenError):
        make_cancel_token("reg-123", "")


# --- cancellation + promotion ---------------------------------------------


async def test_cancelling_frees_the_seat_and_promotes_the_waitlist():
    crm = FakeCrm(
        events=[make_event(venueCapacity=1)],
        registrations=[
            {"id": "r1", "eventId": "ev1", "email": "a@x.com",
             "attendanceStatus": cfg.REG_REGISTERED},
            {"id": "r2", "eventId": "ev1", "email": "b@x.com",
             "attendanceStatus": cfg.REG_WAITLISTED,
             "registrationDate": "2026-07-01 10:00:00"},
            {"id": "r3", "eventId": "ev1", "email": "c@x.com",
             "attendanceStatus": cfg.REG_WAITLISTED,
             "registrationDate": "2026-07-02 10:00:00"},
        ],
    )
    result = await service.cancel_registration(crm, "r1", settings=NoZoom())
    assert result["ok"] and result["promoted"] is True
    # the LONGEST-waiting person gets the seat, not whoever happens to be first
    assert crm.registrations[1]["attendanceStatus"] == cfg.REG_REGISTERED
    assert crm.registrations[2]["attendanceStatus"] == cfg.REG_WAITLISTED


async def test_cancelling_twice_is_not_an_error():
    crm = FakeCrm(registrations=[{
        "id": "r1", "eventId": "ev1", "email": "a@x.com",
        "attendanceStatus": cfg.REG_CANCELLED}])
    result = await service.cancel_registration(crm, "r1", settings=NoZoom())
    assert result["ok"] and result["alreadyCancelled"] is True


async def test_cancelling_an_unknown_registration_is_reported_not_crashed():
    result = await service.cancel_registration(FakeCrm(), "nope", settings=NoZoom())
    assert result["ok"] is False


async def test_no_promotion_when_the_event_is_still_full():
    crm = FakeCrm(
        events=[make_event(venueCapacity=2)],
        registrations=[
            {"id": "r1", "eventId": "ev1", "email": "a@x.com",
             "attendanceStatus": cfg.REG_REGISTERED},
            {"id": "r2", "eventId": "ev1", "email": "b@x.com",
             "attendanceStatus": cfg.REG_REGISTERED},
            {"id": "r3", "eventId": "ev1", "email": "c@x.com",
             "attendanceStatus": cfg.REG_ATTENDED},
            {"id": "r4", "eventId": "ev1", "email": "d@x.com",
             "attendanceStatus": cfg.REG_WAITLISTED},
        ],
    )
    result = await service.cancel_registration(crm, "r1", settings=NoZoom())
    assert result["promoted"] is False
    assert crm.registrations[3]["attendanceStatus"] == cfg.REG_WAITLISTED
