/* Shared grid behaviour — resizable columns, alternating rows and
 * multi-column sorting for every grid (Doug's ruling 10-27-26: "All grids
 * must have resizable columns, alternating colored rows, multi-column
 * sorting"). Plan: prds/shared-grid-plan.md.
 *
 * A screen keeps drawing its own <table>; this adds the behaviour on top:
 *
 *   var grid = CBMGrid.enhance(tableEl, {
 *     key: "lists.index",            // remembers widths and sort per browser
 *     sort: [{ col: "name", dir: "asc" }],   // the starting sort (optional)
 *     onSort: function (keys) { ... },       // sorting done by the screen or
 *                                            // the server; omit it and the
 *                                            // grid sorts its own rows
 *   });
 *   grid.refresh();   // after the screen redraws its rows or headings
 *
 * Columns are named by data-col on each <th> (else their position). A <th>
 * with data-sortable="false" never sorts — a server-paged grid marks the
 * columns its server cannot sort, and says why in the title. A <td> may
 * carry data-sort="<value>" when its text is not what it should sort by.
 *
 * Sorting: a click sorts by that column alone, a second click reverses it;
 * Shift-click adds the column as the next key (or reverses it if it is one
 * already). The heading shows ▲1 / ▼2; the status line below the grid says
 * the order in words, with Clear sort and Reset columns.
 *
 * Widths: a handle on each heading's right edge drags the width; a
 * double-click fits the column to its widest cell; arrow keys move it when
 * the handle has focus. Visual only — it never disables anything. */
(function (root) {
  "use strict";
  var STORE = "cbm.grid.";

  // --- pure helpers (no DOM; tested under node) ---------------------------------

  var DATE_RE = /^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?/;
  var NUM_RE = /^[-+]?[$€£]?\s*[\d,]*\.?\d+\s*%?$/;

  /* What a cell's value sorts as: an empty value last whichever way, a
   * number as a number, a date as a date, anything else as text. */
  function sortValue(v) {
    if (v == null) return { kind: 0, v: "" };
    if (typeof v === "number") return isNaN(v) ? { kind: 0, v: "" } : { kind: 2, v: v };
    var s = String(v).trim();
    if (!s || s === "—" || s === "-") return { kind: 0, v: "" };
    if (NUM_RE.test(s)) {
      var n = parseFloat(s.replace(/[^\d.\-+]/g, ""));
      if (!isNaN(n)) return { kind: 2, v: n };
    }
    if (DATE_RE.test(s)) {
      var t = Date.parse(s.length === 19 ? s.replace(" ", "T") + "Z" : s);
      if (!isNaN(t)) return { kind: 3, v: t };
    }
    return { kind: 1, v: s.toLowerCase() };
  }

  function compareValues(a, b) {
    var x = sortValue(a), y = sortValue(b);
    if (x.kind === 0 || y.kind === 0) return x.kind === y.kind ? 0 : (x.kind === 0 ? 1 : -1);
    if (x.kind !== y.kind) return x.kind - y.kind;
    if (x.kind === 1) return x.v.localeCompare(y.v, undefined, { numeric: true });
    return x.v < y.v ? -1 : x.v > y.v ? 1 : 0;
  }

  /* Sort items by the keys, using get(item, col) for each value. Stable; an
   * empty value stays last in both directions. */
  function sortBy(items, keys, get) {
    var indexed = items.map(function (it, i) { return { it: it, i: i }; });
    indexed.sort(function (a, b) {
      for (var k = 0; k < keys.length; k++) {
        var va = get(a.it, keys[k].col), vb = get(b.it, keys[k].col);
        var ea = sortValue(va).kind === 0, eb = sortValue(vb).kind === 0;
        if (ea !== eb) return ea ? 1 : -1;
        var c = compareValues(va, vb);
        if (c) return keys[k].dir === "desc" ? -c : c;
      }
      return a.i - b.i;
    });
    return indexed.map(function (x) { return x.it; });
  }

  /* The keys after a click on col; shift adds or reverses a further key. */
  function nextSort(keys, col, shift) {
    keys = (keys || []).map(function (k) { return { col: k.col, dir: k.dir }; });
    var at = -1;
    for (var i = 0; i < keys.length; i++) if (keys[i].col === col) at = i;
    if (shift) {
      if (at >= 0) keys[at].dir = keys[at].dir === "asc" ? "desc" : "asc";
      else keys.push({ col: col, dir: "asc" });
      return keys;
    }
    if (keys.length === 1 && at === 0) return [{ col: col, dir: keys[0].dir === "asc" ? "desc" : "asc" }];
    return [{ col: col, dir: "asc" }];
  }

  /* The sort in words, for the status line: "Name ▲, then Members ▼". */
  function describeSort(keys, labels) {
    return keys.map(function (k, i) {
      return (i ? "then " : "") + (labels[k.col] || k.col) + (k.dir === "asc" ? " ▲" : " ▼");
    }).join(", ");
  }

  /* The keys as one query value for a server: "name:asc,type:desc". */
  function sortParam(keys) {
    return keys.map(function (k) { return k.col + ":" + k.dir; }).join(",");
  }

  function load(key) {
    if (!key) return {};
    try { return JSON.parse(root.localStorage.getItem(STORE + key) || "{}") || {}; } catch (_) { return {}; }
  }
  function save(key, data) {
    if (!key) return;
    try { root.localStorage.setItem(STORE + key, JSON.stringify(data)); } catch (_) { /* memory only */ }
  }

  // --- the DOM part --------------------------------------------------------------

  var cssDone = false;
  function injectCss() {
    // The shared stylesheet is grid.css; this is the minimum that keeps a page
    // which forgot it usable (handles placed, cursor, the indicator).
    if (cssDone || !root.document) return;
    cssDone = true;
    var tag = root.document.createElement("style");
    tag.setAttribute("data-cbm-grid", "1");
    tag.textContent = ".cbm-grid th{position:relative}.cbm-grid__handle{position:absolute;top:0;right:-4px;width:9px;height:100%;cursor:col-resize;z-index:2}";
    (root.document.head || root.document.documentElement).appendChild(tag);
  }

  function enhance(table, opts) {
    opts = opts || {};
    injectCss();
    var doc = root.document;
    var stored = load(opts.key);
    var state = {
      keys: stored.sort || opts.sort || [],
      widths: stored.widths || {},
    };
    table.classList.add("cbm-grid");

    var status = doc.createElement("div");
    status.className = "cbm-grid__status";
    var statusText = doc.createElement("span");
    var clearBtn = doc.createElement("button"); clearBtn.type = "button"; clearBtn.className = "cbm-grid__link"; clearBtn.textContent = "Clear sort";
    var resetBtn = doc.createElement("button"); resetBtn.type = "button"; resetBtn.className = "cbm-grid__link"; resetBtn.textContent = "Reset columns";
    status.appendChild(statusText); status.appendChild(clearBtn); status.appendChild(resetBtn);
    var host = opts.statusAfter || (table.parentElement && /overflow|tablebox|gridbox/.test(table.parentElement.className) ? table.parentElement : table);
    host.insertAdjacentElement("afterend", status);

    function heads() { return Array.prototype.slice.call(table.querySelectorAll("thead th")); }
    function colOf(th, i) { return th.getAttribute("data-col") || String(i); }
    function sortable(th) { return th.getAttribute("data-sortable") !== "false" && !th.classList.contains("cbm-grid__nosort"); }
    function labels() {
      var out = {};
      heads().forEach(function (th, i) { out[colOf(th, i)] = (th.getAttribute("data-label") || th.textContent).replace(/[▲▼]\d*/g, "").trim(); });
      return out;
    }

    function persist() { save(opts.key, { sort: state.keys, widths: state.widths }); }

    function paintStatus() {
      var hasWidths = Object.keys(state.widths).length > 0;
      statusText.textContent = state.keys.length ? "Sorted by " + describeSort(state.keys, labels()) + "." : "";
      clearBtn.hidden = !state.keys.length || !!opts.fixedSort;
      resetBtn.hidden = !hasWidths;
      status.hidden = !state.keys.length && !hasWidths;
    }

    function paintHeads() {
      heads().forEach(function (th, i) {
        var col = colOf(th, i);
        var old = th.querySelector(".cbm-grid__ind"); if (old) old.remove();
        th.removeAttribute("aria-sort");
        var at = -1;
        for (var k = 0; k < state.keys.length; k++) if (state.keys[k].col === col) at = k;
        if (sortable(th)) {
          th.classList.add("cbm-grid__sortable");
          if (!th.hasAttribute("tabindex")) th.tabIndex = 0;
        }
        if (at >= 0) {
          var ind = doc.createElement("span");
          ind.className = "cbm-grid__ind";
          ind.textContent = (state.keys[at].dir === "asc" ? "▲" : "▼") + (state.keys.length > 1 ? String(at + 1) : "");
          th.appendChild(ind);
          if (at === 0) th.setAttribute("aria-sort", state.keys[0].dir === "asc" ? "ascending" : "descending");
        }
      });
    }

    function sortRows() {
      if (opts.onSort || !state.keys.length) return;
      var tb = table.tBodies[0];
      if (!tb) return;
      var index = {};
      heads().forEach(function (th, i) { index[colOf(th, i)] = i; });
      var rows = Array.prototype.slice.call(tb.rows);
      var sorted = sortBy(rows, state.keys, function (tr, col) {
        var td = tr.cells[index[col]];
        if (!td) return "";
        return td.hasAttribute("data-sort") ? td.getAttribute("data-sort") : td.textContent;
      });
      sorted.forEach(function (tr) { tb.appendChild(tr); });
    }

    function applySort(keys, quiet) {
      state.keys = keys;
      persist();
      paintHeads();
      paintStatus();
      if (opts.onSort) { if (!quiet) opts.onSort(state.keys.slice()); }
      else sortRows();
    }

    // --- widths ---------------------------------------------------------------

    // Fixed layout with every column but the last at its own width; the last
    // column takes whatever room is left, so the grid still fills its box and
    // the browser never spreads spare width over the columns someone sized.
    function lastIndex() { return heads().length - 1; }
    function layout() {
      var hs = heads(), sum = 0;
      hs.forEach(function (th, i) {
        var col = colOf(th, i);
        th.style.boxSizing = "border-box";   // widths are measured and set as the outer width
        if (i === hs.length - 1) { th.style.width = state.widths[col] ? state.widths[col] + "px" : ""; sum += state.widths[col] || 120; return; }
        th.style.width = Math.round(state.widths[col]) + "px";
        sum += state.widths[col];
      });
      table.style.tableLayout = "fixed";
      table.style.width = "100%";
      table.style.minWidth = Math.round(sum) + "px";
    }

    function freeze() {
      // The first resize records every column at its current width, so moving
      // one edge never reflows the others.
      if (table.style.tableLayout === "fixed") return;
      heads().forEach(function (th, i) {
        var col = colOf(th, i);
        if (!state.widths[col] && i !== lastIndex()) state.widths[col] = Math.round(th.getBoundingClientRect().width);
      });
      layout();
    }

    function setWidth(th, col, w) {
      w = Math.max(48, Math.round(w));
      freeze();
      state.widths[col] = w;
      layout();
    }

    function fit(th, col) {
      // Measure the widest cell with the column released for a moment.
      var i = heads().indexOf(th);
      var cells = [th].concat(Array.prototype.slice.call(table.querySelectorAll("tbody tr")).map(function (tr) { return tr.cells[i]; }).filter(Boolean));
      var widest = 0;
      cells.forEach(function (c) {
        var probe = doc.createElement("span");
        probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap;font:inherit;";
        probe.textContent = c.textContent;
        c.appendChild(probe);
        var cs = root.getComputedStyle(c);
        widest = Math.max(widest, probe.getBoundingClientRect().width + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + 18);
        probe.remove();
      });
      setWidth(th, col, Math.min(widest, 900));
      persist(); paintStatus();
    }

    function addHandles() {
      heads().forEach(function (th, i) {
        if (th.querySelector(".cbm-grid__handle")) return;
        var col = colOf(th, i);
        var h = doc.createElement("span");
        h.className = "cbm-grid__handle";
        h.setAttribute("role", "separator");
        h.setAttribute("aria-orientation", "vertical");
        h.setAttribute("aria-label", "Resize the " + (th.textContent.trim() || "column") + " column");
        h.tabIndex = 0;
        h.addEventListener("click", function (e) { e.stopPropagation(); });
        h.addEventListener("dblclick", function (e) { e.stopPropagation(); e.preventDefault(); fit(th, col); });
        h.addEventListener("keydown", function (e) {
          if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
          e.preventDefault(); e.stopPropagation();
          setWidth(th, col, th.getBoundingClientRect().width + (e.key === "ArrowRight" ? 16 : -16));
          persist(); paintStatus();
        });
        h.addEventListener("pointerdown", function (e) {
          e.preventDefault(); e.stopPropagation();
          var startX = e.clientX, startW = th.getBoundingClientRect().width;
          h.classList.add("is-dragging");
          if (h.setPointerCapture) { try { h.setPointerCapture(e.pointerId); } catch (_) {} }
          function move(ev) { setWidth(th, col, startW + (ev.clientX - startX)); }
          function up() {
            h.classList.remove("is-dragging");
            h.removeEventListener("pointermove", move);
            h.removeEventListener("pointerup", up);
            h.removeEventListener("pointercancel", up);
            persist(); paintStatus();
          }
          h.addEventListener("pointermove", move);
          h.addEventListener("pointerup", up);
          h.addEventListener("pointercancel", up);
        });
        th.appendChild(h);
      });
    }

    function applyStoredWidths() {
      var cols = Object.keys(state.widths);
      table.style.tableLayout = ""; table.style.width = ""; table.style.minWidth = "";
      heads().forEach(function (th) { th.style.width = ""; });
      if (!cols.length) return;
      // Columns nobody sized keep the width the browser gives them now.
      freeze();
    }

    // --- headings: click and keyboard ---------------------------------------

    function onHeadClick(e) {
      var th = e.target.closest && e.target.closest("thead th");
      if (!th || !table.contains(th) || !sortable(th)) return;
      if (e.target.closest(".cbm-grid__handle")) return;
      var i = heads().indexOf(th);
      applySort(nextSort(state.keys, colOf(th, i), e.shiftKey));
    }
    table.addEventListener("click", onHeadClick);
    table.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var th = e.target.closest && e.target.closest("thead th");
      if (!th || e.target !== th) return;
      e.preventDefault();
      onHeadClick({ target: th, shiftKey: e.shiftKey });
    });
    clearBtn.addEventListener("click", function () { applySort(opts.sort ? opts.sort.slice() : []); });
    resetBtn.addEventListener("click", function () { state.widths = {}; persist(); applyStoredWidths(); paintStatus(); });

    function refresh() {
      addHandles();
      paintHeads();
      paintStatus();
      sortRows();
    }

    addHandles();
    applyStoredWidths();
    paintHeads();
    paintStatus();
    sortRows();

    return {
      refresh: refresh,
      keys: function () { return state.keys.slice(); },
      setSort: function (keys, quiet) { applySort(keys || [], quiet); },
      sortParam: function () { return sortParam(state.keys); },
      status: status
    };
  }

  root.CBMGrid = {
    enhance: enhance,
    sortBy: sortBy,
    compare: compareValues,
    nextSort: nextSort,
    describeSort: describeSort,
    sortParam: sortParam
  };
})(typeof window !== "undefined" ? window : globalThis);
