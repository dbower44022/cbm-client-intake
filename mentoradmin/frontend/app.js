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
      tr.appendChild(cell(m.assignedClients == null ? "—" : String(m.assignedClients), "num"));
      tr.appendChild(cell(m.availableCapacity === -1 ? "Unlimited" : (m.availableCapacity == null ? "—" : String(m.availableCapacity)), "num"));
      tr.appendChild(cell(m.industrySector || "—"));
      tb.appendChild(tr);
    });
    show($("mentorTable"));
    updateSortIndicators();
  }
  function cell(content, cls) { var td = document.createElement("td"); if (cls) td.className = cls; if (content instanceof Node) td.appendChild(content); else td.textContent = content; return td; }
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

  function renderReadonly(m) {
    var box = $("readonly"); box.innerHTML = "";
    var items = [
      ["Contact", m.contactRecordName], ["Assigned user", m.assignedUserName],
      ["Assigned clients", m.currentActiveClients], ["Available capacity", m.availableCapacity === -1 ? "Unlimited" : m.availableCapacity],
      ["Max capacity", m.maximumClientCapacity], ["Lifetime sessions", m.totalLifetimeSessions],
      ["Sessions (30d)", m.totalSessionsLast30Days], ["Total hours", m.totalMentoringHours],
    ];
    items.forEach(function (it) {
      if (it[1] == null || it[1] === "") return;
      var d = document.createElement("div"); d.className = "ro-item";
      var l = document.createElement("span"); l.className = "ro-label"; l.textContent = it[0];
      var v = document.createElement("span"); v.className = "ro-value"; v.textContent = it[1];
      d.appendChild(l); d.appendChild(v); box.appendChild(d);
    });
  }

  function renderForm(m) {
    var form = $("editForm"); form.innerHTML = "";
    var groups = {};
    fieldSpec.forEach(function (f) { (groups[f.group] = groups[f.group] || []).push(f); });
    Object.keys(groups).forEach(function (group) {
      var section = document.createElement("fieldset"); section.className = "form-group";
      var legend = document.createElement("legend"); legend.textContent = group; section.appendChild(legend);
      groups[group].forEach(function (f) { section.appendChild(buildField(f, m[f.name])); });
      form.appendChild(section);
    });
  }

  function buildField(f, value) {
    var wrap = document.createElement("div"); wrap.className = "cbm-field field-" + f.type;
    var label = document.createElement("label"); label.textContent = f.label; label.setAttribute("for", "f_" + f.name);
    var input = makeInput(f, value); input.id = "f_" + f.name; input.dataset.field = f.name; input.dataset.type = f.type;
    if (f.type === "bool") {
      wrap.className += " cbm-field--check";
      var lab = document.createElement("label"); lab.appendChild(input); lab.appendChild(document.createTextNode(" " + f.label));
      wrap.appendChild(lab); return wrap;
    }
    wrap.appendChild(label); wrap.appendChild(input); return wrap;
  }

  function makeInput(f, value) {
    var el;
    if (f.type === "enum") {
      el = document.createElement("select");
      (fieldOptions[f.name] || []).forEach(function (o) { el.appendChild(new Option(o === "" ? "(none)" : o, o)); });
      el.value = value == null ? "" : value;
    } else if (f.type === "multiEnum") {
      el = document.createElement("select"); el.multiple = true; el.size = 6;
      var sel = value || [];
      (fieldOptions[f.name] || []).forEach(function (o) { var op = new Option(o, o); op.selected = sel.indexOf(o) >= 0; el.appendChild(op); });
    } else if (f.type === "bool") {
      el = document.createElement("input"); el.type = "checkbox"; el.checked = !!value;
    } else if (f.type === "int") {
      el = document.createElement("input"); el.type = "number"; el.value = (value == null) ? "" : value;
    } else if (f.type === "date") {
      el = document.createElement("input"); el.type = "date"; el.value = value || "";
    } else if (f.type === "text" || f.type === "wysiwyg") {
      el = document.createElement("textarea"); el.rows = f.type === "wysiwyg" ? 4 : 2; el.value = value == null ? "" : value;
    } else {
      el = document.createElement("input"); el.type = "text"; el.value = value == null ? "" : value;
    }
    return el;
  }

  function readField(el) {
    var t = el.dataset.type;
    if (t === "multiEnum") return Array.prototype.map.call(el.selectedOptions, function (o) { return o.value; });
    if (t === "bool") return el.checked;
    if (t === "int") return el.value === "" ? null : Number(el.value);
    if (t === "date") return el.value || null;
    return el.value;
  }

  $("saveBtn").addEventListener("click", async function () {
    if (!current) return;
    var changes = {};
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      changes[el.dataset.field] = readField(el);
    });
    $("saveBtn").disabled = true;
    try {
      current = await api("/mentors/" + encodeURIComponent(current.id), { method: "PUT", body: JSON.stringify({ changes: changes }) });
      listDirty = true;
      $("detailName").textContent = current.name || "(unnamed mentor)";
      renderReadonly(current);
      notice("detailNotice", "Saved.", "success");
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
