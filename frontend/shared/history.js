/* The History panel — one record's changes, newest first (mentor login
 * integrity plan § 4.5; the server half is core/history.py).
 *
 *   var h = CBMHistory.mount(panelEl, { key: "mentoradmin.history" });
 *   h.load("/mentoradmin/api/mentors/" + id + "/history");   // on tab open
 *
 * One line per change: when (this browser's local time), who (a person, or
 * "System" and the job), where (which application, or "In the CRM
 * directly") and what, in one sentence. A line that carries values opens to
 * show each field's old and new value. Filters: date range, person, kind of
 * change — all in the browser, over what the server sent. The table uses the
 * shared grid. The activity page (step 6) uses the same renderer with a
 * "Record" column and a CSV export (toCsv).
 *
 * The server never sends a record id, raw data or a secret; this file only
 * draws what it is given. */
(function (root) {
  "use strict";

  // --- pure helpers (no DOM; tested under node) -------------------------------

  /* Lines passing the filters. f = {from, to (YYYY-MM-DD, local days), who, kind}. */
  function filterLines(lines, f) {
    f = f || {};
    var from = f.from ? localDayStart(f.from) : null;
    var to = f.to ? localDayStart(f.to) + 86400000 : null;
    return (lines || []).filter(function (ln) {
      var t = Date.parse(ln.at);
      if (from !== null && !(t >= from)) return false;
      if (to !== null && !(t < to)) return false;
      if (f.who && personOf(ln) !== f.who) return false;
      if (f.kind && (ln.kind || "") !== f.kind) return false;
      return true;
    });
  }

  function localDayStart(ymd) {
    var p = String(ymd).split("-").map(Number);
    return new Date(p[0], (p[1] || 1) - 1, p[2] || 1).getTime();
  }

  /* "Jane Doe", or "System — nightly clean-up". */
  function personOf(ln) {
    return ln.job ? (ln.who + " — " + ln.job) : (ln.who || "");
  }

  function distinct(lines, fn) {
    var seen = {}, out = [];
    (lines || []).forEach(function (ln) {
      var v = fn(ln);
      if (v && !seen[v]) { seen[v] = true; out.push(v); }
    });
    return out.sort(function (a, b) { return a.localeCompare(b); });
  }

  function whenText(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric",
                                         hour: "numeric", minute: "2-digit" });
  }

  function csvCell(v) {
    var s = v == null ? "" : String(v);
    // A leading = + - @ would run as a formula in a spreadsheet.
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  /* The lines as CSV text, one row per field change (a line with no
   * changes is one row). Columns: When (UTC), Who, Where, Record, What,
   * Kind, Field, Old value, New value. */
  function toCsv(lines) {
    var head = ["When (UTC)", "Who", "Where", "Record", "What", "Kind", "Field", "Old value", "New value"];
    var rows = [head.map(csvCell).join(",")];
    (lines || []).forEach(function (ln) {
      var base = [ln.at, personOf(ln), ln.where, ln.record || "", ln.what, ln.kind];
      var ch = ln.changes && ln.changes.length ? ln.changes : [null];
      ch.forEach(function (c) {
        var cells = base.concat(c ? [c.field, c.from == null ? "" : c.from, c.to == null ? "" : c.to] : ["", "", ""]);
        rows.push(cells.map(csvCell).join(","));
      });
    });
    return rows.join("\r\n") + "\r\n";
  }

  // --- the panel ----------------------------------------------------------------

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function changesTable(ln) {
    var wrap = el("div", "cbm-hist__changes");
    if (!ln.valuesRecorded) {
      wrap.appendChild(el("p", "cbm-hist__note",
        "Old and new values were not recorded for this change — only which fields changed."));
    }
    // Not a nested <table>: the shared grid would take its headings and
    // rows for its own (review 5a). A three-column CSS grid of cells.
    var t = el("div", "cbm-hist__vals"); t.setAttribute("role", "table");
    function row(cells, head) {
      var r = el("div", "cbm-hist__vrow"); r.setAttribute("role", "row");
      cells.forEach(function (c) {
        var d = el("div", (head ? "cbm-hist__vhead" : "") + (c[1] ? " " + c[1] : ""), c[0]);
        d.setAttribute("role", head ? "columnheader" : "cell");
        r.appendChild(d);
      });
      t.appendChild(r);
    }
    row([["Field"], ["Old value"], ["New value"]], true);
    ln.changes.forEach(function (c) {
      var known = "to" in c;
      row([
        [c.field],
        [!known || !c.hasFrom ? "—" : (c.from === "" ? "blank" : c.from), known && c.hasFrom && c.from === "" ? "cbm-hist__blank" : ""],
        [!known ? "—" : (c.to === "" ? "blank" : c.to), known && c.to === "" ? "cbm-hist__blank" : ""],
      ], false);
    });
    wrap.appendChild(t);
    return wrap;
  }

  function whatCell(ln) {
    var td = el("td", "cbm-hist__what");
    if (ln.outcome && ln.outcome !== "Success") {
      td.appendChild(el("span", "cbm-hist__outcome", ln.outcome === "Failed" ? "Did not complete" : "Partly done"));
    }
    if (ln.changes && ln.changes.length) {
      var det = el("details");
      det.appendChild(el("summary", null, ln.what));
      det.appendChild(changesTable(ln));
      td.appendChild(det);
    } else {
      td.appendChild(document.createTextNode(ln.what));
    }
    return td;
  }

  function mount(panel, opts) {
    opts = opts || {};
    var withRecord = !!opts.withRecord;
    panel.classList.add("cbm-hist");
    panel.innerHTML = "";
    var bar = el("div", "cbm-hist__filters");
    function field(label, input) {
      var l = el("label", "cbm-hist__f"); l.appendChild(el("span", null, label)); l.appendChild(input);
      bar.appendChild(l); return input;
    }
    var fFrom = field("From", el("input")); fFrom.type = "date";
    var fTo = field("To", el("input")); fTo.type = "date";
    var fWho = field("Person", el("select"));
    var fKind = field("Kind of change", el("select"));
    var clear = el("button", "cbm-hist__clear", "Clear filters"); clear.type = "button";
    bar.appendChild(clear);
    if (opts.extraControls) opts.extraControls(bar);
    var msg = el("p", "cbm-hist__msg", "");
    var notes = el("div", "cbm-hist__notices");
    var count = el("p", "cbm-hist__count", "");
    var table = el("table", "cbm-hist__table");
    var cols = [["when", "When"], ["who", "Who"], ["where", "Where"]];
    if (withRecord) cols.push(["record", "Record"]);
    cols.push(["what", "What"], ["kind", "Kind"]);
    var htr = el("tr");
    cols.forEach(function (c) {
      var th = el("th", null, c[1]); th.scope = "col"; th.dataset.col = c[0]; htr.appendChild(th);
    });
    var thead = el("thead"); thead.appendChild(htr); table.appendChild(thead);
    var tbody = el("tbody"); table.appendChild(tbody);
    table.hidden = true;
    panel.appendChild(bar); panel.appendChild(notes); panel.appendChild(msg);
    panel.appendChild(count); panel.appendChild(table);
    var grid = root.CBMGrid ? root.CBMGrid.enhance(table, { key: opts.key || "history",
      sort: [{ col: "when", dir: "desc" }] }) : null;

    var state = { lines: [], url: null };

    function fillSelect(sel, values, allLabel) {
      var keep = sel.value;
      sel.innerHTML = "";
      var o = el("option", null, allLabel); o.value = ""; sel.appendChild(o);
      values.forEach(function (v) { var op = el("option", null, v); op.value = v; sel.appendChild(op); });
      sel.value = values.indexOf(keep) >= 0 ? keep : "";
    }

    function render() {
      var shown = filterLines(state.lines, { from: fFrom.value, to: fTo.value,
                                             who: fWho.value, kind: fKind.value });
      tbody.innerHTML = "";
      shown.forEach(function (ln) {
        var tr = el("tr");
        var w = el("td", "cbm-hist__when", whenText(ln.at)); w.dataset.sort = ln.at; tr.appendChild(w);
        tr.appendChild(el("td", null, personOf(ln)));
        tr.appendChild(el("td", ln.where === "In the CRM directly" ? "cbm-hist__crm" : null, ln.where));
        if (withRecord) tr.appendChild(el("td", null, ln.record || ""));
        tr.appendChild(whatCell(ln));
        tr.appendChild(el("td", null, ln.kind || ""));
        tbody.appendChild(tr);
      });
      var filtered = shown.length !== state.lines.length;
      count.textContent = state.lines.length
        ? (filtered ? shown.length + " of " + state.lines.length + " changes shown." : state.lines.length + (state.lines.length === 1 ? " change." : " changes."))
        : "";
      table.hidden = !shown.length;
      msg.textContent = state.lines.length && !shown.length ? "No change matches these filters." :
                        (!state.lines.length && state.loaded ? (opts.emptyText || "No changes recorded yet.") : "");
      if (grid) grid.refresh();
      if (opts.onRender) opts.onRender(shown);
    }

    function notice(text) { notes.appendChild(el("p", "cbm-hist__notice", text)); }

    [fFrom, fTo, fWho, fKind].forEach(function (i) { i.addEventListener("change", render); });
    clear.addEventListener("click", function () {
      fFrom.value = ""; fTo.value = ""; fWho.value = ""; fKind.value = ""; render();
    });

    var ticket = 0;  // only the latest load may draw (two quick clicks)
    async function load(url, force) {
      if (!force && url === state.url && state.loaded) return;
      var mine = ++ticket;
      state.url = url; state.loaded = false; state.lines = [];
      notes.innerHTML = ""; msg.textContent = "Loading…"; table.hidden = true; count.textContent = "";
      try {
        var p = (root.CBMBusy ? root.CBMBusy.fetch(url) : fetch(url));
        if (root.CBMBusy && root.CBMBusy.loading) root.CBMBusy.loading(panel, p);
        var r = await p;
        var body = await r.json().catch(function () { return {}; });
        if (mine !== ticket) return;
        if (r.status === 401) {  // the portal signs in and comes back
          root.location.href = "/?next=" + encodeURIComponent(root.location.pathname + root.location.search);
          return;
        }
        if (!r.ok) throw new Error((body && body.detail) || ("Could not load the history (" + r.status + ")."));
        state.lines = body.lines || [];
        state.loaded = true;
        if (body.actionHistory === false) notice("The applications' own history could not be read just now, so only the CRM's own record changes are listed.");
        if (body.crmNotes === false) notice("The CRM's own record changes could not be read just now, so only the applications' history is listed.");
        if (body.tracked === false && !withRecord) notice("Changes made in the CRM's own screens are listed only for fields the CRM tracks, and this record type has none yet.");
        if (body.truncated) notice("Only the most recent changes are listed; narrow the dates to see older ones.");
        if (body.notice) notice(body.notice);
        fillSelect(fWho, distinct(state.lines, personOf), "Everyone");
        fillSelect(fKind, distinct(state.lines, function (l) { return l.kind; }), "Every kind");
        render();
      } catch (e) {
        if (mine !== ticket) return;
        state.loaded = false; state.url = null;
        msg.textContent = e.message;
      }
    }

    return { load: load, render: render, lines: function () { return state.lines; },
             filtered: function () { return filterLines(state.lines, { from: fFrom.value, to: fTo.value, who: fWho.value, kind: fKind.value }); } };
  }

  root.CBMHistory = { mount: mount, filterLines: filterLines, personOf: personOf,
                      toCsv: toCsv, whenText: whenText };
})(typeof window !== "undefined" ? window : globalThis);
