/* Session Management — one frontend, three domains. The domain (and API base)
   is the first segment of this page's own URL (/mentorsessions, /partnersessions,
   /sponsorsessions), so the same files serve all three routes. */
(function () {
  "use strict";

  // "/mentorsessions/..." -> API base "/mentorsessions/api"
  var SLUG = (location.pathname.split("/")[1] || "").toLowerCase();
  var API = "/" + SLUG + "/api";

  var config = null;        // from /session (title, columns, parentLabel, …)
  var fieldSpec = [];       // CSession editable-field spec
  var fieldOptions = {};    // {fieldName: [options]}
  var fieldRequired = [];   // field names the CRM marks required (e.g. dateStart)
  var records = [];         // owned parents (grid)
  var currentDetail = null; // the open parent detail (has contacts/sessions)
  var currentSession = null;// the session being edited (null attendees only for new)
  var editorSnapshot = {};  // {field: JSON of value at render} — save diffs against this
  var search = "";

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
  function showLogin() { location.href = "/?next=" + encodeURIComponent("/" + SLUG + "/"); }
  function showMessage(text) { hideAll(); $("msgText").textContent = text; show($("msgView")); }
  function bootFail(e) {
    if (e && e.status === 401) { showLogin(); return; }
    if (e && e.status === 403) { showMessage(e.message); return; }
    showMessage("The server isn't responding right now. Please try again in a moment.");
  }
  function hideAll() { hide($("msgView")); hide($("listView")); hide($("detailView")); hide($("editorView")); }
  function showList() { hideAll(); show($("listView")); }
  function showDetail() { hideAll(); show($("detailView")); }
  function showEditor() { hideAll(); show($("editorView")); }

  function notice(elId, text, kind) {
    var n = $(elId); n.textContent = text;
    n.className = "sx__notice " + (kind === "error" ? "is-error" : "is-success");
    show(n); n.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) {}
    location.href = "/";
  });
  $("refreshBtn").addEventListener("click", function () { loadRecords(); });
  $("search").addEventListener("input", function () { search = this.value; renderTable(); });
  $("backBtn").addEventListener("click", function () { showList(); });
  $("newSessionBtn").addEventListener("click", function () { openEditor(null); });
  $("editorBackBtn").addEventListener("click", function () { if (currentDetail) openDetail(currentDetail.id); });
  $("saveSessionBtn").addEventListener("click", function () { saveSession(); });
  $("addCoMentorBtn").addEventListener("click", function () { addCoMentor(); });

  // --- boot ---
  (async function init() {
    try {
      config = await api("/session");
      $("title").textContent = config.title || "Sessions";
      $("subtitle").textContent = config.subtitle || "";
      document.title = "CBM — " + (config.title || "Sessions");
      $("whoName").textContent = config.name || config.userName;
      await bootList();
    } catch (e) { bootFail(e); }
  })();

  async function bootList() {
    showList();
    var fieldsError = null;
    try {
      var f = await api("/fields"); fieldSpec = f.fields || []; fieldOptions = f.options || {}; fieldRequired = f.required || [];
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      fieldsError = e.message;
    }
    await loadRecords();
    if (fieldsError) {
      notice("listNotice", "Could not load the session field definitions, so editing is unavailable. Refresh to retry. (" + fieldsError + ")", "error");
    }
  }

  // --- list ---
  async function loadRecords() {
    hide($("listNotice"));
    show($("loadingState")); hide($("recordsTable")); hide($("emptyState"));
    try {
      var res = await api("/records");
      records = res.records || [];
      if (res.profileFound === false) {
        notice("listNotice", "We couldn't find a CBM profile linked to your login, so there are no records to show. Ask an administrator to link your login to your CBM profile.", "error");
      }
      renderTable();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("listNotice", e.message, "error");
    } finally { hide($("loadingState")); }
  }

  function columns() { return (config && config.columns) || []; }

  function matches(r) {
    if (!search.trim()) return true;
    var hay = columns().map(function (c) { return r[c.key] || ""; }).join(" ").toLowerCase();
    return hay.indexOf(search.trim().toLowerCase()) >= 0;
  }

  function renderTable() {
    var head = $("recordsHead"); head.innerHTML = "";
    var htr = document.createElement("tr");
    columns().forEach(function (c) { var th = document.createElement("th"); th.textContent = c.label; htr.appendChild(th); });
    var created = document.createElement("th"); created.textContent = "Created"; htr.appendChild(created);
    head.appendChild(htr);

    var rows = records.filter(matches);
    $("count").textContent = "Showing " + rows.length + " of " + records.length;
    var tb = $("recordsBody"); tb.innerHTML = "";
    if (!rows.length) { show($("emptyState")); hide($("recordsTable")); return; }
    hide($("emptyState"));
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      columns().forEach(function (c, i) {
        var td = document.createElement("td");
        if (i === 0) {
          var link = document.createElement("button");
          link.type = "button"; link.className = "sx__link";
          link.textContent = r[c.key] || "(unnamed)";
          link.addEventListener("click", function () { openDetail(r.id); });
          td.appendChild(link);
        } else {
          td.textContent = r[c.key] || "—";
        }
        tr.appendChild(td);
      });
      var cd = document.createElement("td"); cd.textContent = fmtDate(r.createdAt); tr.appendChild(cd);
      tb.appendChild(tr);
    });
    show($("recordsTable"));
  }

  function fmtDate(v) { return v ? String(v).slice(0, 10) : "—"; }
  function fmtWhen(v) { return v ? String(v).slice(0, 16).replace("T", " ") : "—"; }

  // --- detail ---
  async function openDetail(id) {
    try { currentDetail = await api("/records/" + encodeURIComponent(id)); }
    catch (e) { if (e.status === 401) { showLogin(); return; } notice("listNotice", e.message, "error"); return; }
    $("detailName").textContent = currentDetail.name || "(unnamed)";
    hide($("detailNotice"));
    renderSummary(currentDetail);
    renderContacts(currentDetail);
    renderSessions(currentDetail);
    renderCoMentors(currentDetail);
    showDetail();
    window.scrollTo(0, 0);
  }

  function renderSummary(d) {
    var box = $("summary"); box.innerHTML = "";
    (d.summary || []).forEach(function (item) {
      var row = document.createElement("div"); row.className = "sx__srow";
      var l = document.createElement("span"); l.className = "sx__slabel"; l.textContent = item.label;
      var v = document.createElement("span"); v.className = "sx__svalue"; v.textContent = item.value == null ? "—" : item.value;
      row.appendChild(l); row.appendChild(v); box.appendChild(row);
    });
  }

  function renderContacts(d) {
    var ul = $("contacts"); ul.innerHTML = "";
    var list = d.contacts || [];
    $("noContacts").hidden = list.length > 0;
    list.forEach(function (c) {
      var li = document.createElement("li");
      var name = document.createElement("span"); name.className = "sx__cname"; name.textContent = c.name || "(unnamed)";
      li.appendChild(name);
      if (c.title) { var t = document.createElement("span"); t.className = "sx__muted"; t.textContent = " · " + c.title; li.appendChild(t); }
      if (c.email) { var a = document.createElement("a"); a.href = "mailto:" + c.email; a.className = "sx__cmail"; a.textContent = c.email; li.appendChild(document.createElement("br")); li.appendChild(a); }
      ul.appendChild(li);
    });
  }

  function renderSessions(d) {
    var list = d.sessions || [];
    var tb = $("sessionsBody"); tb.innerHTML = "";
    $("noSessions").hidden = list.length > 0;
    $("sessionsTable").hidden = list.length === 0;
    list.forEach(function (s) {
      var tr = document.createElement("tr");
      tr.appendChild(td(s.name || "(untitled)"));
      tr.appendChild(td(s.status || "—"));
      tr.appendChild(td(s.sessionType || "—"));
      tr.appendChild(td(fmtWhen(s.dateStart)));
      var actions = document.createElement("td");
      var edit = document.createElement("button"); edit.type = "button"; edit.className = "cbm-button cbm-button--secondary sx__sm";
      edit.textContent = "Edit"; edit.addEventListener("click", function () { openEditor(s.id); });
      actions.appendChild(edit); tr.appendChild(actions);
      tb.appendChild(tr);
    });
  }
  function td(text) { var c = document.createElement("td"); c.textContent = text; return c; }

  function renderCoMentors(d) {
    var sec = $("coMentorSection");
    if (!d.supportsComentor) { sec.hidden = true; return; }
    sec.hidden = false;
    var ul = $("coMentors"); ul.innerHTML = "";
    var list = d.coMentors || [];
    $("noCoMentors").hidden = list.length > 0;
    list.forEach(function (m) { var li = document.createElement("li"); li.textContent = m.name || m.id; ul.appendChild(li); });
    loadCoMentorOptions();
  }

  async function loadCoMentorOptions() {
    var sel = $("coMentorSelect");
    if (sel.dataset.loaded) { return; }
    try {
      var res = await api("/mentors");
      sel.innerHTML = "";
      sel.appendChild(new Option("Choose a co-mentor…", ""));
      (res.mentors || []).forEach(function (m) { sel.appendChild(new Option(m.name || m.id, m.id)); });
      sel.dataset.loaded = "1";
    } catch (e) { /* leave the picker empty; the section still shows current co-mentors */ }
  }

  async function addCoMentor() {
    var sel = $("coMentorSelect"); var id = sel.value;
    if (!id || !currentDetail) return;
    $("addCoMentorBtn").disabled = true;
    try {
      await api("/records/" + encodeURIComponent(currentDetail.id) + "/comentors", {
        method: "POST", body: JSON.stringify({ mentorProfileId: id })
      });
      notice("detailNotice", "Co-mentor added.", "success");
      openDetail(currentDetail.id);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailNotice", e.message, "error");
    } finally { $("addCoMentorBtn").disabled = false; }
  }

  // --- session editor ---
  async function openEditor(sessionId) {
    if (sessionId) {
      try { currentSession = await api("/sessions/" + encodeURIComponent(sessionId)); }
      catch (e) { if (e.status === 401) { showLogin(); return; } notice("detailNotice", e.message, "error"); return; }
      $("editorTitle").textContent = "Edit session";
    } else {
      currentSession = {
        id: null, attendees: [],
        status: "Planned",
        sessionType: (config && config.defaultSessionType) || "",
      };
      $("editorTitle").textContent = "New session";
    }
    hide($("editorNotice"));
    renderForm(currentSession);
    snapshotForm();
    renderAttendees();
    showEditor();
    window.scrollTo(0, 0);
  }

  // Baseline every field's rendered value so saveSession can send only what the
  // user actually changed. Re-sending an unchanged enum whose stored value has
  // drifted out of the CRM's current options would make EspoCRM 400 the whole
  // update (validationFailure), so an untouched field must never be resent.
  function snapshotForm() {
    editorSnapshot = {};
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-field]"), function (el) {
      editorSnapshot[el.dataset.field] = JSON.stringify(readField(el));
    });
  }

  function renderForm(values) {
    var form = $("sessionForm"); form.innerHTML = "";
    var tabs = $("editorTabs"); tabs.innerHTML = "";
    var groups = {}, order = [];
    fieldSpec.forEach(function (f) { if (!groups[f.group]) { groups[f.group] = []; order.push(f.group); } groups[f.group].push(f); });
    order.forEach(function (group) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "sx__tab"; btn.textContent = group; btn.dataset.tab = group;
      btn.setAttribute("role", "tab");
      btn.addEventListener("click", function () { activateTab(group); });
      tabs.appendChild(btn);
      var panel = document.createElement("div"); panel.className = "tab-panel"; panel.dataset.panel = group;
      var rows = {}, rowOrder = [];
      groups[group].forEach(function (f) { var r = f.row || "_d"; if (!rows[r]) { rows[r] = []; rowOrder.push(r); } rows[r].push(f); });
      rowOrder.forEach(function (r) {
        var rowEl = document.createElement("div"); rowEl.className = "tab-row";
        rows[r].forEach(function (f) { rowEl.appendChild(buildField(f, values[f.name])); });
        panel.appendChild(rowEl);
      });
      form.appendChild(panel);
    });
    if (order.length) activateTab(order[0]);
  }

  function activateTab(group) {
    Array.prototype.forEach.call($("editorTabs").children, function (b) {
      var on = b.dataset.tab === group; b.classList.toggle("is-active", on); b.setAttribute("aria-selected", on);
    });
    Array.prototype.forEach.call($("sessionForm").children, function (p) { p.hidden = p.dataset.panel !== group; });
  }

  function buildField(f, value) {
    var wrap = document.createElement("div"); wrap.className = "cbm-field field-" + f.type;
    var input = makeInput(f, value); input.dataset.field = f.name; input.dataset.type = f.type;
    var required = fieldRequired.indexOf(f.name) >= 0;
    if (required) { input.dataset.required = "1"; input.dataset.label = f.label; }
    if (f.type === "bool") {
      wrap.className += " cbm-field--check";
      var lab = document.createElement("label"); lab.appendChild(input); lab.appendChild(document.createTextNode(" " + f.label));
      wrap.appendChild(lab); return wrap;
    }
    var label = document.createElement("label"); label.textContent = f.label;
    if (required) { var star = document.createElement("span"); star.className = "sx__req"; star.textContent = " *"; label.appendChild(star); }
    wrap.appendChild(label); wrap.appendChild(input); return wrap;
  }

  // datetime helpers: CRM stores "YYYY-MM-DD HH:MM:SS" (UTC); the datetime-local
  // input wants "YYYY-MM-DDTHH:MM". Times are shown/sent as-is (no tz shift).
  function toLocalInput(v) { return v ? String(v).replace(" ", "T").slice(0, 16) : ""; }
  function fromLocalInput(v) { return v ? v.replace("T", " ") + ":00" : null; }

  function makeInput(f, value) {
    var el;
    if (f.type === "enum") {
      el = document.createElement("select");
      var opts = (f.options || fieldOptions[f.name] || []).slice();
      if (value != null && value !== "" && opts.indexOf(value) < 0) opts.unshift(value);
      if (opts.indexOf("") < 0) opts.unshift("");
      opts.forEach(function (o) { el.appendChild(new Option(o === "" ? "(none)" : o, o)); });
      el.value = value == null ? "" : value;
    } else if (f.type === "multiEnum") {
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
      el = document.createElement("input"); el.type = "number"; el.value = value == null ? "" : value;
    } else if (f.type === "date") {
      el = document.createElement("input"); el.type = "date"; el.value = value || "";
    } else if (f.type === "datetime") {
      el = document.createElement("input"); el.type = "datetime-local"; el.value = toLocalInput(value);
    } else if (f.type === "wysiwyg") {
      el = makeWysiwyg(value);
    } else if (f.type === "text") {
      el = document.createElement("textarea"); el.rows = 3; el.value = value == null ? "" : value;
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
    if (t === "datetime") return fromLocalInput(el.value);
    if (t === "wysiwyg") {
      var a = el.querySelector(".wysiwyg__area");
      if (!a) return "";
      return a.textContent.trim() === "" ? "" : a.innerHTML;
    }
    return el.value;
  }

  // --- WYSIWYG (contenteditable + minimal toolbar; no external deps) ---
  var WYSIWYG_BUTTONS = [
    { title: "Bold", label: "<b>B</b>", cmd: "bold" },
    { title: "Italic", label: "<i>I</i>", cmd: "italic" },
    { title: "Bulleted list", label: "&bull;", cmd: "insertUnorderedList" },
    { title: "Numbered list", label: "1.", cmd: "insertOrderedList" },
    { title: "Remove formatting", label: "Clear", cmd: "removeFormat" },
  ];

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
    var bar = document.createElement("div"); bar.className = "wysiwyg__toolbar";
    WYSIWYG_BUTTONS.forEach(function (b) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "wysiwyg__btn"; btn.title = b.title; btn.innerHTML = b.label;
      btn.addEventListener("mousedown", function (ev) { ev.preventDefault(); });
      btn.addEventListener("click", function () { document.execCommand(b.cmd, false, null); });
      bar.appendChild(btn);
    });
    var area = document.createElement("div"); area.className = "wysiwyg__area"; area.contentEditable = "true";
    area.innerHTML = sanitizeHtml(value == null ? "" : String(value));
    el.appendChild(bar); el.appendChild(area);
    return el;
  }

  // --- attendees ---
  function renderAttendees() {
    var box = $("attendees"); box.innerHTML = "";
    var contacts = (currentDetail && currentDetail.contacts) || [];
    var chosen = (currentSession && currentSession.attendees) || [];
    $("noAttendeeOptions").hidden = contacts.length > 0;
    contacts.forEach(function (c) {
      var lab = document.createElement("label"); lab.className = "checkgrid__opt";
      var cb = document.createElement("input"); cb.type = "checkbox"; cb.value = c.id; cb.checked = chosen.indexOf(c.id) >= 0;
      cb.className = "sx__attendee";
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + (c.name || c.id)));
      box.appendChild(lab);
    });
  }

  function chosenAttendees() {
    return Array.prototype.map.call($("attendees").querySelectorAll(".sx__attendee:checked"), function (c) { return c.value; });
  }

  async function saveSession() {
    if (!currentDetail) return;
    // Enforce the CRM's required fields (e.g. dateStart) client-side so the user
    // gets a clear message instead of a raw CRM 400 (validationFailure).
    var missing = [];
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-required]"), function (el) {
      var v = readField(el);
      if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) missing.push(el.dataset.label || el.dataset.field);
    });
    if (missing.length) { notice("editorNotice", "Please complete: " + missing.join(", "), "error"); return; }
    var changes = {};
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-field]"), function (el) {
      var v = readField(el);
      // Only send fields the user actually changed (diff vs. the render-time
      // snapshot) — leaves drifted, untouched enums out of the payload.
      if (JSON.stringify(v) !== editorSnapshot[el.dataset.field]) changes[el.dataset.field] = v;
    });
    var attendees = chosenAttendees();
    $("saveSessionBtn").disabled = true;
    try {
      if (currentSession && currentSession.id) {
        await api("/sessions/" + encodeURIComponent(currentSession.id), {
          method: "PUT", body: JSON.stringify({ changes: changes, attendees: attendees })
        });
      } else {
        await api("/records/" + encodeURIComponent(currentDetail.id) + "/sessions", {
          method: "POST", body: JSON.stringify({ changes: changes, attendees: attendees })
        });
      }
      openDetail(currentDetail.id);
      notice("detailNotice", "Session saved.", "success");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("editorNotice", e.message, "error");
    } finally { $("saveSessionBtn").disabled = false; }
  }
})();
