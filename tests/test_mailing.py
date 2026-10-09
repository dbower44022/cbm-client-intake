"""Phase C piece 1 — the mailing service client and its connection store.

No vendor account is needed: the transport is a scripted fake that ENFORCES
the vendor's limits the way the EspoCRM fake enforces 200 — the per-second
pace, the contacts page size, the import chunk — so a wrong assumption fails a
test rather than a night. The store's Postgres half runs only with
``TEST_DATABASE_URL`` (the convention of ``test_store_pg.py``); the schema and
cipher rules below need no database.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from core import mailing as m
from core.crypto import SecretCipher
from core.mailing import (
    CONTACTS_PAGE,
    IMPORT_MAX,
    MIN_REQUEST_INTERVAL,
    ConnectionStore,
    MailingAuthError,
    MailingClient,
    MailingError,
    MailingNotConnected,
    MailingRateLimited,
    TokenSet,
    authorize_url,
    exchange_code,
    needs_refresh,
    refresh_tokens,
    sign_state,
    verify_state,
)

_VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
_NOW = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)


# --- fake transport ----------------------------------------------------------


class FakeVendorHTTP:
    """Scripts responses, records requests, and refuses what the vendor refuses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def install(self, monkeypatch):
        fake = self

        class FakeAsyncClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kw):
                return await self.request("POST", url, **kw)

            async def request(self, method, url, **kw):
                params = kw.get("params") or {}
                body = kw.get("json")
                fake.requests.append({
                    "method": method, "url": url, "params": params, "json": body,
                    "headers": kw.get("headers") or {},
                })
                # The vendor's limits, enforced here so the code cannot drift past them.
                if "limit" in params and "/contacts" in url and "/contact_lists" not in url:
                    assert int(params["limit"]) <= CONTACTS_PAGE, "contacts page over the vendor max"
                if url.endswith("/activities/contacts_json_import"):
                    assert len(body["import_data"]) <= IMPORT_MAX, "import chunk over 40,000"
                    assert body["list_ids"], "an import must name the list"
                if not fake.responses:
                    raise AssertionError(f"unexpected request {method} {url}")
                status, payload, headers = fake.responses.pop(0)
                return httpx.Response(
                    status_code=status, json=payload, headers=headers or {},
                    request=httpx.Request(method, url),
                )

        monkeypatch.setattr(m.httpx, "AsyncClient", FakeAsyncClient)
        return self


@pytest.fixture(autouse=True)
def _record_sleep(monkeypatch):
    """Sleeps are recorded, never slept."""
    calls: list[float] = []

    async def instant(seconds):
        calls.append(float(seconds))

    monkeypatch.setattr(m, "_sleep", instant)
    return calls


def client(token="tok-1"):
    calls = {"force": 0, "plain": 0}

    async def source(force: bool) -> str:
        calls["force" if force else "plain"] += 1
        return token if not force else token + "-fresh"

    api = MailingClient(source, base_url="https://api.example/v3")
    api._calls = calls  # type: ignore[attr-defined]
    return api


# --- state ---------------------------------------------------------------------


def test_state_round_trips_for_the_same_administrator():
    state = sign_state("secret", "user-1")
    verify_state("secret", state, "user-1")  # no raise


def test_state_rejects_another_administrator_a_tamper_and_a_foreign_secret():
    state = sign_state("secret", "user-1")
    with pytest.raises(MailingError, match="different administrator"):
        verify_state("secret", state, "user-2")
    with pytest.raises(MailingError, match="did not come from this application"):
        verify_state("secret", state[:-2] + "xx", "user-1")
    with pytest.raises(MailingError, match="did not come from this application"):
        verify_state("other-secret", state, "user-1")
    with pytest.raises(MailingError, match="did not come from this application"):
        verify_state("secret", "", "user-1")


def test_state_expires(monkeypatch):
    import itsdangerous.timed as timed

    real = time.time
    monkeypatch.setattr(timed.time, "time", lambda: real() - m.STATE_MAX_AGE_SECONDS - 5)
    state = sign_state("secret", "user-1")
    monkeypatch.setattr(timed.time, "time", real)
    with pytest.raises(MailingError, match="took too long"):
        verify_state("secret", state, "user-1")


def test_state_needs_a_secret():
    with pytest.raises(MailingError, match="session secret"):
        sign_state("", "user-1")


# --- authorise URL ---------------------------------------------------------------


def test_authorize_url_carries_the_four_scopes_the_exact_redirect_and_code_flow():
    redirect = "https://cbm-client-intake-svxs3.ondigitalocean.app/api/setup/mailing/callback"
    url = authorize_url("api-key-1", redirect, "st4te")
    assert url.startswith(m.AUTHORIZE_URL + "?")
    q = dict(httpx.URL(url).params)
    assert q["client_id"] == "api-key-1"
    assert q["redirect_uri"] == redirect
    assert q["response_type"] == "code"
    assert q["state"] == "st4te"
    assert q["scope"].split() == ["contact_data", "campaign_data", "account_read", "offline_access"]


def test_authorize_url_refuses_without_a_client_id():
    with pytest.raises(MailingError, match="client ID"):
        authorize_url("", "https://x/cb", "s")


# --- token endpoint ---------------------------------------------------------------


TOKENS_OK = (200, {
    "access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 86400,
    "token_type": "Bearer", "scope": "contact_data account_read offline_access",
}, None)


async def test_exchange_code_uses_basic_auth_and_the_authorization_code_grant(monkeypatch):
    fake = FakeVendorHTTP([TOKENS_OK]).install(monkeypatch)
    tokens = await exchange_code("cid", "sec", "the-code", "https://x/cb")
    req = fake.requests[0]
    assert req["url"] == m.TOKEN_URL
    assert req["headers"]["Authorization"] == "Basic " + __import__("base64").b64encode(b"cid:sec").decode()
    assert req["params"] == {
        "grant_type": "authorization_code", "code": "the-code", "redirect_uri": "https://x/cb",
    }
    assert tokens.access_token == "acc-1" and tokens.refresh_token == "ref-1"
    assert timedelta(hours=23) < tokens.expires_at - datetime.now(timezone.utc) <= timedelta(hours=24)
    assert "offline_access" in tokens.scope


async def test_refresh_uses_the_refresh_token_grant(monkeypatch):
    fake = FakeVendorHTTP([TOKENS_OK]).install(monkeypatch)
    await refresh_tokens("cid", "sec", "old-ref")
    assert fake.requests[0]["params"] == {"grant_type": "refresh_token", "refresh_token": "old-ref"}


@pytest.mark.parametrize("status", [400, 401])
async def test_a_refused_grant_is_terminal_and_never_echoes_the_body(monkeypatch, status):
    FakeVendorHTTP([(status, {"error": "invalid_grant", "client_id": "cid"}, None)]).install(monkeypatch)
    with pytest.raises(MailingAuthError) as exc:
        await refresh_tokens("cid", "sec", "old-ref")
    assert "cid" not in str(exc.value)
    assert str(status) in str(exc.value)


async def test_no_refresh_token_in_the_response_is_an_auth_error(monkeypatch):
    FakeVendorHTTP([(200, {"access_token": "acc", "expires_in": 60}, None)]).install(monkeypatch)
    with pytest.raises(MailingAuthError, match="offline_access"):
        await exchange_code("cid", "sec", "c", "https://x/cb")


async def test_missing_credentials_refuse_before_any_request(monkeypatch):
    fake = FakeVendorHTTP([]).install(monkeypatch)
    with pytest.raises(MailingAuthError):
        await refresh_tokens("", "sec", "r")
    assert fake.requests == []


def test_needs_refresh_only_inside_the_window():
    assert needs_refresh(None)
    assert needs_refresh(_NOW + timedelta(seconds=299), _NOW)
    assert needs_refresh(_NOW - timedelta(seconds=1), _NOW)
    assert not needs_refresh(_NOW + timedelta(seconds=301), _NOW)
    # A naive stamp is read as UTC rather than crashing the comparison.
    assert not needs_refresh(_NOW.replace(tzinfo=None) + timedelta(hours=1), _NOW)


# --- the client: transport rules ----------------------------------------------------


async def test_requests_carry_the_bearer_token_and_are_paced(monkeypatch, _record_sleep):
    fake = FakeVendorHTTP([(200, {"organization_name": "CBM TEST"}, None)] * 3).install(monkeypatch)
    api = client()
    await api.account_summary()
    await api.account_summary()
    await api.account_summary()
    assert all(r["headers"]["Authorization"] == "Bearer tok-1" for r in fake.requests)
    # Three back-to-back requests → two pacing sleeps, each under the interval.
    assert len(_record_sleep) == 2
    assert all(0 < s <= MIN_REQUEST_INTERVAL for s in _record_sleep)


async def test_a_401_forces_one_refresh_and_retries_with_the_new_token(monkeypatch):
    fake = FakeVendorHTTP([
        (401, {"error_key": "unauthorized"}, None),
        (200, {"organization_name": "CBM TEST"}, None),
    ]).install(monkeypatch)
    api = client()
    assert (await api.account_label()) == "CBM TEST"
    assert api._calls["force"] == 1
    assert fake.requests[1]["headers"]["Authorization"] == "Bearer tok-1-fresh"


async def test_a_second_401_gives_up(monkeypatch):
    FakeVendorHTTP([(401, {}, None), (401, {}, None)]).install(monkeypatch)
    with pytest.raises(MailingError, match="HTTP 401"):
        await client().account_summary()


async def test_a_429_waits_retry_after_once_then_reports_partial(monkeypatch, _record_sleep):
    FakeVendorHTTP([
        (429, {"error_key": "throttled"}, {"Retry-After": "3"}),
        (429, {"error_key": "throttled"}, None),
    ]).install(monkeypatch)
    with pytest.raises(MailingRateLimited):
        await client().account_summary()
    assert 3.0 in _record_sleep


async def test_a_5xx_is_retried_with_backoff(monkeypatch, _record_sleep):
    FakeVendorHTTP([(503, {}, None), (200, {"organization_name": "ok"}, None)]).install(monkeypatch)
    assert (await client().account_label()) == "ok"
    assert 1.0 in _record_sleep  # 2 ** 0


async def test_transport_failure_is_a_mailing_error(monkeypatch):
    class Boom:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def request(self, *a, **kw): raise httpx.ConnectError("down")

    monkeypatch.setattr(m.httpx, "AsyncClient", Boom)
    with pytest.raises(MailingError, match="could not reach"):
        await client().account_summary()


# --- the client: the calls Phase C makes ---------------------------------------------


async def test_contacts_follow_the_next_link_and_send_the_filters(monkeypatch):
    fake = FakeVendorHTTP([
        (200, {
            "contacts": [{"contact_id": "a", "email_address": {"address": "A@x.org"}}],
            "_links": {"next": {"href": "/v3/contacts?cursor=abc"}},
        }, None),
        (200, {"contacts": [{"contact_id": "b"}]}, None),
    ]).install(monkeypatch)
    api = client()
    since = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)
    got = [c async for c in api.contacts(status="unsubscribed", updated_after=since, include=("list_memberships",))]
    assert [c["contact_id"] for c in got] == ["a", "b"]
    first = fake.requests[0]
    assert first["params"] == {
        "limit": CONTACTS_PAGE, "status": "unsubscribed",
        "updated_after": "2026-10-08T04:00:00Z", "include": "list_memberships",
    }
    # The next link is a /v3/ path: appended to the base without doubling the version.
    assert fake.requests[1]["url"] == "https://api.example/v3/contacts?cursor=abc"
    assert fake.requests[1]["params"] is None or fake.requests[1]["params"] == {}


async def test_list_members_filter_by_list(monkeypatch):
    fake = FakeVendorHTTP([(200, {"contacts": []}, None)]).install(monkeypatch)
    assert [c async for c in client().contacts(list_id="L1")] == []
    assert fake.requests[0]["params"]["lists"] == "L1"


async def test_find_list_matches_the_name_ignoring_case_and_create_posts_the_name(monkeypatch):
    fake = FakeVendorHTTP([
        (200, {"lists": [{"list_id": "L1", "name": "Event Notices"}, {"list_id": "L2", "name": "Other"}]}, None),
        (200, {"lists": []}, None),
        (201, {"list_id": "L9", "name": "Event notices"}, None),
    ]).install(monkeypatch)
    api = client()
    assert (await api.find_list("event notices"))["list_id"] == "L1"
    assert await api.find_list("event notices") is None
    created = await api.create_list("Event notices")
    assert created["list_id"] == "L9"
    assert fake.requests[2]["json"] == {"name": "Event notices", "favorite": False}


async def test_import_chunks_at_the_vendor_maximum(monkeypatch):
    monkeypatch.setattr(m, "IMPORT_MAX", 2)
    fake = FakeVendorHTTP([
        (201, {"activity_id": "act-1"}, None),
        (201, {"activity_id": "act-2"}, None),
    ]).install(monkeypatch)
    rows = [{"email": f"p{i}@x.org", "first_name": "P", "last_name": str(i)} for i in range(3)]
    ids = await client().import_contacts(rows, list_id="L1")
    assert ids == ["act-1", "act-2"]
    assert [len(r["json"]["import_data"]) for r in fake.requests] == [2, 1]
    assert all(r["json"]["list_ids"] == ["L1"] for r in fake.requests)


async def test_remove_from_list_sends_ids_and_skips_an_empty_set(monkeypatch):
    fake = FakeVendorHTTP([(201, {"activity_id": "act-r"}, None)]).install(monkeypatch)
    api = client()
    assert await api.remove_from_list([], list_id="L1") is None
    assert await api.remove_from_list(["c1", "c2"], list_id="L1") == "act-r"
    assert fake.requests[0]["json"] == {"source": {"contact_ids": ["c1", "c2"]}, "list_ids": ["L1"]}


async def test_wait_for_activity_polls_until_a_terminal_state(monkeypatch, _record_sleep):
    FakeVendorHTTP([
        (200, {"state": "processing"}, None),
        (200, {"state": "completed", "status": {"items_total_count": 3}}, None),
    ]).install(monkeypatch)
    last = await client().wait_for_activity("act-1", attempts=5, interval=2.0)
    assert last["state"] == "completed"
    assert 2.0 in _record_sleep


# --- the connection store: rules that need no database ---------------------------------


class _RecordingOp:
    def __init__(self):
        self.tables: dict[str, list[str]] = {}

    def create_table(self, name, *columns, **kw):
        self.tables[name] = [c.name for c in columns if isinstance(c, sa.Column)]

    def drop_table(self, *a, **k): ...


def _migration_tables(glob: str) -> dict[str, list[str]]:
    rec = _RecordingOp()
    for path in sorted(_VERSIONS.glob(glob)):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        mod.op = rec
        mod.upgrade()
    return rec.tables


def test_migration_0030_and_the_table_object_declare_the_same_columns():
    created = _migration_tables("0030_*.py")
    assert set(created["mailing_connection"]) == set(m.mailing_connection.c.keys())


def test_mailing_connection_is_kept_by_the_sandbox_reset():
    from core import sandbox_reset
    assert "mailing_connection" in sandbox_reset.KEEP_TABLES
    assert "mailing_connection" not in set(sandbox_reset.RESET_TABLES)


def test_the_save_upsert_compiles_for_postgres():
    store = ConnectionStore.__new__(ConnectionStore)
    store._cipher = SecretCipher(SecretCipher.generate_key())
    stmt = (
        sa.dialects.postgresql.insert(m.mailing_connection)
        .values(
            id=m.ROW_ID, status=m.STATUS_CONNECTED, access_token=store._encrypt("a"),
            refresh_token=store._encrypt("r"), expires_at=_NOW, scopes="x",
            account_label="L", connected_by="u", connected_at=_NOW,
            last_refresh_at=None, last_error=None,
        )
    )
    assert "mailing_connection" in str(stmt.compile(dialect=postgresql.dialect()))


def test_tokens_are_refused_without_a_cipher():
    store = ConnectionStore.__new__(ConnectionStore)
    store._cipher = None
    with pytest.raises(MailingError, match="encryption key"):
        store._encrypt("secret-token")
    with pytest.raises(MailingError, match="encryption key"):
        store._decrypt("whatever")


def test_a_token_written_under_one_key_is_unreadable_under_another():
    a = ConnectionStore.__new__(ConnectionStore)
    a._cipher = SecretCipher(SecretCipher.generate_key())
    b = ConnectionStore.__new__(ConnectionStore)
    b._cipher = SecretCipher(SecretCipher.generate_key())
    blob = a._encrypt("acc-1")
    assert a._decrypt(blob) == "acc-1"
    with pytest.raises(MailingAuthError, match="unreadable"):
        b._decrypt(blob)


def test_connection_as_dict_never_carries_a_token():
    conn = m.Connection(
        status=m.STATUS_CONNECTED, account_label="CBM TEST", connected_by="doug",
        connected_at=_NOW, expires_at=_NOW, last_refresh_at=None, last_error=None,
        scopes=("contact_data",), list_id=None, pull_cursor=None, last_push_at=None,
        last_push_summary=None,
    )
    d = conn.as_dict()
    assert d["status"] == "connected" and d["accountLabel"] == "CBM TEST"
    assert not any("token" in k.lower() for k in d)
    assert conn.usable


# --- the connection store: Postgres ---------------------------------------------------

_URL = os.environ.get("TEST_DATABASE_URL")
_pg = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


def _tokens(ttl_seconds: int) -> TokenSet:
    return TokenSet("acc-" + uuid.uuid4().hex[:6], "ref-" + uuid.uuid4().hex[:6],
                    datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds), "contact_data")


@_pg
async def test_save_get_and_a_fresh_token_is_returned_without_refreshing():
    store = ConnectionStore(_URL, SecretCipher(SecretCipher.generate_key()))
    await store.create_all()
    await store.delete()
    tokens = _tokens(86400)
    await store.save(tokens, account_label="CBM TEST", connected_by="doug")
    conn = await store.get()
    assert conn and conn.usable and conn.account_label == "CBM TEST"

    async def never(*a):
        raise AssertionError("must not refresh a fresh token")

    assert await store.access_token("cid", "sec", refresher=never) == tokens.access_token
    await store.delete()
    await store.dispose()


@_pg
async def test_a_near_expiry_token_is_refreshed_under_the_lock_and_the_new_pair_stored():
    store = ConnectionStore(_URL, SecretCipher(SecretCipher.generate_key()))
    await store.create_all()
    await store.delete()
    old = _tokens(60)
    await store.save(old, account_label="x", connected_by="y")
    seen = {}

    async def refresher(cid, sec, refresh_token):
        seen["refresh_token"] = refresh_token
        return _tokens(86400)

    new_access = await store.access_token("cid", "sec", refresher=refresher)
    assert seen["refresh_token"] == old.refresh_token
    assert new_access != old.access_token

    async def never(*a):
        raise AssertionError("already refreshed")

    assert await store.access_token("cid", "sec", refresher=never) == new_access
    conn = await store.get()
    assert conn.last_refresh_at is not None
    await store.delete()
    await store.dispose()


@_pg
async def test_a_refused_refresh_marks_the_row_and_blocks_further_use():
    store = ConnectionStore(_URL, SecretCipher(SecretCipher.generate_key()))
    await store.create_all()
    await store.delete()
    await store.save(_tokens(10), account_label="x", connected_by="y")

    async def refused(*a):
        raise MailingAuthError("HTTP 400")

    with pytest.raises(MailingAuthError):
        await store.access_token("cid", "sec", refresher=refused)
    conn = await store.get()
    assert conn.status == m.STATUS_NEEDS_REAUTH and "400" in conn.last_error
    with pytest.raises(MailingNotConnected, match="re-authorisation"):
        await store.access_token("cid", "sec", refresher=refused)
    # Reconnecting clears the mark.
    await store.save(_tokens(86400), account_label="x", connected_by="y")
    assert (await store.get()).usable
    await store.delete()
    await store.dispose()


@_pg
async def test_no_row_is_not_connected_and_caches_round_trip():
    store = ConnectionStore(_URL, SecretCipher(SecretCipher.generate_key()))
    await store.create_all()
    await store.delete()
    with pytest.raises(MailingNotConnected):
        await store.access_token("cid", "sec")
    await store.save(_tokens(86400), account_label="x", connected_by="y")
    await store.set_list_id("L1")
    await store.set_pull_cursor(_NOW)
    await store.record_push({"added": 3, "removed": 1})
    conn = await store.get()
    assert conn.list_id == "L1" and conn.pull_cursor == _NOW
    assert conn.last_push_summary == {"added": 3, "removed": 1} and conn.last_push_at
    assert await store.delete() is True
    assert await store.get() is None
    await store.dispose()
