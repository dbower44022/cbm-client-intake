"""The setup wizard, phase 8 of the Integrations tab, piloted on Zoom
(prds/integrations-tab-plan.md § 10, rulings W1 to W6; screens approved by
Doug 11-14-26).

Zoom's screens load and name only real checks and settings; the rendered guide
is unchanged by them; the checks; where the wizard starts (W5); answers,
branches and the end; a box saved through the checked save path and checked
at once; a failure stays on its screen with Ask Claude (W6); Back and
restart; no secret value ever in what the page receives.
"""

from __future__ import annotations

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, apply_overrides, get_settings
from core.settings_registry import BY_KEY as SETTINGS_BY_KEY
from integrations import wizard
from integrations.registry import BY_KEY as INTEGRATIONS

from tests.test_integration_diagnosis import _app as diag_app, block, message, scripted, snap  # noqa: E402

SECRET = "zs-very-secret-555"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    apply_overrides({})
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def zoom():
    return wizard.screens_for("zoom")


# --- the screens --------------------------------------------------------------------

def test_zoom_has_the_fourteen_approved_screens_and_their_keys_are_sound():
    ids = [s.id for s in zoom()]
    assert ids == ["zoom-use", "zoom-have-account", "zoom-mailbox", "zoom-signup", "zoom-licence",
                   "zoom-build-app", "zoom-information", "zoom-scopes", "zoom-activate", "zoom-account-id",
                   "zoom-client-id", "zoom-client-secret", "zoom-host", "zoom-switch-on"]
    assert wizard.problems(zoom(), set(SETTINGS_BY_KEY), set(INTEGRATIONS)) == []
    kinds = {s.id: s.kind for s in zoom()}
    assert kinds["zoom-use"] == "question" and kinds["zoom-scopes"] == "done" and kinds["zoom-host"] == "enter"
    assert len(next(s for s in zoom() if s.id == "zoom-scopes").copy) == 7


def test_problems_catches_bad_keys():
    bad = [wizard.Screen("a", "1.1", "A", check="magic"),
           wizard.Screen("b", "1.1", "B", enters="nope", ask=({"answer": "Yes", "then": "zzz", "sets": {"x": "1"}},))]
    assert len(wizard.problems(bad, set(SETTINGS_BY_KEY), set(INTEGRATIONS))) == 4


def test_the_wizard_screens_never_change_the_rendered_guide():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "rdg", Path(__file__).resolve().parents[1] / "scripts" / "render_deployment_guide.py")
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    for stage in r.load():
        stripped = copy.deepcopy(stage)
        for st in stripped["steps"]:
            st.pop("wizard", None)
        assert r.render_stage(stage) == r.render_stage(stripped), stage["stage"]


def test_integrations_without_screens_have_no_wizard_yet():
    assert wizard.screens_for("lob") == []
    assert wizard.view("lob", Settings(), {}, {}, None) is None


# --- the checks and the start (W5) ----------------------------------------------------------

def st(settings=None, overrides=None, runs=None, answers=None):
    return wizard.State(settings=settings or Settings(), overrides=overrides or {},
                        test_runs=runs or {}, answers=answers or {})


def token_run(outcome="ok"):
    return {"zoom": {"outcome": "ok" if outcome == "ok" else "failed",
                     "checks": [{"key": "token", "outcome": outcome, "detail": "Zoom issued a token."},
                                {"key": "host", "outcome": "ok", "detail": "Found zweb, a Licensed user."}]}}


def test_where_the_wizard_starts(monkeypatch):
    monkeypatch.delenv("ZOOM_IN_USE", raising=False)
    screens = zoom()
    # crm-test today: the question has never been answered.
    assert wizard.start(screens, st()) == "zoom-use"
    # Answered, credentials missing: straight to the first box (Done screens never fail).
    assert wizard.start(screens, st(overrides={"zoom_in_use": object()})) == "zoom-account-id"
    creds = Settings(zoom_account_id="a", zoom_client_id="b", zoom_client_secret=SECRET)
    assert wizard.start(screens, st(creds, {"zoom_in_use": object()})) == "zoom-client-secret"
    # Everything passing: set up.
    assert wizard.start(screens, st(creds, {"zoom_in_use": object()}, token_run())) is None


def test_the_check_kinds():
    by = {s.id: s for s in zoom()}
    assert wizard.evaluate(by["zoom-use"], st(answers={"zoom-use": "Yes"}))[0] == wizard.PASS
    assert wizard.evaluate(by["zoom-account-id"], st(Settings(zoom_account_id="a")))[0] == wizard.PASS
    out, why = wizard.evaluate(by["zoom-client-secret"], st(runs=token_run("failed")))
    assert out == wizard.FAIL and "token" in why
    assert wizard.evaluate(by["zoom-client-secret"], st())[1] == "The integration test has not been run yet."
    assert wizard.evaluate(by["zoom-scopes"], st())[0] == wizard.PASS


def test_branches_and_the_end():
    screens = zoom()
    assert wizard.next_screen(screens, "zoom-have-account", {}, "zoom-account-id") == "zoom-account-id"
    assert wizard.next_screen(screens, "zoom-use", {}, "end") is None
    assert wizard.next_screen(screens, "zoom-mailbox", {}) == "zoom-signup"
    assert wizard.next_screen(screens, "zoom-switch-on", {}) is None


def test_a_secret_box_never_carries_its_value():
    view = wizard.view("zoom", Settings(zoom_client_secret=SECRET), {}, {},
                       {"current": "zoom-client-secret", "history": ["zoom-use"]})
    assert view["screen"]["secret"] is True and view["screen"]["isSet"] is True
    assert SECRET not in json.dumps(view)
    host = wizard.view("zoom", Settings(zoom_host_email="zweb@x.org"), {}, {}, {"current": "zoom-host"})
    assert host["screen"]["value"] == "zweb@x.org" and host["position"] == 13 and host["total"] == 14


# --- the endpoints ---------------------------------------------------------------------------

class FakeWizards:
    def __init__(self):
        self.rows, self.calls = {}, {}

    async def get(self, integration):
        return copy.deepcopy(self.rows.get(integration))

    async def all(self):
        return copy.deepcopy(self.rows)

    async def put(self, integration, progress, *, by=""):
        self.rows[integration] = copy.deepcopy(progress)

    async def record_call(self, *, call_id, integration, screen, status, answer="", cost=0.0, asked_by=""):
        self.calls[call_id] = dict(status=status, answer=answer, cost=cost)

    async def spent_this_month(self, **kw):
        return sum(c["cost"] for c in self.calls.values())


def _app(monkeypatch):
    monkeypatch.delenv("ZOOM_IN_USE", raising=False)
    app = diag_app(monkeypatch)
    app.state.wizard_store = FakeWizards()
    saved = []

    async def checked_save(request, user, key, body):
        saved.append((key, body.value))
        apply_overrides({**{k: v for k, v in saved}})
        return {"reverted": None, "confirmBy": None}

    monkeypatch.setattr("setup.router._checked_save", checked_save)
    app.state.saved = saved
    return app


def post(client, action, screen="", answer="", value=""):
    return client.post(f"/setup/api/integrations/zoom/wizard/{action}",
                       json={"screen": screen, "answer": answer, "value": value})


def zoom_view(resp):
    return next(i for i in resp.json()["page"]["integrations"] if i["key"] == "zoom")["wizard"]


def test_no_ends_the_wizard_and_saves_not_in_use(monkeypatch):
    app = _app(monkeypatch)
    client = TestClient(app)
    w = zoom_view(post(client, "answer", "zoom-use", "No"))
    assert w["status"] == "ended" and "not used" in w["ended"]
    assert app.state.saved == [("zoom_in_use", "false")]
    w = zoom_view(post(client, "restart"))
    assert w["status"] == "running"


def test_yes_and_an_existing_account_jump_to_the_first_box(monkeypatch):
    app = _app(monkeypatch)
    client = TestClient(app)
    w = zoom_view(post(client, "answer", "zoom-use", "Yes"))
    assert w["screen"]["id"] == "zoom-have-account" and app.state.saved == [("zoom_in_use", "true")]
    w = zoom_view(post(client, "answer", "zoom-have-account", "Yes"))
    assert w["screen"]["id"] == "zoom-account-id" and w["position"] == 10 and w["canBack"]
    w = zoom_view(post(client, "back"))
    assert w["screen"]["id"] == "zoom-have-account"


def test_a_done_screen_moves_on(monkeypatch):
    client = TestClient(_app(monkeypatch))
    post(client, "answer", "zoom-use", "Yes")
    post(client, "answer", "zoom-have-account", "No")
    w = zoom_view(post(client, "done", "zoom-mailbox"))
    assert w["screen"]["id"] == "zoom-signup"


def test_a_box_is_saved_and_checked_at_once(monkeypatch):
    calls = []

    async def fake_test(integ, settings, deps=None, **kw):
        calls.append(integ.key)
        ok = bool(settings.zoom_client_secret) and settings.zoom_client_secret != "wrong-secret-1"
        return {"integration": "zoom", "outcome": "ok" if ok else "failed",
                "checks": [{"key": "token", "label": "Token", "outcome": "ok" if ok else "failed",
                            "detail": "Zoom issued a token." if ok else "invalid_client"}],
                "facts": [], "startedAt": "2026-11-14T01:00:00+00:00",
                "finishedAt": "2026-11-14T01:00:01+00:00", "durationMs": 1}

    monkeypatch.setattr("integrations.testing.run_integration_test", fake_test)
    app = _app(monkeypatch)
    client = TestClient(app)
    post(client, "answer", "zoom-use", "Yes")
    post(client, "answer", "zoom-have-account", "Yes")
    assert zoom_view(post(client, "enter", "zoom-account-id", value=" acc-1 "))["screen"]["id"] == "zoom-client-id"
    assert ("zoom_account_id", "acc-1") in app.state.saved
    post(client, "enter", "zoom-client-id", value="cid-1")
    w = zoom_view(post(client, "enter", "zoom-client-secret", value="wrong-secret-1"))
    assert w["screen"]["id"] == "zoom-client-secret" and "invalid_client" in w["failure"]["reason"]
    assert calls == ["zoom"]
    resp = post(client, "enter", "zoom-client-secret", value=SECRET)
    assert zoom_view(resp)["screen"]["id"] == "zoom-host"
    assert SECRET not in resp.text and "wrong-secret-1" not in resp.text


def test_ask_claude_is_offered_only_on_a_failure_and_respects_the_budget(monkeypatch):
    seen = {}

    async def fake_ask(app, key, call_id, snapshot, screen, failure, actor):
        seen.update(screen=screen["id"], failure=failure)

    monkeypatch.setattr("setup.router._run_ask", fake_ask)
    app = _app(monkeypatch)
    client = TestClient(app)
    p = {"current": "zoom-client-secret", "history": [], "answers": {}, "done": [], "finished": False,
         "ended": "", "failure": {"screen": "zoom-client-secret", "reason": "Zoom refused the credentials."},
         "help": None}
    run(app.state.wizard_store.put("zoom", p))
    w = zoom_view(post(client, "ask", "zoom-client-secret"))
    assert w["help"]["status"] == "running" and seen == {"screen": "zoom-client-secret",
                                                         "failure": "Zoom refused the credentials."}
    assert post(client, "ask", "zoom-client-secret").status_code == 409  # one at a time
    app.state.fix_plan_store.spent = 25.0
    run(app.state.wizard_store.put("zoom", dict(p, help=None)))
    resp = post(client, "ask", "zoom-client-secret")
    assert resp.status_code == 409 and "monthly budget" in resp.json()["detail"]


def test_the_background_answer_is_stored_with_its_cost(monkeypatch):
    from setup import router

    app = _app(monkeypatch)
    store = app.state.wizard_store
    run(store.put("zoom", {"help": {"status": "running", "id": "c1", "screen": "zoom-host"}}))
    send, _ = scripted(message([block("text", text="The host address is not a licensed user.")], stop="end_turn"))

    from integrations import diagnosis

    real_explain = diagnosis.explain

    async def fake_explain(client, snapshot, screen, failure, **kw):
        return await real_explain(client, snapshot, screen, failure, model="claude-opus-5-5",
                                  secrets=[SECRET], send=send)

    monkeypatch.setattr("integrations.diagnosis.explain", fake_explain)
    app.state.anthropic_client = lambda: None
    run(router._run_ask(app, "zoom", "c1", snap(), {"id": "zoom-host", "title": "Host"}, "No such user", "adm"))
    help_ = store.rows["zoom"]["help"]
    assert help_["status"] == "answered" and "licensed" in help_["text"]
    assert store.calls["c1"]["status"] == "answered"


def test_explain_reads_only_and_never_submits():
    send, sent = scripted(message([block("tool_use", id="t", name="get_settings", input={})]),
                          message([block("text", text="Paste the secret again.")], stop="end_turn"))
    s = snap()
    out = __import__("asyncio").run(
        __import__("integrations.diagnosis", fromlist=["x"]).explain(
            None, s, {"title": "Secret", "what": "", "how": f"uses {SECRET}"}, "refused",
            model="m", secrets=[SECRET], send=send))
    assert out.plan == {"answer": "Paste the secret again."}
    names = {t["name"] for t in sent[0]["tools"]}
    assert "submit_fix_plan" not in names and "submit_setup_plan" not in names
    assert SECRET not in json.dumps(sent, default=str)


def test_the_page_carries_the_wizard_and_the_tables_reset_nightly(monkeypatch):
    from core.sandbox_reset import RESET_TABLES

    page = TestClient(_app(monkeypatch)).get("/setup/api/settings").json()
    z = next(i for i in page["integrations"] if i["key"] == "zoom")
    assert z["wizard"]["screen"]["id"] == "zoom-use" and z["wizard"]["stored"] is True
    assert next(i for i in page["integrations"] if i["key"] == "lob")["wizard"] is None
    assert {"integration_wizard", "integration_agent_call"} <= set(RESET_TABLES)
