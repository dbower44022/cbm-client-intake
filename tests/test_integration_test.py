"""The integration test, phase 2 of the Integrations tab
(prds/integrations-tab-plan.md § 3 part 2; checks approved by Doug 11-13-26).

Each check's ok, failed and unknown paths with fake clients; no secret in any
result; the endpoints are admin-only and dark with the switch off; the status
line reads the last run.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, get_settings
from core.espo import EspoError, EspoTransportError
from core.zoom import ZoomAuthError, ZoomError, ZoomTransportError
from forms import info_request
from integrations import testing
from integrations.checks import espocrm, google, zoom
from integrations.registry import BY_KEY as INTEGRATIONS
from integrations.testing import (
    FAILED, OK, SKIPPED, UNKNOWN, Blocked, Check, Context, Skip, run_checks,
)

SECRET = "sk-very-secret-value-123"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def by_key(result):
    return {c["key"]: c for c in result["checks"]}


def facts(result):
    return {f["label"]: f["value"] for f in result["facts"]}


def no_secret(result, *secrets):
    text = json.dumps(result)
    for s in secrets:
        assert s not in text, f"secret leaked: {s[:6]}…"


# --- the framework -------------------------------------------------------------

def test_each_outcome_and_the_overall_result():
    async def ok(_):
        return OK, "fine"

    async def bad(_):
        return FAILED, "no"

    async def boom(_):
        raise RuntimeError("kaput")

    async def skip(_):
        raise Skip()

    async def blocked(_):
        raise Blocked("Not checked: needs the first.")

    async def slow(_):
        await asyncio.sleep(5)
        return OK, ""

    checks = [Check("a", "A", ok), Check("b", "B", bad), Check("c", "C", boom),
              Check("d", "D", skip), Check("e", "E", blocked),
              Check("f", "F", slow, timeout=0.05)]
    result = run(run_checks("x", checks, Context(settings=Settings())))
    got = {k: (v["outcome"], v["detail"]) for k, v in by_key(result).items()}
    assert got["a"] == (OK, "fine")
    assert got["b"] == (FAILED, "no")
    assert got["c"][0] == UNKNOWN and "kaput" in got["c"][1]
    assert got["d"][0] == SKIPPED and "switched off" in got["d"][1]
    assert got["e"] == (UNKNOWN, "Not checked: needs the first.")
    assert got["f"][0] == UNKNOWN and "did not finish" in got["f"][1]
    assert result["outcome"] == FAILED


def test_overall_unknown_beats_ok_and_skipped_never_counts():
    assert testing.overall([{"outcome": OK}, {"outcome": UNKNOWN}]) == UNKNOWN
    assert testing.overall([{"outcome": OK}, {"outcome": SKIPPED}]) == OK
    assert testing.overall([{"outcome": SKIPPED}]) == UNKNOWN


def test_the_whole_test_has_a_limit():
    async def slow(_):
        await asyncio.sleep(0.2)
        return OK, ""

    checks = [Check("a", "A", slow), Check("b", "B", slow)]
    result = run(run_checks("x", checks, Context(settings=Settings()), limit=0.1))
    assert [c["outcome"] for c in result["checks"]] == [UNKNOWN, UNKNOWN]
    assert "limit" in result["checks"][1]["detail"]


def test_a_secret_setting_is_scrubbed_from_details_and_facts():
    s = Settings(zoom_client_secret=SECRET)

    async def leaky(ctx):
        ctx.fact("Echo", f"token {SECRET} back")
        return FAILED, f"Vendor said: bad secret {SECRET}"

    result = run(run_checks("x", [Check("a", "A", leaky)], Context(settings=s)))
    no_secret(result, SECRET)
    assert "(secret)" in result["checks"][0]["detail"]
    assert facts(result)["Echo"] == "token (secret) back"


def test_one_test_at_a_time(monkeypatch):
    integ = INTEGRATIONS["zoom"]
    started = asyncio.Event()

    async def slow_run(settings, deps=None):
        started.set()
        await asyncio.sleep(0.1)
        return {"ok": True}

    monkeypatch.setattr(zoom, "run", slow_run)

    async def both():
        first = asyncio.create_task(testing.run_integration_test(integ, Settings()))
        await started.wait()
        with pytest.raises(testing.AlreadyRunning):
            await testing.run_integration_test(integ, Settings())
        return await first

    assert run(both()) == {"ok": True}


def test_every_integration_is_testable_since_phase_3():
    assert {k for k, i in INTEGRATIONS.items() if i.testable} == set(INTEGRATIONS)


# --- EspoCRM ----------------------------------------------------------------------

def espo_settings(**kw):
    base = dict(espo_dry_run=False, espo_base_url="https://crm.example.org",
                espo_api_key=SECRET)
    base.update(kw)
    return Settings(**base)


class FakeEspo:
    def __init__(self, *, app_user=None, error=None, denied=(), absent=(), down=()):
        self.app_user_payload = app_user or {
            "user": {"id": "u9", "userName": "api", "type": "api"},
            "settings": {"version": "9.3.10"},
        }
        self.error = error
        self.denied, self.absent, self.down = set(denied), set(absent), set(down)
        self.listed = []

    async def app_user(self):
        if self.error:
            raise self.error
        return self.app_user_payload

    async def get(self, entity, record_id, select=None):
        return {"rolesNames": {"r1": "CustomAppAPIRole"}}

    async def list(self, entity, **kw):
        self.listed.append(entity)
        if entity in self.down:
            raise EspoTransportError("timeout")
        if entity in self.denied:
            raise EspoError(f"list {entity} failed: HTTP 403")
        if entity in self.absent:
            raise EspoError(f"list {entity} failed: HTTP 404")
        return {"total": 1, "list": [{"id": "x"}]}


def conformance(checks=None):
    rows = checks if checks is not None else [
        {"category": "entity", "target": "CEngagement", "outcome": "conformant"},
        {"category": "team", "target": "Team", "outcome": "conformant"},
        {"category": "enum", "target": "CEngagement.engagementStatus", "outcome": "conformant"},
    ]

    async def fn(url, key):
        return 0, {"checks": rows}
    return fn


class FakeAdmin:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"user": {"userName": "crm.config", "type": "admin"}}
        self.error = error

    async def app_user(self):
        if self.error:
            raise self.error
        return self.payload


def espo_deps(client=None, conf=None, admin=None):
    client = client or FakeEspo()
    admin_client = admin

    def admin_factory(settings):
        if admin_client is None:
            return None

        async def make():
            return admin_client
        return make

    return espocrm.Deps(client=lambda s: client, conformance=conf or conformance(),
                        admin=admin_factory)


def test_espocrm_passes_and_reports_its_facts():
    result = run(espocrm.run(espo_settings(), espo_deps()))
    checks = by_key(result)
    assert [c for c in checks] == ["sign_in", "conformance", "read_access", "enums",
                                   "provisioning"]
    assert result["outcome"] == OK
    assert checks["provisioning"]["outcome"] == SKIPPED
    f = facts(result)
    assert f["EspoCRM version"] == "9.3.10"
    assert f["API user"] == "api"
    assert f["API user's roles"] == "CustomAppAPIRole"
    assert f["Entities found"] == "1 of 1 required"
    no_secret(result, SECRET)


def test_espocrm_dry_run_is_unknown_and_runs_nothing_else():
    result = run(espocrm.run(espo_settings(espo_dry_run=True), espo_deps()))
    assert [(c["key"], c["outcome"]) for c in result["checks"]] == [("mode", UNKNOWN)]


def test_espocrm_missing_key_is_failed():
    result = run(espocrm.run(espo_settings(espo_api_key=""), espo_deps()))
    assert result["checks"][0]["outcome"] == FAILED
    assert "API key is not set" in result["checks"][0]["detail"]


@pytest.mark.parametrize("error,outcome", [
    (EspoError("App/user failed: HTTP 401"), FAILED),
    (EspoError("App/user failed: HTTP 404"), FAILED),
    (EspoTransportError("connect failed"), UNKNOWN),
])
def test_espocrm_sign_in_paths_and_later_checks_say_why(error, outcome):
    result = run(espocrm.run(espo_settings(), espo_deps(FakeEspo(error=error))))
    checks = by_key(result)
    assert checks["sign_in"]["outcome"] == outcome
    for key in ("conformance", "read_access", "enums"):
        assert checks[key]["outcome"] == UNKNOWN
        assert "could not sign in" in checks[key]["detail"]


def test_espocrm_conformance_missing_is_failed_and_forbidden_is_unknown():
    absent = conformance([{"category": "entity", "target": "CEngagement",
                           "outcome": "absent", "missing": ["engagementStatus"]}])
    result = run(espocrm.run(espo_settings(), espo_deps(conf=absent)))
    c = by_key(result)["conformance"]
    assert c["outcome"] == FAILED and "CEngagement (engagementStatus)" in c["detail"]

    forbidden = conformance([{"category": "entity", "target": "CEvent", "outcome": "forbidden"}])
    result = run(espocrm.run(espo_settings(), espo_deps(conf=forbidden)))
    assert by_key(result)["conformance"]["outcome"] == UNKNOWN


def test_espocrm_read_access_paths():
    result = run(espocrm.run(espo_settings(), espo_deps(FakeEspo(denied={"CSession"}))))
    c = by_key(result)["read_access"]
    assert c["outcome"] == FAILED and "may not read CSession" in c["detail"]
    result = run(espocrm.run(espo_settings(), espo_deps(FakeEspo(down={"CSession"}))))
    assert by_key(result)["read_access"]["outcome"] == UNKNOWN


def test_espocrm_reads_a_feature_entity_only_when_its_feature_is_on():
    client = FakeEspo()
    run(espocrm.run(espo_settings(), espo_deps(client)))
    assert "CEvent" not in client.listed
    client = FakeEspo()
    run(espocrm.run(espo_settings(events_enabled=True), espo_deps(client)))
    assert "CEvent" in client.listed and "CEventRegistration" in client.listed


def test_espocrm_enum_paths():
    missing = conformance([{"category": "enum", "target": "Contact.cContactType",
                            "outcome": "advisory", "missing": ["Prospect"]}])
    result = run(espocrm.run(espo_settings(), espo_deps(conf=missing)))
    assert by_key(result)["enums"]["outcome"] == FAILED
    unread = conformance([{"category": "enum", "target": "Contact.cContactType",
                           "outcome": "unreachable"}])
    result = run(espocrm.run(espo_settings(), espo_deps(conf=unread)))
    assert by_key(result)["enums"]["outcome"] == UNKNOWN


def test_espocrm_provisioning_paths():
    creds = dict(espo_provision_username="crm.config", espo_provision_password="pw-1234567")
    ok = run(espocrm.run(espo_settings(**creds), espo_deps(admin=FakeAdmin())))
    assert by_key(ok)["provisioning"]["outcome"] == OK
    regular = FakeAdmin({"user": {"userName": "crm.config", "type": "regular"}})
    bad = run(espocrm.run(espo_settings(**creds), espo_deps(admin=regular)))
    assert by_key(bad)["provisioning"]["outcome"] == FAILED
    down = FakeAdmin(error=EspoTransportError("no route"))
    unknown = run(espocrm.run(espo_settings(**creds), espo_deps(admin=down)))
    assert by_key(unknown)["provisioning"]["outcome"] == UNKNOWN
    required = run(espocrm.run(espo_settings(mentor_provision_users=True), espo_deps()))
    assert by_key(required)["provisioning"]["outcome"] == FAILED
    no_secret(ok, "pw-1234567")


# --- Google Workspace ---------------------------------------------------------------

PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nMIIEsecretsecret\n-----END PRIVATE KEY-----\n"
KEY = json.dumps({
    "type": "service_account", "client_email": "app@proj.iam.gserviceaccount.com",
    "client_id": "1234567890", "private_key": PRIVATE_KEY, "private_key_id": "kid-abcdef123",
    "token_uri": "https://oauth2.googleapis.com/token",
})


class Unauthorized(Exception):
    pass


def google_settings(**kw):
    base = dict(google_service_account_json=KEY, google_delegated_admin="admin@cbm.org",
                database_url="")
    base.update(kw)
    return Settings(**base)


def google_deps(*, refuse=(), mint_error=None, responses=None, stored=None):
    """``refuse``: scope names whose delegated token is unauthorized."""
    minted = []

    def mint(info, scopes, subject):
        minted.append((scopes[0].rsplit("/", 1)[-1], subject))
        if mint_error is not None:
            raise mint_error
        if subject and scopes[0].rsplit("/", 1)[-1] in refuse:
            raise Unauthorized("unauthorized_client: Client is unauthorized ... {'error': 'x'}")
        return "tok"

    calls = []

    async def get(url, token, params=None):
        calls.append(url)
        for fragment, answer in (responses or {}).items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        if "/drives/" in url:
            return 200, {"id": "d1", "name": "CBM Documents"}
        if "/profile" in url:
            return 200, {"emailAddress": "info@cbm.org", "messagesTotal": 42}
        if "/groups/" in url:
            return 200, {"email": "members@cbm.org"}
        if "/users/" in url:
            return 200, {"primaryEmail": "admin@cbm.org", "isAdmin": True}
        return 200, {"items": []}

    async def stored_config(settings):
        return stored

    deps = google.Deps(mint=mint, get=get, stored_config=stored_config)
    deps.minted, deps.calls = minted, calls
    return deps


ALL_ON = dict(gdrive_docs=True, gdrive_shared_drive_id="d1", gcal_events=True,
              meet_transcripts=True, gmail_sync=True, ops_mailbox="info@cbm.org",
              google_directory_check=True, mentor_provision_users=True,
              google_members_group="members@cbm.org")


def test_google_everything_on_passes_and_reports_facts():
    result = run(google.run(google_settings(**ALL_ON), google_deps()))
    assert result["outcome"] == OK, result["checks"]
    f = facts(result)
    assert f["Service account"] == "app@proj.iam.gserviceaccount.com"
    assert f["Client ID (for the delegation grant)"] == "1234567890"
    assert f["Shared drive"] == "CBM Documents"
    assert f["Shared mailbox"] == "info@cbm.org (42 messages)"
    assert "gmail.send" in f["Scopes granted"] and f["Scopes missing"] == "none"
    no_secret(result, PRIVATE_KEY, "MIIEsecretsecret", "kid-abcdef123", KEY)


def test_google_checks_only_what_is_switched_on():
    deps = google_deps()
    result = run(google.run(google_settings(), deps))
    checks = by_key(result)
    assert checks["key"]["outcome"] == OK
    assert not [k for k in checks if k.startswith("scope:")]
    for key in ("drive", "mailbox", "calendar", "meet", "directory"):
        assert checks[key]["outcome"] == SKIPPED
    assert deps.calls == []


def test_google_a_scope_not_granted_is_failed_and_named():
    result = run(google.run(google_settings(gcal_events=True),
                            google_deps(refuse={"calendar.events"})))
    checks = by_key(result)
    scope = checks["scope:calendar.events:admin@cbm.org"]
    assert scope["outcome"] == FAILED and "does not grant calendar.events" in scope["detail"]
    assert checks["calendar"]["outcome"] == UNKNOWN
    assert facts(result)["Scopes missing"] == "calendar.events"


def test_google_key_paths():
    revoked = Exception("invalid_grant: Invalid JWT Signature. {'error': 'invalid_grant'}")
    result = run(google.run(google_settings(gcal_events=True), google_deps(mint_error=revoked)))
    checks = by_key(result)
    assert checks["key"]["outcome"] == FAILED and "Invalid JWT Signature" in checks["key"]["detail"]
    assert checks["scope:calendar.events:admin@cbm.org"]["outcome"] == UNKNOWN

    class TransportError(Exception):
        pass

    down = run(google.run(google_settings(), google_deps(mint_error=TransportError("dns"))))
    assert by_key(down)["key"]["outcome"] == UNKNOWN

    unset = run(google.run(google_settings(google_service_account_json=""), google_deps()))
    assert by_key(unset)["key"]["outcome"] == FAILED

    bad = run(google.run(google_settings(google_service_account_json="{not json"), google_deps()))
    assert "not valid JSON" in by_key(bad)["key"]["detail"]


def test_google_uses_the_stored_email_setup_key_first():
    stored = {"service_account_json": KEY.replace("1234567890", "999"),
              "delegated_admin": "boss@cbm.org"}
    result = run(google.run(google_settings(google_service_account_json=""),
                            google_deps(stored=stored)))
    assert facts(result)["Client ID (for the delegation grant)"] == "999"
    assert facts(result)["Delegated admin"] == "boss@cbm.org"


def test_google_drive_paths():
    s = google_settings(gdrive_docs=True, gdrive_shared_drive_id="d1")
    missing = run(google.run(s, google_deps(responses={"/drives/": (404, {})})))
    assert by_key(missing)["drive"]["outcome"] == FAILED
    down = run(google.run(s, google_deps(responses={"/drives/": (503, {})})))
    assert by_key(down)["drive"]["outcome"] == UNKNOWN
    import httpx

    unreachable = run(google.run(s, google_deps(responses={"/drives/": httpx.ConnectError("x")})))
    assert by_key(unreachable)["drive"]["outcome"] == UNKNOWN
    no_id = run(google.run(google_settings(gdrive_docs=True), google_deps()))
    assert by_key(no_id)["drive"]["outcome"] == FAILED


def test_google_service_mode_drive_needs_no_delegation():
    deps = google_deps()
    run(google.run(google_settings(gdrive_docs=True, gdrive_shared_drive_id="d1",
                                   gdrive_identity="service"), deps))
    assert ("drive", None) in deps.minted
    assert ("drive", "admin@cbm.org") not in deps.minted


def test_google_the_shared_mailbox_is_impersonated_itself():
    deps = google_deps()
    run(google.run(google_settings(ops_mailbox="info@cbm.org"), deps))
    assert ("gmail.send", "info@cbm.org") in deps.minted
    assert ("gmail.readonly", "info@cbm.org") in deps.minted


def test_google_directory_paths():
    s = google_settings(google_directory_check=True)
    not_admin = run(google.run(s, google_deps(responses={"/users/": (200, {"isAdmin": False})})))
    assert by_key(not_admin)["directory"]["outcome"] == FAILED
    prov = google_settings(mentor_provision_users=True, google_members_group="members@cbm.org")
    no_group = run(google.run(prov, google_deps(responses={"/groups/": (404, {})})))
    assert by_key(no_group)["directory"]["outcome"] == FAILED


# --- Zoom ----------------------------------------------------------------------------

def zoom_settings(**kw):
    base = dict(zoom_account_id="acc1", zoom_client_id="cid1",
                zoom_client_secret=SECRET, zoom_host_email="zweb@cbm.org")
    base.update(kw)
    return Settings(**base)


class FakeZoom:
    def __init__(self, *, token_error=None, user_error=None, webinar=True, past=True,
                 report_error=None):
        self.token_error, self.user_error = token_error, user_error
        self.webinar, self.past, self.report_error = webinar, past, report_error
        self.scopes = ""

    async def _access_token(self, force=False):
        if self.token_error:
            raise self.token_error
        self.scopes = "user:read:user:admin webinar:read:list_webinars:admin"
        return "tok"

    async def get_user(self, user):
        if self.user_error:
            raise self.user_error
        return {"email": user, "type": 2, "account_number": 8675309}

    async def get_user_settings(self, user):
        return {"feature": {"webinar": self.webinar,
                            "webinar_capacity": 500 if self.webinar else None}}

    async def list_webinars(self, user, *, kind="scheduled", page_size=1):
        if kind == "past":
            return {"webinars": [{"id": 77, "topic": "AI for Small Business"}] if self.past else []}
        return {"total_records": 3, "webinars": [{"id": 1}]}

    async def list_participants(self, webinar_id):
        if self.report_error:
            raise self.report_error
        return [{"user_email": "a@b.c"}, {"user_email": "d@e.f"}]


def zoom_deps(client):
    return zoom.Deps(client=lambda s: client)


def test_zoom_passes_and_reports_its_facts():
    result = run(zoom.run(zoom_settings(zoom_events=True), zoom_deps(FakeZoom())))
    assert result["outcome"] == OK, result["checks"]
    f = facts(result)
    assert f["Host"] == "zweb@cbm.org (Licensed)"
    assert f["Account number"] == "8675309"
    assert f["Webinar capacity"] == "500"
    assert f["Scheduled webinars"] == "3"
    assert "webinar:read:list_webinars:admin" in f["Scopes on the token"]
    assert "2 participant(s)" in by_key(result)["attendance"]["detail"]
    no_secret(result, SECRET)


def test_zoom_missing_settings_is_failed_and_nothing_else_runs():
    result = run(zoom.run(zoom_settings(zoom_client_secret=""), zoom_deps(FakeZoom())))
    checks = by_key(result)
    assert checks["settings"]["outcome"] == FAILED
    assert "client secret" in checks["settings"]["detail"]
    assert all(c["outcome"] == UNKNOWN for k, c in checks.items() if k != "settings")


@pytest.mark.parametrize("error,outcome", [
    (ZoomAuthError("Zoom rejected the app credentials (HTTP 401).", status_code=401), FAILED),
    (ZoomTransportError("Zoom token request failed: ConnectError"), UNKNOWN),
    (ZoomError("Zoom token request failed: HTTP 503", status_code=503), UNKNOWN),
])
def test_zoom_token_paths(error, outcome):
    result = run(zoom.run(zoom_settings(), zoom_deps(FakeZoom(token_error=error))))
    assert by_key(result)["token"]["outcome"] == outcome
    assert by_key(result)["host"]["outcome"] == UNKNOWN


def test_zoom_host_paths():
    gone = ZoomError("Zoom GET /users/x failed: HTTP 404 User does not exist", status_code=404)
    result = run(zoom.run(zoom_settings(), zoom_deps(FakeZoom(user_error=gone))))
    assert by_key(result)["host"]["outcome"] == FAILED
    assert "Check the host's address" in by_key(result)["host"]["detail"]
    scope = ZoomError(f"HTTP 400 Invalid access token, does not contain scopes {SECRET}",
                      status_code=400)
    result = run(zoom.run(zoom_settings(), zoom_deps(FakeZoom(user_error=scope))))
    assert by_key(result)["host"]["outcome"] == FAILED
    no_secret(result, SECRET)


def test_zoom_no_webinar_licence_fails_only_while_provisioning_is_on():
    on = run(zoom.run(zoom_settings(zoom_events=True), zoom_deps(FakeZoom(webinar=False))))
    assert by_key(on)["webinar_licence"]["outcome"] == FAILED
    off = run(zoom.run(zoom_settings(zoom_events=False), zoom_deps(FakeZoom(webinar=False))))
    assert by_key(off)["webinar_licence"]["outcome"] == OK
    assert facts(off)["Webinar capacity"] == "no webinar licence"


def test_zoom_attendance_paths():
    none = run(zoom.run(zoom_settings(), zoom_deps(FakeZoom(past=False))))
    assert by_key(none)["attendance"]["outcome"] == UNKNOWN
    assert "No past webinar" in by_key(none)["attendance"]["detail"]
    denied = ZoomError("HTTP 400 scope report:read", status_code=400)
    result = run(zoom.run(zoom_settings(), zoom_deps(FakeZoom(report_error=denied))))
    assert by_key(result)["attendance"]["outcome"] == FAILED


def test_the_zoom_client_keeps_the_token_scopes_and_types_its_errors(monkeypatch):
    import httpx

    from core import zoom as zoom_mod

    class Resp:
        status_code = 200

        def json(self):
            return {"access_token": "t", "expires_in": 3600, "scope": "a:b c:d"}

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return Resp()

    monkeypatch.setattr(zoom_mod.httpx, "AsyncClient", Client)
    client = zoom_mod.ZoomClient("a", "b", "c")
    run(client._access_token())
    assert client.scopes == "a:b c:d"

    class Down(Client):
        async def post(self, *a, **kw):
            raise httpx.ConnectError("no")

    monkeypatch.setattr(zoom_mod.httpx, "AsyncClient", Down)
    with pytest.raises(ZoomTransportError):
        run(zoom_mod.ZoomClient("a", "b", "c")._access_token())


# --- the endpoints and the status line ------------------------------------------------

_ADMIN = {"userName": "adm", "name": "Ada", "isAdmin": True, "userId": "u1",
          "token": "t", "teams": [], "roles": []}
_STAFF = dict(_ADMIN, isAdmin=False)


class FakeRuns:
    def __init__(self):
        self.rows = []

    async def record(self, result, *, trigger="manual", run_by_id="", run_by=""):
        row = dict(result, trigger=trigger, runBy=run_by)
        self.rows.append(row)
        return row

    async def latest(self, integration):
        rows = [r for r in self.rows if r["integration"] == integration]
        return rows[-1] if rows else None

    async def latest_all(self):
        return {r["integration"]: r for r in self.rows}


class NoSettings:
    async def load(self):
        return {}


def _app(monkeypatch, env, user=_ADMIN):
    from core.app import create_app

    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("SETUP_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("setup.router.current_user", lambda r: user)
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.settings_store = NoSettings()
    app.state.job_store = None
    app.state.integration_test_store = FakeRuns()
    return app


def _fake_result(integration="zoom", outcome=FAILED):
    return {"integration": integration, "outcome": outcome,
            "checks": [{"key": "token", "label": "Token", "outcome": outcome, "detail": "x"}],
            "facts": [{"label": "Host", "value": "zweb@cbm.org"}],
            "startedAt": "2026-11-13T06:00:00+00:00", "finishedAt": "2026-11-13T06:00:02+00:00",
            "durationMs": 2000}


def test_the_endpoints_are_admin_only(monkeypatch):
    client = TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "true"}, user=_STAFF))
    assert client.post("/setup/api/integrations/zoom/test").status_code == 403
    assert client.get("/setup/api/integrations/zoom/test").status_code == 403
    client = TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "true"}, user=None))
    assert client.post("/setup/api/integrations/zoom/test").status_code == 401


def test_the_endpoints_are_absent_with_the_switch_off(monkeypatch):
    client = TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "false"}))
    assert client.post("/setup/api/integrations/zoom/test").status_code == 404
    assert client.get("/setup/api/integrations/zoom/test").status_code == 404


def test_an_integration_without_a_test_says_when_its_test_comes(monkeypatch):
    import dataclasses

    import integrations.registry as registry

    untested = dataclasses.replace(registry.BY_KEY["fathom"], test_module="")
    monkeypatch.setitem(registry.BY_KEY, "fathom", untested)
    client = TestClient(_app(monkeypatch, {"INTEGRATIONS_TAB": "true"}))
    resp = client.post("/setup/api/integrations/fathom/test")
    assert resp.status_code == 409 and "phase 3" in resp.json()["detail"]
    assert client.post("/setup/api/integrations/nope/test").status_code == 404


def test_a_run_is_stored_logged_and_read_back(monkeypatch):
    async def fake_run(settings, deps=None):
        return _fake_result()

    monkeypatch.setattr(zoom, "run", fake_run)
    logged = []

    async def log_action(**kw):
        logged.append(kw)

    monkeypatch.setattr("setup.router.action_log.log_action", log_action)
    app = _app(monkeypatch, {"INTEGRATIONS_TAB": "true"})
    client = TestClient(app)
    resp = client.post("/setup/api/integrations/zoom/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stored"] is True and body["run"]["outcome"] == FAILED
    assert body["run"]["runBy"] == "adm"
    assert logged and logged[0]["action"] == "Integration Test Run"
    assert logged[0]["details"] == {"integration": "zoom", "outcome": FAILED,
                                    "checks": {"token": FAILED}}
    assert client.get("/setup/api/integrations/zoom/test").json()["run"]["outcome"] == FAILED

    # The status line reads the last run.
    page = client.get("/setup/api/settings").json()
    zoom_entry = next(i for i in page["integrations"] if i["key"] == "zoom")
    assert zoom_entry["testable"] is True
    assert zoom_entry["status"]["tested"]["outcome"] == FAILED
    assert zoom_entry["status"]["tested"]["finishedAt"] == "2026-11-13T06:00:02+00:00"
    fathom = next(i for i in page["integrations"] if i["key"] == "fathom")
    assert fathom["testable"] is True and fathom["status"]["tested"] is None


def test_the_page_never_reads_runs_with_the_switch_off(monkeypatch):
    app = _app(monkeypatch, {"INTEGRATIONS_TAB": "false"})

    class Exploding(FakeRuns):
        async def latest_all(self):
            raise AssertionError("read with the switch off")

    app.state.integration_test_store = Exploding()
    page = TestClient(app).get("/setup/api/settings").json()
    assert "integrations" not in page


def test_the_table_is_cleared_by_the_sandbox_reset():
    from core.sandbox_reset import RESET_TABLES

    assert "integration_test_run" in RESET_TABLES
