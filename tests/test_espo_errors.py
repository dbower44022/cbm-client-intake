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


def test_forbidden_hint_names_the_linked_record_on_foreign_denial():
    """noAccessToForeignRecord = the denial is on the LINKED record, not the
    relate's own entity (Anthony Sacco 2026-07-20: told 'edit access to
    CSession' when the real gap was edit on the client Contact)."""
    hint = forbidden_hint(EspoError(
        'relate CSession/s1/sessionAttendees failed: HTTP 403 '
        '{"messageTranslation":{"label":"noAccessToForeignRecord","data":{"action":"edit"}}}'
    ))
    assert "record being linked" in hint
    assert "sessionAttendees" in hint
    assert "not the CSession" in hint
    # unrelate gets the same treatment (its op prefix carries the related id).
    hint2 = forbidden_hint(EspoError(
        'unrelate CEngagement/E1/engagementContacts (C9) failed: HTTP 403 '
        '{"messageTranslation":{"label":"noAccessToForeignRecord"}}'
    ))
    assert "record being linked" in hint2 and "engagementContacts" in hint2


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
