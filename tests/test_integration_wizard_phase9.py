"""The wizard for every integration, phase 9 part two of the Integrations tab
(prds/integrations-tab-plan.md § 10; Google Workspace's scope B and the
screens of all eight approved by Doug 11-15-26, stopping points 3 and 4).

Each integration's screens load and name only real checks, settings, coded
actions and branches; the rendered guide is unchanged by them (also covered
for every stage in tests/test_integration_wizard.py); the new screen kinds
(a coded action, Connect, a box that sets more), checks joined by commas,
a skipped check passing, and the deployment's own address in a copy value.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, apply_overrides, get_settings
from core.settings_registry import BY_KEY as SETTINGS_BY_KEY
from integrations import wizard
from integrations.actions import Result
from integrations.registry import BY_KEY as INTEGRATIONS

from tests.test_integration_wizard import _app  # noqa: E402


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    apply_overrides({})
    get_settings.cache_clear()


#: The screen counts Doug approved (Zoom's two from stopping point 1).
COUNTS = {"espocrm": 9, "google_workspace": 44, "zoom_meetings": 18, "zoom": 16, "fathom": 7,
          "constant_contact": 12, "lob": 11, "twilio": 15, "anthropic": 8, "youtube": 6}


def test_every_integration_has_its_approved_screens_and_they_are_sound():
    assert set(COUNTS) == set(INTEGRATIONS)
    for key, count in COUNTS.items():
        screens = wizard.screens_for(key)
        assert len(screens) == count, key
        assert wizard.problems(screens, set(SETTINGS_BY_KEY), set(INTEGRATIONS)) == [], key


def test_every_in_use_question_comes_first_and_espocrm_has_none():
    for key, integ in INTEGRATIONS.items():
        first = wizard.screens_for(key)[0]
        if integ.always_in_use:
            assert first.kind == "enter", key
        else:
            assert first.check == f"decided:{integ.in_use_setting}", key


def test_the_coded_actions_and_connect_have_their_screens():
    kinds = {(s.id, s.kind) for k in INTEGRATIONS for s in wizard.screens_for(k)}
    assert ("google-drive-create", "action") in kinds
    assert ("twilio-find-number", "action") in kinds
    assert ("mailing-connect", "connect") in kinds
    by = {s.id: s for s in wizard.screens_for("google_workspace")}
    assert by["google-drive-create"].as_dict()["runLabel"] == "Create the shared drive"
    assert by["google-grant"].check == "test:google_workspace/grant"


def test_problems_catches_the_new_keys():
    bad = [wizard.Screen("a", "1.1", "A", runs="nope.action"),
           wizard.Screen("b", "1.1", "B", connect="fax"),
           wizard.Screen("c", "1.1", "C", enters="lob_in_use", sets=(("nope", "1"),)),
           wizard.Screen("d", "1.1", "D", sets=(("lob_in_use", "1"),)),
           wizard.Screen("e", "1.1", "E", check="test:lob/mode,nope")]
    assert len(wizard.problems(bad, set(SETTINGS_BY_KEY), set(INTEGRATIONS))) == 5


def st(runs):
    return wizard.State(settings=Settings(), overrides={}, test_runs=runs)


def test_joined_checks_and_a_skipped_check():
    screen = wizard.Screen("x", "1.1", "X", check="test:constant_contact/list,field")
    run = {"outcome": "failed", "checks": [{"key": "list", "outcome": "ok", "detail": "List found."},
                                           {"key": "field", "outcome": "failed", "detail": "No field."}]}
    assert wizard.evaluate(screen, st({"constant_contact": run})) == (wizard.FAIL, "No field.")
    run["checks"][1]["outcome"] = "ok"
    assert wizard.evaluate(screen, st({"constant_contact": run}))[0] == wizard.PASS
    off = wizard.Screen("y", "1.1", "Y", check="test:google_workspace/calendar")
    skipped = {"outcome": "ok", "checks": [{"key": "calendar", "outcome": "skipped",
                                            "detail": "Not checked — switched off."}]}
    assert wizard.evaluate(off, st({"google_workspace": skipped}))[0] == wizard.PASS


def test_a_copy_value_carries_this_deployments_address():
    view = wizard.view("constant_contact", Settings(app_base_url="https://apps.akron.org/"), {}, {},
                       {"current": "mailing-redirect"})
    assert view["screen"]["copy"] == ["https://apps.akron.org/api/setup/mailing/callback"]
    blank = wizard.view("constant_contact", Settings(app_base_url=""), {}, {}, {"current": "mailing-redirect"})
    assert blank["screen"]["copy"] == ["https://APP-ADDRESS/api/setup/mailing/callback"]


def test_google_starts_at_the_first_failing_screen(monkeypatch):
    monkeypatch.delenv("GOOGLE_WORKSPACE_IN_USE", raising=False)
    screens = wizard.screens_for("google_workspace")
    assert wizard.start(screens, st({})) == "google-use"
    answered = wizard.State(settings=Settings(), overrides={"google_workspace_in_use": object()})
    assert wizard.start(screens, answered) == "google-ops-mailbox"
    # The stage 4 screen appears only after No.
    assert wizard.next_screen(screens, "google-have-workspace", {"google-have-workspace": "No"}) \
        == "google-build-first"


# --- the endpoints ---------------------------------------------------------------------------

def post(client, key, action, screen="", answer="", value=""):
    return client.post(f"/setup/api/integrations/{key}/wizard/{action}",
                       json={"screen": screen, "answer": answer, "value": value})


def view_of(resp, key):
    return next(i for i in resp.json()["page"]["integrations"] if i["key"] == key)["wizard"]


def test_a_coded_action_screen_runs_it_and_saves_what_it_proposes(monkeypatch):
    calls = []

    async def fake_run(name, settings, value, *, dry, deps=None):
        calls.append((name, dry))
        return Result(True, "Found one number.", {"sms_from_number": "+12165550123"})

    monkeypatch.setattr("integrations.actions.run", fake_run)
    app = _app(monkeypatch)
    client = TestClient(app)
    run_ = asyncio.run
    run_(app.state.wizard_store.put("twilio", dict(wizard.blank(), current="twilio-find-number")))
    w = view_of(post(client, "twilio", "run", "twilio-find-number"), "twilio")
    assert calls == [("twilio.find_sender_number", False)]
    assert ("sms_from_number", "+12165550123") in app.state.saved
    assert w["screen"]["id"] == "twilio-sender"


def test_a_failed_coded_action_stays_on_its_screen(monkeypatch):
    async def fake_run(name, settings, value, *, dry, deps=None):
        return Result(False, "The account has 2 numbers that can send texts.")

    monkeypatch.setattr("integrations.actions.run", fake_run)
    app = _app(monkeypatch)
    client = TestClient(app)
    asyncio.run(app.state.wizard_store.put("twilio", dict(wizard.blank(), current="twilio-find-number")))
    w = view_of(post(client, "twilio", "run", "twilio-find-number"), "twilio")
    assert w["screen"]["id"] == "twilio-find-number" and "2 numbers" in w["failure"]["reason"]


def test_a_box_that_sets_more_saves_both(monkeypatch):
    async def fake_test(integ, settings, deps=None, **kw):
        return {"integration": "lob", "outcome": "ok",
                "checks": [{"key": "mode", "label": "Test or live", "outcome": "ok", "detail": "A live key."}],
                "facts": [], "startedAt": "2026-11-15T01:00:00+00:00",
                "finishedAt": "2026-11-15T01:00:01+00:00", "durationMs": 1}

    monkeypatch.setattr("integrations.testing.run_integration_test", fake_test)
    app = _app(monkeypatch)
    client = TestClient(app)
    asyncio.run(app.state.wizard_store.put("lob", dict(wizard.blank(), current="lob-live-key",
                                                         answers={"lob-live": "Yes"})))
    resp = post(client, "lob", "enter", "lob-live-key", value="live_abc")
    assert ("postal_api_key", "live_abc") in app.state.saved
    assert ("postal_test_mode", "false") in app.state.saved
    assert "live_abc" not in resp.text


def test_connect_returns_to_constant_contacts_sub_tab(monkeypatch):
    from setup.mailing import _back

    monkeypatch.setenv("INTEGRATIONS_TAB", "true")
    get_settings.cache_clear()
    assert _back("connected").headers["location"].endswith("#integrations/constant_contact")


