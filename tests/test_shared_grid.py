"""The shared grid, divider and loading spinner — prds/shared-grid-plan.md,
stop 1 (Doug's ruling 10-27-26: resizable columns, alternating rows,
multi-column sorting, a divider for the preview pane, a spinner while
anything loads).

The grid's sorting rules run under node against the real module; the rest
is checked by reading the files (the behaviour is checked in a browser).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parent.parent / "frontend" / "shared"


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime available")
    prog = f"require({json.dumps(str(SHARED / 'grid.js'))});\nconst G = globalThis.CBMGrid;\n{script}"
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_values_sort_as_numbers_dates_and_text_with_empties_last():
    rows = _node("""
      const items = [{v:"10"},{v:"9"},{v:""},{v:"1,200"},{v:"—"},{v:"2"}];
      const up = G.sortBy(items, [{col:"v", dir:"asc"}], (r, c) => r[c]).map(r => r.v);
      const down = G.sortBy(items, [{col:"v", dir:"desc"}], (r, c) => r[c]).map(r => r.v);
      const dates = G.sortBy([{d:"2026-10-27T01:00:00"},{d:"2026-01-02"},{d:"2026-10-26 23:00:00"}],
                             [{col:"d", dir:"asc"}], (r, c) => r[c]).map(r => r.d);
      const text = G.sortBy([{t:"item 10"},{t:"Item 9"},{t:"apple"}], [{col:"t", dir:"asc"}], (r, c) => r[c]).map(r => r.t);
      console.log(JSON.stringify({up, down, dates, text}));
    """)
    assert rows["up"] == ["2", "9", "10", "1,200", "", "—"]
    assert rows["down"] == ["1,200", "10", "9", "2", "", "—"], "an empty value stays last both ways"
    assert rows["dates"] == ["2026-01-02", "2026-10-26 23:00:00", "2026-10-27T01:00:00"]
    assert rows["text"] == ["apple", "Item 9", "item 10"], "text ignores case and orders numbers inside it"


def test_a_second_key_breaks_ties_and_the_sort_is_stable():
    out = _node("""
      const items = [{k:"Static", n:"B", i:1},{k:"Dynamic", n:"Z", i:2},{k:"Static", n:"A", i:3},{k:"Dynamic", n:"Z", i:4}];
      const r = G.sortBy(items, [{col:"k", dir:"asc"},{col:"n", dir:"desc"}], (x, c) => x[c]).map(x => x.i);
      console.log(JSON.stringify(r));
    """)
    assert out == [2, 4, 1, 3]


def test_clicks_and_shift_clicks_build_the_keys():
    out = _node("""
      let k = G.nextSort([], "name", false);
      const a = JSON.parse(JSON.stringify(k));
      k = G.nextSort(k, "name", false);           // reverse
      const b = JSON.parse(JSON.stringify(k));
      k = G.nextSort(k, "kind", true);            // add a second key
      const c = JSON.parse(JSON.stringify(k));
      k = G.nextSort(k, "kind", true);            // reverse the second key
      const d = JSON.parse(JSON.stringify(k));
      const e = G.nextSort(k, "members", false);  // a plain click starts again
      console.log(JSON.stringify({a, b, c, d, e,
        words: G.describeSort(d, {name: "Name", kind: "Type"}), param: G.sortParam(d)}));
    """)
    assert out["a"] == [{"col": "name", "dir": "asc"}]
    assert out["b"] == [{"col": "name", "dir": "desc"}]
    assert out["c"] == [{"col": "name", "dir": "desc"}, {"col": "kind", "dir": "asc"}]
    assert out["d"] == [{"col": "name", "dir": "desc"}, {"col": "kind", "dir": "desc"}]
    assert out["e"] == [{"col": "members", "dir": "asc"}]
    assert out["words"] == "Name ▼, then Type ▼"
    assert out["param"] == "name:desc,kind:desc"


def test_the_shared_parts_never_disable_anything_and_survive_a_blocked_store():
    for name in ("grid.js", "splitpane.js", "busy.js"):
        js = (SHARED / name).read_text()
        assert ".disabled = true" not in js and 'setAttribute("disabled"' not in js, name
    for name in ("grid.js", "splitpane.js"):
        js = (SHARED / name).read_text()
        assert "try { root.localStorage" in js, f"{name} wraps every storage read and write"
    busy = (SHARED / "busy.js").read_text()
    assert "window.CBMBusy = { start: start, fetch: fetchWithTimeout, loading: loading };" in busy


def test_the_spinners_cover_panels_links_and_the_page_opening():
    busy = (SHARED / "busy.js").read_text()
    assert ".cbm-loading::after" in busy and "aria-busy" in busy
    assert ".cbm-busy-link::after" in busy and 'window.addEventListener("pagehide", stop' in busy
    assert ".cbm-pageload" in busy and "PAGE_CAP_MS = 30000" in busy
    # A fast page never flashes the pill.
    assert "}, 400);" in busy
    # Reduced motion keeps a mark and stops the spin.
    assert busy.count("prefers-reduced-motion") >= 2


def test_the_divider_is_reachable_by_keyboard():
    js = (SHARED / "splitpane.js").read_text()
    assert 'setAttribute("role", "separator")' in js and "bar.tabIndex = 0" in js
    assert '"ArrowLeft"' in js and '"ArrowRight"' in js and '"dblclick"' in js
    grid = (SHARED / "grid.js").read_text()
    assert 'h.setAttribute("role", "separator")' in grid and "h.tabIndex = 0" in grid


# --- rollout 2: Mentor Administration (plan § 9) ------------------------------

MENTORADMIN = SHARED.parent.parent / "mentoradmin" / "frontend"


def test_mentor_administration_loads_the_grid_and_fits_its_three_grids():
    page = (MENTORADMIN / "index.html").read_text()
    js = (MENTORADMIN / "app.js").read_text()
    assert page.index("/shared/busy.js") < page.index("/shared/grid.js") < page.index('src="app.js"')
    assert "/shared/grid.css" in page
    # The old one-column sort is gone; every roster heading names its column.
    assert "is-sortable" not in page and "data-sort=" not in page
    assert page.count('<th data-col="') == 11
    for key in ("mentoradmin.roster", "mentoradmin.verify", "mentoradmin.documents"):
        assert f'"{key}"' in js
    assert "sortKey" not in js and "updateSortIndicators" not in js


def test_the_roster_sorts_unlimited_above_every_number_and_blanks_last():
    js = (MENTORADMIN / "app.js").read_text()
    start = js.index("  function sortVal(m, k) {")
    fn = js[start:js.index("\n  }\n", start) + 4]
    rows = [
        {"name": "a", "availableCapacity": 2},
        {"name": "b", "availableCapacity": -1},
        {"name": "c", "availableCapacity": None},
        {"name": "d", "availableCapacity": 5},
    ]
    got = _node(fn + f"""
const rows = {json.dumps(rows)};
const up = G.sortBy(rows, [{{col: "availableCapacity", dir: "asc"}}], sortVal).map(r => r.name);
const down = G.sortBy(rows, [{{col: "availableCapacity", dir: "desc"}}], sortVal).map(r => r.name);
console.log(JSON.stringify({{up, down}}));
""")
    assert got == {"up": ["a", "d", "b", "c"], "down": ["b", "d", "a", "c"]}
