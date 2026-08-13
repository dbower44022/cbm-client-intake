"""The shared address paste-parser is wired into every page that edits an address.

The parser itself is browser code. What Python can guard is the wiring — that
the asset ships, that it is served, and that every address surface loads it —
plus, where a JS runtime is available, the parse table itself.

The parse table matters more than usual here: a false positive silently
rewrites four fields, so the refusal cases (ordinary typing, non-US addresses)
are as load-bearing as the successes.

Plan + rulings: prds/address-paste-parsing-plan.md.
"""

from __future__ import annotations

import json
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


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_the_module_ships_as_a_shared_asset():
    assert (SHARED / "address-paste.js").is_file()
    assert (SHARED / "address-paste.css").is_file()
    source = (SHARED / "address-paste.js").read_text()
    assert "window.CBMAddress = {" in source


def test_shared_asset_is_served(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    get_settings.cache_clear()
    client = TestClient(create_app([info_request.SPEC]))
    assert client.get("/shared/address-paste.js").status_code == 200
    assert client.get("/shared/address-paste.css").status_code == 200


# Every page that edits a postal address. A new address surface that forgets the
# module is the failure this list exists to catch — add the page here when you
# add the form.
ADDRESS_PAGES = [
    ROOT / "sessions" / "frontend" / "index.html",
    ROOT / "mentoradmin" / "frontend" / "index.html",
    ROOT / "mentorprofile" / "frontend" / "index.html",
    ROOT / "directory" / "frontend" / "index.html",
    ROOT / "forms" / "volunteer" / "frontend" / "index.html",
    ROOT / "forms" / "client_intake" / "frontend" / "index.html",
]


@pytest.mark.parametrize("page", ADDRESS_PAGES, ids=lambda p: p.parent.parent.name)
def test_pages_load_the_module(page):
    html = page.read_text()
    assert "/shared/address-paste.js" in html
    assert "/shared/address-paste.css" in html


@pytest.mark.parametrize("page", ADDRESS_PAGES, ids=lambda p: p.parent.parent.name)
def test_module_loads_before_the_app_script(page):
    """`attach` is called during the app's own render, so the module has to be
    in place first — a later tag makes the feature silently absent."""
    html = page.read_text()
    assert html.index("/shared/address-paste.js") < html.index('src="app.js"')


@pytest.mark.parametrize("script,call", [
    (ROOT / "sessions" / "frontend" / "app.js", "window.CBMAddress.attach({"),
    (ROOT / "mentoradmin" / "frontend" / "app.js", "window.CBMAddress.attachByFields(form"),
    (ROOT / "mentorprofile" / "frontend" / "app.js", "window.CBMAddress.attachByFields(form"),
    (ROOT / "directory" / "frontend" / "app.js", "window.CBMAddress.attach({"),
    (ROOT / "forms" / "volunteer" / "frontend" / "app.js", "window.CBMAddress.attach({"),
    (ROOT / "forms" / "client_intake" / "frontend" / "app.js", "window.CBMAddress.attach({"),
])
def test_each_surface_actually_attaches(script, call):
    assert call in script.read_text()


def test_writes_dispatch_bubbling_events():
    """Not cosmetic: the directory binds its dirty-tracking to input/change, and
    the session tools run the "Same as billing" mirror off a DELEGATED `input`
    listener on the form. Setting `.value` alone breaks both silently."""
    source = (SHARED / "address-paste.js").read_text()
    assert 'new Event("input", { bubbles: true })' in source
    assert 'new Event("change", { bubbles: true })' in source


def test_undo_survives_the_notice_being_rebuilt():
    """`showNotice` clears any previous line first, so folding "remove the
    notice" and "forget how to undo" into one helper nulled the snapshot on the
    way IN — Undo rendered, clicked, and silently did nothing. Caught in the
    browser, not by the parse table; keep the two concerns separate."""
    source = (SHARED / "address-paste.js").read_text()
    assert "function removeNotice()" in source and "function dismiss()" in source
    body = source.split("function removeNotice()")[1].split("function dismiss()")[0]
    assert "undoSnapshot" not in body, "removeNotice must not touch the undo snapshot"


def test_volunteer_folds_the_unmapped_components():
    """The volunteer form has Street + ZIP but no City/State input, and the
    intake path has no CRM mapping for them either. Folding keeps the whole
    pasted address in Street instead of dropping half of it."""
    assert "foldUnmapped: true" in (ROOT / "forms" / "volunteer" / "frontend" / "app.js").read_text()


def test_client_intake_watches_the_zip_field_itself():
    """There is no street input on this form, so the ZIP field is both source
    and target — the point being that maxlength="10" used to truncate a pasted
    address into a ten-character fragment."""
    source = (ROOT / "forms" / "client_intake" / "frontend" / "app.js").read_text()
    assert "attach({ source: zipEl, postalCode: zipEl })" in source


def test_paste_is_read_from_the_clipboard_not_the_field():
    """Reading the field after the paste cannot work on a maxlength input — the
    browser truncates first. The handler must build the prospective value from
    the clipboard text."""
    source = (SHARED / "address-paste.js").read_text()
    assert "function prospective(" in source
    assert 'cd.getData("text")' in source


# --- the parse table ---------------------------------------------------------

# (input, expected-subset) — None means the parser must REFUSE and touch nothing.
PARSE_CASES: list[tuple[str, dict | None]] = [
    ("1234 Main St, Cleveland, OH 44113",
     {"street": "1234 Main St", "line2": "", "city": "Cleveland",
      "state": "OH", "postalCode": "44113", "confidence": "full"}),
    ("1234 Main St Suite 200, Cleveland, OH 44113",
     {"street": "1234 Main St", "line2": "Suite 200", "city": "Cleveland",
      "state": "OH", "postalCode": "44113"}),
    ("1234 Main St\nCleveland, OH 44113",
     {"street": "1234 Main St", "city": "Cleveland", "state": "OH", "postalCode": "44113"}),
    # A Google Maps copy leads with the business name.
    ("Acme Widgets, 1234 Main St, Cleveland, OH 44113",
     {"street": "1234 Main St", "city": "Cleveland", "state": "OH"}),
    # …but an addressee line is NOT a business name.
    ("Attn: Jane Doe, 1234 Main St, Cleveland, OH 44113",
     {"street": "Attn: Jane Doe, 1234 Main St", "city": "Cleveland", "state": "OH"}),
    ("1234 Main St, Cleveland, Ohio 44113-1234",
     {"street": "1234 Main St", "city": "Cleveland", "state": "OH", "postalCode": "44113-1234"}),
    ("1234 Main St, Apt 4B, Columbus, OH 43004",
     {"street": "1234 Main St", "line2": "Apt 4B", "city": "Columbus", "state": "OH"}),
    # No commas at all — split on the last street-type suffix.
    ("1234 Main St Suite 200 Cleveland OH 44113",
     {"street": "1234 Main St", "line2": "Suite 200", "city": "Cleveland", "state": "OH"}),
    # A box IS the street, never a unit.
    ("PO Box 417, Cleveland, OH 44113",
     {"street": "PO Box 417", "line2": "", "city": "Cleveland", "state": "OH"}),
    ("100 Public Square, Cleveland, OH 44113",
     {"street": "100 Public Square", "city": "Cleveland", "state": "OH"}),
    ("1234 Main St, Shaker Heights, OH 44120, USA",
     {"street": "1234 Main St", "city": "Shaker Heights", "state": "OH", "country": "USA"}),
    # Trailing contact noise must not hide the ZIP.
    ("1234 Main St, Cleveland, OH 44113, (216) 555-0143",
     {"street": "1234 Main St", "city": "Cleveland", "postalCode": "44113"}),
    # ALL CAPS gets title-cased; a street stays as written.
    ("1234 MAIN ST, CLEVELAND, OH 44113", {"city": "Cleveland", "street": "1234 MAIN ST"}),
    ("Cleveland, OH 44113",
     {"street": "", "city": "Cleveland", "state": "OH", "confidence": "partial"}),
    ("Cleveland, Ohio", {"city": "Cleveland", "state": "OH", "postalCode": ""}),
    ("44113", {"street": "", "city": "", "state": "", "postalCode": "44113"}),
    # --- refusals: the half that keeps ordinary editing safe ---
    ("1234 Main St", None),
    ("10 Downing St, London SW1A 2AA, United Kingdom", None),
    ("Just some notes about the client", None),
    ("Hello, world", None),
]

_HARNESS = """
const fs = require("fs"), vm = require("vm");
const sandbox = { window: {}, setTimeout, Event: function () {} };
vm.createContext(sandbox);
// argv: [node, harness.js, address-paste.js, cases.json]
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
const cases = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
console.log(JSON.stringify(cases.map((c) => sandbox.window.CBMAddress.parse(c))));
"""


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    """Run every case through the real module under node.

    Skips where there is no JS runtime (the deploy image has none) — the wiring
    tests above still run everywhere. Deliberately NOT a Python reimplementation
    of the parser: a twin that drifts would prove nothing about what ships.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime available for the JS parse table")
    tmp = tmp_path_factory.mktemp("addr")
    harness = tmp / "harness.js"
    harness.write_text(_HARNESS)
    inputs = tmp / "cases.json"
    inputs.write_text(json.dumps([c[0] for c in PARSE_CASES]))
    out = subprocess.run(
        [node, str(harness), str(SHARED / "address-paste.js"), str(inputs)],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize("index", range(len(PARSE_CASES)), ids=[c[0] for c in PARSE_CASES])
def test_parse_table(parsed, index):
    text, want = PARSE_CASES[index]
    got = parsed[index]
    if want is None:
        assert got is None, f"{text!r} should be refused, got {got!r}"
        return
    assert got is not None, f"{text!r} should parse"
    for key, value in want.items():
        assert got[key] == value, f"{text!r}: {key} was {got[key]!r}, wanted {value!r}"
