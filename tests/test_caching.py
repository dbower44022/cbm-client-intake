"""Frontend assets must always revalidate; the API must not be cached.

Guards the `no-cache` middleware that keeps deploys from being masked by a
stale browser/edge cache (no hard-refresh needed).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_frontend_assets_revalidate():
    # HTML, JS, and CSS served to the browser must carry no-cache.
    for path in ("/", "/client-intake/", "/client-intake/app.js", "/shared/wizard.css"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers.get("cache-control") == "no-cache", path


def test_unchanged_asset_returns_304():
    # The ETag round-trips to a cheap 304, so no-cache stays efficient.
    first = client.get("/shared/wizard.css")
    etag = first.headers["etag"]
    again = client.get("/shared/wizard.css", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_api_and_healthz_not_marked_no_cache():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") != "no-cache"
