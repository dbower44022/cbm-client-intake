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


# --- duration (EspoCRM's virtual field) --------------------------------------


def test_duration_helpers_are_shared():
    source = (SHARED / "datetime.js").read_text()
    for symbol in ("createDuration", "readDuration", "durationBetween",
                   "endStamp", "DURATION_OPTIONS", "formatDuration"):
        assert symbol in source


def test_sessions_uses_the_shared_duration_helpers():
    """One implementation, so the two editors cannot drift apart."""
    source = (ROOT / "sessions" / "frontend" / "app.js").read_text()
    assert "window.CBMDateTime.DURATION_OPTIONS" in source
    assert "window.CBMDateTime.durationBetween" in source
    assert "window.CBMDateTime.endStamp" in source


def test_events_translates_duration_into_dateend():
    """`duration` is VIRTUAL in EspoCRM (dateEnd - dateStart). Sending it stores
    nothing, which is why events kept a null duration AND a null dateEnd. The
    editor must send the recomputed dateEnd and drop the virtual field."""
    source = (ROOT / "events" / "frontend" / "app.js").read_text()
    assert "window.CBMDateTime.endStamp(changes.dateStart, changes.duration)" in source
    assert "delete changes.duration;" in source
    assert "window.CBMDateTime.createDuration" in source


def test_events_can_actually_write_dateend():
    """The translation is pointless if the server drops the field: dateEnd has
    to be in the update whitelist, while staying out of the rendered form."""
    from events import config as cfg

    assert "dateEnd" in cfg.EVENT_EDIT_NAMES
    spec = next(f for f in cfg.EVENT_FIELDS if f.name == "dateEnd")
    assert spec.hidden and not spec.app_managed


def test_shared_duration_options_match_what_sessions_offered():
    """A shared default is not licence to change a live tool's choices."""
    source = (SHARED / "datetime.js").read_text()
    assert "[300, 600, 900, 1800, 2700, 3600, 7200, 10800]" in source
