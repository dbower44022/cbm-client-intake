"""The nightly integration test, phase 5 of the Integrations tab
(prds/integrations-tab-plan.md § 5, ruling I8; the design Doug approved
11-13-26, option A).

Which integrations run; the web-only checks skip at night instead of failing;
each run is stored as nightly; the alert, its memory through the stored runs,
the third unknown night and the recovery; nothing raises.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from core.config import Settings, get_settings
from core.settings_registry import BY_KEY as SETTINGS_BY_KEY
from integrations import nightly
from integrations.registry import BY_KEY as INTEGRATIONS
from integrations.store import NIGHTLY
from integrations.testing import SKIPPED, run_integration_test


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def S(**kw):
    base = dict(app_base_url="https://apps.example.org", integration_test_tz="America/New_York")
    base.update(kw)
    return Settings(**base)


def result(key="zoom", outcome="failed", failed=("host",), unknown=(), at="2026-11-14T11:00:00+00:00"):
    checks = [{"key": k, "label": k.title(), "outcome": "failed", "detail": f"{k} is wrong"} for k in failed]
    checks += [{"key": k, "label": k.title(), "outcome": "unknown", "detail": f"{k} unreachable"} for k in unknown]
    if outcome == "ok":
        checks = [{"key": "token", "label": "Token", "outcome": "ok", "detail": "fine"}]
    return {"integration": key, "outcome": outcome, "checks": checks, "facts": [],
            "startedAt": at, "finishedAt": at, "durationMs": 1000}


# --- which integrations run ----------------------------------------------------------

def test_espocrm_always_runs_and_others_only_in_use_with_a_feature_on():
    keys = [i.key for i in nightly.due(S())]
    assert keys == ["espocrm"]
    keys = [i.key for i in nightly.due(S(zoom_events=True, fathom_transcripts=True))]
    assert keys == ["espocrm", "zoom", "fathom"]
    keys = [i.key for i in nightly.due(S(zoom_events=True, zoom_in_use=False))]
    assert keys == ["espocrm"]
    lob = [i.key for i in nightly.due(S(postal_provider="lob"))]
    assert "lob" in lob
    # YouTube has no feature switch: it never runs at night.
    assert "youtube" not in [i.key for i in nightly.due(S(youtube_api_key="k"))]


# --- the alert ---------------------------------------------------------------------------

ZOOM = INTEGRATIONS["zoom"]


def test_a_new_failure_alerts_with_each_failed_check_and_the_link():
    text = nightly.message(S(), ZOOM, result(), [])
    assert text.startswith("Integration test failed: Zoom (environment: ")
    assert "11-14-26 06:00" in text  # 11:00 UTC in New York
    assert "Failed: Host (host is wrong)" in text
    assert text.endswith("Open: https://apps.example.org/setup/#integrations/zoom")


def test_an_unchanged_failure_is_not_repeated_even_across_an_unknown_night():
    assert nightly.message(S(), ZOOM, result(), [result()]) is None
    assert nightly.message(S(), ZOOM, result(), [result(outcome="unknown", failed=(), unknown=("token",)),
                                                 result()]) is None
    changed = nightly.message(S(), ZOOM, result(failed=("host", "webinars")), [result()])
    assert changed and "Failed: Webinars" in changed


def test_unknown_alerts_once_on_the_third_night():
    u = result(outcome="unknown", failed=(), unknown=("token",))
    assert nightly.message(S(), ZOOM, u, []) is None
    assert nightly.message(S(), ZOOM, u, [u]) is None
    third = nightly.message(S(), ZOOM, u, [u, u])
    assert third and "could not be completed for 3 nights" in third and "Unknown: Token" in third
    assert nightly.message(S(), ZOOM, u, [u, u, u]) is None


def test_a_recovery_is_reported_once():
    ok = result(outcome="ok")
    u = result(outcome="unknown", failed=(), unknown=("token",))
    assert "passes again" in nightly.message(S(), ZOOM, ok, [result()])
    assert "passes again" in nightly.message(S(), ZOOM, ok, [u, u, u])
    assert "passes again" in nightly.message(S(), ZOOM, ok, [u, result()])
    assert nightly.message(S(), ZOOM, ok, [ok, result()]) is None
    assert nightly.message(S(), ZOOM, ok, [u]) is None
    assert nightly.message(S(), ZOOM, ok, []) is None


def test_no_base_address_still_gives_the_path():
    text = nightly.message(S(app_base_url=""), ZOOM, result(), [])
    assert text.endswith("Open: /setup/#integrations/zoom")


# --- one pass -------------------------------------------------------------------------------

class FakeRuns:
    def __init__(self, earlier=None, fail_record=False):
        self.earlier = earlier or {}
        self.recorded = []
        self.fail_record = fail_record

    async def recent(self, integration, *, trigger=NIGHTLY, limit=5):
        assert trigger == NIGHTLY
        return list(self.earlier.get(integration, []))[:limit]

    async def record(self, res, *, trigger="manual", run_by_id="", run_by=""):
        if self.fail_record:
            raise RuntimeError("db down")
        self.recorded.append((res["integration"], trigger, run_by))
        return res


def test_a_pass_stores_each_run_as_nightly_and_alerts_only_where_due():
    sent = []

    async def send(text):
        sent.append(text)

    async def runner(integ, settings):
        return result(key=integ.key, outcome="failed" if integ.key == "zoom" else "ok")

    store = FakeRuns(earlier={"espocrm": [result(key="espocrm", outcome="ok")]})
    summary = run(nightly.run_nightly(S(zoom_events=True), store, send=send, runner=runner))
    assert summary["outcomes"] == {"espocrm": "ok", "zoom": "failed"}
    assert store.recorded == [("espocrm", NIGHTLY, ""), ("zoom", NIGHTLY, "")]
    assert summary["alerts"] == ["zoom"] and len(sent) == 1 and "Zoom" in sent[0]


def test_a_pass_survives_a_broken_runner_store_and_sender():
    async def runner(integ, settings):
        if integ.key == "espocrm":
            raise RuntimeError("boom")
        return result(key=integ.key)

    async def send(text):
        raise RuntimeError("smtp down")

    summary = run(nightly.run_nightly(S(zoom_events=True), FakeRuns(fail_record=True),
                                      send=send, runner=runner))
    assert summary["outcomes"] == {"espocrm": "not run", "zoom": "failed"}
    assert summary["stored"] == 0 and summary["alerts"] == []


def test_a_pass_with_no_database_still_alerts():
    sent = []

    async def send(text):
        sent.append(text)

    async def runner(integ, settings):
        return result(key=integ.key)

    run(nightly.run_nightly(S(), None, send=send, runner=runner))
    assert len(sent) == 1 and "EspoCRM" in sent[0]


def test_the_next_run_is_at_the_local_hour():
    from worker import _next_local_hour

    after = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)  # 05:00 in New York
    nxt = nightly.next_run_time(S(integration_test_hour=6), after, _next_local_hour)
    assert nxt == datetime(2026, 11, 14, 11, 0, tzinfo=timezone.utc)
    later = nightly.next_run_time(S(integration_test_hour=6), nxt, _next_local_hour)
    assert later == datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc)


# --- web-only values at night (option A) -----------------------------------------------------

def test_the_lob_webhook_check_skips_at_night_and_fails_by_day():
    from tests.test_integration_test_phase3 import SECRET, FakeLob
    from integrations.checks import lob

    s = Settings(postal_api_key="test_" + SECRET, postal_test_mode=True, postal_provider="lob")
    deps = lob.Deps(client=lambda _s: FakeLob())
    day = run(run_integration_test(INTEGRATIONS["lob"], s, deps))
    night = run(run_integration_test(INTEGRATIONS["lob"], s, deps, nightly=True))
    assert {c["key"]: c["outcome"] for c in day["checks"]}["webhook"] == "failed"
    hook = {c["key"]: c for c in night["checks"]}["webhook"]
    assert hook["outcome"] == SKIPPED and "web process" in hook["detail"]
    # A value that reached the worker (saved at /setup) is checked as usual.
    s2 = Settings(postal_api_key="test_" + SECRET, postal_provider="lob", postal_webhook_secret="whsec-1")
    ok = run(run_integration_test(INTEGRATIONS["lob"], s2, deps, nightly=True))
    assert {c["key"]: c["outcome"] for c in ok["checks"]}["webhook"] == "ok"


def test_the_espocrm_provisioning_check_skips_at_night_instead_of_failing():
    from tests.test_integration_test import espo_deps, espo_settings

    s = espo_settings(mentor_provision_users=True)
    day = run(run_integration_test(INTEGRATIONS["espocrm"], s, espo_deps()))
    night = run(run_integration_test(INTEGRATIONS["espocrm"], s, espo_deps(), nightly=True))
    assert {c["key"]: c["outcome"] for c in day["checks"]}["provisioning"] == "failed"
    prov = {c["key"]: c for c in night["checks"]}["provisioning"]
    assert prov["outcome"] == SKIPPED and "web process" in prov["detail"]


def test_the_night_flag_never_outlives_its_run():
    from integrations import testing

    from tests.test_integration_test import espo_deps, espo_settings

    run(run_integration_test(INTEGRATIONS["espocrm"], espo_settings(), espo_deps(), nightly=True))
    assert testing._NIGHTLY.get() is False


def test_the_two_settings_are_registered_for_the_worker():
    for key in ("integration_test_hour", "integration_test_tz"):
        spec = SETTINGS_BY_KEY[key]
        assert spec.group == "Reliability" and spec.component == "worker"
    assert Settings().integration_test_hour == 6


def test_the_worker_runs_the_pass_only_with_the_tab_on_and_in_the_background():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "worker.py").read_text()
    block = src[src.index("if now >= next_nightly:"):]
    block = block[:block.index("if claimed == 0")]
    assert "settings.integrations_tab" in block and "asyncio.create_task" in block


def test_the_google_members_group_is_not_failed_at_night_when_the_worker_lacks_it():
    from tests.test_integration_test import google_deps, google_settings

    s = google_settings(mentor_provision_users=True, google_members_group="")
    day = run(run_integration_test(INTEGRATIONS["google_workspace"], s, google_deps()))
    night = run(run_integration_test(INTEGRATIONS["google_workspace"], s, google_deps(), nightly=True))
    assert {c["key"]: c["outcome"] for c in day["checks"]}["directory"] == "failed"
    directory = {c["key"]: c for c in night["checks"]}["directory"]
    assert directory["outcome"] == "ok" and "web process" in directory["detail"]


@pytest.mark.asyncio
async def test_the_nightly_settings_show_only_with_the_tab_on(monkeypatch, tmp_path):
    from core.config import apply_overrides
    from setup.service import page_payload

    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    def keys(payload):
        return {r["key"] for g in payload["groups"] for r in g["settings"]}

    off = await page_payload(None)
    assert "integration_test_hour" not in keys(off)
    apply_overrides({"integrations_tab": "true"})
    try:
        on = await page_payload(None)
        rel = next(g for g in on["groups"] if g["name"] == "Reliability")
        assert {"integration_test_hour", "integration_test_tz"} <= {r["key"] for r in rel["settings"]}
    finally:
        apply_overrides({})
        get_settings.cache_clear()
