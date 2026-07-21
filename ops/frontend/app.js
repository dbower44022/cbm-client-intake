/* Submission Admin console — vanilla JS. Sign-in happens once at the portal
   (/), which sends the user back here after login.

   Rebuilt 2026-07-19 (Doug's spec): full-height grid with sortable +
   drag-resizable columns, center search, alternating rows; a sessions-style
   tabbed detail view (Overview with facts rail + editable staff notes +
   the email conversation with the submitter; Details with the raw
   payload/progress/error; Communications with the full thread + compose
   via the shared quick-mail widget). */
(function () {
  "use strict";

  var API = "/ops/api";
  var STATUSES = ["pending", "processing", "retry", "completed", "needs_attention", "held_honeypot", "held_review", "discarded"];
  // info-email = an inbound email to the shared info@ mailbox, captured by the
  // worker's poller (held_review until staff Approve or Discard it).
  var FORMS = ["client-intake", "volunteer", "info-request", "partner", "sponsor", "info-email"];
  // Re-drive includes discarded so a mistaken discard can be undone (re-queued).
  var REDRIVABLE = { held_honeypot: 1, held_review: 1, needs_attention: 1, retry: 1, discarded: 1 };
  // Discard resolves a stuck row that can't be re-driven (e.g. a bad payload).
  var DISCARDABLE = { held_honeypot: 1, held_review: 1, needs_attention: 1, retry: 1 };

  // resolution defaults to "open": the grid is a work queue ("is anyone
  // still waiting on us?"), resolved rows are one select away.
  var state = { status: "", form: "", search: "", resolution: "open" };
  var rows = [];                 // the loaded submissions
  var sortKey = null, sortDir = 1;
  var colWidths = null;          // frozen column widths after the first grip drag
  var config = null;             // /session payload (crmUrl, commsEnabled)
  var current = null;            // the open submission row (full detail)
  var messages = null;           // cached conversation for the open submission
  var messagesReason = null;     // why the conversation is unavailable (if it is)

  function $(id) { return document.getElementById(id); }
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    // Timeout-wrapped (CBMBusy.fetch): a hung request ends in a readable
    // message instead of silence. Falls back to plain fetch if busy.js
    // somehow did not load.
    var resp = await (window.CBMBusy && CBMBusy.fetch
      ? CBMBusy.fetch(API + path, opts)
      : fetch(API + path, opts));
    var data = null;
    try { data = await resp.json(); } catch (e) { /* none */ }
    if (!resp.ok) {
      var msg = (data && data.detail) || ("Request failed (" + resp.status + ")");
      var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function showLogin() { location.href = "/?next=" + encodeURIComponent("/ops/"); }
  function showMessage(text) { hide($("dashView")); hide($("detailView")); $("msgText").textContent = text; show($("msgView")); }
  function bootFail(e) {
    if (e && e.status === 401) { showLogin(); return; }
    if (e && e.status === 403) { showMessage(e.message); return; }
    showMessage("The server isn't responding right now. Please try again in a moment.");
  }
  function notice(elId, text, kind) {
    var n = $(elId); n.textContent = text;
    n.className = "ops__notice " + (kind === "error" ? "is-error" : "is-success");
    show(n);
  }
  function clearNotice(elId) { hide($(elId)); }

  // Minimal HTML sanitizer for rendering cleaned email bodies (the server's
  // clean_email output; scripts/styles/handlers stripped again client-side).
  function sanitizeHtml(html) {
    var tmp = document.createElement("div"); tmp.innerHTML = html || "";
    Array.prototype.forEach.call(tmp.querySelectorAll("script,style,iframe,object,embed,link,meta"), function (n) { n.remove(); });
    Array.prototype.forEach.call(tmp.querySelectorAll("*"), function (n) {
      Array.prototype.slice.call(n.attributes).forEach(function (a) {
        var name = a.name.toLowerCase(), val = (a.value || "").replace(/\s/g, "").toLowerCase();
        if (name.indexOf("on") === 0) n.removeAttribute(a.name);
        else if ((name === "href" || name === "src") && val.indexOf("javascript:") === 0) n.removeAttribute(a.name);
      });
    });
    return tmp.innerHTML;
  }

  function fmtDate(s) {
    if (!s) return "—";
    var d = new Date(s.indexOf("T") < 0 ? s.replace(" ", "T") + "Z" : s);
    return isNaN(d) ? s : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function badgeEl(status) {
    var b = document.createElement("span");
    b.className = "status-badge status-" + status;
    b.textContent = (status || "").replace(/_/g, " ");
    return b;
  }

  // Two-step confirm on a button (product convention: no browser dialogs).
  function twoStep(btn, armedText, fn) {
    var armed = false;
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      if (!armed) { armed = true; btn.dataset.orig = btn.textContent; btn.textContent = armedText; return; }
      armed = false; btn.textContent = btn.dataset.orig;
      fn();
    });
    btn.addEventListener("blur", function () {
      if (armed) { armed = false; btn.textContent = btn.dataset.orig; }
    });
  }

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) {}
    location.href = "/";
  });
  $("refreshBtn").addEventListener("click", loadData);
  // Null-guarded: a browser holding yesterday's cached index.html (no
  // resolvedFilter element) must not die on boot with the new app.js.
  var _rf = $("resolvedFilter");
  if (_rf) _rf.addEventListener("change", function () { state.resolution = this.value; renderTable(); });
  $("statusFilter").addEventListener("change", function () { state.status = this.value; loadData(); });
  $("formFilter").addEventListener("change", function () { state.form = this.value; loadData(); });
  $("searchBox").addEventListener("input", function () { state.search = this.value.trim().toLowerCase(); renderTable(); });
  $("backBtn").addEventListener("click", function () { hide($("detailView")); show($("dashView")); loadData(); });

  function fillSelect(sel, values, placeholder) {
    sel.innerHTML = "";
    sel.appendChild(new Option(placeholder, ""));
    values.forEach(function (v) { sel.appendChild(new Option(v.replace(/_/g, " "), v)); });
  }

  // --- list -----------------------------------------------------------------
  async function loadData() {
    clearNotice("notice");
    show($("loadingState")); hide($("subTable")); hide($("emptyState"));
    var qs = [];
    if (state.status) qs.push("status=" + encodeURIComponent(state.status));
    if (state.form) qs.push("form=" + encodeURIComponent(state.form));
    try {
      var data = await api("/submissions" + (qs.length ? "?" + qs.join("&") : ""));
      rows = data.submissions || [];
      renderCounts(data.counts || {});
      renderTable();
      loadReplyStates();
      api("/metrics").then(renderMetrics).catch(function () {
        $("metrics").textContent = "metrics unavailable";
        $("metrics").className = "ops__metrics is-muted";
      });
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("notice", e.message, "error");
    } finally { hide($("loadingState")); }
  }

  function renderMetrics(m) {
    var bits = ["backlog: " + (m.backlog || 0), "needs attention: " + (m.needsAttention || 0)];
    if (m.oldestPendingAgeSeconds != null) bits.push("oldest pending: " + Math.round(m.oldestPendingAgeSeconds / 60) + " min");
    if (m.avgLatencySeconds != null) bits.push("avg delivery: " + Math.round(m.avgLatencySeconds) + "s");
    $("metrics").textContent = bits.join("  ·  ");
    $("metrics").className = "ops__metrics" + (m.needsAttention ? " is-alert" : "");
  }

  function renderCounts(counts) {
    var box = $("counts"); box.innerHTML = "";
    var total = 0;
    STATUSES.forEach(function (s) {
      var n = counts[s] || 0; total += n;
      if (!n) return;
      var chip = document.createElement("span");
      chip.className = "count-chip status-" + s;
      chip.textContent = s.replace(/_/g, " ") + ": " + n;
      box.appendChild(chip);
    });
    var t = document.createElement("span"); t.className = "count-chip"; t.textContent = "total: " + total;
    box.appendChild(t);
    // Open vs resolved (the staff workflow split), from the loaded rows.
    var resolved = rows.filter(function (r) { return r.resolved_at; }).length;
    var o = document.createElement("span"); o.className = "count-chip chip-open";
    o.textContent = "open: " + (rows.length - resolved); box.appendChild(o);
    if (resolved) {
      var rc = document.createElement("span"); rc.className = "count-chip chip-resolved";
      rc.textContent = "resolved: " + resolved; box.appendChild(rc);
    }
  }

  var COLUMNS = [
    { key: "id", label: "Reference", get: function (r) { return (r.id || "").slice(0, 8); } },
    { key: "form_slug", label: "Form" },
    { key: "status", label: "Status" },
    { key: "email", label: "Submitter" },
    { key: "_reply", label: "Reply", sortKey: "_replyState" },
    { key: "received_at", label: "Received", fmt: fmtDate },
    { key: "attempt_count", label: "Attempts", cls: "num" },
    { key: "last_error", label: "Last error", cls: "err",
      get: function (r) { return r.last_error ? r.last_error.slice(0, 80) : ""; } },
    { key: "_actions", label: "", sort: false },
  ];

  function rowMatches(r) {
    if (state.resolution === "open" && r.resolved_at) return false;
    if (state.resolution === "resolved" && !r.resolved_at) return false;
    if (!state.search) return true;
    var hay = [r.id, r.form_slug, r.status, r.email, r.last_error, r.notes, fmtDate(r.received_at)]
      .filter(Boolean).join(" ").toLowerCase();
    return hay.indexOf(state.search) >= 0;
  }

  function sortedRows(list) {
    if (!sortKey) return list;
    return list.slice().sort(function (a, b) {
      var x = a[sortKey], y = b[sortKey];
      if (x == null || x === "") return y == null || y === "" ? 0 : 1;
      if (y == null || y === "") return -1;
      if (typeof x === "number" && typeof y === "number") return (x - y) * sortDir;
      return String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" }) * sortDir;
    });
  }

  function renderTable() {
    var head = $("subHead"); head.innerHTML = "";
    var htr = document.createElement("tr");
    COLUMNS.forEach(function (c, i) {
      var th = document.createElement("th");
      if (c.cls) th.className = c.cls;
      th.textContent = c.label;
      if (colWidths && colWidths[i]) th.style.width = colWidths[i] + "px";
      if (c.sort !== false) {
        var sk = c.sortKey || c.key;
        if (sortKey === sk) {
          var ind = document.createElement("span"); ind.textContent = sortDir > 0 ? " ▲" : " ▼";
          th.appendChild(ind);
          th.setAttribute("aria-sort", sortDir > 0 ? "ascending" : "descending");
        }
        th.addEventListener("click", function () {
          if (sortKey === sk) { sortDir = -sortDir; }
          else { sortKey = sk; sortDir = sk === "received_at" || sk === "attempt_count" ? -1 : 1; }
          renderTable();
        });
      }
      // Drag grip: first drag freezes the table layout so widths stick.
      var grip = document.createElement("span"); grip.className = "grip";
      grip.addEventListener("pointerdown", function (e) {
        e.preventDefault(); e.stopPropagation();
        var table = $("subTable");
        if (!colWidths) {
          colWidths = Array.prototype.map.call(head.querySelectorAll("th"), function (h) {
            return h.getBoundingClientRect().width;
          });
          table.style.tableLayout = "fixed";
        }
        var startX = e.clientX, startW = colWidths[i];
        function move(ev) {
          colWidths[i] = Math.max(48, startW + (ev.clientX - startX));
          head.querySelectorAll("th")[i].style.width = colWidths[i] + "px";
          ev.preventDefault();
        }
        function up() {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          window.removeEventListener("pointercancel", up);
        }
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", up);
      });
      grip.addEventListener("click", function (e) { e.stopPropagation(); });
      th.appendChild(grip);
      htr.appendChild(th);
    });
    head.appendChild(htr);

    var list = sortedRows(rows.filter(rowMatches));
    var body = $("subBody"); body.innerHTML = "";
    if (!list.length) {
      hide($("subTable"));
      $("emptyState").textContent = state.search ? "No submissions match your search." : "No submissions match.";
      show($("emptyState"));
      return;
    }
    hide($("emptyState"));
    list.forEach(function (r) { body.appendChild(buildRow(r)); });
    show($("subTable"));
  }

  function buildRow(r) {
    var tr = document.createElement("tr");
    tr.addEventListener("click", function () { openDetail(r.id); });

    COLUMNS.forEach(function (c) {
      var td = document.createElement("td");
      if (c.cls) td.className = c.cls;
      if (c.key === "id") {
        var link = document.createElement("button");
        link.type = "button"; link.className = "ref-link";
        link.textContent = (r.id || "").slice(0, 8);
        link.addEventListener("click", function (ev) { ev.stopPropagation(); openDetail(r.id); });
        td.appendChild(link);
      } else if (c.key === "status") {
        td.appendChild(badgeEl(r.status));
        if (r.resolved_at) {
          var rv = document.createElement("span"); rv.className = "resolved-chip";
          rv.textContent = "✓ resolved"; rv.title = "Resolved " + fmtDate(r.resolved_at) +
            (r.resolved_by ? " by " + r.resolved_by : "");
          td.appendChild(rv);
        }
      } else if (c.key === "_reply") {
        td.appendChild(replyCell(r));
      } else if (c.key === "_actions") {
        td.className = "actions";
        if (REDRIVABLE[r.status]) td.appendChild(redriveBtn(r, "notice"));
        if (DISCARDABLE[r.status]) td.appendChild(actionBtn("Discard", "Really discard?", function () { discard(r, "notice"); }));
      } else {
        var v = c.get ? c.get(r) : r[c.key];
        if (c.fmt) v = c.fmt(v);
        td.textContent = v == null || v === "" ? "—" : v;
      }
      tr.appendChild(td);
    });
    return tr;
  }

  // The awaiting-reply column: who spoke last with each OPEN submitter (2
  // Gmail calls per row server-side, so open rows only, capped at 30).
  // "reply owed" = their message is newest; "waiting" = ours is.
  function replyCell(r) {
    var s = document.createElement("span");
    var st = r._replyState;
    if (st === "owed") { s.className = "reply-owed"; s.textContent = "↳ reply owed"; }
    else if (st === "waiting") { s.className = "reply-waiting"; s.textContent = "waiting on them"; }
    else if (st === "none") { s.className = "is-muted"; s.textContent = "—"; }
    else if (st === "pending") { s.className = "is-muted"; s.textContent = "…"; }
    else { s.className = "is-muted"; s.textContent = ""; }
    return s;
  }

  async function loadReplyStates() {
    if (!config || config.commsEnabled === false) return;
    var open = rows.filter(function (r) { return !r.resolved_at && r.email; }).slice(0, 30);
    if (!open.length) return;
    open.forEach(function (r) { if (!r._replyState) r._replyState = "pending"; });
    renderTable();
    try {
      var res = await api("/replystates", {
        method: "POST", body: JSON.stringify({ ids: open.map(function (r) { return r.id; }) })
      });
      var states = (res && res.states) || {};
      rows.forEach(function (r) {
        if (states[r.id]) { r._replyState = states[r.id].state; r._replyDate = states[r.id].date || ""; }
        else if (r._replyState === "pending") { r._replyState = ""; }
      });
    } catch (e) {
      rows.forEach(function (r) { if (r._replyState === "pending") r._replyState = ""; });
    }
    renderTable();
  }

  function actionBtn(label, armedText, fn) {
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "cbm-button cbm-button--secondary row-btn";
    btn.textContent = label;
    twoStep(btn, armedText, fn);
    return btn;
  }

  // Re-drive, labelled for what it means on this row: approving a held
  // inbound email DELIVERS it (creates the CRM records) — same endpoint,
  // honest words.
  function redriveBtn(r, noticeEl) {
    var approve = r.form_slug === "info-email" && r.status === "held_review";
    return actionBtn(
      approve ? "Approve" : "Re-drive",
      approve ? "Create CRM records?" : "Re-drive?",
      function () { redrive(r, noticeEl); }
    );
  }

  async function redrive(r, noticeEl) {
    try {
      await api("/submissions/" + encodeURIComponent(r.id) + "/redrive", { method: "POST" });
      notice(noticeEl, "Re-queued " + r.id.slice(0, 8) + " — the worker will pick it up.", "success");
      if (noticeEl === "notice") loadData(); else refreshDetailRow();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(noticeEl, e.message, "error");
    }
  }

  async function discard(r, noticeEl) {
    try {
      await api("/submissions/" + encodeURIComponent(r.id) + "/discard", { method: "POST" });
      notice(noticeEl, "Discarded " + r.id.slice(0, 8) + ".", "success");
      if (noticeEl === "notice") loadData(); else refreshDetailRow();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(noticeEl, e.message, "error");
    }
  }

  // --- detail view ----------------------------------------------------------
  var TABS = [
    { key: "overview", label: "Overview" },
    { key: "details", label: "Details" },
    { key: "communications", label: "Communications" },
  ];

  function activateTab(key) {
    Array.prototype.forEach.call($("detailTabs").children, function (b) {
      var on = b.dataset.tab === key;
      b.classList.toggle("is-active", on); b.setAttribute("aria-selected", on);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".ops__panel"), function (p) {
      p.hidden = p.dataset.panel !== key;
    });
  }

  async function openDetail(id) {
    clearNotice("detailNotice");
    try { current = await api("/submissions/" + encodeURIComponent(id)); }
    catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("notice", e.message, "error"); return;
    }
    messages = null; messagesReason = null;
    hide($("dashView")); show($("detailView"));
    $("detailTitle").textContent = "Submission " + (current.id || "").slice(0, 8) + " — " + (current.form_slug || "");
    var badgeBox = $("detailBadge"); badgeBox.innerHTML = ""; badgeBox.appendChild(badgeEl(current.status));
    renderDetailActions();
    var tabs = $("detailTabs"); tabs.innerHTML = "";
    TABS.forEach(function (t) {
      var b = document.createElement("button");
      b.type = "button"; b.dataset.tab = t.key; b.textContent = t.label;
      b.setAttribute("role", "tab");
      b.addEventListener("click", function () { activateTab(t.key); });
      tabs.appendChild(b);
    });
    renderOverview();
    renderDetailsTab();
    renderComms();       // both surfaces render from the same fetch
    activateTab("overview");
    loadMessages();
    window.scrollTo(0, 0);
  }

  // Re-read the open submission after an action (status changed).
  async function refreshDetailRow() {
    if (!current) return;
    try {
      current = await api("/submissions/" + encodeURIComponent(current.id));
      var badgeBox = $("detailBadge"); badgeBox.innerHTML = ""; badgeBox.appendChild(badgeEl(current.status));
      renderDetailActions();
      renderOverview();
      renderDetailsTab();
    } catch (e) { /* keep the stale view; the list refresh will correct */ }
  }

  function renderDetailActions() {
    var box = $("detailActions"); box.innerHTML = "";
    // Resolve/Reopen: the staff workflow marker — single click, reversible.
    var rb = document.createElement("button");
    rb.type = "button"; rb.className = "cbm-button" + (current.resolved_at ? " cbm-button--secondary" : "");
    rb.textContent = current.resolved_at ? "Reopen" : "Mark resolved";
    rb.addEventListener("click", async function () {
      rb.disabled = true;
      try {
        await api("/submissions/" + encodeURIComponent(current.id) + "/resolved",
          { method: "PUT", body: JSON.stringify({ resolved: !current.resolved_at }) });
        notice("detailNotice", current.resolved_at ? "Reopened." : "Marked resolved.", "success");
        await refreshDetailRow();
        var row = rows.filter(function (r) { return r.id === current.id; })[0];
        if (row) { row.resolved_at = current.resolved_at; row.resolved_by = current.resolved_by; }
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        rb.disabled = false;
        notice("detailNotice", e.message, "error");
      }
    });
    box.appendChild(rb);
    if (REDRIVABLE[current.status]) box.appendChild(redriveBtn(current, "detailNotice"));
    if (DISCARDABLE[current.status]) box.appendChild(actionBtn("Discard", "Really discard?", function () { discard(current, "detailNotice"); }));
  }

  // Payload keys shown as curated facts (label + the payload field). Forms
  // share these names; anything else stays on the Details tab.
  var PAYLOAD_FACTS = [
    ["Name", function (p) { return [p.first_name, p.last_name].filter(Boolean).join(" "); }],
    ["Email", "email"],
    ["Phone", "phone"],
    ["Company", "company"],
    ["Website", "business_website"],
    ["How they heard", "how_did_you_hear"],
    ["Subject", "subject"],
    ["Message", "message"],
  ];

  function fact(label, value) {
    var row = document.createElement("div"); row.className = "ops__fact";
    var l = document.createElement("span"); l.className = "ops__fact-l"; l.textContent = label;
    var v = document.createElement("span"); v.className = "ops__fact-v";
    if (value instanceof Node) v.appendChild(value);
    else v.textContent = value == null || value === "" ? "—" : String(value);
    row.appendChild(l); row.appendChild(v);
    return row;
  }

  function renderOverview() {
    var box = $("ovFacts"); box.innerHTML = "";
    var p = current.payload || {};
    box.appendChild(fact("Reference", (current.id || "").slice(0, 8)));
    box.appendChild(fact("Form", current.form_slug));
    box.appendChild(fact("Status", badgeEl(current.status)));
    box.appendChild(fact("Received", fmtDate(current.received_at)));
    if (current.processed_at) box.appendChild(fact("Processed", fmtDate(current.processed_at)));
    box.appendChild(fact("Attempts", current.attempt_count || 0));
    if (current.resolved_at) {
      box.appendChild(fact("Resolved", fmtDate(current.resolved_at) +
        (current.resolved_by ? " by " + current.resolved_by : "")));
    }
    if (current.acted_by) box.appendChild(fact("Last acted by", current.acted_by));
    PAYLOAD_FACTS.forEach(function (f) {
      var label = f[0], src = f[1];
      var v = typeof src === "function" ? src(p) : p[src];
      if (v == null || v === "") return;
      if (label === "Email" && window.CBMQuickMail) {
        box.appendChild(fact(label, CBMQuickMail.emailLink(String(v))));
      } else {
        box.appendChild(fact(label, v));
      }
    });
    renderNotes();
  }

  // --- staff notes (view + inline edit; the Edit button is always visible) --
  function renderNotes() {
    var card = $("notesCard"); card.innerHTML = "";
    var head = document.createElement("div"); head.className = "ops__notes-head";
    var h = document.createElement("h3"); h.textContent = "Submission notes";
    var eb = document.createElement("button");
    eb.type = "button"; eb.className = "small-btn"; eb.textContent = "Edit";
    eb.addEventListener("click", editNotes);
    head.appendChild(h); head.appendChild(eb);
    card.appendChild(head);
    var body = document.createElement("div"); body.className = "ops__notes-body";
    var v = (current.notes || "").trim();
    if (v) { body.textContent = v; }
    else { body.className += " is-muted"; body.textContent = "No notes yet — click Edit to add triage notes for other admins."; }
    card.appendChild(body);
  }

  function editNotes() {
    var card = $("notesCard"); card.innerHTML = "";
    var head = document.createElement("div"); head.className = "ops__notes-head";
    var h = document.createElement("h3"); h.textContent = "Submission notes";
    head.appendChild(h); card.appendChild(head);
    var ta = document.createElement("textarea");
    ta.value = current.notes || "";
    card.appendChild(ta);
    var err = document.createElement("p"); err.className = "ops__notice is-error"; err.hidden = true;
    card.appendChild(err);
    var actions = document.createElement("div"); actions.className = "ops__notes-actions";
    var cancel = document.createElement("button");
    cancel.type = "button"; cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
    var cancelArmed = false;
    cancel.addEventListener("click", function () {
      if (ta.value !== (current.notes || "") && !cancelArmed) {
        cancelArmed = true; cancel.textContent = "Discard changes?"; return;
      }
      renderNotes();
    });
    var save = document.createElement("button");
    save.type = "button"; save.className = "cbm-button"; save.textContent = "Save";
    save.addEventListener("click", async function () {
      save.disabled = true; err.hidden = true;
      try {
        await api("/submissions/" + encodeURIComponent(current.id) + "/notes",
          { method: "PUT", body: JSON.stringify({ notes: ta.value }) });
        current.notes = ta.value;
        var row = rows.filter(function (r) { return r.id === current.id; })[0];
        if (row) row.notes = ta.value;
        renderNotes();
        notice("detailNotice", "Notes saved.", "success");
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        save.disabled = false;
        err.textContent = "Couldn't save: " + e.message; err.hidden = false;
      }
    });
    actions.appendChild(cancel); actions.appendChild(save);
    card.appendChild(actions);
    ta.focus();
  }

  // --- details tab (raw payload / progress / error + CRM record links) ------
  function field(label, value) {
    var wrap = document.createElement("div"); wrap.className = "detail-field";
    var h = document.createElement("h3"); h.textContent = label; wrap.appendChild(h);
    var pre = document.createElement("pre"); pre.textContent = value; wrap.appendChild(pre);
    return wrap;
  }

  // result ids -> EspoCRM deep links (accountId -> #Account/view/<id> etc.).
  var RESULT_ENTITIES = {
    accountId: "Account", contactId: "Contact", clientProfileId: "CClientProfile",
    engagementId: "CEngagement", mentorProfileId: "CMentorProfile",
    partnerProfileId: "CPartnerProfile", sponsorProfileId: "CSponsorProfile",
    informationRequestId: "CInformationRequest",
  };

  function renderDetailsTab() {
    var body = $("detailBody"); body.innerHTML = "";
    body.appendChild(field("Status", current.status + "  (attempts: " + (current.attempt_count || 0) + ")"));
    if (current.last_error) body.appendChild(field("Last error", current.last_error));
    body.appendChild(field("Payload", JSON.stringify(current.payload, null, 2)));
    if (current.progress) body.appendChild(field("Progress (created so far)", JSON.stringify(current.progress, null, 2)));
    if (current.result) {
      body.appendChild(field("Result", JSON.stringify(current.result, null, 2)));
      // Deep links into the CRM for the records this delivery created.
      var crm = config && config.crmUrl;
      if (crm) {
        var links = document.createElement("div"); links.className = "crm-links";
        Object.keys(current.result).forEach(function (k) {
          var entity = RESULT_ENTITIES[k];
          var id = current.result[k];
          if (!entity || !id) return;
          var a = document.createElement("a");
          a.href = crm.replace(/\/$/, "") + "/#" + entity + "/view/" + id;
          a.target = "_blank"; a.rel = "noopener";
          a.textContent = "Open " + entity + " in the CRM ↗";
          links.appendChild(a);
        });
        if (links.childNodes.length) body.appendChild(links);
      }
    }
  }

  // --- conversation (Overview list + Communications tab) --------------------
  // Compose options for "Email the submitter": an existing conversation makes
  // the send a REPLY on its newest Gmail thread (subject + In-Reply-To /
  // References; build_mime chains them); a fresh conversation on an
  // info-request pre-applies the canned reply template (silent fallback to a
  // blank compose when no template with that name exists).
  function composeOpts() {
    // Every ops compose carries the submission id: the server anchors the
    // sent message's Gmail thread to the submission, and the conversation
    // view reads exactly the anchored threads (never an address search).
    var opts = { extra: { submissionId: current.id } };
    var last = messages && messages.length ? messages[0] : null;  // newest first
    if (last) {
      var subj = last.subject || "";
      if (subj && !/^re:/i.test(subj)) subj = "Re: " + subj;
      opts.subject = subj;
      opts.reply = {
        threadId: last.threadId || null,
        inReplyTo: last.rfcMessageId || "",
        references: last.references || "",
      };
      return opts;
    }
    if (current.form_slug === "info-request" && config && config.replyTemplate) {
      opts.template = config.replyTemplate;
    }
    return opts;
  }

  function emailButton() {
    var addr = (current.payload || {}).email;
    if (!addr) return null;
    var replying = messages && messages.length;
    var label = replying ? "↩ Reply to the submitter" : "✉ Email the submitter";
    if (config && config.commsEnabled && window.CBMQuickMail) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "small-btn"; b.textContent = label;
      b.addEventListener("click", function () {
        CBMQuickMail.composeIfEnabled(String(addr), composeOpts());
      });
      return b;
    }
    var m = document.createElement("a");
    m.className = "small-btn"; m.href = "mailto:" + addr; m.textContent = label;
    return m;
  }

  function refreshMsgButton() {
    var b = document.createElement("button");
    b.type = "button"; b.className = "small-btn"; b.textContent = "Refresh";
    b.addEventListener("click", function () { loadMessages(true); });
    return b;
  }

  async function loadMessages(force) {
    if (messages !== null && !force) { renderConversation(); renderComms(); return; }
    var conv = $("convList"); conv.innerHTML = "<p class='is-muted'>Loading conversation…</p>";
    try {
      var res = await api("/submissions/" + encodeURIComponent(current.id) + "/messages");
      messages = res.messages || [];
      messagesReason = res.reason || null;
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      messages = []; messagesReason = e.message;
    }
    renderConversation();
    renderComms();
  }

  function msgCard(m, expandable) {
    var card = document.createElement("div");
    card.className = "msg " + (m.direction === "sent" ? "msg--sent" : "msg--received");
    var head = document.createElement("div"); head.className = "msg__head";
    var who = document.createElement("span"); who.className = "msg__who";
    who.textContent = m.direction === "sent" ? "You → " + (m.to || "") : (m.fromName || m.fromAddress);
    var dir = document.createElement("span"); dir.className = "msg__dir";
    dir.textContent = m.direction === "sent" ? "sent" : "received";
    var date = document.createElement("span"); date.className = "msg__date"; date.textContent = fmtDate(m.date);
    var subj = document.createElement("span"); subj.className = "msg__subject"; subj.textContent = m.subject;
    head.appendChild(who); head.appendChild(dir); head.appendChild(date); head.appendChild(subj);
    card.appendChild(head);
    if (expandable) {
      var snip = document.createElement("div"); snip.className = "msg__snippet"; snip.textContent = m.snippet || "";
      card.appendChild(snip);
      var bodyEl = null;
      head.addEventListener("click", function () {
        if (bodyEl) { bodyEl.remove(); bodyEl = null; snip.hidden = false; return; }
        snip.hidden = true;
        bodyEl = document.createElement("div"); bodyEl.className = "msg__body";
        bodyEl.innerHTML = sanitizeHtml(m.bodyHtml || "") || "<p class='is-muted'>(no content)</p>";
        card.appendChild(bodyEl);
      });
    } else {
      var s = document.createElement("div"); s.className = "msg__snippet"; s.textContent = m.snippet || "";
      card.appendChild(s);
      card.style.cursor = "pointer";
      card.addEventListener("click", function () { activateTab("communications"); });
    }
    return card;
  }

  // Overview: the latest few messages, newest first, below the notes.
  function renderConversation() {
    var box = $("convList"); box.innerHTML = "";
    var actions = $("convActions"); actions.innerHTML = "";
    var eb = emailButton(); if (eb) actions.appendChild(eb);
    actions.appendChild(refreshMsgButton());
    if (messagesReason && !(messages && messages.length)) {
      var p = document.createElement("p"); p.className = "is-muted"; p.textContent = messagesReason;
      box.appendChild(p); return;
    }
    if (!messages || !messages.length) {
      var e = document.createElement("p"); e.className = "is-muted";
      e.textContent = "No emails with this submitter yet — use “Email the submitter” to start the conversation.";
      box.appendChild(e); return;
    }
    messages.slice(0, 5).forEach(function (m) { box.appendChild(msgCard(m, false)); });
    if (messages.length > 5) {
      var more = document.createElement("button");
      more.type = "button"; more.className = "small-btn";
      more.textContent = "Show all " + messages.length + " messages";
      more.addEventListener("click", function () { activateTab("communications"); });
      box.appendChild(more);
    }
  }

  // Communications tab: the full history, expandable bodies, compose.
  function renderComms() {
    var box = $("commList"); box.innerHTML = "";
    var actions = $("commActions"); actions.innerHTML = "";
    var eb = emailButton(); if (eb) actions.appendChild(eb);
    actions.appendChild(refreshMsgButton());
    if (config && config.commsEnabled === false) {
      var off = document.createElement("p"); off.className = "is-muted";
      off.textContent = "Email isn't enabled on this deployment.";
      box.appendChild(off); return;
    }
    if (messagesReason && !(messages && messages.length)) {
      var p = document.createElement("p"); p.className = "is-muted"; p.textContent = messagesReason;
      box.appendChild(p); return;
    }
    if (!messages || !messages.length) {
      var e = document.createElement("p"); e.className = "is-muted";
      e.textContent = "No emails with this submitter yet.";
      box.appendChild(e); return;
    }
    messages.forEach(function (m) { box.appendChild(msgCard(m, true)); });
  }

  // --- boot -----------------------------------------------------------------
  fillSelect($("statusFilter"), STATUSES, "All statuses");
  fillSelect($("formFilter"), FORMS, "All forms");
  (async function init() {
    try {
      config = await api("/session");
      $("whoName").textContent = config.name || config.userName;
      show($("userCorner"));
      hide($("msgView")); show($("dashView"));
      loadData();
    } catch (e) { bootFail(e); }
  })();
})();
