"""The scripts a chapter build runs must never carry another chapter's values,
and must never complete a chapter's CRM target from Cleveland's own settings.

Four defects, found by the deployment guide's precision sweep (2026-09-19):
render_spec.py hard-coded the trial chapter's label, origin and branch;
apply_api_half.py hard-coded Lakeside's name and provisioning account; and
preflight_crm.py and build_networkstandard.py filled a missing half of a CRM
target from this deployment's settings or the repo's .env."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


render_spec = _load("scripts/rehearsal/render_spec.py", "render_spec_under_test")
apply_api_half = _load("scripts/rehearsal/apply_api_half.py", "apply_api_half_under_test")
preflight = _load("scripts/preflight_crm.py", "preflight_under_test")
networkstandard = _load("scripts/build_networkstandard.py", "networkstandard_under_test")


def _values(**over):
    v = {
        "chapter": {"name": "Akron Business Mentors", "slug": "akron", "timezone": "America/Chicago",
                    "currency": "USD", "locale": "en_US"},
        "web": {"app_base_url": "https://apps.akronmentors.org/some/path",
                "events_public_base_url": "",
                "docs_site_url": "",
                "policy_client_conduct_url": "https://akronmentors.org/a/",
                "policy_mentor_ethics_url": "https://akronmentors.org/b/",
                "policy_terms_url": "https://akronmentors.org/c/",
                "policy_privacy_url": "https://akronmentors.org/d/"},
        "crm": {"base_url": "https://crm.akronmentors.org", "application_name": "Akron CRM",
                "outbound_from_name": "Akron Business Mentors",
                "outbound_from_address": "info@akronmentors.org"},
        "flags": {"espo_dry_run": False, "async_delivery": True, "analytics_enabled": True,
                  "setup_enabled": True, "events_enabled": True, "events_public_api": False,
                  "record_quick_add": True, "mentor_provision_users": True, "deploy_on_push": True},
    }
    v.update(over)
    return v


SECRETS = {"ESPO_API_KEY": "k", "ESPO_PROVISION_USERNAME": "akron.provision",
           "ESPO_PROVISION_PASSWORD": "p", "SESSION_SECRET": "s",
           "APP_ENCRYPTION_KEY": "q2Qx0p7Yw1bQ3rX9mJk8u5t4s3r2q1p0o9n8m7l6k5A="}


def _envs(spec):
    web = {e["key"]: e["value"] for e in spec["services"][0]["envs"]}
    return web


# --- render_spec ------------------------------------------------------------

def test_spec_carries_no_rehearsal_label_and_no_localhost_origin():
    web = _envs(render_spec.build_spec(_values(), SECRETS))
    assert "ENV_LABEL" not in web
    assert web["ALLOWED_ORIGINS"] == "https://apps.akronmentors.org"
    assert "localhost" not in str(web)


def test_spec_leaves_origin_out_until_the_app_address_is_known():
    v = _values()
    v["web"]["app_base_url"] = ""
    web = _envs(render_spec.build_spec(v, SECRETS))
    assert "ALLOWED_ORIGINS" not in web and "APP_BASE_URL" not in web


def test_spec_follows_the_release_branch_on_every_component():
    spec = render_spec.build_spec(_values(), SECRETS)
    branches = {spec["services"][0]["github"]["branch"], spec["workers"][0]["github"]["branch"],
                spec["jobs"][0]["github"]["branch"]}
    assert branches == {"release"}


def test_spec_refuses_the_development_branch_unless_asked_for():
    with pytest.raises(ValueError, match="release"):
        render_spec.build_spec(_values(deploy={"branch": "main"}), SECRETS)
    spec = render_spec.build_spec(
        _values(deploy={"branch": "main", "allow_development_branch": True}), SECRETS)
    assert spec["services"][0]["github"]["branch"] == "main"


def test_spec_omits_an_empty_events_address_so_the_app_uses_its_own():
    assert "EVENTS_PUBLIC_BASE_URL" not in _envs(render_spec.build_spec(_values(), SECRETS))


def _worker(spec):
    return {e["key"]: e["value"] for e in spec["workers"][0]["envs"]}


GOOGLE = {"primary_domain": "akronmentors.org", "ops_mailbox": "info@akronmentors.org",
          "alert_email_from": "alerts@akronmentors.org", "alert_email_to": "ops@akronmentors.org",
          "members_group": "members@akronmentors.org", "mentor_email_domain": "akronmentors.net",
          "delegated_admin": "admin@akronmentors.org", "shared_drive_id": "0ABCdrive",
          "zoom_host_email": "webinars@akronmentors.org"}


def _google_values(**flags):
    v = _values(google=dict(GOOGLE))
    v["flags"].update(flags)
    v["web"]["website_base_url"] = "https://akronmentors.org"
    return v


@pytest.fixture
def keyfile(tmp_path):
    import json
    p = tmp_path / "key.json"
    p.write_text(json.dumps({"type": "service_account", "private_key": "-----BEGIN\nX\n-----END\n",
                             "client_email": "sa@akron.iam.gserviceaccount.com"}, indent=2))
    return {**SECRETS, "GOOGLE_SERVICE_ACCOUNT_KEY_FILE": str(p)}


def test_spec_carries_every_chapter_setting_to_the_right_process(keyfile):
    spec = render_spec.build_spec(
        _google_values(gmail_sync=True, gcal_events=True, gdrive_docs=True,
                       google_directory_check=True, google_create_mailbox=True,
                       gdrive_identity="service"), keyfile)
    web, worker = _envs(spec), _worker(spec)
    for env in (web, worker):  # the worker decides at start-up from these
        assert env["GMAIL_SYNC"] == "true" and env["GDRIVE_DOCS"] == "true"
        assert env["OPS_MAILBOX"] == "info@akronmentors.org"
        assert env["COMMS_INTERNAL_DOMAINS"] == "akronmentors.org,akronmentors.net"
        assert env["MENTOR_EMAIL_DOMAIN"] == "akronmentors.net"
        assert env["GDRIVE_SHARED_DRIVE_ID"] == "0ABCdrive" and env["GDRIVE_IDENTITY"] == "service"
        assert env["APP_ENCRYPTION_KEY"] == SECRETS["APP_ENCRYPTION_KEY"]
        assert env["APP_BASE_URL"] == "https://apps.akronmentors.org/some/path"
        assert "\n" not in env["GOOGLE_SERVICE_ACCOUNT_JSON"]  # one line
    assert web["GCAL_EVENTS"] == "true" and web["GOOGLE_CREATE_MAILBOX"] == "true"
    assert web["GOOGLE_DELEGATED_ADMIN"] == "admin@akronmentors.org"
    assert web["ORGANIZATION_WEBSITE_URL"] == "https://akronmentors.org"
    assert "cbmentors" not in str(spec) and "cleveland" not in str(spec).lower()


def test_spec_refuses_google_switches_without_the_key():
    with pytest.raises(ValueError, match="GOOGLE_SERVICE_ACCOUNT_KEY_FILE"):
        render_spec.build_spec(_google_values(gmail_sync=True), SECRETS)


def test_spec_refuses_drive_without_the_shared_drive(keyfile):
    v = _google_values(gdrive_docs=True)
    v["google"]["shared_drive_id"] = "none yet"
    with pytest.raises(ValueError, match="shared_drive_id"):
        render_spec.build_spec(v, keyfile)


def test_spec_switches_google_off_when_the_form_does(keyfile):
    spec = render_spec.build_spec(_google_values(), keyfile)
    assert _envs(spec)["GMAIL_SYNC"] == "false" and _envs(spec)["GCAL_EVENTS"] == "false"


def test_spec_treats_none_yet_as_absent():
    v = _values()
    v["web"]["docs_site_url"] = "none yet"
    assert "DOCS_SITE_URL" not in _envs(render_spec.build_spec(v, SECRETS))


def test_spec_refuses_an_encryption_key_the_application_would_reject():
    import secrets as pysecrets
    bad = {**SECRETS, "APP_ENCRYPTION_KEY": pysecrets.token_urlsafe(32)}
    with pytest.raises(ValueError, match="APP_ENCRYPTION_KEY"):
        render_spec.build_spec(_values(), bad)


def test_minted_encryption_key_is_one_the_application_accepts(tmp_path):
    from core.crypto import SecretCipher
    import yaml
    values = tmp_path / "v.yaml"
    values.write_text(yaml.safe_dump(_values()))
    env = tmp_path / "c.env"
    env.write_text("".join(f"{k}={v}\n" for k, v in SECRETS.items()
                           if k not in ("SESSION_SECRET", "APP_ENCRYPTION_KEY")))
    assert render_spec.main(["x", str(values), str(env), str(tmp_path / "out.yaml")]) == 0
    key = render_spec.read_env(env)["APP_ENCRYPTION_KEY"]
    SecretCipher(key)  # raises on a key the application would refuse


def test_spec_refuses_when_a_secret_is_not_minted():
    partial = {k: v for k, v in SECRETS.items() if k != "ESPO_API_KEY"}
    with pytest.raises(ValueError, match="ESPO_API_KEY"):
        render_spec.build_spec(_values(), partial)


# --- apply_api_half -----------------------------------------------------------

def test_crm_settings_come_from_the_chapter_form():
    s = apply_api_half.chapter_settings(_values())
    assert s["applicationName"] == "Akron CRM"
    assert s["outboundEmailFromName"] == "Akron Business Mentors"
    assert s["outboundEmailFromAddress"] == "info@akronmentors.org"
    assert s["timeZone"] == "America/Chicago"
    assert "Lakeside" not in str(s)


def test_crm_settings_refuse_a_form_without_a_name():
    with pytest.raises(ValueError):
        apply_api_half.chapter_settings({"chapter": {}})


def test_provisioning_account_is_the_chapters_own():
    assert apply_api_half.provision_user(_values(), {}) == "akron.provision"
    assert apply_api_half.provision_user(_values(), {"ESPO_PROVISION_USERNAME": "x.provision"}) == "x.provision"
    assert not hasattr(apply_api_half, "PROVISION_USER")
    assert not hasattr(apply_api_half, "CHAPTER_NAME")


# --- preflight_crm --------------------------------------------------------------

def _settings(url="https://crm-test.example", key="cleveland-key"):
    return lambda: SimpleNamespace(espo_base_url=url, espo_api_key=key)


def test_preflight_uses_the_arguments_when_both_are_given():
    url, key, source = preflight.resolve_target("https://crm.akron", "akron-key", _settings())
    assert (url, key) == ("https://crm.akron", "akron-key") and "arguments" in source


def test_preflight_uses_the_deployment_when_neither_is_given():
    url, key, _ = preflight.resolve_target(None, None, _settings())
    assert (url, key) == ("https://crm-test.example", "cleveland-key")


@pytest.mark.parametrize("url,key", [("https://crm.akron", None), (None, "akron-key")])
def test_preflight_never_completes_half_a_target_from_the_deployment(url, key):
    with pytest.raises(ValueError, match="together"):
        preflight.resolve_target(url, key, _settings())


def test_preflight_explains_when_nothing_is_configured():
    with pytest.raises(ValueError, match="--url"):
        preflight.resolve_target(None, None, _settings(url="", key=""))


# --- build_networkstandard -------------------------------------------------------

def _dotenv(tmp_path):
    p = tmp_path / ".env"
    p.write_text("ESPO_ADMIN_BASE=https://crm-test.example\nESPO_ADMIN_USER=clev\n"
                 "ESPO_ADMIN_PASS=clevpass\nESPO_API_KEY=cleveland-key\n")
    return p


def test_networkstandard_never_mixes_the_environment_with_dotenv(tmp_path):
    env, source = networkstandard._env({"ESPO_ADMIN_BASE": "https://crm.akron"}, _dotenv(tmp_path))
    assert source == "the environment"
    assert env["ESPO_ADMIN_BASE"] == "https://crm.akron"
    assert env["ESPO_API_KEY"] == "" and env["ESPO_ADMIN_PASS"] == ""


def test_networkstandard_reads_dotenv_only_when_the_environment_is_silent(tmp_path):
    env, source = networkstandard._env({"PATH": "/usr/bin"}, _dotenv(tmp_path))
    assert ".env" in source
    assert env["ESPO_ADMIN_BASE"] == "https://crm-test.example"
    assert env["ESPO_API_KEY"] == "cleveland-key"
