"""A notes value stored before its field went rich is plain text. The session
tools' rich editor and read views must up-convert it (escape + ``<br>``) or its
line breaks collapse into one run, and the first save stores it that way.

Found by review of the funder-notes handoff on 2026-10-11: the handoff
promised "the editor up-converts line breaks when it opens", which was true of
the Client Administration Notes column (its own ``plainToHtml``) and not of the
session tools, which handed the stored value straight to the editor. Browser
code, so the guards are on source, plus the real helper run under node.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SESSIONS_JS = (ROOT / "sessions" / "frontend" / "app.js").read_text()
ASSIGN_JS = (ROOT / "assignments" / "frontend" / "app.js").read_text()

_FN = re.compile(r"function plainToHtml\(s\) \{(.*?)\n  \}", re.S)


def _body(src: str) -> str:
    m = _FN.search(src)
    assert m, "plainToHtml missing"
    return m.group(1)


def test_the_two_apps_share_one_up_conversion_rule():
    """Client Administration and the session tools render the same CRM notes
    fields; the helpers must agree byte for byte or the two drift apart."""
    assert _body(SESSIONS_JS) == _body(ASSIGN_JS)


def test_rich_editor_opens_on_the_up_converted_value():
    # The shared editor and the legacy fallback both receive the converted text.
    assert "CBMRichText.create(inlineImgToDisplay(plainToHtml(value))" in SESSIONS_JS
    assert "|| makeWysiwyg(plainToHtml(value));" in SESSIONS_JS


def test_notes_read_views_up_convert_and_transcripts_do_not():
    # Every record-notes render goes through notesHtml (plainToHtml + sanitize):
    # the Overview panel (and its empty probe), its View pop-up, the Overview
    # rich blocks (partner notes, sponsor message) and the Details facts.
    assert SESSIONS_JS.count("notesHtml(") >= 6
    assert 'else if (n.type === "html") { body.innerHTML = notesHtml(raw); }' in SESSIONS_JS
    assert 'if (item.type === "html") { body.innerHTML = notesHtml(item.value || ""); }' in SESSIONS_JS
    assert 'else if (t === "wysiwyg") { v.innerHTML = notesHtml(val); }' in SESSIONS_JS
    # The notes paths must not fall back to the bare sanitizer.
    assert 'body.innerHTML = sanitizeHtml(raw)' not in SESSIONS_JS
    # A transcript and an AI summary are plain text by design (pre-wrap CSS):
    # up-converting them would double every line break. They keep the bare call.
    assert SESSIONS_JS.count("bodyEl.innerHTML = sanitizeHtml(String(text));") == 2


_HARNESS = """
const fs = require("fs"), vm = require("vm");
const sandbox = {};
vm.createContext(sandbox);
// argv: [node, harness.js, fn.js, cases.json]
vm.runInContext(fs.readFileSync(process.argv[2], "utf8") + "\\nthis.f = plainToHtml;", sandbox);
const cases = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
console.log(JSON.stringify(cases.map((c) => sandbox.f(c))));
"""

CASES = [
    ("First line\nSecond & third < fourth > fifth", "First line<br>Second &amp; third &lt; fourth &gt; fifth"),
    # The markup test is deliberately loose: a plain note that happens to read
    # like a tag passes through unconverted. Same rule as Client Administration.
    ("Windows\r\nbreaks", "Windows<br>breaks"),
    ("<p>Already <b>rich</b></p>\n<p>Two</p>", "<p>Already <b>rich</b></p>\n<p>Two</p>"),
    ("", ""),
    (None, ""),
]


@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    """Run the real helper (lifted from app.js) under node — never a Python twin."""
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime")
    tmp = tmp_path_factory.mktemp("notes")
    (tmp / "harness.js").write_text(_HARNESS)
    (tmp / "fn.js").write_text("function plainToHtml(s) {" + _body(SESSIONS_JS) + "\n}")
    (tmp / "cases.json").write_text(json.dumps([c[0] for c in CASES]))
    out = subprocess.run(
        [node, str(tmp / "harness.js"), str(tmp / "fn.js"), str(tmp / "cases.json")],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize("index", range(len(CASES)), ids=[repr(c[0])[:24] for c in CASES])
def test_plain_to_html_table(converted, index):
    assert converted[index] == CASES[index][1]
