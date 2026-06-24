"""Tests for the CRM submission log (CIntakeSubmission record)."""

from __future__ import annotations

import json

import pytest

from core.submission_log import (
    REASON_HONEYPOT,
    REASON_NORMAL,
    REASON_ORCHESTRATOR_ERROR,
    STATUS_NEW,
    STATUS_PROCESSED,
    SUBMISSION_ENTITY,
    build_submission_payload,
    log_submission,
)
from forms.info_request.schemas import InfoRequest


class CapturingClient:
    def __init__(self, fail=False):
        self.creates: list[tuple[str, dict]] = []
        self._fail = fail
        self._n = 0

    async def create(self, entity, payload):
        if self._fail:
            raise RuntimeError("entity does not exist")
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}


def _submission(**overrides) -> InfoRequest:
    base = dict(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        message="Please tell me about mentoring.",
        how_did_you_hear="Online search",
        submission_token="tok-log-1",
        company_url="",  # not a honeypot hit by default
    )
    base.update(overrides)
    return InfoRequest(**base)


def test_normal_payload_processed_with_source_and_contact():
    payload = build_submission_payload(
        "info-request", _submission(), reason=REASON_NORMAL,
        status=STATUS_PROCESSED, contact_id="contact-9",
    )
    assert payload["form"] == "info-request"
    assert payload["reason"] == "Normal"
    assert payload["status"] == "Processed"
    assert payload["submitterEmail"] == "ada@example.com"
    # email-type field: also sent as the *Data array so EspoCRM actually stores it
    assert payload["submitterEmailData"] == [
        {"emailAddress": "ada@example.com", "primary": True, "optOut": False, "invalid": False}
    ]
    assert payload["source"] == "Online search"
    assert payload["contactId"] == "contact-9"
    # A processed record is an audit log — no reprocess instructions.
    assert "/api/info-request/intake" not in payload["description"]


def test_form_value_matches_crm_enum_casing():
    # CRM is the source of truth: partner/sponsor are Title-case in the enum;
    # the original three use the lowercase slug.
    for slug, expected in [
        ("partner", "Partner"),
        ("sponsor", "Sponsor"),
        ("info-request", "info-request"),
    ]:
        payload = build_submission_payload(
            slug, _submission(), reason=REASON_NORMAL, status=STATUS_PROCESSED
        )
        assert payload["form"] == expected


def test_honeypot_payload_clears_field_and_has_reprocess_steps():
    payload = build_submission_payload(
        "info-request", _submission(company_url="http://spam.example"),
        reason=REASON_HONEYPOT, status=STATUS_NEW,
    )
    assert payload["reason"] == "Honeypot"
    assert payload["status"] == "New"
    desc = payload["description"]
    assert "http://spam.example" in desc                 # caught value reported
    assert "/api/info-request/intake" in desc            # reprocess instructions
    block = json.loads(desc[desc.index("{"): desc.rindex("}") + 1])
    assert block["company_url"] == ""                    # cleared in the JSON


def test_error_payload_flags_failure_and_keeps_reprocess_steps():
    payload = build_submission_payload(
        "info-request", _submission(), reason=REASON_ORCHESTRATOR_ERROR, status=STATUS_NEW,
    )
    assert payload["reason"] == "OrchestratorError"
    assert "FAILED" in payload["description"]
    assert "/api/info-request/intake" in payload["description"]


def test_source_omitted_when_absent():
    payload = build_submission_payload(
        "info-request", _submission(how_did_you_hear=None),
        reason=REASON_NORMAL, status=STATUS_PROCESSED,
    )
    assert "source" not in payload


def test_oversized_fields_are_redacted():
    payload = build_submission_payload(
        "info-request", _submission(message="x" * 5000),
        reason=REASON_NORMAL, status=STATUS_PROCESSED,
    )
    assert "chars omitted>" in payload["description"]
    assert "x" * 5000 not in payload["description"]


@pytest.mark.asyncio
async def test_writes_record_to_crm():
    client = CapturingClient()
    ok = await log_submission(
        client, "info-request", _submission(),
        reason=REASON_NORMAL, status=STATUS_PROCESSED, contact_id="c-1",
    )
    assert ok is True
    [(entity, payload)] = client.creates
    assert entity == SUBMISSION_ENTITY
    assert payload["contactId"] == "c-1"


@pytest.mark.asyncio
async def test_crm_failure_is_swallowed():
    client = CapturingClient(fail=True)
    assert await log_submission(
        client, "info-request", _submission(),
        reason=REASON_NORMAL, status=STATUS_PROCESSED,
    ) is False
