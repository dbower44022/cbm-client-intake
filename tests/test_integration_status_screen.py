"""The Integrations status screen (Doug's rulings 11-15-26, after the phase 11
live review): each sub-tab is a status screen with one button — Setup, Fix or
Test Integration — and Other Actions ▾ for the rest; the setup runs in a
dialog. These run the page's own state rules in node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "setup" / "frontend" / "app.js").read_text(encoding="utf-8")


def _function(name: str) -> str:
    start = SRC.index(f"function {name}(")
    depth, i = 0, SRC.index("{", start)
    while True:
        if SRC[i] == "{":
            depth += 1
        elif SRC[i] == "}":
            depth -= 1
            if depth == 0:
                return SRC[start:i + 1]
        i += 1


def _const(name: str) -> str:
    start = SRC.index(f"var {name} =")
    return SRC[start:SRC.index("};", start) + 2]


def _state(cases: list[dict]) -> list[dict]:
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime available")
    prog = "\n".join([_const("ACTION_LABEL"), _function("integrationState"), _function("otherActions"),
                      _function("primaryLabel"),
                      f"var cases = {json.dumps(cases)};",
                      "console.log(JSON.stringify(cases.map(function (i) { var s = integrationState(i);"
                      " return {key: s.key, badge: s.badge, button: primaryLabel(i, s.action),"
                      " others: otherActions(i, s.action)}; })));"])
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


WIZ_RUNNING = {"status": "running", "inProgress": False, "position": 3, "total": 9}


def case(**kw):
    status = {"inUse": True, "credentialsMissing": [], "tested": None}
    status.update(kw.pop("status", {}))
    return {"key": "espocrm", "name": "EspoCRM", "testable": True, "status": status,
            "wizard": kw.pop("wizard", dict(WIZ_RUNNING))}


def test_one_button_follows_the_state():
    failed = {"outcome": "failed", "checks": [{"key": "conformance", "outcome": "failed"},
                                              {"key": "sign_in", "outcome": "ok"}]}
    passed = {"outcome": "ok", "checks": [{"key": "sign_in", "outcome": "ok"}]}
    got = _state([
        case(status={"tested": failed}),                                        # the Association today
        case(status={"credentialsMissing": ["API key"]}),                       # never set up
        case(),                                                                 # entered, never tested
        case(status={"tested": passed}, wizard={"status": "done", "inProgress": False}),
        case(status={"tested": passed}),                                        # a step still fails
        case(status={"inUse": False}, wizard={"status": "ended", "inProgress": False}),
        case(status={"tested": failed}, wizard=dict(WIZ_RUNNING, inProgress=True)),
        case(status={"tested": {"outcome": "unknown", "checks": []}}),
    ])
    assert got[0] == {"key": "bad", "badge": "Needs attention · 1 check fails", "button": "Fix EspoCRM",
                      "others": ["test", "review", "restart"]}
    assert (got[1]["button"], got[1]["badge"]) == ("Setup EspoCRM", "Not set up")
    assert (got[2]["button"], got[2]["badge"]) == ("Test Integration", "Not tested yet")
    assert got[3] == {"key": "ok", "badge": "Set up", "button": "Test Integration", "others": ["review", "restart"]}
    assert (got[4]["button"], got[4]["badge"]) == ("Setup EspoCRM", "Setup not finished")
    assert (got[5]["key"], got[5]["button"]) == ("unused", "Setup EspoCRM")
    assert (got[6]["key"], got[6]["button"], got[6]["badge"]) == ("progress", "Continue setup", "Setup in progress · step 3 of 9")
    assert got[6]["others"] == ["test", "review", "restart"]
    assert (got[7]["button"], got[7]["key"]) == ("Fix EspoCRM", "bad")


def test_no_action_is_a_link_and_the_rest_sit_under_other_actions():
    """Doug, 11-15-26: never a link styled as a button; one primary button and
    Other Actions ▾ for the rest. Back and Ask Claude in the dialog are buttons."""
    card = _function("statusCard")
    assert "Other Actions ▾" in card and 'class="cbm-button"' in card
    dialog = _function("renderDialog")
    assert "← Back</button>" in dialog and "Ask Claude about this</button>" in dialog
    assert "Check again" in dialog
    for name in ("statusCard", "renderDialog", "checksBlock"):
        assert 'class="link"' not in _function(name) and "<a " not in _function(name).replace(
            '<a class="cbm-button" href="/api/setup/mailing/connect">', ""), name


def test_the_dialog_is_on_the_page_and_closing_keeps_the_place():
    html = (ROOT / "setup" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="wizOverlay"' in html and 'data-wizclose="1"' in html
    # Closing only hides the dialog: no request is made, nothing is undone.
    assert "api(" not in _function("closeDialog")
