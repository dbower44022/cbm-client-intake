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
  var confirmOnSave = null, confirmOnDiscard = null;  // unsaved-changes dialog callbacks
  var currentDetails = null;// Details tab payload for the open record (lazy-loaded)
  var detailsSnapshot = {}; // "sectionIndex:field" -> JSON of value at edit-render
  var detailsEditSet = {};  // sectionIndex -> true when that panel is in edit mode
  var currentViewSessions = []; // ordered session rows for the read-only view's prev/next
  var currentViewIndex = -1;    // position within currentViewSessions
  var search = "";
  var statusFilter = "";        // selected status value ("" = all)
  var sortKey = null;           // grid column key to sort by (null = default order)
  var sortDir = 1;              // 1 asc, -1 desc

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
  function hideAll() { hide($("msgView")); hide($("listView")); hide($("detailView")); hide($("editorView")); hide($("sessionView")); }
  function showList() { hideAll(); show($("listView")); }
  function showDetail() { hideAll(); show($("detailView")); }
  function showEditor() { hideAll(); show($("editorView")); }
  function showSessionView() { hideAll(); show($("sessionView")); }

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
  $("statusFilter").addEventListener("change", function () { statusFilter = this.value; renderTable(); });
  $("backBtn").addEventListener("click", function () { showList(); });
  $("newSessionBtn").addEventListener("click", function () { openEditor(null); });
  $("editorBackBtn").addEventListener("click", function () { leaveEditor(); });
  $("saveSessionBtn").addEventListener("click", function () { saveSession(); });
  $("addCoMentorBtn").addEventListener("click", function () { addCoMentor(); });
  // Read-only session view.
  $("viewBackBtn").addEventListener("click", function () { showDetail(); });
  $("viewPrevBtn").addEventListener("click", function () { stepSessionView(-1); });
  $("viewNextBtn").addEventListener("click", function () { stepSessionView(1); });
  $("viewEditBtn").addEventListener("click", function () {
    var s = currentViewSessions[currentViewIndex]; if (s) openEditor(s.id);
  });
  document.addEventListener("keydown", function (e) {
    if ($("sessionView").hidden) return;
    if (e.key === "ArrowLeft") { stepSessionView(-1); } else if (e.key === "ArrowRight") { stepSessionView(1); }
  });

  // Detail tabs are built from the domain config (see buildDetailTabs, called
  // once config loads).
  // Details tab uses per-panel Edit/Save/Cancel, wired per panel in renderDetails.
  // Pop-up detail modal.
  $("peekClose").addEventListener("click", closePeek);
  $("peekCopy").addEventListener("click", function () {
    if (!peekCopyText) return;
    var btn = $("peekCopy");
    var done = function () { btn.textContent = "✓ Copied"; setTimeout(function () { btn.textContent = "⧉ Copy"; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(peekCopyText).then(done, function () { fallbackCopy(peekCopyText); done(); });
    } else { fallbackCopy(peekCopyText); done(); }
  });
  $("peekBackdrop").addEventListener("click", closePeek);
  // Unsaved-changes confirm dialog (leaving the session editor).
  $("confirmSave").addEventListener("click", function () { hide($("confirmModal")); if (confirmOnSave) confirmOnSave(); });
  $("confirmDiscard").addEventListener("click", function () { hide($("confirmModal")); if (confirmOnDiscard) confirmOnDiscard(); });
  $("confirmCancel").addEventListener("click", function () { hide($("confirmModal")); });
  $("confirmBackdrop").addEventListener("click", function () { hide($("confirmModal")); });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (!$("confirmModal").hidden) { hide($("confirmModal")); }  // Escape = keep editing
    else if (!$("peekModal").hidden) closePeek();
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
      refreshStatusFilter();
      renderTable();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("listNotice", e.message, "error");
    } finally { hide($("loadingState")); }
  }

  function columns() { return (config && config.columns) || []; }
  // All grid columns = the configured columns + the trailing date column.
  function allColumns() {
    var cols = columns().slice();
    if (config && config.dateColumn) cols.push({ key: config.dateColumn.key, label: config.dateColumn.label, date: true });
    return cols;
  }

  function matches(r) {
    if (statusFilter && config && config.statusKey && (r[config.statusKey] || "") !== statusFilter) return false;
    if (!search.trim()) return true;
    var hay = columns().map(function (c) { return r[c.key] || ""; }).join(" ").toLowerCase();
    return hay.indexOf(search.trim().toLowerCase()) >= 0;
  }

  // Populate the status filter from the distinct statuses present (keeps the
  // current selection if still available).
  function refreshStatusFilter() {
    var wrap = $("statusFilterWrap"); var key = config && config.statusKey;
    if (!key) { wrap.hidden = true; return; }
    wrap.hidden = false;
    var seen = {}, vals = [];
    records.forEach(function (r) { var v = r[key]; if (v && !seen[v]) { seen[v] = 1; vals.push(v); } });
    vals.sort();
    var sel = $("statusFilter"); sel.innerHTML = "";
    sel.appendChild(new Option("All", ""));
    vals.forEach(function (v) { sel.appendChild(new Option(v, v)); });
    if (vals.indexOf(statusFilter) < 0) statusFilter = "";
    sel.value = statusFilter;
  }

  function setSort(key) {
    if (sortKey === key) { sortDir = -sortDir; } else { sortKey = key; sortDir = 1; }
    renderTable();
  }

  function sortRows(rows) {
    if (!sortKey) return rows;
    return rows.slice().sort(function (a, b) {
      var x = a[sortKey], y = b[sortKey];
      if (x == null || x === "") return y == null || y === "" ? 0 : 1;   // blanks last
      if (y == null || y === "") return -1;
      var c = String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" });
      return c * sortDir;
    });
  }

  function renderTable() {
    var cols = allColumns();
    var head = $("recordsHead"); head.innerHTML = "";
    var htr = document.createElement("tr");
    cols.forEach(function (c) {
      var th = document.createElement("th"); th.className = "sx__th-sort";
      th.textContent = c.label;
      if (sortKey === c.key) { var ind = document.createElement("span"); ind.className = "sx__sortind"; ind.textContent = sortDir > 0 ? " ▲" : " ▼"; th.appendChild(ind); th.setAttribute("aria-sort", sortDir > 0 ? "ascending" : "descending"); }
      th.addEventListener("click", function () { setSort(c.key); });
      htr.appendChild(th);
    });
    head.appendChild(htr);

    var rows = sortRows(records.filter(matches));
    $("count").textContent = records.length ? "Showing " + rows.length + " of " + records.length : "";
    var tb = $("recordsBody"); tb.innerHTML = "";
    if (!rows.length) { show($("emptyState")); hide($("recordsTable")); return; }
    hide($("emptyState"));
    var contactKey = config && config.contactKey;
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      cols.forEach(function (c, i) {
        var td = document.createElement("td");
        if (i === 0) {
          var link = document.createElement("button");
          link.type = "button"; link.className = "sx__link";
          link.textContent = r[c.key] || "(unnamed)";
          link.addEventListener("click", function () { openDetail(r.id); });
          td.appendChild(link);
        } else if (c.date) {
          td.textContent = fmtDate(r[c.key]);
        } else if (c.key === contactKey && r.contactId && r[c.key]) {
          var cl = document.createElement("button");
          cl.type = "button"; cl.className = "sx__link";
          cl.textContent = r[c.key];
          cl.addEventListener("click", function () { openPeek("Contact", r.contactId, r[c.key]); });
          td.appendChild(cl);
        } else {
          td.textContent = r[c.key] || "—";
        }
        tr.appendChild(td);
      });
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
    var when = document.createElement("div"); when.className = "sx__next-when";
    when.textContent = fmtSessionDate(ns.dateStart, "short"); when.title = ns.dateStart || "";
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

  // Overview "Session notes" summary — the Session Summary Display Standard
  // (v0.2). Two-zone cards (tinted header band by temporal state + white body),
  // grouped Upcoming/Past, most-relevant-first, notes clamped to 4 lines.
  function renderNoteFeed(feed) {
    var box = $("noteFeed"); box.innerHTML = "";
    $("notesCount").textContent = feed.length ? "(" + feed.length + ")" : "";  // counts all
    $("noNotes").hidden = feed.length > 0;
    var upcoming = [], past = [];
    feed.forEach(function (s) { (isFutureSession(s) ? upcoming : past).push(s); });
    upcoming.sort(function (a, b) { return cmpSessionDate(a, b); });    // soonest first
    past.sort(function (a, b) { return cmpSessionDate(b, a); });        // most recent first
    // Group + label only when the list actually mixes future and past, and one
    // group has 3+ (the band tint already encodes the split at lower counts).
    var labels = upcoming.length && past.length && (upcoming.length >= 3 || past.length >= 3);
    if (upcoming.length) {
      if (labels) box.appendChild(feedLabel("Upcoming"));
      upcoming.forEach(function (s) { box.appendChild(sessionCard(s)); });
    }
    if (past.length) {
      if (labels) box.appendChild(feedLabel("Past"));
      past.forEach(function (s) { box.appendChild(sessionCard(s)); });
    }
  }

  function feedLabel(text) {
    var d = document.createElement("div"); d.className = "sx__feed-label"; d.textContent = text; return d;
  }

  // One session-summary card per the standard.
  function sessionCard(s) {
    var scls = statusClass(s.status);
    var future = isFutureSession(s);
    var card = document.createElement("div"); card.className = "sx__scard";

    var head = document.createElement("div"); head.className = "sx__scard-head " + (future ? "is-future" : "is-past");
    var date = document.createElement("span"); date.className = "sx__scard-date";
    date.textContent = fmtSessionDate(s.dateStart); date.title = s.dateStart || "";  // ISO in tooltip
    head.appendChild(date);
    if (s.sessionType) { var tc = document.createElement("span"); tc.className = "sx__chip-type"; tc.textContent = s.sessionType; head.appendChild(tc); }
    if (s.status) { var sc = document.createElement("span"); sc.className = "sx__chip-status sx__chip-" + scls; sc.textContent = s.status; head.appendChild(sc); }
    var custom = customSessionTitle(s.name);
    if (custom) { var t = document.createElement("span"); t.className = "sx__scard-title"; t.textContent = custom; head.appendChild(t); }
    var acts = document.createElement("span"); acts.className = "sx__scard-acts";
    acts.appendChild(scardBtn("View", function () { openSessionView(s.id); }));
    acts.appendChild(scardBtn("Edit", function () { openEditor(s.id); }));
    head.appendChild(acts);
    card.appendChild(head);

    var body = document.createElement("div"); body.className = "sx__scard-body";
    var att = document.createElement("div"); att.className = "sx__scard-att";
    var al = document.createElement("div"); al.className = "sx__scard-att-l"; al.textContent = "Attendees"; att.appendChild(al);
    var names = s.attendees || [];
    if (names.length) { names.forEach(function (n) { var a = document.createElement("div"); a.className = "sx__scard-att-n"; a.textContent = n; att.appendChild(a); }); }
    else { var none = document.createElement("div"); none.className = "sx__scard-att-n sx__muted"; none.textContent = "—"; att.appendChild(none); }
    body.appendChild(att);

    var notes = document.createElement("div"); notes.className = "sx__scard-notes";
    var hasNotes = s.notes && String(s.notes).trim() !== "";
    var hasNext = s.nextSteps && String(s.nextSteps).trim() !== "";
    if (hasNotes) {
      var nb = document.createElement("div"); nb.className = "sx__scard-notebody is-clamped";
      nb.innerHTML = sanitizeHtml(String(s.notes)); notes.appendChild(nb);
    } else {
      var copy = emptyNoteCopy(scls);
      if (copy) { var em = document.createElement("p"); em.className = "sx__scard-empty"; em.textContent = copy; notes.appendChild(em); }
    }
    if (hasNext) notes.appendChild(nextStepsCallout(s.nextSteps));
    body.appendChild(notes);
    card.appendChild(body);
    return card;
  }

  function scardBtn(label, fn) {
    var b = document.createElement("button"); b.type = "button"; b.className = "sx__scard-btn"; b.textContent = label;
    b.addEventListener("click", fn); return b;
  }
  function nextStepsCallout(html) {
    var box = document.createElement("div"); box.className = "sx__scallout";
    var l = document.createElement("span"); l.className = "sx__scallout-l"; l.textContent = "Next steps";
    var b = document.createElement("div"); b.className = "sx__scallout-b"; b.innerHTML = sanitizeHtml(String(html));
    box.appendChild(l); box.appendChild(b); return box;
  }
  // Auto-generated titles look like "YYYY-MM-DD - <parent>" — not shown (they
  // duplicate the date). A mentor's custom title is shown in the header.
  function customSessionTitle(name) {
    if (!name) return null;
    return /^\d{4}-\d{2}-\d{2}\s*-\s*/.test(String(name)) ? null : name;
  }
  function emptyNoteCopy(cls) {
    if (cls === "scheduled") return "Scheduled — notes are recorded when the session is held.";
    if (cls === "cancelled" || cls === "noshow") return null;  // no empty-state copy
    return "No notes recorded for this session.";              // completed / other
  }

  // --- session status + date helpers (Session Summary Display Standard) ---
  function statusClass(status) {
    var s = String(status || "").toLowerCase().replace(/[^a-z]/g, "");
    if (s === "scheduled" || s === "planned") return "scheduled";
    if (s === "completed" || s === "held" || s === "done") return "completed";
    if (s === "cancelled" || s === "canceled") return "cancelled";
    if (s === "noshow") return "noshow";
    return "other";
  }
  // Parse the CRM's "YYYY-MM-DD HH:MM:SS" as wall-clock (no tz shift — the app
  // shows/sends times as-is, matching the editor).
  function parseNaive(v) {
    if (!v) return null;
    var m = String(v).replace("T", " ").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ ](\d{2}):(\d{2}))?/);
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)) : null;
  }
  function isFutureSession(s) {
    if (statusClass(s.status) !== "scheduled") return false;
    var d = parseNaive(s.dateStart);
    return d != null && d.getTime() >= Date.now();
  }
  function cmpSessionDate(a, b) {
    var da = parseNaive(a.dateStart), db = parseNaive(b.dateStart);
    return (da ? da.getTime() : 0) - (db ? db.getTime() : 0);
  }
  // "Weekday, Month D — h:mm AM/PM"; year appended only when not the current year.
  // weekdayStyle: "long" (default, e.g. Monday) or "short" (e.g. Mon).
  function fmtSessionDate(v, weekdayStyle) {
    var d = parseNaive(v); if (!d) return "—";
    var opts = { weekday: weekdayStyle || "long", month: "long", day: "numeric" };
    if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
    return d.toLocaleDateString(undefined, opts) + " — " +
           d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }

  function tag(text, kind) {
    var s = document.createElement("span"); s.className = "sx__tag sx__tag--" + kind; s.textContent = text; return s;
  }

  // --- pop-up detail (peek) ---
  var peekCopyText = "";  // paste-ready contact card for the modal's Copy button
  function peekOpen(name) {
    $("peekName").textContent = name || "…"; $("peekKind").textContent = "";
    $("peekBody").innerHTML = "<p class='sx__muted'>Loading…</p>";
    peekCopyText = ""; $("peekCopy").hidden = true; $("peekCopy").textContent = "⧉ Copy";
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
      if (res.copyText) { peekCopyText = res.copyText; $("peekCopy").hidden = false; }
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

  // Clipboard fallback for when the async Clipboard API is unavailable (e.g.
  // non-secure origins) or denied.
  function fallbackCopy(text) {
    var ta = document.createElement("textarea"); ta.value = text;
    ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* best effort */ }
    document.body.removeChild(ta);
  }

  // --- Details tab: read-optimized by default, whole page flips to edit ---
  async function ensureDetails() {
    if (!currentDetail) return;
    if (currentDetails && currentDetails._for === currentDetail.id) return;
    await loadDetails(currentDetail.id);
  }

  async function loadDetails(id) {
    show($("detailsLoading")); $("detailsSections").innerHTML = ""; hide($("detailsNotice"));
    detailsEditSet = {};
    try {
      var res = await api("/details/" + encodeURIComponent(id));
      res._for = id; currentDetails = res;
      renderDetails();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailsNotice", e.message, "error");
    } finally { hide($("detailsLoading")); }
  }

  // Each section renders as a panel with its OWN Edit/Save/Cancel (no page-global
  // bar). View mode composes fields into readable summary blocks per entity type;
  // Edit mode keeps the full field-level form.
  function renderDetails() {
    if (!currentDetails) return;
    hide($("detailsNotice"));
    var host = $("detailsSections"); host.innerHTML = "";
    (currentDetails.sections || []).forEach(function (sec, si) {
      host.appendChild(detailPanel(sec, si));
    });
  }

  function detailPanel(sec, si) {
    var editing = !!detailsEditSet[si];
    var card = document.createElement("div"); card.className = "sx__dsection";
    var h = document.createElement("div"); h.className = "sx__dsection-h";
    var t = document.createElement("span"); t.className = "sx__dsection-t"; t.textContent = sec.title;
    h.appendChild(t);
    if (sec.entity === "Contact") { var k = document.createElement("span"); k.className = "sx__dsection-k"; k.textContent = "Contact"; h.appendChild(k); }
    if (!editing && sec.editable) {
      var edit = document.createElement("button"); edit.type = "button"; edit.className = "sx__dpanel-edit"; edit.textContent = "Edit";
      edit.addEventListener("click", function () { detailsEditSet[si] = true; replaceDetailPanel(si); });
      h.appendChild(edit);
    }
    card.appendChild(h);
    card.appendChild(editing ? detailPanelEdit(sec, si) : detailPanelView(sec));
    return card;
  }

  // Re-render just one panel (toggle view/edit) without disturbing the others.
  function replaceDetailPanel(si) {
    var host = $("detailsSections");
    var next = detailPanel(currentDetails.sections[si], si);
    if (host.children[si]) host.replaceChild(next, host.children[si]); else host.appendChild(next);
  }

  // === Edit mode (per panel): the full field-level form + Save/Cancel ===
  function detailPanelEdit(sec, si) {
    var body = document.createElement("div"); body.className = "sx__dform"; body.dataset.sectionIndex = si;
    var snap = {};
    sec.fields.forEach(function (f) {
      if (!f.editable) { body.appendChild(detailsReadField(f)); return; }
      var field = detailsEditField(f);
      body.appendChild(field);
      var el = field.querySelector("[data-field]"); if (el) snap[el.dataset.field] = JSON.stringify(readField(el));
    });
    detailsSnapshot[si] = snap;
    var actions = document.createElement("div"); actions.className = "sx__dpanel-actions";
    var notice = document.createElement("p"); notice.className = "sx__dpanel-error"; notice.hidden = true;
    var save = document.createElement("button"); save.type = "button"; save.className = "cbm-button"; save.textContent = "Save changes";
    var cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
    save.addEventListener("click", function () { savePanel(sec, si, body, save, notice); });
    cancel.addEventListener("click", function () { detailsEditSet[si] = false; replaceDetailPanel(si); });
    actions.appendChild(cancel); actions.appendChild(save);
    var wrap = document.createElement("div"); wrap.appendChild(body); wrap.appendChild(notice); wrap.appendChild(actions);
    return wrap;
  }

  // Save one panel; on failure keep the edit view open and show the error inline.
  async function savePanel(sec, si, body, saveBtn, errEl) {
    var snap = detailsSnapshot[si] || {}, changes = {};
    Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
      var v = readField(el);
      if (JSON.stringify(v) !== snap[el.dataset.field]) changes[el.dataset.field] = v;
    });
    if (!Object.keys(changes).length) { detailsEditSet[si] = false; replaceDetailPanel(si); return; }
    saveBtn.disabled = true; errEl.hidden = true;
    try {
      await api("/details/" + encodeURIComponent(sec.entity) + "/" + encodeURIComponent(sec.id),
        { method: "PUT", body: JSON.stringify({ changes: changes }) });
      detailsEditSet[si] = false;
      await loadDetails(currentDetail.id);  // refresh values, all panels back to view
      notice("detailsNotice", sec.title + " saved.", "success");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      saveBtn.disabled = false;
      errEl.textContent = e.status === 403
        ? "You don't have permission to edit " + sec.title + "."
        : "Couldn't save: " + e.message;
      errEl.hidden = false;
    }
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

  // === View mode: composed summary blocks per entity type (no field grids) ===
  function detailPanelView(sec) {
    var e = sec.entity;
    if (e === "Contact") return contactSummary(sec);
    if (e === "Account") return companySummary(sec);
    if (e === "CClientProfile") return clientProfileSummary(sec);
    if (e === "CEngagement") return engagementSummary(sec);
    return genericSummary(sec);  // CPartnerProfile / CSponsorProfile
  }

  // --- summary helpers ---
  function dv(sec, name) { return (sec.values || {})[name]; }
  function dvs(sec, name) { var v = dv(sec, name); return v == null ? "" : String(v); }
  function dvArr(sec, name) { var v = dv(sec, name); return Array.isArray(v) ? v : []; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function cityLine(city, state, zip) {
    var region = [state, zip].filter(Boolean).join(" ");
    return [city, region].filter(Boolean).join(", ");
  }
  function fmtLongDate(v) { var d = parseNaive(v); return d ? d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }) : String(v); }
  function fmtMonthYear(v) { var d = parseNaive(v); return d ? d.toLocaleDateString(undefined, { year: "numeric", month: "long" }) : String(v); }
  function txtLine(t) { var d = document.createElement("div"); d.textContent = t; return d; }
  function factsLine(html) { var d = document.createElement("div"); d.className = "sx__dfacts"; d.innerHTML = html; return d; }
  function ledeLine(html) { var d = document.createElement("div"); d.className = "sx__lede"; d.innerHTML = html; return d; }
  function badgeRow(label, vals) {
    var row = document.createElement("div"); row.className = "sx__chips";
    var l = document.createElement("span"); l.className = "sx__chip-l"; l.textContent = label; row.appendChild(l);
    vals.forEach(function (o) { var c = document.createElement("span"); c.className = "sx__chip"; c.textContent = o; row.appendChild(c); });
    return row;
  }
  function noDetails() { var p = document.createElement("p"); p.className = "sx__muted sx__dbody"; p.textContent = "No details on file."; return p; }
  // Acceptance flag — surfaces only when NOT accepted (operationally meaningful).
  function acceptFlag(label, v) { return v === true ? null : label + ' <span class="sx__flag-no">not accepted</span>'; }

  function contactSummary(sec) {
    var wrap = document.createElement("div"); wrap.className = "sx__dbody sx__cols2";
    var dir = document.createElement("div"); dir.className = "sx__dir";
    var name = [dvs(sec, "salutationName"), dvs(sec, "firstName"), dvs(sec, "lastName")].filter(Boolean).join(" ");
    var pref = dvs(sec, "cPreferredName");
    if (pref && pref !== dvs(sec, "firstName")) name += " (" + pref + ")";
    var nm = document.createElement("div"); nm.className = "sx__dir-name"; nm.textContent = name || sec.name || "(unnamed)"; dir.appendChild(nm);
    if (dvs(sec, "addressStreet")) dir.appendChild(txtLine(dvs(sec, "addressStreet")));
    var cl = cityLine(dvs(sec, "addressCity"), dvs(sec, "addressState"), dvs(sec, "addressPostalCode")); if (cl) dir.appendChild(txtLine(cl));
    if (dvs(sec, "addressCountry")) dir.appendChild(txtLine(dvs(sec, "addressCountry")));
    if (dvs(sec, "phoneNumber")) dir.appendChild(txtLine(dvs(sec, "phoneNumber")));
    var email = dvs(sec, "emailAddress");
    if (email) { var ed = document.createElement("div"); var a = document.createElement("a"); a.href = "mailto:" + email; a.textContent = email; ed.appendChild(a); dir.appendChild(ed); }
    wrap.appendChild(dir);
    var right = document.createElement("div");
    var bits = [];
    var ct = dvArr(sec, "cContactType"); if (ct.length) bits.push("<b>" + esc(ct.join(", ")) + "</b> contact");
    if (dvs(sec, "cPreferredContactMethod")) bits.push("prefers <b>" + esc(dvs(sec, "cPreferredContactMethod").toLowerCase()) + "</b>");
    if (dvs(sec, "cNotificationPreference")) bits.push("notifications by <b>" + esc(dvs(sec, "cNotificationPreference").toLowerCase()) + "</b>");
    if (bits.length) right.appendChild(factsLine(bits.join(" &middot; ")));
    var flags = [acceptFlag("Privacy policy", dv(sec, "cPrivacyPolicyAccepted")),
                 acceptFlag("Terms of use", dv(sec, "cTermsOfUseAccepted")),
                 acceptFlag("Code of conduct", dv(sec, "cCodeOfConductAccepted"))].filter(Boolean);
    if (flags.length) right.appendChild(factsLine(flags.join(" &middot; ")));
    if (right.children.length) wrap.appendChild(right);
    return wrap;
  }

  function companySummary(sec) {
    var wrap = document.createElement("div"); wrap.className = "sx__dbody sx__cols2";
    var dir = document.createElement("div"); dir.className = "sx__dir";
    var nm = document.createElement("div"); nm.className = "sx__dir-name"; nm.textContent = sec.name || "Company"; dir.appendChild(nm);
    if (dvs(sec, "billingAddressStreet")) dir.appendChild(txtLine(dvs(sec, "billingAddressStreet")));
    var bcl = cityLine(dvs(sec, "billingAddressCity"), dvs(sec, "billingAddressState"), dvs(sec, "billingAddressPostalCode")); if (bcl) dir.appendChild(txtLine(bcl));
    if (dvs(sec, "phoneNumber")) dir.appendChild(txtLine(dvs(sec, "phoneNumber")));
    var web = dvs(sec, "website");
    if (web) { var wd = document.createElement("div"); var a = document.createElement("a"); a.href = /^https?:\/\//i.test(web) ? web : "https://" + web; a.target = "_blank"; a.rel = "noopener"; a.textContent = web; wd.appendChild(a); dir.appendChild(wd); }
    wrap.appendChild(dir);
    var right = document.createElement("div");
    var lede = [];
    if (dvs(sec, "cOrganizationType")) lede.push("<strong>" + esc(dvs(sec, "cOrganizationType")) + "</strong>");
    if (dvs(sec, "cBusinessStage")) lede.push("<strong>" + esc(dvs(sec, "cBusinessStage")) + "</strong>");
    var ledeStr = lede.join(", ");
    if (dvs(sec, "cIndustrySector")) ledeStr += (ledeStr ? " &mdash; " : "") + esc(dvs(sec, "cIndustrySector"));
    if (ledeStr) right.appendChild(ledeLine(ledeStr));
    var bits = [];
    var at = dvArr(sec, "cAccountType"); if (at.length) bits.push("Account type <b>" + esc(at.join(", ")) + "</b>");
    if (dvs(sec, "cClientStatus")) bits.push("Client status <b>" + esc(dvs(sec, "cClientStatus")) + "</b>");
    if (dvs(sec, "cPartnerContactCadence")) bits.push("Contact cadence <b>" + esc(dvs(sec, "cPartnerContactCadence")) + "</b>");
    if (dv(sec, "cPublicAnnouncementAllowed") === false) bits.push('Public announcement <span class="sx__flag-no">not allowed</span>');
    if (bits.length) right.appendChild(factsLine(bits.join(" &middot; ")));
    var bill = [dvs(sec, "billingAddressStreet"), bcl].filter(Boolean).join(", ");
    var ship = [dvs(sec, "shippingAddressStreet"), cityLine(dvs(sec, "shippingAddressCity"), dvs(sec, "shippingAddressState"), dvs(sec, "shippingAddressPostalCode"))].filter(Boolean).join(", ");
    if (ship && ship !== bill) right.appendChild(factsLine("Shipping: " + esc(ship)));
    if (right.children.length) wrap.appendChild(right);
    return wrap;
  }

  function clientProfileSummary(sec) {
    var wrap = document.createElement("div"); wrap.className = "sx__dbody";
    var struct = [];
    if (dvs(sec, "legalEntityType")) struct.push("<strong>" + esc(dvs(sec, "legalEntityType")) + "</strong>");
    if (dv(sec, "formationDate")) struct.push("formed " + esc(fmtMonthYear(dv(sec, "formationDate"))));
    if (dv(sec, "isHomeBased") === true) struct.push("home-based");
    var fin = [];
    if (dvs(sec, "annualRevenueRange")) fin.push("revenue <strong>" + esc(dvs(sec, "annualRevenueRange")) + "</strong>");
    if (dvs(sec, "revenueTrend")) fin.push(esc(dvs(sec, "revenueTrend").toLowerCase()));
    if (dvs(sec, "profitabilityStatus")) fin.push("currently <strong>" + esc(dvs(sec, "profitabilityStatus").toLowerCase()) + "</strong>");
    var ledeStr = [struct.join(", "), fin.join(", ")].filter(Boolean).join(" &middot; ");
    if (ledeStr) wrap.appendChild(ledeLine(ledeStr));
    var sells = [];
    var ct = dvArr(sec, "primaryCustomerType"); if (ct.length) sells.push("Sells <b>" + esc(ct.join(", ")) + "</b>");
    var sc = dvArr(sec, "salesChannels"); if (sc.length) sells.push("through <b>" + esc(sc.join(", ")) + "</b>");
    if (dvs(sec, "geographicMarketReach")) sells.push("reaching a <b>" + esc(dvs(sec, "geographicMarketReach")) + "</b> market");
    if (sells.length) wrap.appendChild(factsLine(sells.join(" ")));
    var desc = dvs(sec, "description");
    if (desc) { var q = document.createElement("div"); q.className = "sx__dquote"; q.textContent = "“" + desc + "”"; wrap.appendChild(q); }
    var certs = dvArr(sec, "certificationsHeld"); if (certs.length) wrap.appendChild(badgeRow("Certifications", certs));
    var funds = dvArr(sec, "fundingSourcesUsedToDate"); if (funds.length) wrap.appendChild(badgeRow("Funding to date", funds));
    return wrap.children.length ? wrap : noDetails();
  }

  function engagementSummary(sec) {
    var wrap = document.createElement("div"); wrap.className = "sx__dbody";
    var lede = document.createElement("div"); lede.className = "sx__lede";
    var nm = document.createElement("strong"); nm.textContent = sec.name || "Engagement"; lede.appendChild(nm);
    if (dvs(sec, "engagementStatus")) { var pill = document.createElement("span"); pill.className = "sx__status-pill"; pill.textContent = dvs(sec, "engagementStatus"); lede.appendChild(pill); }
    wrap.appendChild(lede);
    var facts = [];
    if (dv(sec, "engagementStartDate")) facts.push("Started <b>" + esc(fmtLongDate(dv(sec, "engagementStartDate"))) + "</b>");
    var mentor = dvs(sec, "mentorProfileName") || namesOf(dv(sec, "assignedUsersNames"));
    if (mentor) facts.push("Mentor <b>" + esc(mentor) + "</b>");
    if (dvs(sec, "meetingCadence")) facts.push("Cadence <b>" + esc(dvs(sec, "meetingCadence")) + "</b>");
    if (facts.length) wrap.appendChild(factsLine(facts.join(" &middot; ")));
    var f2 = [];
    if (dv(sec, "lastSessionDate")) f2.push("Last session <b>" + esc(fmtLongDate(dv(sec, "lastSessionDate"))) + "</b>");
    var tot = dv(sec, "totalSessions");
    if (tot != null) f2.push("<b>" + tot + "</b> session" + (tot === 1 ? "" : "s") + " to date");
    if (f2.length) wrap.appendChild(factsLine(f2.join(" &middot; ")));
    return wrap;
  }

  function namesOf(v) { return v && typeof v === "object" ? Object.keys(v).map(function (k) { return v[k]; }).join(", ") : ""; }

  // Fallback composed summary (partner/sponsor profile): facts + badges + quotes.
  function genericSummary(sec) {
    var wrap = document.createElement("div"); wrap.className = "sx__dbody";
    var facts = [], quotes = [];
    (sec.fields || []).forEach(function (f) {
      var v = f.value;
      if (v == null || v === "" || (Array.isArray(v) && !v.length)) return;
      if (f.type === "multiEnum" && Array.isArray(v)) { wrap.appendChild(badgeRow(f.label, v)); return; }
      if (f.type === "text" || f.type === "wysiwyg") { quotes.push(f); return; }
      var out = f.type === "bool" ? (v ? "Yes" : "No") : (f.type === "date" ? fmtDate(v) : (f.type === "datetime" ? fmtWhen(v) : String(v)));
      facts.push(esc(f.label) + " <b>" + esc(out) + "</b>");
    });
    if (facts.length) wrap.insertBefore(factsLine(facts.join(" &middot; ")), wrap.firstChild);
    quotes.forEach(function (f) { var q = document.createElement("div"); q.className = "sx__dquote"; if (f.type === "wysiwyg") q.innerHTML = sanitizeHtml(String(f.value)); else q.textContent = String(f.value); wrap.appendChild(q); });
    return wrap.children.length ? wrap : noDetails();
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
      var nameCell = document.createElement("td");
      var link = document.createElement("button"); link.type = "button"; link.className = "sx__link";
      link.textContent = s.name || "(untitled)";
      link.addEventListener("click", function () { openSessionView(s.id); });
      nameCell.appendChild(link); tr.appendChild(nameCell);
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

  // --- read-only session view (with prev/next through the record's sessions) ---
  function openSessionView(sessionId) {
    currentViewSessions = (currentDetail && currentDetail.sessions) || [];
    currentViewIndex = -1;
    for (var i = 0; i < currentViewSessions.length; i++) {
      if (currentViewSessions[i].id === sessionId) { currentViewIndex = i; break; }
    }
    if (currentViewIndex < 0) {  // not in the list (shouldn't happen) — view it alone
      currentViewSessions = [{ id: sessionId }]; currentViewIndex = 0;
    }
    showSessionView();
    loadSessionView();
  }

  function stepSessionView(delta) {
    var i = currentViewIndex + delta;
    if (i < 0 || i >= currentViewSessions.length) return;
    currentViewIndex = i; loadSessionView();
  }

  async function loadSessionView() {
    var row = currentViewSessions[currentViewIndex];
    hide($("viewNotice"));
    $("viewPrevBtn").disabled = true; $("viewNextBtn").disabled = true;
    try {
      var s = await api("/sessions/" + encodeURIComponent(row.id));
      renderSessionView(s);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("viewNotice", e.message, "error");
    }
  }

  // Session detail View (Display Standard §12): summary header card (tinted band
  // per §4 + key-value grid) → Session notes → Action items callout. Transcript is
  // omitted (§12.5 — the CSST long-text field does not exist yet). Reuses the
  // summary card's status-chip and band-tint tokens; the nav row is untouched.
  function renderSessionView(s) {
    var scls = statusClass(s.status);
    var future = isFutureSession(s);
    // §12.1 nav row (unchanged) — just position + button state.
    $("viewPos").textContent = currentViewSessions.length ? (currentViewIndex + 1) + " of " + currentViewSessions.length : "";
    $("viewPrevBtn").disabled = currentViewIndex <= 0;
    $("viewNextBtn").disabled = currentViewIndex < 0 || currentViewIndex >= currentViewSessions.length - 1;

    var body = $("viewBody"); body.innerHTML = "";

    // === §12.2 Summary header card ===
    var hcard = document.createElement("div"); hcard.className = "sx__vcard";
    var band = document.createElement("div"); band.className = "sx__vband " + (future ? "is-future" : "is-past");
    var l1 = document.createElement("div"); l1.className = "sx__vband-1";
    var date = document.createElement("span"); date.className = "sx__vband-date";
    date.textContent = fmtSessionDate(s.dateStart); date.title = s.dateStart || "";  // ISO in tooltip
    l1.appendChild(date);
    if (s.status) l1.appendChild(vChip("status", s.status, scls));
    if (s.sessionType) l1.appendChild(vChip("type", s.sessionType));
    band.appendChild(l1);
    var l2 = document.createElement("div"); l2.className = "sx__vband-2";
    var custom = customSessionTitle(s.name);  // auto-generated titles never shown
    if (custom) { var ct = document.createElement("span"); ct.className = "sx__vband-title"; ct.textContent = custom; l2.appendChild(ct); }
    var eng = document.createElement("span"); eng.textContent = engagementLine(); l2.appendChild(eng);
    band.appendChild(l2);
    hcard.appendChild(band);

    var grid = document.createElement("div"); grid.className = "sx__vgrid";
    addKV(grid, "Meeting type", s.meetingType, "multiEnum");
    addKV(grid, "Location", locationValue(s), "text");
    addKV(grid, "Video meeting link", s.videoMeetingLink, "link");
    addKV(grid, "Next session", s.nextSessionDateTime, "datetime");
    // §12.4: No Show uses "Expected attendees".
    addKV(grid, scls === "noshow" ? "Expected attendees" : "Attendees", s.attendeeNames || [], "chips", true);
    hcard.appendChild(grid);
    body.appendChild(hcard);

    // === §12.3.1 Session notes (full-width reading block; no clamp) ===
    var notesZone = vZone("SESSION NOTES");
    if (s.notes && String(s.notes).trim() !== "") {
      var nb = document.createElement("div"); nb.className = "sx__vzone-body"; nb.innerHTML = sanitizeHtml(String(s.notes));
      notesZone.appendChild(nb);
    } else {
      var copy = emptyNoteCopy(scls);  // scheduled/completed get copy; cancelled/noshow get none
      if (copy) { var em = document.createElement("p"); em.className = "sx__vzone-empty"; em.textContent = copy; notesZone.appendChild(em); }
    }
    body.appendChild(notesZone);

    // === §12.3.2 Action items / next steps (gold callout; only if present) ===
    if (s.nextSteps && String(s.nextSteps).trim() !== "") {
      var cal = document.createElement("div"); cal.className = "sx__vcallout";
      var cl = document.createElement("div"); cl.className = "sx__vcallout-l"; cl.textContent = "ACTION ITEMS / NEXT STEPS";
      var cb = document.createElement("div"); cb.className = "sx__vcallout-b"; cb.innerHTML = sanitizeHtml(String(s.nextSteps));
      cal.appendChild(cl); cal.appendChild(cb); body.appendChild(cal);
    }

    // === §12.3.3 Transcript — OMITTED (§12.5: no transcript field on CSession) ===
  }

  // Reuse the summary card's chip classes/tokens (no new colors).
  function vChip(kind, text, cls) {
    var c = document.createElement("span");
    c.className = kind === "status" ? "sx__chip-status sx__chip-" + (cls || statusClass(text)) : "sx__chip-type";
    c.textContent = text; return c;
  }
  function vZone(label) {
    var z = document.createElement("div"); z.className = "sx__vzone";
    var l = document.createElement("div"); l.className = "sx__vzone-l"; l.textContent = label; z.appendChild(l); return z;
  }
  // "{parent} — {primary contact} {parentLabel}" (e.g. "Agape W8 Loss — James Koran engagement").
  function engagementLine() {
    var d = currentDetail; if (!d) return "";
    var pieces = [];
    if (d.name) pieces.push(d.name);
    var pc = viewPrimaryContactName(); if (pc) pieces.push(pc);
    var line = pieces.join(" — ");
    var label = (d.parentLabel || "").toLowerCase();
    return label ? (line + " " + label).trim() : line;
  }
  function viewPrimaryContactName() {
    var d = currentDetail; if (!d) return null;
    var list = d.contacts || [];
    for (var i = 0; i < list.length; i++) { if (list[i].id === d.primaryContactId) return list[i].name; }
    return null;
  }
  function locationValue(s) {
    return [s.meetingLocationType, s.locationDetails].filter(function (x) { return x && String(x).trim(); }).join(" — ");
  }
  // A key-value grid cell; empty values are omitted entirely (no empty boxes).
  function addKV(grid, label, value, type, span) {
    if (value == null || value === "" || (Array.isArray(value) && !value.length)) return;
    var cell = document.createElement("div"); cell.className = "sx__vkv" + (span ? " sx__vkv--span" : "");
    var l = document.createElement("div"); l.className = "sx__vkv-l"; l.textContent = label;
    var v = document.createElement("div"); v.className = "sx__vkv-v";
    if ((type === "multiEnum" || type === "chips") && Array.isArray(value)) {
      value.forEach(function (o) { var c = document.createElement("span"); c.className = "sx__chip"; c.textContent = o; v.appendChild(c); });
    } else if (type === "datetime") { v.textContent = fmtSessionDate(value); v.title = value || ""; }
    else if (type === "link") {
      var href = /^https?:\/\//i.test(value) ? value : "https://" + value;
      var a = document.createElement("a"); a.href = href; a.target = "_blank"; a.rel = "noopener"; a.textContent = value; v.appendChild(a);
    } else { v.textContent = String(value); }
    cell.appendChild(l); cell.appendChild(v); grid.appendChild(cell);
  }

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
        status: "Scheduled",
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

  // True if the editor form or attendees differ from their render-time values.
  function editorHasUnsavedChanges() {
    var dirty = false;
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-field]"), function (el) {
      if (JSON.stringify(readField(el)) !== editorSnapshot[el.dataset.field]) dirty = true;
    });
    if (dirty) return true;
    var orig = ((currentSession && currentSession.attendees) || []).slice().sort().join(",");
    var now = chosenAttendees().slice().sort().join(",");
    return orig !== now;
  }

  // Leaving the editor: if there are unsaved changes, offer to Save / Discard /
  // Keep editing (Save persists then returns; Discard drops them and returns).
  function leaveEditor() {
    if (!currentDetail) return;
    if (!editorHasUnsavedChanges()) { openDetail(currentDetail.id); return; }
    confirmOnSave = function () { saveSession(); };  // saveSession returns to the record on success
    confirmOnDiscard = function () { openDetail(currentDetail.id); };
    show($("confirmModal"));
    $("confirmSave").focus();
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
