"""The diagnosis agent and fix plans, phase 6 of the Integrations tab
(prds/integrations-tab-plan.md § 6; the design Doug approved 11-13-26).

With a fake Anthropic client: no secret in anything sent to the Claude API;
the call's settings; a refused plan goes back and a good one is kept; no plan
when the model declines, fails or never submits; the plan check; approval of
that exact plan; setting changes through the checked save path; a manual step
pauses; a failed step stops; the re-test ends it; the monthly budget.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.config import Settings, get_settings
from integrations import diagnosis, events, fixplans
from integrations.diagnosis import Snapshot, check_plan, run_tool

SECRET = "sk-very-secret-value-123"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def snap(**kw):
    base = dict(
        integration="zoom", name="Zoom",
        test={"outcome": "failed", "checks": [{"key": "host", "label": "The host user",
                                                "outcome": "failed", "detail": "No user zweb@x.org"}],
              "facts": []},
        settings=diagnosis.settings_rows([
            {"key": "zoom_host_email", "label": "Zoom host", "value": "zweb@x.org", "source": "deployment",
             "override": None},
            {"key": "zoom_client_secret", "label": "Zoom client secret", "value": "••••", "isSet": True,
             "source": "override", "override": {"updatedAt": "2026-11-13T10:00:00+00:00"}},
            {"key": "zoom_events", "label": "Zoom webinar provisioning", "value": "false", "source": "default",
             "override": None},
        ]),
        checklist=[{"id": "5.5", "name": "Create the video meeting account", "state": "done"}],
        runbooks=("EVENTS-SETUP.md",), errors=[{"source": "attendance pull", "message": "x", "at": "t"}],
        doc_sites=("developers.zoom.us",),
    )
    base.update(kw)
    return Snapshot(**base)


# --- what the agent may read ----------------------------------------------------------

def test_a_secret_is_only_set_or_not_set_with_when_it_changed():
    rows = {r["key"]: r for r in snap().settings}
    assert rows["zoom_client_secret"]["value"] == "set"
    assert rows["zoom_client_secret"]["lastChanged"] == "2026-11-13T10:00:00+00:00"
    assert rows["zoom_client_secret"]["editable"] is False
    assert rows["zoom_host_email"]["value"] == "zweb@x.org" and rows["zoom_host_email"]["editable"]


def test_the_read_only_tools():
    s = snap()
    assert run_tool("get_test_result", {}, s)[0]["outcome"] == "failed"
    assert "editable" not in run_tool("get_settings", {}, s)[0][0]
    assert run_tool("get_recent_errors", {}, s)[0][0]["source"] == "attendance pull"
    step, err = run_tool("read_guide_step", {"step_id": "5.5"}, s)
    assert not err and "Zoom" in json.dumps(step)
    assert run_tool("read_guide_step", {"step_id": "9.7"}, s)[1] is True
    text, err = run_tool("read_runbook", {"name": "EVENTS-SETUP.md"}, s)
    assert not err and len(text) <= diagnosis.RUNBOOK_MAX + 20
    assert run_tool("read_runbook", {"name": "../.env"}, s)[1] is True
    assert run_tool("drop_tables", {}, s)[1] is True


def test_the_web_tools_are_held_to_the_documentation_sites():
    tools = {t["name"]: t for t in diagnosis.tools_for(snap())}
    assert tools["web_search"]["allowed_domains"] == ["developers.zoom.us"]
    assert tools["web_fetch"]["allowed_domains"] == ["developers.zoom.us"]
    assert tools["web_search"]["max_uses"] == diagnosis.MAX_SEARCHES
    assert tools["submit_fix_plan"]["strict"] is True
    assert "web_search" not in {t["name"] for t in diagnosis.tools_for(snap(doc_sites=()))}


def test_every_integration_has_documentation_sites():
    from integrations.registry import INTEGRATIONS

    assert all(i.doc_sites for i in INTEGRATIONS)
    google = next(i for i in INTEGRATIONS if i.key == "google_workspace")
    assert "knowledge.workspace.google.com" in google.doc_sites


# --- the plan check ---------------------------------------------------------------------------

def step(kind="setting_change", **kw):
    base = dict(kind=kind, key="", value="", where="", action="", copy_value="", expect="", if_not="")
    base.update(kw)
    return base


def test_a_good_plan_is_kept_with_the_retest_last():
    plan, problems = check_plan({"diagnosis": "The host is wrong.", "confidence": "likely", "steps": [
        step(key="zoom_host_email", value="webinars@x.org"),
        step("manual_step", where="Zoom, Users", action="Add the user", copy_value="webinars@x.org")]}, snap())
    assert problems == []
    assert [s["kind"] for s in plan["steps"]] == ["setting_change", "manual_step", "retest"]
    assert plan["steps"][0]["label"] == "Zoom host" and plan["steps"][1]["copyValue"] == "webinars@x.org"


@pytest.mark.parametrize("bad,word", [
    (step(key="zoom_client_secret", value="x"), "secret"),
    (step(key="espo_api_key", value="x"), "not a setting on this sub-tab"),
    (step("manual_step"), "needs its action"),
    (step("delete_everything"), "unknown kind"),
])
def test_a_bad_step_is_refused(bad, word):
    plan, problems = check_plan({"diagnosis": "d", "confidence": "likely", "steps": [bad]}, snap())
    assert plan is None and word in " ".join(problems)


def test_an_empty_diagnosis_a_bad_confidence_and_too_many_steps_are_refused():
    plan, problems = check_plan({"diagnosis": " ", "confidence": "certain",
                                 "steps": [step("manual_step", action="a")] * 13}, snap())
    assert plan is None and len(problems) == 3


def test_the_fingerprint_ignores_progress():
    steps = [{"n": 1, "kind": "retest", "state": "pending"}]
    done = [{"n": 1, "kind": "retest", "state": "done", "detail": "ok", "doneBy": "a", "doneAt": "t"}]
    assert fixplans.fingerprint("d", steps) == fixplans.fingerprint("d", done)
    assert fixplans.fingerprint("d", steps) != fixplans.fingerprint("e", steps)


# --- the call -------------------------------------------------------------------------------------

def block(type_, **kw):
    return SimpleNamespace(type=type_, **kw)


def message(content, stop="tool_use", usage=None):
    return SimpleNamespace(content=content, stop_reason=stop, model="claude-opus-5-5",
                           usage=usage or {"input_tokens": 1000, "output_tokens": 500})


GOOD = {"diagnosis": "The host address is wrong.", "confidence": "verified",
        "steps": [step(key="zoom_host_email", value="webinars@x.org")]}


def scripted(*responses):
    sent = []

    async def send(client, kwargs):
        sent.append(copy.deepcopy(kwargs))
        r = responses[len(sent) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    return send, sent


def test_a_diagnosis_reads_then_submits_and_never_sends_a_secret():
    send, sent = scripted(
        message([block("tool_use", id="t1", name="get_test_result", input={}),
                 block("tool_use", id="t2", name="get_settings", input={})]),
        message([block("tool_use", id="t3", name="submit_fix_plan",
                        input={**GOOD, "steps": [step(key="zoom_client_secret", value="x")]})]),
        message([block("tool_use", id="t4", name="submit_fix_plan", input=GOOD)]),
    )
    s = snap()
    s.test["checks"][0]["detail"] = f"vendor echoed {SECRET}"
    out = run(diagnosis.diagnose(None, s, model="claude-opus-5-5", secrets=[SECRET], send=send))
    assert out.plan and out.plan["steps"][0]["key"] == "zoom_host_email" and out.error == ""
    assert out.cost > 0 and out.usage["input_tokens"] == 3000
    assert SECRET not in json.dumps(sent, default=str)
    first = sent[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert first["betas"] == [diagnosis.FALLBACK_BETA] and first["output_config"] == {"effort": "high"}
    assert "thinking" not in first  # adaptive is the model's default
    refused = sent[2]["messages"][-1]["content"][0]
    assert refused["is_error"] and "secret" in refused["content"]


def test_no_plan_when_the_model_declines_fails_or_never_submits():
    send, _ = scripted(message([], stop="refusal"))
    assert "declined" in run(diagnosis.diagnose(None, snap(), model="m", secrets=[], send=send)).error
    send, _ = scripted(RuntimeError("overloaded"))
    out = run(diagnosis.diagnose(None, snap(), model="m", secrets=[], send=send))
    assert out.plan is None and "overloaded" in out.error
    text = message([block("text", text="I think it is the host.")], stop="end_turn")
    send, sent = scripted(text, text)
    out = run(diagnosis.diagnose(None, snap(), model="m", secrets=[], send=send))
    assert out.plan is None and "without submitting" in out.error
    assert sent[1]["messages"][-1]["content"].startswith("Call submit_fix_plan")


def test_a_paused_server_turn_is_resumed():
    send, sent = scripted(message([block("server_tool_use", id="s1", name="web_search", input={})],
                                  stop="pause_turn"),
                          message([block("tool_use", id="t1", name="submit_fix_plan", input=GOOD)]))
    out = run(diagnosis.diagnose(None, snap(), model="m", secrets=[], send=send))
    assert out.plan and len(sent) == 2


def test_a_refused_plan_three_times_ends_the_diagnosis():
    bad = message([block("tool_use", id="t", name="submit_fix_plan",
                         input={**GOOD, "steps": [step(key="nope", value="1")]})])
    send, _ = scripted(bad, bad, bad)
    out = run(diagnosis.diagnose(None, snap(), model="m", secrets=[], send=send))
    assert out.plan is None and "refused" in out.error


def test_an_expensive_diagnosis_stops_itself():
    big = {"input_tokens": 0, "output_tokens": 400_000}
    send, _ = scripted(message([block("tool_use", id="t1", name="get_settings", input={})], usage=big))
    out = run(diagnosis.diagnose(None, snap(), model="claude-opus-5-5", secrets=[], send=send))
    assert out.plan is None and "limit" in out.error


# --- recent errors ----------------------------------------------------------------------------------

def test_a_recent_error_is_scrubbed_and_never_raises():
    s = Settings(zoom_client_secret=SECRET)
    assert SECRET not in events.clean(s, f"401 with {SECRET}\nsecond line")
    run(events.record_event(Settings(database_url=""), "zoom", "x", "boom"))  # no database: nothing


# --- the endpoints -------------------------------------------------------------------------------------

from tests.test_integration_test import _ADMIN, FakeRuns, NoSettings  # noqa: E402


class FakePlans:
    def __init__(self):
        self.rows = {}
        self.spent = 0.0

    async def create(self, **kw):
        row = fixplans.public({
            "id": f"p{len(self.rows) + 1}", "integration": kw["integration"], "kind": kw.get("kind", "fix"),
            "test_run_id": kw.get("test_run_id"), "status": kw["status"], "diagnosis": kw.get("diagnosis", ""),
            "confidence": "", "steps": kw.get("steps") or [], "fingerprint": None, "model": "", "cost": 0.0,
            "usage": {}, "error": None, "created_by": kw.get("created_by"),
            "created_at": datetime.now(timezone.utc), "approved_by": None, "approved_at": None,
            "finished_at": None})
        self.rows[row["id"]] = row
        return dict(row)

    def put(self, steps, status=fixplans.PROPOSED, diagnosis_="The host is wrong.", kind="fix"):
        row = run(self.create(integration="zoom", status=status, kind=kind))
        row.update(diagnosis=diagnosis_, steps=steps, fingerprint=fixplans.fingerprint(diagnosis_, steps))
        self.rows[row["id"]] = row
        return row

    async def get(self, plan_id):
        r = self.rows.get(plan_id)
        return copy.deepcopy(r) if r else None

    async def latest(self, integration, kind="fix"):
        rows = [r for r in self.rows.values() if r["integration"] == integration and r["kind"] == kind]
        return copy.deepcopy(rows[-1]) if rows else None

    async def latest_all(self, kind="fix"):
        return {r["integration"]: r for r in self.rows.values() if r["kind"] == kind}

    async def update(self, plan_id, **values):
        names = {"approved_by": "approvedBy", "finished_at": "finishedAt"}
        for k, v in values.items():
            self.rows[plan_id][names.get(k, k)] = v

    async def complete(self, plan_id, **kw):
        self.rows[plan_id].update(status=kw["status"], steps=kw.get("steps") or [], error=kw.get("error", ""))

    async def spent_this_month(self, **kw):
        return self.spent


def _app(monkeypatch, *, last="failed", key=SECRET, budget="25"):
    from core.app import create_app
    from forms import info_request

    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("SETUP_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("INTEGRATIONS_TAB", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    monkeypatch.setenv("INTEGRATION_AGENT_MONTHLY_BUDGET", budget)
    monkeypatch.setattr("setup.router.current_user", lambda r: _ADMIN)
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.settings_store = NoSettings()
    app.state.job_store = None
    runs = FakeRuns()
    if last:
        run(runs.record({"integration": "zoom", "outcome": last, "checks": [], "facts": [],
                         "startedAt": "2026-11-13T10:00:00+00:00", "finishedAt": "2026-11-13T10:00:01+00:00",
                         "durationMs": 1}))
    app.state.integration_test_store = runs
    app.state.integration_tick_store = None
    app.state.mailing_store = None
    app.state.fix_plan_store = FakePlans()
    logged = []

    async def log_action(**kw):
        logged.append(kw)

    monkeypatch.setattr("setup.router.action_log.log_action", log_action)

    async def no_readiness(settings, *a, **k):
        return {"features": []}

    monkeypatch.setattr("setup.readiness.readiness_payload", no_readiness)
    app.state.logged = logged
    return app


def test_diagnose_is_refused_without_a_failure_a_key_or_budget(monkeypatch):
    assert TestClient(_app(monkeypatch, last="ok")).post(
        "/setup/api/integrations/zoom/diagnose").status_code == 409
    assert TestClient(_app(monkeypatch, last=None)).post(
        "/setup/api/integrations/zoom/diagnose").status_code == 409
    resp = TestClient(_app(monkeypatch, key="")).post("/setup/api/integrations/zoom/diagnose")
    assert resp.status_code == 409 and "Anthropic API key" in resp.json()["detail"]
    app = _app(monkeypatch)
    app.state.fix_plan_store.spent = 25.0
    resp = TestClient(app).post("/setup/api/integrations/zoom/diagnose")
    assert resp.status_code == 409 and "monthly budget" in resp.json()["detail"]


def test_diagnose_starts_one_at_a_time_and_the_snapshot_holds_no_secret(monkeypatch):
    seen = {}

    async def fake_run(app, plan_id, snapshot, user, mode="fix"):
        seen["snap"] = snapshot

    monkeypatch.setattr("setup.router._run_diagnosis", fake_run)
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "zs-very-secret-999")
    app = _app(monkeypatch)
    client = TestClient(app)
    resp = client.post("/setup/api/integrations/zoom/diagnose")
    assert resp.status_code == 200 and resp.json()["plan"]["status"] == fixplans.DIAGNOSING
    assert client.post("/setup/api/integrations/zoom/diagnose").status_code == 409
    text = json.dumps(seen["snap"].__dict__, default=str)
    assert "zs-very-secret-999" not in text and SECRET not in text
    assert seen["snap"].doc_sites == ("developers.zoom.us",)


def test_the_background_diagnosis_stores_the_plan(monkeypatch):
    from setup import router

    app = _app(monkeypatch)
    plans = app.state.fix_plan_store
    plan = run(plans.create(integration="zoom", status=fixplans.DIAGNOSING))

    class Stream:
        def __init__(self, msg):
            self.msg = msg

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_final_message(self):
            return self.msg

    class Client:
        def __init__(self):
            self.beta = SimpleNamespace(messages=SimpleNamespace(
                stream=lambda **kw: Stream(message([block("tool_use", id="t", name="submit_fix_plan", input=GOOD)]))))

    app.state.anthropic_client = Client
    monkeypatch.setattr("setup.router._log", lambda *a, **k: asyncio.sleep(0))
    run(router._run_diagnosis(app, plan["id"], snap(), _ADMIN))
    assert plans.rows[plan["id"]]["status"] == fixplans.PROPOSED
    assert plans.rows[plan["id"]]["steps"][-1]["kind"] == "retest"


def _setting(n=1):
    return {"n": n, "kind": "setting_change", "key": "zoom_host_email", "label": "Zoom host",
            "value": "webinars@x.org", "state": "pending"}


def _manual(n):
    return {"n": n, "kind": "manual_step", "where": "Zoom", "action": "Add the user", "copyValue": "",
            "expect": "", "ifNot": "", "state": "pending"}


def _retest(n):
    return {"n": n, "kind": "retest", "state": "pending"}


def test_apply_needs_that_exact_plan(monkeypatch):
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put([_setting(), _retest(2)])
    client = TestClient(app)
    resp = client.post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/apply", json={"fingerprint": "x"})
    assert resp.status_code == 409 and "changed" in resp.json()["detail"]


def test_apply_saves_through_the_checked_path_pauses_continues_and_retests(monkeypatch):
    saved = []

    async def checked_save(request, user, key, body):
        saved.append((key, body.value, body.reason, user["userName"]))
        return {"reverted": None, "confirmBy": None}

    async def retest(integ, settings, deps=None, **kw):
        return {"integration": "zoom", "outcome": "ok", "checks": [], "facts": [],
                "startedAt": "2026-11-13T11:00:00+00:00", "finishedAt": "2026-11-13T11:00:01+00:00",
                "durationMs": 1}

    monkeypatch.setattr("setup.router._checked_save", checked_save)
    monkeypatch.setattr("integrations.testing.run_integration_test", retest)
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put([_setting(), _manual(2), _retest(3)])
    client = TestClient(app)
    resp = client.post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/apply",
                       json={"fingerprint": row["fingerprint"]})
    assert resp.status_code == 200, resp.text
    plan = resp.json()["plan"]
    assert plan["status"] == fixplans.WAITING and plan["approvedBy"] == "adm"
    assert saved == [("zoom_host_email", "webinars@x.org", f"applied from a fix plan ({row['id'][:8]})", "adm")]
    assert client.post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/steps/3/done").status_code == 409
    resp = client.post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/steps/2/done")
    plan = resp.json()["plan"]
    assert plan["status"] == fixplans.APPLIED
    assert plan["steps"][2]["outcome"] == "ok" and "passes" in plan["steps"][2]["detail"]
    actions = [l["action"] for l in app.state.logged]
    assert fixplans.ACT_PLAN_APPLIED in actions and fixplans.ACT_PLAN_STEP in actions


def test_a_refused_setting_change_stops_the_plan(monkeypatch):
    async def refused(request, user, key, body):
        raise HTTPException(status_code=400, detail="Zoom host was not saved — Zoom has no such user")

    monkeypatch.setattr("setup.router._checked_save", refused)
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put([_setting(), _retest(2)])
    plan = TestClient(app).post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/apply",
                                json={"fingerprint": row["fingerprint"]}).json()["plan"]
    assert plan["status"] == fixplans.STOPPED
    assert plan["steps"][0]["state"] == "failed" and "no such user" in plan["steps"][0]["detail"]
    assert plan["steps"][1]["state"] == "pending"


def test_a_change_reverted_by_the_post_apply_check_stops_the_plan(monkeypatch):
    async def reverted(request, user, key, body):
        return {"reverted": "the CRM stopped answering", "confirmBy": None}

    monkeypatch.setattr("setup.router._checked_save", reverted)
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put([_setting(), _retest(2)])
    plan = TestClient(app).post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/apply",
                                json={"fingerprint": row["fingerprint"]}).json()["plan"]
    assert plan["status"] == fixplans.STOPPED and "Reverted" in plan["steps"][0]["detail"]


def test_a_plan_can_be_discarded_and_then_not_applied(monkeypatch):
    app = _app(monkeypatch)
    row = app.state.fix_plan_store.put([_manual(1), _retest(2)])
    client = TestClient(app)
    assert client.post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/discard").json()["plan"]["status"] \
        == fixplans.DISCARDED
    assert client.post(f"/setup/api/integrations/zoom/fixplan/{row['id']}/apply",
                       json={"fingerprint": row["fingerprint"]}).status_code == 409


def test_the_page_carries_the_plan_and_the_budget(monkeypatch):
    app = _app(monkeypatch)
    app.state.fix_plan_store.put([_retest(1)])
    page = TestClient(app).get("/setup/api/settings").json()
    zoom = next(i for i in page["integrations"] if i["key"] == "zoom")
    assert zoom["fixPlan"]["status"] == fixplans.PROPOSED
    assert zoom["agent"] == {"spent": 0.0, "budget": 25.0, "keySet": True, "stored": True}


def test_the_agent_settings_are_on_the_anthropic_sub_tab_and_hidden_with_the_switch_off():
    from core.settings_registry import BY_KEY
    from setup.service import TAB_ONLY_KEYS

    for key in ("integration_agent_model", "integration_agent_monthly_budget"):
        assert BY_KEY[key].integration == "anthropic" and key in TAB_ONLY_KEYS
    assert Settings().integration_agent_model == "claude-opus-5-5"


def test_the_new_tables_are_cleared_by_the_sandbox_reset_and_follow_the_ticks():
    from pathlib import Path

    from core.sandbox_reset import RESET_TABLES

    assert {"integration_fix_plan", "integration_event"} <= set(RESET_TABLES)
    text = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0046_integration_fix_plan.py").read_text()
    assert 'down_revision = "0045_integration_checklist_tick"' in text


def test_the_overall_confidence_lives_only_in_its_field():
    """The live check on crm-test (11-13-26) showed the confidence twice, the
    two disagreeing; the prompt now keeps the overall one in the field."""
    assert "goes only in the confidence field" in diagnosis.SYSTEM
    assert "never repeated as a line of its own" in diagnosis.SYSTEM


def test_the_page_reads_its_data_again_after_a_test_and_a_diagnosis():
    """The live check found the setup checklist and the agent's spend stale
    after a test and after a diagnosis: both are worked out on the server."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "setup" / "frontend" / "app.js").read_text()
    run_test = src[src.index("async function runTest"):]
    run_test = run_test[:run_test.index("\n  }\n")]
    assert "await refreshPage()" in run_test
    poll = src[src.index("function pollDiagnosis"):]
    poll = poll[:poll.index("\n  }\n")]
    assert "refreshPage()" in poll
    assert 'state.page = await api("/settings")' in src
