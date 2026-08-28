"""Dangerous settings are editable, and something catches a bad value.

Doug's ruling, 2026-08-28: *"All settings should be editable, unless a change
would make the system unusable. Then there must be a verification that the
system is still functional."*

Twenty settings that used to be hidden are now editable. That is only defensible
because three mechanisms stand behind them, and these tests are the things that
notice if one quietly stops working:

* a **pre-flight probe** tries the value and refuses one that fails;
* a **post-apply check** undoes a change that broke the system;
* a **confirm-or-revert countdown** rescues an admin who locked themselves out,
  which is the case no probe and no health check can ever detect — the
  application is working perfectly and simply will not let anyone back in.

The property worth stating plainly, because it is what makes the ruling safe
rather than reckless: **hiding these settings never made them safe.** It moved
the risk to whoever edits the deployment configuration by hand, where there is
no probe, no health check and no undo at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.settings_registry import DENYLIST, LOCKOUT_KEYS, VERIFIED_KEYS, is_editable
from core.settings_store import Override, SettingsError
from setup import verify
from setup.router import CONFIRM_WINDOW_MINUTES, _revert_deadline


# --- the probes -------------------------------------------------------------

@pytest.mark.anyio
async def test_a_probe_refuses_a_value_that_cannot_work():
    got = await verify.probe("google_service_account_json", "{ not json")
    assert got.outcome == verify.FAILED
    assert got.blocks_save


def _live(**kw):
    """A Settings that is NOT in dry-run, so the CRM probe actually tries.

    Worth its own helper: the default test environment has dry-run on, where
    the probe correctly returns OK without connecting to anything — which would
    make every probe test below pass for the wrong reason.
    """
    from core.config import Settings

    return Settings(**{
        "espo_dry_run": False,
        "espo_base_url": "https://nothing.invalid",
        "espo_api_key": "k",
        **kw,
    })


@pytest.mark.anyio
async def test_dry_run_needs_no_crm_check():
    from core.config import Settings

    got = await verify._crm_reachable(Settings(espo_dry_run=True))
    assert got.outcome == verify.OK
    assert "Dry-run" in got.detail


@pytest.mark.anyio
async def test_a_probe_that_cannot_reach_its_target_says_unknown_never_ok():
    """Reporting success for an unverified value is this codebase's documented
    failure mode, and it is exactly what a verification feature must not do."""
    got = await verify._crm_reachable(_live())
    assert got.outcome == verify.UNKNOWN
    assert got.outcome != verify.OK


@pytest.mark.anyio
async def test_a_missing_key_is_a_failure_not_an_unknown():
    got = await verify._crm_reachable(_live(espo_api_key=""))
    assert got.outcome == verify.FAILED


@pytest.mark.anyio
async def test_unknown_does_not_block_the_save():
    """An admin fixing configuration DURING an outage must not be blocked by the
    outage — that is when they most need the page."""
    assert not verify.Result(verify.UNKNOWN, "unreachable").blocks_save
    assert verify.Result(verify.FAILED, "rejected").blocks_save


@pytest.mark.anyio
async def test_an_uncheckable_setting_is_reported_as_such_not_as_passing():
    got = await verify.probe("worker_batch_size", "5")
    assert got.outcome == verify.NOT_CHECKED
    assert not got.blocks_save


@pytest.mark.anyio
async def test_a_probe_never_raises_however_badly_it_fails(monkeypatch):
    async def _boom(_k, _v):
        raise RuntimeError("probe exploded")

    monkeypatch.setitem(verify.PROBES, "espo_api_key", _boom)
    got = await verify.probe("espo_api_key", "x")
    assert got.outcome == verify.UNKNOWN
    assert not got.blocks_save


@pytest.mark.anyio
async def test_the_crm_probe_rejects_a_stranger_instance():
    """A bare connectivity check would pass on any EspoCRM and then fail on
    every write. The probe asks for one of this application's own entities."""
    class _Client:
        async def metadata(self, key):
            return {}  # answers, but has no CEngagement

    import core.espo as espo_mod
    real = espo_mod.EspoClient
    espo_mod.EspoClient = lambda *a, **k: _Client()
    try:
        got = await verify._crm_reachable(_live())
    finally:
        espo_mod.EspoClient = real
    assert got.outcome == verify.FAILED
    assert "CEngagement" in got.detail


# --- the countdown ----------------------------------------------------------

def test_lockout_settings_get_a_deadline():
    for key in LOCKOUT_KEYS:
        deadline = _revert_deadline(key)
        assert deadline is not None, key
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        assert 0 < remaining <= CONFIRM_WINDOW_MINUTES * 60 + 5


def test_nothing_else_gets_one():
    """An unattended change undoing itself is disruptive. It must happen only
    where the alternative is being locked out."""
    for key in ("worker_batch_size", "espo_api_key", "gmail_sync", "organization_name"):
        assert _revert_deadline(key) is None


def test_a_change_with_a_deadline_starts_unconfirmed():
    """Silence is what undoes it. A change that started confirmed would sit
    there forever and the mechanism would be decorative."""
    o = Override(key="setup_enabled", value="false",
                 revert_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                 confirmed=False)
    assert o.awaiting_confirmation


def test_a_confirmed_change_is_not_awaiting_anything():
    o = Override(key="setup_enabled", value="false", revert_at=None, confirmed=True)
    assert not o.awaiting_confirmation


# --- what stays impossible, and why -----------------------------------------

def test_only_three_things_cannot_be_changed():
    assert DENYLIST == {"database_url", "app_encryption_key", "release_tag"}


@pytest.mark.parametrize("key,phrase", [
    ("database_url", "left behind in the database"),
    ("app_encryption_key", "permanently unreadable"),
    ("release_tag", "misreport which build"),
])
def test_each_refusal_explains_itself(key, phrase):
    """'You cannot do that' with no reason is what makes people edit the
    deployment configuration by hand instead."""
    from core.settings_store import validate_value

    with pytest.raises(SettingsError) as e:
        validate_value(key, "x")
    assert phrase in str(e.value)


def test_everything_previously_hidden_is_now_editable():
    """The twenty settings this ruling was about."""
    for key in (
        "espo_base_url", "espo_api_key", "espo_dry_run", "espo_provision_username",
        "espo_provision_password", "session_secret", "session_cookie_secure",
        "allowed_origins", "setup_enabled", "settings_overrides", "setup_peer_url",
        "setup_peer_token", "google_service_account_json", "anthropic_api_key",
        "zoom_account_id", "zoom_client_id", "zoom_client_secret", "fathom_api_key",
        "youtube_api_key", "sandbox_nightly_reset",
    ):
        assert is_editable(key), f"{key} is still hidden"
        assert key in (LOCKOUT_KEYS | VERIFIED_KEYS), f"{key} has no safety tier"


def test_the_database_url_is_masked_not_merely_read_only():
    """A Postgres URL carries the password inside it. Read-only is not enough —
    rendering the value hands any admin the database credential, which it did in
    the read-only "show all" list before 2026-08-28."""
    from core.settings_registry import SECRET_KEYS, is_secret

    assert is_secret("database_url")
    assert "database_url" in SECRET_KEYS
    d = Override(key="database_url", value="postgres://u:pw@h/db").as_dict()
    assert "pw" not in str(d)


# --- secrets: editable, never readable --------------------------------------

def test_a_secret_is_never_rendered_back():
    d = Override(key="espo_api_key", value="hunter2").as_dict()
    assert d["value"] == ""
    assert d["isSet"] is True
    assert "hunter2" not in str(d)


def test_a_non_secret_is_rendered_normally():
    d = Override(key="worker_batch_size", value="25").as_dict()
    assert d["value"] == "25"
    assert d["isSet"] is None


def test_a_secret_is_refused_rather_than_written_in_plain_text():
    """Quietly writing a plaintext credential into a database that gets backed
    up is not a failure to fail open on."""
    from core.settings_store import SettingsStore

    store = SettingsStore.__new__(SettingsStore)
    store._cipher = None
    with pytest.raises(SettingsError) as e:
        store._encode("espo_api_key", "hunter2")
    assert "encryption key" in str(e.value)


def test_a_secret_round_trips_through_the_cipher():
    from core.crypto import SecretCipher
    from core.settings_store import SettingsStore

    store = SettingsStore.__new__(SettingsStore)
    store._cipher = SecretCipher(SecretCipher.generate_key())
    stored, encrypted = store._encode("espo_api_key", "hunter2")
    assert encrypted
    assert stored != "hunter2"          # not plain text at rest
    assert store._decode(stored, True) == "hunter2"


def test_an_undecryptable_secret_does_not_break_the_load():
    """A rotated key must degrade to 'this setting is unusable', never to an
    exception that stops every other setting loading with it."""
    from core.crypto import SecretCipher
    from core.settings_store import SettingsStore

    store = SettingsStore.__new__(SettingsStore)
    store._cipher = SecretCipher(SecretCipher.generate_key())
    assert store._decode("not-a-valid-token", True) == ""
