"""Phase 6 infra hardening (reliability review 2026-07-17): fail-fast
contradictory config, the intake body cap + per-IP rate limit (decision D3:
2 MB / 30 per 10 min), and the gdrive_identity Literal."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.app import create_app
from core.config import Settings, get_settings
from forms import info_request, volunteer


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _body(**over):
    body = {
        "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
        "message": "Tell me more.", "submission_token": "tok-limits-1",
    }
    body.update(over)
    return body


# --- fail-fast contradictory config -------------------------------------------


def test_live_mode_without_api_key_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("ESPO_DRY_RUN", "false")
    monkeypatch.setenv("ESPO_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ESPO_API_KEY"):
        create_app([info_request.SPEC])


def test_async_delivery_without_store_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("ASYNC_DELIVERY", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app([info_request.SPEC])


def test_normal_dry_run_config_boots():
    with TestClient(create_app([info_request.SPEC])) as c:
        assert c.get("/healthz").status_code == 200


def test_gdrive_identity_is_a_literal():
    assert Settings(gdrive_identity="service").gdrive_identity == "service"
    with pytest.raises(ValidationError):
        Settings(gdrive_identity="Service")  # a typo must fail LOUDLY at boot


# --- intake body cap (D3) ------------------------------------------------------


def test_oversized_intake_body_is_rejected_413():
    with TestClient(create_app([info_request.SPEC])) as c:
        big = _body(message="x" * (2 * 1024 * 1024 + 100))
        r = c.post("/api/info-request/intake", json=big)
    assert r.status_code == 413
    assert "too large" in r.json()["detail"]


def test_volunteer_keeps_the_larger_resume_cap():
    """The volunteer form carries its base64 resume INSIDE the JSON — a 3 MB
    body must clear the middleware (it then fails ordinary validation, not
    413)."""
    with TestClient(create_app([volunteer.SPEC])) as c:
        r = c.post(
            "/api/volunteer/intake",
            json={"filler": "x" * (3 * 1024 * 1024)},
        )
    assert r.status_code == 422  # past the cap; rejected by the schema


def test_non_intake_routes_are_untouched():
    with TestClient(create_app([info_request.SPEC])) as c:
        assert c.get("/healthz").status_code == 200


# --- per-IP rate limit (D3) ----------------------------------------------------


def test_rate_limit_answers_429_after_the_budget(monkeypatch):
    monkeypatch.setenv("INTAKE_RATE_LIMIT", "3")
    get_settings.cache_clear()
    with TestClient(create_app([info_request.SPEC])) as c:
        for i in range(3):
            r = c.post("/api/info-request/intake", json=_body(submission_token=f"tok-rl-{i}"))
            assert r.status_code == 200, f"request {i} should pass"
        r = c.post("/api/info-request/intake", json=_body(submission_token="tok-rl-over"))
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert "wait" in r.json()["detail"]


def test_rate_limit_zero_disables(monkeypatch):
    monkeypatch.setenv("INTAKE_RATE_LIMIT", "0")
    get_settings.cache_clear()
    with TestClient(create_app([info_request.SPEC])) as c:
        for i in range(5):
            r = c.post("/api/info-request/intake", json=_body(submission_token=f"tok-nl-{i}"))
            assert r.status_code == 200


def test_rate_limit_is_per_ip(monkeypatch):
    monkeypatch.setenv("INTAKE_RATE_LIMIT", "1")
    get_settings.cache_clear()
    with TestClient(create_app([info_request.SPEC])) as c:
        assert c.post(
            "/api/info-request/intake", json=_body(submission_token="tok-ip-a"),
            headers={"X-Forwarded-For": "10.0.0.1"},
        ).status_code == 200
        assert c.post(
            "/api/info-request/intake", json=_body(submission_token="tok-ip-a2"),
            headers={"X-Forwarded-For": "10.0.0.1"},
        ).status_code == 429
        # A different caller still gets through.
        assert c.post(
            "/api/info-request/intake", json=_body(submission_token="tok-ip-b"),
            headers={"X-Forwarded-For": "10.0.0.2"},
        ).status_code == 200
