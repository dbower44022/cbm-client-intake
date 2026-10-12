"""The partner record's own client intake link on the Details tab (2026-10-12):
``<base>/client-intake/?partner=<id>``, derived from the deployment's address,
never stored, partner domain only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request
from sessions.config import MENTOR, PARTNER, SPONSOR
from sessions.service import intake_referral_link

_PARTNER_USER = {
    "userId": "u-p", "userName": "partner.manager", "name": "Pat Partner",
    "isAdmin": False, "token": "tok", "teams": ["Partner Management Team"],
}
_MENTOR_USER = {**_PARTNER_USER, "userName": "joe.mentor", "teams": ["Mentor Team"]}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_only_the_partner_domain_offers_the_link():
    assert PARTNER.intake_link_form == "client-intake"
    assert MENTOR.intake_link_form is None
    assert SPONSOR.intake_link_form is None


@pytest.mark.parametrize("base", ["https://apps.example.org", "https://apps.example.org/"])
def test_the_link_is_the_form_with_the_partner_parameter(base):
    assert intake_referral_link(base, "client-intake", "abc123") == \
        "https://apps.example.org/client-intake/?partner=abc123"


def _app(monkeypatch, base_url=""):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("APP_BASE_URL", base_url)
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())

    async def fake_details(cfg, client, parent_id, user_id=None):
        return {"id": parent_id, "sections": [], "contacts": []}

    monkeypatch.setattr("sessions.details.build_details", fake_details)


def test_partner_details_carry_the_link_from_app_base_url(monkeypatch):
    _as(monkeypatch, _PARTNER_USER)
    c = TestClient(_app(monkeypatch, "https://apps.example.org"))
    res = c.get("/partnersessions/api/details/p-1")
    assert res.status_code == 200, res.text
    assert res.json()["intakeLink"] == {
        "url": "https://apps.example.org/client-intake/?partner=p-1",
        "label": "Client intake link",
    }


def test_without_app_base_url_the_request_origin_is_used(monkeypatch):
    _as(monkeypatch, _PARTNER_USER)
    c = TestClient(_app(monkeypatch, ""))
    res = c.get("/partnersessions/api/details/p-1")
    assert res.status_code == 200, res.text
    assert res.json()["intakeLink"]["url"] == "http://testserver/client-intake/?partner=p-1"


def test_the_mentor_domain_has_no_link(monkeypatch):
    _as(monkeypatch, _MENTOR_USER)
    c = TestClient(_app(monkeypatch, "https://apps.example.org"))
    res = c.get("/mentorsessions/api/details/e-1")
    assert res.status_code == 200, res.text
    assert "intakeLink" not in res.json()
