"""The coded actions (integrations/actions.py), which the set-up wizard's
button screens run (prds/integrations-tab-plan.md § 10, ruling W4).

Built in phase 7 for the setup assistant's setup plans; moved here in phase 10
when setup plans were removed. Their dry run, apply, idempotency and refusals,
with fake vendor clients.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from core.config import Settings, get_settings
from integrations import actions


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


# --- the coded actions ----------------------------------------------------------------------

KEY = json.dumps({"type": "service_account", "client_email": "app@proj.iam.gserviceaccount.com",
                  "private_key": "x", "token_uri": "https://oauth2.googleapis.com/token"})


def gsettings(**kw):
    base = dict(google_service_account_json=KEY, google_delegated_admin="admin@cbm.org",
                app_base_url="https://apps.example.org", database_url="")
    base.update(kw)
    return Settings(**base)


class FakeGoogle:
    def __init__(self, drives=(), create_status=200, members=()):
        self.drives = list(drives)
        self.create_status = create_status
        self.members = list(members)
        self.calls = []

    async def stored(self, settings):
        return None

    def mint(self, info, scopes, subject):
        self.calls.append(("mint", scopes[0], subject))
        return "tok"

    async def http(self, method, url, token, params=None, body=None):
        self.calls.append((method, url.rsplit("/v3", 1)[-1], params, body))
        if method == "GET" and url.endswith("/drives"):
            return 200, {"drives": self.drives}
        if method == "POST" and url.endswith("/drives"):
            if self.create_status != 200:
                return self.create_status, {}
            self.drives.append({"id": "d-new", "name": body["name"]})
            return 200, {"id": "d-new"}
        if method == "GET" and url.endswith("/permissions"):
            return 200, {"permissions": [{"emailAddress": m} for m in self.members]}
        if method == "POST" and url.endswith("/permissions"):
            self.members.append(body["emailAddress"])
            return 200, {}
        return 404, {}


def gdeps(fake):
    return actions.GoogleDeps(stored=fake.stored, mint=fake.mint, http=fake.http)


def test_the_drive_dry_run_reads_only():
    fake = FakeGoogle()
    res = run(actions.drive_dry_run(gsettings(), "", gdeps(fake)))
    assert res.ok and "Would create a shared drive" in res.summary and res.proposes == {}
    assert all(c[0] in ("mint", "GET") for c in fake.calls)
    assert ("mint", actions.S_DRIVE, "admin@cbm.org") in fake.calls
    found = run(actions.drive_dry_run(gsettings(), "CBM Documents",
                                      gdeps(FakeGoogle(drives=[{"id": "d1", "name": "CBM Documents"}]))))
    assert found.proposes == {"gdrive_shared_drive_id": "d1"} and "already exists" in found.summary


def test_the_drive_apply_creates_once_adds_the_service_account_and_is_idempotent():
    fake = FakeGoogle()
    res = run(actions.drive_apply(gsettings(), "", gdeps(fake)))
    assert res.ok and res.proposes == {"gdrive_shared_drive_id": "d-new"}
    create = next(c for c in fake.calls if c[0] == "POST" and c[1] == "/drives")
    rid = create[2]["requestId"]
    assert rid == str(uuid.uuid5(uuid.NAMESPACE_URL, "https://apps.example.org|shared-drive|CBM Documents"))
    assert fake.members == ["app@proj.iam.gserviceaccount.com"]
    again = run(actions.drive_apply(gsettings(), "", gdeps(fake)))
    assert again.ok and "Found" in again.summary
    assert sum(1 for c in fake.calls if c[0] == "POST" and c[1] == "/drives") == 1
    assert len(fake.members) == 1


def test_the_drive_refusals_say_why():
    assert "refused to create" in run(actions.drive_apply(gsettings(), "", gdeps(FakeGoogle(create_status=403)))).summary
    assert "No delegated admin" in run(actions.drive_dry_run(gsettings(google_delegated_admin=""), "",
                                                             gdeps(FakeGoogle()))).summary
    assert "No service-account key" in run(actions.drive_dry_run(gsettings(google_service_account_json=""), "",
                                                                 gdeps(FakeGoogle()))).summary


class FakeTwilio:
    def __init__(self, numbers):
        self.numbers = numbers

    async def list_numbers(self):
        return {"incoming_phone_numbers": self.numbers}


def tw(**kw):
    return Settings(sms_account_sid="AC1", sms_auth_token="tok-123456", **kw)


def test_the_twilio_lookup_proposes_only_a_single_texting_number():
    one = [{"phone_number": "+12165550123", "capabilities": {"sms": True}},
           {"phone_number": "+12165550999", "capabilities": {"sms": False}}]
    res = run(actions.twilio_numbers(tw(), "", lambda s: FakeTwilio(one)))
    assert res.ok and res.proposes == {"sms_from_number": "+12165550123"}
    two = [dict(one[0]), {"phone_number": "+12165550124", "capabilities": {"sms": True}}]
    res = run(actions.twilio_numbers(tw(), "", lambda s: FakeTwilio(two)))
    assert not res.ok and "+12165550124" in res.summary and res.proposes == {}
    assert not run(actions.twilio_numbers(tw(), "", lambda s: FakeTwilio([]))).ok
    assert "not set" in run(actions.twilio_numbers(Settings(), "", lambda s: FakeTwilio(one))).summary


class FakeZoom:
    def __init__(self, user=None, error=None):
        self.user, self.error = user, error

    async def get_user(self, host):
        if self.error:
            raise self.error
        return self.user


def zs(**kw):
    base = dict(zoom_account_id="a", zoom_client_id="b", zoom_client_secret="c-secret", zoom_host_email="zweb@x.org")
    base.update(kw)
    return Settings(**base)


def test_the_zoom_host_check():
    ok = run(actions.zoom_host(zs(), "webinars@x.org", lambda s: FakeZoom({"type": 2})))
    assert ok.ok and ok.proposes == {"zoom_host_email": "webinars@x.org"}
    err = Exception("404")
    err.status_code = 404
    assert "no user" in run(actions.zoom_host(zs(), "", lambda s: FakeZoom(error=err))).summary
    assert "not a licensed user" in run(actions.zoom_host(zs(), "", lambda s: FakeZoom({"type": 1}))).summary
    assert "not all set" in run(actions.zoom_host(zs(zoom_client_secret=""), "", lambda s: FakeZoom({}))).summary


def test_run_never_raises_and_knows_only_its_list():
    assert not run(actions.run("crm.apply_plan", Settings(), "", dry=True)).ok

    async def boom(settings, value, deps=None):
        raise RuntimeError("kaput")

    name = "zoom.confirm_host"
    orig = actions.ACTIONS[name]
    actions.ACTIONS[name] = actions.CodedAction(name, "zoom", "x", "x", "x", boom, boom)
    try:
        res = run(actions.run(name, Settings(), "", dry=False))
        assert not res.ok and "kaput" in res.summary
    finally:
        actions.ACTIONS[name] = orig
    assert {a.integration for a in actions.ACTIONS.values()} == {"google_workspace", "twilio", "zoom"}
