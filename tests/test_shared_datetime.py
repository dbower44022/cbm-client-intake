"""The shared date/time control is wired into every page that needs it.

The control itself is browser code; what Python can usefully guard is the
wiring — that the asset is served, that the pages load it, and above all that
nobody reintroduces a raw `datetime-local`, which is what stored every event
four hours early before v0.192.2.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "frontend" / "shared"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_the_control_ships_as_a_shared_asset():
    assert (SHARED / "datetime.js").is_file()
    assert (SHARED / "datetime.css").is_file()
    source = (SHARED / "datetime.js").read_text()
    assert "window.CBMDateTime = CBMDateTime" in source


def test_shared_asset_is_served(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    get_settings.cache_clear()
    client = TestClient(create_app([info_request.SPEC]))
    assert client.get("/shared/datetime.js").status_code == 200
    assert client.get("/shared/datetime.css").status_code == 200


@pytest.mark.parametrize("page", [
    ROOT / "sessions" / "frontend" / "index.html",
    ROOT / "events" / "frontend" / "index.html",
])
def test_pages_load_the_control(page):
    html = page.read_text()
    assert "/shared/datetime.js" in html
    assert "/shared/datetime.css" in html


@pytest.mark.parametrize("script", [
    ROOT / "sessions" / "frontend" / "app.js",
    ROOT / "events" / "frontend" / "app.js",
])
def test_no_raw_datetime_local_inputs(script):
    """A `datetime-local` hands you LOCAL wall time; sending that to EspoCRM,
    which stores UTC, is the four-hour bug. The shared control exists so no
    editor has to remember.

    Matches the QUOTED string, i.e. actual use as an input type — the comments
    explaining why we don't use one are the point, not a violation."""
    assert '"datetime-local"' not in script.read_text()


def test_the_widget_was_removed_from_sessions_not_shadowed():
    """sessions/app.js is one shared IIFE where a later duplicate declaration
    silently wins — the extraction had to delete the original, not hide it."""
    source = (ROOT / "sessions" / "frontend" / "app.js").read_text()
    assert "window.CBMDateTime.create" in source
    for gone in ("sx__timepop", "sx__timegrid", "sx__dtdate", "function closeTimePops"):
        assert gone not in source, f"{gone} survived the extraction"
    css = (ROOT / "sessions" / "frontend" / "styles.css").read_text()
    assert "sx__timepop" not in css
