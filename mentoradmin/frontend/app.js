/* Mentor Admin — list (search/filter/sort) + per-mentor review & edit. */
(function () {
  "use strict";

  var API = "/mentoradmin/api";
  var mentors = [];
  var metricsAvailable = true;   // false = server couldn't read CEngagement
  var fieldSpec = [];      // [{name,label,type,group}]
  var fieldOptions = {};   // {fieldName: [options]}
  var current = null;      // the mentor being edited
  var listDirty = false;   // reload list after an edit
  var isAdmin = false;     // gates the Email Setup screen
  var docsEnabled = false; // GDRIVE_DOCS server-side: shows the Documents tab
  var filter = { q: "", status: "", record: "", type: "", sortKey: "name", sortDir: 1 };

  function $(id) { return document.getElementById(id); }
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    var resp = await fetch(API + path, opts);
    var data = null;
    try { data = await resp.json(); } catch (e) {}
    if (!resp.ok) {
      var msg = (data && data.detail) || ("Request failed (" + resp.status + ")");
      var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  // --- views ---
  // Not signed in: hand off to the portal, which brings the user back here
  // after login (single sign-on — this app has no login form of its own).
  function showLogin() {
    location.href = "/?next=" + encodeURIComponent("/mentoradmin/");
  }
  function showMessage(text) { hideAll(); $("msgText").textContent = text; show($("msgView")); }
  // On boot: 401 = not signed in (go sign in at the portal); 403 = signed in
  // but not entitled to this app (show the exact reason); anything else = the
  // server is down — say so.
  function bootFail(e) {
    if (e && e.status === 401) { showLogin(); return; }
    if (e && e.status === 403) { showMessage(e.message); return; }
    showMessage("The server isn't responding right now. Please try again in a moment.");
  }
  function hideAll() { hide($("msgView")); hide($("listView")); hide($("detailView")); hide($("setupView")); }
  function showList() { hideAll(); show($("listView")); }
  function showDetail() { hideAll(); show($("detailView")); }
  function showSetup() { hideAll(); show($("setupView")); }

  function setUser(user) {
    $("whoName").textContent = user.name || user.userName;
    isAdmin = !!user.isAdmin;
    docsEnabled = !!user.docsEnabled;
    $("setupBtn").hidden = !isAdmin;
  }

  function notice(elId, text, kind) {
    var n = $(elId); n.textContent = text;
    n.className = "ma__notice " + (kind === "error" ? "is-error" : kind === "warn" ? "is-warn" : "is-success");
    show(n); n.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function fillSelect(sel, values, placeholder) {
    var cur = sel.value; sel.innerHTML = "";
    sel.appendChild(new Option(placeholder, ""));
    values.forEach(function (v) { sel.appendChild(new Option(v, v)); });
    sel.value = cur;
  }

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) {}
    location.href = "/";  // back to the portal sign-in
  });
  $("refreshBtn").addEventListener("click", function () { loadMentors(); });
  function returnToList() { showList(); if (listDirty) { listDirty = false; loadMentors(); } }
  $("backBtn").addEventListener("click", function () {
    var changed = unsavedFieldLabels();
    if (changed.length) showDiscardModal(changed, returnToList);
    else returnToList();
  });
  $("search").addEventListener("input", function () { filter.q = this.value; renderTable(); });
  $("statusFilter").addEventListener("change", function () { filter.status = this.value; renderTable(); });
  $("recordFilter").addEventListener("change", function () { filter.record = this.value; renderTable(); });
  $("typeFilter").addEventListener("change", function () { filter.type = this.value; renderTable(); });
  $("setupBtn").addEventListener("click", function () { openSetup(); });
  $("setupBackBtn").addEventListener("click", function () { showList(); });
  $("setupSaveBtn").addEventListener("click", function () { saveSetup(); });
  $("setupTestBtn").addEventListener("click", function () { testSetup(); });
  // Copy-to-clipboard for the scope strings in the setup guide.
  $("setupView").addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest(".ma__copy");
    if (!btn) return;
    var text = btn.getAttribute("data-copy") || "";
    var done = function () { btn.classList.add("is-copied"); btn.textContent = "✓"; setTimeout(function () { btn.classList.remove("is-copied"); btn.textContent = "⧉"; }, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () {});
    else { try { var t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select(); document.execCommand("copy"); document.body.removeChild(t); done(); } catch (e) {} }
  });

  // --- list ---
  async function bootList() {
    showList();
    // field spec/options loaded once (used by the detail form)
    var fieldsError = null;
    try {
      var f = await api("/fields"); fieldSpec = f.fields || []; fieldOptions = f.options || {};
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      fieldsError = e.message;
    }
    await loadMentors();  // hides listNotice on entry, so warn afterwards
    // Without the field spec the editor can't render — warn, but still show the
    // roster (read-only) rather than failing the whole view.
    if (fieldsError) {
      notice("listNotice", "Could not load the editable-field definitions, so mentor editing is unavailable. Refresh to retry. (" + fieldsError + ")", "error");
    }
  }

  async function loadMentors() {
    var ln = $("listNotice"); hide(ln);
    show($("loadingState")); hide($("mentorTable")); hide($("emptyState"));
    try {
      var res = await api("/mentors");
      mentors = res.mentors || [];
      // False when the server couldn't read CEngagement (metric columns come
      // back blank) — noted on the count line so blanks aren't read as zeros.
      metricsAvailable = res.metricsAvailable !== false;
      fillSelect($("statusFilter"), distinct(function (m) { return [m.status]; }), "All statuses");
      fillSelect($("recordFilter"), distinct(function (m) { return [m.recordStatus]; }), "All record statuses");
      // Type filter = the CRM's full mentorType enum (every type selectable, not
      // just the ones in the roster), plus any stored value the enum no longer has.
      fillSelect($("typeFilter"),
        withOptions(res.mentorTypeOptions || [], distinct(function (m) { return [m.mentorType]; })),
        "All types");
      renderTable();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("listNotice", e.message, "error");
    } finally { hide($("loadingState")); }
  }

  function distinct(getList) {
    var set = {}; mentors.forEach(function (m) { getList(m).forEach(function (v) { if (v) set[v] = true; }); });
    return Object.keys(set).sort();
  }
  // CRM-declared options first (their order), then any row values not in the
  // declared list (e.g. a since-removed enum value still stored on a mentor).
  function withOptions(declared, found) {
    var out = (declared || []).slice();
    found.forEach(function (v) { if (out.indexOf(v) < 0) out.push(v); });
    return out;
  }
  function avail(m) { return m.availableCapacity === -1 ? Infinity : (typeof m.availableCapacity === "number" ? m.availableCapacity : -Infinity); }
  function haystack(m) { return [m.name, m.status, m.cbmEmail, m.mentorType, (m.expertise || []).join(" "), (m.focusAreas || []).join(" ")].join(" ").toLowerCase(); }
  function sortVal(m, k) {
    if (k === "availableCapacity") return avail(m);
    if (k === "activeClients" || k === "maxCapacity" || k === "assignedLast30" || k === "lifetimeClients")
      return m[k] == null ? -Infinity : m[k];
    return (m[k] || "").toString().toLowerCase();
  }

  function renderTable() {
    var q = filter.q.trim().toLowerCase();
    var rows = mentors.filter(function (m) {
      if (q && haystack(m).indexOf(q) < 0) return false;
      if (filter.status && m.status !== filter.status) return false;
      if (filter.record && m.recordStatus !== filter.record) return false;
      if (filter.type && m.mentorType !== filter.type) return false;
      return true;
    });
    var k = filter.sortKey, dir = filter.sortDir;
    rows.sort(function (a, b) { var x = sortVal(a, k), y = sortVal(b, k); return (x < y ? -1 : x > y ? 1 : 0) * dir; });

    var tb = $("mentorBody"); tb.innerHTML = "";
    $("count").textContent = "Showing " + rows.length + " of " + mentors.length + " mentors" +
      (metricsAvailable ? "" : " — client counts unavailable (your account can't read engagements)");
    if (!rows.length) { show($("emptyState")); hide($("mentorTable")); return; }
    hide($("emptyState"));
    rows.forEach(function (m) {
      var tr = document.createElement("tr"); tr.className = "ma-row";
      var name = document.createElement("td");
      var link = document.createElement("button"); link.type = "button"; link.className = "name-link";
      link.textContent = m.name || "(unnamed)";
      link.addEventListener("click", function () { openMentor(m.id); });
      name.appendChild(link); tr.appendChild(name);
      tr.appendChild(cell(emailLink(m.cbmEmail)));
      tr.appendChild(cell(recordBadge(m.recordStatus)));
      tr.appendChild(cell(badge(m.status)));
      tr.appendChild(cell(m.mentorType || "—"));
      tr.appendChild(cell(fmtDate(m.createdAt)));
      // Client counts are app-computed from CEngagement (Active/Assigned/Pending
      // Acceptance = active); Available = Max Clients − Active Clients.
      tr.appendChild(cell(num(m.activeClients), "num"));
      tr.appendChild(cell(num(m.maxCapacity), "num"));
      tr.appendChild(cell(m.availableCapacity === -1 ? "Unlimited" : num(m.availableCapacity), "num"));
      tr.appendChild(cell(num(m.assignedLast30), "num"));
      tr.appendChild(cell(num(m.lifetimeClients), "num"));
      tb.appendChild(tr);
    });
    show($("mentorTable"));
    updateSortIndicators();
  }
  function cell(content, cls) { var td = document.createElement("td"); if (cls) td.className = cls; if (content instanceof Node) td.appendChild(content); else td.textContent = content; return td; }
  // Clickable email: opens the app's quick-compose dialog (sends as the
  // signed-in user's CBM mailbox); falls back to mailto: when sending isn't
  // available. Shared widget: /shared/quickmail.js.
  function emailLink(email) {
    if (!email) return document.createTextNode("—");
    if (window.CBMQuickMail) return CBMQuickMail.emailLink(email);
    var a = document.createElement("a"); a.className = "email-link";
    a.href = "mailto:" + email; a.textContent = email;
    return a;
  }
  function fmtDate(v) { return v ? String(v).slice(0, 10) : "—"; }  // ISO date part (YYYY-MM-DD)
  function num(v) { return v == null ? "—" : String(v); }
  function badge(status) { var s = document.createElement("span"); s.className = "status-badge status-" + (status || "none"); s.textContent = status || "—"; return s; }
  function recordBadge(rs) {
    if (!rs) { var d = document.createElement("span"); d.className = "ro-muted"; d.textContent = "—"; return d; }
    var s = document.createElement("span"); s.className = "complete-badge complete-" + rs.toLowerCase(); s.textContent = rs; return s;
  }
  function updateSortIndicators() {
    Array.prototype.forEach.call($("mentorTable").querySelectorAll("th[data-sort]"), function (th) {
      th.dataset.dir = th.getAttribute("data-sort") === filter.sortKey ? (filter.sortDir === 1 ? "asc" : "desc") : "";
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll("#mentorTable th[data-sort]"), function (th) {
    th.addEventListener("click", function () {
      var key = th.getAttribute("data-sort");
      if (filter.sortKey === key) filter.sortDir = -filter.sortDir;
      else { filter.sortKey = key; filter.sortDir = (key === "name" || key === "status" || key === "cbmEmail" || key === "mentorType") ? 1 : -1; }
      renderTable();
    });
  });

  // --- detail / edit ---
  async function openMentor(id) {
    try {
      current = await api("/mentors/" + encodeURIComponent(id));
    } catch (e) { if (e.status === 401) { showLogin(); return; } notice("listNotice", e.message, "error"); return; }
    // The detail GET self-heals a drifted recordStatus (persist-on-view). If it
    // changed the stored value, reload the grid on return so the Record column matches.
    var row = mentors.filter(function (m) { return m.id === id; })[0];
    if (row && current.recordStatus && row.recordStatus !== current.recordStatus) listDirty = true;
    $("detailName").textContent = current.name || "(unnamed mentor)";
    hide($("detailNotice"));
    renderReadonly(current);
    renderForm(current);
    showDetail();
    window.scrollTo(0, 0);
  }

  // Compact, read-only summary card: status + contact + activity, at a glance.
  function roItem(box, label, value, wide) {
    if (value == null || value === "") return;
    var d = document.createElement("div"); d.className = "ro-item" + (wide ? " ro-item--wide" : "");
    var l = document.createElement("span"); l.className = "ro-label"; l.textContent = label;
    var v = document.createElement("span"); v.className = "ro-value";
    if (value instanceof Node) v.appendChild(value); else v.textContent = value;
    d.appendChild(l); d.appendChild(v); box.appendChild(d);
  }
  function roLink(href, text) { var a = document.createElement("a"); a.className = "ro-link"; a.href = href; a.textContent = text; return a; }

  // US-style display phone "(216)-555-1234" — the product-wide shared formatter
  // (/shared/phone-format.js); non-10-digit values are shown as-is.
  function formatPhone(raw) {
    if (!raw) return raw;
    return window.CBM && CBM.formatPhone ? CBM.formatPhone(raw) : raw;
  }

  // Two-line address: street on line 1, "City  ZIP" on line 2.
  function addressNode(m) {
    var line2 = [m.contactCity, m.postalCode].filter(Boolean).join("  ");
    if (!m.contactStreet && !line2) return null;
    var wrap = document.createElement("span"); wrap.className = "ro-address";
    [m.contactStreet, line2].forEach(function (line) {
      if (!line) return;
      var s = document.createElement("span"); s.textContent = line; wrap.appendChild(s);
    });
    return wrap;
  }

  function completenessNode(c) {
    var s = document.createElement("span");
    s.className = "complete-badge complete-" + (c.status || "").toLowerCase();
    s.textContent = c.status;
    s.title = "Click for details";
    s.setAttribute("role", "button");
    s.tabIndex = 0;
    s.addEventListener("click", function () { showCompletenessModal(c); });
    s.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showCompletenessModal(c); }
    });
    return s;
  }

  function showCompletenessModal(c) {
    var prev = document.getElementById("compModal");
    if (prev) prev.remove();
    var overlay = document.createElement("div");
    overlay.id = "compModal"; overlay.className = "modal-overlay";
    var card = document.createElement("div"); card.className = "modal-card";
    var h = document.createElement("h3");
    h.textContent = c.status === "Complete"
      ? "Mentor data is complete" : "Mentor data is incomplete";
    card.appendChild(h);
    if (c.issues && c.issues.length) {
      var p = document.createElement("p"); p.textContent = "The following must be resolved:";
      card.appendChild(p);
      var ul = document.createElement("ul");
      c.issues.forEach(function (i) { var li = document.createElement("li"); li.textContent = i; ul.appendChild(li); });
      card.appendChild(ul);
    } else {
      var ok = document.createElement("p");
      ok.textContent = "All required records, links, and sign-offs are in place.";
      card.appendChild(ok);
    }
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "cbm-button"; btn.textContent = "Close";
    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    btn.addEventListener("click", close);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
    card.appendChild(btn); overlay.appendChild(card); document.body.appendChild(overlay);
    btn.focus();
  }

  // --- "Update Mentor Status" — bulk login-user + mailbox verification ---
  $("verifyBtn").addEventListener("click", function () { runStatusVerify(); });

  async function runStatusVerify() {
    var btn = $("verifyBtn");
    btn.disabled = true;
    var orig = btn.textContent;
    btn.textContent = "Checking…";
    hide($("listNotice"));
    try {
      var res = await api("/mentors/status-check", { method: "POST" });
      showVerifyModal(res);
      loadMentors(); // the sweep may have re-synced recordStatus values
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("listNotice", e.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  }

  function verifyMark(ok, text) {
    var s = document.createElement("span");
    s.className = ok === true ? "verify-ok" : ok === false ? "verify-bad" : "verify-warn";
    s.textContent = (ok === true ? "✓ " : ok === false ? "✗ " : "? ") + text;
    return s;
  }

  function userCell(row) {
    if (row.error) return verifyMark(false, "check failed: " + row.error);
    var u = row.user || {};
    if (u.exists === true) {
      return verifyMark(true, (u.userName || "user") + (u.active ? "" : " (deactivated)"));
    }
    if (u.exists === false) return verifyMark(false, u.detail || "no login User");
    return verifyMark(null, u.detail || "could not verify");
  }

  function mailboxCell(row) {
    if (row.error) return document.createTextNode("—");
    var mb = row.mailbox || {};
    if (mb.status === "exists") return verifyMark(true, mb.email);
    if (mb.status === "missing") return verifyMark(false, "no mailbox for " + mb.email);
    if (mb.status === "no-email") return verifyMark(false, "no CBM email on the profile");
    if (mb.status === "unavailable") {
      var s = document.createElement("span");
      s.className = "verify-na";
      s.textContent = "n/a — check not configured";
      return s;
    }
    return verifyMark(null, mb.detail || "could not determine");
  }

  function showVerifyModal(res) {
    var prev = document.getElementById("verifyModal");
    if (prev) prev.remove();
    var overlay = document.createElement("div");
    overlay.id = "verifyModal"; overlay.className = "modal-overlay";
    var card = document.createElement("div"); card.className = "modal-card modal-card--wide";
    var h = document.createElement("h3");
    h.textContent = "Mentor status check";
    card.appendChild(h);

    var rows = res.mentors || [];
    var intro = document.createElement("p");
    intro.textContent = "Checked " + rows.length + " mentor(s): does the login user exist, " +
      "and does the @cbmentors.org mailbox exist. Record statuses were refreshed.";
    card.appendChild(intro);
    if (!res.mailboxCheckEnabled) {
      var warn = document.createElement("p");
      warn.className = "verify-na";
      warn.textContent = "Mailbox checking is not configured — connect Google Workspace under Email Setup to enable it.";
      card.appendChild(warn);
    }

    var wrap = document.createElement("div"); wrap.className = "verify-tablewrap";
    var table = document.createElement("table"); table.className = "ma__table verify-table";
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    ["Mentor", "Status", "Record", "Login user", "Mailbox"].forEach(function (t) {
      var th = document.createElement("th"); th.textContent = t; htr.appendChild(th);
    });
    thead.appendChild(htr); table.appendChild(thead);
    var tbody = document.createElement("tbody");
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.appendChild(cell(row.name || row.id));
      tr.appendChild(cell(row.mentorStatus || "—"));
      tr.appendChild(cell(row.error ? "—" : (row.recordStatus || "—")));
      tr.appendChild(cell(userCell(row)));
      tr.appendChild(cell(mailboxCell(row)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    card.appendChild(wrap);

    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "cbm-button"; btn.textContent = "Close";
    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    btn.addEventListener("click", close);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
    var actions = document.createElement("div"); actions.className = "modal-actions";
    actions.appendChild(btn);
    card.appendChild(actions);
    overlay.appendChild(card); document.body.appendChild(overlay);
    btn.focus();
  }

  function renderReadonly(m) {
    var box = $("readonly"); box.innerHTML = "";
    // data-structure completeness (first, most prominent)
    if (m.completeness) roItem(box, "Data completeness", completenessNode(m.completeness));
    // status
    roItem(box, "Mentoring status", badge(m.mentorStatus));
    roItem(box, "Accepting new clients", m.acceptingNewClients ? "Yes" : "No");
    // contact
    if (m.personalEmail) roItem(box, "Email", emailLink(m.personalEmail));
    if (m.contactPhone) roItem(box, "Phone", roLink("tel:" + m.contactPhone, formatPhone(m.contactPhone)));
    roItem(box, "Address", addressNode(m), true);
    // activity / capacity
    roItem(box, "Assigned user", m.assignedUserName);
    // The same app-computed client counts as the roster grid (clientCounts on
    // the detail response), always shown — "—" when unknown, never omitted.
    var cc = m.clientCounts || {};
    roItem(box, "Active clients", num(cc.activeClients));
    roItem(box, "Max clients", num(cc.maxCapacity));
    roItem(box, "Available", cc.availableCapacity === -1 ? "Unlimited" : num(cc.availableCapacity));
    roItem(box, "Assigned (30d)", num(cc.assignedLast30));
    roItem(box, "Lifetime clients", num(cc.lifetimeClients));
    roItem(box, "Lifetime sessions", m.totalLifetimeSessions);
    roItem(box, "Sessions (30d)", m.totalSessionsLast30Days);
    roItem(box, "Total hours", m.totalMentoringHours);
  }

  // Editable fields, one tab per major area; all panels stay in the DOM (hidden
  // when inactive) so Save still reads every field across all tabs.
  function renderForm(m) {
    var form = $("editForm"); form.innerHTML = "";
    var tabs = $("editTabs"); tabs.innerHTML = "";
    var groups = {}, order = [];
    fieldSpec.forEach(function (f) { if (!groups[f.group]) { groups[f.group] = []; order.push(f.group); } groups[f.group].push(f); });
    order.forEach(function (group) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "ma__tab"; btn.textContent = group;
      btn.dataset.tab = group; btn.setAttribute("role", "tab");
      btn.addEventListener("click", function () { activateTab(group); });
      tabs.appendChild(btn);
      var panel = document.createElement("div"); panel.className = "tab-panel"; panel.dataset.panel = group;
      // Sub-group fields by optional `row` (e.g. Compliance: checks then dates);
      // fields with no `row` share one default row, in declaration order.
      var rows = {}, rowOrder = [];
      groups[group].forEach(function (f) { var r = f.row || "_default"; if (!rows[r]) { rows[r] = []; rowOrder.push(r); } rows[r].push(f); });
      rowOrder.forEach(function (r) {
        var rowEl = document.createElement("div"); rowEl.className = "tab-row" + (r === "checks" ? " tab-row--checks" : "");
        rows[r].forEach(function (f) { rowEl.appendChild(buildField(f, m[f.name])); });
        panel.appendChild(rowEl);
      });
      form.appendChild(panel);
    });
    // Documents (Google Drive, DOC-MGMT) — a non-field tab anchored to the
    // mentor's linked Contact; only when the integration is on server-side.
    if (docsEnabled) {
      var dbtn = document.createElement("button");
      dbtn.type = "button"; dbtn.className = "ma__tab"; dbtn.textContent = "Documents";
      dbtn.dataset.tab = "__documents"; dbtn.setAttribute("role", "tab");
      dbtn.addEventListener("click", function () { activateTab("__documents"); loadMentorDocs(); });
      tabs.appendChild(dbtn);
      form.appendChild(buildDocsPanel());
    }
    if (order.length) activateTab(order[0]);
  }

  // --- Documents tab (mentor documents on the linked Contact) ---------------

  var mdocTypes = [];
  var mdocPendingFile = null;

  function buildDocsPanel() {
    var panel = document.createElement("div");
    panel.className = "tab-panel"; panel.dataset.panel = "__documents";

    var head = document.createElement("div"); head.className = "ma__doc-head";
    var pick = document.createElement("button");
    pick.type = "button"; pick.className = "cbm-button"; pick.id = "mdocPickBtn";
    pick.textContent = "⬆ Upload document…";
    head.appendChild(pick); panel.appendChild(head);

    var file = document.createElement("input");
    file.type = "file"; file.id = "mdocFile"; file.hidden = true;
    panel.appendChild(file);

    var pending = document.createElement("div");
    pending.className = "ma__doc-pending"; pending.id = "mdocPending"; pending.hidden = true;
    var pname = document.createElement("span"); pname.className = "ma__doc-pending-name"; pname.id = "mdocPendingName";
    var tlabel = document.createElement("label"); tlabel.className = "ma__doc-type"; tlabel.textContent = "Type ";
    var tsel = document.createElement("select"); tsel.id = "mdocTypeSelect"; tlabel.appendChild(tsel);
    var up = document.createElement("button");
    up.type = "button"; up.className = "cbm-button ma__sm"; up.id = "mdocUploadBtn"; up.textContent = "Upload";
    var cancel = document.createElement("button");
    cancel.type = "button"; cancel.className = "cbm-button cbm-button--secondary ma__sm"; cancel.id = "mdocCancelBtn"; cancel.textContent = "Cancel";
    pending.appendChild(pname); pending.appendChild(tlabel); pending.appendChild(up); pending.appendChild(cancel);
    panel.appendChild(pending);

    var err = document.createElement("p"); err.className = "form-error"; err.id = "mdocError"; err.hidden = true;
    panel.appendChild(err);

    var table = document.createElement("table"); table.className = "ma__table"; table.id = "mdocTable"; table.hidden = true;
    table.innerHTML = "<thead><tr><th scope='col'>File</th><th scope='col'>Type</th>" +
      "<th scope='col'>Uploaded by</th><th scope='col'>Uploaded</th><th scope='col'></th></tr></thead>";
    var tbody = document.createElement("tbody"); tbody.id = "mdocBody"; table.appendChild(tbody);
    panel.appendChild(table);

    var empty = document.createElement("p"); empty.className = "ma__muted"; empty.id = "mdocEmpty"; empty.hidden = true;
    panel.appendChild(empty);

    pick.addEventListener("click", function () { file.click(); });
    cancel.addEventListener("click", resetMdocPending);
    file.addEventListener("change", function () {
      var f = this.files && this.files[0];
      if (!f) return;
      mdocPendingFile = f;
      hide(err);
      pname.textContent = f.name;
      tsel.innerHTML = "";
      mdocTypes.forEach(function (t) { tsel.appendChild(new Option(t, t)); });
      show(pending);
    });
    up.addEventListener("click", function () { uploadMentorDoc(); });
    return panel;
  }

  function resetMdocPending() {
    mdocPendingFile = null;
    var f = $("mdocFile"); if (f) f.value = "";
    var p = $("mdocPending"); if (p) hide(p);
    var b = $("mdocUploadBtn"); if (b) { b.disabled = false; b.textContent = "Upload"; }
  }

  function fmtDocDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) +
      " — " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }

  async function loadMentorDocs() {
    if (!current) return;
    var body = $("mdocBody"); body.innerHTML = "";
    hide($("mdocError")); hide($("mdocTable"));
    var empty = $("mdocEmpty"); empty.textContent = "Loading documents…"; show(empty);
    try {
      var res = await api("/mentors/" + encodeURIComponent(current.id) + "/documents");
      mdocTypes = res.docTypes || [];
      renderMentorDocRows(res.documents || []);
      // DOC-02 completion: re-sync modifiedTimes from Drive AFTER the metadata
      // render (never blocks it). Best-effort.
      if ((res.documents || []).length) refreshMentorDocTimes();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      hide(empty);
      $("mdocError").textContent = e.message; show($("mdocError"));
    }
  }

  async function refreshMentorDocTimes() {
    if (!current) return;
    var forId = current.id;
    try {
      var res = await api(
        "/mentors/" + encodeURIComponent(forId) + "/documents/refresh",
        { method: "POST" }
      );
      if (!current || current.id !== forId) return;  // user moved on
      mdocTypes = res.docTypes || mdocTypes;
      renderMentorDocRows(res.documents || []);
    } catch (e) { /* lazy refresh is best-effort; the metadata render stands */ }
  }

  function renderMentorDocRows(rows) {
    var body = $("mdocBody"); body.innerHTML = "";
    var empty = $("mdocEmpty");
    if (!rows.length) {
      empty.textContent = "No documents yet — use Upload document to add the first one.";
      show(empty); hide($("mdocTable")); return;
    }
    hide(empty); show($("mdocTable"));
    rows.forEach(function (d) {
      var tr = document.createElement("tr");
      var c0 = document.createElement("td"); c0.textContent = d.filename || "—";
      if (d.changedInDrive) {
        var flag = document.createElement("span");
        flag.className = "ma__doc-flag"; flag.textContent = "Updated in Drive";
        c0.appendChild(flag);
      }
      var c1 = document.createElement("td"); c1.textContent = d.docType || "";
      var c2 = document.createElement("td"); c2.textContent = d.uploadedBy || "—";
      var c3 = document.createElement("td"); c3.textContent = fmtDocDate(d.uploadedAt);
      var c4 = document.createElement("td"); c4.className = "ma__doc-acts";
      ["View", "Open in Drive", "Archive"].forEach(function (label) {
        var b = document.createElement("button");
        b.type = "button"; b.className = "cbm-button cbm-button--secondary ma__sm";
        b.textContent = label;
        // View (DOC-03) + Open in Drive (DOC-05) are live; Archive is Phase 3.
        if (label === "View") {
          b.addEventListener("click", function () { openMdocViewer(d); });
        } else if (label === "Open in Drive" && d.webViewLink) {
          b.addEventListener("click", function () {
            window.open(d.webViewLink, "_blank", "noopener");
          });
        } else {
          b.disabled = true; b.title = "Coming soon";
        }
        c4.appendChild(b);
      });
      tr.appendChild(c0); tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3); tr.appendChild(c4);
      body.appendChild(tr);
    });
  }

  // --- in-app document viewer (DOC-03/04/06) ---------------------------------
  // Same behavior as the session tools' viewer: PDFs/text (and Google-native
  // files, which the proxy serves as exported PDF) in an iframe, images inline,
  // anything else falls back to Open in Drive. The proxy URL is versioned by
  // modifiedTime and served immutable — the browser is the cache (DOC-06).

  var MDOC_GOOGLE_NATIVE = {
    "application/vnd.google-apps.document": true,
    "application/vnd.google-apps.spreadsheet": true,
    "application/vnd.google-apps.presentation": true,
  };

  function mdocContentUrl(d) {
    return API + "/mentors/" + encodeURIComponent(current.id) + "/documents/" +
      encodeURIComponent(d.id) + "/content?v=" + encodeURIComponent(d.modifiedTime || "");
  }

  function mdocViewMode(d) {
    var mime = (d.mimeType || "").toLowerCase();
    if (mime === "application/pdf" || MDOC_GOOGLE_NATIVE[mime] || mime === "text/plain") return "frame";
    if (mime.indexOf("image/") === 0) return "image";
    return "none";
  }

  function mdocFallback(d, failed) {
    var wrap = document.createElement("div"); wrap.className = "ma__docview-fallback";
    var p = document.createElement("p");
    p.textContent = failed
      ? "The document couldn't be loaded — try again, or use Open in Drive."
      : ("This file type can't be previewed in the app" +
         (d.webViewLink ? " — use Open in Drive to view it." : "."));
    wrap.appendChild(p);
    if (d.webViewLink) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "cbm-button"; b.textContent = "Open in Drive";
      b.addEventListener("click", function () { window.open(d.webViewLink, "_blank", "noopener"); });
      wrap.appendChild(b);
    }
    return wrap;
  }

  function openMdocViewer(d) {
    var overlay = document.createElement("div");
    overlay.className = "modal-overlay"; overlay.id = "mdocViewer";
    var card = document.createElement("div"); card.className = "modal-card modal-card--doc";
    var head = document.createElement("div"); head.className = "ma__docview-head";
    var title = document.createElement("h3"); title.textContent = d.filename || "Document";
    var acts = document.createElement("span"); acts.className = "ma__docview-acts";
    if (d.webViewLink) {
      var db = document.createElement("button");
      db.type = "button"; db.className = "cbm-button cbm-button--secondary ma__sm";
      db.textContent = "Open in Drive";
      db.addEventListener("click", function () { window.open(d.webViewLink, "_blank", "noopener"); });
      acts.appendChild(db);
    }
    var close = document.createElement("button");
    close.type = "button"; close.className = "cbm-button cbm-button--secondary ma__sm";
    close.textContent = "Close";
    close.addEventListener("click", function () { overlay.remove(); });
    acts.appendChild(close);
    head.appendChild(title); head.appendChild(acts);
    card.appendChild(head);
    var view = document.createElement("div"); view.className = "ma__docview";
    var mode = mdocViewMode(d);
    if (mode === "image") {
      var img = document.createElement("img");
      img.className = "ma__docview-img"; img.alt = d.filename || "Document";
      img.addEventListener("error", function () {
        view.innerHTML = ""; view.appendChild(mdocFallback(d, true));
      });
      img.src = mdocContentUrl(d);
      view.appendChild(img);
    } else if (mode === "frame") {
      var frame = document.createElement("iframe");
      frame.className = "ma__docview-frame"; frame.title = d.filename || "Document";
      frame.src = mdocContentUrl(d);
      view.appendChild(frame);
    } else {
      view.appendChild(mdocFallback(d, false));
    }
    card.appendChild(view);
    overlay.appendChild(card);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  }

  async function uploadMentorDoc() {
    if (!mdocPendingFile || !current) return;
    var f = mdocPendingFile;
    var btn = $("mdocUploadBtn");
    btn.disabled = true; btn.textContent = "Uploading…";
    hide($("mdocError"));
    try {
      var resp = await fetch(
        API + "/mentors/" + encodeURIComponent(current.id) + "/documents" +
        "?filename=" + encodeURIComponent(f.name) +
        "&docType=" + encodeURIComponent($("mdocTypeSelect").value || ""),
        {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": f.type || "application/octet-stream" },
          body: f,
        }
      );
      var data = null;
      try { data = await resp.json(); } catch (e2) {}
      if (!resp.ok) {
        var msg = (data && data.detail) || ("Upload failed (" + resp.status + ")");
        var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        err.status = resp.status;
        throw err;
      }
      resetMdocPending();
      notice("detailNotice", "Document uploaded.", "success");
      loadMentorDocs();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      btn.disabled = false; btn.textContent = "Upload";
      $("mdocError").textContent = e.message; show($("mdocError"));
    }
  }

  function activateTab(group) {
    Array.prototype.forEach.call($("editTabs").children, function (b) {
      var on = b.dataset.tab === group; b.classList.toggle("is-active", on); b.setAttribute("aria-selected", on);
    });
    Array.prototype.forEach.call($("editForm").children, function (p) { p.hidden = p.dataset.panel !== group; });
  }

  function buildField(f, value) {
    var wrap = document.createElement("div"); wrap.className = "cbm-field field-" + f.type;
    var label = document.createElement("label"); label.textContent = f.label; label.setAttribute("for", "f_" + f.name);
    var input = makeInput(f, value); input.id = "f_" + f.name; input.dataset.field = f.name; input.dataset.type = f.type;
    // Snapshot the initial (normalized) value so Save can send only changed
    // fields — re-sending an unchanged value that has drifted out of its CRM
    // enum options would 400 the whole update.
    input.dataset.original = JSON.stringify(readField(input));
    if (f.type === "bool") {
      wrap.className += " cbm-field--check";
      var lab = document.createElement("label"); lab.appendChild(input); lab.appendChild(document.createTextNode(" " + f.label));
      wrap.appendChild(lab); return wrap;
    }
    wrap.appendChild(label); wrap.appendChild(input); return wrap;
  }

  // --- WYSIWYG editor (contenteditable + minimal toolbar; no external deps) ---
  var WYSIWYG_BUTTONS = [
    { title: "Bold", label: "<b>B</b>", cmd: "bold" },
    { title: "Italic", label: "<i>I</i>", cmd: "italic" },
    { title: "Underline", label: "<u>U</u>", cmd: "underline" },
    { title: "Bulleted list", label: "&bull;", cmd: "insertUnorderedList" },
    { title: "Numbered list", label: "1.", cmd: "insertOrderedList" },
    { title: "Link", label: "Link", cmd: "createLink" },
    { title: "Remove formatting", label: "Clear", cmd: "removeFormat" },
  ];

  // Strip dangerous markup before loading CRM HTML into a contenteditable
  // (scripts won't run via innerHTML, but on* handlers / javascript: URLs can).
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

  function makeWysiwyg(value) {
    var el = document.createElement("div"); el.className = "wysiwyg";
    var area = document.createElement("div");
    area.className = "wysiwyg__area"; area.contentEditable = "true";
    area.innerHTML = sanitizeHtml(value == null ? "" : String(value));
    var bar = document.createElement("div"); bar.className = "wysiwyg__toolbar";
    WYSIWYG_BUTTONS.forEach(function (b) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "wysiwyg__btn"; btn.title = b.title; btn.innerHTML = b.label;
      // mousedown preventDefault keeps the editor's selection while clicking.
      btn.addEventListener("mousedown", function (ev) { ev.preventDefault(); });
      btn.addEventListener("click", function () {
        if (b.cmd === "createLink") {
          var url = window.prompt("Link URL:", "https://");
          if (url) document.execCommand("createLink", false, url);
        } else {
          document.execCommand(b.cmd, false, null);
        }
      });
      bar.appendChild(btn);
    });
    el.appendChild(bar); el.appendChild(area);
    return el;
  }

  function makeInput(f, value) {
    var el;
    if (f.type === "enum") {
      el = document.createElement("select");
      var opts = (f.options || fieldOptions[f.name] || []).slice();
      // Keep an existing free-text value selectable even if it's not in the list.
      if (value != null && value !== "" && opts.indexOf(value) < 0) opts.unshift(value);
      if (opts.indexOf("") < 0) opts.unshift("");  // allow clearing
      opts.forEach(function (o) { el.appendChild(new Option(o === "" ? "(none)" : o, o)); });
      el.value = value == null ? "" : value;
    } else if (f.type === "multiEnum") {
      // A checkbox grid (flows into as many columns as fit) is far more compact
      // and scannable than a tall <select multiple> for these long lists.
      el = document.createElement("div"); el.className = "checkgrid";
      var sel = value || [];
      (fieldOptions[f.name] || []).forEach(function (o) {
        var lab = document.createElement("label"); lab.className = "checkgrid__opt";
        var cb = document.createElement("input"); cb.type = "checkbox"; cb.value = o; cb.checked = sel.indexOf(o) >= 0;
        lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + o));
        el.appendChild(lab);
      });
    } else if (f.type === "bool") {
      el = document.createElement("input"); el.type = "checkbox"; el.checked = !!value;
    } else if (f.type === "int") {
      el = document.createElement("input"); el.type = "number"; el.value = (value == null) ? "" : value;
    } else if (f.type === "date") {
      el = document.createElement("input"); el.type = "date"; el.value = value || "";
    } else if (f.type === "wysiwyg") {
      // Standard editor (shared CBMRichText/Jodit); legacy contenteditable
      // only if the vendored script failed to load.
      el = (window.CBMRichText && window.CBMRichText.create(value)) || makeWysiwyg(value);
    } else if (f.type === "text") {
      el = document.createElement("textarea"); el.rows = 2; el.value = value == null ? "" : value;
    } else {
      el = document.createElement("input"); el.type = "text"; el.value = value == null ? "" : value;
    }
    return el;
  }

  function readField(el) {
    var t = el.dataset.type;
    if (t === "multiEnum") return Array.prototype.map.call(el.querySelectorAll("input:checked"), function (c) { return c.value; });
    if (t === "bool") return el.checked;
    if (t === "int") return el.value === "" ? null : Number(el.value);
    if (t === "date") return el.value || null;
    if (t === "wysiwyg") {
      if (el._cbmRichText) return el._cbmRichText.getValue();
      var a = el.querySelector(".wysiwyg__area");
      if (!a) return "";
      return a.textContent.trim() === "" ? "" : a.innerHTML;  // empty -> "" not "<br>"
    }
    return el.value;
  }

  function currentFormValues() {
    var v = {};
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      v[el.dataset.field] = readField(el);
    });
    return v;
  }
  // Completeness issues the staffer must address before saving. Excludes the
  // member/Contact User assignments — the save auto-creates/reconciles those.
  // Each issue carries the editable field it maps to (or null) so the confirm
  // modal can both list it and jump the user to it on Cancel.
  function pendingCompletenessIssues(v) {
    var issues = [];
    if (!current.contactRecordId) issues.push({ field: null, text: "no linked Contact record" });
    // Background check is optional; publicProfile is not part of completeness.
    [["ethicsAgreementAccepted", "ethics agreement"],
     ["trainingCompleted", "training completed"], ["termsAccepted", "terms accepted"]].forEach(function (f) {
      if (!v[f[0]]) issues.push({ field: f[0], text: f[1] + " not confirmed" });
    });
    if (v.mentorStatus === "Active" && !(v.cbmEmail || "").trim()) issues.push({ field: "cbmEmail", text: "no CBM email address" });
    return issues;
  }

  // Jump to the first issue that maps to an editable field: switch to its tab,
  // focus it (the rich-text area / first checkbox for compound fields), scroll in.
  function focusFirstIssue(issues) {
    for (var i = 0; i < issues.length; i++) {
      if (!issues[i].field) continue;
      var el = $("f_" + issues[i].field);
      if (!el) continue;
      var panel = el.closest && el.closest(".tab-panel");
      if (panel) activateTab(panel.dataset.panel);
      var focusEl = el;
      if (el._cbmRichText) { el._cbmRichText.focus(); focusEl = null; }
      else if (el.classList && el.classList.contains("wysiwyg")) focusEl = el.querySelector(".wysiwyg__area") || el;
      else if (el.classList && el.classList.contains("checkgrid")) focusEl = el.querySelector("input") || el;
      if (focusEl && focusEl.focus) focusEl.focus();
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
  }

  // Generic confirm modal. `opts`: {title, intro, items[], outro, cancelLabel,
  // confirmLabel, onConfirm, onCancel}. Cancel is the safe/default action (focused).
  function modalConfirm(opts) {
    var prev = document.getElementById("confirmModal"); if (prev) prev.remove();
    var overlay = document.createElement("div"); overlay.id = "confirmModal"; overlay.className = "modal-overlay";
    var card = document.createElement("div"); card.className = "modal-card";
    var h = document.createElement("h3"); h.textContent = opts.title; card.appendChild(h);
    if (opts.intro) { var p = document.createElement("p"); p.textContent = opts.intro; card.appendChild(p); }
    if (opts.items && opts.items.length) {
      var ul = document.createElement("ul");
      opts.items.forEach(function (t) { var li = document.createElement("li"); li.textContent = t; ul.appendChild(li); });
      card.appendChild(ul);
    }
    if (opts.outro) { var p2 = document.createElement("p"); p2.textContent = opts.outro; card.appendChild(p2); }
    var actions = document.createElement("div"); actions.className = "modal-actions";
    var cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = opts.cancelLabel;
    var ok = document.createElement("button"); ok.type = "button"; ok.className = "cbm-button"; ok.textContent = opts.confirmLabel;
    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    cancel.addEventListener("click", function () { close(); if (opts.onCancel) opts.onCancel(); });
    ok.addEventListener("click", function () { close(); opts.onConfirm(); });
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
    actions.appendChild(cancel); actions.appendChild(ok); card.appendChild(actions);
    overlay.appendChild(card); document.body.appendChild(overlay);
    cancel.focus();
  }

  function showConfirmModal(issues, onConfirm, onCancel) {
    // Cancel returns the user to the first unresolved field rather than dropping
    // them into a multi-tab form with nothing highlighted.
    modalConfirm({
      title: "This record is still incomplete",
      intro: "The following still need attention:",
      items: issues.map(function (i) { return i.text; }),
      outro: "Cancel to fix it, or save anyway?",
      cancelLabel: "Cancel", confirmLabel: "Save anyway",
      onConfirm: onConfirm, onCancel: onCancel,
    });
  }

  // Fields the user has changed but not yet saved (readField != render snapshot).
  function unsavedFieldLabels() {
    var labels = [];
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      if (JSON.stringify(readField(el)) !== el.dataset.original) {
        var spec = fieldSpec.filter(function (f) { return f.name === el.dataset.field; })[0];
        labels.push(spec ? spec.label : el.dataset.field);
      }
    });
    return labels;
  }

  // Warn before leaving the detail view with unsaved edits (Save re-baselines the
  // snapshots, so a clean save leaves nothing to warn about).
  function showDiscardModal(labels, onDiscard) {
    modalConfirm({
      title: "Discard unsaved changes?",
      intro: "You have unsaved changes to these fields:",
      items: labels,
      outro: "Keep editing to save them, or discard and return to the list.",
      cancelLabel: "Keep editing", confirmLabel: "Discard changes",
      onConfirm: onDiscard,
    });
  }

  // An Approved/Active mentor with no login User needs one provisioned (mailbox
  // check/create + EspoCRM user) — done via the live status window, not the PUT.
  function needsProvisioning(m) {
    return (m.mentorStatus === "Approved" || m.mentorStatus === "Active") && !m.assignedUserId;
  }

  function rebaseline() {
    // Re-baseline the change snapshots to the just-saved state, so a later edit
    // that reverts a field to its render-time value is still sent.
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      el.dataset.original = JSON.stringify(readField(el));
    });
  }

  async function doSave(changes) {
    $("saveBtn").disabled = true;
    try {
      // provision:false — the field save never provisions inline; if a login is
      // needed we drive it through the streaming status window below.
      current = await api("/mentors/" + encodeURIComponent(current.id), { method: "PUT", body: JSON.stringify({ changes: changes, provision: false }) });
      listDirty = true;
      rebaseline();
      $("detailName").textContent = current.name || "(unnamed mentor)";
      renderReadonly(current);
      // Non-fatal server-side notes (e.g. a drifted enum value dropped rather
      // than failing the save) — the save succeeded, but the user should know.
      var warn = (current.warnings && current.warnings.length) ? " " + current.warnings.join(" ") : "";
      if (needsProvisioning(current)) {
        notice("detailNotice", "Saved. Setting up the mentor's login…" + warn, warn ? "warn" : "success");
        startProvision(current.id);
      } else if (warn) {
        notice("detailNotice", "Saved, with a note:" + warn, "warn");
      } else {
        notice("detailNotice", "Saved.", "success");
      }
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailNotice", e.message, "error");
    } finally { $("saveBtn").disabled = false; }
  }

  // --- live provisioning status window (Server-Sent Events) ---
  var PROV_ICON = { running: "⏳", done: "✓", error: "✗" };

  function startProvision(id) {
    var modal = buildProvisionModal();
    streamProvision(id, modal.onEvent)
      .catch(function (e) {
        if (e && e.status === 401) { modal.close(); showLogin(); return; }
        modal.onEvent({ step: "login", status: "error", message: (e && e.message) || "Provisioning failed." });
      })
      .finally(function () { modal.finish(); });
  }

  // POST + read the text/event-stream body (EventSource is GET-only). Parses
  // "data: {json}\n\n" frames and forwards each parsed event.
  async function streamProvision(id, onEvent) {
    var resp = await fetch(API + "/mentors/" + encodeURIComponent(id) + "/provision", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }
    });
    if (!resp.ok) {
      if (resp.status === 401) { var err = new Error("auth"); err.status = 401; throw err; }
      onEvent({ step: "login", status: "error", message: "Could not start provisioning (" + resp.status + ")." });
      return;
    }
    var reader = resp.body.getReader(), dec = new TextDecoder(), buf = "";
    while (true) {
      var r = await reader.read();
      if (r.done) break;
      buf += dec.decode(r.value, { stream: true });
      var frames = buf.split("\n\n"); buf = frames.pop();
      frames.forEach(function (frame) {
        var data = frame.split("\n").filter(function (l) { return l.indexOf("data:") === 0; })
          .map(function (l) { return l.slice(5).trim(); }).join("");
        if (!data) return;
        try { onEvent(JSON.parse(data)); } catch (e) {}
      });
    }
  }

  function buildProvisionModal() {
    var prev = document.getElementById("provModal"); if (prev) prev.remove();
    var overlay = document.createElement("div"); overlay.id = "provModal"; overlay.className = "modal-overlay";
    var card = document.createElement("div"); card.className = "modal-card";
    var h = document.createElement("h3"); h.textContent = "Setting up the mentor's login"; card.appendChild(h);
    var ul = document.createElement("ul"); ul.className = "prov-steps"; card.appendChild(ul);
    var extra = document.createElement("div"); card.appendChild(extra);
    var actions = document.createElement("div"); actions.className = "modal-actions";
    var closeBtn = document.createElement("button"); closeBtn.type = "button"; closeBtn.className = "cbm-button";
    closeBtn.textContent = "Working…"; closeBtn.disabled = true;
    var finished = false;
    function close() {
      overlay.remove(); document.removeEventListener("keydown", onKey);
      // Refresh the detail so the badge + assigned-user reflect the new login.
      if (current) openMentor(current.id);
    }
    function onKey(e) { if (e.key === "Escape" && finished) close(); }
    closeBtn.addEventListener("click", function () { if (finished) close(); });
    document.addEventListener("keydown", onKey);
    actions.appendChild(closeBtn); card.appendChild(actions);
    overlay.appendChild(card); document.body.appendChild(overlay);

    var lines = {};  // step -> <li>
    function upsert(step, status, message) {
      var li = lines[step];
      if (!li) {
        li = document.createElement("li"); li.className = "prov-step";
        var icon = document.createElement("span"); icon.className = "prov-step__icon";
        var txt = document.createElement("span"); txt.className = "prov-step__text";
        li.appendChild(icon); li.appendChild(txt); ul.appendChild(li); lines[step] = li;
      }
      li.className = "prov-step is-" + status;
      li.querySelector(".prov-step__icon").textContent = PROV_ICON[status] || "";
      li.querySelector(".prov-step__text").textContent = message;
    }
    function done() {
      finished = true; closeBtn.disabled = false; closeBtn.textContent = "Close"; closeBtn.focus();
    }
    function showCreds(result) {
      if (!result || !result.tempPassword) return;
      var box = document.createElement("div"); box.className = "prov-creds";
      box.innerHTML = "The mentor's mailbox was just created. Give them this temporary password (they'll be asked to change it at first sign-in):<br>" +
        "Sign-in: <code>" + escapeHtml(result.email || "") + "</code><br>" +
        "Temp password: <code>" + escapeHtml(result.tempPassword) + "</code>" +
        (result.recoveryEmail ? "<br>A password-reset can also be sent to their personal email: <code>" + escapeHtml(result.recoveryEmail) + "</code>." : "");
      extra.appendChild(box);
    }
    return {
      onEvent: function (ev) {
        if (ev.step === "done") { showCreds(ev.result); done(); return; }
        if (!ev.step) return;
        upsert(ev.step, ev.status, ev.message || "");
        if (ev.status === "error") { if (ev.mailboxCreated) showCreds(ev); done(); }
      },
      finish: function () { if (!finished) done(); },
      close: close,
    };
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // --- Email Setup (admin only) ---
  async function openSetup() {
    hide($("setupNotice"));
    $("setupStatus").textContent = "Loading…";
    showSetup();
    try {
      var s = await api("/setup/google");
      if (!s.available) {
        $("setupStatus").textContent = s.reason || "In-app setup is unavailable on this server.";
        $("setupForm").hidden = true;
        return;
      }
      $("setupForm").hidden = false;
      $("su_admin").value = s.delegatedAdmin || "";
      $("su_json").value = "";
      $("su_json").placeholder = s.configured
        ? "A key is already stored. Leave blank to keep it, or paste a new key to replace it."
        : "Paste the service-account JSON key.";
      $("su_check").checked = s.directoryCheck !== false;
      $("su_create").checked = !!s.createMailbox;
      $("setupStatus").textContent = s.configured
        ? ("Configured ✓" + (s.updatedAt ? " — last updated " + String(s.updatedAt).slice(0, 10) : ""))
        : "Not configured yet.";
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      $("setupStatus").textContent = ""; notice("setupNotice", e.message, "error");
    }
  }

  function setupPayload() {
    return {
      service_account_json: $("su_json").value,
      delegated_admin: $("su_admin").value.trim(),
      directory_check: $("su_check").checked,
      create_mailbox: $("su_create").checked,
    };
  }

  async function saveSetup() {
    hide($("setupNotice")); $("setupSaveBtn").disabled = true;
    try {
      await api("/setup/google", { method: "PUT", body: JSON.stringify(setupPayload()) });
      notice("setupNotice", "Saved.", "success");
      openSetup();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("setupNotice", e.message, "error");
    } finally { $("setupSaveBtn").disabled = false; }
  }

  async function testSetup() {
    hide($("setupNotice")); $("setupTestBtn").disabled = true;
    notice("setupNotice", "Testing the connection…", "success");
    try {
      var r = await api("/setup/google/test", { method: "POST", body: JSON.stringify(setupPayload()) });
      notice("setupNotice", r.message, r.ok ? "success" : "error");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("setupNotice", e.message, "error");
    } finally { $("setupTestBtn").disabled = false; }
  }

  $("saveBtn").addEventListener("click", function () {
    if (!current) return;
    var changes = {};
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      var cur = readField(el);
      // Only send fields the user actually changed (see buildField snapshot).
      if (JSON.stringify(cur) !== el.dataset.original) changes[el.dataset.field] = cur;
    });
    // Pre-save completeness check: if the record will still be incomplete, ask
    // for confirmation (styled modal). Cancel -> stay in edit mode, no save.
    var issues = pendingCompletenessIssues(currentFormValues());
    if (issues.length) showConfirmModal(issues, function () { doSave(changes); }, function () { focusFirstIssue(issues); });
    else doSave(changes);
  });

  // --- boot ---
  (async function init() {
    try { var u = await api("/session"); setUser(u); await bootList(); }
    catch (e) { bootFail(e); }
  })();
})();
