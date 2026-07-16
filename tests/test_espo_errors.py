"""core.espo.validation_message — plain-language classification of EspoCRM
validation rejections (routers use it to answer 400 instead of 502/504)."""

from core.espo import EspoError, forbidden_hint, validation_message

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
    assert forbidden_hint(EspoError(
        'relate CEngagement/E1/engagementContacts failed: HTTP 403 '
        '{"messageTranslation":{"label":"noAccessToForeignRecord"}}'
    )) == "edit access to CEngagement records"


def test_forbidden_hint_none_for_unrecognized_message():
    assert forbidden_hint(EspoError("something exploded")) is None
    assert forbidden_hint(Exception("HTTP 403")) is None
