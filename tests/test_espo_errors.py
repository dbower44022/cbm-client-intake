"""core.espo.validation_message — plain-language classification of EspoCRM
validation rejections (routers use it to answer 400 instead of 502/504) — and
the P0-3 transport-error wrap (every httpx failure becomes an EspoError)."""

import httpx
import pytest

from core.espo import EspoClient, EspoError, EspoTransportError, forbidden_hint, validation_message

# The exact error shape from the 2026-07-11 prod failure (Allen Ingram save).
_PROD_BODY = (
    'update CMentorProfile/6a529b15921200c55 failed: HTTP 400 '
    '{"messageTranslation":{"label":"validationFailure","scope":null,'
    '"data":{"field":"howDidYouHearAboutCBM","type":"valid"}}}'
)


def test_validation_failure_names_field_readably():
    msg = validation_message(EspoError(_PROD_BODY))
    assert msg is not None
    assert "How Did You Hear About CBM" in msg
    assert "does not accept" in msg
    assert "messageTranslation" not in msg  # no raw CRM jargon


def test_required_rule_message():
    msg = validation_message(EspoError(
        'create CSession failed: HTTP 400 {"messageTranslation":'
        '{"label":"validationFailure","data":{"field":"dateStart","type":"required"}}}'
    ))
    assert msg is not None and "Date Start" in msg and "required" in msg


def test_unknown_rule_still_readable():
    msg = validation_message(EspoError(
        'update Contact/c1 failed: HTTP 400 {"messageTranslation":'
        '{"label":"validationFailure","data":{"field":"emailAddress","type":"emailAddress"}}}'
    ))
    assert msg is not None and "Email Address" in msg


def test_non_400_is_none():
    assert validation_message(EspoError("list CMentorProfile failed: HTTP 500 Server Error")) is None
    assert validation_message(EspoError("get Contact/c1 failed: HTTP 403 Forbidden")) is None


def test_400_without_validation_body_is_none():
    # e.g. "Forbidden attribute in where" style 400s — not a field validation
    assert validation_message(EspoError(
        'list CMentorProfile failed: HTTP 400 {"message":"Forbidden attribute"}'
    )) is None
    assert validation_message(EspoError("update X failed: HTTP 400 Bad Request")) is None


def test_truncated_body_is_none():
    # EspoError truncates bodies at 300 chars — unparseable JSON must not crash
    assert validation_message(EspoError(
        'update X failed: HTTP 400 {"messageTranslation":{"label":"validationFail'
    )) is None


# --- forbidden_hint -----------------------------------------------------------


def test_forbidden_hint_names_operation_and_entity():
    assert forbidden_hint(EspoError(
        "get CClientProfile/x1 failed: HTTP 403 Forbidden"
    )) == "read access to CClientProfile records"
    assert forbidden_hint(EspoError(
        "list_related CEngagement/E1/engagementContacts failed: HTTP 403 "
    )) == "read access to CEngagement records"
    assert forbidden_hint(EspoError(
        "create Contact failed: HTTP 403 "
    )) == "create access to Contact records"
    assert forbidden_hint(EspoError(
        "update Account/a1 failed: HTTP 403 "
    )) == "edit access to Account records"
    # relate/unrelate need EDIT on the records being linked
    # relate/unrelate WITHOUT the foreign-record label = denied on the record
    # whose link is being changed.
    assert forbidden_hint(EspoError(
        "relate CEngagement/E1/engagementContacts failed: HTTP 403 Forbidden"
    )) == "edit access to CEngagement records"


def test_forbidden_hint_names_an_assignment_refusal_not_the_scope():
    """EspoCRM's AssignmentChecker refuses an unowned create for a role whose
    Assignment Permission is not-set. Reported as "create access to Contact
    records" it sent a funder manager to ask for a grant she already held
    (live, crm-test, 2026-10-09)."""
    hint = forbidden_hint(EspoError(
        "create Contact failed: HTTP 403 "
        "[Assignment failure: assigned user or team not allowed.]"
    ))
    assert hint.startswith("the Assignment Permission its Contact write needs")
    assert "create access" not in hint


def test_forbidden_hint_names_the_linked_record_on_foreign_denial():
    """noAccessToForeignRecord = the denial is on the LINKED record, not the
    relate's own entity (Anthony Sacco 2026-07-20: told 'edit access to
    CSession' when the real gap was edit on the client Contact)."""
    hint = forbidden_hint(EspoError(
        'relate CSession/s1/sessionAttendees failed: HTTP 403 '
        '{"messageTranslation":{"label":"noAccessToForeignRecord","data":{"action":"edit"}}}'
    ))
    # For a link the user acts on by name, say what they PICKED rather than
    # quoting the CRM's link identifier at them (2026-07-26).
    assert "the contact you selected" in hint
    assert "not to the CSession" in hint
    # unrelate gets the same treatment (its op prefix carries the related id).
    hint2 = forbidden_hint(EspoError(
        'unrelate CEngagement/E1/engagementContacts (C9) failed: HTTP 403 '
        '{"messageTranslation":{"label":"noAccessToForeignRecord"}}'
    ))
    assert "the contact you selected" in hint2 and "not to the CEngagement" in hint2
    # Co-mentor linking — the case that 403'd on prod for every non-admin
    # mentor when Mentor Role's CMentorProfile edit was scoped to "own".
    hint3 = forbidden_hint(EspoError(
        'relate CEngagement/E1/additionalMentors failed: HTTP 403 '
        '{"messageTranslation":{"label":"noAccessToForeignRecord"}}'
    ))
    assert "the CBM member you selected" in hint3
    # An unknown link still gets the generic (but honest) wording.
    hint4 = forbidden_hint(EspoError(
        'relate CFoo/1/someLink failed: HTTP 403 '
        '{"messageTranslation":{"label":"noAccessToForeignRecord"}}'
    ))
    assert "record being linked" in hint4 and "someLink" in hint4


def test_forbidden_hint_none_for_unrecognized_message():
    assert forbidden_hint(EspoError("something exploded")) is None
    assert forbidden_hint(Exception("HTTP 403")) is None


# --- EspoTransportError (P0-3, reliability review 2026-07-17) ------------------
# Transport-level failures (DNS, connect, timeout) must surface as EspoError so
# every ``except EspoError`` net — _crm_failure mapping, refresh_membership
# fail-open, per-target error accumulation — covers a CRM outage too.


def _unreachable_client(monkeypatch, exc: httpx.HTTPError) -> EspoClient:
    async def _raise(self, method, url, **kwargs):
        raise exc

    monkeypatch.setattr(httpx.AsyncClient, "request", _raise)
    return EspoClient("https://crm-test.example.org", "super-secret-api-key")


async def test_transport_error_wrapped_as_espo_error(monkeypatch):
    client = _unreachable_client(monkeypatch, httpx.ConnectError("connection refused"))
    with pytest.raises(EspoError) as exc_info:
        await client.get("Contact", "c1")
    exc = exc_info.value
    assert isinstance(exc, EspoTransportError)
    # Names the operation and the host…
    assert "get Contact/c1 failed" in str(exc)
    assert "crm-test.example.org" in str(exc)
    assert "ConnectError" in str(exc)
    # …and never the credentials.
    assert "super-secret-api-key" not in str(exc)


async def test_transport_error_wrapped_on_writes(monkeypatch):
    client = _unreachable_client(monkeypatch, httpx.ReadTimeout("timed out"))
    with pytest.raises(EspoTransportError) as exc_info:
        await client.create("Contact", {"firstName": "Ada"})
    assert "create Contact failed" in str(exc_info.value)
    with pytest.raises(EspoTransportError):
        await client.update("Contact", "c1", {"firstName": "Ada"})
    with pytest.raises(EspoTransportError):
        await client.relate("CEngagement", "e1", "engagementContacts", "c1")
    with pytest.raises(EspoTransportError):
        await client.find_one("Contact", "emailAddress", "a@b.c")


def test_transport_error_not_a_validation_or_forbidden_match():
    exc = EspoTransportError(
        "get Contact/c1 failed: could not reach the CRM (host): ConnectError: boom"
    )
    assert validation_message(exc) is None
    assert not str(exc).startswith("HTTP")


def test_http_error_detail_includes_x_status_reason():
    # EspoCRM puts the denial reason in the X-Status-Reason HEADER with an
    # empty body (e.g. the Email from-address rejection) — the detail string
    # must carry it so errors never read as a bare "HTTP 403".
    from core.espo import http_error_detail

    class Resp:
        status_code = 403
        headers = {"x-status-reason": "Not allowed 'from' address."}
        text = ""

    assert http_error_detail(Resp()) == "HTTP 403 [Not allowed 'from' address.]"

    class RespBody:
        status_code = 400
        headers = {}
        text = '{"messageTranslation": {"label": "validationFailure"}}'

    detail = http_error_detail(RespBody())
    assert detail.startswith("HTTP 400 {")


# --- where-clause serialization (the v0.181 "search matched nothing" bug) ----
# EspoClient.list serializes `where` into bracketed query params. A flat
# implementation read clause["attribute"] unconditionally, so an OR GROUP clause
# (no attribute; value = a list of sub-clauses) raised KeyError — every
# all-fields directory search threw before hitting the network.


def test_encode_where_flat_clause_is_unchanged():
    from core.espo import _encode_where_clause

    assert _encode_where_clause("where[0]", {
        "type": "contains", "attribute": "name", "value": "acme",
    }) == [
        ("where[0][type]", "contains"),
        ("where[0][attribute]", "name"),
        ("where[0][value]", "acme"),
    ]


def test_encode_where_array_value_is_indexed():
    from core.espo import _encode_where_clause

    assert _encode_where_clause("where[0]", {
        "type": "in", "attribute": "status", "value": ["A", "B"],
    }) == [
        ("where[0][type]", "in"),
        ("where[0][attribute]", "status"),
        ("where[0][value][0]", "A"),
        ("where[0][value][1]", "B"),
    ]


def test_encode_where_or_group_recurses_into_subclauses():
    from core.espo import _encode_where_clause

    params = _encode_where_clause("where[0]", {
        "type": "or", "value": [
            {"type": "contains", "attribute": "name", "value": "x"},
            {"type": "contains", "attribute": "mentorTitle", "value": "x"},
        ],
    })
    assert params == [
        ("where[0][type]", "or"),
        ("where[0][value][0][type]", "contains"),
        ("where[0][value][0][attribute]", "name"),
        ("where[0][value][0][value]", "x"),
        ("where[0][value][1][type]", "contains"),
        ("where[0][value][1][attribute]", "mentorTitle"),
        ("where[0][value][1][value]", "x"),
    ]


@pytest.mark.asyncio
async def test_list_serializes_or_group_without_keyerror(monkeypatch):
    # The full EspoClient.list path must not KeyError on a group clause.
    client = EspoClient("https://crm.example", "k", 30)
    captured = {}

    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"total": 0, "list": []}

    async def fake_request(method, url, *, op, params=None, json_body=None):
        captured["params"] = params
        return FakeResp()

    monkeypatch.setattr(client, "_request", fake_request)
    await client.list("CMentorProfile", where=[{
        "type": "or", "value": [
            {"type": "contains", "attribute": "name", "value": "q"},
            {"type": "contains", "attribute": "cbmEmail", "value": "q"},
        ],
    }])
    keys = [k for k, _ in captured["params"]]
    assert "where[0][type]" in keys
    assert "where[0][value][0][attribute]" in keys
    assert "where[0][value][1][attribute]" in keys


# --- an empty metadata body is "not there", never a crash ----------------------

def _metadata_client(monkeypatch, body: bytes):
    """A client whose Metadata request answers 200 with ``body`` — a REAL
    httpx.Response, so ``.json()`` behaves exactly as it does in production."""
    client = EspoClient("https://crm.example", "k", 30)

    async def fake_request(method, url, *, op, params=None, json_body=None):
        return httpx.Response(200, content=body, request=httpx.Request(method, url))

    monkeypatch.setattr(client, "_request", fake_request)
    return client


@pytest.mark.asyncio
async def test_enum_options_of_a_field_the_crm_lacks_read_as_none(monkeypatch):
    """EspoCRM answers a metadata key it does not have with HTTP 200 and an
    EMPTY body (verified on crm-test 2026-10-01). Before this, ``resp.json()``
    raised JSONDecodeError — not an EspoError — and the Event Administration
    editor 500'd on production for every F2/F3 field its CRM did not have."""
    client = _metadata_client(monkeypatch, b"")
    assert await client.metadata_enum_options("CEvent", "audience") is None
    assert await client.metadata("entityDefs.CEvent.fields.audience") is None


@pytest.mark.asyncio
async def test_enum_options_still_parse_a_real_list(monkeypatch):
    client = _metadata_client(monkeypatch, b'["Internal","Public"]')
    assert await client.metadata_enum_options("CEvent", "audience") == ["Internal", "Public"]


@pytest.mark.asyncio
async def test_metadata_that_is_not_json_reads_as_none(monkeypatch):
    client = _metadata_client(monkeypatch, b"<html>maintenance</html>")
    assert await client.metadata("scopes") is None


# --- the shared connection pool (v0.245.0) -------------------------------------
# Every CRM call used to open its own httpx.AsyncClient — a TCP + TLS handshake
# per call (~100-125 ms against ~37 ms reused, measured 10-09-26). All calls now
# go through one process-wide pool, bound to the running loop.

from core.espo import close_shared_http, shared_http  # noqa: E402


@pytest.mark.asyncio
async def test_every_call_shares_one_pool(monkeypatch):
    seen: list[httpx.AsyncClient] = []

    async def fake_request(self, method, url, **kwargs):
        seen.append(self)
        return httpx.Response(200, json={"id": "x"}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    await close_shared_http()
    a = EspoClient("https://crm.example", "k", 30)
    b = EspoClient.for_user_token("https://crm.example", "u", "t")
    await a.get("Contact", "c1")
    await b.get("Contact", "c2")
    await a.get("Contact", "c3")
    assert len(seen) == 3
    assert len({id(c) for c in seen}) == 1, "one pool for every client and call"
    assert seen[0] is shared_http()
    await close_shared_http()
    assert seen[0].is_closed


@pytest.mark.asyncio
async def test_pool_is_rebuilt_after_close(monkeypatch):
    await close_shared_http()
    first = shared_http()
    assert shared_http() is first
    await close_shared_http()
    second = shared_http()
    assert second is not first and not second.is_closed
    await close_shared_http()


@pytest.mark.asyncio
async def test_per_call_timeout_rides_the_request(monkeypatch):
    captured = {}

    async def fake_request(self, method, url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    await EspoClient("https://crm.example", "k", 7).get("Contact", "c1")
    assert captured["timeout"] == 7
    assert captured["headers"] == {"X-Api-Key": "k"}
    await close_shared_http()


@pytest.mark.asyncio
async def test_stale_pooled_connection_retries_a_read_once(monkeypatch):
    """A keep-alive socket the server closed while idle fails on first use with
    RemoteProtocolError. A GET is retried once on a fresh socket; nothing else is."""
    calls = {"n": 0}

    async def flaky(self, method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected")
        return httpx.Response(200, json={"id": "c1"}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", flaky)
    assert (await EspoClient("https://crm.example", "k").get("Contact", "c1"))["id"] == "c1"
    assert calls["n"] == 2

    calls["n"] = 0
    with pytest.raises(EspoTransportError):
        await EspoClient("https://crm.example", "k").update("Contact", "c1", {"a": 1})
    assert calls["n"] == 1, "a write is never replayed"
    await close_shared_http()


# --- the metadata cache (v0.246.0) ---------------------------------------------
# Field definitions, layouts, labels and enum options are remembered for
# CRM_METADATA_CACHE_SECONDS, keyed by CRM address + caller identity, and ONLY
# when the process armed the cache (the web app and the worker do; a script
# never does, so the CRM-plan applier's read-back after a build stays exact).

from core.espo import arm_metadata_cache, clear_metadata_cache  # noqa: E402


def _counting_client(monkeypatch, body=b'{"name": {"type": "varchar"}}', **kw):
    client = EspoClient("https://crm.example", kw.pop("key", "k"), 30, **kw)
    calls = {"n": 0}

    async def fake_request(method, url, *, op, params=None, json_body=None):
        calls["n"] += 1
        return httpx.Response(200, content=body, request=httpx.Request(method, url))

    monkeypatch.setattr(client, "_request", fake_request)
    return client, calls


async def test_metadata_is_not_cached_unless_armed(monkeypatch):
    client, calls = _counting_client(monkeypatch)
    await client.metadata("entityDefs.Contact.fields")
    await client.metadata("entityDefs.Contact.fields")
    assert calls["n"] == 2


async def test_armed_cache_serves_repeat_reads_from_memory(monkeypatch):
    arm_metadata_cache()
    client, calls = _counting_client(monkeypatch)
    first = await client.metadata("entityDefs.Contact.fields")
    again = await client.metadata("entityDefs.Contact.fields")
    assert calls["n"] == 1 and again == first
    # A caller editing what it got does not corrupt the next reader's copy.
    again.clear()
    assert await client.metadata("entityDefs.Contact.fields") == first
    # Layouts, labels and enum options ride the same cache …
    await client.layout("Contact", "detail"); await client.layout("Contact", "detail")
    await client.i18n("Contact"); await client.i18n("Contact")
    assert calls["n"] == 3
    # … and a different key, a different CRM or a different identity does not hit.
    await client.metadata("entityDefs.Account.fields")
    other_user = EspoClient.for_user_token("https://crm.example", "u", "t")
    monkeypatch.setattr(other_user, "_request", client._request)
    await other_user.metadata("entityDefs.Contact.fields")
    assert calls["n"] == 5
    clear_metadata_cache()
    await client.metadata("entityDefs.Contact.fields")
    assert calls["n"] == 6


async def test_cache_honours_the_setting_and_never_holds_an_error(monkeypatch):
    from core.config import get_settings

    arm_metadata_cache()
    monkeypatch.setattr(get_settings(), "crm_metadata_cache_seconds", 0)
    client, calls = _counting_client(monkeypatch)
    await client.metadata("entityDefs.Contact.fields")
    await client.metadata("entityDefs.Contact.fields")
    assert calls["n"] == 2, "0 = read the CRM every time"
    monkeypatch.setattr(get_settings(), "crm_metadata_cache_seconds", 60)

    failing = EspoClient("https://crm.example", "k", 30)
    n = {"v": 0}

    async def boom(method, url, *, op, params=None, json_body=None):
        n["v"] += 1
        return httpx.Response(500, content=b"down", request=httpx.Request(method, url))

    monkeypatch.setattr(failing, "_request", boom)
    for _ in range(2):
        with pytest.raises(EspoError):
            await failing.metadata("entityDefs.Contact.fields")
    assert n["v"] == 2


async def test_an_absent_key_is_cached_as_absent(monkeypatch):
    """EspoCRM answers a key it lacks with 200 + empty body → None. Absence is
    as stable as presence inside the window (a built field shows within it)."""
    arm_metadata_cache()
    client, calls = _counting_client(monkeypatch, body=b"")
    assert await client.metadata_enum_options("CEvent", "audience") is None
    assert await client.metadata_enum_options("CEvent", "audience") is None
    assert await client.metadata("entityDefs.CEvent.fields.audience.options") is None
    assert calls["n"] == 1, "all three read the same key"


# --- per-request CRM call accounting (v0.248.0) --------------------------------

async def test_crm_calls_are_counted_only_inside_an_accounting_scope(monkeypatch):
    from core.espo import begin_crm_accounting, crm_calls

    async def fake_request(self, method, url, **kwargs):
        return httpx.Response(200, json={"id": "x"}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    client = EspoClient("https://crm.example", "k", 30)
    crm_calls.set(None)
    await client.get("Contact", "c1")          # no scope: nothing recorded
    ledger = begin_crm_accounting()
    await client.get("Contact", "c1")
    await client.get("Contact", "c2")
    assert len(ledger) == 2 and all(d >= 0 for d in ledger)

    async def boom(self, method, url, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "request", boom)
    with pytest.raises(EspoTransportError):
        await client.get("Contact", "c3")
    assert len(ledger) == 3, "a failed call still counts"
    crm_calls.set(None)
    await close_shared_http()
