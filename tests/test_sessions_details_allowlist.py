"""P0-4 (reliability review 2026-07-17): the Details-tab PUT must only accept
the domain's configured entities + Contact. Without the allowlist it was a
generic write proxy bounded only by the caller's CRM ACL — and the Mentor Role
deliberately carries CMentorProfile edit=all (co-mentor relates), so any
Mentor Team member could set mentorStatus/dues on anyone's profile through
``PUT /mentorsessions/api/details/CMentorProfile/{id}``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request

# A NON-admin Mentor Team member — the population the bypass affected.
_MENTOR = {
    "userId": "u-mentor", "userName": "mentor.one", "name": "Mentor One",
    "isAdmin": False, "token": "tok", "teams": ["Mentor Team"],
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())


def test_details_put_rejects_unlisted_entity_with_404(monkeypatch):
    _as(monkeypatch, _MENTOR)
    saved = []

    async def fake_save(client, entity, record_id, changes):
        saved.append((entity, record_id))
        return {"status": "ok"}

    monkeypatch.setattr("sessions.details.save_details", fake_save)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put(
            "/mentorsessions/api/details/CMentorProfile/victim-1",
            json={"changes": {"mentorStatus": "Inactive"}},
        )
    # 404 (not 403) so probing can't confirm which entity names exist —
    # and the save function must never have been reached.
    assert r.status_code == 404
    assert saved == []


def test_details_put_rejects_other_uncovered_entities(monkeypatch):
    _as(monkeypatch, _MENTOR)

    async def fake_save(client, entity, record_id, changes):  # pragma: no cover
        raise AssertionError("must not be reached")

    monkeypatch.setattr("sessions.details.save_details", fake_save)
    with TestClient(_app(monkeypatch)) as c:
        for entity in ("User", "CIntakeSubmission", "CSponsorProfile"):
            r = c.put(
                f"/mentorsessions/api/details/{entity}/x1",
                json={"changes": {"name": "zz"}},
            )
            assert r.status_code == 404, entity


def test_details_put_allows_configured_entities(monkeypatch):
    _as(monkeypatch, _MENTOR)
    saved = []

    async def fake_save(client, entity, record_id, changes):
        saved.append(entity)
        return {"status": "ok"}

    monkeypatch.setattr("sessions.details.save_details", fake_save)
    with TestClient(_app(monkeypatch)) as c:
        # The mentor domain's Details tab edits exactly these.
        for entity in ("CEngagement", "Account", "CClientProfile", "Contact"):
            r = c.put(
                f"/mentorsessions/api/details/{entity}/r1",
                json={"changes": {"description": "ok"}},
            )
            assert r.status_code == 200, entity
    assert saved == ["CEngagement", "Account", "CClientProfile", "Contact"]


def test_details_put_allowlist_is_per_domain(monkeypatch):
    """CClientProfile is a mentor-domain entity — the partner domain must not
    accept it (its list is CPartnerProfile + Account + Contact)."""
    _as(monkeypatch, {**_MENTOR, "teams": ["Mentor Team", "Partner Management Team"]})

    async def fake_save(client, entity, record_id, changes):
        return {"status": "ok"}

    monkeypatch.setattr("sessions.details.save_details", fake_save)
    with TestClient(_app(monkeypatch)) as c:
        assert c.put(
            "/partnersessions/api/details/CClientProfile/r1",
            json={"changes": {"description": "x"}},
        ).status_code == 404
        assert c.put(
            "/partnersessions/api/details/CPartnerProfile/r1",
            json={"changes": {"description": "x"}},
        ).status_code == 200
