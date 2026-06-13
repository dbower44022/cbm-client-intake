"""Tests for honeypot-held submission quarantine (email for admin review)."""

from __future__ import annotations

import json

import pytest

from core.config import Settings
from core.quarantine import build_quarantine_message, quarantine_submission
from forms.info_request.schemas import InfoRequest


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


def test_message_carries_payload_and_clears_honeypot():
    msg = build_quarantine_message(
        "info-request", _submission(), mail_from="bot@cbm", mail_to="admin@cbm"
    )
    assert msg["To"] == "admin@cbm"
    assert "ada@example.com" in msg["Subject"]
    body = msg.get_content()
    # The honeypot value is reported for context...
    assert "http://spam.example" in body
    # ...but the reprocess-ready JSON block has it cleared.
    start = body.index("----- submission payload -----")
    payload = json.loads(body[body.index("{", start) : body.rindex("}") + 1])
    assert payload["company_url"] == ""
    assert payload["email"] == "ada@example.com"
    assert payload["message"] == "Please tell me about mentoring."


def test_oversized_fields_are_redacted():
    msg = build_quarantine_message(
        "info-request",
        _submission(message="x" * 5000),
        mail_from="bot@cbm",
        mail_to="admin@cbm",
    )
    body = msg.get_content()
    assert "chars omitted>" in body
    assert "x" * 5000 not in body


@pytest.mark.asyncio
async def test_disabled_when_smtp_unconfigured():
    settings = Settings(smtp_host="", quarantine_email_to="", quarantine_email_from="")
    assert settings.quarantine_enabled is False
    assert await quarantine_submission(settings, "info-request", _submission()) is False


@pytest.mark.asyncio
async def test_sends_when_configured(monkeypatch):
    settings = Settings(
        smtp_host="smtp.example",
        quarantine_email_from="bot@cbm",
        quarantine_email_to="admin@cbm",
    )
    assert settings.quarantine_enabled is True

    sent = {}

    def fake_send(s, msg):
        sent["to"] = msg["To"]

    monkeypatch.setattr("core.quarantine._send_smtp", fake_send)
    ok = await quarantine_submission(settings, "info-request", _submission())
    assert ok is True
    assert sent["to"] == "admin@cbm"


@pytest.mark.asyncio
async def test_send_failure_is_swallowed(monkeypatch):
    settings = Settings(
        smtp_host="smtp.example",
        quarantine_email_from="bot@cbm",
        quarantine_email_to="admin@cbm",
    )

    def boom(s, msg):
        raise OSError("connection refused")

    monkeypatch.setattr("core.quarantine._send_smtp", boom)
    # Best-effort: a transport failure must not raise, just return False.
    assert await quarantine_submission(settings, "info-request", _submission()) is False
