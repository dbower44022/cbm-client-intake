/* Mentor Admin — list (search/filter/sort) + per-mentor review & edit. */
(function () {
  "use strict";

  var API = "/mentoradmin/api";
  var mentors = [];
  var fieldSpec = [];      // [{name,label,type,group}]
  var fieldOptions = {};   // {fieldName: [options]}
  var current = null;      // the mentor being edited
  var listDirty = false;   // reload list after an edit
  var filter = { q: "", status: "", industry: "", sortKey: "name", sortDir: 1 };

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
  function showLogin() { hide($("listView")); hide($("detailView")); show($("loginView")); $("username").focus(); }
  function showList() { hide($("loginView")); hide($("detailView")); show($("listView")); }
  function showDetail() { hide($("loginView")); hide($("listView")); show($("detailView")); }

  function notice(elId, text, kind) {
    var n = $(elId); n.textContent = text;
    n.className = "ma__notice " + (kind === "error" ? "is-error" : "is-success");
    show(n); n.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function fillSelect(sel, values, placeholder) {
    var cur = sel.value; sel.innerHTML = "";
    sel.appendChild(new Option(placeholder, ""));
    values.forEach(function (v) { sel.appendChild(new Option(v, v)); });
    sel.value = cur;
  }

  // --- login ---
  $("loginForm").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    hide($("loginError")); $("loginBtn").disabled = true;
    try {
      var user = await api("/login", { method: "POST", body: JSON.stringify({ username: $("username").value, password: $("password").value }) });
      $("password").value = "";
      $("whoName").textContent = user.name || user.userName;
      await bootList();
    } catch (e) {
      var le = $("loginError"); le.textContent = e.message; show(le);
    } finally { $("loginBtn").disabled = false; }
  });
  $("logoutBtn").addEventListener("click", async function () { try { await api("/logout", { method: "POST" }); } catch (e) {} showLogin(); });
  $("refreshBtn").addEventListener("click", function () { loadMentors(); });
  $("backBtn").addEventListener("click", function () { showList(); if (listDirty) { listDirty = false; loadMentors(); } });
  $("search").addEventListener("input", function () { filter.q = this.value; renderTable(); });
  $("statusFilter").addEventListener("change", function () { filter.status = this.value; renderTable(); });
  $("industryFilter").addEventListener("change", function () { filter.industry = this.value; renderTable(); });

  // --- list ---
  async function bootList() {
    showList();
    // field spec/options loaded once (used by the detail form)
    try { var f = await api("/fields"); fieldSpec = f.fields || []; fieldOptions = f.options || {}; } catch (e) { if (e.status === 401) { showLogin(); return; } }
    await loadMentors();
  }

  async function loadMentors() {
    var ln = $("listNotice"); hide(ln);
    show($("loadingState")); hide($("mentorTable")); hide($("emptyState"));
    try {
      mentors = (await api("/mentors")).mentors || [];
      fillSelect($("statusFilter"), distinct(function (m) { return [m.status]; }), "All statuses");
      fillSelect($("industryFilter"), distinct(function (m) { return [m.industrySector]; }), "All industries");
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
  function avail(m) { return m.availableCapacity === -1 ? Infinity : (typeof m.availableCapacity === "number" ? m.availableCapacity : -Infinity); }
  function haystack(m) { return [m.name, m.status, m.industrySector, (m.expertise || []).join(" "), (m.focusAreas || []).join(" ")].join(" ").toLowerCase(); }
  function sortVal(m, k) { if (k === "availableCapacity") return avail(m); if (k === "assignedClients") return m.assignedClients == null ? -Infinity : m.assignedClients; return (m[k] || "").toString().toLowerCase(); }

  function renderTable() {
    var q = filter.q.trim().toLowerCase();
    var rows = mentors.filter(function (m) {
      if (q && haystack(m).indexOf(q) < 0) return false;
      if (filter.status && m.status !== filter.status) return false;
      if (filter.industry && m.industrySector !== filter.industry) return false;
      return true;
    });
    var k = filter.sortKey, dir = filter.sortDir;
    rows.sort(function (a, b) { var x = sortVal(a, k), y = sortVal(b, k); return (x < y ? -1 : x > y ? 1 : 0) * dir; });

    var tb = $("mentorBody"); tb.innerHTML = "";
    $("count").textContent = "Showing " + rows.length + " of " + mentors.length + " mentors";
    if (!rows.length) { show($("emptyState")); hide($("mentorTable")); return; }
    hide($("emptyState"));
    rows.forEach(function (m) {
      var tr = document.createElement("tr"); tr.className = "ma-row";
      var name = document.createElement("td");
      var link = document.createElement("button"); link.type = "button"; link.className = "name-link";
      link.textContent = m.name || "(unnamed)";
      link.addEventListener("click", function () { openMentor(m.id); });
      name.appendChild(link); tr.appendChild(name);
      tr.appendChild(cell(badge(m.status)));
      tr.appendChild(cell(fmtDate(m.createdAt)));
      tr.appendChild(cell(m.assignedClients == null ? "—" : String(m.assignedClients), "num"));
      tr.appendChild(cell(m.availableCapacity === -1 ? "Unlimited" : (m.availableCapacity == null ? "—" : String(m.availableCapacity)), "num"));
      tr.appendChild(cell(m.industrySector || "—"));
      tb.appendChild(tr);
    });
    show($("mentorTable"));
    updateSortIndicators();
  }
  function cell(content, cls) { var td = document.createElement("td"); if (cls) td.className = cls; if (content instanceof Node) td.appendChild(content); else td.textContent = content; return td; }
  function fmtDate(v) { return v ? String(v).slice(0, 10) : "—"; }  // ISO date part (YYYY-MM-DD)
  function badge(status) { var s = document.createElement("span"); s.className = "status-badge status-" + (status || "none"); s.textContent = status || "—"; return s; }
  function updateSortIndicators() {
    Array.prototype.forEach.call($("mentorTable").querySelectorAll("th[data-sort]"), function (th) {
      th.dataset.dir = th.getAttribute("data-sort") === filter.sortKey ? (filter.sortDir === 1 ? "asc" : "desc") : "";
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll("#mentorTable th[data-sort]"), function (th) {
    th.addEventListener("click", function () {
      var key = th.getAttribute("data-sort");
      if (filter.sortKey === key) filter.sortDir = -filter.sortDir;
      else { filter.sortKey = key; filter.sortDir = (key === "name" || key === "status" || key === "industrySector") ? 1 : -1; }
      renderTable();
    });
  });

  // --- detail / edit ---
  async function openMentor(id) {
    try {
      current = await api("/mentors/" + encodeURIComponent(id));
    } catch (e) { if (e.status === 401) { showLogin(); return; } notice("listNotice", e.message, "error"); return; }
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

  // US-style phone: (216) 555-1234, tolerating a leading +1 / 1. Non-10-digit
  // (international, extensions, etc.) values are shown as-is.
  function formatPhone(raw) {
    if (!raw) return raw;
    var d = String(raw).replace(/\D/g, "");
    if (d.length === 11 && d.charAt(0) === "1") d = d.slice(1);
    if (d.length !== 10) return raw;
    return "(" + d.slice(0, 3) + ") " + d.slice(3, 6) + "-" + d.slice(6);
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
    if (c.issues && c.issues.length) s.title = "Missing/incorrect: " + c.issues.join("; ");
    return s;
  }

  function renderReadonly(m) {
    var box = $("readonly"); box.innerHTML = "";
    // data-structure completeness (first, most prominent)
    if (m.completeness) roItem(box, "Data completeness", completenessNode(m.completeness));
    // status
    roItem(box, "Mentoring status", badge(m.mentorStatus));
    roItem(box, "Accepting new clients", m.acceptingNewClients ? "Yes" : "No");
    // contact
    if (m.personalEmail) roItem(box, "Email", roLink("mailto:" + m.personalEmail, m.personalEmail));
    if (m.contactPhone) roItem(box, "Phone", roLink("tel:" + m.contactPhone, formatPhone(m.contactPhone)));
    roItem(box, "Address", addressNode(m), true);
    // activity / capacity
    roItem(box, "Assigned user", m.assignedUserName);
    roItem(box, "Assigned clients", m.currentActiveClients);
    roItem(box, "Available capacity", m.availableCapacity === -1 ? "Unlimited" : m.availableCapacity);
    roItem(box, "Max capacity", m.maximumClientCapacity);
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
    if (order.length) activateTab(order[0]);
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
      el = makeWysiwyg(value);
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
      var a = el.querySelector(".wysiwyg__area");
      if (!a) return "";
      return a.textContent.trim() === "" ? "" : a.innerHTML;  // empty -> "" not "<br>"
    }
    return el.value;
  }

  $("saveBtn").addEventListener("click", async function () {
    if (!current) return;
    var changes = {};
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      var cur = readField(el);
      // Only send fields the user actually changed (see buildField snapshot).
      if (JSON.stringify(cur) !== el.dataset.original) changes[el.dataset.field] = cur;
    });
    if (!Object.keys(changes).length) { notice("detailNotice", "No changes to save.", "success"); return; }
    $("saveBtn").disabled = true;
    try {
      current = await api("/mentors/" + encodeURIComponent(current.id), { method: "PUT", body: JSON.stringify({ changes: changes }) });
      listDirty = true;
      // Re-baseline the change snapshots to the just-saved state, so a later
      // edit that reverts a field to its render-time value is still sent.
      Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
        el.dataset.original = JSON.stringify(readField(el));
      });
      $("detailName").textContent = current.name || "(unnamed mentor)";
      renderReadonly(current);
      // Approving a mentor provisions a login user (server-side) — report it.
      var p = current.provision;
      if (p && p.ok) {
        notice("detailNotice", "Saved. Created login " + p.userName + " in " + p.team + " and sent a welcome email.", "success");
      } else if (p && !p.ok) {
        notice("detailNotice", "Saved, but the mentor's login could not be created: " + p.error, "error");
      } else {
        notice("detailNotice", "Saved.", "success");
      }
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailNotice", e.message, "error");
    } finally { $("saveBtn").disabled = false; }
  });

  // --- boot ---
  (async function init() {
    try { var u = await api("/session"); $("whoName").textContent = u.name || u.userName; await bootList(); }
    catch (e) { showLogin(); }
  })();
})();
