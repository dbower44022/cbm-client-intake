"""The shared grid on Event Administration, System Settings and the
Analytics panels — prds/shared-grid-plan.md § 12 (rollout 5).

The pages are checked by reading their files; the events sort values run
under node against the real grid module (the behaviour is checked in a
browser).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "frontend" / "shared"
EVENTS = ROOT / "events" / "frontend"
SETUP = ROOT / "setup" / "frontend"
ANALYTICS = ROOT / "analytics" / "frontend"


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime available")
    prog = f"require({json.dumps(str(SHARED / 'grid.js'))});\nconst G = globalThis.CBMGrid;\n{script}"
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _fn(js: str, signature: str) -> str:
    start = js.index(signature)
    return js[start:js.index("\n  }\n", start) + 4]


def _loads_grid(page: str) -> None:
    assert page.index("/shared/busy.js") < page.index("/shared/grid.js") < page.index('src="app.js"')
    assert "/shared/grid.css" in page


# --- Event Administration ---------------------------------------------------


def test_event_administration_loads_the_grid_and_drops_its_own_sort():
    page = (EVENTS / "index.html").read_text()
    js = (EVENTS / "app.js").read_text()
    _loads_grid(page)
    assert 'data-sort="' not in page
    for key in ("events.list", "events.registrants", "events.conversion"):
        assert f'"{key}"' in js
    assert "state.sort" not in js and "[data-sort]" not in js
    assert 'data-col="actions" data-sortable="false"' in page
    # The list still opens newest first.
    assert 'var EVENT_SORT = [{ col: "startsAtUtc", dir: "desc" }];' in js


def test_the_public_preview_pages_are_untouched_by_the_grid():
    for name in ("preview.html", "preview-event.html", "preview.js", "preview-event.js"):
        text = (EVENTS / name).read_text()
        assert "/shared/grid." not in text and "CBMGrid" not in text, name


def test_events_sort_by_their_data_with_blanks_last():
    fn = _fn((EVENTS / "app.js").read_text(), "  function eventSortValue(row, col) {")
    rows = [
        {"topic": "B", "startsAtUtc": "2026-03-01 15:00:00", "summary_counts": {"registered": 9, "showRate": 0.5}},
        {"topic": "a", "startsAtUtc": "2026-05-01 15:00:00", "summary_counts": {"registered": 9, "showRate": None},
         "recordingUrl": "https://x"},
        {"topic": "C", "startsAtUtc": None, "summary_counts": {}},
        {"topic": "D", "startsAtUtc": "2025-12-01 15:00:00", "summary_counts": {"registered": 30, "showRate": 0}},
    ]
    got = _node(fn + f"""
const rows = {json.dumps(rows)};
const pick = (keys) => G.sortBy(rows, keys, eventSortValue).map(r => r.topic);
console.log(JSON.stringify({{
  when: pick([{{col: "startsAtUtc", dir: "desc"}}]),
  two: pick([{{col: "registered", dir: "asc"}}, {{col: "name", dir: "asc"}}]),
  rate: pick([{{col: "showRate", dir: "asc"}}]),
  rec: pick([{{col: "recording", dir: "desc"}}]),
}}));
""")
    assert got == {
        "when": ["a", "B", "D", "C"],
        "two": ["a", "B", "D", "C"],
        "rate": ["D", "B", "a", "C"],
        "rec": ["a", "B", "C", "D"],
    }


def test_registrants_sort_by_their_data_not_their_buttons():
    fn = _fn((EVENTS / "app.js").read_text(), "  function registrantSortValue(r, col) {")
    rows = [
        {"firstName": "Zoe", "lastName": "A", "minutesAttended": 40},
        {"firstName": "Al", "lastName": "B", "minutesAttended": None, "confirmationSentAt": "2026-01-01"},
        {"firstName": "Bo", "lastName": "C", "minutesAttended": 5},
    ]
    got = _node(fn + f"""
const rows = {json.dumps(rows)};
const pick = (keys) => G.sortBy(rows, keys, registrantSortValue).map(r => r.firstName);
console.log(JSON.stringify({{
  mins: pick([{{col: "minutes", dir: "desc"}}]),
  name: pick([{{col: "name", dir: "asc"}}]),
  emails: pick([{{col: "emails", dir: "asc"}}]),
}}));
""")
    assert got == {"mins": ["Zoe", "Bo", "Al"], "name": ["Al", "Bo", "Zoe"], "emails": ["Al", "Zoe", "Bo"]}


# --- System Settings ----------------------------------------------------------


def test_system_settings_loads_the_grid_and_fits_its_tables():
    page = (SETUP / "index.html").read_text()
    js = (SETUP / "app.js").read_text()
    _loads_grid(page)
    assert 'data-sort="' not in page and 'data-sort="' not in js
    for key in ("setup.settings", "setup.allSettings", "setup.diff", "setup.runs", "setup.history"):
        assert f'"{key}"' in js
    # The settings groups are a form in rows and the run history has a report
    # row under each run: resize and shading, never a sort.
    head = js[js.index("var SETTINGS_HEAD"):js.index("function fitGrid")]
    assert head.count('data-sortable="false"') == 3
    runs = js[js.index("su__table--runs"):js.index('"setup.runs"')]
    assert 'data-sortable="false"' in runs


# --- Analytics ----------------------------------------------------------------


def test_rows_panels_use_the_grid_only_where_it_is_loaded():
    charts = (SHARED / "charts.js").read_text()
    assert "if (window.CBMGrid)" in charts
    assert '"analytics.rows."' in charts
    assert 'th.setAttribute("data-col", c.key)' in charts
    # Every page that draws analytics panels loads the grid after busy.js.
    pages = [
        ROOT / "portal" / "frontend" / "index.html",
        ANALYTICS / "index.html",
        ROOT / "directory" / "frontend" / "record.html",
        ROOT / "mentoradmin" / "frontend" / "index.html",
        ROOT / "sessions" / "frontend" / "index.html",
        ROOT / "campaigns" / "frontend" / "index.html",
    ]
    for p in pages:
        text = p.read_text()
        assert "/shared/charts.js" in text, p
        assert text.index("/shared/busy.js") < text.index("/shared/grid.js"), p
        assert "/shared/grid.css" in text, p


def test_the_analytics_library_lists_use_the_grid():
    page = (ANALYTICS / "index.html").read_text()
    js = (ANALYTICS / "app.js").read_text()
    _loads_grid(page)
    for key in ("analytics.metrics", "analytics.pages"):
        assert f'"{key}"' in js
