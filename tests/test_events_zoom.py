"""Events Phase 2 — the Zoom client and the webinar decision layer.

No Zoom account is needed to run these: the transport is exercised against a
stubbed HTTP layer and the decision matrix is pure. What they protect is the
behaviour that would hurt if wrong — sending registrants two of everything,
orphaning a webinar nobody can cancel, or failing an event save because Zoom
had a bad minute.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from core import zoom as zoom_mod
from core.zoom import (
    APPROVAL_AUTOMATIC,
    ZoomAuthError,
    ZoomClient,
    ZoomError,
    parse_zoom_time,
    to_zoom_time,
    webinar_settings,
)
from events import config as cfg
from events import zoom_sync

from tests.test_events_service import make_event


# --- stub transport --------------------------------------------------------


class StubZoomHTTP:
    """Scripts HTTP responses and records what was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def install(self, monkeypatch):
        stub = self

        class FakeAsyncClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kw):
                return await self.request("POST", url, **kw)

            async def request(self, method, url, **kw):
                stub.requests.append({
                    "method": method, "url": url,
                    "json": kw.get("json"), "params": kw.get("params"),
                    "headers": kw.get("headers") or {},
                })
                status, payload, headers = stub.responses.pop(0)
                return httpx.Response(
                    status_code=status, json=payload, headers=headers or {},
                    request=httpx.Request(method, url),
                )

        monkeypatch.setattr(zoom_mod.httpx, "AsyncClient", FakeAsyncClient)
        return self


TOKEN_OK = (200, {"access_token": "tok-1", "expires_in": 3600}, None)


def client():
    return ZoomClient("acct", "cid", "secret")


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    async def instant(_seconds):
        return None
    monkeypatch.setattr(zoom_mod, "_sleep", instant)


# --- auth ------------------------------------------------------------------


async def test_token_is_fetched_once_and_reused(monkeypatch):
    stub = StubZoomHTTP([
        TOKEN_OK,
        (200, {"id": 1}, None),
        (200, {"id": 2}, None),
    ]).install(monkeypatch)
    api = client()
    await api.get_webinar("1")
    await api.get_webinar("2")
    token_calls = [r for r in stub.requests if "oauth/token" in r["url"]]
    assert len(token_calls) == 1, "the token should be cached between calls"


async def test_bad_credentials_raise_a_configuration_error(monkeypatch):
    StubZoomHTTP([(401, {"reason": "Invalid client"}, None)]).install(monkeypatch)
    with pytest.raises(ZoomAuthError) as exc:
        await client().get_webinar("1")
    assert "ZOOM_ACCOUNT_ID" in str(exc.value)


async def test_credentials_are_never_echoed_in_the_error(monkeypatch):
    StubZoomHTTP([(400, {"reason": "bad client_id super-secret-value"}, None)]).install(
        monkeypatch)
    with pytest.raises(ZoomAuthError) as exc:
        await client().get_webinar("1")
    assert "super-secret-value" not in str(exc.value)


async def test_a_revoked_token_triggers_one_reauth_then_succeeds(monkeypatch):
    stub = StubZoomHTTP([
        TOKEN_OK,
        (401, {"message": "Access token is expired"}, None),
        TOKEN_OK,
        (200, {"id": 99}, None),
    ]).install(monkeypatch)
    assert (await client().get_webinar("99"))["id"] == 99
    assert len([r for r in stub.requests if "oauth/token" in r["url"]]) == 2


# --- backoff ---------------------------------------------------------------


async def test_rate_limit_is_retried(monkeypatch):
    StubZoomHTTP([
        TOKEN_OK,
        (429, {}, {"Retry-After": "1"}),
        (200, {"id": 7}, None),
    ]).install(monkeypatch)
    assert (await client().get_webinar("7"))["id"] == 7


async def test_server_errors_are_retried_then_surface(monkeypatch):
    StubZoomHTTP([TOKEN_OK] + [(503, {}, None)] * 4).install(monkeypatch)
    with pytest.raises(ZoomError) as exc:
        await client().get_webinar("7")
    assert "503" in str(exc.value)


async def test_transport_failure_is_a_zoom_error(monkeypatch):
    class Boom:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): raise httpx.ConnectError("no route")
        async def request(self, *a, **kw): raise httpx.ConnectError("no route")

    monkeypatch.setattr(zoom_mod.httpx, "AsyncClient", Boom)
    with pytest.raises(ZoomError):
        await client().get_webinar("1")


# --- webinar calls ---------------------------------------------------------


async def test_create_webinar_sends_the_right_shape(monkeypatch):
    stub = StubZoomHTTP([
        TOKEN_OK,
        (201, {"id": 123456789, "join_url": "https://zoom.us/j/1",
               "registration_url": "https://zoom.us/w/1"}, None),
    ]).install(monkeypatch)
    result = await client().create_webinar(
        "zweb@cbmentors.org",
        topic="Grant Writing Basics",
        start=datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc),
        duration_minutes=90,
        agenda="Demystifying the dollar signs.",
    )
    sent = stub.requests[-1]
    assert sent["url"].endswith("/users/zweb@cbmentors.org/webinars")
    assert sent["json"]["start_time"] == "2026-09-15T18:00:00Z"
    assert sent["json"]["duration"] == 90
    assert sent["json"]["type"] == 5
    assert result["id"] == 123456789


async def test_registration_is_enabled_and_auto_approved(monkeypatch):
    """approval_type 0 is what makes the registrants API usable at all."""
    stub = StubZoomHTTP([TOKEN_OK, (201, {"id": 1}, None)]).install(monkeypatch)
    await client().create_webinar(
        "h", topic="t", start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        duration_minutes=60)
    assert stub.requests[-1]["json"]["settings"]["approval_type"] == APPROVAL_AUTOMATIC


def test_zoom_reminders_are_off_but_confirmation_stays_on():
    """EV-24/D-13: Zoom's confirmation carries the unique join link so it must
    stay; its reminders would duplicate ours so they must not."""
    settings = webinar_settings(cbm_sends_reminders=True)
    assert settings["registrants_confirmation_email"] is True
    assert settings["attendees_and_panelists_reminder_email_notification"]["enable"] is False
    assert settings["follow_up_attendees_email_notification"]["enable"] is False
    assert settings["follow_up_absentees_email_notification"]["enable"] is False


def test_reminders_can_be_left_to_zoom():
    settings = webinar_settings(cbm_sends_reminders=False)
    assert "attendees_and_panelists_reminder_email_notification" not in settings


async def test_update_tolerates_a_204_with_no_body(monkeypatch):
    StubZoomHTTP([TOKEN_OK, (204, None, None)]).install(monkeypatch)
    await client().update_webinar("123", topic="New title")  # must not raise


async def test_update_with_nothing_to_change_makes_no_call(monkeypatch):
    stub = StubZoomHTTP([]).install(monkeypatch)
    await client().update_webinar("123")
    assert stub.requests == []


async def test_delete_asks_zoom_to_notify_registrants(monkeypatch):
    stub = StubZoomHTTP([TOKEN_OK, (204, None, None)]).install(monkeypatch)
    await client().delete_webinar("123")
    assert stub.requests[-1]["params"]["cancel_webinar_reminder"] == "true"


async def test_add_registrant_returns_the_personal_join_link(monkeypatch):
    stub = StubZoomHTTP([
        TOKEN_OK,
        (201, {"id": 123, "registrant_id": "reg-abc",
               "join_url": "https://zoom.us/w/123?tk=personal"}, None),
    ]).install(monkeypatch)
    result = await client().add_registrant(
        "123", email="ada@example.com", first_name="Ada", last_name="Lovelace")
    assert stub.requests[-1]["json"]["email"] == "ada@example.com"
    assert result["registrant_id"] == "reg-abc"
    assert "tk=personal" in result["join_url"]


async def test_participants_report_follows_pagination(monkeypatch):
    StubZoomHTTP([
        TOKEN_OK,
        (200, {"participants": [{"user_email": "a@x.com"}], "next_page_token": "p2"}, None),
        (200, {"participants": [{"user_email": "b@x.com"}], "next_page_token": ""}, None),
    ]).install(monkeypatch)
    rows = await client().list_participants("123")
    assert [r["user_email"] for r in rows] == ["a@x.com", "b@x.com"]


# --- time helpers ----------------------------------------------------------


def test_zoom_time_round_trip():
    moment = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)
    assert to_zoom_time(moment) == "2026-09-15T18:00:00Z"
    assert parse_zoom_time("2026-09-15T18:00:00Z") == moment
    assert parse_zoom_time(None) is None
    assert parse_zoom_time("nonsense") is None


# --- the decision matrix (pure) -------------------------------------------


def test_published_online_event_without_a_webinar_is_created():
    action, _ = zoom_sync.decide(make_event(zoomWebinarId=""))
    assert action == "create"


def test_unpublished_event_is_skipped_unless_forced():
    event = make_event(zoomWebinarId="", publishToWebsite=False)
    assert zoom_sync.decide(event)[0] == "skip"
    assert zoom_sync.decide(event, force=True)[0] == "create"


def test_in_person_event_never_gets_a_webinar():
    action, reason = zoom_sync.decide(
        make_event(zoomWebinarId="", format=cfg.FORMAT_IN_PERSON))
    assert action == "skip"
    assert "in-person" in reason


def test_hybrid_event_does_get_a_webinar():
    assert zoom_sync.decide(
        make_event(zoomWebinarId="", format=cfg.FORMAT_HYBRID))[0] == "create"


def test_event_without_a_start_time_is_skipped():
    assert zoom_sync.decide(make_event(zoomWebinarId="", dateStart=None))[0] == "skip"


def test_material_change_patches():
    previous = make_event(zoomWebinarId="123")
    event = make_event(zoomWebinarId="123", name="A New Title")
    assert zoom_sync.decide(event, previous=previous)[0] == "patch"


def test_immaterial_change_does_not_patch():
    """Patching for a capacity or category tweak is pointless traffic, and can
    make Zoom mail every registrant about an 'update'."""
    previous = make_event(zoomWebinarId="123")
    event = make_event(zoomWebinarId="123", venueCapacity=999, topic="Operations")
    assert zoom_sync.decide(event, previous=previous)[0] == "skip"


def test_cancelled_event_cancels_its_webinar():
    action, _ = zoom_sync.decide(
        make_event(zoomWebinarId="123", status=cfg.STATUS_CANCELLED))
    assert action == "cancel"


def test_cancelled_event_without_a_webinar_does_nothing():
    assert zoom_sync.decide(
        make_event(zoomWebinarId="", status=cfg.STATUS_CANCELLED))[0] == "skip"


def test_switching_an_online_event_to_in_person_cancels_the_webinar():
    """Otherwise registrants keep a join link to a room nobody will host."""
    action, reason = zoom_sync.decide(
        make_event(zoomWebinarId="123", format=cfg.FORMAT_IN_PERSON))
    assert action == "cancel"
    assert "no longer online" in reason


# --- duration conversion ---------------------------------------------------


@pytest.mark.parametrize("event,expected", [
    ({"duration": 5400}, 90),
    ({"duration": 3600}, 60),
    ({"duration": None, "dateStart": "2026-09-15 18:00:00",
      "dateEnd": "2026-09-15 19:00:00"}, 60),
    ({"duration": None, "dateStart": None, "dateEnd": None}, 60),  # sane default
])
def test_duration_is_converted_from_seconds_to_minutes(event, expected):
    assert zoom_sync._duration_minutes(event) == expected


# --- the sync hook ---------------------------------------------------------


class FakeCrm:
    def __init__(self, fail=False):
        self.updates = []
        self.fail = fail

    async def update(self, entity, record_id, payload):
        if self.fail:
            raise RuntimeError("CRM write failed")
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}


class FakeZoom:
    def __init__(self, **behaviour):
        self.behaviour = behaviour
        self.calls = []

    async def create_webinar(self, host, **kw):
        self.calls.append(("create", host, kw))
        if self.behaviour.get("create_fails"):
            raise ZoomError("Zoom is down")
        return self.behaviour.get("created", {
            "id": 987654321, "join_url": "https://zoom.us/j/9",
            "registration_url": "https://zoom.us/w/9"})

    async def update_webinar(self, webinar_id, **kw):
        self.calls.append(("update", webinar_id, kw))

    async def delete_webinar(self, webinar_id, **kw):
        self.calls.append(("delete", webinar_id, kw))
        if self.behaviour.get("delete_fails"):
            raise ZoomError("cannot delete")

    async def get_webinar(self, webinar_id):
        self.calls.append(("get", webinar_id, {}))
        if self.behaviour.get("get_fails"):
            raise ZoomError("no such webinar")
        return {"id": int(webinar_id), "join_url": "https://zoom.us/j/x",
                "registration_url": "https://zoom.us/w/x", "topic": "Existing"}


class Settings:
    zoom_events = True
    zoom_host_email = "zweb@cbmentors.org"


async def test_create_persists_the_webinar_id_to_the_crm():
    crm, zoom = FakeCrm(), FakeZoom()
    event = make_event(id="ev1", zoomWebinarId="")
    result = await zoom_sync.sync_event_webinar(Settings(), crm, event, zoom=zoom)
    assert result["ok"] and result["action"] == "created"
    entity, record_id, payload = crm.updates[0]
    assert (entity, record_id) == (cfg.EVENT, "ev1")
    assert payload["zoomWebinarId"] == "987654321"
    # the in-memory record is updated too, so the response needs no re-read
    assert event["zoomWebinarId"] == "987654321"


async def test_a_failed_id_write_deletes_the_webinar_rather_than_orphan_it():
    """An unrecorded webinar is invisible to the app forever — nobody could
    cancel it or push registrants to it."""
    crm, zoom = FakeCrm(fail=True), FakeZoom()
    result = await zoom_sync.sync_event_webinar(
        Settings(), crm, make_event(zoomWebinarId=""), zoom=zoom)
    assert result["ok"] is False
    assert ("delete", "987654321") == zoom.calls[-1][:2]
    assert "orphanedWebinarId" not in result


async def test_an_unrecoverable_orphan_is_reported_loudly():
    crm, zoom = FakeCrm(fail=True), FakeZoom(delete_fails=True)
    result = await zoom_sync.sync_event_webinar(
        Settings(), crm, make_event(zoomWebinarId=""), zoom=zoom)
    assert result["ok"] is False
    assert result["orphanedWebinarId"] == "987654321"


async def test_zoom_being_down_never_fails_the_save():
    crm, zoom = FakeCrm(), FakeZoom(create_fails=True)
    result = await zoom_sync.sync_event_webinar(
        Settings(), crm, make_event(zoomWebinarId=""), zoom=zoom)
    assert result["ok"] is False
    assert "Zoom is down" in result["error"]
    assert crm.updates == []


async def test_cancel_clears_the_stored_id():
    crm, zoom = FakeCrm(), FakeZoom()
    event = make_event(id="ev1", zoomWebinarId="123", status=cfg.STATUS_CANCELLED)
    result = await zoom_sync.sync_event_webinar(Settings(), crm, event, zoom=zoom)
    assert result["action"] == "cancelled"
    assert crm.updates[0][2]["zoomWebinarId"] == ""
    assert event["zoomWebinarId"] == ""


async def test_cancel_reports_a_warning_if_the_clear_fails():
    """The webinar IS cancelled — say so, and tell the user how to tidy up."""
    crm, zoom = FakeCrm(fail=True), FakeZoom()
    result = await zoom_sync.sync_event_webinar(
        Settings(), crm,
        make_event(zoomWebinarId="123", status=cfg.STATUS_CANCELLED), zoom=zoom)
    assert result["ok"] is True and result["action"] == "cancelled"
    assert "warning" in result


async def test_disabled_when_zoom_is_off():
    class Off:
        zoom_events = False
        zoom_host_email = "h"
    result = await zoom_sync.sync_event_webinar(
        Off(), FakeCrm(), make_event(zoomWebinarId=""))
    assert result["ok"] is False and result["disabled"] is True


async def test_disabled_when_no_host_is_configured():
    class NoHost:
        zoom_events = True
        zoom_host_email = ""
    result = await zoom_sync.sync_event_webinar(
        NoHost(), FakeCrm(), make_event(zoomWebinarId=""), zoom=FakeZoom())
    assert result["ok"] is False and result["disabled"] is True


async def test_adopting_an_existing_webinar_verifies_it_first():
    crm, zoom = FakeCrm(), FakeZoom()
    event = make_event(id="ev1", zoomWebinarId="")
    result = await zoom_sync.adopt_existing_webinar(
        Settings(), crm, event, "89002896927", zoom=zoom)
    assert result["ok"] and result["action"] == "linked"
    assert event["zoomWebinarId"] == "89002896927"


async def test_adopting_a_bad_id_fails_loudly_and_writes_nothing():
    crm, zoom = FakeCrm(), FakeZoom(get_fails=True)
    result = await zoom_sync.adopt_existing_webinar(
        Settings(), crm, make_event(zoomWebinarId=""), "nope", zoom=zoom)
    assert result["ok"] is False
    assert crm.updates == []
