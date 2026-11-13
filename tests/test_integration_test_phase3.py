"""The integration test, phase 3 of the Integrations tab: Fathom, Constant
Contact, Lob, Twilio, Anthropic and YouTube (prds/integrations-tab-plan.md § 3
part 2; the check lists Doug approved 11-13-26, Constant Contact option A).

Each check's ok, failed and unknown paths with fake clients, no secret in any
result, and the client reads the checks use.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from core.config import Settings, get_settings
from integrations.checks import anthropic_api, constant_contact, fathom, lob, twilio, youtube
from integrations.testing import FAILED, OK, SKIPPED, UNKNOWN

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


def outcomes(result):
    return {c["key"]: c["outcome"] for c in result["checks"]}


def facts(result):
    return {f["label"]: f["value"] for f in result["facts"]}


def no_secret(result, *secrets):
    text = json.dumps(result)
    for s in secrets:
        assert s not in text, f"secret leaked: {s[:6]}…"


class StatusError(Exception):
    def __init__(self, message, status_code=None, **extra):
        super().__init__(message)
        self.status_code = status_code
        for k, v in extra.items():
            setattr(self, k, v)


# --- Fathom -------------------------------------------------------------------------

class FakeFathom:
    def __init__(self, answer=None, error=None):
        self.answer = answer if answer is not None else {
            "items": [{"recorded_by": {"email": "a@cbm.org"}}, {"recorded_by": {"email": "b@cbm.org"}},
                      {"recorded_by": {"email": "a@cbm.org"}}],
            "next_cursor": None, "limit": 10}
        self.error = error
        self.since = None

    async def meetings_page(self, since):
        self.since = since
        if self.error:
            raise self.error
        return self.answer


def fathom_run(fake, **kw):
    s = Settings(fathom_api_key=kw.pop("key", SECRET), **kw)
    return run(fathom.run(s, fathom.Deps(client=lambda _s: fake)))


def test_fathom_passes_and_reports_who_recorded():
    fake = FakeFathom()
    result = fathom_run(fake)
    assert outcomes(result) == {"settings": OK, "meetings": OK}
    assert facts(result)["Meetings seen (last 30 days)"] == "3"
    assert facts(result)["Recorded by"] == "a@cbm.org, b@cbm.org"
    assert datetime.now(timezone.utc) - fake.since > timedelta(days=29)
    no_secret(result, SECRET)


def test_fathom_more_pages_and_an_empty_window():
    assert facts(fathom_run(FakeFathom({"items": [], "next_cursor": "c"})))[
        "Meetings seen (last 30 days)"] == "0 or more"
    assert facts(fathom_run(FakeFathom({"items": []})))["Recorded by"] == "no meeting in the window"


def test_fathom_missing_key_is_failed_and_the_read_is_not_run():
    result = fathom_run(FakeFathom(), key="")
    assert outcomes(result) == {"settings": FAILED, "meetings": UNKNOWN}


@pytest.mark.parametrize("error,outcome", [
    (StatusError(f"HTTP 401 bad key {SECRET}", 401), FAILED),
    (StatusError("HTTP 400", 400), FAILED),
    (StatusError("HTTP 503 after retries", 503), UNKNOWN),
    (StatusError("HTTP 429 after retries", 429), UNKNOWN),
    (StatusError("could not reach", None), UNKNOWN),
])
def test_fathom_read_paths(error, outcome):
    result = fathom_run(FakeFathom(error=error))
    assert by_key(result)["meetings"]["outcome"] == outcome
    no_secret(result, SECRET)


def test_fathom_an_unexpected_shape_is_unknown():
    assert by_key(fathom_run(FakeFathom({"meetings": "?"})))["meetings"]["outcome"] == UNKNOWN


def test_the_fathom_client_types_its_errors_and_reads_one_page(monkeypatch):
    from core import fathom as fathom_mod

    seen = []

    def handler(request):
        seen.append(request)
        if request.headers["X-Api-Key"] == "bad":
            return httpx.Response(401, text="no")
        return httpx.Response(200, json={"items": [], "next_cursor": "more"})

    async def nosleep(_):
        return None

    monkeypatch.setattr(fathom_mod, "_sleep", nosleep)
    client = fathom_mod.FathomClient("good", transport=httpx.MockTransport(handler))
    data = run(client.meetings_page(datetime(2026, 11, 1, tzinfo=timezone.utc)))
    assert data["next_cursor"] == "more" and len(seen) == 1  # one page, never follows
    assert seen[0].url.params["created_after"] == "2026-11-01T00:00:00Z"
    assert "include_summary" not in seen[0].url.params
    bad = fathom_mod.FathomClient("bad", transport=httpx.MockTransport(handler))
    with pytest.raises(fathom_mod.FathomError) as info:
        run(bad.meetings_page(datetime.now(timezone.utc)))
    assert info.value.status_code == 401

    def down(request):
        raise httpx.ConnectError("no")

    with pytest.raises(fathom_mod.FathomError) as info:
        run(fathom_mod.FathomClient("k", transport=httpx.MockTransport(down)).meetings_page(
            datetime.now(timezone.utc)))
    assert info.value.status_code is None


# --- YouTube ------------------------------------------------------------------------

class FakeYouTube:
    def __init__(self, items=None, error=None):
        self.items = items
        self.error = error
        self.asked = None

    async def playlists(self, ids):
        self.asked = ids
        if self.error:
            raise self.error
        if self.items is not None:
            return self.items
        return [{"id": i, "snippet": {"title": f"Title {i}"}, "contentDetails": {"itemCount": 7}}
                for i in ids]


def yt_run(fake, **kw):
    s = Settings(youtube_api_key=kw.pop("key", SECRET),
                 youtube_playlist_id=kw.pop("ids", "PL1, PL2"), **kw)
    return run(youtube.run(s, youtube.Deps(client=lambda _s: fake)))


def test_youtube_passes_with_titles_and_counts_in_one_call():
    fake = FakeYouTube()
    result = yt_run(fake)
    assert outcomes(result) == {"settings": OK, "playlists": OK}
    assert fake.asked == ["PL1", "PL2"]
    assert facts(result)["Playlist PL1"] == "Title PL1 (7 videos)"
    no_secret(result, SECRET)


def test_youtube_missing_settings_are_named():
    result = yt_run(FakeYouTube(), key="", ids="")
    assert by_key(result)["settings"]["outcome"] == FAILED
    assert "API key" in by_key(result)["settings"]["detail"]
    assert "playlist" in by_key(result)["settings"]["detail"]
    assert by_key(result)["playlists"]["outcome"] == UNKNOWN


def test_youtube_a_missing_playlist_is_failed_and_named():
    result = yt_run(FakeYouTube(items=[{"id": "PL1", "snippet": {"title": "One"},
                                        "contentDetails": {"itemCount": 3}}]))
    assert by_key(result)["playlists"]["outcome"] == FAILED
    assert "PL2" in by_key(result)["playlists"]["detail"]
    assert facts(result)["Playlist PL2"] == "not found"


@pytest.mark.parametrize("error,outcome,word", [
    (StatusError("HTTP 400 (keyInvalid)", 400, reason="keyInvalid"), FAILED, "refused the API key"),
    (StatusError("HTTP 403 (accessNotConfigured)", 403, reason="accessNotConfigured"), FAILED, "not switched on"),
    (StatusError("HTTP 403 (quotaExceeded)", 403, reason="quotaExceeded"), UNKNOWN, "quota"),
    (StatusError("HTTP 500", 500, reason=""), UNKNOWN, "Could not read"),
    (StatusError("could not be reached", None, reason=""), UNKNOWN, "Could not read"),
])
def test_youtube_error_paths(error, outcome, word):
    check = by_key(yt_run(FakeYouTube(error=error)))["playlists"]
    assert check["outcome"] == outcome and word in check["detail"]


def test_the_youtube_client_reads_playlists_and_the_error_reason(monkeypatch):
    from core import youtube as yt

    answers = {}

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            answers["url"], answers["params"] = url, params
            return answers["resp"]

    monkeypatch.setattr(yt.httpx, "AsyncClient", Client)
    req = httpx.Request("GET", "https://x")
    answers["resp"] = httpx.Response(200, json={"items": [{"id": "PL1"}]}, request=req)
    assert run(yt.YouTubeClient("k").playlists(["PL1", "PL2"])) == [{"id": "PL1"}]
    assert answers["url"].endswith("/playlists") and answers["params"]["id"] == "PL1,PL2"
    answers["resp"] = httpx.Response(403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}}, request=req)
    with pytest.raises(yt.YouTubeError) as info:
        run(yt.YouTubeClient("k").playlists(["PL1"]))
    assert info.value.status_code == 403 and info.value.reason == "quotaExceeded"
    answers["resp"] = httpx.Response(403, json={"error": {"details": [{"reason": "SERVICE_DISABLED"}]}}, request=req)
    with pytest.raises(yt.YouTubeError) as info:
        run(yt.YouTubeClient("k").playlists(["PL1"]))
    assert info.value.reason == "SERVICE_DISABLED"
    answers["resp"] = httpx.Response(200, json={"nothing": 1}, request=req)
    with pytest.raises(yt.YouTubeError):
        run(yt.YouTubeClient("k").playlists(["PL1"]))


# --- Twilio ---------------------------------------------------------------------------

class FakeTwilio:
    def __init__(self, account=None, numbers=None, account_error=None, number_error=None):
        self.account = account if account is not None else {
            "status": "active", "type": "Full", "friendly_name": "CBM"}
        self.numbers = numbers if numbers is not None else {"incoming_phone_numbers": [
            {"phone_number": "+12165550123", "friendly_name": "CBM texts",
             "capabilities": {"sms": True, "mms": True, "voice": False}}]}
        self.account_error = account_error
        self.number_error = number_error
        self.sent = []

    async def get_account(self):
        if self.account_error:
            raise self.account_error
        return self.account

    async def find_number(self, number):
        if self.number_error:
            raise self.number_error
        return self.numbers

    async def send(self, **kw):  # pragma: no cover — must never be called
        self.sent.append(kw)


def tw_run(fake, **kw):
    base = dict(sms_account_sid="AC123", sms_auth_token=SECRET, sms_from_number="+12165550123")
    base.update(kw)
    return run(twilio.run(Settings(**base), twilio.Deps(client=lambda _s: fake)))


def test_twilio_passes_reports_facts_and_never_sends():
    fake = FakeTwilio()
    result = tw_run(fake, sms_provider="twilio")
    assert outcomes(result) == {"settings": OK, "account": OK, "number": OK, "hours": OK}
    f = facts(result)
    assert f["Account type"] == "Full" and f["Sender can"] == "SMS, MMS"
    assert "console" in f["Carrier registration (A2P 10DLC)"]
    assert fake.sent == []
    no_secret(result, SECRET)


def test_twilio_dry_run_says_nothing_is_sent_and_a_trial_is_named():
    result = tw_run(FakeTwilio(account={"status": "active", "type": "Trial"}))
    assert "dry run" in by_key(result)["settings"]["detail"]
    assert "trial" in by_key(result)["account"]["detail"]


def test_twilio_missing_settings_are_failed_and_nothing_else_reads():
    result = tw_run(FakeTwilio(), sms_auth_token="", sms_from_number="")
    assert outcomes(result)["settings"] == FAILED
    assert outcomes(result)["account"] == UNKNOWN and outcomes(result)["number"] == UNKNOWN


@pytest.mark.parametrize("error,outcome,word", [
    (StatusError("HTTP 401 [20003]", 401), FAILED, "refused the account SID"),
    (StatusError("HTTP 403 [20008]", 403), FAILED, "Test credentials"),
    (StatusError("HTTP 404", 404), FAILED, "no such account"),
    (StatusError("HTTP 503", 503), UNKNOWN, "Could not read"),
    (StatusError("could not be reached", None), UNKNOWN, "Could not read"),
])
def test_twilio_account_error_paths(error, outcome, word):
    result = tw_run(FakeTwilio(account_error=error))
    assert by_key(result)["account"]["outcome"] == outcome
    assert word in by_key(result)["account"]["detail"]
    assert by_key(result)["number"]["outcome"] == UNKNOWN


def test_twilio_suspended_and_shapeless_accounts():
    assert outcomes(tw_run(FakeTwilio(account={"status": "suspended"})))["account"] == FAILED
    assert outcomes(tw_run(FakeTwilio(account={"type": "Full"})))["account"] == UNKNOWN


def test_twilio_sender_number_paths():
    assert outcomes(tw_run(FakeTwilio(numbers={"incoming_phone_numbers": []})))["number"] == FAILED
    no_sms = {"incoming_phone_numbers": [{"phone_number": "+12165550123",
                                          "capabilities": {"sms": False, "voice": True}}]}
    assert outcomes(tw_run(FakeTwilio(numbers=no_sms)))["number"] == FAILED
    silent = {"incoming_phone_numbers": [{"phone_number": "+12165550123", "capabilities": {}}]}
    assert outcomes(tw_run(FakeTwilio(numbers=silent)))["number"] == UNKNOWN
    assert outcomes(tw_run(FakeTwilio(numbers={"x": 1})))["number"] == UNKNOWN
    assert outcomes(tw_run(FakeTwilio(number_error=StatusError("HTTP 500", 500))))["number"] == UNKNOWN


def test_twilio_sending_hours_paths():
    assert outcomes(tw_run(FakeTwilio(), sms_send_hours="nine to five"))["hours"] == FAILED
    assert outcomes(tw_run(FakeTwilio(), sms_send_hours="20-9"))["hours"] == FAILED
    assert outcomes(tw_run(FakeTwilio(), sms_timezone="Mars/Olympus"))["hours"] == FAILED
    assert outcomes(tw_run(FakeTwilio(), sms_send_hours="8-21"))["hours"] == OK


def test_the_twilio_client_reads_without_sending_and_types_its_errors():
    from core.sms import SmsError, TwilioSmsClient

    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/IncomingPhoneNumbers.json"):
            return httpx.Response(403, json={"code": 20008, "message": "Test credentials"})
        return httpx.Response(200, json={"status": "active", "type": "Full"})

    client = TwilioSmsClient("AC1", "tok", "+1216", transport=httpx.MockTransport(handler))
    assert run(client.get_account())["status"] == "active"
    with pytest.raises(SmsError) as info:
        run(client.find_number("+12165550123"))
    assert info.value.status_code == 403 and info.value.code == 20008
    assert [r.method for r in seen] == ["GET", "GET"]
    assert seen[1].url.params["PhoneNumber"] == "+12165550123"


# --- Lob ------------------------------------------------------------------------------

class FakeLob:
    def __init__(self, answer=None, error=None):
        self.answer = answer if answer is not None else {"object": "list", "data": [], "count": 0}
        self.error = error
        self.created = []

    async def list_postcards(self, limit=1):
        if self.error:
            raise self.error
        return self.answer

    async def create_postcard(self, **kw):  # pragma: no cover — must never be called
        self.created.append(kw)

    async def verify_address(self, address):  # pragma: no cover — billed in live mode
        self.created.append(address)


def lob_run(fake, **kw):
    base = dict(postal_api_key="test_" + SECRET, postal_test_mode=True,
                postal_webhook_secret="whsec-abcdef")
    base.update(kw)
    return run(lob.run(Settings(**base), lob.Deps(client=lambda _s: fake)))


def test_lob_passes_in_test_mode_and_never_mails():
    fake = FakeLob(answer={"object": "list", "data": [], "count": 0, "total_count": 4})
    result = lob_run(fake, postal_provider="lob")
    assert outcomes(result) == {"settings": OK, "mode": OK, "postcards": OK, "webhook": OK}
    assert facts(result)["Lob environment"].startswith("test")
    assert facts(result)["Postcards on the account"] == "4"
    assert fake.created == []
    no_secret(result, SECRET, "test_" + SECRET, "whsec-abcdef")


def test_lob_dry_run_says_nothing_can_be_mailed():
    result = lob_run(FakeLob())
    assert "dry run" in by_key(result)["settings"]["detail"]
    assert facts(result)["Postcards on the account"] == "not reported"


def test_lob_a_live_key_with_test_mode_on_is_failed_and_the_reverse_too():
    assert outcomes(lob_run(FakeLob(), postal_api_key="live_" + SECRET))["mode"] == FAILED
    assert outcomes(lob_run(FakeLob(), postal_test_mode=False))["mode"] == FAILED
    live = lob_run(FakeLob(), postal_api_key="live_" + SECRET, postal_test_mode=False)
    assert outcomes(live)["mode"] == OK and facts(live)["Lob environment"].startswith("live")
    assert outcomes(lob_run(FakeLob(), postal_api_key="xyz_" + SECRET))["mode"] == UNKNOWN


def test_lob_missing_key_is_failed_and_the_reads_are_not_run():
    result = lob_run(FakeLob(), postal_api_key="")
    assert outcomes(result)["settings"] == FAILED
    assert outcomes(result)["mode"] == UNKNOWN and outcomes(result)["postcards"] == UNKNOWN


def test_lob_read_paths():
    from core.postal import PostalAuthError, PostalError, PostalUnavailable

    assert outcomes(lob_run(FakeLob(error=PostalAuthError("rejected"))))["postcards"] == FAILED
    assert outcomes(lob_run(FakeLob(error=PostalError("HTTP 422"))))["postcards"] == FAILED
    assert outcomes(lob_run(FakeLob(error=PostalUnavailable("down"))))["postcards"] == UNKNOWN
    assert outcomes(lob_run(FakeLob(answer={"weird": True})))["postcards"] == UNKNOWN


def test_lob_webhook_secret_fails_only_while_lob_is_chosen():
    assert outcomes(lob_run(FakeLob(), postal_webhook_secret="", postal_provider="lob"))["webhook"] == FAILED
    assert outcomes(lob_run(FakeLob(), postal_webhook_secret=""))["webhook"] == OK


def test_the_lob_client_lists_with_a_get_and_says_when_it_is_unavailable(monkeypatch):
    from core import postal

    calls = []

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, json=None, headers=None):
            calls.append((method, url))
            return calls_resp[0]

    async def nosleep(_):
        return None

    monkeypatch.setattr(postal.httpx, "AsyncClient", Client)
    monkeypatch.setattr(postal, "_sleep", nosleep)
    req = httpx.Request("GET", "https://x")
    calls_resp = [httpx.Response(200, json={"data": []}, request=req)]
    assert run(postal.LobPostalClient("test_k").list_postcards())["data"] == []
    assert calls[0] == ("GET", "https://api.lob.com/v1/postcards?limit=1")
    calls_resp[0] = httpx.Response(503, text="down", request=req)
    with pytest.raises(postal.PostalUnavailable):
        run(postal.LobPostalClient("test_k").list_postcards())
    calls_resp[0] = httpx.Response(401, text="no", request=req)
    with pytest.raises(postal.PostalAuthError):
        run(postal.LobPostalClient("test_k").list_postcards())


# --- Anthropic --------------------------------------------------------------------------

def _api_error(cls, status):
    req = httpx.Request("GET", "https://api.anthropic.com/v1/models")
    return cls(f"HTTP {status}", response=httpx.Response(status, request=req), body=None)


class FakeModels:
    def __init__(self, known=("claude-opus-4-8", "claude-opus-5-5"), list_error=None, get_error=None):
        self.known = set(known)
        self.list_error = list_error
        self.get_error = get_error

    async def list(self, limit=20):
        if self.list_error:
            raise self.list_error
        return SimpleNamespace(data=[SimpleNamespace(id=m) for m in self.known], has_more=False)

    async def retrieve(self, model_id):
        if self.get_error:
            raise self.get_error
        if model_id not in self.known:
            raise _api_error(anthropic.NotFoundError, 404)
        return SimpleNamespace(id=model_id, display_name=f"Claude {model_id}")


class FakeAnthropic:
    def __init__(self, **kw):
        self.models = FakeModels(**kw)
        self.messages = None  # a message is never sent


def ai_run(fake, **kw):
    base = dict(anthropic_api_key=SECRET)
    base.update(kw)
    return run(anthropic_api.run(Settings(**base), anthropic_api.Deps(client=lambda _s: fake)))


def test_anthropic_passes_and_names_each_model():
    result = ai_run(FakeAnthropic())
    assert outcomes(result) == {"settings": OK, "models": OK, "configured": OK}
    f = facts(result)
    assert f["Models available"] == "2"
    assert f["Summary model"] == "claude-opus-4-8 (Claude claude-opus-4-8)"
    assert f["Research model"] == "claude-opus-5-5 (Claude claude-opus-5-5)"
    no_secret(result, SECRET)


def test_anthropic_missing_key_is_failed():
    result = ai_run(FakeAnthropic(), anthropic_api_key="")
    assert outcomes(result) == {"settings": FAILED, "models": UNKNOWN, "configured": UNKNOWN}


@pytest.mark.parametrize("error,outcome", [
    (_api_error(anthropic.AuthenticationError, 401), FAILED),
    (_api_error(anthropic.PermissionDeniedError, 403), FAILED),
    (_api_error(anthropic.RateLimitError, 429), UNKNOWN),
    (_api_error(anthropic.InternalServerError, 500), UNKNOWN),
    (anthropic.APIConnectionError(request=httpx.Request("GET", "https://x")), UNKNOWN),
])
def test_anthropic_list_paths(error, outcome):
    result = ai_run(FakeAnthropic(list_error=error))
    assert outcomes(result)["models"] == outcome
    assert outcomes(result)["configured"] == UNKNOWN


def test_anthropic_an_unknown_model_fails_only_while_its_feature_is_on():
    off = ai_run(FakeAnthropic(), summary_model="claude-nope")
    assert outcomes(off)["configured"] == OK and "claude-nope" in by_key(off)["configured"]["detail"]
    assert facts(off)["Summary model"] == "claude-nope: does not exist"
    on = ai_run(FakeAnthropic(), summary_model="claude-nope", comms_ai_summary=True)
    assert outcomes(on)["configured"] == FAILED and "email summaries" in by_key(on)["configured"]["detail"]
    research = ai_run(FakeAnthropic(), enrichment_ai_model="", enrichment_ai=True)
    assert outcomes(research)["configured"] == FAILED


def test_anthropic_a_model_read_that_cannot_complete_is_unknown():
    result = ai_run(FakeAnthropic(get_error=_api_error(anthropic.InternalServerError, 503)))
    assert outcomes(result)["configured"] == UNKNOWN


def test_the_anthropic_client_never_retries_inside_a_check():
    client = anthropic_api._default_client(Settings(anthropic_api_key="k"))
    assert client.max_retries == 0


# --- Constant Contact ---------------------------------------------------------------------

def _conn(**kw):
    from core.mailing import Connection

    base = dict(status="connected", account_label="CBM", connected_by="Ada",
                connected_at=datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 11, 14, 6, 0, tzinfo=timezone.utc),
                last_refresh_at=datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc),
                last_error=None,
                scopes=("contact_data", "campaign_data", "account_read", "offline_access"),
                list_id=None, pull_cursor=None, last_push_at=None, last_push_summary=None)
    base.update(kw)
    return Connection(**base)


class FakeStore:
    def __init__(self, conn=None, error=None):
        self.conn = conn
        self.error = error
        self.refreshed = 0

    async def get(self):
        if self.error:
            raise self.error
        return self.conn

    async def access_token(self, *a, force=False, **kw):  # pragma: no cover
        self.refreshed += 1
        return "t"


class FakeMail:
    def __init__(self, summary=None, lists=None, field=None, error=None, list_error=None):
        self.summary = summary if summary is not None else {"organization_name": "Cleveland BM"}
        self._lists = lists if lists is not None else [{"name": "Event notices", "membership_count": 412}]
        self.field = field
        self.error = error
        self.list_error = list_error
        self.membership_asked = None
        self.writes = []

    async def account_summary(self):
        if self.error:
            raise self.error
        return self.summary

    async def lists(self, *, membership_count=False):
        self.membership_asked = membership_count
        if self.list_error:
            raise self.list_error
        return self._lists

    async def find_custom_field(self, name):
        return self.field

    async def create_list(self, name):  # pragma: no cover — never written
        self.writes.append(name)

    async def create_custom_field(self, label):  # pragma: no cover — never written
        self.writes.append(label)


def cc_run(store, mail, **kw):
    base = dict(mailing_client_id="cid", mailing_client_secret=SECRET)
    base.update(kw)
    deps = constant_contact.Deps(store=lambda _s: store, client=lambda _st, _s: mail)
    return run(constant_contact.run(Settings(**base), deps))


def test_constant_contact_passes_reports_facts_and_writes_nothing():
    mail = FakeMail()
    store = FakeStore(_conn())
    result = cc_run(store, mail)
    assert outcomes(result) == {"settings": OK, "connection": OK, "account": OK,
                                "list": OK, "field": SKIPPED}
    f = facts(result)
    assert f["Account"] == "Cleveland BM"
    assert f["List"] == "Event notices (412 members)"
    assert f["Connected by"] == "Ada, 10-08-26 14:00 UTC"
    assert f["Access token expires"] == "11-14-26 06:00 UTC"
    assert mail.membership_asked is True and mail.writes == []
    assert store.refreshed == 0  # option A: the test adds no refresh of its own
    no_secret(result, SECRET)


def test_constant_contact_missing_settings_and_no_database():
    result = cc_run(FakeStore(_conn()), FakeMail(), mailing_client_secret="")
    assert outcomes(result)["settings"] == FAILED and outcomes(result)["connection"] == UNKNOWN
    assert outcomes(cc_run(None, FakeMail()))["connection"] == FAILED


def test_constant_contact_connection_paths():
    assert "Connect" in by_key(cc_run(FakeStore(None), FakeMail()))["connection"]["detail"]
    reauth = cc_run(FakeStore(_conn(status="needs_reauthorisation", last_error="refused")), FakeMail())
    assert outcomes(reauth)["connection"] == FAILED and "refused" in by_key(reauth)["connection"]["detail"]
    assert outcomes(reauth)["account"] == UNKNOWN
    scopes = cc_run(FakeStore(_conn(scopes=("contact_data", "offline_access"))), FakeMail())
    assert outcomes(scopes)["connection"] == FAILED and "account_read" in by_key(scopes)["connection"]["detail"]
    broken = cc_run(FakeStore(error=RuntimeError("db down")), FakeMail())
    assert outcomes(broken)["connection"] == UNKNOWN


def test_constant_contact_account_paths():
    from core.mailing import MailingError, MailingNotConnected, MailingRateLimited

    refused = MailingError("HTTP 403")
    refused.status_code = 403
    down = MailingError("could not reach the service")
    assert outcomes(cc_run(FakeStore(_conn()), FakeMail(error=refused)))["account"] == FAILED
    assert outcomes(cc_run(FakeStore(_conn()), FakeMail(error=down)))["account"] == UNKNOWN
    assert outcomes(cc_run(FakeStore(_conn()), FakeMail(error=MailingRateLimited("x"))))["account"] == UNKNOWN
    gone = cc_run(FakeStore(_conn()), FakeMail(error=MailingNotConnected("needs re-authorisation")))
    assert outcomes(gone)["account"] == FAILED and outcomes(gone)["list"] == UNKNOWN
    assert outcomes(cc_run(FakeStore(_conn()), FakeMail(summary={})))["account"] == UNKNOWN


def test_constant_contact_list_and_field_paths():
    absent = cc_run(FakeStore(_conn()), FakeMail(lists=[{"name": "Other"}]))
    assert outcomes(absent)["list"] == OK and "first push" in by_key(absent)["list"]["detail"]
    uncounted = cc_run(FakeStore(_conn()), FakeMail(lists=[{"name": "event NOTICES"}]))
    assert facts(uncounted)["List"] == "event NOTICES (count not reported members)"
    down = MailingErrorWith(500)
    assert outcomes(cc_run(FakeStore(_conn()), FakeMail(list_error=down)))["list"] == UNKNOWN
    assert outcomes(cc_run(FakeStore(_conn()), FakeMail(), mailing_list_name=""))["list"] == FAILED
    on = cc_run(FakeStore(_conn()), FakeMail(field={"name": "cbm_lead_code"}), campaign_list_sync=True)
    assert outcomes(on)["field"] == OK and facts(on)["Lead-code field"] == "cbm_lead_code"
    missing = cc_run(FakeStore(_conn()), FakeMail(field=None), campaign_list_sync=True)
    assert outcomes(missing)["field"] == OK and "next push" in by_key(missing)["field"]["detail"]


def MailingErrorWith(status):
    from core.mailing import MailingError

    err = MailingError(f"HTTP {status}")
    err.status_code = status
    return err


def test_the_mailing_client_asks_for_the_membership_count_and_keeps_the_status(monkeypatch):
    from core import mailing

    seen = []

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, params=None, json=None, headers=None):
            seen.append(params)
            return resp[0]

    async def token(_force):
        return "t"

    async def nosleep(_):
        return None

    monkeypatch.setattr(mailing.httpx, "AsyncClient", Client)
    monkeypatch.setattr(mailing, "_sleep", nosleep)
    req = httpx.Request("GET", "https://x")
    resp = [httpx.Response(200, json={"lists": [{"name": "A", "membership_count": 3}]}, request=req)]
    client = mailing.MailingClient(token)
    assert run(client.lists(membership_count=True))[0]["membership_count"] == 3
    assert seen[-1]["include_membership_count"] == "all"
    run(client.lists())
    assert "include_membership_count" not in seen[-1]
    resp[0] = httpx.Response(403, text="no", request=req)
    with pytest.raises(mailing.MailingError) as info:
        run(client.account_summary())
    assert info.value.status_code == 403
