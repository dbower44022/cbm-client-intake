"""Submission Admin on the shared grid — prds/shared-grid-plan.md § 12.

The page is checked by reading its files; the queue's sort values run under
node against the real grid module and the page's own functions.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "frontend" / "shared"
OPS = ROOT / "ops" / "frontend"


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime available")
    prog = f"require({json.dumps(str(SHARED / 'grid.js'))});\nconst G = globalThis.CBMGrid;\n{script}"
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _fn(js: str, name: str) -> str:
    start = js.index(f"  function {name}(")
    line_end = js.index("\n", start) + 1
    if js[start:line_end].rstrip().endswith("}"):   # a one-line function
        return js[start:line_end]
    return js[start:js.index("\n  }\n", start) + 4]


def _var(js: str, name: str) -> str:
    m = re.search(rf"  var {name} = .*?;\n", js, re.S)
    assert m, name
    return m.group(0)


def test_submission_admin_loads_the_grid_and_drops_its_own_sort():
    page = (OPS / "index.html").read_text()
    js = (OPS / "app.js").read_text()
    css = (OPS / "styles.css").read_text()
    assert page.index("/shared/busy.js") < page.index("/shared/grid.js") < page.index('src="app.js"')
    assert "/shared/grid.css" in page
    assert 'data-sort="' not in page
    for gone in ("sortKey", "sortDir", "colWidths", "sortedRows", "_intakeSort", '"grip"'):
        assert gone not in js, gone
    assert ".grip" not in css
    for key in ("ops.queue", "ops.correspondence"):
        assert f'"{key}"' in js, key
    # Both grids show the spinner while their rows load.
    assert 'busyOver($("gridWrap"), api("/submissions"))' in js
    assert 'busyOver($("corrTable").parentElement, api("/correspondence"))' in js
    # The correspondence headings name their columns; the chip column is "Status".
    for col in ("owed", "with", "subject", "lastAt"):
        assert f'data-col="{col}"' in page, col


def test_the_queue_sorts_statuses_by_rank_dates_by_time_and_blanks_last():
    js = (OPS / "app.js").read_text()
    prelude = "".join(
        _var(js, n) for n in ("STATUS_LABELS", "INTAKE", "INTAKE_RANK", "RESPONSE_RANK", "LIVE_REQUEST")
    ) + "".join(_fn(js, n) for n in ("statusLabel", "parseTs", "intakeInfo", "responseInfo", "queueSortVal"))
    rows = [
        {"id": "a", "status": "completed", "received_at": "2026-10-27T18:00:00+00:00",
         "last_activity_at": None, "_replyState": "owed"},
        {"id": "b", "status": "needs_attention", "received_at": "2026-10-02T07:00:00+00:00",
         "last_activity_at": "2026-10-28T09:00:00+00:00"},
        {"id": "c", "status": "held_review", "received_at": "2026-10-26 12:00:00",
         "last_activity_at": "2026-09-01T08:00:00+00:00"},
        {"id": "d", "status": "completed", "received_at": "2026-10-20T07:00:00+00:00",
         "last_activity_at": None},
    ]
    got = _node(prelude + f"""
const rows = {json.dumps(rows)};
const ids = (keys) => G.sortBy(rows, keys, queueSortVal).map(r => r.id).join("");
console.log(JSON.stringify({{
  intake: ids([{{col: "_intake", dir: "asc"}}]),
  respUp: ids([{{col: "_response", dir: "asc"}}]),
  respDown: ids([{{col: "_response", dir: "desc"}}]),
  recvUp: ids([{{col: "received_at", dir: "asc"}}]),
  lastDown: ids([{{col: "_lastact", dir: "desc"}}]),
  lastUp: ids([{{col: "_lastact", dir: "asc"}}]),
}}));
""")
    assert got == {
        "intake": "bcad",            # Error, Held-Email, Completed, Completed
        "respUp": "acdb",            # Reply owed, Awaiting review, New; "—" last
        "respDown": "dcab",          # reversed, "—" still last
        "recvUp": "bdca",            # a space-separated stamp sorts with the ISO ones
        "lastDown": "bcad",          # no activity last both ways
        "lastUp": "cbad",
    }
