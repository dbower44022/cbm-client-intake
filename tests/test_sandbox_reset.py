"""The safety properties of the nightly sandbox reset.

``scripts/sandbox/reset_crm_sandbox.py`` runs on the crm-test droplet and
drops the CRM's record tables.  It is the most destructive thing in this
repository, so the two properties that stop it destroying the wrong thing are
tested here rather than trusted:

* :func:`test_it_refuses_a_non_sandbox_site` — the production guard.  The
  script reads the deployment's own site URL and refuses anything that is not
  crm-test, so a copy of it landing on the wrong droplet is inert.
* :func:`test_credentials_and_definitions_are_kept` — the keep-list floor.
  Losing ``integration`` / ``external_account`` / ``o_auth_*`` / ``app_secret``
  would silently disconnect Google every night; losing ``role`` / ``team``
  would lock everyone out of a sandbox they are meant to train on.

:func:`test_keep_by_exception` pins the direction of the default: an entity the
CRM team adds later is NOT in the keep list, so it resets as records without
anyone remembering to update anything.  That is the property that lets the CRM
team keep working on crm-test while it doubles as the training sandbox.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sandbox" / "reset_crm_sandbox.py"

_spec = importlib.util.spec_from_file_location("reset_crm_sandbox", SCRIPT)
assert _spec and _spec.loader
sandbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sandbox)


def _fake_home(tmp_path: Path, site_url: str) -> Path:
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  espocrm-db:\n"
        "    environment:\n"
        "      MARIADB_ROOT_PASSWORD: not-a-real-password\n"
        "  espocrm:\n"
        "    environment:\n"
        f'      ESPOCRM_CONFIG_SITE_URL: "{site_url}"\n',
        encoding="utf-8",
    )
    return tmp_path


def test_it_refuses_a_non_sandbox_site(tmp_path, monkeypatch):
    """Pointed at production, the script exits instead of resetting anything."""
    monkeypatch.setattr(sandbox, "HOME", _fake_home(tmp_path, "https://crm.clevelandbusinessmentors.org"))
    with pytest.raises(SystemExit) as excinfo:
        sandbox.guard_not_production()
    assert "REFUSING" in str(excinfo.value)


def test_it_allows_the_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "HOME", _fake_home(tmp_path, "https://crm-test.clevelandbusinessmentors.org"))
    sandbox.guard_not_production()  # does not raise


def test_credentials_and_definitions_are_kept():
    """Tables whose loss would break the sandbox rather than clean it."""
    must_survive = {
        # Google / mailbox wiring — a reset that drops these disconnects the app.
        "integration", "external_account", "o_auth_account", "o_auth_provider",
        "app_secret", "inbound_email", "email_account",
        # Access control — trainees have to be able to log in on day two.
        "role", "team", "portal",
        # Authored artefacts staff build up: templates drive the email tooling.
        "email_template", "scheduled_job", "system_data",
    }
    assert must_survive <= sandbox.KEEP_TABLES


def test_keep_by_exception():
    """Record tables — including every custom entity — must NOT be kept.

    This is the direction that matters: a new ``c_*`` table the CRM team adds
    after the baseline defaults to resetting, so nobody has to maintain a list
    to keep the sandbox pristine.
    """
    records = {
        "account", "contact", "c_engagement", "c_session", "c_mentor_profile",
        "c_partner_profile", "c_sponsor_profile", "c_intake_submission",
        "attachment", "email", "note", "user", "preferences", "team_user",
    }
    assert not (records & sandbox.KEEP_TABLES)


# ---------------------------------------------------------------------------
# The app-database half (core/sandbox_reset.py)
# ---------------------------------------------------------------------------

import re  # noqa: E402

from core import sandbox_reset  # noqa: E402
from core.config import Settings  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _tables_created_by_migrations() -> set[str]:
    names: set[str] = set()
    for path in MIGRATIONS.glob("*.py"):
        names |= set(re.findall(r'op\.create_table\(\s*"(\w+)"', path.read_text(encoding="utf-8")))
    return names


def test_every_app_table_is_classified():
    """The maintenance guard, and the reason this half lives in the repo.

    A migration that adds a table fails here until someone decides whether it
    holds training data or configuration. Without this the sandbox quietly
    stops being pristine one table at a time.
    """
    unclassified = sandbox_reset.unclassified(_tables_created_by_migrations())
    assert not unclassified, (
        f"unclassified app tables: {sorted(unclassified)} — add each to RESET_TABLES "
        "or KEEP_TABLES in core/sandbox_reset.py"
    )


def test_reset_and_keep_do_not_overlap():
    assert not (set(sandbox_reset.RESET_TABLES) & sandbox_reset.KEEP_TABLES)


def test_the_setup_overrides_survive():
    """crm-test is the only pre-production review gate this project has.

    A flag turned on at /setup to review a change must still be on in the
    morning, so app_setting is never cleared.
    """
    assert "app_setting" in sandbox_reset.KEEP_TABLES
    assert "app_setting_history" in sandbox_reset.KEEP_TABLES
    assert "app_setting" not in sandbox_reset.RESET_TABLES


def test_the_ops_queue_and_drive_index_reset():
    """Both halves have to move together, or the sandbox is merely confusing."""
    for table in ("submission", "record_comment", "app_document", "conversation_thread"):
        assert table in sandbox_reset.RESET_TABLES


def test_guard_refuses_when_the_flag_is_off():
    settings = Settings(espo_base_url="https://crm-test.clevelandbusinessmentors.org")
    with pytest.raises(sandbox_reset.SandboxResetRefused):
        sandbox_reset.guard(settings)


def test_guard_refuses_production_even_with_the_flag_on():
    """The flag alone is not enough: the CRM URL decides.

    Deliberately not Settings.environment — that honours ENV_LABEL, and the
    guard on a destructive job must not be overridable by a label.
    """
    settings = Settings(
        espo_base_url="https://crm.clevelandbusinessmentors.org",
        sandbox_nightly_reset=True,
        env_label="test",
    )
    with pytest.raises(sandbox_reset.SandboxResetRefused) as excinfo:
        sandbox_reset.guard(settings)
    assert "not the sandbox" in str(excinfo.value)


def test_guard_allows_the_armed_sandbox():
    settings = Settings(
        espo_base_url="https://crm-test.clevelandbusinessmentors.org",
        sandbox_nightly_reset=True,
    )
    sandbox_reset.guard(settings)  # does not raise


def test_the_reset_is_off_by_default():
    assert Settings().sandbox_nightly_reset is False
