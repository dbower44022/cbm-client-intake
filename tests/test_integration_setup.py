"""The setup assistant, phase 7 of the Integrations tab
(prds/integrations-tab-plan.md § 6.5, rulings I11 and I12; the design Doug
approved 11-13-26).

The setup plan's check; the coded actions' dry run, apply, idempotency and
refusals with fake vendor clients; every setup step waiting for confirmation;
a coded action's proposals saved through the checked save path; a manual step
linked to an automatic checklist step stays open until its check passes; the
setting reset in fix plans too.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.config import Settings, get_settings
from integrations import actions, diagnosis, fixplans
from integrations.diagnosis import SETUP, check_plan

from tests.test_integration_diagnosis import (  # noqa: E402
    _app, block, message, scripted, snap, step,
)


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def setup_snap(**kw):
    base = dict(actions=(("zoom.confirm_host", "Confirm the Zoom host", "Checks the host.", "The host"),),
                checklist=[{"id": "decide", "name": "Decide", "state": "open"},
                           {"id": "5.5", "name": "Create the video meeting account", "state": "open"}])
    base.update(kw)
    return snap(**base)


# --- the setup plan's check ---------------------------------------------------------

def test_a_setup_plan_has_a_summary_and_four_kinds_of_step():
    plan, problems = check_plan({"summary": "Sets up Zoom.", "steps": [
        step(key="zoom_host_email", value="webinars@x.org"),
        step("setting_reset", key="zoom_events"),
        step("coded_action", coded_action="zoom.confirm_host", action_input="webinars@x.org"),
        step("manual_step", where="Zoom App Marketplace", action="Build the app", checklist_step="5.5"),
        step("manual_step", where="x", action="y", checklist_step="99.9"),
    ]}, setup_snap(), SETUP)
    assert problems == [], problems
    kinds = [s["kind"] for s in plan["steps"]]
    assert kinds == ["setting_change", "setting_reset", "coded_action", "manual_step", "manual_step", "retest"]
    assert plan["steps"][2] == {"n": 3, "kind": "coded_action", "name": "zoom.confirm_host",
                                "label": "Confirm the Zoom host", "input": "webinars@x.org", "state": "pending"}
    assert plan["steps"][3]["checklistStep"] == "5.5" and plan["steps"][4]["checklistStep"] == ""
    assert plan["diagnosis"] == "Sets up Zoom." and plan["confidence"] == ""


def test_a_coded_action_must_be_offered_and_never_in_a_fix_plan():
    _, problems = check_plan({"summary": "s", "steps": [step("coded_action", coded_action="crm.apply_plan")]},
                             setup_snap(), SETUP)
    assert "not one of the coded actions offered" in " ".join(problems)
    _, problems = check_plan({"diagnosis": "d", "confidence": "likely",
                              "steps": [step("coded_action", coded_action="zoom.confirm_host")]}, setup_snap())
    assert "a fix plan has no coded actions" in " ".join(problems)
    _, problems = check_plan({"summary": "", "steps": []}, setup_snap(), SETUP)
    assert "summary is empty" in " ".join(problems)


def test_a_fix_plan_may_reset_a_setting_even_a_secret():
    plan, problems = check_plan({"diagnosis": "d", "confidence": "likely",
                                 "steps": [step("setting_reset", key="zoom_client_secret")]}, setup_snap())
    assert problems == [] and plan["steps"][0]["kind"] == "setting_reset"


def test_the_setup_call_uses_its_own_prompt_tool_and_opening():
    send, sent = scripted(message([block("tool_use", id="t", name="submit_setup_plan",
                                         input={"summary": "Sets up Zoom.", "steps": []})]))
    out = run(diagnosis.diagnose(None, setup_snap(), model="m", secrets=[], send=send, mode=SETUP))
    assert out.plan and out.plan["steps"][-1]["kind"] == "retest"
    first = sent[0]
    assert first["system"][0]["text"] == diagnosis.SETUP_SYSTEM
    names = {t["name"] for t in first["tools"]}
    assert "submit_setup_plan" in names and "submit_fix_plan" not in names
    opening = first["messages"][0]["content"]
    assert "5.5 Create the video meeting account" in opening and "zoom.confirm_host" in opening
    assert "never ask for one" in diagnosis.SETUP_SYSTEM and "A new secret is always a manual step" in diagnosis.SETUP_SYSTEM


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


# --- the endpoints and the runner --------------------------------------------------------------------

def test_setup_starts_in_the_background_and_reads_back(monkeypatch):
    seen = {}

    async def fake_run(app, plan_id, snapshot, user, mode="fix"):
        seen.update(mode=mode, snap=snapshot)

    monkeypatch.setattr("setup.router._run_diagnosis", fake_run)
    app = _app(monkeypatch, last=None)
    client = TestClient(app)
    resp = client.post("/setup/api/integrations/zoom/setup")
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"]["kind"] == "setup" and seen["mode"] == "setup"
    assert ("zoom.confirm_host", "Confirm the Zoom host") == seen["snap"].actions[0][:2]
    assert client.post("/setup/api/integrations/zoom/setup").status_code == 409
    assert client.get("/setup/api/integrations/zoom/setupplan").json()["plan"]["status"] == fixplans.DIAGNOSING
    # A diagnosis is a separate plan kind with its own lock.
    resp = client.post("/setup/api/integrations/zoom/diagnose")
    assert resp.status_code == 409 and "did not fail" in resp.json()["detail"]


def _steps():
    return [
        {"n": 1, "kind": "setting_change", "key": "zoom_host_email", "label": "Zoom host",
         "value": "webinars@x.org", "state": "pending"},
        {"n": 2, "kind": "coded_action", "name": "zoom.confirm_host", "label": "Confirm the Zoom host",
         "input": "", "state": "pending"},
        {"n": 3, "kind": "manual_step", "where": "Zoom", "action": "Build the app", "copyValue": "",
         "expect": "", "ifNot": "", "checklistStep": "", "state": "pending"},
        {"n": 4, "kind": "retest", "state": "pending"},
    ]


def test_every_setup_step_waits_for_confirmation(monkeypatch):
    saved, runs = [], []

    async def checked_save(request, user, key, body):
        saved.append((key, body.value))
        return {"reverted": None, "confirmBy": None}

    async def fake_action(name, settings, value, *, dry, deps=None):
        runs.append((name, dry))
        return actions.Result(True, "dry: would confirm" if dry else "webinars@x.org is licensed.",
                              {} if dry else {"zoom_host_email": "webinars@x.org"})

    async def retest(integ, settings, deps=None, **kw):
        return {"integration": "zoom", "outcome": "ok", "checks": [], "facts": [],
                "startedAt": "2026-11-13T11:00:00+00:00", "finishedAt": "2026-11-13T11:00:01+00:00",
                "durationMs": 1}

    monkeypatch.setattr("setup.router._checked_save", checked_save)
    monkeypatch.setattr("integrations.actions.run", fake_action)
    monkeypatch.setattr("integrations.testing.run_integration_test", retest)
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put(_steps(), kind="setup", diagnosis_="Sets up Zoom.")
    client = TestClient(app)
    base = f"/setup/api/integrations/zoom/fixplan/{row['id']}"
    plan = client.post(f"{base}/apply", json={"fingerprint": row["fingerprint"]}).json()["plan"]
    assert plan["status"] == fixplans.WAITING and saved == []          # nothing until confirmed
    assert client.post(f"{base}/steps/2/done").status_code == 409       # only the step it waits at
    plan = client.post(f"{base}/steps/1/done").json()["plan"]
    assert saved == [("zoom_host_email", "webinars@x.org")] and plan["status"] == fixplans.WAITING
    assert plan["steps"][1]["dryRun"]["summary"] == "dry: would confirm" and runs == [("zoom.confirm_host", True)]
    plan = client.post(f"{base}/steps/2/done").json()["plan"]
    assert runs[-1] == ("zoom.confirm_host", False)
    assert saved[-1] == ("zoom_host_email", "webinars@x.org") and plan["steps"][1]["state"] == "done"
    plan = client.post(f"{base}/steps/3/done").json()["plan"]
    assert plan["steps"][2]["state"] == "done" and plan["status"] == fixplans.WAITING
    plan = client.post(f"{base}/steps/4/done").json()["plan"]
    assert plan["status"] == fixplans.APPLIED and plan["steps"][3]["outcome"] == "ok"


def test_a_failed_setup_step_stays_open_with_the_reason(monkeypatch):
    async def refused(request, user, key, body):
        raise HTTPException(status_code=400, detail="Zoom host was not saved — no such user")

    monkeypatch.setattr("setup.router._checked_save", refused)
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put(_steps(), kind="setup", diagnosis_="Sets up Zoom.")
    client = TestClient(app)
    base = f"/setup/api/integrations/zoom/fixplan/{row['id']}"
    client.post(f"{base}/apply", json={"fingerprint": row["fingerprint"]})
    plan = client.post(f"{base}/steps/1/done").json()["plan"]
    assert plan["status"] == fixplans.WAITING
    assert plan["steps"][0]["state"] == "pending" and "no such user" in plan["steps"][0]["detail"]


def test_a_manual_step_linked_to_an_open_automatic_check_stays_open(monkeypatch):
    app = _app(monkeypatch)
    steps = [{"n": 1, "kind": "manual_step", "where": "Zoom App Marketplace", "action": "Build the app",
              "copyValue": "", "expect": "", "ifNot": "", "checklistStep": "5.5", "state": "pending"},
             {"n": 2, "kind": "retest", "state": "pending"}]
    row = app.state.fix_plan_store.put(steps, kind="setup", diagnosis_="Sets up Zoom.")
    client = TestClient(app)
    base = f"/setup/api/integrations/zoom/fixplan/{row['id']}"
    client.post(f"{base}/apply", json={"fingerprint": row["fingerprint"]})
    plan = client.post(f"{base}/steps/1/done").json()["plan"]
    assert plan["steps"][0]["state"] == "pending"
    assert "Not done yet" in plan["steps"][0]["detail"] and "not set" in plan["steps"][0]["detail"]


def test_a_fix_plan_resets_a_setting_straight_through(monkeypatch):
    resets = []

    async def checked_reset(request, user, key, reason):
        resets.append(key)
        if key == "zoom_events":
            raise HTTPException(status_code=404, detail="'zoom_events' was not overridden.")

    async def retest(integ, settings, deps=None, **kw):
        return {"integration": "zoom", "outcome": "failed", "checks": [], "facts": [],
                "startedAt": "2026-11-13T11:00:00+00:00", "finishedAt": "2026-11-13T11:00:01+00:00",
                "durationMs": 1}

    monkeypatch.setattr("setup.router._checked_reset", checked_reset)
    monkeypatch.setattr("integrations.testing.run_integration_test", retest)
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put([
        {"n": 1, "kind": "setting_reset", "key": "zoom_host_email", "label": "Zoom host", "state": "pending"},
        {"n": 2, "kind": "setting_reset", "key": "zoom_events", "label": "Zoom webinar provisioning", "state": "pending"},
        {"n": 3, "kind": "retest", "state": "pending"}])
    plan = TestClient(app).post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/apply",
                                json={"fingerprint": row["fingerprint"]}).json()["plan"]
    assert resets == ["zoom_host_email", "zoom_events"] and plan["status"] == fixplans.APPLIED
    assert "already" in plan["steps"][1]["detail"] and "still fails" in plan["steps"][2]["detail"]


def test_the_page_carries_the_setup_plan(monkeypatch):
    app = _app(monkeypatch)
    app.state.fix_plan_store.put(_steps(), kind="setup", diagnosis_="Sets up Zoom.")
    page = TestClient(app).get("/setup/api/settings").json()
    zoom = next(i for i in page["integrations"] if i["key"] == "zoom")
    assert zoom["setupPlan"]["kind"] == "setup" and zoom["fixPlan"] is None
