"""What Ask Claude reads (integrations/diagnosis.py; prds/integrations-tab-plan.md
§ 6.2 and § 10, ruling W6).

Phase 6's diagnosis agent and its fix plans were removed in phase 10 (ruling
W4); what Ask Claude still uses is tested here: a secret only as set or not
set, the read-only tools, the web tools held to the documentation sites, no
tool that changes anything, recent errors scrubbed. The fake Anthropic client
and the application these tests and the wizard's share live here too.
"""

from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from core.config import Settings, get_settings
from integrations import diagnosis, events
from integrations.diagnosis import Snapshot, run_tool

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
        steps=[{"id": "5.18", "name": "Set up Zoom Webinars"}],
        runbooks=("EVENTS-SETUP.md",), errors=[{"source": "attendance pull", "message": "x", "at": "t"}],
        doc_sites=("developers.zoom.us",),
    )
    base.update(kw)
    return Snapshot(**base)


# --- what Claude may read ----------------------------------------------------------

def test_a_secret_is_only_set_or_not_set_with_when_it_changed():
    rows = {r["key"]: r for r in snap().settings}
    assert rows["zoom_client_secret"]["value"] == "set"
    assert rows["zoom_client_secret"]["lastChanged"] == "2026-11-13T10:00:00+00:00"
    assert rows["zoom_host_email"]["value"] == "zweb@x.org"


def test_the_read_only_tools():
    s = snap()
    assert run_tool("get_test_result", {}, s)[0]["outcome"] == "failed"
    assert "editable" not in run_tool("get_settings", {}, s)[0][0]
    assert run_tool("get_recent_errors", {}, s)[0][0]["source"] == "attendance pull"
    assert run_tool("list_guide_steps", {}, s)[0] == [{"id": "5.18", "name": "Set up Zoom Webinars"}]
    step, err = run_tool("read_guide_step", {"step_id": "5.18"}, s)
    assert not err and "Zoom" in json.dumps(step)
    assert run_tool("read_guide_step", {"step_id": "9.7"}, s)[1] is True  # not this integration's
    text, err = run_tool("read_runbook", {"name": "EVENTS-SETUP.md"}, s)
    assert not err and len(text) <= diagnosis.RUNBOOK_MAX + 20
    assert run_tool("read_runbook", {"name": "../.env"}, s)[1] is True
    assert run_tool("get_checklist", {}, s)[1] is True  # removed with the checklist (W4)
    assert run_tool("drop_tables", {}, s)[1] is True


def test_the_web_tools_are_held_to_the_documentation_sites_and_nothing_can_change_anything():
    tools = {t["name"]: t for t in diagnosis.tools_for(snap())}
    assert tools["web_search"]["allowed_domains"] == ["developers.zoom.us"]
    assert tools["web_fetch"]["allowed_domains"] == ["developers.zoom.us"]
    assert tools["web_search"]["max_uses"] == diagnosis.MAX_SEARCHES
    assert set(tools) == {"get_test_result", "get_settings", "get_readiness", "list_guide_steps",
                          "read_guide_step", "read_runbook", "get_recent_errors", "web_search", "web_fetch"}
    assert "web_search" not in {t["name"] for t in diagnosis.tools_for(snap(doc_sites=()))}


def test_the_fix_and_setup_plan_writers_are_gone():
    for name in ("diagnose", "check_plan", "SUBMIT_TOOL", "SUBMIT_SETUP_TOOL", "SYSTEM", "SETUP_SYSTEM"):
        assert not hasattr(diagnosis, name), name


def test_every_integration_has_documentation_sites():
    from integrations.registry import INTEGRATIONS

    assert all(i.doc_sites for i in INTEGRATIONS)
    google = next(i for i in INTEGRATIONS if i.key == "google_workspace")
    assert "knowledge.workspace.google.com" in google.doc_sites


# --- the fake Anthropic client -------------------------------------------------------

def block(type_, **kw):
    return SimpleNamespace(type=type_, **kw)


def message(content, stop="tool_use", usage=None):
    return SimpleNamespace(content=content, stop_reason=stop, model="claude-opus-5-5",
                           usage=usage or {"input_tokens": 1000, "output_tokens": 500})


def scripted(*responses):
    sent = []

    async def send(client, kwargs):
        sent.append(copy.deepcopy(kwargs))
        r = responses[len(sent) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    return send, sent


def test_an_expensive_answer_stops_itself():
    big = {"input_tokens": 0, "output_tokens": 400_000}
    send, _ = scripted(message([block("tool_use", id="t1", name="get_settings", input={})], usage=big))
    out = run(diagnosis.explain(None, snap(), {"title": "Host"}, "refused", model="claude-opus-5-5",
                                secrets=[], send=send))
    assert out.plan is None and "cost" in out.error


# --- recent errors ----------------------------------------------------------------------

def test_a_recent_error_is_scrubbed_and_never_raises():
    s = Settings(zoom_client_secret=SECRET)
    assert SECRET not in events.clean(s, f"401 with {SECRET}\nsecond line")
    run(events.record_event(Settings(database_url=""), "zoom", "x", "boom"))  # no database: nothing


# --- the application the endpoint tests share ---------------------------------------------

from tests.test_integration_test import _ADMIN, FakeRuns, NoSettings  # noqa: E402


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
    app.state.mailing_store = None
    app.state.wizard_store = None
    logged = []

    async def log_action(**kw):
        logged.append(kw)

    monkeypatch.setattr("setup.router.action_log.log_action", log_action)

    async def no_readiness(settings, *a, **k):
        return {"features": []}

    monkeypatch.setattr("setup.readiness.readiness_payload", no_readiness)
    app.state.logged = logged
    return app


def test_the_agent_settings_are_on_the_anthropic_sub_tab_and_hidden_with_the_switch_off():
    from core.settings_registry import BY_KEY
    from setup.service import TAB_ONLY_KEYS

    for key in ("integration_agent_model", "integration_agent_monthly_budget"):
        assert BY_KEY[key].integration == "anthropic" and key in TAB_ONLY_KEYS
    assert Settings().integration_agent_model == "claude-opus-5-5"


def test_the_recent_errors_table_is_cleared_by_the_sandbox_reset():
    from core.sandbox_reset import RESET_TABLES

    assert "integration_event" in RESET_TABLES
