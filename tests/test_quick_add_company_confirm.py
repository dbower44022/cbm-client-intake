"""Quick add — a company name typed but never picked (Doug's ruling 10-30-26,
option C).

The Company search box hid its "+ New company…" entry as soon as the typed
text matched no company, so a new company could not be entered and the save
said "choose + New company…". Now a typed-but-unpicked name is resolved at
Create: one exact match is used as if picked, anything else asks "create it
as a new company?" with the name editable and the near matches offered.

The decision is the pure helper ``qaddCompanyIntent`` in the page script; it
runs here under node, lifted from app.js, never as a Python twin.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_APP_JS = (_ROOT / "sessions" / "frontend" / "app.js").read_text()
_INDEX = (_ROOT / "sessions" / "frontend" / "index.html").read_text()
_CSS = (_ROOT / "sessions" / "frontend" / "styles.css").read_text()


def _function(src: str, name: str) -> str:
    """The full text of ``function name(...) {...}``, by brace matching."""
    start = src.index("function " + name + "(")
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError("unbalanced " + name)


_HARNESS = """
const fs = require("fs"), vm = require("vm");
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8") + "\\nthis.f = qaddCompanyIntent;", sandbox);
const cases = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
console.log(JSON.stringify(cases.map((c) => sandbox.f(c[0], c[1]))));
"""

_COMPANIES = [
    {"id": "A1", "name": "Ironwood Credit Union"},
    {"id": "A2", "name": "Key Bank"},
    {"id": "A3", "name": "Key Bank"},
    {"id": "A4", "name": "Westlake Porter Library"},
    {"id": "A5", "name": "Co"},
]

_CASES = [
    ("", _COMPANIES),
    ("   ", _COMPANIES),
    ("ironwood  credit union ", _COMPANIES),   # exact, capitals and spacing ignored
    ("Brand New Bakery", _COMPANIES),          # nothing like it
    ("Westlake Porter", _COMPANIES),           # part of a known name
    ("Ironwood Credit Union Inc", _COMPANIES), # a known name inside it
    ("Key Bank", _COMPANIES),                  # two companies share it
    ("Acme Corp", _COMPANIES),                 # "Co" is too short to count as inside it
    ("Anything", []),                          # no company list at all
]


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime")
    tmp = tmp_path_factory.mktemp("qadd")
    (tmp / "harness.js").write_text(_HARNESS)
    (tmp / "fn.js").write_text(_function(_APP_JS, "qaddCompanyIntent"))
    (tmp / "cases.json").write_text(json.dumps(_CASES))
    out = subprocess.run(
        [node, str(tmp / "harness.js"), str(tmp / "fn.js"), str(tmp / "cases.json")],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _ids(r):
    return [a["id"] for a in r["near"]]


def test_nothing_typed_asks_nothing(results):
    assert results[0] == {"kind": "none"}
    assert results[1] == {"kind": "none"}


def test_one_exact_match_is_used_as_if_picked(results):
    assert results[2]["kind"] == "exact"
    assert results[2]["company"]["id"] == "A1"


def test_an_unknown_name_asks_to_create_it(results):
    r = results[3]
    assert r["kind"] == "new" and r["name"] == "Brand New Bakery"
    assert r["near"] == [] and r["several"] is False


def test_a_partial_match_still_asks_and_offers_the_match(results):
    r = results[4]
    assert r["kind"] == "new" and r["name"] == "Westlake Porter"
    assert _ids(r) == ["A4"]


def test_a_known_name_inside_the_typed_one_is_offered(results):
    assert _ids(results[5]) == ["A1"]


def test_two_same_named_companies_are_never_guessed_between(results):
    r = results[6]
    assert r["kind"] == "new" and r["several"] is True
    assert _ids(r) == ["A2", "A3"]


def test_a_very_short_name_is_not_a_near_match(results):
    assert _ids(results[7]) == []


def test_no_company_list_still_asks(results):
    assert results[8]["kind"] == "new" and results[8]["near"] == []


def test_the_save_routes_a_typed_name_through_the_confirmation():
    save = _function(_APP_JS, "saveQuickAdd")
    assert "qaddCompanyIntent(qadd.companyCombo.input.value, qadd.companies)" in save
    assert "if (pending) { qaddShowConfirm(pending); return; }" in save
    # The confirmation comes only after every other required field is filled.
    assert save.index("if (missing.length)") < save.index("qaddShowConfirm(pending)")


def test_the_confirmation_panel_is_wired():
    assert 'id="qaddConfirm"' in _INDEX and 'id="qaddActions"' in _INDEX
    # display:block / flex would beat [hidden] without these.
    assert ".qadd__form[hidden], .qadd__form-actions[hidden] { display: none; }" in _CSS
    show = _function(_APP_JS, "qaddShowConfirm")
    assert "Create it as a new company?" in show
    assert '"Create company and "' in show
    # A corrected name that matches a known company uses it, never a duplicate.
    assert re.search(r'again\.kind === "exact"\) qaddUseCompany', show)


# --- the record name follows a corrected company name (v0.301.2) -------------
# Doug's ruling 10-30-26: on the crm-test pass the company was corrected to
# "Rocky River Test Bakery" while the partner kept "Rocky Rivr Test Bakery".

_FOLLOW_HARNESS = """
const fs = require("fs"), vm = require("vm");
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8") + "\\nthis.f = qaddFollowsCorrection;", sandbox);
const cases = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
console.log(JSON.stringify(cases.map((c) => sandbox.f(c[0], c[1], c[2]))));
"""

_FOLLOW_CASES = [
    # (record name, typed company, corrected company) -> follows?
    (("Rocky Rivr Test Bakery", "Rocky Rivr Test Bakery", "Rocky River Test Bakery"), True),
    (("rocky  rivr test bakery", "Rocky Rivr Test Bakery", "Rocky River Test Bakery"), True),
    (("Rocky Bakery Partnership", "Rocky Rivr Test Bakery", "Rocky River Test Bakery"), False),
    (("", "Rocky Rivr Test Bakery", "Rocky River Test Bakery"), False),
    (("Rocky Rivr Test Bakery", "Rocky Rivr Test Bakery", "rocky rivr test bakery"), False),
]


@pytest.fixture(scope="module")
def follows(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime")
    tmp = tmp_path_factory.mktemp("qaddfollow")
    (tmp / "harness.js").write_text(_FOLLOW_HARNESS)
    (tmp / "fn.js").write_text(_function(_APP_JS, "qaddFollowsCorrection"))
    (tmp / "cases.json").write_text(json.dumps([c[0] for c in _FOLLOW_CASES]))
    out = subprocess.run(
        [node, str(tmp / "harness.js"), str(tmp / "fn.js"), str(tmp / "cases.json")],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize("index", range(len(_FOLLOW_CASES)))
def test_record_name_follows_only_an_exact_typo(follows, index):
    assert follows[index] is _FOLLOW_CASES[index][1]


def test_the_confirmation_applies_the_follow_rule():
    show = _function(_APP_JS, "qaddShowConfirm")
    assert 'qaddFollowsCorrection(qaddValue("name"), intent.name, n)' in show
    # The rule runs before either branch, so an exact match follows too.
    assert show.index("qaddFollowsCorrection(") < show.index("var again = qaddCompanyIntent(n")
