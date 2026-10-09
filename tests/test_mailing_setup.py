"""Phase C piece 2 — the mailing service settings, readiness line and the
connect / callback / disconnect round trip on the System Settings page.

The vendor is never called: the code exchange and the account read are
monkeypatched, and the connection store is a fake. What is protected is the
gate (admins only, page on), the redirect address coming from APP_BASE_URL and
nowhere else, the state check, the outcome landing on the Readiness tab, and
the rule that no token ever reaches the browser.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from core import action_log
from core import mailing as mailing_mod
from core.app import create_app
from core.config import Settings, get_settings
from core.mailing import Connection, MailingError, TokenSet
from core.settings_registry import SECRET_KEYS, VERIFIED_KEYS, spec_for
from forms import info_request
from setup import mailing as setup_mailing
from setup.readiness import FEATURES, readiness_payload

from tests.test_system_settings import _ADMIN, _STAFF, FakeStore

REDIRECT = "https://cbm-client-intake-svxs3.ondigitalocean.app/api/setup/mailing/callback"
_NOW = datetime(2026, 10, 9, 1, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeConnStore:
    """The connection store's surface, in memory; ``_cipher`` mirrors the real one."""

    def __init__(self, conn=None, *, cipher=True):
        self.conn = conn
        self._cipher = object() if cipher else None
        self.saved = []
        self.deleted = 0

    async def get(self):
        return self.conn

    async def save(self, tokens, *, account_label, connected_by, scopes=""):
        self.saved.append({"tokens": tokens, "label": account_label, "by": connected_by})
        self.conn = _connection(label=account_label)

    async def delete(self):
        existed = self.conn is not None
        self.conn = None
        self.deleted += 1
        return existed


def _connection(status=mailing_mod.STATUS_CONNECTED, label="Test Org", error=None):
    return Connection(
        status=status, account_label=label, connected_by="adm", connected_at=_NOW,
        expires_at=_NOW + timedelta(hours=24), last_refresh_at=None, last_error=error,
        scopes=("contact_data",), list_id=None, pull_cursor=None, last_push_at=None,
        last_push_summary=None,
    )


def _app(monkeypatch, *, store=None, client_id="api-key", secret="sec", base_url="https://cbm-client-intake-svxs3.ondigitalocean.app/"):
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    monkeypatch.setenv("SETUP_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("APP_BASE_URL", base_url)
    monkeypatch.setenv("MAILING_CLIENT_ID", client_id)
    monkeypatch.setenv("MAILING_CLIENT_SECRET", secret)
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.settings_store = FakeStore()
    app.state.job_store = None
    app.state.mailing_store = store if store is not None else FakeConnStore()
    return app


def _authed(monkeypatch, user):
    monkeypatch.setattr("setup.router.current_user", lambda r: user)


def _logged(monkeypatch):
    calls = []

    async def fake(**kw):
        calls.append(kw)
        return True

    monkeypatch.setattr(action_log, "log_action", fake)
    return calls


# --- settings -----------------------------------------------------------------------


def test_the_redirect_address_comes_from_app_base_url_only():
    assert Settings(app_base_url="https://apps.example.org/").mailing_redirect_uri \
        == "https://apps.example.org/api/setup/mailing/callback"
    assert Settings(app_base_url="").mailing_redirect_uri == ""


def test_the_client_secret_is_a_secret_and_not_a_verified_key():
    assert "mailing_client_secret" in SECRET_KEYS
    assert "mailing_client_secret" not in VERIFIED_KEYS  # the Connect step is its check
    assert spec_for("mailing_sync").component == "worker"
    assert spec_for("mailing_client_id").component == "both"
    for key in ("mailing_list_name", "mailing_push_seconds", "mailing_pull_seconds"):
        assert spec_for(key).component == "worker"
    assert Settings().mailing_list_name == "Event notices"
    assert Settings().mailing_push_seconds == 86400 and Settings().mailing_pull_seconds == 3600


def test_the_settings_labels_never_name_the_vendor():
    """Plan § 11.4: the page reads the same on every chapter; help text may name it."""
    for key in ("mailing_sync", "mailing_client_id", "mailing_client_secret",
                "mailing_list_name", "mailing_push_seconds", "mailing_pull_seconds",
                "mailing_base_url"):
        assert "constant" not in spec_for(key).label.lower(), key


# --- readiness ----------------------------------------------------------------------


def _feature():
    return next(f for f in FEATURES if f.key == "mailing")


def test_the_mailing_feature_runs_on_the_worker_and_needs_the_pair_and_a_database():
    f = _feature()
    assert f.component == "worker" and f.flag == "mailing_sync" and f.needs_database
    assert set(f.requires) == {"mailing_client_id", "mailing_client_secret"}


async def _readiness(monkeypatch, store, **env):
    monkeypatch.setattr("setup.readiness._crm_snapshot", _none)
    settings = Settings(app_base_url="https://apps.example.org", **env)
    return await readiness_payload(settings, None, store)


async def _none(settings):
    return None


def _mailing_row(payload):
    return next(f for f in payload["features"] if f["key"] == "mailing")


@pytest.mark.asyncio
async def test_readiness_says_not_connected_and_shows_the_redirect_address(monkeypatch):
    payload = await _readiness(monkeypatch, FakeConnStore(None), mailing_client_id="k", mailing_client_secret="s")
    row = _mailing_row(payload)
    line = next(c for c in row["checks"] if c["kind"] == "connection")
    assert line["ok"] is False and line["detail"] == "not connected"
    assert payload["mailing"]["redirectUri"] == "https://apps.example.org/api/setup/mailing/callback"
    assert payload["mailing"]["connection"] is None


@pytest.mark.asyncio
async def test_readiness_says_connected_as_and_carries_no_token(monkeypatch):
    payload = await _readiness(monkeypatch, FakeConnStore(_connection(label="Test Org")))
    line = next(c for c in _mailing_row(payload)["checks"] if c["kind"] == "connection")
    assert line["ok"] is True and line["detail"] == "connected as Test Org"
    conn = payload["mailing"]["connection"]
    assert conn["accountLabel"] == "Test Org"
    assert not any("token" in k.lower() for k in conn)


@pytest.mark.asyncio
async def test_readiness_says_needs_reauthorisation_with_the_reason(monkeypatch):
    conn = _connection(status=mailing_mod.STATUS_NEEDS_REAUTH, error="HTTP 400")
    payload = await _readiness(monkeypatch, FakeConnStore(conn))
    line = next(c for c in _mailing_row(payload)["checks"] if c["kind"] == "connection")
    assert line["ok"] is False and line["detail"] == "needs re-authorisation: HTTP 400"


@pytest.mark.asyncio
async def test_readiness_without_a_store_is_unknown_not_an_error(monkeypatch):
    payload = await _readiness(monkeypatch, None)
    line = next(c for c in _mailing_row(payload)["checks"] if c["kind"] == "connection")
    assert line["ok"] is None and "no database" in line["detail"]


# --- connect ------------------------------------------------------------------------


def test_connect_is_admin_only_and_absent_when_the_page_is_off(monkeypatch):
    _authed(monkeypatch, _STAFF)
    client = TestClient(_app(monkeypatch))
    assert client.get("/api/setup/mailing/connect", follow_redirects=False).status_code == 403
    _authed(monkeypatch, None)
    assert client.get("/api/setup/mailing/connect", follow_redirects=False).status_code == 401
    monkeypatch.setenv("SETUP_ENABLED", "false")
    get_settings.cache_clear()
    _authed(monkeypatch, _ADMIN)
    assert client.get("/api/setup/mailing/connect", follow_redirects=False).status_code == 404


def test_connect_redirects_to_the_vendor_with_the_registered_address_and_a_verifiable_state(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    client = TestClient(_app(monkeypatch))
    resp = client.get("/api/setup/mailing/connect", follow_redirects=False)
    assert resp.status_code == 302
    target = resp.headers["location"]
    assert target.startswith(mailing_mod.AUTHORIZE_URL + "?")
    q = {k: v[0] for k, v in parse_qs(urlsplit(target).query).items()}
    assert q["client_id"] == "api-key"
    assert q["redirect_uri"] == REDIRECT  # trailing slash on APP_BASE_URL stripped
    assert q["response_type"] == "code"
    assert q["scope"].split() == list(mailing_mod.SCOPES)
    mailing_mod.verify_state("s3cret", q["state"], "u1")  # the signed-in admin's


@pytest.mark.parametrize("kw,phrase", [
    ({"client_id": ""}, "client ID"),
    ({"secret": ""}, "client secret"),
    ({"base_url": ""}, "APP_BASE_URL"),
])
def test_connect_explains_what_is_missing_instead_of_guessing(monkeypatch, kw, phrase):
    _authed(monkeypatch, _ADMIN)
    client = TestClient(_app(monkeypatch, **kw))
    resp = client.get("/api/setup/mailing/connect", follow_redirects=False)
    assert resp.status_code == 400
    assert phrase in resp.json()["detail"]


def test_connect_refuses_before_the_trip_when_there_is_no_encryption_key(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    client = TestClient(_app(monkeypatch, store=FakeConnStore(None, cipher=False)))
    resp = client.get("/api/setup/mailing/connect", follow_redirects=False)
    assert resp.status_code == 400 and "APP_ENCRYPTION_KEY" in resp.json()["detail"]


# --- callback -----------------------------------------------------------------------


def _outcome(resp):
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith("/setup/?") and loc.endswith("#readiness")
    return {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}


def test_callback_rejects_a_foreign_or_another_admins_state(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    store = FakeConnStore()
    client = TestClient(_app(monkeypatch, store=store))
    bad = mailing_mod.sign_state("s3cret", "someone-else")
    out = _outcome(client.get(f"/api/setup/mailing/callback?code=c&state={bad}", follow_redirects=False))
    assert out["mailing"] == "failed" and "different administrator" in out["detail"]
    out = _outcome(client.get("/api/setup/mailing/callback?code=c&state=garbage", follow_redirects=False))
    assert out["mailing"] == "failed"
    assert store.saved == []


def test_callback_reports_a_declined_authorisation(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    client = TestClient(_app(monkeypatch))
    out = _outcome(client.get(
        "/api/setup/mailing/callback?error=access_denied&error_description=User+declined",
        follow_redirects=False,
    ))
    assert out["mailing"] == "declined" and out["detail"] == "User declined"


def test_callback_exchanges_the_code_stores_the_connection_and_records_it(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    logged = _logged(monkeypatch)
    store = FakeConnStore()
    client = TestClient(_app(monkeypatch, store=store))
    seen = {}

    async def fake_exchange(cid, sec, code, redirect_uri):
        seen.update(cid=cid, sec=sec, code=code, redirect_uri=redirect_uri)
        return TokenSet("acc-TOKEN-1", "ref-TOKEN-1", _NOW + timedelta(hours=24), "contact_data offline_access")

    class FakeClient:
        def __init__(self, source, *, base_url):
            seen["base_url"] = base_url
        async def account_label(self):
            return "Test Org"

    monkeypatch.setattr(setup_mailing.mailing_mod, "exchange_code", fake_exchange)
    monkeypatch.setattr(setup_mailing.mailing_mod, "MailingClient", FakeClient)
    state = mailing_mod.sign_state("s3cret", "u1")
    out = _outcome(client.get(f"/api/setup/mailing/callback?code=the-code&state={state}", follow_redirects=False))
    assert out == {"mailing": "connected", "detail": "Test Org"}
    assert seen["code"] == "the-code" and seen["redirect_uri"] == REDIRECT
    assert seen["cid"] == "api-key" and seen["sec"] == "sec"
    assert store.saved and store.saved[0]["label"] == "Test Org" and store.saved[0]["by"] == "adm"
    assert logged and logged[0]["action"] == setup_mailing.ACTION_CONNECTED
    assert "TOKEN-1" not in str(logged[0])  # the record names the account, never a token


def test_callback_without_an_account_name_still_connects(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    _logged(monkeypatch)
    store = FakeConnStore()
    client = TestClient(_app(monkeypatch, store=store))

    async def fake_exchange(*a):
        return TokenSet("acc", "ref", _NOW + timedelta(hours=24))

    class Failing:
        def __init__(self, *a, **kw): ...
        async def account_label(self):
            raise MailingError("HTTP 403")

    monkeypatch.setattr(setup_mailing.mailing_mod, "exchange_code", fake_exchange)
    monkeypatch.setattr(setup_mailing.mailing_mod, "MailingClient", Failing)
    state = mailing_mod.sign_state("s3cret", "u1")
    out = _outcome(client.get(f"/api/setup/mailing/callback?code=c&state={state}", follow_redirects=False))
    assert out["mailing"] == "connected"
    assert store.saved[0]["label"] == ""


def test_callback_reports_a_refused_exchange_and_stores_nothing(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    store = FakeConnStore()
    client = TestClient(_app(monkeypatch, store=store))

    async def refused(*a):
        raise mailing_mod.MailingAuthError("The mailing service refused the credentials (HTTP 401).")

    monkeypatch.setattr(setup_mailing.mailing_mod, "exchange_code", refused)
    state = mailing_mod.sign_state("s3cret", "u1")
    out = _outcome(client.get(f"/api/setup/mailing/callback?code=c&state={state}", follow_redirects=False))
    assert out["mailing"] == "failed" and "HTTP 401" in out["detail"]
    assert store.saved == []


def test_callback_is_gated_like_the_page(monkeypatch):
    _authed(monkeypatch, _STAFF)
    client = TestClient(_app(monkeypatch))
    assert client.get("/api/setup/mailing/callback?code=c&state=s", follow_redirects=False).status_code == 403


# --- disconnect ---------------------------------------------------------------------


def test_disconnect_removes_the_row_and_records_it(monkeypatch):
    _authed(monkeypatch, _ADMIN)
    logged = _logged(monkeypatch)
    store = FakeConnStore(_connection())
    client = TestClient(_app(monkeypatch, store=store))
    body = client.post("/api/setup/mailing/disconnect").json()
    assert body == {"ok": True, "removed": True} and store.conn is None
    assert logged[0]["action"] == setup_mailing.ACTION_DISCONNECTED
    body = client.post("/api/setup/mailing/disconnect").json()
    assert body == {"ok": True, "removed": False}
    assert len(logged) == 1  # nothing to record the second time


def test_disconnect_is_admin_only(monkeypatch):
    _authed(monkeypatch, _STAFF)
    client = TestClient(_app(monkeypatch))
    assert client.post("/api/setup/mailing/disconnect").status_code == 403


# --- the page -----------------------------------------------------------------------


def test_the_settings_page_wires_the_connection_controls():
    import pathlib
    js = (pathlib.Path(__file__).resolve().parents[1] / "setup" / "frontend" / "app.js").read_text()
    assert 'href="/api/setup/mailing/connect"' in js
    assert "/api/setup/mailing/disconnect" in js
    assert "data-copy" in js and "mailingRedirect" in js
    assert "announceMailingOutcome" in js
