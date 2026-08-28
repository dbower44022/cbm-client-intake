"""System Settings — the override layer, the page, readiness, diff and jobs.

Covers the rulings that are easy to regress: the denylist is refused at the
server (not merely hidden), a bad value can never take the app down, a scoped
override does not change the process-wide configuration, and a mutating job
refuses to apply a plan that has moved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core import config as config_module
from core.app import create_app
from core.config import apply_overrides, get_settings, overrides_version
from core.settings_registry import DENYLIST, SETTINGS, is_editable
from core.settings_store import (
    Override,
    SettingsError,
    global_overrides,
    setting_for_user,
    validate_value,
)
from forms import info_request
from setup import jobs as jobs_mod
from setup import snapshot as snapshot_mod
from setup.service import page_payload

_ADMIN = {"userName": "adm", "name": "Ada", "isAdmin": True, "userId": "u1",
          "token": "t", "teams": [], "roles": []}
_STAFF = {"userName": "stf", "name": "Sam", "isAdmin": False, "userId": "u2",
          "token": "t", "teams": ["Mentor Team"], "roles": []}


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- the override layer ------------------------------------------------------

def test_override_applies_and_coerces():
    assert get_settings().worker_batch_size == 10
    apply_overrides({"worker_batch_size": "25", "gmail_sync": "true"})
    s = get_settings()
    assert s.worker_batch_size == 25 and isinstance(s.worker_batch_size, int)
    assert s.gmail_sync is True


def test_a_reference_captured_at_boot_sees_later_overrides():
    """The 2026-08-09 regression: `create_app` captures a settings object once
    and its request handlers close over it. If an override produced a NEW object
    every one of those references would stay frozen at boot — the save would
    succeed and change nothing."""
    captured = get_settings()          # what create_app does
    assert captured.env_label == ""
    apply_overrides({"env_label": "Test Bench"})
    assert captured.env_label == "Test Bench"
    assert captured.environment == "Test Bench"
    assert captured is get_settings()


def test_clearing_an_override_restores_the_deployment_value():
    captured = get_settings()
    baseline = captured.worker_batch_size
    apply_overrides({"worker_batch_size": "25"})
    assert captured.worker_batch_size == 25
    apply_overrides({})
    assert captured.worker_batch_size == baseline


def test_bad_override_leaves_the_configuration_unchanged():
    """Ruling 6: a broken override must never silently reconfigure the app."""
    apply_overrides({"worker_batch_size": "twenty"})
    assert get_settings().worker_batch_size == 10
    # And from a good state it keeps the good state rather than reverting.
    apply_overrides({"worker_batch_size": "25"})
    apply_overrides({"worker_batch_size": "twenty"})
    assert get_settings().worker_batch_size == 25


def test_version_bumps_only_on_change():
    apply_overrides({"gmail_sync": "true"})
    first = overrides_version()
    apply_overrides({"gmail_sync": "true"})
    assert overrides_version() == first
    apply_overrides({"gmail_sync": "false"})
    assert overrides_version() == first + 1


def test_cache_clear_resets_overrides_too():
    apply_overrides({"worker_batch_size": "99"})
    assert get_settings().worker_batch_size == 99
    get_settings.cache_clear()
    assert get_settings().worker_batch_size == 10


# --- the denylist and validation --------------------------------------------

@pytest.mark.parametrize("key", ["espo_api_key", "database_url", "espo_dry_run",
                                 "session_secret", "settings_overrides"])
def test_denylisted_keys_are_refused(key):
    assert not is_editable(key)
    with pytest.raises(SettingsError):
        validate_value(key, "anything")


def test_unknown_key_refused():
    with pytest.raises(SettingsError):
        validate_value("not_a_setting", "x")


def test_unparseable_value_refused_before_storage():
    with pytest.raises(SettingsError):
        validate_value("worker_batch_size", "lots")


def test_valid_value_accepted():
    validate_value("worker_batch_size", "12")
    validate_value("gmail_sync", "true")
    validate_value("gdrive_identity", "service")


def test_a_curated_key_is_denylisted_only_when_read_only():
    """An editable control the server always refuses is a lie. The one allowed
    overlap is a spec marked `readonly`, which is curated precisely so the value
    is VISIBLE and explained rather than hidden, and renders no control."""
    from core.settings_registry import BY_KEY

    for key in {s.key for s in SETTINGS} & DENYLIST:
        assert BY_KEY[key].readonly, f"{key} is curated, denylisted and editable"


def test_boot_read_settings_are_on_the_page_and_marked_restart():
    """Doug's ruling, 2026-08-28: every setting belongs on the page. Hiding one
    where it cannot be viewed or edited is not acceptable.

    This reverses the v0.190.1 lesson rather than forgetting it. That failure
    was a setting that SILENTLY did nothing — offered with a "next deploy"
    badge while create_app mounted routers from the environment before the
    override layer loaded, so the override never applied at all and toggling
    events_enabled produced a portal tile whose routes did not exist. The fix is
    both halves: `boot_overrides.load_at_boot` now installs overrides BEFORE
    create_app reads anything, so a restart really does apply them, and the row
    shows which value is in force meanwhile."""
    from core.settings_registry import BOOT_READ_KEYS, BY_KEY, GROUP_RESTART

    for key in BOOT_READ_KEYS:
        spec = BY_KEY.get(key)
        assert spec is not None, f"{key} is boot-read but not on the page"
        assert spec.group == GROUP_RESTART
        assert spec.restart, f"{key} must be marked as needing a restart"
        # Editable unless it is a value the app cannot own at all.
        assert spec.readonly == (key in DENYLIST)


def test_the_release_tag_is_visible_but_never_editable():
    """It is stamped into the image. A stored override would survive a restart
    and make the deployment misreport which image it is running — so it is
    curated read-only, which is visible-and-explained rather than hidden."""
    from core.settings_registry import BY_KEY

    assert "release_tag" in BY_KEY          # on the page
    assert BY_KEY["release_tag"].readonly   # but no control
    assert not is_editable("release_tag")
    with pytest.raises(SettingsError):
        validate_value("release_tag", "v9.9.9")


def test_a_stored_denylisted_row_is_ignored_on_load():
    """A row can outlive the rule that allowed it — filtering only on write
    would leave a stale override live forever. Uses a genuinely denylisted key:
    the boot-read ones are permitted now."""
    rows = {
        "espo_base_url": _override("espo_base_url", "https://evil.example"),
        "worker_batch_size": _override("worker_batch_size", "7"),
    }
    assert global_overrides(rows) == {"worker_batch_size": "7"}


def test_a_boot_read_override_now_survives_the_load():
    """The other half of the ruling: these must actually reach the config layer,
    or "takes effect on restart" would still be a promise the app cannot keep."""
    rows = {"events_enabled": _override("events_enabled", "true")}
    assert global_overrides(rows) == {"events_enabled": "true"}


# --- scoped rollout ----------------------------------------------------------

def _override(key, value, **kw):
    return Override(key=key, value=value, **kw)


def test_scoped_override_is_excluded_from_global_config():
    rows = {
        "gcal_events": _override("gcal_events", "true", scope_teams=("Mentor Team",)),
        "worker_batch_size": _override("worker_batch_size", "5"),
    }
    assert global_overrides(rows) == {"worker_batch_size": "5"}


def test_scoped_override_applies_only_to_matching_users(monkeypatch):
    from core import settings_store

    monkeypatch.setattr(
        settings_store, "_scoped",
        {"gcal_events": _override("gcal_events", "true", scope_teams=("Mentor Team",))},
    )
    s = get_settings()
    assert s.gcal_events is False
    assert setting_for_user("gcal_events", _STAFF, s) is True     # in the team
    assert setting_for_user("gcal_events", _ADMIN, s) is False    # not in the team
    assert setting_for_user("gcal_events", None, s) is False      # no user at all


# --- the page payload --------------------------------------------------------

class FakeStore:
    def __init__(self, rows=None):
        self.rows = rows or {}

    async def load(self):
        return dict(self.rows)


@pytest.mark.asyncio
async def test_page_payload_shows_both_values_when_they_disagree():
    apply_overrides({"worker_batch_size": "42"})
    store = FakeStore({"worker_batch_size": _override("worker_batch_size", "42")})
    payload = await page_payload(store)
    row = next(
        r for g in payload["groups"] for r in g["settings"]
        if r["key"] == "worker_batch_size"
    )
    assert row["value"] == "42"
    assert row["envValue"] == "10"
    assert row["differs"] is True
    assert row["source"] == "override"


@pytest.mark.asyncio
async def test_page_payload_never_leaks_a_secret():
    payload = await page_payload(FakeStore())
    everything = payload["other"] + [
        r for g in payload["groups"] for r in g["settings"]
    ]
    secret_rows = [r for r in everything if r.get("secret")]
    assert secret_rows, "expected some secret rows in the read-only list"
    for row in secret_rows:
        assert row["value"] == "••••••••"
        assert row["isSet"] in (True, False)


@pytest.mark.asyncio
async def test_worker_only_settings_are_not_scopable():
    payload = await page_payload(FakeStore())
    rows = {r["key"]: r for g in payload["groups"] for r in g["settings"]}
    assert rows["gmail_sync_seconds"]["scopable"] is False   # worker
    assert rows["membership_refresh_seconds"]["scopable"] is True  # web


@pytest.mark.asyncio
async def test_overdue_temporary_overrides_are_reported():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    store = FakeStore({
        "gmail_resync": _override("gmail_resync", "true", temporary=True, review_at=past),
    })
    payload = await page_payload(store)
    assert [o["key"] for o in payload["overdue"]] == ["gmail_resync"]


# --- environment diff --------------------------------------------------------

def test_diff_reports_differing_values_and_secret_presence():
    settings = get_settings()
    local = snapshot_mod.build_snapshot(settings)
    peer = snapshot_mod.build_snapshot(settings)
    peer["environment"] = "test"
    peer["settings"]["gmail_sync"]["value"] = "true"
    # Flip whatever this machine's .env happens to say, so the assertion is
    # about the comparison rather than about the developer's environment.
    local_has_key = bool(local["settings"]["fathom_api_key"]["set"])
    peer["settings"]["fathom_api_key"] = {"secret": True, "set": not local_has_key}

    result = snapshot_mod.diff_snapshots(local, peer)
    keys = {d["key"]: d for d in result["differences"]}
    assert keys["gmail_sync"]["local"] == "false"
    assert keys["gmail_sync"]["peer"] == "true"
    assert keys["fathom_api_key"]["kind"] == "secret-presence"
    assert keys["fathom_api_key"]["local"] == ("set" if local_has_key else "not set")
    assert keys["fathom_api_key"]["peer"] == ("not set" if local_has_key else "set")


def test_diff_reports_nothing_when_the_two_agree():
    settings = get_settings()
    local = snapshot_mod.build_snapshot(settings)
    peer = snapshot_mod.build_snapshot(settings)
    result = snapshot_mod.diff_snapshots(local, peer)
    assert result["differences"] == []
    assert result["sameCount"] == len(snapshot_mod.compared_keys())


def test_snapshot_never_contains_a_secret_value(monkeypatch):
    monkeypatch.setenv("FATHOM_API_KEY", "super-secret-value")
    monkeypatch.setenv("ESPO_API_KEY", "another-secret")
    get_settings.cache_clear()
    snap = snapshot_mod.build_snapshot(get_settings())
    assert snap["settings"]["fathom_api_key"] == {"secret": True, "set": True}
    assert "super-secret-value" not in str(snap)
    assert "another-secret" not in str(snap)


def test_peer_token_closed_when_unset():
    settings = get_settings()
    assert settings.setup_peer_token == ""
    assert snapshot_mod.token_matches(settings, "") is False
    assert snapshot_mod.token_matches(settings, "guess") is False


# --- jobs --------------------------------------------------------------------

class FakeJobStore:
    def __init__(self):
        self.rows = {}

    async def start(self, spec, mode, *, actor, reason, plan_of=""):
        job_id = f"job{len(self.rows) + 1}"
        self.rows[job_id] = {
            "id": job_id, "job_key": spec.key, "mode": mode, "status": "running",
            "plan_fingerprint": None, "plan_of": plan_of or None, "output": None,
            "error": None, "reason": reason, "actor": actor,
            "started_at": datetime.now(timezone.utc), "finished_at": None,
        }
        return job_id

    async def finish(self, job_id, spec, mode, *, status, output="", error="",
                     plan_fingerprint="", actor="", reason="", plan_of=""):
        self.rows[job_id].update({
            "status": status, "output": output or None, "error": error or None,
            "plan_fingerprint": plan_fingerprint or None,
        })

    async def get(self, job_id):
        return self.rows.get(job_id)

    async def recent(self, limit=25):
        return list(self.rows.values())


def _spec(plan_text):
    async def dry(_settings):
        return plan_text["value"]

    async def apply(_settings):
        return "applied"

    return jobs_mod.JobSpec(
        key="t", name="T", description="", mutating=True, dry_run=dry, apply=apply
    )


@pytest.mark.asyncio
async def test_apply_requires_a_dry_run_first():
    store = FakeJobStore()
    spec = _spec({"value": "plan"})
    result = await jobs_mod.run_apply(
        store, spec, get_settings(), plan_id="", actor="a", reason="r"
    )
    assert result["status"] == jobs_mod.STATUS_REFUSED


@pytest.mark.asyncio
async def test_apply_runs_the_reviewed_plan():
    store = FakeJobStore()
    plan = {"value": "one change"}
    spec = _spec(plan)
    dry = await jobs_mod.run_dry_run(store, spec, get_settings(), actor="a", reason="")
    result = await jobs_mod.run_apply(
        store, spec, get_settings(), plan_id=dry["id"], actor="a", reason="because"
    )
    assert result["status"] == jobs_mod.STATUS_DONE
    assert result["output"] == "applied"


@pytest.mark.asyncio
async def test_apply_refused_when_the_plan_moved():
    """Ruling 7: you apply the plan you reviewed, not a fresh one."""
    store = FakeJobStore()
    plan = {"value": "one change"}
    spec = _spec(plan)
    dry = await jobs_mod.run_dry_run(store, spec, get_settings(), actor="a", reason="")
    plan["value"] = "something else entirely"   # the world moved
    result = await jobs_mod.run_apply(
        store, spec, get_settings(), plan_id=dry["id"], actor="a", reason="because"
    )
    assert result["status"] == jobs_mod.STATUS_REFUSED
    assert "changed since you reviewed it" in result["error"]


def test_jobs_without_a_dry_run_are_not_runnable():
    receipt = jobs_mod.BY_KEY["receipt_sweep"]
    assert receipt.mutating and not receipt.runnable
    assert receipt.unavailable_reason


# --- routing and the admin gate ---------------------------------------------

def _app(monkeypatch, *, enabled=True, database="postgresql://x/y"):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("SETUP_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("DATABASE_URL", database)
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.settings_store = FakeStore()
    app.state.job_store = None
    return app


def _authed(monkeypatch, user):
    monkeypatch.setattr("setup.router.current_user", lambda r: user)


def test_setup_requires_authentication(monkeypatch):
    _authed(monkeypatch, None)
    app = _app(monkeypatch)
    # The lifespan would try to reach the (fake) database; the routes are what
    # is under test, so exercise them without starting it.
    client = TestClient(app)
    assert client.get("/setup/api/settings").status_code == 401


def test_setup_is_admin_only(monkeypatch):
    _authed(monkeypatch, _STAFF)
    client = TestClient(_app(monkeypatch))
    resp = client.get("/setup/api/settings")
    assert resp.status_code == 403
    assert "administrator" in resp.json()["detail"]


def test_admin_sees_the_page(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    client = TestClient(_app(monkeypatch))
    body = client.get("/setup/api/settings").json()
    assert body["groups"] and body["overridesActive"] is True


def test_setup_absent_when_disabled(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    client = TestClient(_app(monkeypatch, enabled=False))
    assert client.get("/setup/api/settings").status_code == 404


def test_setup_absent_without_a_database(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    client = TestClient(_app(monkeypatch, database=""))
    assert client.get("/setup/api/settings").status_code == 404


def test_snapshot_endpoint_absent_without_a_token(monkeypatch):
    client = TestClient(_app(monkeypatch))
    assert client.get("/api/setup/snapshot").status_code == 404


def test_snapshot_endpoint_rejects_a_wrong_token(monkeypatch):
    monkeypatch.setenv("SETUP_PEER_TOKEN", "right")
    client = TestClient(_app(monkeypatch))
    assert client.get("/api/setup/snapshot").status_code == 401
    assert client.get(
        "/api/setup/snapshot", headers={"X-CBM-Setup-Token": "wrong"}
    ).status_code == 401
    ok = client.get("/api/setup/snapshot", headers={"X-CBM-Setup-Token": "right"})
    assert ok.status_code == 200 and "settings" in ok.json()


def test_portal_tile_is_admin_only(monkeypatch):
    from portal.router import _apps_for

    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("SETUP_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    get_settings.cache_clear()
    settings = get_settings()
    titles = {a["title"] for a in _apps_for(_ADMIN, settings)}
    assert "System Settings" in titles
    assert "System Settings" not in {a["title"] for a in _apps_for(_STAFF, settings)}


def test_healthz_reports_the_override_layer(monkeypatch):
    client = TestClient(_app(monkeypatch))
    body = client.get("/healthz").json()
    assert body["settings"]["page"] is True
    assert body["settings"]["overridesActive"] is True
    assert "settingsVersion" in body["settings"]
