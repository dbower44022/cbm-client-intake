"""Tests for honeypot-held submission quarantine (CRM CIntakeSubmission record)."""

from __future__ import annotations

import json

import pytest

from core.quarantine import (
    QUARANTINE_ENTITY,
    build_quarantine_payload,
    quarantine_submission,
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
        submission_token="tok-quar-1",
        company_url="http://spam.example",  # honeypot was filled
    )
    base.update(overrides)
    return InfoRequest(**base)


def test_payload_has_review_fields_and_clears_honeypot():
    payload = build_quarantine_payload("info-request", _submission())
    assert payload["form"] == "info-request"
    assert payload["reason"] == "Honeypot"
    assert payload["status"] == "New"
    assert payload["submitterEmail"] == "ada@example.com"
    desc = payload["description"]
    # The honeypot value is reported for context...
    assert "http://spam.example" in desc
    # ...but the reprocess-ready JSON block has it cleared.
    block = json.loads(desc[desc.index("{") : desc.rindex("}") + 1])
    assert block["company_url"] == ""
    assert block["email"] == "ada@example.com"


def test_oversized_fields_are_redacted():
    payload = build_quarantine_payload(
        "info-request", _submission(message="x" * 5000)
    )
    assert "chars omitted>" in payload["description"]
    assert "x" * 5000 not in payload["description"]


@pytest.mark.asyncio
async def test_writes_record_to_crm():
    client = CapturingClient()
    ok = await quarantine_submission(client, "info-request", _submission())
    assert ok is True
    [(entity, payload)] = client.creates
    assert entity == QUARANTINE_ENTITY
    assert payload["reason"] == "Honeypot"


@pytest.mark.asyncio
async def test_crm_failure_is_swallowed():
    client = CapturingClient(fail=True)
    # Best-effort: a CRM create failure (e.g. entity not built yet) must not
    # raise, just return False so the user still gets a generic success.
    assert await quarantine_submission(client, "info-request", _submission()) is False
