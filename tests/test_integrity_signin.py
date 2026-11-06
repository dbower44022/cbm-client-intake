"""Mentor login integrity, step 4c, condition 7 (plan § 4.2): a login with no
mentor profile opens Client Management or My Mentor Profile — recorded and
(with the digest on) emailed at once, at most once per login per day,
confirmed under the key so a role that hides a profile is no fault."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import Settings
from integrity import signin

T0 = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)
USER = {"userId": "uX", "userName": "new.mentor@cbmentors.org", "name": "New Mentor",
        "teams": ["Mentor Team"]}


@pytest.fixture(autouse=True)
def _fresh():
    signin._handled.clear()
    yield
    signin._handled.clear()


class Reader:
    def __init__(self, profiles=()):
        self.profiles = list(profiles)

    async def list(self, entity, **kw):
        return {"list": self.profiles if not kw.get("offset") else []}


class Store:
    def __init__(self):
        self.keys: set[str] = set()
        self.notified: list[str] = []

    async def record_event(self, fault, now=None):
        if fault["key"] in self.keys:
            return None
        self.keys.add(fault["key"])
        return {"id": "r" + str(len(self.keys)), **fault}

    async def mark_notified(self, ids, now=None):
        self.notified.extend(ids)


def _settings(**kw):
    base = dict(integrity_signin_alert=True, integrity_digest=True,
                integrity_digest_to="staff@x.org", app_base_url="https://apps.example.org")
    base.update(kw)
    return Settings(**base)


async def test_recorded_and_emailed_once_a_day():
    store, sent = Store(), []

    async def send(to, subject, text):
        sent.append((to, subject, text))

    for _ in range(2):
        await signin.report_no_profile(USER, signin.APP_CLIENT_MANAGEMENT, settings=_settings(),
                                       reader=Reader(), store=store, send=send, now=T0)
    assert store.keys == {"7:uX:2026-11-06"}
    assert len(sent) == 1 and sent[0][0] == ["staff@x.org"]
    assert "New Mentor (new.mentor@cbmentors.org) opened Client Management" in sent[0][2]
    assert "https://apps.example.org/mentoradmin/?faults=1" in sent[0][2]
    assert store.notified == ["r1"]


async def test_no_email_without_the_digest_switch_but_still_recorded():
    store, sent = Store(), []

    async def send(*a):
        sent.append(a)

    row = await signin.report_no_profile(USER, signin.APP_MY_MENTOR_PROFILE,
                                         settings=_settings(integrity_digest=False),
                                         reader=Reader(), store=store, send=send, now=T0)
    assert row is not None and sent == [] and store.notified == []


async def test_a_profile_the_key_sees_is_no_fault_and_the_switch_off_does_nothing():
    store = Store()
    carried = Reader([{"id": "MP", "name": "N", "assignedUsersIds": ["uX"]}])
    assert await signin.report_no_profile(USER, "x", settings=_settings(), reader=carried,
                                          store=store, now=T0) is None
    assert await signin.report_no_profile(USER, "x", settings=_settings(
        integrity_signin_alert=False), reader=Reader(), store=store, now=T0) is None
    assert store.keys == set()


async def test_staff_off_the_mentor_teams_are_not_reported_and_a_repeat_skips_the_read():
    store = Store()
    staff = dict(USER, teams=["Mentor Administration Team"], isAdmin=True)
    assert await signin.report_no_profile(staff, "x", settings=_settings(), reader=Reader(),
                                          store=store, now=T0) is None
    assert store.keys == set()

    class Counting(Reader):
        reads = 0

        async def list(self, entity, **kw):
            Counting.reads += 1
            return await super().list(entity, **kw)

    r = Counting()
    for _ in range(3):
        await signin.report_no_profile(USER, "x", settings=_settings(integrity_digest=False),
                                       reader=r, store=store, now=T0)
    assert Counting.reads == 1  # one CRM read a day per process, however often the page loads


async def test_a_failure_never_raises():
    class Broken(Reader):
        async def list(self, entity, **kw):
            raise RuntimeError("HTTP 500")

    assert await signin.report_no_profile(USER, "x", settings=_settings(), reader=Broken(),
                                          store=Store(), now=T0) is None


# --- the two pages call it after answering ----------------------------------------

def test_client_management_and_my_mentor_profile_report_a_missing_profile(monkeypatch):
    from fastapi.testclient import TestClient

    from core.app import create_app
    from core.config import get_settings
    from forms import info_request

    calls = []

    async def fake_report(user, app, **kw):
        calls.append((user["userId"], app))

    async def no_records(cfg, client, user):
        return {"records": [], "profileFound": False}

    async def no_profile(client, user_id, settings=None):
        return {"profileFound": False}

    async def ambiguous(client, user_id, settings=None):
        return {"profileFound": False, "ambiguous": True}

    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    monkeypatch.setattr("integrity.signin.report_no_profile", fake_report)
    user = {"userId": "uX", "userName": "n", "name": "N", "isAdmin": True, "token": "t"}
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda s, u: object())
    monkeypatch.setattr("mentorprofile.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("mentorprofile.router.client_for", lambda s, u: object())
    monkeypatch.setattr("sessions.service.list_records", no_records)
    monkeypatch.setattr("mentorprofile.service.get_own_profile", no_profile)
    with TestClient(create_app([info_request.SPEC])) as c:
        assert c.get("/mentorsessions/api/records").json()["profileFound"] is False
        c.get("/partnersessions/api/records")  # Partner Management is not condition 7
        assert c.get("/mentorprofile/api/profile").json()["profileFound"] is False
        monkeypatch.setattr("mentorprofile.service.get_own_profile", ambiguous)
        c.get("/mentorprofile/api/profile")  # several profiles: condition 1's job
    get_settings.cache_clear()
    assert calls == [("uX", "Client Management"), ("uX", "My Mentor Profile")]
