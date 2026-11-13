"""The setup checklist, phase 4 of the Integrations tab
(prds/integrations-tab-plan.md § 4; the mapping Doug approved 11-13-26).

The step-file keys parse and name only real checks; the new keys never change
the rendered guide; each check's done, open and unknown paths; the hand-tick
endpoint refuses automatic steps; ticks reach the History tab.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, get_settings
from core.settings_registry import BY_KEY as SETTINGS_BY_KEY
from integrations import checklist
from integrations.checklist import DONE, OPEN, UNKNOWN, State
from integrations.registry import BY_KEY as INTEGRATIONS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _renderer():
    spec = importlib.util.spec_from_file_location(
        "render_deployment_guide", ROOT / "scripts" / "render_deployment_guide.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the step files ---------------------------------------------------------------

def test_every_key_names_a_real_integration_check_and_setting():
    steps = checklist.load_steps()
    assert checklist.problems(steps, set(INTEGRATIONS), set(SETTINGS_BY_KEY)) == []


def test_every_integration_has_steps_from_the_guide():
    for key in INTEGRATIONS:
        assert checklist.steps_for(key), f"{key} has no setup steps"


def test_the_approved_mapping():
    by_id = {s.id: s for s in checklist.load_steps()}
    assert by_id["8.4"].integrations == ("google_workspace", "zoom")
    assert by_id["5.5"].auto == tuple(f"setting_set:{k}" for k in (
        "zoom_account_id", "zoom_client_id", "zoom_client_secret", "zoom_host_email"))
    assert by_id["11.19"].auto == ("mailing_connected",)
    assert by_id["10.3"].auto == ("test_passed:google_workspace",)
    assert by_id["5.16"].manual and by_id["11.21"].manual
    for new in ("5.13", "5.14", "5.15", "5.16", "5.17", "10.6", "11.19", "11.20", "11.21"):
        assert new in by_id, new
    assert [s.id for s in checklist.steps_for("twilio")] == ["5.15", "5.16", "11.21"]
    assert "4.1" not in by_id and "4.13" not in by_id


def test_problems_catches_bad_names():
    bad = (checklist.Step("1.1", "x", 1, "s", ("nope",), ("setting_set:nope", "test_passed:nope", "magic")),)
    found = checklist.problems(bad, set(INTEGRATIONS), set(SETTINGS_BY_KEY))
    assert len(found) == 4


def test_the_new_keys_never_change_the_rendered_guide():
    r = _renderer()
    for stage in r.load():
        stripped = copy.deepcopy(stage)
        for step in stripped["steps"]:
            step.pop("integration", None)
            (step.get("check") or {}).pop("auto", None)
        assert r.render_stage(stage) == r.render_stage(stripped), stage["stage"]


def test_the_guide_is_rendered_and_its_information_check_passes():
    r = _renderer()
    stages = r.load()
    assert r.information_check(stages) == []
    for path, text in r.build(stages).items():
        assert path.read_text(encoding="utf-8") == text, f"stale: {path.name}"


# --- the checks ------------------------------------------------------------------------

def st(**kw):
    settings = kw.pop("settings", Settings())
    return State(settings=settings, **kw)


def test_setting_set_paths_and_the_stored_email_setup():
    assert checklist.evaluate("setting_set:zoom_client_id", st(settings=Settings(zoom_client_id="x")))[0] == DONE
    state, reason = checklist.evaluate("setting_set:zoom_client_id", st())
    assert state == OPEN and "not set" in reason
    stored = st(stored_google={"google_service_account_json": True})
    assert checklist.evaluate("setting_set:google_service_account_json", stored)[0] == DONE
    assert checklist.evaluate("setting_set:google_delegated_admin", stored)[0] == OPEN


def test_test_passed_paths():
    name = "test_passed:zoom"
    assert checklist.evaluate(name, st())[0] == OPEN
    run = {"outcome": "ok", "finishedAt": "2026-11-13T06:00:00+00:00"}
    assert checklist.evaluate(name, st(test_runs={"zoom": run}))[0] == DONE
    for outcome in ("failed", "unknown"):
        state, reason = checklist.evaluate(name, st(test_runs={"zoom": dict(run, outcome=outcome)}))
        assert state == OPEN and "2026-11-13 06:00" in reason


def test_mailing_connected_paths_and_an_unknown_check():
    assert checklist.evaluate("mailing_connected", st(mailing_connected=True))[0] == DONE
    assert checklist.evaluate("mailing_connected", st(mailing_connected=False))[0] == OPEN
    assert checklist.evaluate("mailing_connected", st())[0] == UNKNOWN
    assert checklist.evaluate("magic", st())[0] == UNKNOWN


def test_the_decide_row_needs_a_deliberate_choice(monkeypatch):
    zoom = INTEGRATIONS["zoom"]
    monkeypatch.delenv("ZOOM_IN_USE", raising=False)
    row = checklist.build(zoom, st())["rows"][0]
    assert row["id"] == "decide" and row["state"] == OPEN
    row = checklist.build(zoom, st(overrides={"zoom_in_use": object()}))["rows"][0]
    assert row["state"] == DONE and "in use" in row["reason"]
    monkeypatch.setenv("ZOOM_IN_USE", "false")
    row = checklist.build(zoom, st(settings=Settings(zoom_in_use=False)))["rows"][0]
    assert row["state"] == DONE and "not used" in row["reason"]


def test_espocrm_has_no_decide_row_and_every_list_ends_with_the_test():
    rows = checklist.build(INTEGRATIONS["espocrm"], st())["rows"]
    assert rows[0]["id"] != "decide" and rows[-1]["id"] == "test"


def test_a_manual_step_is_done_only_when_ticked_and_a_shared_step_is_one_step():
    tick = {"stepId": "8.4", "ticked": True, "by": "adm", "at": "2026-11-13T10:00:00+00:00"}
    for key in ("google_workspace", "zoom"):
        row = next(r for r in checklist.build(INTEGRATIONS[key], st(ticks={"8.4": tick}))["rows"]
                   if r["id"] == "8.4")
        assert row["state"] == DONE and row["tick"]["by"] == "adm"
    untick = dict(tick, ticked=False)
    row = next(r for r in checklist.build(INTEGRATIONS["zoom"], st(ticks={"8.4": untick}))["rows"]
               if r["id"] == "8.4")
    assert row["state"] == OPEN and row["tick"] is None
    assert row["shared"] == ["google_workspace"]


def test_an_automatic_step_ticks_itself_only_when_every_check_passes():
    s = Settings(zoom_account_id="a", zoom_client_id="b", zoom_client_secret="c", zoom_host_email="")
    row = next(r for r in checklist.build(INTEGRATIONS["zoom"], st(settings=s))["rows"] if r["id"] == "5.5")
    assert row["automatic"] and row["state"] == OPEN and "host" in row["reason"].lower()
    s = Settings(zoom_account_id="a", zoom_client_id="b", zoom_client_secret="c",
                 zoom_host_email="webinars@x.org")
    row = next(r for r in checklist.build(INTEGRATIONS["zoom"], st(settings=s))["rows"] if r["id"] == "5.5")
    assert row["state"] == DONE
    built = checklist.build(INTEGRATIONS["zoom"], st(settings=s))
    assert built["total"] == 4 and built["done"] == 1


def test_a_secret_value_never_reaches_the_checklist():
    secret = "sk-very-secret-value-123"
    s = Settings(anthropic_api_key=secret)
    text = repr(checklist.build(INTEGRATIONS["anthropic"], st(settings=s)))
    assert secret not in text


# --- the endpoint, the page and the history ------------------------------------------------

from tests.test_integration_test import _ADMIN, _STAFF, FakeRuns, NoSettings  # noqa: E402


class FakeTicks:
    def __init__(self):
        self.rows = []

    async def record(self, step_id, integration, ticked, *, actor_id="", actor=""):
        row = {"stepId": step_id, "integration": integration, "ticked": ticked, "by": actor,
               "at": f"2026-11-13T10:0{len(self.rows)}:00+00:00"}
        self.rows.append(row)
        return row

    async def current(self):
        out = {}
        for r in self.rows:
            out[r["stepId"]] = r
        return out

    async def history(self, limit=50):
        return list(reversed(self.rows))[:limit]


class History(NoSettings):
    async def history(self, key="", limit=50):
        return [{"key": "zoom_events", "oldValue": "false", "newValue": "true", "action": "set",
                 "reason": "", "actor": "adm", "at": "2026-11-13T09:00:00+00:00"}]


def _app(monkeypatch, env, user=_ADMIN, ticks=True):
    from core.app import create_app
    from forms import info_request

    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("SETUP_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("setup.router.current_user", lambda r: user)
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.settings_store = History()
    app.state.job_store = None
    app.state.integration_test_store = FakeRuns()
    app.state.integration_tick_store = FakeTicks() if ticks else None
    app.state.mailing_store = None
    logged = []

    async def log_action(**kw):
        logged.append(kw)

    monkeypatch.setattr("setup.router.action_log.log_action", log_action)
    app.state.logged = logged
    return app


def test_ticking_a_manual_step_is_kept_logged_and_shown(monkeypatch):
    app = _app(monkeypatch, {"INTEGRATIONS_TAB": "true"})
    client = TestClient(app)
    resp = client.post("/setup/api/integrations/twilio/checklist/5.16", json={"ticked": True})
    assert resp.status_code == 200, resp.text
    page = resp.json()["page"]
    twilio = next(i for i in page["integrations"] if i["key"] == "twilio")
    row = next(r for r in twilio["checklist"]["rows"] if r["id"] == "5.16")
    assert row["state"] == DONE and row["tick"]["by"] == "adm"
    assert app.state.logged[-1]["action"] == "Setup Checklist Step Ticked"
    assert app.state.logged[-1]["details"] == {"integration": "twilio", "step": "5.16", "ticked": True}
    resp = client.post("/setup/api/integrations/twilio/checklist/5.16", json={"ticked": False})
    row = next(r for r in next(i for i in resp.json()["page"]["integrations"] if i["key"] == "twilio")
               ["checklist"]["rows"] if r["id"] == "5.16")
    assert row["state"] == OPEN
    assert app.state.logged[-1]["action"] == "Setup Checklist Step Unticked"


def test_an_automatic_step_and_the_framing_rows_cannot_be_ticked(monkeypatch):
    client = TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "true"}))
    for step in ("5.5", "decide", "test"):
        resp = client.post(f"/setup/api/integrations/zoom/checklist/{step}", json={"ticked": True})
        assert resp.status_code == 409, step
        assert "ticks itself" in resp.json()["detail"]
    assert client.post("/setup/api/integrations/zoom/checklist/5.16", json={}).status_code == 404
    assert client.post("/setup/api/integrations/nope/checklist/5.16", json={}).status_code == 404


def test_the_tick_endpoint_is_admin_only_dark_and_needs_a_database(monkeypatch):
    assert TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "true"}, user=_STAFF)).post(
        "/setup/api/integrations/twilio/checklist/5.16", json={}).status_code == 403
    assert TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "false"})).post(
        "/setup/api/integrations/twilio/checklist/5.16", json={}).status_code == 404
    resp = TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "true"}, ticks=False)).post(
        "/setup/api/integrations/twilio/checklist/5.16", json={})
    assert resp.status_code == 400 and "database" in resp.json()["detail"]


def test_ticks_join_the_history_tab_only_with_the_switch_on(monkeypatch):
    app = _app(monkeypatch, {"INTEGRATIONS_TAB": "true"})
    client = TestClient(app)
    client.post("/setup/api/integrations/google_workspace/checklist/4.11", json={"ticked": True})
    rows = client.get("/setup/api/history").json()["history"]
    assert rows[0]["key"] == "checklist 4.11" and rows[0]["newValue"] == "ticked"
    assert rows[0]["actor"] == "adm" and rows[1]["key"] == "zoom_events"
    only = client.get("/setup/api/history?key=checklist").json()["history"]
    assert any(r["key"] == "checklist 4.11" for r in only)
    off = TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "false"}))
    assert [r["key"] for r in off.get("/setup/api/history").json()["history"]] == ["zoom_events"]


def test_every_sub_tab_carries_its_checklist_and_the_page_reads_no_outside_service(monkeypatch):
    app = _app(monkeypatch, {"INTEGRATIONS_TAB": "true"})

    class Boom:
        async def get(self):
            raise RuntimeError("db down")

    app.state.mailing_store = Boom()
    page = TestClient(app).get("/setup/api/settings").json()
    for integ in page["integrations"]:
        cl = integ["checklist"]
        assert cl["rows"] and cl["total"] == len(cl["rows"]), integ["key"]
        assert integ["ticksStored"] is True
    cc = next(i for i in page["integrations"] if i["key"] == "constant_contact")
    row = next(r for r in cc["checklist"]["rows"] if r["id"] == "11.19")
    assert row["state"] == UNKNOWN


def test_the_page_never_reads_ticks_with_the_switch_off(monkeypatch):
    app = _app(monkeypatch, {"INTEGRATIONS_TAB": "false"})

    class Exploding(FakeTicks):
        async def current(self):
            raise AssertionError("read with the switch off")

    app.state.integration_tick_store = Exploding()
    page = TestClient(app).get("/setup/api/settings").json()
    assert "integrations" not in page


def test_the_tick_table_is_cleared_by_the_sandbox_reset():
    from core.sandbox_reset import RESET_TABLES

    assert "integration_checklist_tick" in RESET_TABLES


def test_the_tick_table_follows_the_evaluation_tables():
    text = (ROOT / "alembic" / "versions" / "0045_integration_checklist_tick.py").read_text()
    assert 'down_revision = "0044_evaluation_links"' in text
