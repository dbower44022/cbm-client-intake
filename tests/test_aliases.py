"""Friendly URL aliases: /clientintake (etc.) redirect straight to the form.

Any single-segment path is normalized (lowercase, alphanumerics only) and
redirected to the canonical /{slug}/ when it matches a form slug or staff
tool; unknown paths stay 404.
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_alias_variants_redirect_to_canonical_form():
    for path in ("/clientintake", "/ClientIntake", "/client_intake", "/CLIENT-INTAKE"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 307, path
        assert resp.headers["location"] == "/client-intake/", path


def test_alias_redirect_lands_on_the_form():
    resp = client.get("/inforequest")
    assert resp.status_code == 200
    assert resp.request.url.path == "/info-request/"


def test_exact_slug_without_slash_still_reaches_the_form():
    # The alias route now answers /{slug} (no trailing slash) ahead of the
    # static mount — it must land in the same place the mount's redirect did.
    resp = client.get("/volunteer")
    assert resp.status_code == 200
    assert resp.request.url.path == "/volunteer/"


def test_unknown_alias_is_404():
    assert client.get("/nope").status_code == 404


def test_staff_tool_aliases_when_active(monkeypatch):
    from core.app import create_app
    from core.config import get_settings
    from forms import ALL_SPECS

    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    try:
        staff_app = create_app(ALL_SPECS)
    finally:
        get_settings.cache_clear()
    c = TestClient(staff_app)
    resp = c.get("/MentorAdmin", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/mentoradmin/"


def test_staff_tool_aliases_absent_when_inactive():
    # main.app runs without SESSION_SECRET in tests -> staff tools unmounted,
    # so their aliases must 404 rather than redirect into nothing.
    if os.environ.get("SESSION_SECRET"):
        return  # environment has the tools enabled; covered by the test above
    assert client.get("/mentor-admin", follow_redirects=False).status_code == 404
