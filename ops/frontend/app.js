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
  // Delivery statuses that are "an exception worth showing" next to the derived
  // conversational state (everything else reads plainly "completed").
  var DELIVERY_EXCEPTIONS = { pending: 1, processing: 1, retry: 1,
                              needs_attention: 1, held_honeypot: 1, discarded: 1 };
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
  var closeReasons = [];         // /session closeReasons — the disposition list
  var presenceTimer = null;      // periodic presence poll on the open detail

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

  function parseTs(s) {
    if (!s) return null;
    var d = new Date(s.indexOf("T") < 0 ? s.replace(" ", "T") + "Z" : s);
    return isNaN(d) ? null : d;
  }
  function fmtDate(s) {
    var d = parseTs(s);
    return d ? d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : (s || "—");
  }
  // Compact relative time ("just now", "12 min ago", "3 hr ago", "2 days ago").
  function relTime(s) {
    var d = parseTs(s); if (!d) return "";
    var sec = Math.round((Date.now() - d.getTime()) / 1000);
    if (sec < 45) return "just now";
    if (sec < 3600) return Math.round(sec / 60) + " min ago";
    if (sec < 86400) return Math.round(sec / 3600) + " hr ago";
    var days = Math.round(sec / 86400);
    return days + (days === 1 ? " day ago" : " days ago");
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
  $("backBtn").addEventListener("click", function () { stopPresencePoll(); hide($("detailView")); show($("dashView")); loadData(); });

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

  // The grid collapses the old Status / Request / Reply columns into ONE derived
  // "State" (see stateInfo) + a "Last activity" collision signal.
  var COLUMNS = [
    { key: "id", label: "Reference", get: function (r) { return (r.id || "").slice(0, 8); } },
    { key: "form_slug", label: "Form" },
    { key: "_state", label: "State", sortKey: "_stateSort" },
    { key: "email", label: "Submitter" },
    { key: "_lastact", label: "Last activity", sortKey: "last_activity_at" },
    { key: "received_at", label: "Received", fmt: fmtDate },
    { key: "_actions", label: "", sort: false },
  ];

  // The derived conversational state: closed wins, then the live reply state
  // (owed / bounced / waiting) overlays an otherwise in-progress/new base.
  function stateInfo(r) {
    // A closed row shows its disposition reason (e.g. "Process completed" for an
    // auto-closed intake) rather than a bare "Closed".
    if (r.baseState === "closed") return { cls: "closed", text: r.close_reason || "Closed", reason: r.close_reason };
    var rs = r._replyState;
    if (rs === "owed") return { cls: "owed", text: "Reply owed" };
    if (rs === "bounced") return { cls: "bounced", text: "Delivery failed" };
    if (rs === "waiting") return { cls: "wait", text: "Waiting on them" };
    if (r.baseState === "in_progress") return { cls: "prog", text: "In progress" };
    return { cls: "new", text: "New" };
  }
  var STATE_RANK = { owed: 0, bounced: 1, prog: 2, new: 3, wait: 4, closed: 5 };
  function stateRank(r) { return STATE_RANK[stateInfo(r).cls]; }

  function subBadge(text, tone) {
    var b = document.createElement("span");
    b.className = "state-sub tone-" + tone; b.textContent = text; return b;
  }
  function stateCell(r) {
    var info = stateInfo(r);
    var wrap = document.createElement("span"); wrap.className = "state state-" + info.cls;
    var dot = document.createElement("span"); dot.className = "state-dot"; wrap.appendChild(dot);
    var t = document.createElement("span"); t.textContent = info.text; wrap.appendChild(t);
    if (info.reason) wrap.title = "Closed — " + info.reason;
    // A delivery problem (or an inbound email awaiting Approve) stays visible.
    if (r.status === "held_review") wrap.appendChild(subBadge("held review", "warn"));
    else if (r.status === "discarded") wrap.appendChild(subBadge("discarded", "muted"));
    else if (DELIVERY_EXCEPTIONS[r.status]) wrap.appendChild(subBadge(r.status.replace(/_/g, " "), "crit"));
    return wrap;
  }
  function lastActCell(r) {
    var s = document.createElement("span"); s.className = "lastact";
    if (!r.last_activity_at) { s.innerHTML = "<span class='is-muted'>—</span>"; return s; }
    var who = document.createElement("b"); who.textContent = r.last_activity_by || "—";
    var t = document.createElement("span"); t.className = "is-muted";
    t.textContent = " · " + relTime(r.last_activity_at);
    s.appendChild(who); s.appendChild(t); return s;
  }

  function rowMatches(r) {
    if (state.resolution === "open" && r.resolved_at) return false;
    if (state.resolution === "resolved" && !r.resolved_at) return false;
    if (!state.search) return true;
    var hay = [r.id, r.form_slug, r.status, stateInfo(r).text, r.close_reason,
               r.email, r.last_error, r.last_activity_by, fmtDate(r.received_at)]
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

    rows.forEach(function (r) { r._stateSort = stateRank(r); });  // for the State sort
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
      } else if (c.key === "_state") {
        td.appendChild(stateCell(r));
      } else if (c.key === "_lastact") {
        td.appendChild(lastActCell(r));
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

  // `big` = full-size (detail header, to match the Close button); default is the
  // compact `row-btn` used inside the grid.
  function actionBtn(label, armedText, fn, big) {
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "cbm-button cbm-button--secondary" + (big ? "" : " row-btn");
    btn.textContent = label;
    twoStep(btn, armedText, fn);
    return btn;
  }

  // Re-drive, labelled for what it means on this row: approving a held
  // inbound email DELIVERS it (creates the CRM records) — same endpoint,
  // honest words.
  function redriveBtn(r, noticeEl, big) {
    var approve = r.form_slug === "info-email" && r.status === "held_review";
    return actionBtn(
      approve ? "Approve" : "Re-drive",
      approve ? "Create CRM records?" : "Re-drive?",
      function () { redrive(r, noticeEl); },
      big
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
    renderPresence();
    renderOverview();
    renderDetailsTab();
    renderComms();       // both surfaces render from the same fetch
    activateTab("overview");
    loadMessages();
    startPresencePoll();
    window.scrollTo(0, 0);
  }

  // Presence: re-check who else is looking every ~20s while a detail is open.
  function startPresencePoll() {
    stopPresencePoll();
    presenceTimer = setInterval(async function () {
      if (!current) { stopPresencePoll(); return; }
      try {
        var d = await api("/submissions/" + encodeURIComponent(current.id) + "/presence");
        current.viewers = d.viewers || [];
        renderPresence();
      } catch (e) { /* transient — keep the last presence line */ }
    }, 20000);
  }
  function stopPresencePoll() { if (presenceTimer) { clearInterval(presenceTimer); presenceTimer = null; } }

  // Re-read the open submission after an action (status changed).
  async function refreshDetailRow() {
    if (!current) return;
    try {
      current = await api("/submissions/" + encodeURIComponent(current.id));
      var badgeBox = $("detailBadge"); badgeBox.innerHTML = ""; badgeBox.appendChild(badgeEl(current.status));
      renderDetailActions();
      renderPresence();
      renderOverview();
      renderDetailsTab();
    } catch (e) { /* keep the stale view; the list refresh will correct */ }
  }

  function renderDetailActions() {
    var box = $("detailActions"); box.innerHTML = "";
    if (current.closed_at) {
      // Closed: show the disposition + a Reopen escape hatch.
      var lbl = document.createElement("span"); lbl.className = "closed-label";
      lbl.textContent = "Closed — " + (current.close_reason || "");
      if (current.closed_by) lbl.title = "Closed by " + current.closed_by;
      box.appendChild(lbl);
      var reopen = document.createElement("button");
      reopen.type = "button"; reopen.className = "cbm-button cbm-button--secondary";
      reopen.textContent = "Reopen";
      reopen.addEventListener("click", reopenSubmission);
      box.appendChild(reopen);
    } else {
      box.appendChild(closeControl());  // the single terminal action
    }
    // Full-size (big=true) so Re-drive / Approve / Discard match the Close button.
    if (REDRIVABLE[current.status]) box.appendChild(redriveBtn(current, "detailNotice", true));
    if (DISCARDABLE[current.status]) box.appendChild(actionBtn("Discard", "Really discard?", function () { discard(current, "detailNotice"); }, true));
  }

  // Close ▾ — one deliberate action with a disposition reason (+ optional note).
  function closeControl() {
    var wrap = document.createElement("span"); wrap.className = "closewrap";
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "cbm-button"; btn.textContent = "Close ▾";
    var menu = document.createElement("div"); menu.className = "closemenu"; menu.hidden = true;
    var h = document.createElement("h5"); h.textContent = "Close this request — reason"; menu.appendChild(h);
    var note = document.createElement("input");
    note.type = "text"; note.className = "closemenu__note"; note.placeholder = "Optional note…";
    menu.appendChild(note);
    (closeReasons.length ? closeReasons : ["Responded — resolved"]).forEach(function (reason) {
      var b = document.createElement("button"); b.type = "button"; b.className = "closemenu__opt";
      b.textContent = reason;
      b.addEventListener("click", function () { menu.hidden = true; closeSubmission(reason, note.value.trim()); });
      menu.appendChild(b);
    });
    btn.addEventListener("click", function (e) {
      e.stopPropagation(); menu.hidden = !menu.hidden; if (!menu.hidden) note.focus();
    });
    document.addEventListener("click", function (ev) { if (!wrap.contains(ev.target)) menu.hidden = true; });
    wrap.appendChild(btn); wrap.appendChild(menu);
    return wrap;
  }

  function syncListRow() {
    var row = rows.filter(function (r) { return r.id === current.id; })[0];
    if (!row) return;
    row.resolved_at = current.resolved_at; row.resolved_by = current.resolved_by;
    row.closed_at = current.closed_at; row.close_reason = current.close_reason;
    row.baseState = current.baseState; row.request_status = current.request_status;
    row.last_activity_at = current.last_activity_at; row.last_activity_by = current.last_activity_by;
  }

  async function closeSubmission(reason, note) {
    clearNotice("detailNotice");
    try {
      var res = await api("/submissions/" + encodeURIComponent(current.id) + "/close",
        { method: "POST", body: JSON.stringify({ reason: reason, note: note || "" }) });
      if (res && res.crmWarning) notice("detailNotice", res.crmWarning, "error");
      else notice("detailNotice", "Closed — " + reason + ".", "success");
      await refreshDetailRow(); syncListRow();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailNotice", e.message, "error");
    }
  }

  async function reopenSubmission() {
    clearNotice("detailNotice");
    try {
      await api("/submissions/" + encodeURIComponent(current.id) + "/reopen", { method: "POST" });
      notice("detailNotice", "Reopened — back in the open queue.", "success");
      await refreshDetailRow(); syncListRow();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailNotice", e.message, "error");
    }
  }

  // Payload keys shown first, with curated labels; every OTHER payload field
  // renders after them with a humanized label (Doug's ruling 2026-07-22 —
  // nothing the submitter typed should be visible only as raw JSON).
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
  // Keys the curated facts above already consume.
  var CURATED_KEYS = { first_name: 1, last_name: 1, email: 1, phone: 1, company: 1,
                       business_website: 1, how_did_you_hear: 1, subject: 1, message: 1 };
  // Internal/system fields never shown as facts (honeypot, idempotency token,
  // the email-capture thread anchor).
  var HIDDEN_PAYLOAD_KEYS = { company_url: 1, submission_token: 1, gmail_thread_id: 1 };

  function humanizeKey(key) {
    var s = String(key).replace(/_/g, " ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  // A payload value as display text; null = skip the row (empty). File uploads
  // (base64 objects, e.g. the volunteer resume) show name + size, never bytes.
  function payloadValueText(v) {
    if (v == null || v === "") return null;
    if (Array.isArray(v)) return v.length ? v.map(String).join(", ") : null;
    if (typeof v === "boolean") return v ? "Yes" : "No";
    if (typeof v === "object") {
      if (v.data_base64) {
        var kb = Math.round((v.data_base64.length * 3) / 4 / 1024);
        return (v.filename || "attached file") + " (" + kb + " KB)";
      }
      try { return JSON.stringify(v); } catch (e) { return String(v); }
    }
    return String(v);
  }

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
    box.appendChild(fact("Request status", current.request_status || "New"));
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
    // Every remaining payload field, humanized — the complete submission is
    // readable here without opening the raw JSON on the Details tab.
    Object.keys(p).sort().forEach(function (k) {
      if (CURATED_KEYS[k] || HIDDEN_PAYLOAD_KEYS[k]) return;
      var t = payloadValueText(p[k]);
      if (t == null) return;
      box.appendChild(fact(humanizeKey(k), t));
    });
    renderDiscussion();
    renderActivity();
  }

  // Initials for a small avatar, from a display name.
  function initials(name) {
    var parts = (name || "?").trim().split(/\s+/);
    return ((parts[0] || "?")[0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
  }
  function avatar(name, cls) {
    var a = document.createElement("span"); a.className = "av" + (cls ? " " + cls : "");
    a.textContent = initials(name); a.title = name || ""; return a;
  }

  // --- presence line: who else is looking at this right now ------------------
  function renderPresence() {
    var box = $("presence"); box.innerHTML = "";
    var live = document.createElement("span"); live.className = "presence__live";
    live.textContent = "You're viewing this";
    box.appendChild(live);
    var viewers = current.viewers || [];
    viewers.slice(0, 6).forEach(function (v) {
      var span = document.createElement("span"); span.className = "presence__who";
      span.appendChild(avatar(v.display_name || v.user_name, "p"));
      var t = document.createElement("span");
      t.textContent = (v.display_name || v.user_name) + " · viewed " + relTime(v.viewed_at);
      span.appendChild(t); box.appendChild(span);
    });
    show(box);
  }

  // --- discussion: attributed internal comments among admins -----------------
  function renderDiscussion() {
    var col = $("discussionCol"); col.innerHTML = "";
    col.className = "ops__col";
    var head = document.createElement("div"); head.className = "ops__col-head";
    var h = document.createElement("h3"); h.textContent = "Discussion";
    var hint = document.createElement("span"); hint.className = "ops__col-hint"; hint.textContent = "internal · staff only";
    head.appendChild(h); head.appendChild(hint); col.appendChild(head);

    var body = document.createElement("div"); body.className = "ops__col-body";
    var comments = current.comments || [];
    if (!comments.length) {
      var empty = document.createElement("p"); empty.className = "is-muted";
      empty.textContent = "No comments yet — start the thread for other admins.";
      body.appendChild(empty);
    } else {
      comments.forEach(function (c) {
        var row = document.createElement("div"); row.className = "comment";
        row.appendChild(avatar(c.author_name || c.author, "g"));
        var b = document.createElement("div"); b.className = "comment__body";
        var meta = document.createElement("div"); meta.className = "comment__meta";
        var who = document.createElement("b"); who.textContent = c.author_name || c.author;
        var when = document.createElement("time"); when.textContent = relTime(c.created_at);
        when.title = fmtDate(c.created_at);
        meta.appendChild(who); meta.appendChild(when);
        var p = document.createElement("p"); p.textContent = c.body;
        b.appendChild(meta); b.appendChild(p); row.appendChild(b); body.appendChild(row);
      });
    }
    // add box, pinned to the bottom
    var addbox = document.createElement("div"); addbox.className = "comment__add";
    var ta = document.createElement("textarea"); ta.placeholder = "Add a comment for the team…";
    var r = document.createElement("div"); r.className = "comment__add-row";
    var btn = document.createElement("button"); btn.type = "button";
    btn.className = "cbm-button"; btn.textContent = "Comment";
    btn.addEventListener("click", async function () {
      var text = ta.value.trim();
      if (!text) { ta.focus(); return; }
      btn.disabled = true;
      try {
        var res = await api("/submissions/" + encodeURIComponent(current.id) + "/comments",
          { method: "POST", body: JSON.stringify({ body: text }) });
        current.comments = (current.comments || []).concat(res.comment);
        // reflect the touch: this row is now "in progress" + last-activity is us
        current.baseState = "in_progress";
        current.last_activity_at = res.comment.created_at;
        current.last_activity_by = (config && (config.name || config.userName)) || current.last_activity_by;
        renderDiscussion(); loadActivity(); syncListRow();
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        btn.disabled = false;
        notice("detailNotice", e.message, "error");
      }
    });
    r.appendChild(btn); addbox.appendChild(ta); addbox.appendChild(r);
    body.appendChild(addbox);
    col.appendChild(body);
  }

  // --- activity feed: the automatic, ordered log -----------------------------
  var ACT_ICON = {
    submitted: "✦", delivered: "✓", inbound_received: "↓", comment_added: "💬",
    reply_sent: "↑", status_changed: "•", resolved: "✓", reopened: "↺",
    closed: "✓", redriven: "↻", discarded: "✕",
  };
  var ACT_TONE = { reply_sent: "send", closed: "close", resolved: "close",
                   inbound_received: "in", discarded: "crit" };
  function renderActivity() {
    var col = $("activityCol"); col.innerHTML = "";
    col.className = "ops__col";
    var head = document.createElement("div"); head.className = "ops__col-head";
    var h = document.createElement("h3"); h.textContent = "Activity";
    var hint = document.createElement("span"); hint.className = "ops__col-hint"; hint.textContent = "automatic";
    head.appendChild(h); head.appendChild(hint); col.appendChild(head);
    var body = document.createElement("div"); body.className = "ops__col-body";
    var feed = document.createElement("div"); feed.className = "feed";
    var events = current.activity || [];
    if (!events.length) {
      var e = document.createElement("p"); e.className = "is-muted"; e.textContent = "No activity yet.";
      body.appendChild(e);
    } else {
      events.forEach(function (ev) {
        var row = document.createElement("div"); row.className = "ev";
        var ic = document.createElement("span"); ic.className = "ev__ic" + (ACT_TONE[ev.kind] ? " ev__ic--" + ACT_TONE[ev.kind] : "");
        ic.textContent = ACT_ICON[ev.kind] || "•"; row.appendChild(ic);
        var txt = document.createElement("div"); txt.className = "ev__txt";
        var line = document.createElement("span");
        var who = ev.actor_name || ev.actor || "system";
        line.innerHTML = "<b></b> ";
        line.querySelector("b").textContent = who === "system" ? "System" : who;
        line.appendChild(document.createTextNode(" " + ev.summary));
        var t = document.createElement("time"); t.textContent = relTime(ev.created_at); t.title = fmtDate(ev.created_at);
        txt.appendChild(line); txt.appendChild(t); row.appendChild(txt); feed.appendChild(row);
      });
    }
    body.appendChild(feed); col.appendChild(body);
  }

  // Re-fetch just the activity feed (after posting a comment / action).
  async function loadActivity() {
    try {
      var d = await api("/submissions/" + encodeURIComponent(current.id));
      current.activity = d.activity || current.activity;
      current.viewers = d.viewers || current.viewers;
      renderActivity(); renderPresence();
    } catch (e) { /* keep the current feed */ }
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
    var isSent = m.direction === "sent";
    var dir = m.bounce ? "bounce" : (isSent ? "out" : "in");
    var card = document.createElement("div");
    card.className = "msg msg--" + (isSent ? "sent" : "received");
    if (m.bounce) card.className += " msg--bounce";

    var senderName = m.bounce ? "Delivery failed"
      : (isSent ? (m.fromName ? CBMConversation.partyName(m.fromName) : "We")
                : CBMConversation.partyName(m.fromName || m.fromAddress));
    var avatar = document.createElement("div"); avatar.className = "msg__avatar";
    avatar.textContent = m.bounce ? "!" : CBMConversation.initials(senderName);
    avatar.style.background = m.bounce ? "#b3261e"
      : CBMConversation.avatarColor(m.fromAddress || m.fromName || senderName);
    card.appendChild(avatar);

    var main = document.createElement("div"); main.className = "msg__main";

    var head = document.createElement("div"); head.className = "msg__head";
    var who = document.createElement("span"); who.className = "msg__who"; who.textContent = senderName;
    head.appendChild(who);
    head.appendChild(CBMConversation.badge(dir));
    if (isSent && m.to && !m.bounce) {
      head.appendChild(CBMConversation.el("span", "msg__to", "to " + CBMConversation.partyName(m.to)));
    }
    var date = document.createElement("span"); date.className = "msg__date"; date.textContent = fmtDate(m.date);
    head.appendChild(date);
    var subj = document.createElement("span"); subj.className = "msg__subject"; subj.textContent = m.subject;
    head.appendChild(subj);
    main.appendChild(head);

    if (m.bounce) {
      var warn = document.createElement("div"); warn.className = "msg__bounce-note";
      warn.textContent = "Your reply could NOT be delivered — the address rejected it. " +
        "Check the address for typos (open this notice for the mail system's reason).";
      main.appendChild(warn);
    }

    if (expandable) {
      var snip = document.createElement("div"); snip.className = "msg__snippet"; snip.textContent = m.snippet || "";
      main.appendChild(snip);
      var bodyEl = null;
      head.addEventListener("click", function () {
        if (bodyEl) { bodyEl.remove(); bodyEl = null; snip.hidden = false; return; }
        snip.hidden = true;
        bodyEl = document.createElement("div"); bodyEl.className = "msg__body";
        bodyEl.innerHTML = sanitizeHtml(m.bodyHtml || "") || "<p class='is-muted'>(no content)</p>";
        main.appendChild(bodyEl);
      });
    } else {
      var s = document.createElement("div"); s.className = "msg__snippet"; s.textContent = m.snippet || "";
      main.appendChild(s);
      card.style.cursor = "pointer";
      card.addEventListener("click", function () { activateTab("communications"); });
    }
    card.appendChild(main);
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
      closeReasons = config.closeReasons || [];
      $("whoName").textContent = config.name || config.userName;
      show($("userCorner"));
      hide($("msgView")); show($("dashView"));
      loadData();
    } catch (e) { bootFail(e); }
  })();
})();
