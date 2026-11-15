"""Phase 10 of the Integrations tab: the removal (prds/integrations-tab-plan.md
§ 10, ruling W4; the list Doug approved 11-15-26, option A).

The setup checklist with its hand ticks, the setup assistant with its setup
plans, and the diagnosis's fix plans are gone: their endpoints answer 404,
the page carries none of their fields, their tables are dropped by migration
0049 and no longer reset nightly. Fix with the wizard is offered after a failed
test. With the switch off, System Settings is exactly as before.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import get_settings

from tests.test_integration_diagnosis import _app as diag_app  # noqa: E402
from tests.test_integration_wizard import FakeWizards  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

REMOVED = [
    ("post", "/setup/api/integrations/zoom/checklist/5.18", {"ticked": True}),
    ("post", "/setup/api/integrations/zoom/diagnose", None),
    ("post", "/setup/api/integrations/zoom/setup", None),
    ("get", "/setup/api/integrations/zoom/fixplan", None),
    ("get", "/setup/api/integrations/zoom/setupplan", None),
    ("post", "/setup/api/integrations/zoom/fixplan/p1/apply", {"fingerprint": "x"}),
    ("post", "/setup/api/integrations/zoom/fixplan/p1/steps/1/done", None),
    ("post", "/setup/api/integrations/zoom/fixplan/p1/discard", None),
]


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(monkeypatch, tab="true"):
    app = diag_app(monkeypatch)
    monkeypatch.setenv("INTEGRATIONS_TAB", tab)
    get_settings.cache_clear()
    app.state.wizard_store = FakeWizards()
    return app


@pytest.mark.parametrize("method,path,body", REMOVED)
def test_every_removed_endpoint_is_gone(monkeypatch, method, path, body):
    client = TestClient(_app(monkeypatch))
    resp = getattr(client, method)(path, **({"json": body} if body is not None else {}))
    assert resp.status_code in (404, 405), path


def test_the_page_carries_no_checklist_and_no_plan_and_the_budget_counts_ask_claude(monkeypatch):
    app = _app(monkeypatch)
    app.state.wizard_store.calls["c1"] = dict(status="answered", answer="x", cost=1.25)
    page = TestClient(app).get("/setup/api/settings").json()
    for integ in page["integrations"]:
        for gone in ("checklist", "ticksStored", "fixPlan", "setupPlan"):
            assert gone not in integ, (integ["key"], gone)
        assert integ["phases"] == {"test": integ["phases"]["test"]}
        assert integ["agent"] == {"spent": 1.25, "budget": 25.0, "keySet": True, "stored": True}


def test_the_stores_are_no_longer_made():
    src = (ROOT / "core" / "app.py").read_text()
    assert "integration_tick_store" not in src and "fix_plan_store" not in src
    for module in ("ticks", "fixplans"):
        assert not (ROOT / "integrations" / f"{module}.py").exists()


def test_the_history_tab_has_no_tick_rows(monkeypatch):
    from tests.test_integration_test import NoSettings

    class History(NoSettings):
        async def history(self, key="", limit=50):
            return [{"key": "zoom_events", "action": "set", "at": "2026-11-13T09:00:00+00:00"}]

    app = _app(monkeypatch)
    app.state.settings_store = History()
    rows = TestClient(app).get("/setup/api/history").json()["history"]
    assert [r["key"] for r in rows] == ["zoom_events"]


def test_with_the_switch_off_the_page_is_as_before_and_reads_no_wizard(monkeypatch):
    app = _app(monkeypatch, tab="false")

    class Exploding(FakeWizards):
        async def all(self):
            raise AssertionError("read with the switch off")

        async def spent_this_month(self, **kw):
            raise AssertionError("read with the switch off")

    app.state.wizard_store = Exploding()
    client = TestClient(app)
    page = client.get("/setup/api/settings").json()
    assert "integrations" not in page and "integrationsTab" not in page
    resp = client.post("/setup/api/integrations/zoom/wizard/restart", json={})
    assert resp.status_code == 404


def test_fix_follows_a_failed_test_on_the_page():
    """Since the status screen (Doug's rulings 11-15-26): a failed test makes the
    one button Fix, which restarts the setup at the first failing step (W5).
    The state rules themselves run in tests/test_integration_status_screen.py."""
    src = (ROOT / "setup" / "frontend" / "app.js").read_text()
    action = src[src.index("async function integrationAction"):]
    action = action[:action.index("\n  }\n")]
    assert 'action === "fix"' in action and '"|restart|"' in action
    for gone in ("Diagnose with Claude", "Set up with Claude", "Approve and apply", "Setup checklist",
                 "data-tick", "/fixplan", "/checklist/", "Fix with the wizard"):
        assert gone not in src, gone
    # The nightly alert's link opens the status screen and changes nothing.
    assert 'hash.split("/")[2] === "wizard"' in src


def test_fix_with_the_wizard_starts_at_the_first_failing_screen(monkeypatch):
    """Restart clears a finished run, so the wizard opens where the stored
    test fails (W5)."""
    app = _app(monkeypatch)
    asyncio.run(app.state.wizard_store.put("zoom", {"finished": True, "history": ["zoom-use"],
                                                    "answers": {"zoom-use": "Yes"}}))
    client = TestClient(app)
    zoom = next(i for i in client.get("/setup/api/settings").json()["integrations"] if i["key"] == "zoom")
    assert zoom["wizard"]["status"] == "done"
    resp = client.post("/setup/api/integrations/zoom/wizard/restart", json={})
    zoom = next(i for i in resp.json()["page"]["integrations"] if i["key"] == "zoom")
    assert zoom["wizard"]["status"] == "running" and zoom["wizard"]["screen"]


def test_the_tables_are_dropped_and_no_longer_reset():
    from core.sandbox_reset import RESET_TABLES

    assert "integration_checklist_tick" not in RESET_TABLES
    assert "integration_fix_plan" not in RESET_TABLES
    assert {"integration_event", "integration_wizard", "integration_agent_call"} <= set(RESET_TABLES)
    text = (ROOT / "alembic" / "versions" / "0049_drop_checklist_fix_plans.py").read_text()
    assert 'down_revision = "0048_integration_wizard"' in text
    assert "INSERT INTO integration_agent_call" in text
    assert 'drop_table("integration_fix_plan")' in text and 'drop_table("integration_checklist_tick")' in text


def test_every_migration_revision_fits_alembics_version_column():
    """``alembic_version.version_num`` is varchar(32): a longer revision id
    fails the deploy's migrate job (found on Postgres while building 0049)."""
    import re

    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        m = re.search(r'^revision = "([^"]+)"', path.read_text(), re.M)
        assert m is None or len(m.group(1)) <= 32, path.name
