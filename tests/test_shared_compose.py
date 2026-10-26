"""The shared email composer (frontend/shared/compose.js + compose.css) — one
component served to the session tools and to the lead's page in Marketing
Management (Doug's ruling 10-25-26, prospect marketing ruling 128).

The composer itself is browser code. What Python guards is the wiring: the
asset ships and is served, both pages load it in the right order (after
busy.js and the rich-text editor, before the page's own script), the page's
own stylesheet comes after the shared one so its overrides still win, and the
session tools' page script no longer carries a composer of its own.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "frontend" / "shared"
SESSIONS = ROOT / "sessions" / "frontend"
CAMPAIGNS = ROOT / "campaigns" / "frontend"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_component_ships_as_a_shared_asset():
    js = _text(SHARED / "compose.js")
    assert "window.CBMCompose = {" in js
    for part in ("open: open", "parseAddrList: parseAddrList", "makeCombobox: makeCombobox"):
        assert part in js, part
    # The whole dialog travelled: templates, attachments, drafts, the address
    # book, the write-back retry and the send-anyway gate.
    for marker in ("Replace current content?", "Attach from documents…", "Restored your unsent draft.",
                   "Add & Send", "Retry recording", "Send anyway", "function doSend()"):
        assert marker in js, marker
    assert (SHARED / "compose.css").is_file()
    css = _text(SHARED / "compose.css")
    for cls in (".sx__modal--compose .sx__modal-card", ".sx__msg-field", ".sx__combo-list", ".sx__attach-chip"):
        assert cls in css, cls


def test_shared_asset_is_served(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    get_settings.cache_clear()
    client = TestClient(create_app([info_request.SPEC]))
    assert client.get("/shared/compose.js").status_code == 200
    assert client.get("/shared/compose.css").status_code == 200


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_component_parses():
    subprocess.run(["node", "--check", str(SHARED / "compose.js")], check=True)
    subprocess.run(["node", "--check", str(SESSIONS / "app.js")], check=True)


@pytest.mark.parametrize("page", [SESSIONS / "index.html", CAMPAIGNS / "index.html"])
def test_both_pages_load_it_in_the_right_order(page: Path):
    html = _text(page)
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts.index("/shared/busy.js") == 0
    assert scripts.index("/shared/richtext.js") < scripts.index("/shared/compose.js") < scripts.index("app.js")
    sheets = re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)
    assert sheets.index("/shared/compose.css") < sheets.index("styles.css")


def test_the_session_tools_hand_the_component_their_own_modal_and_every_feature():
    app = _text(SESSIONS / "app.js")
    # One wrapper, no second composer: the body of the old composeMessage is gone.
    assert app.count("function composeMessage(") == 1
    for gone in ("function doSend()", "Replace current content?", "Add & Send", "Retry recording",
                 "function commField(", "function parseAddrList(", "function apiPostProgress("):
        assert gone not in app, gone
    wrapper = app[app.index("function composeMessage("):app.index("// --- pop-up detail (peek) ---")]
    assert "composeGuard = CBMCompose.open({" in wrapper
    assert "features: { cc: true, templates: true, attachments: true, documents: docsOn(), drafts: true, reply: true, addressBook: true }" in wrapper
    assert "requestClose: requestCloseComm" in wrapper and "open: openComm, close: closeComm" in wrapper
    # The guard still drives the page's keyboard and close handling.
    assert "composeGuard && composeGuard.send" in app and "composeGuard.dirty()" in app
    # The compose modal carries the shared sizing class.
    assert 'class="sx__modal sx__modal--compose" id="commModal"' in _text(SESSIONS / "index.html")


def test_the_compose_rules_moved_out_of_the_session_tools_sheet():
    css = _text(SESSIONS / "styles.css")
    for moved in ("#commModal .sx__modal-card", "\n.sx__msg-input {", "\n.sx__combo-list {", "\n.sx__attach-chip {"):
        assert moved not in css, moved
    # The page's own overrides of the shared shell stay where they were.
    assert "#qaddModal .sx__modal-body" in css and "#grtModal .sx__modal-card" in css
