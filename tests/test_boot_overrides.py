"""Restart-required settings: the boot-time load, and telling the truth about
which value is actually in force.

Doug ruled on 2026-08-28 that **every setting belongs on the Settings page** —
hiding one where it cannot be viewed or edited is not acceptable. Honouring that
took two halves, and both are tested here:

1. **The override layer is installed before the app is built.** Without this,
   "takes effect on restart" would be false: ``create_app`` mounts routers,
   builds middleware and configures logging from the environment, and the
   overrides used to load afterwards — so every restart re-ran the mounting
   first and a stored override for one of those keys never applied at all.

2. **The page reports what the process is really running.** The periodic refresh
   installs a newer value into the live settings object while the already-built
   routers carry on with the old one, so reading the setting back would report a
   change as taken effect when it had not. The boot snapshot is the only honest
   source, and this is the failure the whole section exists to prevent.

The safety property that must not be lost in the change: **a database problem
degrades to the deployment's own values, never to the code defaults.** A
database incident must not silently reconfigure the application.
"""

from __future__ import annotations

import pytest

from core import boot_overrides
from core.config import Settings


@pytest.fixture(autouse=True)
def _clean():
    boot_overrides.reset()
    yield
    boot_overrides.reset()


class _Settings:
    """Just enough of a Settings object for load_at_boot."""

    def __init__(self, **kw):
        self.database_url = kw.get("database_url", "")
        self.settings_overrides = kw.get("settings_overrides", True)
        for k, v in kw.items():
            setattr(self, k, v)


# --- when it does nothing, it says so --------------------------------------

def test_no_database_is_reported_not_silently_skipped():
    got = boot_overrides.load_at_boot(_Settings(database_url=""))
    assert got.outcome == boot_overrides.BOOT_DISABLED
    assert got.healthy
    assert "deployment configuration" in got.detail


def test_break_glass_off_is_reported():
    got = boot_overrides.load_at_boot(
        _Settings(database_url="postgres://x", settings_overrides=False)
    )
    assert got.outcome == boot_overrides.BOOT_DISABLED


def test_it_snapshots_the_boot_read_keys_even_when_disabled():
    """The snapshot is what the page calls 'in force'. It must exist on every
    path, or a deployment with no database would have nothing to show."""
    from core.settings_registry import BOOT_READ_KEYS

    got = boot_overrides.load_at_boot(Settings(database_url=""))
    assert set(got.snapshot) == set(BOOT_READ_KEYS)


# --- failure degrades to the deployment's values, never to defaults ---------

def test_an_unreadable_database_does_not_stop_the_app(monkeypatch):
    async def _boom(_settings):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(boot_overrides, "_load", _boom)
    got = boot_overrides.load_at_boot(_Settings(database_url="postgres://x"))
    assert got.outcome == boot_overrides.BOOT_FAILED
    assert not got.healthy
    assert "connection refused" in got.detail


def test_a_failure_never_raises(monkeypatch):
    """A raise here would mean the app does not boot at all."""
    async def _boom(_settings):
        raise KeyError("anything")

    monkeypatch.setattr(boot_overrides, "_load", _boom)
    boot_overrides.load_at_boot(_Settings(database_url="postgres://x"))  # no raise


@pytest.mark.anyio
async def test_it_skips_rather_than_deadlocks_inside_a_running_loop():
    """Called from within a loop (tests, embedded use) a synchronous read would
    deadlock. The periodic refresh picks the overrides up regardless."""
    got = boot_overrides.load_at_boot(_Settings(database_url="postgres://x"))
    assert got.outcome == boot_overrides.BOOT_SKIPPED


# --- the honest "in force" reporting ----------------------------------------

def _restart_rows(payload):
    return {
        r["key"]: r
        for g in payload["groups"] if g["name"] == "Restart required"
        for r in g["settings"]
    }


@pytest.mark.anyio
async def test_nothing_pending_is_the_quiet_case():
    from setup.service import page_payload

    payload = await page_payload(None)
    assert payload["restart"]["count"] == 0
    assert payload["restart"]["pending"] == []
    for row in _restart_rows(payload).values():
        assert row["pendingRestart"] is False


@pytest.mark.anyio
async def test_a_changed_boot_read_setting_reports_the_OLD_value_as_in_force(monkeypatch):
    """The heart of it. The live settings object says the new value; the
    process is still running the old one. Reporting the live object would tell
    the reader a change had taken effect when it had not."""
    from core.config import get_settings
    from setup.service import page_payload

    # The process booted with analytics off...
    boot_overrides._state = boot_overrides.BootLoad(
        outcome=boot_overrides.BOOT_APPLIED,
        snapshot={"analytics_enabled": False},
    )
    # ...and a later refresh installed "on" into the live object.
    monkeypatch.setattr(get_settings(), "analytics_enabled", True, raising=False)

    payload = await page_payload(None)
    row = _restart_rows(payload)["analytics_enabled"]

    assert row["inForce"] == "false"       # what is actually running
    assert row["value"] == "true"          # what is stored
    assert row["pendingRestart"] is True
    assert payload["restart"]["count"] == 1
    assert payload["restart"]["pending"][0]["key"] == "analytics_enabled"


@pytest.mark.anyio
async def test_the_page_says_when_the_boot_load_itself_failed():
    """If the stored settings could not be read at startup, NONE of them are in
    force — whatever the rows say. The page has to be able to say that."""
    from setup.service import page_payload

    boot_overrides._state = boot_overrides.BootLoad(
        outcome=boot_overrides.BOOT_FAILED, detail="OperationalError: timeout"
    )
    payload = await page_payload(None)
    assert payload["restart"]["bootOutcome"] == "failed"
    assert "timeout" in payload["restart"]["bootDetail"]


@pytest.mark.anyio
async def test_the_read_only_row_offers_no_control():
    from setup.service import page_payload

    row = _restart_rows(await page_payload(None))["release_tag"]
    assert row["editable"] is False
