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
  var currentDetails = null;// Details tab payload for the open record (lazy-loaded)
  var detailsSnapshot = {}; // "sectionIndex:field" -> JSON of value at edit-render
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

  // Detail tabs are built from the domain config (see buildDetailTabs, called
  // once config loads).
  // Details tab (read view + Edit toggle).
  $("detailsEditBtn").addEventListener("click", function () { renderDetails(true); });
  $("detailsSaveBtn").addEventListener("click", function () { saveDetails(); });
  $("detailsCancelBtn").addEventListener("click", function () { renderDetails(false); });
  // Pop-up detail modal.
  $("peekClose").addEventListener("click", closePeek);
  $("peekBackdrop").addEventListener("click", closePeek);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !$("peekModal").hidden) closePeek();
  });

  // Build the detail tab bar from config.detailTabs. Built-in keys (overview/
  // contacts/sessions) map to the static panels in index.html; a tab flagged
  // placeholder gets a generated "coming soon" panel.
  function buildDetailTabs() {
    var nav = $("detailTabs"); nav.innerHTML = "";
    var tabs = (config && config.detailTabs) || [
      { key: "overview", label: "Overview" },
      { key: "contacts", label: "Contacts" },
      { key: "sessions", label: "Sessions" },
    ];
    tabs.forEach(function (t, i) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "sx__tab" + (i === 0 ? " is-active" : "");
      b.dataset.dtab = t.key; b.setAttribute("role", "tab"); b.textContent = t.label;
      b.addEventListener("click", function () { activateDetailTab(t.key); });
      nav.appendChild(b);
      if (t.placeholder) ensurePlaceholderPanel(t);
    });
  }

  function ensurePlaceholderPanel(t) {
    if (document.querySelector('[data-dpanel="' + t.key + '"]')) return;
    var div = document.createElement("div");
    div.className = "sx__dpanel"; div.dataset.dpanel = t.key; div.hidden = true;
    var box = document.createElement("div"); box.className = "sx__placeholder";
    var h = document.createElement("h3"); h.textContent = t.label;
    var p = document.createElement("p"); p.className = "sx__muted";
    p.textContent = "This section is coming soon.";
    box.appendChild(h); box.appendChild(p); div.appendChild(box);
    $("detailView").appendChild(div);
  }

  function activateDetailTab(tab) {
    Array.prototype.forEach.call($("detailTabs").children, function (b) {
      var on = b.dataset.dtab === tab;
      b.classList.toggle("is-active", on); b.setAttribute("aria-selected", on);
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-dpanel]"), function (p) {
      p.hidden = p.dataset.dpanel !== tab;
    });
    if (tab === "details") ensureDetails();
  }

  // Draggable splitter: resize the facts rail (wider = more room for the
  // mentoring need). Sets --ov-left on the Overview grid; clamped to sane bounds.
  (function setupSplitter() {
    var sp = $("ovSplitter"), grid = $("ovGrid");
    if (!sp || !grid) return;
    var dragging = false;
    function clampedWidth(clientX) {
      var rect = grid.getBoundingClientRect();
      var min = 260, max = Math.max(min, rect.width * 0.72);
      return Math.min(max, Math.max(min, clientX - rect.left));
    }
    function onMove(e) {
      if (!dragging) return;
      grid.style.setProperty("--ov-left", clampedWidth(e.clientX) + "px");
      e.preventDefault();
    }
    function stop() { dragging = false; document.body.classList.remove("sx--resizing"); }
    sp.addEventListener("pointerdown", function (e) {
      dragging = true; document.body.classList.add("sx--resizing"); e.preventDefault();
    });
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    sp.addEventListener("keydown", function (e) {
      var cur = parseInt(getComputedStyle(grid).getPropertyValue("--ov-left"), 10) || 340;
      if (e.key === "ArrowLeft") { grid.style.setProperty("--ov-left", Math.max(260, cur - 24) + "px"); e.preventDefault(); }
      else if (e.key === "ArrowRight") { grid.style.setProperty("--ov-left", (cur + 24) + "px"); e.preventDefault(); }
    });
  })();

  // --- boot ---
  (async function init() {
    try {
      config = await api("/session");
      $("title").textContent = config.title || "Sessions";
      $("subtitle").textContent = config.subtitle || "";
      document.title = "CBM — " + (config.title || "Sessions");
      $("whoName").textContent = config.name || config.userName;
      if (config.emptyMessage) $("emptyState").textContent = config.emptyMessage;
      buildDetailTabs();
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
      // No linked profile / no owned records is a normal empty state, not an
      // error — the grid just shows the domain's empty message. If a record is
      // later assigned to this user, a Refresh picks it up (re-queried each call).
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
    $("count").textContent = records.length ? "Showing " + rows.length + " of " + records.length : "";
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
    $("detailKind").textContent = currentDetail.parentLabel || "";
    currentDetails = null;  // Details tab reloads for the new record on activation
    hide($("detailNotice"));
    renderOverview(currentDetail);
    renderSessions(currentDetail);
    renderCoMentors(currentDetail);
    activateDetailTab("overview");
    showDetail();
    window.scrollTo(0, 0);
  }

  // --- Overview tab: facts rail + aggregated session-notes feed ---
  function renderOverview(d) {
    var sections = $("factSections"); sections.innerHTML = "";
    var blocks = $("factBlocks"); blocks.innerHTML = "";

    // Fact cards, one per section (key identity, then activity), in config order.
    var order = [], bySection = {};
    (d.overview || []).forEach(function (item) {
      if (item.block) { blocks.appendChild(factBlock(item)); return; }
      var s = item.section || "key";
      if (!bySection[s]) { bySection[s] = []; order.push(s); }
      bySection[s].push(item);
    });
    order.forEach(function (s) {
      var card = document.createElement("div"); card.className = "sx__facts";
      bySection[s].forEach(function (item) {
        var row = document.createElement("div"); row.className = "sx__fact";
        var l = document.createElement("span"); l.className = "sx__fact-l"; l.textContent = item.label;
        var v = document.createElement("span"); v.className = "sx__fact-v";
        renderValue(v, item);
        row.appendChild(l); row.appendChild(v); card.appendChild(row);
      });
      sections.appendChild(card);
    });

    renderNextSession(d);
    renderOtherContacts(d);
    renderOverallNotes(d);
    renderNoteFeed(d.noteFeed || []);
  }

  // Bold, easy-to-read "Next session" panel (soonest upcoming session), on the
  // rail under the activity facts and above Other contacts.
  function renderNextSession(d) {
    var box = $("nextSession"); box.innerHTML = "";
    var ns = d.nextSession;
    if (!ns) return;
    var card = document.createElement("div"); card.className = "sx__next";
    var l = document.createElement("div"); l.className = "sx__next-l"; l.textContent = "Next session";
    var when = document.createElement("div"); when.className = "sx__next-when"; when.textContent = fmtWhen(ns.dateStart);
    card.appendChild(l); card.appendChild(when);
    // Start/Open: a quick way to open the session (and launch the video call if
    // one is scheduled) for editing.
    var hasVideo = !!(ns.videoMeetingLink && String(ns.videoMeetingLink).trim());
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "cbm-button sx__next-btn";
    btn.textContent = hasVideo ? "Start Session" : "Open Session";
    btn.addEventListener("click", function () { startSession(ns); });
    card.appendChild(btn);
    box.appendChild(card);
  }

  // Launch the video call (if the session has a link) in a new tab, then open the
  // session for editing.
  function startSession(ns) {
    var link = ns.videoMeetingLink && String(ns.videoMeetingLink).trim();
    if (link) {
      if (!/^https?:\/\//i.test(link)) link = "https://" + link;
      window.open(link, "_blank", "noopener");
    }
    openEditor(ns.id);
  }

  // Overall notes about the whole engagement / partner / sponsor — above the
  // per-session feed, since they're usually the most important.
  function renderOverallNotes(d) {
    var box = $("overallNotes"); box.innerHTML = "";
    var n = d.overallNotes;
    if (!n) return;
    var card = document.createElement("div"); card.className = "sx__overall";
    var h = document.createElement("h3"); h.className = "sx__overall-h"; h.textContent = n.label;
    var body = document.createElement("div"); body.className = "sx__overall-body";
    if (n.type === "html") { body.innerHTML = sanitizeHtml(String(n.value || "")); }
    else { body.className += " sx__pre"; body.textContent = n.value == null ? "" : String(n.value); }
    card.appendChild(h); card.appendChild(body); box.appendChild(card);
  }

  // "Other contacts" (engagement contacts besides the primary, labeled) + the
  // co-mentors list — on the Overview rail, above the mentoring-need block.
  function renderOtherContacts(d) {
    var box = $("otherContacts"); box.innerHTML = "";
    var others = (d.contacts || []).filter(function (c) { return c.id !== d.primaryContactId; });
    var coMentors = (d.supportsComentor && d.coMentors) || [];
    if (!others.length && !coMentors.length) return;

    var card = document.createElement("div"); card.className = "sx__facts sx__ocard";
    if (others.length) {
      card.appendChild(cardHead("Other contacts"));
      others.forEach(function (c) {
        var row = document.createElement("div"); row.className = "sx__oc";
        var b = document.createElement("button"); b.type = "button"; b.className = "sx__peek";
        b.textContent = c.name || "(unnamed)";
        b.addEventListener("click", function () { openPeek("Contact", c.id, c.name || ""); });
        row.appendChild(b);
        if (c.title) { var t = document.createElement("span"); t.className = "sx__oc-role"; t.textContent = c.title; row.appendChild(t); }
        card.appendChild(row);
      });
    }
    if (coMentors.length) {
      card.appendChild(cardHead("CBM Contacts"));
      coMentors.forEach(function (m) {
        var row = document.createElement("div"); row.className = "sx__oc";
        var n = document.createElement("span"); n.textContent = m.name || m.id; row.appendChild(n);
        card.appendChild(row);
      });
    }
    box.appendChild(card);
  }

  function cardHead(text) {
    var h = document.createElement("div"); h.className = "sx__facts-h"; h.textContent = text; return h;
  }

  // A full-width emphasized block for a long rich-text/message overview item
  // (the mentoring need, partner notes, sponsor message).
  function factBlock(item) {
    var box = document.createElement("div"); box.className = "sx__block";
    var h = document.createElement("h4"); h.className = "sx__block-h"; h.textContent = item.label;
    var body = document.createElement("div"); body.className = "sx__block-body";
    if (item.type === "html") { body.innerHTML = sanitizeHtml(String(item.value || "")); }
    else { body.className += " sx__pre"; body.textContent = item.value == null ? "—" : String(item.value); }
    box.appendChild(h); box.appendChild(body); return box;
  }

  // Render a single overview value into `el` by its type (badge/chips/date/
  // currency/link/text). Links become buttons that open the pop-up detail panel.
  function renderValue(el, item) {
    var t = item.type, v = item.value;
    if (item.link) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "sx__peek"; b.textContent = v == null ? "(view)" : String(v);
      if (item.link.aggregate) {
        b.addEventListener("click", function () { openAggregatePeek(item.link.aggregate, String(v || "")); });
      } else {
        b.addEventListener("click", function () { openPeek(item.link.entity, item.link.id, String(v || "")); });
      }
      el.appendChild(b); return;
    }
    if (t === "badge") { el.appendChild(badge(v)); return; }
    if (t === "multiEnum" && Array.isArray(v)) {
      v.forEach(function (o) { var c = document.createElement("span"); c.className = "sx__chip"; c.textContent = o; el.appendChild(c); });
      return;
    }
    if (t === "date") { el.textContent = fmtDate(v); return; }
    if (t === "datetime") { el.textContent = fmtWhen(v); return; }
    if (t === "currency") { el.className += " sx__stat"; el.textContent = fmtMoney(v, item.currency); return; }
    el.textContent = v == null || v === "" ? "—" : String(v);
  }

  function badge(v) {
    var s = document.createElement("span"); s.className = "sx__badge";
    s.classList.add("sx__badge--" + String(v || "").toLowerCase().replace(/[^a-z0-9]+/g, "-"));
    s.textContent = v || "—"; return s;
  }

  function fmtMoney(v, cur) {
    if (v == null || v === "") return "—";
    var n = Number(v); if (isNaN(n)) return String(v);
    var s = n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    return (cur === "USD" || !cur ? "$" : cur + " ") + s;
  }

  function renderNoteFeed(feed) {
    var box = $("noteFeed"); box.innerHTML = "";
    $("notesCount").textContent = feed.length ? "(" + feed.length + ")" : "";
    $("noNotes").hidden = feed.length > 0;
    feed.forEach(function (s) {
      var card = document.createElement("div"); card.className = "sx__note";
      var head = document.createElement("div"); head.className = "sx__note-head";
      var when = document.createElement("span"); when.className = "sx__note-when"; when.textContent = fmtWhen(s.dateStart);
      head.appendChild(when);
      if (s.sessionType) { head.appendChild(tag(s.sessionType, "type")); }
      if (s.status) { head.appendChild(tag(s.status, "status")); }
      if (s.name) { var nm = document.createElement("span"); nm.className = "sx__note-name"; nm.textContent = s.name; head.appendChild(nm); }
      var editBtn = document.createElement("button");
      editBtn.type = "button"; editBtn.className = "sx__note-edit"; editBtn.textContent = "Edit";
      editBtn.addEventListener("click", function () { openEditor(s.id); });
      head.appendChild(editBtn);
      card.appendChild(head);

      // Body: attendees on the left, notes + next steps on the right.
      var main = document.createElement("div"); main.className = "sx__note-main";
      var att = document.createElement("div"); att.className = "sx__note-att";
      var atts = s.attendees || [];
      var al = document.createElement("span"); al.className = "sx__note-att-l"; al.textContent = "Attendees";
      att.appendChild(al);
      if (atts.length) {
        atts.forEach(function (n) { var a = document.createElement("span"); a.className = "sx__note-att-n"; a.textContent = n; att.appendChild(a); });
      } else {
        var none = document.createElement("span"); none.className = "sx__muted"; none.textContent = "—"; att.appendChild(none);
      }
      main.appendChild(att);

      var content = document.createElement("div"); content.className = "sx__note-content";
      var hasNotes = s.notes && String(s.notes).trim() !== "";
      var hasNext = s.nextSteps && String(s.nextSteps).trim() !== "";
      if (hasNotes) {
        var body = document.createElement("div"); body.className = "sx__note-body";
        body.innerHTML = sanitizeHtml(String(s.notes)); content.appendChild(body);
      }
      if (hasNext) {
        var ns = document.createElement("div"); ns.className = "sx__note-next";
        var nl = document.createElement("span"); nl.className = "sx__note-next-l"; nl.textContent = "Next steps";
        var nb = document.createElement("div"); nb.innerHTML = sanitizeHtml(String(s.nextSteps));
        ns.appendChild(nl); ns.appendChild(nb); content.appendChild(ns);
      }
      if (!hasNotes && !hasNext) {
        var em = document.createElement("p"); em.className = "sx__muted sx__note-empty"; em.textContent = "No notes recorded for this session.";
        content.appendChild(em);
      }
      main.appendChild(content);
      card.appendChild(main);
      box.appendChild(card);
    });
  }

  function tag(text, kind) {
    var s = document.createElement("span"); s.className = "sx__tag sx__tag--" + kind; s.textContent = text; return s;
  }

  // --- pop-up detail (peek) ---
  function peekOpen(name) {
    $("peekName").textContent = name || "…"; $("peekKind").textContent = "";
    $("peekBody").innerHTML = "<p class='sx__muted'>Loading…</p>";
    show($("peekModal"));
  }
  function peekFail(e) {
    if (e.status === 401) { closePeek(); showLogin(); return true; }
    var body = $("peekBody"); body.innerHTML = "";
    var p = document.createElement("p"); p.className = "form-error"; p.textContent = e.message; body.appendChild(p);
    return true;
  }
  function peekFieldsInto(container, fields) {
    (fields || []).forEach(function (f) {
      var row = document.createElement("div"); row.className = "sx__fact";
      var l = document.createElement("span"); l.className = "sx__fact-l"; l.textContent = f.label;
      var v = document.createElement("span"); v.className = "sx__fact-v"; renderPeekValue(v, f);
      row.appendChild(l); row.appendChild(v); container.appendChild(row);
    });
  }

  // Single record.
  async function openPeek(entity, id, name) {
    peekOpen(name);
    try {
      var res = await api("/peek/" + encodeURIComponent(entity) + "/" + encodeURIComponent(id));
      $("peekName").textContent = res.name || name || "(unnamed)";
      $("peekKind").textContent = peekLabel(entity);
      var body = $("peekBody"); body.innerHTML = "";
      if (!res.fields || !res.fields.length) { body.innerHTML = "<p class='sx__muted'>No additional details available.</p>"; return; }
      peekFieldsInto(body, res.fields);
    } catch (e) { peekFail(e); }
  }

  // Aggregated: several 1:1 org records (company Account + profile) in one modal,
  // one titled section each.
  async function openAggregatePeek(pairs, name) {
    peekOpen(name);
    $("peekKind").textContent = "Company";
    var results = [];
    for (var i = 0; i < pairs.length; i++) {
      try {
        results.push({ entity: pairs[i].entity,
          data: await api("/peek/" + encodeURIComponent(pairs[i].entity) + "/" + encodeURIComponent(pairs[i].id)) });
      } catch (e) {
        if (e.status === 401) { closePeek(); showLogin(); return; }
        results.push({ entity: pairs[i].entity, error: e.message });
      }
    }
    var title = name;
    results.forEach(function (r) { if (!title && r.data && r.data.name) title = r.data.name; });
    $("peekName").textContent = title || "(details)";
    var body = $("peekBody"); body.innerHTML = "";
    results.forEach(function (r) {
      var sec = document.createElement("div"); sec.className = "sx__peek-sec";
      var h = document.createElement("div"); h.className = "sx__peek-sec-h"; h.textContent = peekLabel(r.entity);
      sec.appendChild(h);
      if (r.error) { var p = document.createElement("p"); p.className = "form-error"; p.textContent = r.error; sec.appendChild(p); }
      else if (!r.data.fields || !r.data.fields.length) { var m = document.createElement("p"); m.className = "sx__muted sx__peek-empty"; m.textContent = "No details available."; sec.appendChild(m); }
      else { peekFieldsInto(sec, r.data.fields); }
      body.appendChild(sec);
    });
  }

  function renderPeekValue(el, f) {
    var v = f.value;
    if (f.type === "email" && v) { var a = document.createElement("a"); a.href = "mailto:" + v; a.textContent = v; el.appendChild(a); return; }
    if (f.type === "url" && v) { var u = document.createElement("a"); u.href = v; u.target = "_blank"; u.rel = "noopener"; u.textContent = v; el.appendChild(u); return; }
    if (f.type === "multiEnum" && Array.isArray(v)) { v.forEach(function (o) { var c = document.createElement("span"); c.className = "sx__chip"; c.textContent = o; el.appendChild(c); }); return; }
    if (f.type === "date") { el.textContent = fmtDate(v); return; }
    if (f.type === "currency") { el.textContent = fmtMoney(v, null); return; }
    if (f.type === "longtext") { el.className += " sx__pre"; el.textContent = v == null ? "—" : String(v); return; }
    el.textContent = v == null || v === "" ? "—" : String(v);
  }

  function peekLabel(entity) {
    if (entity === "Contact") return "Contact";
    if (entity === "Account") return "Company";
    if (entity === "CClientProfile") return "Client business profile";
    if (entity === "CPartnerProfile") return "Partnership profile";
    if (entity === "CSponsorProfile") return "Sponsor profile";
    return entity;
  }

  function closePeek() { hide($("peekModal")); }

  // --- Details tab: read-optimized by default, whole page flips to edit ---
  async function ensureDetails() {
    if (!currentDetail) return;
    if (currentDetails && currentDetails._for === currentDetail.id) return;
    await loadDetails(currentDetail.id);
  }

  async function loadDetails(id) {
    show($("detailsLoading")); $("detailsSections").innerHTML = ""; hide($("detailsNotice"));
    $("detailsEditBtn").hidden = true; $("detailsEditActions").hidden = true;
    try {
      var res = await api("/details/" + encodeURIComponent(id));
      res._for = id; currentDetails = res;
      renderDetails(false);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailsNotice", e.message, "error");
    } finally { hide($("detailsLoading")); }
  }

  // editing=false => read-optimized view (no edit controls); true => whole page
  // becomes the field editor with Save/Cancel.
  function detailsAnyEditable() {
    return ((currentDetails && currentDetails.sections) || []).some(function (s) { return s.editable; });
  }

  function renderDetails(editing) {
    if (!currentDetails) return;
    // Edit button only if the user can actually edit at least one section.
    $("detailsEditBtn").hidden = editing || !detailsAnyEditable();
    $("detailsEditActions").hidden = !editing;
    hide($("detailsNotice"));
    var host = $("detailsSections"); host.innerHTML = "";
    (currentDetails.sections || []).forEach(function (sec, si) {
      var sectionEditing = editing && sec.editable;  // read-only sections never show inputs
      var card = document.createElement("div"); card.className = "sx__dsection";
      var h = document.createElement("div"); h.className = "sx__dsection-h";
      var t = document.createElement("span"); t.className = "sx__dsection-t"; t.textContent = sec.title;
      h.appendChild(t);
      if (sec.entity === "Contact") { var k = document.createElement("span"); k.className = "sx__dsection-k"; k.textContent = "Contact"; h.appendChild(k); }
      if (editing && !sec.editable) { var ro = document.createElement("span"); ro.className = "sx__dsection-ro"; ro.textContent = "Read-only"; h.appendChild(ro); }
      card.appendChild(h);
      var body = document.createElement("div"); body.className = sectionEditing ? "sx__dform" : "sx__dgrid";
      body.dataset.sectionIndex = si;
      var rendered = 0;
      sec.fields.forEach(function (f) {
        if (sectionEditing) { body.appendChild(f.editable ? detailsEditField(f) : detailsReadField(f)); rendered++; return; }
        // read rendering (read mode, or a section the user can't edit): hide empties
        if (f.value == null || f.value === "" || (Array.isArray(f.value) && !f.value.length)) return;
        body.appendChild(detailsReadField(f)); rendered++;
      });
      if (!rendered) {
        var none = document.createElement("p"); none.className = "sx__muted"; none.textContent = "No details on file.";
        body.appendChild(none);
      }
      card.appendChild(body); host.appendChild(card);
    });
    if (editing) snapshotDetails();
    window.scrollTo(0, 0);
  }

  function detailsReadField(f) {
    var row = document.createElement("div"); row.className = "sx__fact";
    var l = document.createElement("span"); l.className = "sx__fact-l"; l.textContent = f.label;
    var v = document.createElement("span"); v.className = "sx__fact-v";
    var t = f.type, val = f.value;
    if (val == null || val === "" || (Array.isArray(val) && !val.length)) { v.textContent = "—"; v.className += " sx__muted"; }
    else if (t === "multiEnum" && Array.isArray(val)) { val.forEach(function (o) { var c = document.createElement("span"); c.className = "sx__chip"; c.textContent = o; v.appendChild(c); }); }
    else if (t === "bool") { v.textContent = val ? "Yes" : "No"; }
    else if (t === "date") { v.textContent = fmtDate(val); }
    else if (t === "datetime") { v.textContent = fmtWhen(val); }
    else if (t === "wysiwyg") { v.innerHTML = sanitizeHtml(String(val)); }
    else if (t === "text") { v.className += " sx__pre"; v.textContent = String(val); }
    else { v.textContent = String(val); }
    row.appendChild(l); row.appendChild(v); return row;
  }

  function detailsEditField(f) {
    var wrap = document.createElement("div"); wrap.className = "cbm-field field-" + f.type;
    var input = makeInput(f, f.value); input.dataset.field = f.name; input.dataset.type = f.type;
    if (f.type === "bool") {
      wrap.className += " cbm-field--check";
      var lab = document.createElement("label"); lab.appendChild(input); lab.appendChild(document.createTextNode(" " + f.label));
      wrap.appendChild(lab); return wrap;
    }
    var label = document.createElement("label"); label.textContent = f.label;
    wrap.appendChild(label); wrap.appendChild(input); return wrap;
  }

  function snapshotDetails() {
    detailsSnapshot = {};
    Array.prototype.forEach.call($("detailsSections").querySelectorAll("[data-section-index]"), function (body) {
      var si = body.dataset.sectionIndex;
      Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
        detailsSnapshot[si + ":" + el.dataset.field] = JSON.stringify(readField(el));
      });
    });
  }

  // Save = one PUT per entity that has changed fields (diffed vs. the edit-render
  // snapshot, so a drifted untouched enum is never resent), then reload the read view.
  async function saveDetails() {
    var sections = currentDetails.sections || [];
    var updates = [];
    Array.prototype.forEach.call($("detailsSections").querySelectorAll("[data-section-index]"), function (body) {
      var si = body.dataset.sectionIndex, sec = sections[si], changes = {};
      Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
        var v = readField(el);
        if (JSON.stringify(v) !== detailsSnapshot[si + ":" + el.dataset.field]) changes[el.dataset.field] = v;
      });
      if (Object.keys(changes).length) updates.push({ entity: sec.entity, id: sec.id, changes: changes });
    });
    if (!updates.length) { renderDetails(false); return; }
    $("detailsSaveBtn").disabled = true;
    // Save each entity independently so one denied record doesn't lose the rest.
    var okCount = 0, failures = [];
    for (var i = 0; i < updates.length; i++) {
      try {
        await api("/details/" + encodeURIComponent(updates[i].entity) + "/" + encodeURIComponent(updates[i].id),
          { method: "PUT", body: JSON.stringify({ changes: updates[i].changes }) });
        okCount++;
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        failures.push({ entity: updates[i].entity, id: updates[i].id, status: e.status, msg: e.message });
      }
    }
    $("detailsSaveBtn").disabled = false;
    await loadDetails(currentDetail.id);  // reflect whatever saved, back to read view
    if (!failures.length) { notice("detailsNotice", "Changes saved.", "success"); return; }
    var names = failures.map(function (f) { return sectionTitleFor(f.entity, f.id); });
    var msg;
    if (failures.every(function (f) { return f.status === 403; })) {
      msg = "You don't have permission to edit " + names.join(", ") +
            (okCount ? ". Your other changes were saved." : ".");
    } else {
      msg = (okCount ? "Saved " + okCount + " section(s). " : "") +
            "Couldn't save " + names.join(", ") + ": " + failures[0].msg;
    }
    notice("detailsNotice", msg, "error");
  }

  function sectionTitleFor(entity, id) {
    var list = (currentDetails && currentDetails.sections) || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].entity === entity && list[i].id === id) return list[i].title;
    }
    return entity;
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
      sel.appendChild(new Option("Choose a CBM contact…", ""));
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
      notice("detailNotice", "CBM contact added.", "success");
      openDetail(currentDetail.id);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailNotice", e.message, "error");
    } finally { $("addCoMentorBtn").disabled = false; }
  }

  // Default title shown pre-filled for a NEW session so the user sees what will
  // be stored if they don't change it: "YYYY-MM-DD - <parent name>". The user can
  // edit it; on create the app always sends the name (see saveSession), and the
  // CRM name formula is set to keep any value already present.
  function defaultSessionName() {
    var d = new Date();
    function p(n) { return (n < 10 ? "0" : "") + n; }
    var date = d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
    var parent = (currentDetail && currentDetail.name) || "";
    return parent ? date + " - " + parent : date;
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
        name: defaultSessionName(),
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
    if (f.big) wrap.className += " cbm-field--big";  // large, prominent editor (notes/action items)
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
      (f.options || fieldOptions[f.name] || []).forEach(function (o) {
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
    var isNew = !(currentSession && currentSession.id);
    var changes = {};
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-field]"), function (el) {
      var v = readField(el);
      // On create send every field (it's a new record, and the pre-filled name
      // must reach the CRM verbatim). On update send only fields the user changed
      // (diff vs. the render-time snapshot) so a drifted, untouched enum isn't
      // re-sent and rejected.
      if (isNew || JSON.stringify(v) !== editorSnapshot[el.dataset.field]) changes[el.dataset.field] = v;
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
