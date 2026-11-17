"""Hosting methods in Events — step 4 of prds/events/event-hosting-plan.md.

Zoom Meetings beside Zoom Webinars (EH2, EH11; members-only events too, Doug
11-17-26 option B), Other platform's registrations and confirmation (EH3, EH12,
EH13), and the guard that fixes the method once anyone has registered (EH4).
"""

from __future__ import annotations

import pytest

from core.zoom import PRODUCT_MEETING, PRODUCT_WEBINAR, meeting_settings
from events import attendance, confirm, hosting, member, notify, service, zoom_sync
from events import config as cfg
from events import visibility
from tests.test_events_admin import HOST_LINK, HostedEspo, public_online
from tests.test_events_confirm import reg, settings_on
from tests.test_events_service import make_event

SHARED = "https://teams.example/meet/123"


def public(**over):
    base = dict(audience="Public", format=cfg.FORMAT_VIRTUAL, zoomWebinarId="",
                virtualMeetingUrl="")
    base.update(over)
    return make_event(**base)


def members(**over):
    base = dict(audience="Internal", format=cfg.FORMAT_VIRTUAL, zoomWebinarId="",
                virtualMeetingUrl="", takesRegistrations=True)
    base.update(over)
    return make_event(**base)


# --- the one rule ---------------------------------------------------------------


@pytest.mark.parametrize("event, expected", [
    (public(), hosting.WEBINARS),                               # empty: Zoom Webinars
    (public(hostedBy="CBM Zoom"), hosting.WEBINARS),
    (public(hostedBy="Something new"), hosting.WEBINARS),       # unknown: as before
    (public(hostedBy="Zoom Meetings"), hosting.MEETINGS),
    (public(hostedBy="Other platform"), hosting.OTHER),
    (public(hostedBy="Outside host"), hosting.OUTSIDE),
    (public(hostedBy="Zoom Meetings", format=cfg.FORMAT_HYBRID), hosting.MEETINGS),
    (public(hostedBy="Zoom Meetings", format=cfg.FORMAT_IN_PERSON), ""),
    (members(hostedBy="Zoom Meetings"), hosting.MEETINGS),
    (members(hostedBy="CBM Zoom"), hosting.MEMBERS_LINK),      # D2 stands
    (members(hostedBy="Other platform"), hosting.MEMBERS_LINK),
    (members(hostedBy=None), hosting.MEMBERS_LINK),
])
def test_the_method_where_it_counts(event, expected):
    assert hosting.method(event) == expected


def test_an_event_with_no_audience_set_is_the_public_programmes():
    """The D2 carry-over: an event from before the audience field keeps
    behaving as the public programme's, ticked or not."""
    event = public(audience=None, publishToWebsite=False)
    assert hosting.method(event) == hosting.WEBINARS


def test_the_product_and_the_product_of_an_existing_id():
    assert hosting.zoom_product(public()) == PRODUCT_WEBINAR
    assert hosting.zoom_product(public(hostedBy="Zoom Meetings")) == PRODUCT_MEETING
    assert hosting.zoom_product(public(hostedBy="Other platform")) == ""
    assert hosting.zoom_product(members(hostedBy="CBM Zoom")) == ""
    # The stored value says what an id is, whatever the audience now.
    assert hosting.stored_product(members(hostedBy="Zoom Meetings")) == PRODUCT_MEETING
    assert hosting.stored_product(members(hostedBy="CBM Zoom")) == PRODUCT_WEBINAR


def test_a_members_only_meeting_registers_only_when_the_event_does():
    assert hosting.zoom_registration(public(hostedBy="Zoom Meetings"))
    assert hosting.zoom_registration(members(hostedBy="Zoom Meetings"))
    assert not hosting.zoom_registration(
        members(hostedBy="Zoom Meetings", takesRegistrations=False))


class Switch:
    def __init__(self, on):
        self.events_other_platform = on


@pytest.mark.parametrize("event, on, expected", [
    (public(), False, hosting.LINK_PERSONAL),
    (public(hostedBy="Zoom Meetings"), False, hosting.LINK_PERSONAL),
    (public(hostedBy="Other platform"), True, hosting.LINK_SHARED),
    (public(hostedBy="Other platform"), False, hosting.LINK_PERSONAL),  # dark: waits
    (members(hostedBy="Zoom Meetings"), False, hosting.LINK_PERSONAL),
    (members(hostedBy="Zoom Meetings", takesRegistrations=False), False, hosting.LINK_SHARED),
    (members(), False, hosting.LINK_SHARED),
    (public(format=cfg.FORMAT_IN_PERSON), False, hosting.LINK_NONE),
])
def test_which_link_a_confirmation_carries(event, on, expected):
    assert hosting.confirmation_link(event, Switch(on)) == expected


def test_a_public_page_never_carries_a_shared_or_meeting_link():
    assert hosting.public_join_url(public(hostedBy="Other platform",
                                          virtualMeetingUrl=SHARED)) == ""
    assert hosting.public_join_url(public(hostedBy="Zoom Meetings",
                                          virtualMeetingUrl="https://zoom.us/j/5")) == ""
    assert hosting.public_join_url(public(virtualMeetingUrl="https://zoom.us/j/9")) \
        == "https://zoom.us/j/9"
    detail = service.public_event_detail(public(hostedBy="Other platform",
                                                virtualMeetingUrl=SHARED))
    assert detail["joinUrl"] == ""


# --- the Zoom client --------------------------------------------------------------


def test_a_meeting_is_set_up_like_a_webinar():
    """EH11: muted, cameras off, nobody before the host, no waiting room, no
    recording, every Zoom email off, registration on and auto-approved."""
    s = meeting_settings()
    assert s["approval_type"] == 0 and s["registration_type"] == 1
    assert s["mute_upon_entry"] is True and s["participant_video"] is False
    assert s["join_before_host"] is False and s["waiting_room"] is False
    assert s["auto_recording"] == "none"
    assert s["registrants_confirmation_email"] is False
    assert s["registrants_email_notification"] is False
    without = meeting_settings(registration=False)
    assert without["approval_type"] == 2 and "registration_type" not in without


class Recorder:
    """A ZoomClient whose transport is recorded, not sent."""

    def __init__(self):
        from core.zoom import ZoomClient

        self.client = ZoomClient("a", "b", "c")
        self.calls = []

        async def fake(method, path, *, params=None, json_body=None, expect_body=True):
            self.calls.append((method, path, params, json_body))
            return {"id": 555, "join_url": "https://zoom.us/j/555", "registrant_id": "r1"}

        self.client._request = fake


async def test_meeting_calls_use_the_meetings_paths():
    rec = Recorder()
    from datetime import datetime, timezone
    await rec.client.create_meeting("events@example.org", topic="T",
                                    start=datetime(2026, 12, 1, 17, tzinfo=timezone.utc),
                                    duration_minutes=60)
    await rec.client.add_registrant("555", email="a@x.org", first_name="A",
                                    product=PRODUCT_MEETING)
    await rec.client.cancel_registrant("555", registrant_id="r1", product=PRODUCT_MEETING)
    await rec.client.update_meeting("555", registration=False)
    await rec.client.delete_meeting("555")
    paths = [(m, p) for m, p, _, _ in rec.calls]
    assert paths == [
        ("POST", "/users/events@example.org/meetings"),
        ("POST", "/meetings/555/registrants"),
        ("PUT", "/meetings/555/registrants/status"),
        ("PATCH", "/meetings/555"),
        ("DELETE", "/meetings/555"),
    ]
    assert rec.calls[0][3]["type"] == 2
    assert rec.calls[3][3] == {"settings": {"approval_type": 2}}
    # A webinar registration still goes where it always did.
    await rec.client.add_registrant("777", email="a@x.org", first_name="A")
    assert rec.calls[-1][1] == "/webinars/777/registrants"


# --- the sync ---------------------------------------------------------------------


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
    """Serves both products, as the sync's test seam does."""

    def __init__(self):
        self.calls = []

    async def create_webinar(self, host, **kw):
        self.calls.append(("create_webinar", host, kw))
        return {"id": 111, "join_url": "https://zoom.us/w/111", "registration_url": "r"}

    async def create_meeting(self, host, **kw):
        self.calls.append(("create_meeting", host, kw))
        return {"id": 222, "join_url": "https://zoom.us/j/222", "registration_url": "m"}

    async def update_webinar(self, wid, **kw):
        self.calls.append(("update_webinar", wid, kw))

    async def update_meeting(self, wid, **kw):
        self.calls.append(("update_meeting", wid, kw))

    async def delete_webinar(self, wid, **kw):
        self.calls.append(("delete_webinar", wid, kw))

    async def delete_meeting(self, wid, **kw):
        self.calls.append(("delete_meeting", wid, kw))

    async def get_meeting(self, wid):
        self.calls.append(("get_meeting", wid, {}))
        return {"id": int(wid), "join_url": "https://zoom.us/j/x", "registration_url": ""}

    def names(self):
        return [c[0] for c in self.calls]


class Both:
    zoom_events = True
    zoom_host_email = "zweb@example.org"
    zoom_meetings_events = True
    zoom_event_host_email = "events@example.org"


async def test_a_public_event_on_zoom_meetings_gets_a_meeting():
    crm, zoom = FakeCrm(), FakeZoom()
    event = public(hostedBy="Zoom Meetings")
    result = await zoom_sync.sync_event_webinar(Both(), crm, event, zoom=zoom)
    assert result["action"] == "created" and result["product"] == PRODUCT_MEETING
    name, host, kw = zoom.calls[0]
    assert name == "create_meeting" and host == "events@example.org"
    assert kw["registration"] is True
    assert crm.updates[0][2]["zoomWebinarId"] == "222"


async def test_a_members_only_meeting_follows_takes_registrations():
    zoom = FakeZoom()
    await zoom_sync.sync_event_webinar(
        Both(), FakeCrm(), members(hostedBy="Zoom Meetings", takesRegistrations=False),
        zoom=zoom)
    assert zoom.calls[0][0] == "create_meeting"
    assert zoom.calls[0][2]["registration"] is False


async def test_turning_registrations_on_patches_the_meeting():
    zoom = FakeZoom()
    before = members(hostedBy="Zoom Meetings", zoomWebinarId="222", takesRegistrations=False)
    after = {**before, "takesRegistrations": True}
    result = await zoom_sync.sync_event_webinar(Both(), FakeCrm(), after,
                                                previous=before, zoom=zoom)
    assert result["action"] == "patched"
    assert zoom.calls[0][0] == "update_meeting"
    assert zoom.calls[0][2]["registration"] is True


async def test_a_members_only_event_not_on_zoom_meetings_never_gets_zoom():
    for stored in ("CBM Zoom", "Other platform", None):
        zoom = FakeZoom()
        result = await zoom_sync.sync_event_webinar(
            Both(), FakeCrm(), members(hostedBy=stored), force=True, zoom=zoom)
        assert result["action"] == "skipped" and zoom.calls == []


async def test_other_platform_never_gets_a_zoom_event():
    zoom = FakeZoom()
    result = await zoom_sync.sync_event_webinar(
        Both(), FakeCrm(), public(hostedBy="Other platform", virtualMeetingUrl=SHARED),
        force=True, zoom=zoom)
    assert result["action"] == "skipped" and zoom.calls == []


async def test_moving_to_other_platform_cancels_the_webinar_and_keeps_the_typed_link():
    crm, zoom = FakeCrm(), FakeZoom()
    before = public(zoomWebinarId="111", virtualMeetingUrl="https://zoom.us/w/111")
    after = {**before, "hostedBy": "Other platform", "virtualMeetingUrl": SHARED}
    result = await zoom_sync.sync_event_webinar(Both(), crm, after, previous=before, zoom=zoom)
    assert result["action"] == "cancelled"
    assert zoom.names() == ["delete_webinar"]
    assert "virtualMeetingUrl" not in crm.updates[0][2]
    assert after["virtualMeetingUrl"] == SHARED


async def test_a_link_the_save_left_unchanged_is_zooms_and_is_cleared():
    """Moving to Other platform without typing a link leaves the webinar's own
    link, now dead; it must not stay on the event as if it were the shared one."""
    crm, zoom = FakeCrm(), FakeZoom()
    before = public(zoomWebinarId="111", virtualMeetingUrl="https://zoom.us/w/111")
    after = {**before, "hostedBy": "Other platform"}
    await zoom_sync.sync_event_webinar(Both(), crm, after, previous=before, zoom=zoom)
    assert crm.updates[0][2]["virtualMeetingUrl"] == ""


async def test_moving_from_webinars_to_meetings_replaces_the_zoom_event():
    crm, zoom = FakeCrm(), FakeZoom()
    before = public(zoomWebinarId="111", virtualMeetingUrl="https://zoom.us/w/111")
    after = {**before, "hostedBy": "Zoom Meetings"}
    result = await zoom_sync.sync_event_webinar(Both(), crm, after, previous=before, zoom=zoom)
    assert zoom.names() == ["delete_webinar", "create_meeting"]
    assert result["action"] == "created" and result["replaced"] == PRODUCT_WEBINAR
    assert after["zoomWebinarId"] == "222"


async def test_a_meetings_id_is_cancelled_as_a_meeting():
    zoom = FakeZoom()
    event = public(hostedBy="Zoom Meetings", zoomWebinarId="222",
                   status=cfg.STATUS_CANCELLED)
    await zoom_sync.sync_event_webinar(Both(), FakeCrm(), event, zoom=zoom)
    assert zoom.names() == ["delete_meeting"]


async def test_zoom_meetings_switched_off_is_reported_and_never_falls_back():
    class WebinarsOnly:
        zoom_events = True
        zoom_account_id = zoom_client_id = zoom_client_secret = "x"
        zoom_host_email = "zweb@example.org"
        zoom_meetings_events = False
        zoom_webinars_same_account = False
    result = await zoom_sync.sync_event_webinar(
        WebinarsOnly(), FakeCrm(), public(hostedBy="Zoom Meetings"))
    assert result["ok"] is False and result["disabled"] is True
    assert "Zoom Meetings" in result["reason"]


async def test_adopting_a_meeting_reads_it_as_a_meeting():
    zoom, crm = FakeZoom(), FakeCrm()
    result = await zoom_sync.adopt_existing_webinar(
        Both(), crm, public(hostedBy="Zoom Meetings"), "222", zoom=zoom)
    assert result["ok"] and zoom.names() == ["get_meeting"]


def test_the_save_warning_names_the_zoom_product():
    [warning] = visibility.save_warnings(public(hostedBy="Zoom Meetings"))
    assert "Zoom meeting exists" in warning


def test_the_save_warning_for_other_platform_says_it_is_switched_off(monkeypatch):
    monkeypatch.setattr(hosting, "other_platform_on", lambda settings=None: False)
    [warning] = visibility.save_warnings(public(hostedBy="Other platform"))
    assert "another platform" in warning and "switched off" in warning


# --- registrations ------------------------------------------------------------------


class RegZoom:
    def __init__(self):
        self.calls = []

    async def add_registrant(self, wid, **kw):
        self.calls.append(("add", wid, kw))
        return {"registrant_id": "r9", "join_url": "https://zoom.us/j/222?tk=abc"}

    async def cancel_registrant(self, wid, **kw):
        self.calls.append(("cancel", wid, kw))


async def test_a_registration_lands_on_the_meeting(monkeypatch):
    fake = RegZoom()
    monkeypatch.setattr(hosting, "zoom_client", lambda settings, product: fake)
    crm = FakeCrm()
    row = {"id": "reg1", "email": "a@x.org", "firstName": "A"}
    result = await service.push_registration_to_zoom(
        Both(), crm, public(hostedBy="Zoom Meetings", zoomWebinarId="222"), row)
    assert result["ok"] and row["zoomJoinUrl"].endswith("tk=abc")
    assert fake.calls[0][1] == "222" and fake.calls[0][2]["product"] == PRODUCT_MEETING


async def test_no_registration_on_a_meeting_that_takes_none(monkeypatch):
    monkeypatch.setattr(hosting, "zoom_client", lambda settings, product: RegZoom())
    api, _, reason = service.registrant_zoom(
        Both(), members(hostedBy="Zoom Meetings", zoomWebinarId="222",
                        takesRegistrations=False))
    assert api is None and "takes no registrations" in reason


async def test_a_cancellation_frees_the_meeting_seat(monkeypatch):
    fake = RegZoom()
    monkeypatch.setattr(hosting, "zoom_client", lambda settings, product: fake)

    class Crm:
        async def get(self, entity, record_id, select=None):
            return public(hostedBy="Zoom Meetings", zoomWebinarId="222")
    await service._remove_from_zoom(
        Crm(), {"id": "reg1", "eventId": "ev1", "zoomRegistrantId": "r9"}, Both())
    assert fake.calls == [("cancel", "222", {"registrant_id": "r9", "email": "",
                                             "product": PRODUCT_MEETING})]


def test_a_registered_member_sees_their_own_meeting_link():
    event = members(hostedBy="Zoom Meetings", virtualMeetingUrl="https://zoom.us/j/222")
    mine = {"id": "reg1", "attendanceStatus": "Registered",
            "zoomJoinUrl": "https://zoom.us/j/222?tk=me"}
    assert member.join_url_for(event, mine) == "https://zoom.us/j/222?tk=me"
    # Not yet pushed to Zoom: nothing, never the registration-page link.
    assert member.join_url_for(event, {**mine, "zoomJoinUrl": ""}) == ""
    # A meeting that takes no registrations: its one link, to every member.
    open_event = members(hostedBy="Zoom Meetings", takesRegistrations=False,
                         virtualMeetingUrl="https://zoom.us/j/222")
    assert member.join_url_for(open_event, None) == "https://zoom.us/j/222"


# --- attendance -------------------------------------------------------------------


async def test_a_meetings_report_is_read_as_a_meeting():
    class Zoom:
        def __init__(self):
            self.asked = []

        async def list_participants(self, wid):
            self.asked.append(("webinar", wid))
            return []

        async def list_meeting_participants(self, wid):
            self.asked.append(("meeting", wid))
            return []

    zoom = Zoom()
    await attendance._report(zoom, public(hostedBy="Zoom Meetings", zoomWebinarId="222"))
    await attendance._report(zoom, public(zoomWebinarId="111"))
    assert zoom.asked == [("meeting", "222"), ("webinar", "111")]


# --- the confirmation -------------------------------------------------------------------


def test_an_other_platform_confirmation_carries_the_shared_link_and_the_note():
    s = settings_on(events_other_platform=True)
    event = public(hostedBy="Other platform", virtualMeetingUrl=SHARED)
    assert confirm.skip_reason(s, event, reg(), confirm.KIND_CONFIRMATION) is None
    tokens = confirm.app_tokens(s, event, reg(), kind=confirm.KIND_CONFIRMATION)
    assert tokens["joinUrl"] == SHARED
    assert "the same for everyone attending" in tokens["joinBlock"]


def test_an_other_platform_confirmation_waits_while_its_switch_is_off():
    s = settings_on(events_other_platform=False)
    event = public(hostedBy="Other platform", virtualMeetingUrl=SHARED)
    assert confirm.skip_reason(s, event, reg(), confirm.KIND_CONFIRMATION) \
        == "no personal join link yet"


def test_a_zoom_meetings_confirmation_needs_the_personal_link():
    s = settings_on()
    event = members(hostedBy="Zoom Meetings", virtualMeetingUrl="https://zoom.us/j/222")
    assert confirm.skip_reason(s, event, reg(), confirm.KIND_CONFIRMATION) \
        == "no personal join link yet"
    tokens = confirm.app_tokens(s, event, reg(zoomJoinUrl="https://zoom.us/j/222?tk=1"),
                                kind=confirm.KIND_CONFIRMATION)
    assert tokens["joinUrl"].endswith("tk=1")
    assert "same for everyone" not in tokens["joinBlock"]


# --- writing the event -------------------------------------------------------------------


async def test_other_platforms_link_is_typed_only_while_its_switch_is_on(monkeypatch):
    monkeypatch.setattr(hosting, "other_platform_on", lambda settings=None: False)
    crm = HostedEspo([public_online()])
    await service.update_event(crm, "ev1", {"hostedBy": "Other platform",
                                            "virtualMeetingUrl": SHARED})
    assert "virtualMeetingUrl" not in crm.updated[-1]

    monkeypatch.setattr(hosting, "other_platform_on", lambda settings=None: True)
    crm = HostedEspo([public_online()])
    await service.update_event(crm, "ev1", {"hostedBy": "Other platform",
                                            "virtualMeetingUrl": SHARED})
    assert crm.updated[-1]["virtualMeetingUrl"] == SHARED


async def test_other_platforms_link_must_be_https(monkeypatch):
    monkeypatch.setattr(hosting, "other_platform_on", lambda settings=None: True)
    crm = HostedEspo([public_online()])
    with pytest.raises(service.EventError, match="https://"):
        await service.update_event(crm, "ev1", {"hostedBy": "Other platform",
                                                "virtualMeetingUrl": "teams.example/x"})


async def test_a_members_only_meeting_keeps_zooms_link():
    crm = HostedEspo([public_online(audience="Internal", hostedBy="Zoom Meetings")])
    await service.update_event(crm, "ev1", {"name": "Renamed",
                                            "virtualMeetingUrl": HOST_LINK})
    assert "virtualMeetingUrl" not in crm.updated[-1]
    # Any other members-only event keeps its typed link (D3 of the portal design).
    crm = HostedEspo([public_online(audience="Internal")])
    await service.update_event(crm, "ev1", {"virtualMeetingUrl": HOST_LINK})
    assert crm.updated[-1]["virtualMeetingUrl"] == HOST_LINK


async def test_the_method_is_fixed_once_anyone_has_registered():
    """EH4: webinars to meetings, with people registered, is refused."""
    crm = HostedEspo([public_online(zoomWebinarId="1", virtualMeetingUrl="https://zoom.us/w/1")],
                     registrations=[{"attendanceStatus": "Registered"}])
    with pytest.raises(service.EventError,
                       match="from Zoom Webinars to Zoom Meetings"):
        await service.update_event(crm, "ev1", {"hostedBy": "Zoom Meetings"})
    assert crm.updated == []


async def test_an_audience_edit_is_not_a_method_change():
    crm = HostedEspo([public_online(zoomWebinarId="1", virtualMeetingUrl="https://zoom.us/w/1")],
                     registrations=[{"attendanceStatus": "Registered"}])
    await service.update_event(crm, "ev1", {"audience": "Internal"})
    assert crm.updated[-1]["audience"] == "Internal"


# --- EH12 -------------------------------------------------------------------------


def test_no_show_on_other_platform_warns_until_attendance_is_marked():
    event = public(hostedBy="Other platform", virtualMeetingUrl=SHARED)
    no_show = notify.BY_KIND[notify.KIND_NO_SHOW]
    rows = [reg()]
    assert "Mark attendance" in notify.attendance_warning(event, no_show, rows)
    assert notify.attendance_warning(event, no_show, [reg(attendanceStatus="No-Show")]) == ""
    assert notify.attendance_warning(public(), no_show, rows) == ""
    assert notify.attendance_warning(event, notify.BY_KIND[notify.KIND_SURVEY], rows) == ""


async def test_the_preview_carries_the_warning():
    event = public(hostedBy="Other platform", virtualMeetingUrl=SHARED)
    result = await notify.send_follow_up(
        settings_on(), None, event, notify.BY_KIND[notify.KIND_NO_SHOW],
        registrations=[reg()], dry_run=True)
    assert result["warning"]


# === Step 5: the event form (EH4 to EH6, EH14) ======================================


class FormSettings:
    zoom_active = True
    zoom_meetings_active = False
    events_other_platform = False
    zoom_meetings_capacity = 100
    events_default_method_public = "CBM Zoom"
    events_default_method_members = "Zoom Meetings"
    zoom_events = True
    zoom_meetings_events = True
    zoom_host_email = "events@example.org"
    zoom_event_host_email = "events@example.org"


def test_every_method_is_offered_with_its_reason_never_hidden():
    payload = hosting.methods_payload(FormSettings())
    by = {m["value"]: m for m in payload["methods"]}
    assert list(by) == ["CBM Zoom", "Zoom Meetings", "Other platform", "Outside host"]
    assert by["CBM Zoom"]["ready"] and by["CBM Zoom"]["label"] == "Zoom Webinars"
    assert not by["Zoom Meetings"]["ready"]
    assert by["Zoom Meetings"]["reason"].startswith("Not set up")
    assert not by["Other platform"]["ready"] and by["Outside host"]["ready"]
    assert "Up to 100" in by["Zoom Meetings"]["explain"]
    assert payload["defaults"] == {"Public": "CBM Zoom", "Internal": "Zoom Meetings"}
    labels = hosting.option_labels(FormSettings())
    assert labels["Zoom Meetings"] == "Zoom Meetings (not set up)"
    assert labels["CBM Zoom"] == "Zoom Webinars"


def test_a_members_only_event_explains_the_typed_link():
    assert "link you paste below" in hosting.explain("CBM Zoom", members=True)
    assert "Zoom Webinars are for public events" in hosting.explain("CBM Zoom", members=True)
    assert "every member sees one link" in hosting.explain("Zoom Meetings", members=True)


@pytest.mark.parametrize("fmt, capacity, expected", [
    (cfg.FORMAT_VIRTUAL, 140, "refuse"),
    (cfg.FORMAT_HYBRID, 140, "warn"),     # EH14: the room counts too
    (cfg.FORMAT_VIRTUAL, 100, ""),
    (cfg.FORMAT_VIRTUAL, None, ""),
])
def test_the_capacity_guard(fmt, capacity, expected):
    event = public(hostedBy="Zoom Meetings", format=fmt, venueCapacity=capacity)
    kind, message = hosting.capacity_check(event, FormSettings())
    assert kind == expected
    if expected == "warn":
        assert message == ("Capacity 140 is above Zoom Meetings' 100. If more than 100 "
                           "join online, the rest cannot get in.")


def test_the_capacity_guard_is_for_zoom_meetings_only():
    assert hosting.capacity_check(public(venueCapacity=500), FormSettings()) == ("", "")


async def test_a_fully_online_meeting_above_capacity_is_refused_on_save():
    crm = HostedEspo([public_online(format=cfg.FORMAT_VIRTUAL)])
    with pytest.raises(service.EventError, match="Capacity 140 is above Zoom Meetings' 100"):
        await service.update_event(crm, "ev1", {"hostedBy": "Zoom Meetings",
                                                "venueCapacity": 140})
    assert crm.updated == []
    # Hybrid: saved, and warned.
    crm = HostedEspo([public_online(format=cfg.FORMAT_HYBRID)])
    await service.update_event(crm, "ev1", {"hostedBy": "Zoom Meetings", "venueCapacity": 140})
    assert crm.updated[-1]["venueCapacity"] == 140


def test_hosting_warnings_name_a_method_not_set_up():
    [warning] = hosting.warnings(public(hostedBy="Zoom Meetings"), FormSettings())
    assert warning.startswith("Zoom Meetings is not set up")
    # A members-only event on the typed link has nothing to set up.
    assert hosting.warnings(members(hostedBy="CBM Zoom"), FormSettings()) == []


async def test_a_new_event_starts_on_its_audiences_default(monkeypatch):
    monkeypatch.setattr(hosting, "default_for",
                        lambda audience, settings=None: FormSettings.events_default_method_members
                        if audience == "Internal" else FormSettings.events_default_method_public)
    crm = HostedEspo([])
    await service.create_event(crm, {"name": "Roundtable", "audience": "Internal",
                                     "format": cfg.FORMAT_VIRTUAL}, chapter_key="cleveland")
    assert crm.created[-1]["hostedBy"] == "Zoom Meetings"
    crm = HostedEspo([])
    await service.create_event(crm, {"name": "Webinar", "format": cfg.FORMAT_VIRTUAL},
                               chapter_key="cleveland")
    assert crm.created[-1]["hostedBy"] == "CBM Zoom"
    # A chosen method is kept.
    crm = HostedEspo([])
    await service.create_event(crm, {"name": "Partner", "format": cfg.FORMAT_VIRTUAL,
                                     "hostedBy": "Outside host"}, chapter_key="cleveland")
    assert crm.created[-1]["hostedBy"] == "Outside host"


def _at(start, end, **over):
    return public(dateStart=start, dateEnd=end, **over)


def test_two_zoom_events_under_one_host_overlap_from_half_an_hour_before():
    mine = _at("2026-12-01 18:00:00", "2026-12-01 19:00:00", id="a")
    # Starts 20 minutes after mine ends — but its host opens 30 minutes early.
    near = _at("2026-12-01 19:20:00", "2026-12-01 20:00:00", id="b",
               hostedBy="Zoom Meetings", name="Roundtable")
    far = _at("2026-12-01 19:40:00", "2026-12-01 20:30:00", id="c")
    gone = _at("2026-12-01 18:00:00", "2026-12-01 19:00:00", id="d",
               status=cfg.STATUS_CANCELLED)
    other = _at("2026-12-01 18:00:00", "2026-12-01 19:00:00", id="e",
                hostedBy="Other platform")
    clashes = hosting.overlaps(mine, [mine, near, far, gone, other], FormSettings())
    assert [c["id"] for c in clashes] == ["b"]
    text = hosting.overlap_warning(mine, clashes, FormSettings())
    assert "“Roundtable”" in text and "events@example.org" in text


def test_webinars_on_their_own_account_do_not_clash_with_meetings():
    class Separate(FormSettings):
        zoom_webinars_same_account = False
        zoom_meetings_account_id = zoom_meetings_client_id = zoom_meetings_client_secret = "m"
        zoom_host_email = "webinars@example.org"
    mine = _at("2026-12-01 18:00:00", "2026-12-01 19:00:00", id="a")
    meeting = _at("2026-12-01 18:00:00", "2026-12-01 19:00:00", id="b",
                  hostedBy="Zoom Meetings")
    assert hosting.overlaps(mine, [meeting], Separate()) == []


async def test_the_overlap_check_reads_the_crm_and_warns():
    clash = _at("2026-12-01 18:30:00", "2026-12-01 19:30:00", id="b", name="Other talk")
    crm = HostedEspo([clash])
    mine = _at("2026-12-01 18:00:00", "2026-12-01 19:00:00", id="a")
    [warning] = await service.overlap_warnings(crm, mine, FormSettings())
    assert "“Other talk”" in warning


async def test_the_check_names_the_platform_before_publishing(monkeypatch):
    """EH6: "This creates a Zoom Meeting, not a webinar"."""
    class Ready(FormSettings):
        zoom_meetings_active = True
    crm = HostedEspo([public_online(publishToWebsite=False, virtualMeetingUrl="",
                                    zoomWebinarId="")])
    result = await service.check_event(
        crm, "ev1", {"hostedBy": "Zoom Meetings", "publishToWebsite": True},
        settings=Ready())
    assert result["zoom"]["action"] == "create"
    assert result["confirm"][0] == "This creates a Zoom Meeting, not a webinar."
    assert result["refusal"] == ""


async def test_the_check_says_when_the_method_is_not_set_up():
    crm = HostedEspo([public_online(publishToWebsite=False, virtualMeetingUrl="",
                                    zoomWebinarId="")])
    result = await service.check_event(
        crm, "ev1", {"hostedBy": "Zoom Meetings", "publishToWebsite": True},
        settings=FormSettings())
    assert "not set up in System Settings" in result["confirm"][0]


async def test_the_check_reports_the_refusal_and_writes_nothing():
    crm = HostedEspo([public_online(format=cfg.FORMAT_VIRTUAL)],
                     registrations=[{"attendanceStatus": "Registered"}])
    result = await service.check_event(crm, "ev1", {"hostedBy": "Zoom Meetings"},
                                       settings=FormSettings())
    assert "registered for this event" in result["refusal"]
    assert crm.updated == [] and crm.created == []


async def test_the_check_names_a_replacement():
    class Ready(FormSettings):
        zoom_meetings_active = True
    crm = HostedEspo([public_online(zoomWebinarId="111",
                                    virtualMeetingUrl="https://zoom.us/w/111")])
    result = await service.check_event(crm, "ev1", {"hostedBy": "Zoom Meetings"},
                                       settings=Ready())
    assert result["confirm"][0] == ("This cancels the Zoom webinar and creates a Zoom "
                                    "Meeting in its place.")


def test_the_editor_offers_the_method_with_its_line_and_checks_before_saving():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "events" / "frontend" / "app.js").read_text()
    assert "function hostingControls(" in source
    assert "checkBeforeSave(raw.id, changes)" in source and "checkBeforeSave(null, changes)" in source
    # Zoom Meetings' link is Zoom's: the Join URL box is not shown for it.
    assert 'if (method === "Zoom Meetings") joinWrap.hidden = true;' in source
