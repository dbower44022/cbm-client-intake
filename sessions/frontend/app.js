/* Session Management — one frontend, three domains. The domain (and API base)
   is the first segment of this page's own URL (/mentorsessions, /partnersessions,
   /sponsorsessions), so the same files serve all three routes. */
(function () {
  "use strict";

  // "/mentorsessions/..." -> API base "/mentorsessions/api".
  // "/mentorsessions/record/<id>" = the dedicated RECORD PAGE: boots straight
  // into that record — no list is loaded and there is no back-to-list.
  var _segs = location.pathname.split("/");
  var SLUG = (_segs[1] || "").toLowerCase();
  var API = "/" + SLUG + "/api";
  var RECORD_ID = _segs[2] === "record" ? decodeURIComponent(_segs[3] || "") : null;

  var config = null;        // from /session (title, columns, parentLabel, …)
  var fieldSpec = [];       // CSession editable-field spec
  var fieldOptions = {};    // {fieldName: [options]}
  var fieldRequired = [];   // field names the CRM marks required (e.g. dateStart)
  var records = [];         // owned parents (grid)
  var currentDetail = null; // the open parent detail (has contacts/sessions)
  var currentSession = null;// the session being edited (null attendees only for new)
  var editorSnapshot = {};  // {field: JSON of value at render} — save diffs against this
  // Duplicate-save protection. saveSession has THREE entry points (the Save
  // button, the unsaved-changes dialog's "Save changes", and the calendar
  // prompt's two buttons) and only the button could be disabled — so a save
  // in flight could be fired again from the other two, creating a second
  // identical session (it happened: 3 on one engagement, 2026-07-17). The flag
  // guards saveSession itself, so it covers every entry point; the token makes
  // the CREATE idempotent server-side for retries the flag can't see (lost
  // response, reload, second tab). One token per open new-session editor.
  var savingSession = false;
  var editorCreateToken = null;
  var confirmOnSave = null, confirmOnDiscard = null;  // unsaved-changes dialog callbacks
  var currentDetails = null;// Details tab payload for the open record (lazy-loaded)
  var detailsSnapshot = {}; // editKey -> {field: JSON of value at edit-render}
  var detailsEditSet = {};  // editKey ("parent"/"orgN"/"cN"/"bN") -> true when editing
  var detailsAdd = null;    // open add-contact flow: "client-menu"|"client-existing"|"client-new"|"cbm-menu"|"cbm-pick"
  var detailsDraftApply = {}; // editKey -> draft values to merge into the next form build (Restore)

  // --- Edit-draft protection (Doug's 2026-07-19 ruling: typed work must
  // survive accidents — crash, tab close, session expiry). Dirty edit-form
  // fields autosave to localStorage (7-day expiry) and are offered back when
  // the form reopens; a successful save (or a confirmed discard) clears the
  // draft. Same pattern as the compose dialogs (v0.88.0). ---
  // NOTE: names must not collide with the COMPOSE draft helpers
  // (draftKey/loadDraft/storeDraft/clearDraft, the v0.88.0 email-draft
  // persistence further down this file) — in one shared scope the later
  // function declaration silently wins, which mis-keyed these drafts once.
  var EDIT_DRAFT_TTL_MS = 7 * 24 * 3600 * 1000;
  function editDraftKey(entity, id, part) {
    return "cbmEditDraft:" + SLUG + ":" + entity + ":" + id + (part ? ":" + part : "");
  }
  function saveEditDraft(key, values) {
    try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), v: values })); } catch (_) {}
  }
  function readEditDraft(key) {
    try {
      var d = JSON.parse(localStorage.getItem(key));
      if (!d || Date.now() - d.t > EDIT_DRAFT_TTL_MS) return null;
      return d.v;
    } catch (_) { return null; }
  }
  function clearEditDraft(key) { try { localStorage.removeItem(key); } catch (_) {} }

  // Warn before leaving the page with unsaved edits (the .sxf__dirty marks
  // the live diff scan maintains, the Overview notes editor's own flag, and
  // an open session editor with changes).
  var overallNotesDirty = false;
  window.addEventListener("beforeunload", function (e) {
    var ev = document.getElementById("editorView");
    if (document.querySelector(".sxf__dirty") || overallNotesDirty ||
        (ev && !ev.hidden && editorHasUnsavedChanges())) {
      e.preventDefault(); e.returnValue = "";
    }
  });
  var currentViewSessions = []; // ordered session rows for the read-only view's prev/next
  var currentViewIndex = -1;    // position within currentViewSessions
  var senderMailbox;        // the user's own From address (/api/mailbox); undefined = not fetched yet
  var senderSignature;      // their EspoCRM Preferences signature (rides /api/mailbox)
  var composeGuard = null;  // open compose dialog's close-guard: {dirty(), discard(), send(), backConvId}
  var commTrapEl = null;    // focus-trap root while the comm modal is open
  var search = "";
  var statusFilter = "";        // selected status value ("" = all)
  var sortKey = null;           // grid column key to sort by (null = default order)
  var sortDir = 1;              // 1 asc, -1 desc

  function $(id) { return document.getElementById(id); }
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

  // A request that hangs forever is what made a save look like it had failed
  // (no spinner, no end, nothing to cancel) — the user then saved again and
  // again. Generous, because a real save can legitimately take a while: a big
  // notes body, the CRM write, the calendar hook. Long enough that a normal
  // save never trips it; short enough that a dead request ends in a readable
  // message instead of silence.
  var API_TIMEOUT_MS = 60000;

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    var ctl = window.AbortController ? new AbortController() : null;
    var timedOut = false;
    var timer = null;
    if (ctl && !opts.signal) {
      opts.signal = ctl.signal;
      timer = setTimeout(function () { timedOut = true; ctl.abort(); }, API_TIMEOUT_MS);
    }
    var resp;
    try {
      resp = await fetch(API + path, opts);
    } catch (e) {
      if (timedOut) {
        // Deliberately says a retry is safe: session creates carry an
        // idempotency token (v0.112.0), so saving again after a timeout
        // returns the session already created rather than duplicating it.
        var t = new Error(
          "The server is taking too long to respond. Nothing you typed has been "
          + "lost. Refresh the record to see whether it saved — and if it didn't, "
          + "saving again is safe (it won't create a duplicate)."
        );
        t.status = 0;
        t.timeout = true;
        throw t;
      }
      throw e;
    } finally {
      if (timer) clearTimeout(timer);
    }
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
  function hideAll() { hide($("msgView")); hide($("blockedView")); hide($("listView")); hide($("detailView")); hide($("editorView")); hide($("sessionView")); }
  function showList() { hideAll(); show($("listView")); }
  function showBlocked() { hideAll(); show($("blockedView")); }
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
  $("newSessionBtn").addEventListener("click", function () { openEditor(null); });
  $("editorBackBtn").addEventListener("click", function () { leaveEditor(); });
  // Session-editor draft autosave: any interaction inside the editor view
  // (typing, checking attendees, rich-text toolbar clicks) debounces a stash.
  ["input", "change", "keyup", "click"].forEach(function (ev) {
    $("editorView").addEventListener(ev, function () {
      clearTimeout(sessionStashTimer);
      sessionStashTimer = setTimeout(stashSessionDraft, 300);
    });
  });
  $("saveSessionBtn").addEventListener("click", function () { saveSession(); });
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
  // Communications: compose + view/reply modal.
  $("composeBtn").addEventListener("click", function () { composeMessage(null); });
  $("addEmailsBtn").addEventListener("click", function () { addEmailsDialog(); });
  $("commModalClose").addEventListener("click", requestCloseComm);
  $("commBackdrop").addEventListener("click", requestCloseComm);
  // Unsaved-changes confirm dialog (leaving the session editor).
  $("confirmSave").addEventListener("click", function () { hide($("confirmModal")); if (confirmOnSave) confirmOnSave(); });
  $("confirmDiscard").addEventListener("click", function () { hide($("confirmModal")); if (confirmOnDiscard) confirmOnDiscard(); });
  $("confirmCancel").addEventListener("click", function () { hide($("confirmModal")); });
  $("confirmBackdrop").addEventListener("click", function () { hide($("confirmModal")); });
  // Calendar-invite prompt before saving a new Scheduled session.
  $("gcalCreate").addEventListener("click", function () { hide($("gcalModal")); saveSession("create"); });
  $("gcalSkip").addEventListener("click", function () { hide($("gcalModal")); saveSession("skip"); });
  $("gcalCancel").addEventListener("click", function () { hide($("gcalModal")); });
  $("gcalBackdrop").addEventListener("click", function () { hide($("gcalModal")); });
  document.addEventListener("keydown", function (e) {
    // Ctrl/Cmd+Enter sends from anywhere inside an open compose dialog.
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" &&
        !$("commModal").hidden && composeGuard && composeGuard.send) {
      e.preventDefault(); composeGuard.send(); return;
    }
    // Keep keyboard focus inside the comm modal while it's open (focus trap).
    if (e.key === "Tab" && commTrapEl && $("confirmModal").hidden) {
      var focusables = commTrapEl.querySelectorAll(
        "button, [href], input, select, textarea, [contenteditable=true], [tabindex]:not([tabindex='-1'])"
      );
      var list = Array.prototype.filter.call(focusables, function (el) {
        return !el.hidden && el.offsetParent !== null && !el.disabled;
      });
      if (list.length) {
        var first = list[0], last = list[list.length - 1];
        if (e.shiftKey && (document.activeElement === first || !commTrapEl.contains(document.activeElement))) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        } else if (!commTrapEl.contains(document.activeElement)) {
          e.preventDefault(); first.focus();
        }
      }
    }
    if (e.key !== "Escape") return;
    if (!$("confirmModal").hidden) { hide($("confirmModal")); }  // Escape = keep editing
    else if (!$("gcalModal").hidden) { hide($("gcalModal")); }
    else if (!$("commModal").hidden) requestCloseComm();
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
    if (tab === "contributions") renderContributions();
    if (tab === "communications") renderComms();
    if (tab === "documents") renderDocuments();
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
  $("blockedReloadBtn").addEventListener("click", function () { location.reload(); });

  // --- Single-tab guard (Doug 2026-07-19): the same engagement open in two
  // browser tabs invites dirty-data edits — each tab saves values that are
  // stale relative to the other. On the dedicated record page we elect ONE
  // owner tab per record via a BroadcastChannel; a second tab opening the same
  // record yields and shows the blocked view. Deterministic tiebreak on
  // (openedAt, tabId) so even simultaneous opens pick a single owner. When the
  // owner tab closes, a blocked tab reloads to take over. Degrades to "allow"
  // where BroadcastChannel is unavailable (the named-tab reuse still helps).
  function acquireRecordLock(key) {
    return new Promise(function (resolve) {
      var BC = window.BroadcastChannel;
      if (!BC) { resolve(true); return; }
      var ch;
      try { ch = new BC("cbm-record-lock"); } catch (_) { resolve(true); return; }
      var me = { openedAt: Date.now(), tabId: Math.random().toString(36).slice(2) + "-" + Date.now() };
      var decided = false, owner = true;
      function isOlder(a, b) {
        return a.openedAt < b.openedAt || (a.openedAt === b.openedAt && a.tabId < b.tabId);
      }
      ch.onmessage = function (ev) {
        var m = ev.data || {};
        if (!m || m.key !== key || m.tabId === me.tabId) return;
        if (m.type === "hello") {
          // Announce myself so the newcomer can compare against me.
          try { ch.postMessage({ type: "present", key: key, openedAt: me.openedAt, tabId: me.tabId }); } catch (_) {}
        }
        if ((m.type === "hello" || m.type === "present") && isOlder(m, me) && !decided) {
          decided = true; owner = false; resolve(false);   // an older tab owns it — I'm the duplicate
        }
        if (m.type === "bye" && m.owner && !owner) {
          location.reload();   // the owner left — reclaim by re-running the election
        }
      };
      try { ch.postMessage({ type: "hello", key: key, openedAt: me.openedAt, tabId: me.tabId }); } catch (_) {}
      window.__cbmRecordLock = ch;   // keep the channel alive (GC guard)
      window.addEventListener("pagehide", function () {
        try { ch.postMessage({ type: "bye", key: key, tabId: me.tabId, owner: owner }); } catch (_) {}
      });
      setTimeout(function () { if (!decided) { decided = true; resolve(true); } }, 350);
    });
  }

  (async function init() {
    try {
      config = await api("/session");
      $("title").textContent = config.title || "Sessions";
      $("subtitle").textContent = config.subtitle || "";
      document.title = "CBM — " + (config.title || "Sessions");
      $("whoName").textContent = config.name || config.userName;
      if (config.emptyMessage) $("emptyState").textContent = config.emptyMessage;
      buildDetailTabs();
      if (RECORD_ID) {
        // Single-tab guard: if this engagement is already open in another tab,
        // block this one before loading/rendering anything editable.
        var owned = await acquireRecordLock(SLUG + ":" + RECORD_ID);
        if (!owned) { showBlocked(); return; }
        // Record page: fields only (for the session editor) — the list is
        // never fetched here.
        try {
          var rf = await api("/fields");
          fieldSpec = rf.fields || []; fieldOptions = rf.options || {}; fieldRequired = rf.required || [];
        } catch (e) { if (e.status === 401) { showLogin(); return; } }
        await openDetail(RECORD_ID);
      } else {
        await bootList();
      }
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
      // The Next Session column derives from the row's real sessions (the
      // stored CEngagement.nextSessionDateTime is never populated): soonest
      // SCHEDULED session that is today (viewer-local) or later. Falls back
      // to whatever the stored attr held. Done here so column sorting works
      // on the derived value.
      records.forEach(function (r) {
        var next = (r.upcomingSessions || []).filter(function (s) {
          return statusClass(s.status) === "scheduled" &&
            (isTodayLocal(s.dateStart) || (parseNaive(s.dateStart) || 0) >= Date.now());
        })[0];
        if (next) r.nextSession = next.dateStart;
      });
      // Both empty states are normal, not errors, but they read differently:
      // profileFound=false means no CMentorProfile is linked to this login (an
      // administrator has to link it — say so), while an empty list on a linked
      // profile just gets the domain's plain empty message. A Refresh picks up
      // either fix (re-queried each call).
      $("emptyState").textContent = res.profileFound === false
        ? (config.noProfileMessage || "Your login isn't linked to a profile — ask an administrator.")
        : (config.emptyMessage || "No records found.");
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
    var companyKey = config && config.companyKey;
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      cols.forEach(function (c, i) {
        var td = document.createElement("td");
        if (i === 0) {
          // A real link to the record's own PAGE. A plain click opens it in a
          // STABLE per-record tab (window name), so re-clicking the same record
          // reuses that tab instead of spawning a duplicate — several DIFFERENT
          // records still open side by side. Modifier/middle clicks fall through
          // to the browser (a new tab); the record page's single-tab guard then
          // blocks that duplicate.
          var link = document.createElement("a");
          link.className = "sx__link";
          link.href = "/" + SLUG + "/record/" + encodeURIComponent(r.id);
          link.textContent = r[c.key] || "(unnamed)";
          (function (recId, href) {
            link.addEventListener("click", function (ev) {
              if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
              ev.preventDefault();
              window.open(href, "cbm-rec-" + SLUG + "-" + recId);
            });
          })(r.id, link.href);
          // A record with a session scheduled TODAY (viewer-local, from the
          // server's upcomingSessions window) reads red + bold in the grid.
          if ((r.upcomingSessions || []).some(isTodaySession)) {
            link.classList.add("sx__link--today");
            link.title = "Session scheduled today";
          }
          td.appendChild(link);
        } else if (c.key === companyKey && r.companyPeek && r[c.key]) {
          // Company link -> the standard company/client pop-up (sections the
          // user's ACL can't read are omitted, so an unassigned user sees
          // only the company information).
          var comp = document.createElement("button");
          comp.type = "button"; comp.className = "sx__link";
          comp.textContent = r[c.key];
          comp.addEventListener("click", function () { openAggregatePeek(r.companyPeek, r[c.key]); });
          td.appendChild(comp);
        } else if (c.date || c.type === "date") {
          td.textContent = fmtDate(r[c.key]);
        } else if (c.type === "datetime") {
          td.textContent = fmtSessionDate(r[c.key], "short");  // "Mon, Aug 4 — 3:30 PM"
        } else if (c.key === contactKey && r.contactId && r[c.key]) {
          var cl = document.createElement("button");
          cl.type = "button"; cl.className = "sx__link";
          cl.textContent = r[c.key];
          cl.addEventListener("click", function () { openPeek("Contact", r.contactId, r[c.key]); });
          td.appendChild(cl);
        } else if (c.key === "mentor" && r.mentorId && r[c.key]) {
          // Assigned Mentor / Partner Manager -> the mentor-profile pop-up
          // (CBM + personal email render as compose/mailto links there, so
          // the assigned manager can be emailed in two clicks).
          var ml = document.createElement("button");
          ml.type = "button"; ml.className = "sx__link";
          ml.textContent = r[c.key];
          ml.addEventListener("click", function () { openPeek("CMentorProfile", r.mentorId, r[c.key]); });
          td.appendChild(ml);
        } else if (config.statusAccept && c.key === config.statusKey &&
                   r[c.key] === config.statusAccept.from) {
          // Status cell of a Pending Acceptance engagement -> a two-step accept
          // button (product convention: no browser confirm dialogs). Second
          // click sets the status to Assigned via the server (stale-guarded).
          td.appendChild(statusAcceptButton(r));
        } else {
          td.textContent = r[c.key] || "—";
        }
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    show($("recordsTable"));
  }

  // The grid's accept action: first click arms ("Accept — set to Assigned?"),
  // second click posts. A 400 means the row went stale (someone else changed
  // the status) — the message shows and the grid reloads to correct itself.
  function statusAcceptButton(r) {
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "sx__link sx__accept";
    btn.textContent = r[config.statusKey];
    btn.title = "Click to accept this engagement (sets the status to " + config.statusAccept.to + ")";
    var armed = false;
    btn.addEventListener("click", async function () {
      if (!armed) { armed = true; btn.textContent = "Accept — set to " + config.statusAccept.to + "?"; return; }
      btn.disabled = true; btn.textContent = "Saving…";
      try {
        var res = await api("/records/" + encodeURIComponent(r.id) + "/accept", { method: "POST" });
        r[config.statusKey] = (res && res.to) || config.statusAccept.to;
        notice("listNotice", "Engagement accepted — the status is now " + r[config.statusKey] + ".", "success");
        refreshStatusFilter();
        renderTable();
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        notice("listNotice", e.message, "error");
        loadRecords();  // stale guard / failure — re-sync the grid with the CRM
      }
    });
    return btn;
  }

  function fmtDate(v) { return v ? String(v).slice(0, 10) : "—"; }
  // Stored UTC stamp → "YYYY-MM-DD HH:MM" in the viewer's local time; a value
  // without a time component (date-only) is shown as-is.
  function fmtWhen(v) {
    if (!v) return "—";
    var s = String(v);
    if (!/[T ]\d{2}:\d{2}/.test(s)) return s.slice(0, 16).replace("T", " ");
    var d = parseNaive(s);
    if (!d) return s.slice(0, 16).replace("T", " ");
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) +
           " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }
  // US display phone "(216)-555-1234" via the shared formatter
  // (/shared/phone-format.js); edit inputs and tel: hrefs keep the raw value.
  function fmtPhone(v) {
    if (!v) return "";
    return window.CBM && CBM.formatPhone ? CBM.formatPhone(v) : String(v);
  }
  // Absolute external URL for a stored website/link value — a bare
  // "example.com" would otherwise resolve relative to this app's own path
  // (e.g. /mentorsessions/example.com).
  function externalHref(v) {
    v = String(v || "").trim();
    return /^https?:\/\//i.test(v) ? v : "https://" + v;
  }

  // --- detail ---
  async function openDetail(id) {
    try { currentDetail = await api("/records/" + encodeURIComponent(id)); }
    catch (e) {
      if (e.status === 401) { showLogin(); return; }
      if (RECORD_ID) { showMessage(e.message); return; }
      notice("listNotice", e.message, "error"); return;
    }
    if (RECORD_ID) document.title = (currentDetail.name || "Record") + " — CBM";
    $("detailName").textContent = currentDetail.name || "(unnamed)";
    $("detailKind").textContent = currentDetail.parentLabel || "";
    currentDetails = null;  // Details tab reloads for the new record on activation
    hide($("detailNotice"));
    renderOverview(currentDetail);
    renderSessions(currentDetail);
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
    // The meeting link itself, visible + copyable (not just behind the button),
    // so it can be pasted into an email or agenda.
    var vlink = ns.videoMeetingLink && String(ns.videoMeetingLink).trim();
    if (vlink) {
      var lrow = document.createElement("div"); lrow.className = "sx__next-link";
      lrow.appendChild(linkWithCopy(vlink));
      card.appendChild(lrow);
    }
    // Start/Open: a quick way to open the session (and launch the video call if
    // one is scheduled) for editing.
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "cbm-button sx__next-btn";
    btn.textContent = vlink ? "Start Session" : "Open Session";
    btn.addEventListener("click", function () { startSession(ns); });
    card.appendChild(btn);
    box.appendChild(card);
  }

  // Launch the video call (if the session has a link) in a new tab, then open the
  // session for editing.
  function startSession(ns) {
    var link = ns.videoMeetingLink && String(ns.videoMeetingLink).trim();
    if (link) {
      window.open(externalHref(link), "_blank", "noopener");
    }
    openEditor(ns.id);
  }

  // Overall notes about the whole engagement / partner / sponsor — above the
  // per-session feed, since they're usually the most important. The panel
  // always renders when the domain has a notes field (empty => a muted
  // placeholder), so the record-level notes are always visible at the top —
  // and editable IN PLACE (Doug's ruling 2026-07-18: notes are the most
  // important item on partners/sponsors, so no trip to the Details tab).
  // The Edit button is always active; a user without the CRM edit grant
  // gets the readable 403 on Save (buttons-never-disabled convention).
  // Long notes (Doug's rulings 2026-07-19): the panel body caps at 50% of
  // the page height (scrolls inside); a horizontal splitter under it drags
  // the cap; a View button (and right-click → View) opens the whole notes
  // in a full-page, freely resizable pop-up.
  var notesPanelPx = null;  // user-dragged cap (px); survives re-renders this page
  function renderOverallNotes(d) {
    overallNotesDirty = false;  // read view = nothing unsaved in this panel
    var box = $("overallNotes"); box.innerHTML = "";
    var n = d.overallNotes;
    if (!n) return;
    var card = document.createElement("div"); card.className = "sx__overall";
    var head = document.createElement("div"); head.className = "sx__overall-head";
    var h = document.createElement("h3"); h.className = "sx__overall-h"; h.textContent = n.label;
    head.appendChild(h);
    var btns = document.createElement("span"); btns.className = "sx__overall-btns";
    var vb = document.createElement("button");
    vb.type = "button"; vb.className = "sxd__btn"; vb.textContent = "View";
    vb.title = "Open the full " + String(n.label || "notes").toLowerCase() + " in a resizable window";
    vb.addEventListener("click", function () { viewOverallNotes(d); });
    btns.appendChild(vb);
    if (n.entity && n.attr) {
      var eb = document.createElement("button");
      eb.type = "button"; eb.className = "sxd__btn"; eb.textContent = "Edit";
      eb.addEventListener("click", function () { editOverallNotes(d); });
      btns.appendChild(eb);
    }
    head.appendChild(btns);
    var body = document.createElement("div"); body.className = "sx__overall-body sx__overall-clip";
    if (notesPanelPx) body.style.maxHeight = notesPanelPx + "px";
    var raw = n.value == null ? "" : String(n.value);
    // A wysiwyg field that's "empty" can still hold blank markup (<p><br></p>).
    var isEmpty = !raw.trim();
    if (!isEmpty && n.type === "html") {
      var probe = document.createElement("div"); probe.innerHTML = sanitizeHtml(raw);
      isEmpty = !(probe.textContent || "").trim();
    }
    if (isEmpty) {
      body.className += " sx__muted";
      body.textContent = "No " + String(n.label || "notes").toLowerCase() + " recorded yet.";
    } else if (n.type === "html") { body.innerHTML = sanitizeHtml(raw); }
    else { body.className += " sx__pre"; body.textContent = raw; }
    card.appendChild(head); card.appendChild(body);
    card.appendChild(notesResizeBar(body));
    // Right-click anywhere on the panel: View / Edit (assignments' every-
    // function-right-clickable convention).
    card.addEventListener("contextmenu", function (e) {
      e.preventDefault();
      var items = [{ label: "View", fn: function () { viewOverallNotes(d); } }];
      if (n.entity && n.attr) items.push({ label: "Edit", fn: function () { editOverallNotes(d); } });
      openContextMenu(e.clientX, e.clientY, items);
    });
    // Double-click = the fastest route to the full-page View (Doug's
    // 2026-07-19 follow-up). Not when the double-click lands on a button
    // or the drag bar — those have their own jobs.
    card.addEventListener("dblclick", function (e) {
      if (e.target.closest("button") || e.target.closest(".sx__overall-resize")) return;
      viewOverallNotes(d);
    });
    box.appendChild(card);
  }

  // The horizontal drag handle under the notes body: dragging changes the
  // body's max-height (min 6rem, max 90% of the viewport).
  function notesResizeBar(body) {
    var bar = document.createElement("div"); bar.className = "sx__overall-resize";
    bar.setAttribute("role", "separator"); bar.setAttribute("aria-orientation", "horizontal");
    bar.title = "Drag to resize the notes panel";
    bar.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      try { bar.setPointerCapture(e.pointerId); } catch (_) { /* synthetic events */ }
      var startY = e.clientY, startH = body.getBoundingClientRect().height;
      function move(ev) {
        var h = Math.min(window.innerHeight * 0.9, Math.max(96, startH + (ev.clientY - startY)));
        notesPanelPx = Math.round(h);
        body.style.maxHeight = notesPanelPx + "px";
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
    return bar;
  }

  // Small floating context menu (fixed at the cursor); click-away/Escape closes.
  function openContextMenu(x, y, items) {
    closeContextMenu();
    var m = document.createElement("div"); m.className = "sx__ctxmenu"; m.id = "sxCtxMenu";
    items.forEach(function (it) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = it.label;
      b.addEventListener("click", function () { closeContextMenu(); it.fn(); });
      m.appendChild(b);
    });
    m.style.left = x + "px"; m.style.top = y + "px";
    document.body.appendChild(m);
    // Keep it on-screen if opened near the edge.
    var r = m.getBoundingClientRect();
    if (r.right > window.innerWidth) m.style.left = Math.max(0, window.innerWidth - r.width - 4) + "px";
    if (r.bottom > window.innerHeight) m.style.top = Math.max(0, window.innerHeight - r.height - 4) + "px";
    setTimeout(function () {
      document.addEventListener("click", closeContextMenu, { once: true });
      document.addEventListener("contextmenu", closeContextMenu, { once: true });
    }, 0);
    document.addEventListener("keydown", ctxEscClose);
  }
  function ctxEscClose(e) { if (e.key === "Escape") closeContextMenu(); }
  function closeContextMenu() {
    var m = document.getElementById("sxCtxMenu");
    if (m) m.remove();
    document.removeEventListener("keydown", ctxEscClose);
  }

  // Full-page, freely resizable pop-up with the complete notes (for very long
  // notes the capped panel clips). CSS resize on the card; Escape / × /
  // backdrop close.
  function viewOverallNotes(d) {
    var n = d.overallNotes;
    if (!n) return;
    var overlay = document.createElement("div"); overlay.className = "sx__modal sx__notesview";
    var backdrop = document.createElement("div"); backdrop.className = "sx__modal-backdrop";
    backdrop.addEventListener("click", close);
    var card = document.createElement("div"); card.className = "sx__notesview-card";
    var head = document.createElement("div"); head.className = "sx__modal-head";
    var t = document.createElement("h3"); t.className = "sx__modal-name"; t.textContent = n.label;
    var x = document.createElement("button");
    x.type = "button"; x.className = "sxd__btn"; x.textContent = "Close"; x.addEventListener("click", close);
    head.appendChild(t); head.appendChild(x);
    var body = document.createElement("div"); body.className = "sx__overall-body sx__notesview-body";
    var raw = n.value == null ? "" : String(n.value);
    if (!raw.trim()) { body.className += " sx__muted"; body.textContent = "No " + String(n.label || "notes").toLowerCase() + " recorded yet."; }
    else if (n.type === "html") { body.innerHTML = sanitizeHtml(raw); }
    else { body.className += " sx__pre"; body.textContent = raw; }
    card.appendChild(head); card.appendChild(body);
    overlay.appendChild(backdrop); overlay.appendChild(card);
    document.body.appendChild(overlay);
    function esc(e) { if (e.key === "Escape") close(); }
    function close() { overlay.remove(); document.removeEventListener("keydown", esc); }
    document.addEventListener("keydown", esc);
  }

  // Swap the notes panel for an inline editor (CBMRichText for wysiwyg notes,
  // a textarea for plain-text ones). Save PUTs through the same whitelisted
  // /details endpoint the Details tab uses, then re-renders the panel; the
  // Details tab's cached copy is invalidated so it re-reads on next activation.
  function editOverallNotes(d) {
    var n = d.overallNotes;
    var box = $("overallNotes"); box.innerHTML = "";
    var card = document.createElement("div"); card.className = "sx__overall";
    var head = document.createElement("div"); head.className = "sx__overall-head";
    var h = document.createElement("h3"); h.className = "sx__overall-h"; h.textContent = n.label;
    head.appendChild(h);
    var stored = n.value == null ? "" : n.value;
    var dkey = editDraftKey(n.entity, d.id, n.attr);
    var draft = readEditDraft(dkey);
    var ftype = n.type === "html" ? "wysiwyg" : "text";
    // A stashed draft from an earlier visit opens IN the editor (with a
    // "Start fresh" escape back to the stored value — quickmail pattern).
    var input = makeInput({ name: n.attr, type: ftype }, draft != null ? draft : stored);
    input.dataset.field = n.attr; input.dataset.type = ftype;
    if (ftype === "text") input.rows = 8;
    overallNotesDirty = draft != null;
    var closed = false;  // stops the autosave debounce once the editor is done
    var err = document.createElement("p"); err.className = "sx__notice"; err.hidden = true;
    // Save/Cancel at BOTH the top (in the header, always in reach on a long
    // editor) and the bottom (Doug's ruling 2026-07-19). Shared handlers.
    var saveBtns = [];
    function doCancel(ev) {
      var btn = ev.currentTarget;
      // Compute dirtiness AT CLICK TIME (never trust the debounced flag —
      // a click inside the debounce window must still get the two-step).
      var dirtyNow = overallNotesDirty ||
        JSON.stringify(readField(input)) !== JSON.stringify(stored);
      if (dirtyNow && btn.dataset.armed !== "1") {  // two-step discard
        btn.dataset.armed = "1"; btn.textContent = "Discard changes?";
        return;
      }
      closed = true; clearEditDraft(dkey); overallNotesDirty = false;
      renderOverallNotes(d);
    }
    async function doSave() {
      var val = readField(input);
      saveBtns.forEach(function (b) { b.disabled = true; }); err.hidden = true;
      try {
        var changes = {}; changes[n.attr] = val;
        await api("/details/" + encodeURIComponent(n.entity) + "/" + encodeURIComponent(d.id),
          { method: "PUT", body: JSON.stringify({ changes: changes }) });
        n.value = val;
        closed = true; clearEditDraft(dkey); overallNotesDirty = false;
        currentDetails = null;  // the Details tab re-reads on next activation
        renderOverallNotes(d);
        notice("detailNotice", n.label + " saved.", "success");
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        saveBtns.forEach(function (b) { b.disabled = false; });
        err.textContent = e.status === 403
          ? "You don't have permission to edit " + n.label + "."
          : "Couldn't save: " + e.message;
        err.hidden = false; err.classList.add("is-error");
        err.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
    function buttonPair(cls) {
      var row = document.createElement("span"); row.className = cls;
      var cancel = document.createElement("button");
      cancel.type = "button"; cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
      cancel.addEventListener("click", doCancel);
      var save = document.createElement("button");
      save.type = "button"; save.className = "cbm-button"; save.textContent = "Save";
      save.addEventListener("click", doSave);
      row.appendChild(cancel); row.appendChild(save);
      saveBtns.push(save);
      return row;
    }
    head.appendChild(buttonPair("sx__overall-btns"));
    card.appendChild(head);
    if (draft != null) {
      var bar = document.createElement("div"); bar.className = "sxf__draftbar";
      var msg = document.createElement("span");
      msg.textContent = "Restored your unsaved changes from earlier.";
      var fresh = document.createElement("button");
      fresh.type = "button"; fresh.className = "sxd__btn"; fresh.textContent = "Start fresh";
      fresh.addEventListener("click", function () {
        closed = true; clearEditDraft(dkey); overallNotesDirty = false; editOverallNotes(d);
      });
      bar.appendChild(msg); bar.appendChild(fresh);
      card.appendChild(bar);
    }
    card.appendChild(input);
    card.appendChild(err);
    card.appendChild(buttonPair("sx__overall-actions"));
    // Autosave the draft as the user types (debounced; keyup/click cover the
    // rich-text editor, which fires no native input events on toolbar use).
    var stashTimer = null;
    function stash() {
      if (closed) return;  // a late debounce must not resurrect a cleared draft
      var v = readField(input);
      overallNotesDirty = JSON.stringify(v) !== JSON.stringify(stored);
      if (overallNotesDirty) saveEditDraft(dkey, v); else clearEditDraft(dkey);
    }
    ["input", "change", "keyup", "click"].forEach(function (ev) {
      card.addEventListener(ev, function () { clearTimeout(stashTimer); stashTimer = setTimeout(stash, 300); });
    });
    box.appendChild(card);
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
        if (m.contactId) {  // link to the co-mentor's contact info (email/phone) pop-up
          var b = document.createElement("button"); b.type = "button"; b.className = "sx__peek";
          b.textContent = m.name || m.id;
          b.addEventListener("click", function () { openPeek("Contact", m.contactId, m.name || ""); });
          row.appendChild(b);
        } else {
          var n = document.createElement("span"); n.textContent = m.name || m.id; row.appendChild(n);
        }
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
    // A scheduled session TODAY belongs under Upcoming even if its start time
    // has already passed — it's the day's business, not history.
    feed.forEach(function (s) { (isTodaySession(s) || isFutureSession(s) ? upcoming : past).push(s); });
    upcoming.sort(function (a, b) { return cmpSessionDate(a, b); });    // soonest first
    past.sort(function (a, b) { return cmpSessionDate(b, a); });        // most recent first
    // The Upcoming / Past sections ALWAYS render when there are any sessions
    // (Doug's 2026-07-16 ruling — the old "only when both groups are big
    // enough" heuristic made the split appear on some records and not others).
    if (!feed.length) return;
    box.appendChild(feedLabel("Upcoming"));
    if (upcoming.length) upcoming.forEach(function (s) { box.appendChild(sessionCard(s)); });
    else box.appendChild(feedEmpty("No upcoming sessions scheduled."));
    box.appendChild(feedLabel("Past"));
    if (past.length) past.forEach(function (s) { box.appendChild(sessionCard(s)); });
    else box.appendChild(feedEmpty("No past sessions yet."));
  }

  function feedLabel(text) {
    var d = document.createElement("div"); d.className = "sx__feed-label"; d.textContent = text; return d;
  }
  function feedEmpty(text) {
    var d = document.createElement("div"); d.className = "sx__feed-none sx__muted"; d.textContent = text; return d;
  }

  // One session-summary card per the standard.
  function sessionCard(s) {
    var scls = statusClass(s.status);
    var future = isFutureSession(s);
    var card = document.createElement("div"); card.className = "sx__scard";

    var head = document.createElement("div");
    head.className = "sx__scard-head " + (isTodaySession(s) ? "is-today" : future ? "is-future" : "is-past");
    var date = document.createElement("span"); date.className = "sx__scard-date";
    date.textContent = fmtSessionDate(s.dateStart); date.title = s.dateStart || "";  // ISO in tooltip
    head.appendChild(date);
    var dur = fmtDuration(sessionDurationSeconds(s));
    if (dur) { var du = document.createElement("span"); du.className = "sx__scard-dur"; du.textContent = dur; head.appendChild(du); }
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
  // Parse the CRM's "YYYY-MM-DD HH:MM:SS" as UTC (EspoCRM's API speaks UTC),
  // so the resulting Date renders in the viewer's local timezone — keeping the
  // app, the EspoCRM UI, and calendar events synced from the CRM in agreement.
  // A date-only "YYYY-MM-DD" stays a local calendar date (no day shift).
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function parseNaive(v) {
    if (!v) return null;
    var m = String(v).replace("T", " ").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ ](\d{2}):(\d{2}))?/);
    if (!m) return null;
    if (m[4] == null) return new Date(+m[1], +m[2] - 1, +m[3]);
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]));
  }
  function isFutureSession(s) {
    if (statusClass(s.status) !== "scheduled") return false;
    var d = parseNaive(s.dateStart);
    return d != null && d.getTime() >= Date.now();
  }
  // "Scheduled for today" — the viewer's LOCAL today (parseNaive already
  // converts the CRM's UTC stamp). A 9 AM session still counts at 5 PM: it
  // needs attention (notes, status) until its status moves off Scheduled.
  function isTodayLocal(stamp) {
    var d = parseNaive(stamp);
    if (!d) return false;
    var n = new Date();
    return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
  }
  function isTodaySession(s) {
    return statusClass(s.status) === "scheduled" && isTodayLocal(s.dateStart);
  }
  function cmpSessionDate(a, b) {
    var da = parseNaive(a.dateStart), db = parseNaive(b.dateStart);
    return (da ? da.getTime() : 0) - (db ? db.getTime() : 0);
  }
  // --- duration (CRM-virtual: dateEnd − dateStart, in seconds) ---
  // Preset choices mirroring the CRM duration field's options; used only when
  // the live metadata options aren't available.
  var DURATION_OPTIONS = [300, 600, 900, 1800, 2700, 3600, 7200, 10800];
  function sessionDurationSeconds(s) {
    var a = parseNaive(s && s.dateStart), b = parseNaive(s && s.dateEnd);
    if (!a || !b) return null;
    var secs = Math.round((b.getTime() - a.getTime()) / 1000);
    return secs > 0 ? secs : null;
  }
  function fmtDuration(secs) {
    if (secs == null || !(secs > 0)) return "";
    var h = Math.floor(secs / 3600), m = Math.round((secs % 3600) / 60);
    if (h && m) return h + "h " + m + "m";
    if (h) return h + (h === 1 ? " hour" : " hours");
    return m + " min";
  }
  // "YYYY-MM-DD HH:MM:SS" (UTC) + seconds → same format, still UTC (the result
  // goes back to the CRM as dateEnd).
  function stampPlusSeconds(stamp, secs) {
    var d = parseNaive(stamp);
    if (!d) return null;
    d = new Date(d.getTime() + secs * 1000);
    return d.getUTCFullYear() + "-" + pad2(d.getUTCMonth() + 1) + "-" + pad2(d.getUTCDate()) +
           " " + pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes()) + ":00";
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

  // --- Documents tab (Google Drive, DOC-MGMT Phases 1+2) -----------------------
  // ENABLED (config.docsEnabled, GDRIVE_DOCS server-side): list this record's
  // documents from the app's metadata table + upload new files to the shared
  // drive. DISABLED: a "coming soon" placeholder. Phase 2: View streams the
  // bytes through the app proxy into an in-app overlay (PDFs/images/text;
  // Google-native files arrive as exported PDF); the proxy URL is versioned by
  // modifiedTime and served immutable, so the BROWSER is the cache (DOC-06);
  // a lazy refresh re-syncs modifiedTimes after the metadata render (DOC-02).
  // Archive/Restore (DOC-07, Phase 3): soft delete — the file moves to the
  // record folder's /_Archived subfolder and the row leaves the default
  // list; the "Include archived" toggle reveals archived rows.

  var docTypes = [];        // upload doc-type choices (from the list endpoint)
  var docMaxMb = 0;         // server upload size cap (from the list endpoint)
  var pendingDocFile = null;  // the picked File awaiting its doc type + confirm

  function docsOn() { return !!(config && config.docsEnabled); }

  function renderDocuments() {
    hide($("docsError")); hide($("docsNotice"));
    resetDocPending();
    $("docIncludeArchived").checked = false;
    if (!docsOn()) {
      $("docPickBtn").hidden = true;
      $("docArchivedToggle").hidden = true;
      hide($("docsTable"));
      $("noDocs").textContent = "Document management is coming soon.";
      show($("noDocs"));
      return;
    }
    $("docPickBtn").hidden = false;
    $("docArchivedToggle").hidden = false;
    loadDocuments();
  }

  // The "Include archived" state rides every list/refresh call as a query
  // param, so the server returns exactly the rows the toggle asks for.
  function docListQuery() {
    return $("docIncludeArchived").checked ? "?includeArchived=true" : "";
  }

  async function loadDocuments() {
    if (!currentDetail) return;
    $("docsBody").innerHTML = "";
    $("noDocs").textContent = "Loading documents…"; show($("noDocs")); hide($("docsTable"));
    try {
      var res = await api("/records/" + encodeURIComponent(currentDetail.id) + "/documents" + docListQuery());
      docTypes = res.docTypes || [];
      docMaxMb = res.maxFileMb || docMaxMb;
      renderDocumentRows(res.documents || []);
      // DOC-02 completion: re-sync modifiedTimes from Drive AFTER the metadata
      // render (never blocks it). Best-effort — a failure leaves the list as is.
      if ((res.documents || []).length) refreshDocumentTimes();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      hide($("noDocs"));
      $("docsError").textContent = e.message; show($("docsError"));
    }
  }

  async function refreshDocumentTimes() {
    if (!currentDetail) return;
    var forId = currentDetail.id;
    try {
      var res = await api(
        "/records/" + encodeURIComponent(forId) + "/documents/refresh" + docListQuery(),
        { method: "POST" }
      );
      // The user may have moved to another record while Drive was queried.
      if (!currentDetail || currentDetail.id !== forId) return;
      docTypes = res.docTypes || docTypes;
      renderDocumentRows(res.documents || []);
    } catch (e) { /* lazy refresh is best-effort; the metadata render stands */ }
  }

  function renderDocumentRows(rows) {
    var body = $("docsBody"); body.innerHTML = "";
    if (!rows.length) {
      $("noDocs").textContent = "No documents yet — use Upload document to add the first one.";
      show($("noDocs")); hide($("docsTable")); return;
    }
    hide($("noDocs")); show($("docsTable"));
    rows.forEach(function (d) {
      var archived = d.status === "archived";
      var tr = document.createElement("tr");
      if (archived) tr.className = "sx__doc-archived-row";
      var c0 = document.createElement("td"); c0.className = "sx__doc-file"; c0.textContent = d.filename || "—";
      if (archived) c0.appendChild(tag("Archived", "flag"));
      if (d.changedInDrive) c0.appendChild(tag("Updated in Drive", "flag"));
      var c1 = document.createElement("td"); if (d.docType) c1.appendChild(tag(d.docType, "type"));
      var c2 = document.createElement("td"); c2.textContent = d.uploadedBy || "—";
      var c3 = document.createElement("td"); c3.textContent = fmtSessionDate(d.uploadedAt, "short");
      var c4 = document.createElement("td"); c4.className = "sx__doc-acts";
      ["View", "Download", "Open in Drive", archived ? "Restore" : "Archive"].forEach(function (label) {
        var b = document.createElement("button");
        b.type = "button"; b.className = "cbm-button cbm-button--secondary sx__sm";
        b.textContent = label;
        // View (DOC-03), Download (the original bytes — opens in the locally
        // installed app), Open in Drive (DOC-05), and Archive/Restore
        // (DOC-07) are all live.
        if (label === "View") {
          b.addEventListener("click", function () { openDocViewer(d); });
        } else if (label === "Download") {
          b.title = "Download the original file — open it with the application installed for its type";
          b.addEventListener("click", function () { downloadDoc(d); });
        } else if (label === "Open in Drive") {
          if (d.webViewLink) {
            b.addEventListener("click", function () {
              window.open(d.webViewLink, "_blank", "noopener");
            });
          } else {
            b.disabled = true;
          }
        } else if (label === "Archive" || label === "Restore") {
          var action = archived ? "restore" : "archive";
          b.title = archived
            ? "Move the file back to the record folder and the row back to the list"
            : "Move the file to the record's _Archived folder — it leaves this list but is never deleted";
          b.addEventListener("click", function () { lifecycleDoc(d, action, b); });
        }
        c4.appendChild(b);
      });
      tr.appendChild(c0); tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3); tr.appendChild(c4);
      body.appendChild(tr);
    });
  }

  // Archive/Restore with the product's two-step confirm (the Details-tab
  // Remove precedent): first click arms the button, second click acts;
  // the armed state disarms itself after a few seconds.
  function lifecycleDoc(d, action, btn) {
    var idle = action === "archive" ? "Archive" : "Restore";
    if (btn.dataset.armed !== "1") {
      btn.dataset.armed = "1";
      btn.textContent = "Really " + action + "?";
      setTimeout(function () {
        if (btn.isConnected && btn.dataset.armed === "1") {
          btn.dataset.armed = ""; btn.textContent = idle;
        }
      }, 4000);
      return;
    }
    btn.disabled = true; btn.textContent = idle === "Archive" ? "Archiving…" : "Restoring…";
    hide($("docsError")); hide($("docsNotice"));
    api(
      "/records/" + encodeURIComponent(currentDetail.id) + "/documents/" +
      encodeURIComponent(d.id) + "/" + action,
      { method: "POST" }
    ).then(function () {
      notice("docsNotice", action === "archive" ? "Document archived." : "Document restored.", "success");
      loadDocuments();
    }).catch(function (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("docsNotice", e.message, "error");
      loadDocuments();  // re-render — the row's true state may have changed
    });
  }

  // --- in-app document viewer (DOC-03/04/06) ---------------------------------

  // Google-native editor formats have no native bytes; the proxy serves them
  // as exported PDF (DOC-04), so they render in the PDF frame.
  var GOOGLE_NATIVE_MIMES = {
    "application/vnd.google-apps.document": true,
    "application/vnd.google-apps.spreadsheet": true,
    "application/vnd.google-apps.presentation": true,
  };
  // Office formats also arrive as PDF — the server converts on view
  // (copy-as-Google-format → export → delete temp; the stored file is
  // untouched). Keep in sync with core/gdrive.OFFICE_CONVERT_MIMES.
  var OFFICE_VIEW_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": true,
    "application/msword": true,
    "application/vnd.oasis.opendocument.text": true,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": true,
    "application/vnd.ms-excel": true,
    "application/vnd.oasis.opendocument.spreadsheet": true,
    "text/csv": true,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": true,
    "application/vnd.ms-powerpoint": true,
    "application/vnd.oasis.opendocument.presentation": true,
  };

  function docContentUrl(d) {
    // Versioned by modifiedTime: the response is immutable per URL, so the
    // browser caches the bytes and a Drive edit (new modifiedTime after the
    // lazy refresh) busts the cache automatically (DOC-06).
    return API + "/records/" + encodeURIComponent(currentDetail.id) +
      "/documents/" + encodeURIComponent(d.id) + "/content?v=" +
      encodeURIComponent(d.modifiedTime || "");
  }

  function docViewMode(d) {
    var mime = (d.mimeType || "").toLowerCase();
    if (mime === "application/pdf" || GOOGLE_NATIVE_MIMES[mime] ||
        OFFICE_VIEW_MIMES[mime] || mime === "text/plain") return "frame";
    if (mime.indexOf("image/") === 0) return "image";
    return "none";  // anything else (zip, video, …) — Open in Drive fallback
  }

  // The Download action: the stored file's EXACT bytes (formulas and all —
  // no PDF conversion), as an attachment. Google-native files export to
  // their Office equivalent (Sheets → .xlsx), like Drive's own Download.
  function downloadDoc(d) {
    var a = document.createElement("a");
    a.href = docContentUrl(d) + "&original=true";
    document.body.appendChild(a); a.click(); a.remove();
  }

  function docViewerFallback(d, failed) {
    var wrap = document.createElement("div"); wrap.className = "sx__docview-fallback";
    var p = document.createElement("p");
    p.textContent = failed
      ? "The document couldn't be loaded — try again, or use Open in Drive."
      : ("This file type can't be previewed in the app" +
         (d.webViewLink ? " — use Open in Drive to view it." : "."));
    wrap.appendChild(p);
    if (d.webViewLink) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "cbm-button";
      b.textContent = "Open in Drive";
      b.addEventListener("click", function () {
        window.open(d.webViewLink, "_blank", "noopener");
      });
      wrap.appendChild(b);
    }
    return wrap;
  }

  function openDocViewer(d) {
    var body = $("docModalBody"); body.innerHTML = "";
    $("docModalKind").textContent = d.docType || "Document";
    $("docModalTitle").textContent = d.filename || "Document";
    var driveBtn = $("docModalDrive");
    // "Download original" in the viewer header (created here, not in the
    // HTML): what the viewer SHOWS may be a PDF rendering (Office /
    // Google-native), so the browser PDF viewer's own download button saves
    // the rendering — this one always yields the stored file's exact bytes.
    var dlBtn = $("docModalDownload");
    if (!dlBtn) {
      dlBtn = document.createElement("button");
      dlBtn.type = "button"; dlBtn.id = "docModalDownload";
      dlBtn.className = "cbm-button cbm-button--secondary sx__sm";
      dlBtn.textContent = "Download original";
      driveBtn.parentNode.insertBefore(dlBtn, driveBtn);
    }
    dlBtn.onclick = function () { downloadDoc(d); };
    driveBtn.hidden = !d.webViewLink;
    driveBtn.onclick = d.webViewLink ? function () {
      window.open(d.webViewLink, "_blank", "noopener");
    } : null;
    var mode = docViewMode(d);
    if (mode === "image") {
      var img = document.createElement("img");
      img.className = "sx__docview-img"; img.alt = d.filename || "Document";
      img.addEventListener("error", function () {
        body.innerHTML = ""; body.appendChild(docViewerFallback(d, true));
      });
      img.src = docContentUrl(d);
      body.appendChild(img);
    } else if (mode === "frame") {
      var frame = document.createElement("iframe");
      frame.className = "sx__docview-frame"; frame.title = d.filename || "Document";
      frame.src = docContentUrl(d);
      body.appendChild(frame);
    } else {
      body.appendChild(docViewerFallback(d, false));
    }
    show($("docModal"));
  }

  function closeDocViewer() {
    hide($("docModal"));
    $("docModalBody").innerHTML = "";  // stop the PDF plugin / drop the bytes
  }

  $("docModalClose").addEventListener("click", closeDocViewer);
  $("docModalBackdrop").addEventListener("click", closeDocViewer);

  function resetDocPending() {
    pendingDocFile = null;
    $("docFile").value = "";
    hide($("docPending"));
    $("docUploadBtn").disabled = false; $("docUploadBtn").textContent = "Upload";
  }

  // XHR (not fetch) so the upload reports progress — a large file on a slow
  // uplink shows "Uploading… N%" instead of an inscrutable frozen button. A
  // connection that dies mid-upload gets a plain-language message, never a
  // silent reset.
  function docXhrUpload(url, file, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
      xhr.upload.onprogress = function (e) {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = function () {
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e2) {}
        if (xhr.status >= 200 && xhr.status < 300) { resolve(data); return; }
        var msg = (data && data.detail) || ("Upload failed (" + xhr.status + ")");
        var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        err.status = xhr.status;
        reject(err);
      };
      xhr.onerror = xhr.onabort = xhr.ontimeout = function () {
        reject(new Error(
          "The upload was interrupted before it finished — check your " +
          "connection and try again. If it keeps happening, tell CBM staff " +
          "the file name and size."
        ));
      };
      xhr.send(file);
    });
  }

  $("docPickBtn").addEventListener("click", function () { $("docFile").click(); });
  $("docIncludeArchived").addEventListener("change", function () {
    if (docsOn() && currentDetail) loadDocuments();
  });
  $("docCancelBtn").addEventListener("click", resetDocPending);
  $("docFile").addEventListener("change", function () {
    var f = this.files && this.files[0];
    if (!f) return;
    hide($("docsError")); hide($("docsNotice"));
    // Size gate BEFORE any upload starts: the server enforces the same cap,
    // but a clear immediate message beats a long doomed upload.
    if (docMaxMb && f.size > docMaxMb * 1024 * 1024) {
      this.value = "";
      notice("docsNotice", "“" + f.name + "” is " +
        (f.size / (1024 * 1024)).toFixed(1) + " MB — the upload limit is " +
        docMaxMb + " MB.", "error");
      return;
    }
    pendingDocFile = f;
    $("docPendingName").textContent = f.name;
    var sel = $("docTypeSelect"); sel.innerHTML = "";
    docTypes.forEach(function (t) {
      var o = document.createElement("option"); o.value = t; o.textContent = t; sel.appendChild(o);
    });
    show($("docPending"));
  });
  $("docUploadBtn").addEventListener("click", async function () {
    if (!pendingDocFile || !currentDetail) return;
    var f = pendingDocFile;
    var btn = $("docUploadBtn");
    btn.disabled = true; btn.textContent = "Uploading…";
    hide($("docsError")); hide($("docsNotice"));
    try {
      // Raw bytes (not JSON) — filename/docType ride as query params, the MIME
      // type as the Content-Type header.
      await docXhrUpload(
        API + "/records/" + encodeURIComponent(currentDetail.id) + "/documents" +
        "?filename=" + encodeURIComponent(f.name) +
        "&docType=" + encodeURIComponent($("docTypeSelect").value || ""),
        f,
        function (pct) { btn.textContent = "Uploading… " + pct + "%"; }
      );
      resetDocPending();
      notice("docsNotice", "Document uploaded.", "success");
      loadDocuments();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      btn.disabled = false; btn.textContent = "Upload";
      // The notice bar sits ABOVE the table and scrolls itself into view —
      // failures must never be silent (or hidden below the fold).
      notice("docsNotice", e.message, "error");
    }
  });

  // --- Communications tab -----------------------------------------------------
  // Two modes, switched by config.commsEnabled (GMAIL_SYNC server-side):
  //  * ENABLED: real conversations from the CRM (synced from the managers'
  //    Gmail — prds/communications-gmail-integration.md): conversation list →
  //    thread view (two-zone bodies, optional AI summary) → reply/compose →
  //    curation (remove / add-by-search).
  //  * DISABLED: the original sample-data scaffold so the layout stays
  //    reviewable before the integration is switched on.

  function commsOn() { return !!(config && config.commsEnabled); }

  // Conversation-list sorting + resizing — same capabilities as the Sessions
  // grid (v0.72.0): sortable headers (first click sorts, dates newest-first;
  // second reverses) and drag-to-resize column grips. The head is built once
  // and kept across tab revisits so resized widths survive.
  var convSort = { key: null, dir: 1 };
  var convRows = [];
  var CONV_COLUMNS = [
    { key: "status", label: "Status" },
    { key: "participants", label: "Participants" },
    { key: "subject", label: "Conversation" },
    { key: "lastMessageAt", label: "Last activity" }
  ];

  function buildConvHead() {
    var head = $("inboxHead");
    if (head.dataset.built === "conv") return;
    head.dataset.built = "conv";
    head.innerHTML = "";
    CONV_COLUMNS.forEach(function (c) {
      var th = document.createElement("th");
      th.scope = "col"; th.textContent = c.label;
      th.className = "sx__th-sort"; th.setAttribute("data-sort", c.key);
      th.addEventListener("click", function () {
        if (convSort.key === c.key) {
          convSort.dir = -convSort.dir;
        } else {
          convSort.key = c.key;
          convSort.dir = c.key === "lastMessageAt" ? -1 : 1;
        }
        renderConversationRows(convRows);
      });
      head.appendChild(th);
    });
    makeColumnsResizable($("inboxTable"));
  }

  function renderComms() {
    if (!commsOn()) { renderSampleComms(); return; }
    hide($("commBanner"));
    $("addEmailsBtn").hidden = false;
    hide($("commError"));
    buildConvHead();
    loadConversations();
  }

  async function loadConversations() {
    if (!currentDetail) return;
    // Warm the mailbox/signature cache: Reply All excludes the user's own
    // address, and the compose seeds their signature — both ride /mailbox.
    if (senderMailbox === undefined && commsOn()) {
      api("/mailbox").then(function (r) {
        senderMailbox = (r && r.mailbox) || null;
        senderSignature = (r && r.signature) || "";
      }).catch(function () { /* compose refetches on open */ });
    }
    var body = $("inboxBody"); body.innerHTML = "";
    $("noMessages").textContent = "Loading conversations…"; show($("noMessages")); hide($("inboxTable"));
    try {
      var res = await api("/records/" + encodeURIComponent(currentDetail.id) + "/conversations");
      convRows = res.conversations || [];
      renderConversationRows(convRows);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      hide($("noMessages"));
      $("commError").textContent = e.message; show($("commError"));
    }
  }

  function convSortVal(c, k) {
    if (k === "lastMessageAt") return c.lastMessageAt || "";  // UTC stamps compare as strings
    return (c[k] || "").toString().toLowerCase();
  }

  function updateConvSortIndicators() {
    Array.prototype.forEach.call(document.querySelectorAll("#inboxTable th[data-sort]"), function (th) {
      var active = th.getAttribute("data-sort") === convSort.key;
      th.setAttribute("aria-sort", active ? (convSort.dir === 1 ? "ascending" : "descending") : "none");
      th.dataset.dir = active ? (convSort.dir === 1 ? "asc" : "desc") : "";
    });
  }

  function renderConversationRows(rows) {
    var body = $("inboxBody"); body.innerHTML = "";
    updateConvSortIndicators();
    if (!rows.length) {
      $("noMessages").textContent = "No email conversations found for this record yet.";
      show($("noMessages")); hide($("inboxTable")); return;
    }
    hide($("noMessages")); show($("inboxTable"));
    rows = rows.slice();
    if (convSort.key) {
      var k = convSort.key, dir = convSort.dir;
      rows.sort(function (a, b) {
        var va = convSortVal(a, k), vb = convSortVal(b, k);
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
    }
    rows.forEach(function (c) {
      var tr = document.createElement("tr");
      // Unread (this user hasn't opened it since the last message) reads bold
      // with the classic inbox dot; opening the thread clears it.
      tr.className = "sx__inbox-row" + (c.unread ? " is-unread" : "");
      tr.tabIndex = 0; tr.setAttribute("role", "button");

      var c0 = document.createElement("td"); c0.className = "sx__inbox-dir";
      if (c.status) c0.appendChild(tag(c.status, c.status === "Open" ? "status" : "type"));
      if (c.awaitingReply) {
        var aw = document.createElement("span"); aw.className = "sx__chip-awaiting";
        aw.textContent = "Awaiting reply"; aw.title = "The last message is from them — the ball is in your court.";
        c0.appendChild(aw);
      }

      var c1 = document.createElement("td"); c1.className = "sx__inbox-party";
      c1.textContent = c.participants || "—";

      var c2 = document.createElement("td"); c2.className = "sx__inbox-subj";
      var subj = document.createElement("span"); subj.className = "sx__inbox-subject";
      subj.textContent = (c.subject || "(no subject)") + (c.messageCount ? " (" + c.messageCount + ")" : "");
      var sn = document.createElement("span"); sn.className = "sx__inbox-snippet";
      sn.textContent = snippet(c.summary || "", 110);
      c2.appendChild(subj); c2.appendChild(sn);

      var c3 = document.createElement("td"); c3.className = "sx__inbox-date";
      c3.textContent = fmtSessionDate(c.lastMessageAt, "short");

      tr.appendChild(c0); tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3);
      tr.addEventListener("click", function () { viewConversation(c.id); });
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); viewConversation(c.id); } });
      body.appendChild(tr);
    });
    updateCommTabBadge();
  }

  // The Communications tab button carries the record's unread count.
  function updateCommTabBadge() {
    var btn = document.querySelector('[data-dtab="communications"]');
    if (!btn) return;
    var label = "Communications";
    ((config && config.detailTabs) || []).forEach(function (t) {
      if (t.key === "communications") label = t.label || label;
    });
    var n = convRows.filter(function (c) { return c.unread; }).length;
    btn.textContent = n ? label + " (" + n + ")" : label;
  }

  async function viewConversation(convId) {
    openComm("Conversation", "Loading…");
    var body = $("commModalBody");
    try {
      var c = await api("/conversations/" + encodeURIComponent(convId));
    } catch (e) {
      if (e.status === 401) { closeComm(); showLogin(); return; }
      body.innerHTML = ""; var p = document.createElement("p"); p.className = "form-error";
      p.textContent = e.message; body.appendChild(p); return;
    }
    $("commModalTitle").textContent = c.subject || "(no subject)";
    body.innerHTML = "";
    // The server stamped this thread read on the fetch — reflect it locally.
    convRows.forEach(function (r) { if (r.id === convId) r.unread = false; });
    renderConversationRows(convRows);

    // Optional AI summary block (empty when the summary layer is off).
    if (c.summary || (c.actionItems || []).length) {
      var sum = document.createElement("div"); sum.className = "sx__conv-summary";
      if (c.status) sum.appendChild(tag(c.status, c.status === "Open" ? "status" : "type"));
      if (c.summary) { var st = document.createElement("p"); st.textContent = c.summary; sum.appendChild(st); }
      if ((c.actionItems || []).length) {
        var cal = document.createElement("div"); cal.className = "sx__scallout";
        var l = document.createElement("span"); l.className = "sx__scallout-l"; l.textContent = "Action items";
        var b = document.createElement("div"); b.className = "sx__scallout-b";
        var ul = document.createElement("ul");
        c.actionItems.forEach(function (a) { var li = document.createElement("li"); li.textContent = a; ul.appendChild(li); });
        b.appendChild(ul); cal.appendChild(l); cal.appendChild(b); sum.appendChild(cal);
      }
      body.appendChild(sum);
    }

    var lastInbound = null;
    (c.messages || []).forEach(function (m) {
      if (m.direction === "Inbound") lastInbound = m;
      var card = document.createElement("div"); card.className = "sx__msg-card";
      var head = document.createElement("div"); head.className = "sx__msg-head";
      var who = document.createElement("span"); who.className = "sx__msg-who";
      // Always lead with WHO WROTE IT (a mentor and co-mentor can both send on
      // the same engagement — "To: client" hid which of them was talking);
      // outbound keeps the recipient after an arrow.
      who.textContent = (m.from || m.fromAddress || "") +
        (m.direction === "Outbound" && m.to ? " → " + m.to : "");
      var when = document.createElement("span"); when.className = "sx__msg-when";
      when.textContent = fmtSessionDate(m.sentAt, "short");
      head.appendChild(who); head.appendChild(when);
      if (m.gmailMessageId && m.sourceMailbox) {
        var a = document.createElement("a");
        a.href = "https://mail.google.com/mail/u/" + encodeURIComponent(m.sourceMailbox) + "/#all/" + encodeURIComponent(m.gmailMessageId);
        a.target = "_blank"; a.rel = "noopener"; a.className = "sx__msg-gmail"; a.textContent = "Open in Gmail";
        head.appendChild(a);
      }
      card.appendChild(head);
      var mb = document.createElement("div"); mb.className = "sx__msg-html";
      mb.innerHTML = sanitizeHtml(m.bodyHtml || "");
      card.appendChild(mb);
      body.appendChild(card);
    });
    if (!(c.messages || []).length) {
      var none = document.createElement("p"); none.className = "sx__muted";
      none.textContent = "No messages stored for this conversation."; body.appendChild(none);
    }

    var foot = $("commModalFoot"); foot.innerHTML = "";
    // The message being answered rides into the compose as a quoted block, so
    // the writer still sees what they're replying to (the compose replaces
    // this thread view in the modal).
    var lastMsg = (c.messages || [])[(c.messages || []).length - 1] || null;
    var quoteSrc = lastInbound || lastMsg;
    function quoteOf(m) {
      if (!m || !m.bodyHtml) return null;
      return {
        html: m.bodyHtml,
        from: m.from || m.fromAddress || "",
        date: m.sentAt || "",
      };
    }
    // Every address seen on the thread (senders + To + Cc), minus the user's
    // own mailbox — the Reply All recipient set.
    function threadParticipants() {
      var seen = {}, out = [];
      (c.messages || []).forEach(function (m) {
        [m.fromAddress].concat(
          String(m.to || "").split(/[,;]+/),
          String(m.cc || "").split(/[,;]+/)
        ).forEach(function (a) {
          a = extractEmail(a || "").toLowerCase();
          if (!a || a.indexOf("@") === -1 || seen[a]) return;
          if (senderMailbox && a === String(senderMailbox).toLowerCase()) return;
          seen[a] = 1; out.push(a);
        });
      });
      return out;
    }
    function openReply(toList) {
      composeMessage({
        to: toList.join(", "),
        subject: replySubject(c.subject),
        replyToId: lastInbound ? lastInbound.id : null,
        quote: quoteOf(quoteSrc),
        backToConv: convId,
      });
    }
    var reply = document.createElement("button"); reply.type = "button"; reply.className = "cbm-button";
    reply.textContent = "↩ Reply";
    reply.addEventListener("click", function () {
      openReply(lastInbound && lastInbound.fromAddress ? [lastInbound.fromAddress] : []);
    });
    foot.appendChild(reply);
    var participants = threadParticipants();
    if (participants.length > 1) {
      var replyAll = document.createElement("button"); replyAll.type = "button";
      replyAll.className = "cbm-button cbm-button--secondary";
      replyAll.textContent = "↩ Reply all (" + participants.length + ")";
      replyAll.addEventListener("click", function () { openReply(participants); });
      foot.appendChild(replyAll);
    }
    // Forward the latest message to someone new: nobody pre-selected, the
    // message rides along as a forwarded block (headers + body).
    if (lastMsg && lastMsg.bodyHtml) {
      var fwd = document.createElement("button"); fwd.type = "button";
      fwd.className = "cbm-button cbm-button--secondary"; fwd.textContent = "↪ Forward";
      fwd.addEventListener("click", function () {
        var s = String(c.subject || "");
        composeMessage({
          subject: /^fwd:/i.test(s) ? s : "Fwd: " + s,
          forward: {
            html: lastMsg.bodyHtml,
            from: lastMsg.from || lastMsg.fromAddress || "",
            date: lastMsg.sentAt || "",
            to: lastMsg.to || "",
            subject: c.subject || "",
          },
          backToConv: convId,
        });
      });
      foot.appendChild(fwd);
    }
    foot.appendChild(removeConversationBtn(convId));
    var close = document.createElement("button"); close.type = "button";
    close.className = "cbm-button cbm-button--secondary"; close.textContent = "Close";
    close.addEventListener("click", closeComm);
    foot.appendChild(close);
  }

  // Two-step "Not related — remove" (no browser confirm dialogs).
  function removeConversationBtn(convId) {
    var btn = document.createElement("button"); btn.type = "button";
    btn.className = "cbm-button cbm-button--secondary"; btn.textContent = "Not related — remove";
    var armed = false;
    btn.addEventListener("click", async function () {
      if (!armed) { armed = true; btn.textContent = "Really remove from this record?"; return; }
      btn.disabled = true;
      try {
        await api("/records/" + encodeURIComponent(currentDetail.id) +
                  "/conversations/" + encodeURIComponent(convId) + "/exclude", { method: "POST" });
        closeComm(); loadConversations();
      } catch (e) {
        if (e.status === 401) { closeComm(); showLogin(); return; }
        btn.disabled = false; btn.textContent = e.message;
      }
    });
    return btn;
  }

  // "Add emails…": live search of YOUR mailbox, add a thread to this record.
  function addEmailsDialog() {
    openComm("Add emails", "Find a conversation in your mailbox");
    var body = $("commModalBody");
    var row = document.createElement("div"); row.className = "sx__msg-field";
    var input = document.createElement("input"); input.type = "text"; input.className = "sx__msg-input";
    input.placeholder = "Search your mailbox (sender, subject, words…)";
    var go = document.createElement("button"); go.type = "button"; go.className = "cbm-button"; go.textContent = "Search";
    row.appendChild(input); row.appendChild(go); body.appendChild(row);
    var results = document.createElement("div"); body.appendChild(results);

    async function run() {
      var q = input.value.trim(); if (!q) return;
      results.innerHTML = "<p class='sx__muted'>Searching…</p>";
      try {
        var res = await api("/mailsearch?q=" + encodeURIComponent(q));
        results.innerHTML = "";
        var threads = res.threads || [];
        if (!threads.length) { results.innerHTML = "<p class='sx__muted'>No matching conversations.</p>"; return; }
        threads.forEach(function (t) {
          var card = document.createElement("div"); card.className = "sx__msg-card";
          var head = document.createElement("div"); head.className = "sx__msg-head";
          var who = document.createElement("span"); who.className = "sx__msg-who";
          who.textContent = (t.from || "") + " — " + (t.subject || "(no subject)");
          var when = document.createElement("span"); when.className = "sx__msg-when";
          when.textContent = fmtSessionDate(t.date, "short");
          head.appendChild(who); head.appendChild(when);
          var add = document.createElement("button"); add.type = "button";
          add.className = "cbm-button sx__sm"; add.textContent = "Add to this record";
          add.addEventListener("click", async function () {
            add.disabled = true; add.textContent = "Adding…";
            try {
              await api("/records/" + encodeURIComponent(currentDetail.id) + "/conversations/include", {
                method: "POST", body: JSON.stringify({ gmailThreadId: t.gmailThreadId })
              });
              add.textContent = "Added ✓"; loadConversations();
            } catch (e) {
              if (e.status === 401) { closeComm(); showLogin(); return; }
              add.disabled = false; add.textContent = e.message;
            }
          });
          head.appendChild(add);
          card.appendChild(head);
          var sn = document.createElement("p"); sn.className = "sx__muted"; sn.textContent = t.snippet || "";
          card.appendChild(sn);
          results.appendChild(card);
        });
      } catch (e) {
        if (e.status === 401) { closeComm(); showLogin(); return; }
        results.innerHTML = ""; var p = document.createElement("p"); p.className = "form-error";
        p.textContent = e.message; results.appendChild(p);
      }
    }
    go.addEventListener("click", run);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") run(); });
    var foot = $("commModalFoot"); foot.innerHTML = "";
    var close = document.createElement("button"); close.type = "button";
    close.className = "cbm-button cbm-button--secondary"; close.textContent = "Close";
    close.addEventListener("click", closeComm);
    foot.appendChild(close);
    input.focus();
  }

  // --- sample-data scaffold (shown until GMAIL_SYNC is enabled) ---------------
  var SAMPLE_MESSAGES = [
    { id: "s1", direction: "received", from: "Pat Rivera <pat.rivera@example.com>",
      to: "mentor@cbmentors.org", subject: "Re: Agenda for our next meeting",
      date: "2026-07-08 14:22:00", unread: true,
      body: "Thanks for sending the agenda over. I had a couple of questions about the marketing plan we discussed — mainly around budget and timing. Could we walk through those first? Looking forward to it." },
    { id: "s2", direction: "sent", from: "mentor@cbmentors.org",
      to: "Pat Rivera <pat.rivera@example.com>", subject: "Agenda for our next meeting",
      date: "2026-07-07 09:10:00", unread: false,
      body: "Hi Pat,\n\nHere's what I'd like to cover on Thursday:\n\n1. Review last month's numbers\n2. Marketing plan next steps\n3. Hiring timeline\n\nLet me know if you'd like to add anything.\n\nBest," },
    { id: "s3", direction: "received", from: "Pat Rivera <pat.rivera@example.com>",
      to: "mentor@cbmentors.org", subject: "Thank you!",
      date: "2026-06-30 17:45:00", unread: false,
      body: "Just wanted to say thanks for all your help this month — the introductions you made were incredibly valuable." },
  ];

  function partyName(addr) {
    // "Name <email>" -> "Name"; a bare address -> the address.
    var m = /^\s*"?([^"<]+?)"?\s*</.exec(addr || "");
    return (m ? m[1] : (addr || "")).trim() || "(unknown)";
  }
  function extractEmail(addr) {
    // "Name <email>" -> "email"; a bare address passes through.
    var m = /<([^>]+)>/.exec(addr || "");
    return (m ? m[1] : String(addr || "")).trim();
  }
  function snippet(body, n) {
    var t = String(body || "").replace(/\s+/g, " ").trim();
    n = n || 90;
    return t.length > n ? t.slice(0, n - 1) + "…" : t;
  }
  function replySubject(subj) {
    var s = String(subj || "");
    return /^re:/i.test(s) ? s : "Re: " + s;
  }

  function renderSampleComms() {
    var body = $("inboxBody"); if (!body) return;
    show($("commBanner")); $("addEmailsBtn").hidden = true;
    body.innerHTML = "";
    var msgs = SAMPLE_MESSAGES;
    if (!msgs.length) { hide($("inboxTable")); show($("noMessages")); return; }
    hide($("noMessages")); show($("inboxTable"));
    msgs.forEach(function (m) {
      var tr = document.createElement("tr");
      tr.className = "sx__inbox-row" + (m.unread ? " is-unread" : "");
      tr.tabIndex = 0; tr.setAttribute("role", "button");

      var c0 = document.createElement("td"); c0.className = "sx__inbox-dir";
      c0.appendChild(tag(m.direction === "sent" ? "Sent" : "Received",
        m.direction === "sent" ? "type" : "status"));

      var c1 = document.createElement("td"); c1.className = "sx__inbox-party";
      c1.textContent = partyName(m.from) +
        (m.direction === "sent" ? " → " + partyName(m.to) : "");

      var c2 = document.createElement("td"); c2.className = "sx__inbox-subj";
      var subj = document.createElement("span"); subj.className = "sx__inbox-subject";
      subj.textContent = m.subject || "(no subject)";
      var sn = document.createElement("span"); sn.className = "sx__inbox-snippet";
      sn.textContent = snippet(m.body);
      c2.appendChild(subj); c2.appendChild(sn);

      var c3 = document.createElement("td"); c3.className = "sx__inbox-date";
      c3.textContent = fmtSessionDate(m.date, "short");

      tr.appendChild(c0); tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3);
      tr.addEventListener("click", function () { viewMessage(m); });
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); viewMessage(m); } });
      body.appendChild(tr);
    });
  }

  // Generic styled confirm (the #confirmModal shell): every caller sets ALL
  // the labels, so the dialog never leaks a previous caller's wording.
  function openConfirm(opts) {
    $("confirmTitle").textContent = opts.title || "Are you sure?";
    $("confirmMsg").textContent = opts.msg || "";
    var save = $("confirmSave");
    save.hidden = !opts.onSave;
    save.textContent = opts.saveLabel || "Save";
    $("confirmDiscard").textContent = opts.discardLabel || "Discard";
    $("confirmCancel").textContent = opts.cancelLabel || "Cancel";
    confirmOnSave = opts.onSave || null;
    confirmOnDiscard = opts.onDiscard || null;
    show($("confirmModal"));
    (opts.onSave ? save : $("confirmCancel")).focus();
  }

  // --- Communications: view / compose / reply modal ---
  function openComm(kind, title) {
    composeGuard = null;  // any (re)open resets the compose close-guard
    $("commModalKind").textContent = kind || "";
    $("commModalTitle").textContent = title || "";
    $("commModalBody").innerHTML = ""; $("commModalFoot").innerHTML = "";
    show($("commModal"));
    commTrapEl = document.querySelector("#commModal .sx__modal-card");
  }
  function closeComm() { composeGuard = null; commTrapEl = null; hide($("commModal")); }

  // Closing the comm modal by Escape / × / backdrop / Cancel: a compose with
  // real content asks before discarding (the draft also survives in
  // localStorage either way — "Discard draft" is what deletes it).
  function requestCloseComm() {
    if (!composeGuard || !composeGuard.dirty()) {
      var back = composeGuard && composeGuard.backConvId;
      closeComm();
      if (back) viewConversation(back);  // a reply returns to its thread
      return;
    }
    var g = composeGuard;
    openConfirm({
      title: "Discard this draft?",
      msg: "Your message hasn't been sent. It stays saved as a draft unless you discard it.",
      discardLabel: "Discard draft",
      cancelLabel: "Keep writing",
      onDiscard: function () {
        g.discard();
        closeComm();
        if (g.backConvId) viewConversation(g.backConvId);
      },
    });
  }

  // "a@b.c, Jane Doe <jane@x.org>; bob@y.io" -> {emails: [...], invalid: [...]}.
  // Splits on commas/semicolons/newlines (NOT bare spaces — display names
  // contain them); accepts Name <email>; validates the address shape.
  function parseAddrList(str) {
    var emails = [], invalid = [], seen = {};
    String(str || "").split(/[,;\n]+/).forEach(function (tok) {
      tok = tok.trim();
      if (!tok) return;
      var m = /<([^>]+)>/.exec(tok);
      var addr = (m ? m[1] : tok).trim();
      // A bare space-separated run without <>: keep the @-looking parts.
      if (!m && /\s/.test(addr)) {
        var parts = addr.split(/\s+/).filter(function (p) { return p.indexOf("@") !== -1; });
        if (parts.length === 1) addr = parts[0];
      }
      if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)) {
        var k = addr.toLowerCase();
        if (!seen[k]) { seen[k] = 1; emails.push(addr); }
      } else {
        invalid.push(tok);
      }
    });
    return { emails: emails, invalid: invalid };
  }

  function fmtBytes(n) {
    if (!n && n !== 0) return "";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  // Searchable dropdown (template picker, company picker): one input, a
  // filtered list below it. opts: {placeholder, options: [{id,label,muted}],
  // emptyLabel, onSelect(id|null, option), allowClear}. Returns {el, setOptions,
  // setText, close}.
  function makeCombobox(opts) {
    var wrap = document.createElement("div"); wrap.className = "sx__combo";
    var input = document.createElement("input");
    input.type = "text"; input.className = "sx__msg-input";
    input.placeholder = opts.placeholder || "";
    input.setAttribute("role", "combobox"); input.setAttribute("aria-expanded", "false");
    var list = document.createElement("ul"); list.className = "sx__combo-list"; list.hidden = true;
    wrap.appendChild(input); wrap.appendChild(list);
    var options = opts.options || [];
    var active = -1, visible = [];
    function close() { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; }
    function render(filter) {
      list.innerHTML = ""; visible = []; active = -1;
      if (opts.allowClear) visible.push({ id: null, label: opts.emptyLabel || "(none)", muted: true });
      options.forEach(function (o) {
        if (filter && String(o.label || "").toLowerCase().indexOf(filter.toLowerCase()) === -1) return;
        visible.push(o);
      });
      visible.forEach(function (o, i) {
        var li = document.createElement("li");
        li.textContent = o.label; if (o.muted) li.className = "is-muted";
        li.addEventListener("mousedown", function (e) { e.preventDefault(); pick(i); });
        list.appendChild(li);
      });
      list.hidden = !visible.length;
      input.setAttribute("aria-expanded", String(!visible.length ? false : true));
    }
    function highlight() {
      Array.prototype.forEach.call(list.children, function (li, i) {
        li.className = (visible[i] && visible[i].muted ? "is-muted" : "") + (i === active ? " is-active" : "");
        if (i === active) li.scrollIntoView({ block: "nearest" });
      });
    }
    function pick(i) {
      var o = visible[i];
      if (!o) return;
      input.value = o.id === null ? "" : o.label;
      close();
      opts.onSelect(o.id, o);
    }
    input.addEventListener("input", function () { render(input.value); });
    input.addEventListener("focus", function () { render(input.value); });
    input.addEventListener("blur", function () { setTimeout(close, 150); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { if (list.hidden) render(input.value); active = Math.min(active + 1, visible.length - 1); highlight(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); highlight(); e.preventDefault(); }
      else if (e.key === "Enter") { if (!list.hidden && active >= 0) { pick(active); e.preventDefault(); } else if (!list.hidden && visible.length === 1) { pick(0); e.preventDefault(); } }
      else if (e.key === "Escape" && !list.hidden) { close(); e.stopPropagation(); }
    });
    return {
      el: wrap,
      input: input,
      setOptions: function (o) { options = o || []; },
      setText: function (t) { input.value = t || ""; },
      close: close,
    };
  }

  // POST with upload progress (an email with attachments is one big JSON body
  // — fetch gives no upload feedback). Mirrors api()'s error contract.
  function apiPostProgress(path, payload, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", API + path);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.withCredentials = true;
      if (xhr.upload && onProgress) {
        xhr.upload.addEventListener("progress", function (ev) {
          if (ev.lengthComputable) onProgress(Math.round((ev.loaded / ev.total) * 100));
        });
      }
      xhr.onload = function () {
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e) {}
        if (xhr.status >= 200 && xhr.status < 300) { resolve(data); return; }
        var msg = (data && data.detail) || ("Request failed (" + xhr.status + ")");
        var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        err.status = xhr.status;
        reject(err);
      };
      xhr.onerror = xhr.onabort = xhr.ontimeout = function () {
        reject(new Error("The send was interrupted — check your connection and try again."));
      };
      xhr.send(JSON.stringify(payload));
    });
  }

  // --- compose draft persistence (accidental close / session expiry) --------
  function draftKey(replyToId) {
    return "cbmDraft:" + SLUG + ":" + (currentDetail ? currentDetail.id : "none") +
      ":" + (replyToId || "new");
  }
  function loadDraft(replyToId) {
    try {
      var raw = localStorage.getItem(draftKey(replyToId));
      if (!raw) return null;
      var d = JSON.parse(raw);
      // Stale drafts (a week old) silently expire.
      if (!d || !d.ts || Date.now() - d.ts > 7 * 24 * 3600 * 1000) return null;
      return d;
    } catch (e) { return null; }
  }
  function storeDraft(replyToId, state) {
    try { localStorage.setItem(draftKey(replyToId), JSON.stringify(state)); } catch (e) {}
  }
  function clearDraft(replyToId) {
    try { localStorage.removeItem(draftKey(replyToId)); } catch (e) {}
  }

  function commHeaderRow(label, value) {
    var row = document.createElement("div"); row.className = "sx__fact";
    var l = document.createElement("span"); l.className = "sx__fact-l"; l.textContent = label;
    var v = document.createElement("span"); v.className = "sx__fact-v"; v.textContent = value || "—";
    row.appendChild(l); row.appendChild(v); return row;
  }

  function viewMessage(m) {
    if (m.unread) { m.unread = false; renderSampleComms(); }
    openComm(m.direction === "sent" ? "Sent message" : "Received message", m.subject || "(no subject)");
    var body = $("commModalBody");
    body.appendChild(commHeaderRow("From", m.from));
    body.appendChild(commHeaderRow("To", m.to));
    body.appendChild(commHeaderRow("Date", fmtSessionDate(m.date, "short")));
    var pre = document.createElement("div"); pre.className = "sx__msg-body"; pre.textContent = m.body || "";
    body.appendChild(pre);
    var reply = document.createElement("button"); reply.type = "button"; reply.className = "cbm-button";
    reply.textContent = "↩ Reply";
    reply.addEventListener("click", function () {
      composeMessage({ to: m.from, subject: replySubject(m.subject) });
    });
    var close = document.createElement("button"); close.type = "button";
    close.className = "cbm-button cbm-button--secondary"; close.textContent = "Close";
    close.addEventListener("click", closeComm);
    $("commModalFoot").appendChild(reply); $("commModalFoot").appendChild(close);
  }

  function commField(label, id, value, isTextarea, opts) {
    opts = opts || {};
    // The message body is the standard rich-text editor (CBMRichText/Jodit) —
    // the send path is HTML-native (comms.service.send_message body_html, with
    // a plain-text alternative derived server-side). A div wrapper, not label:
    // wrapping a whole editor in a <label> re-routes clicks to its first input.
    if (isTextarea && window.CBMRichText) {
      // The dialog is a 90% workspace — give the editor real height (roughly
      // the space left after the recipient/subject/attachment rows).
      var minH = opts.minHeight || Math.max(240, Math.floor(window.innerHeight * 0.32));
      var rich = window.CBMRichText.create(value || "", { minHeight: minH, onInput: opts.onInput });
      if (rich) {
        var rwrap = document.createElement("div"); rwrap.className = "sx__msg-field";
        var rl = document.createElement("span"); rl.className = "sx__msg-label"; rl.textContent = label;
        rich.id = id; rich.classList.add("sx__msg-rich");
        rwrap.appendChild(rl); rwrap.appendChild(rich); return rwrap;
      }
    }
    // A div wrapper + explicit label element (never a wrapping <label> — the
    // recipients row carries the Cc/Bcc BUTTONS on its label line, and a
    // button inside a <label> becomes the label's implicit control).
    var wrap = document.createElement("div"); wrap.className = "sx__msg-field";
    var l = document.createElement("label"); l.className = "sx__msg-label"; l.textContent = label;
    l.htmlFor = id;
    var input = isTextarea ? document.createElement("textarea") : document.createElement("input");
    input.id = id; input.className = "sx__msg-input";
    if (isTextarea) { input.rows = 10; } else { input.type = "text"; }
    if (opts.placeholder) input.placeholder = opts.placeholder;
    input.value = value || "";
    if (opts.onInput) input.addEventListener("input", opts.onInput);
    wrap.appendChild(l); wrap.appendChild(input); return wrap;
  }

  // The compose body's current value: HTML from the rich editor, or the plain
  // textarea's text when the editor script didn't load (the send path accepts
  // both — plain text is upconverted server-side).
  function commBodyValue() {
    var el = $("commBody");
    if (!el) return "";
    return el._cbmRichText ? el._cbmRichText.getValue() : el.value;
  }

  // Product-wide rule (Doug, 2026-07-16): an email address shown anywhere in
  // the UI opens the compose dialog pre-filled with that address. The link
  // keeps a real mailto: href (middle-click/copy still work), and a plain
  // click falls back to mailto: only when comms is off or there's no open
  // record to send from (e.g. a company peek on the grid page).
  function emailComposeLink(email) {
    if (!email) return document.createTextNode("—");
    // No open record (grid-page peeks): the record-scoped compose can't be
    // used, so delegate to the shared quick-compose widget (which itself
    // falls back to mailto: when sending isn't available). Render-time
    // check is safe — the grid and record views are separate pages.
    if (!currentDetail && window.CBMQuickMail) return CBMQuickMail.emailLink(email);
    var a = document.createElement("a");
    a.href = "mailto:" + email; a.textContent = email; a.title = "Send email";
    a.addEventListener("click", function (e) {
      if (!commsOn() || !currentDetail) return;
      e.preventDefault();
      composeMessage({ to: email });
    });
    return a;
  }

  function composeMessage(pre) {
    pre = pre || {};
    var replyKey = pre.replyToId || null;
    // Header: the record name for context, the action as the title.
    openComm(currentDetail ? (currentDetail.name || "") : "",
      pre.forward ? "Forward" : (pre.replyToId ? "Reply" : "New email"));
    var body = $("commModalBody");

    // From: the signed-in user's own CBM mailbox — the address the message
    // actually goes out as. Fetched once and cached for the page's lifetime.
    var fromRow = commHeaderRow("From", senderMailbox || "…");
    body.appendChild(fromRow);
    function setFrom(text) { fromRow.querySelector(".sx__fact-v").textContent = text; }
    if (senderMailbox === undefined) {
      api("/mailbox").then(function (r) {
        senderMailbox = (r && r.mailbox) || null;
        senderSignature = (r && r.signature) || "";
        setFrom(senderMailbox || "no CBM email on your profile — sending won't work");
        seedSignature();
      }).catch(function () { setFrom("your CBM email address"); });
    } else if (senderMailbox === null) {
      setFrom("no CBM email on your profile — sending won't work");
    }

    // To: every record contact with an email address as a checkbox — ALL
    // checked by default on a fresh compose (uncheck to leave someone off);
    // a reply pre-checks only the addresses it's replying to.
    var contactRecips = ((currentDetail && currentDetail.contacts) || [])
      .filter(function (c) { return c.email; });
    var preAddrs = String(pre.to || "").split(/[,;\s]+/).filter(Boolean)
      .map(function (a) { return extractEmail(a); });
    var preKeys = preAddrs.map(function (a) { return a.toLowerCase(); });
    var recipChecks = [];   // {email, box} per listed contact
    if (contactRecips.length) {
      var toWrap = document.createElement("div"); toWrap.className = "sx__msg-field";
      var toHead = document.createElement("div"); toHead.className = "sx__to-head";
      var toLab = document.createElement("span"); toLab.className = "sx__msg-label"; toLab.textContent = "To";
      toHead.appendChild(toLab);
      // Long contact lists get one-click All / None.
      if (contactRecips.length > 5) {
        var allBtn = document.createElement("button"); allBtn.type = "button";
        allBtn.className = "sx__link-btn"; allBtn.textContent = "All";
        var noneBtn = document.createElement("button"); noneBtn.type = "button";
        noneBtn.className = "sx__link-btn"; noneBtn.textContent = "None";
        allBtn.addEventListener("click", function () {
          recipChecks.forEach(function (r) { r.box.checked = true; }); onRecipientsChanged();
        });
        noneBtn.addEventListener("click", function () {
          recipChecks.forEach(function (r) { r.box.checked = false; }); onRecipientsChanged();
        });
        toHead.appendChild(allBtn); toHead.appendChild(noneBtn);
      }
      toWrap.appendChild(toHead);
      var listEl = document.createElement("div"); listEl.className = "sx__to-list";
      contactRecips.forEach(function (c) {
        var lab = document.createElement("label"); lab.className = "sx__addr-check";
        var box = document.createElement("input"); box.type = "checkbox";
        // A forward starts with NOBODY selected (the whole point is sending
        // to someone new); a reply pre-checks the replied-to addresses; a
        // fresh compose selects every record contact.
        box.checked = pre.forward ? false
          : (pre.to ? preKeys.indexOf(c.email.toLowerCase()) !== -1 : true);
        box.addEventListener("change", onRecipientsChanged);
        lab.appendChild(box);
        lab.appendChild(document.createTextNode(" " + (c.name || c.email) + " — " + c.email));
        listEl.appendChild(lab);
        recipChecks.push({ email: c.email, box: box });
      });
      toWrap.appendChild(listEl);
      body.appendChild(toWrap);
    }
    // Free-entry field for anyone not on the record; reply addresses that
    // aren't record contacts land here so they stay on the thread. Cc/Bcc
    // reveal on demand (Gmail-style) from the label line.
    var knownEmails = {};
    recipChecks.forEach(function (r) { knownEmails[r.email.toLowerCase()] = 1; });
    var extra = preAddrs.filter(function (a) { return !knownEmails[a.toLowerCase()]; }).join(", ");
    var addrPlaceholder = "name@example.com, another@example.com";
    var otherWrap = commField(contactRecips.length ? "Other recipients" : "To",
      "commTo", extra, false, { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
    var otherLab = otherWrap.querySelector(".sx__msg-label");
    var toggles = document.createElement("span"); toggles.className = "sx__ccbcc-toggles";
    var ccLink = document.createElement("button"); ccLink.type = "button";
    ccLink.className = "sx__link-btn"; ccLink.textContent = "Cc";
    var bccLink = document.createElement("button"); bccLink.type = "button";
    bccLink.className = "sx__link-btn"; bccLink.textContent = "Bcc";
    toggles.appendChild(ccLink); toggles.appendChild(bccLink);
    var labLine = document.createElement("div"); labLine.className = "sx__to-head";
    otherWrap.insertBefore(labLine, otherLab);
    labLine.appendChild(otherLab); labLine.appendChild(toggles);
    body.appendChild(otherWrap);
    var ccField = commField("Cc", "commCc", "", false,
      { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
    var bccField = commField("Bcc", "commBcc", "", false,
      { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
    ccField.hidden = true; bccField.hidden = true;
    body.appendChild(ccField); body.appendChild(bccField);
    ccLink.addEventListener("click", function () {
      ccField.hidden = false; ccLink.hidden = true; $("commCc").focus();
    });
    bccLink.addEventListener("click", function () {
      bccField.hidden = false; bccLink.hidden = true; $("commBcc").focus();
    });

    // Checked contacts + whatever was typed, deduped case-insensitively.
    function fieldAddrs(id) {
      var el = $(id);
      return el && !el.closest(".sx__msg-field").hidden ? parseAddrList(el.value) : { emails: [], invalid: [] };
    }
    function recipientSets() {
      var seen = {};
      function dedupe(list) {
        var out = [];
        list.forEach(function (a) {
          var k = a.toLowerCase();
          if (!seen[k]) { seen[k] = 1; out.push(a); }
        });
        return out;
      }
      var toParsed = fieldAddrs("commTo"), ccParsed = fieldAddrs("commCc"), bccParsed = fieldAddrs("commBcc");
      var checked = [];
      recipChecks.forEach(function (r) { if (r.box.checked) checked.push(r.email); });
      return {
        to: dedupe(checked.concat(toParsed.emails)),
        cc: dedupe(ccParsed.emails),
        bcc: dedupe(bccParsed.emails),
        invalid: toParsed.invalid.concat(ccParsed.invalid, bccParsed.invalid),
      };
    }
    function recipientList() {
      var s = recipientSets();
      return s.to.concat(s.cc, s.bcc);
    }

    // --- Email template picker (ET). EspoCRM renders the template server-side
    // (placeholders resolved against this record + the first recipient); the
    // result loads here as a plain editable draft. Selecting over a non-empty
    // draft asks before replacing (ET-113); a parse failure leaves the draft
    // untouched (ET-114); "No template" restores the pre-template draft.
    var templateAttachments = [];   // {id, name} chips from the selected template
    var localAttachments = [];      // {filename, contentType, dataBase64, size} uploads
    var tplAll = [], tplConfirmEl = null, preTplSnapshot = null;
    var tplWrap = document.createElement("div"); tplWrap.className = "sx__msg-field";
    tplWrap.hidden = true;
    var tplLab = document.createElement("span"); tplLab.className = "sx__msg-label"; tplLab.textContent = "Template";
    var tplLine = document.createElement("div"); tplLine.className = "sx__opt-line";
    var tplCombo = makeCombobox({
      placeholder: "Search templates…",
      allowClear: true,
      emptyLabel: "No template",
      onSelect: function (id) { onTemplatePicked(id); },
    });
    tplLine.appendChild(tplCombo.el);
    var tplNotice = document.createElement("p"); tplNotice.className = "sx__notice"; tplNotice.hidden = true;
    tplWrap.appendChild(tplLab); tplWrap.appendChild(tplLine); tplWrap.appendChild(tplNotice);
    body.appendChild(tplWrap);
    if (commsOn()) {
      api("/emailtemplates").then(function (r) {
        tplAll = (r && r.templates) || [];
        if (tplAll.length) {
          tplCombo.setOptions(tplAll.map(function (t) { return { id: t.id, label: t.name }; }));
          tplWrap.hidden = false;
        }
      }).catch(function () { /* no picker — compose works without it */ });
    }
    // Signature (the user's EspoCRM Preferences signature, riding /mailbox):
    // seeded into a PRISTINE body when the dialog opens — from there it's
    // plain editable text. A body still equal to any auto-generated state
    // counts as empty/untouched, so a template pick right after opening
    // doesn't ask to "replace" and closing doesn't ask to discard.
    var quoteHtml = pre.quote ? buildQuoteHtml(pre.quote)
      : (pre.forward ? buildForwardHtml(pre.forward) : "");
    var initialSubject = pre.subject || "";
    var pristineBodies = {};   // every auto-generated body state we've set
    function markPristine(v) { pristineBodies[String(v || "")] = 1; }
    function bodyPristine() { return !!pristineBodies[String(commBodyValue() || "")]; }
    function seedSignature() {
      if (!senderSignature) return;
      if (!bodyPristine()) return;  // the user already typed — never overwrite
      setCommBody("<p><br></p><p><br></p>" + senderSignature +
        (quoteHtml ? "<p><br></p>" + quoteHtml : ""));
      markPristine(commBodyValue());
    }
    function draftHasContent() {
      return !!($("commSubject").value.trim() !== initialSubject.trim() && $("commSubject").value.trim()) ||
        !bodyPristine() ||
        localAttachments.length > 0 ||
        docAttachments.length > 0;
    }
    function setCommBody(html) {
      var el = $("commBody");
      if (!el) return;
      if (el._cbmRichText) el._cbmRichText.setValue(html);
      else el.value = html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/p\s*>/gi, "\n\n").replace(/<[^>]+>/g, "");
    }
    function buildQuoteHtml(q) {
      var head = "On " + (q.date ? fmtSessionDate(q.date, "short") : "an earlier date") +
        ", " + (q.from || "they") + " wrote:";
      var p = document.createElement("p"); p.textContent = head;  // escapes the name
      return "<blockquote class=\"quoted-reply\">" + p.outerHTML + (q.html || "") + "</blockquote>";
    }
    // Gmail-style forwarded block: header lines, then the original message.
    function buildForwardHtml(f) {
      var lines = [
        "---------- Forwarded message ----------",
        "From: " + (f.from || "?"),
        f.date ? "Date: " + fmtSessionDate(f.date, "short") : "",
        f.subject ? "Subject: " + f.subject : "",
        f.to ? "To: " + f.to : "",
      ].filter(Boolean);
      var headHtml = lines.map(function (t) {
        var p = document.createElement("p"); p.textContent = t;  // escapes everything
        return p.outerHTML;
      }).join("");
      return "<blockquote class=\"quoted-reply\">" + headHtml + (f.html || "") + "</blockquote>";
    }
    function onTemplatePicked(id) {
      if (tplConfirmEl) { tplConfirmEl.remove(); tplConfirmEl = null; }
      if (!id) {
        // "No template": restore whatever the draft was before the last apply.
        if (preTplSnapshot) {
          $("commSubject").value = preTplSnapshot.subject;
          setCommBody(preTplSnapshot.body);
          if (preTplSnapshot.pristine) markPristine(commBodyValue());
          templateAttachments = preTplSnapshot.tplAttach.slice();
          renderAttachChips();
          preTplSnapshot = null;
          tplNotice.hidden = true;
          markEdited();
        }
        return;
      }
      if (!draftHasContent()) { applyTemplate(id); return; }
      // ET-113/ET-B1: never silently overwrite an edited draft.
      tplConfirmEl = document.createElement("div"); tplConfirmEl.className = "sx__notice is-warn";
      tplConfirmEl.appendChild(document.createTextNode("Replace current content? "));
      var yes = document.createElement("button"); yes.type = "button";
      yes.className = "cbm-button"; yes.textContent = "Replace";
      var no = document.createElement("button"); no.type = "button";
      no.className = "cbm-button cbm-button--secondary"; no.textContent = "Keep my draft";
      yes.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; applyTemplate(id);
      });
      no.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; tplCombo.setText("");
      });
      tplConfirmEl.appendChild(yes); tplConfirmEl.appendChild(document.createTextNode(" "));
      tplConfirmEl.appendChild(no);
      tplWrap.appendChild(tplConfirmEl);
    }
    async function applyTemplate(id) {
      tplNotice.hidden = true;
      preTplSnapshot = {
        subject: $("commSubject").value,
        body: String(commBodyValue() || ""),
        pristine: bodyPristine(),
        tplAttach: templateAttachments.slice(),
      };
      try {
        var r = await api("/records/" + encodeURIComponent(currentDetail.id) +
          "/emailtemplates/" + encodeURIComponent(id) + "/parse", {
          method: "POST",
          body: JSON.stringify({ emailAddress: recipientList()[0] || "" }),
        });
        $("commSubject").value = r.subject || "";
        // The rendered draft replaces the body; the signature re-appends
        // below it (EspoCRM's own compose behavior) — templates shouldn't
        // carry their own sign-off. A reply keeps its quoted original at
        // the bottom.
        setCommBody((r.bodyHtml || "") +
          (senderSignature ? "<p><br></p>" + senderSignature : "") +
          (quoteHtml ? "<p><br></p>" + quoteHtml : ""));
        templateAttachments = (r.attachments || []).slice();
        renderAttachChips();
        if ((r.leftoverTokens || []).length) {
          tplNotice.textContent = "Some placeholders couldn't be filled: " +
            r.leftoverTokens.join(", ") + " — review the draft before sending.";
          tplNotice.className = "sx__notice is-warn"; tplNotice.hidden = false;
        }
        markEdited();
      } catch (e) {
        if (e.status === 401) { flushDraft(); closeComm(); showLogin(); return; }
        // ET-114: non-destructive — the existing draft stays untouched.
        preTplSnapshot = null;
        tplNotice.textContent = e.message || "Couldn't apply the template.";
        tplNotice.className = "sx__notice is-error"; tplNotice.hidden = false;
        tplCombo.setText("");
      }
    }

    body.appendChild(commField("Subject", "commSubject", pre.subject, false,
      { onInput: markEdited }));
    body.appendChild(commField("Message", "commBody", "", true, { onInput: markEdited }));
    markPristine("");
    if (quoteHtml) {
      setCommBody("<p><br></p>" + quoteHtml);
      markPristine(commBodyValue());
    }
    // Cached signature seeds now; a first-ever compose seeds when the
    // /mailbox fetch above resolves.
    if (senderSignature) seedSignature();

    // --- Attachments: template chips (bytes stay in the CRM until send) plus
    // the user's own files, with sizes and a running total against the cap.
    var attachWrap = document.createElement("div"); attachWrap.className = "sx__msg-field";
    var attachLab = document.createElement("span"); attachLab.className = "sx__msg-label"; attachLab.textContent = "Attachments";
    var chipsEl = document.createElement("div"); chipsEl.className = "sx__attach-chips";
    var attachTotalEl = document.createElement("p"); attachTotalEl.className = "sx__attach-total"; attachTotalEl.hidden = true;
    var attachLine = document.createElement("div"); attachLine.className = "sx__opt-line";
    var fileBtn = document.createElement("button"); fileBtn.type = "button";
    fileBtn.className = "cbm-button cbm-button--secondary"; fileBtn.textContent = "Attach files…";
    var fileInput = document.createElement("input"); fileInput.type = "file";
    fileInput.multiple = true; fileInput.hidden = true;
    fileBtn.addEventListener("click", function () { fileInput.click(); });
    attachLine.appendChild(fileBtn); attachLine.appendChild(fileInput);
    // "Attach from documents…" — the record's Google Drive documents, without
    // a round-trip through the user's disk. Chips carry {documentId}; the
    // SERVER fetches the original bytes at send time through the same
    // record-scoped path as the Download action.
    var docAttachments = [];   // {documentId, filename}
    var docPickWrap = null, docPickList = null, docsCache = null;
    if (docsOn() && currentDetail) {
      docPickWrap = document.createElement("div"); docPickWrap.className = "sx__combo";
      var docBtn = document.createElement("button"); docBtn.type = "button";
      docBtn.className = "cbm-button cbm-button--secondary"; docBtn.textContent = "Attach from documents…";
      docPickList = document.createElement("ul"); docPickList.className = "sx__combo-list"; docPickList.hidden = true;
      docPickWrap.appendChild(docBtn); docPickWrap.appendChild(docPickList);
      attachLine.appendChild(docPickWrap);
      docBtn.addEventListener("click", async function () {
        if (!docPickList.hidden) { docPickList.hidden = true; return; }
        if (docsCache === null) {
          docBtn.disabled = true;
          try {
            var res = await api("/records/" + encodeURIComponent(currentDetail.id) + "/documents");
            docsCache = res.documents || [];
          } catch (e) {
            docsCache = null;
            if (e.status === 401) { flushDraft(); closeComm(); showLogin(); return; }
            footErr(e.status === 503
              ? "The document integration isn't enabled — attach a file from your computer instead."
              : (e.message || "Couldn't load this record's documents."));
            return;
          } finally { docBtn.disabled = false; }
        }
        renderDocPick();
      });
      document.addEventListener("click", function (e) {
        if (docPickWrap && !docPickWrap.contains(e.target)) docPickList.hidden = true;
      });
    }
    function renderDocPick() {
      docPickList.innerHTML = "";
      var chosen = {};
      docAttachments.forEach(function (d) { chosen[d.documentId] = 1; });
      var avail = (docsCache || []).filter(function (d) {
        return !chosen[d.id] && (d.status || "active") === "active";
      });
      if (!avail.length) {
        var li = document.createElement("li"); li.className = "is-muted";
        li.textContent = (docsCache || []).length
          ? "Every document is already attached."
          : "No documents on this record yet.";
        docPickList.appendChild(li);
      }
      avail.forEach(function (d) {
        var li = document.createElement("li");
        li.textContent = d.filename + (d.docType ? " — " + d.docType : "");
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          docAttachments.push({ documentId: d.id, filename: d.filename });
          docPickList.hidden = true;
          renderAttachChips(); markEdited();
        });
        docPickList.appendChild(li);
      });
      docPickList.hidden = false;
    }
    attachWrap.appendChild(attachLab); attachWrap.appendChild(chipsEl);
    attachWrap.appendChild(attachTotalEl); attachWrap.appendChild(attachLine);
    body.appendChild(attachWrap);
    var MAX_ATTACH_TOTAL = 20 * 1024 * 1024;  // matches the server cap
    function attachTotal() {
      return localAttachments.reduce(function (n, f) { return n + (f.size || 0); }, 0);
    }
    function renderAttachChips() {
      chipsEl.innerHTML = "";
      function chip(name, size, onRemove) {
        var c = document.createElement("span"); c.className = "sx__attach-chip";
        c.appendChild(document.createTextNode(name + " "));
        if (size) {
          var s = document.createElement("span"); s.className = "sx__attach-size";
          s.textContent = "(" + fmtBytes(size) + ") ";
          c.appendChild(s);
        }
        var x = document.createElement("button"); x.type = "button";
        x.className = "sx__chip-x"; x.textContent = "✕"; x.title = "Remove attachment";
        x.addEventListener("click", onRemove);
        c.appendChild(x); chipsEl.appendChild(c);
      }
      templateAttachments.forEach(function (a, i) {
        chip(a.name || "attachment", a.size || 0, function () {
          templateAttachments.splice(i, 1); renderAttachChips(); markEdited();
        });
      });
      localAttachments.forEach(function (f, i) {
        chip(f.filename, f.size || 0, function () {
          localAttachments.splice(i, 1); renderAttachChips(); markEdited();
        });
      });
      docAttachments.forEach(function (d, i) {
        chip("📄 " + d.filename, 0, function () {
          docAttachments.splice(i, 1); renderAttachChips(); markEdited();
        });
      });
      var total = attachTotal();
      attachTotalEl.hidden = !localAttachments.length;
      attachTotalEl.textContent = "Total " + fmtBytes(total) + " of 20 MB";
    }
    fileInput.addEventListener("change", function () {
      Array.prototype.forEach.call(fileInput.files || [], function (file) {
        if (attachTotal() + file.size > MAX_ATTACH_TOTAL) {
          footErr("“" + file.name + "” would push the attachments over 20 MB — remove something first.");
          return;
        }
        var reader = new FileReader();
        reader.onload = function () {
          var b64 = String(reader.result || "").split(",")[1] || "";
          localAttachments.push({
            filename: file.name,
            contentType: file.type || "application/octet-stream",
            dataBase64: b64,
            size: file.size,
          });
          renderAttachChips();
          markEdited();
        };
        reader.readAsDataURL(file);
      });
      fileInput.value = "";
    });
    function attachmentPayload() {
      return templateAttachments.map(function (a) {
        return { espoId: a.id, filename: a.name };
      }).concat(localAttachments.map(function (f) {
        return { filename: f.filename, contentType: f.contentType, dataBase64: f.dataBase64 };
      })).concat(docAttachments.map(function (d) {
        return { documentId: d.documentId, filename: d.filename };
      }));
    }

    var allowUnknown = false;
    var resolvedAddresses = {};   // addresses handled (linked/created) this compose
    var commResolvers = null;     // one entry per non-record recipient, built once
    var optionsPanel = document.createElement("div");
    body.appendChild(optionsPanel);

    // --- footer: status line + Cancel + Send (Send rightmost, the app's
    // primary-action slot; the message/summary stays pinned and visible).
    var foot = $("commModalFoot"); foot.innerHTML = "";
    var footMsg = document.createElement("p"); footMsg.className = "sx__foot-msg form-error"; footMsg.hidden = true;
    var footSummary = document.createElement("p"); footSummary.className = "sx__foot-summary";
    var cancel = document.createElement("button"); cancel.type = "button";
    cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
    cancel.addEventListener("click", requestCloseComm);
    var send = document.createElement("button"); send.type = "button";
    send.className = "cbm-button"; send.textContent = "Send";
    foot.appendChild(footSummary); foot.appendChild(footMsg);
    foot.appendChild(cancel); foot.appendChild(send);

    function footErr(text) {
      footMsg.textContent = text; footMsg.className = "sx__foot-msg form-error";
      footMsg.hidden = false; footSummary.hidden = true;
    }
    function footWarn(text) {
      footMsg.textContent = text; footMsg.className = "sx__foot-msg sx__notice is-warn";
      footMsg.hidden = false; footSummary.hidden = true;
    }
    function clearFootMsg() {
      footMsg.hidden = true; footSummary.hidden = false;
    }
    function updateSummary() {
      var s = recipientSets();
      var n = s.to.length + s.cc.length + s.bcc.length;
      if (!n) { footSummary.textContent = "No recipients selected."; return; }
      var parts = [];
      if (s.cc.length || s.bcc.length) {
        parts.push(s.to.length + " To");
        if (s.cc.length) parts.push(s.cc.length + " Cc");
        if (s.bcc.length) parts.push(s.bcc.length + " Bcc");
      }
      footSummary.textContent = "Sending to " + n + (n === 1 ? " recipient" : " recipients") +
        (parts.length ? " (" + parts.join(", ") + ")" : "");
    }

    // Any recipient change invalidates a built add-to-record panel and any
    // armed "send anyway" state — the user changed the question.
    var sendArmed = false;
    function disarmSend() {
      if (sendArmed) { sendArmed = false; send.textContent = commResolvers ? "Add & Send" : "Send"; }
    }
    function onRecipientsChanged() {
      if (commResolvers) {
        commResolvers = null; allowUnknown = false;
        optionsPanel.innerHTML = "";
        send.textContent = "Send";
      }
      disarmSend(); clearFootMsg(); updateSummary(); markEdited();
    }
    updateSummary();

    // --- draft persistence: an accidental close, tab crash, or session
    // expiry never loses a typed message. Saved (debounced) on every edit;
    // cleared on send or an explicit "Discard draft".
    var draftTimer = null;
    function draftState() {
      return {
        ts: Date.now(),
        subject: $("commSubject").value,
        body: String(commBodyValue() || ""),
        to: $("commTo").value,
        cc: $("commCc") ? $("commCc").value : "",
        bcc: $("commBcc") ? $("commBcc").value : "",
        ccShown: !ccField.hidden, bccShown: !bccField.hidden,
        checked: recipChecks.filter(function (r) { return r.box.checked; })
          .map(function (r) { return r.email.toLowerCase(); }),
        tplAttach: templateAttachments,
        docAttach: docAttachments,
      };
    }
    function flushDraft() {
      if (draftTimer) { clearTimeout(draftTimer); draftTimer = null; }
      if (draftHasContent()) storeDraft(replyKey, draftState());
    }
    function markEdited() {
      disarmSend();
      if (draftTimer) clearTimeout(draftTimer);
      draftTimer = setTimeout(function () {
        draftTimer = null;
        if (draftHasContent()) storeDraft(replyKey, draftState());
        else clearDraft(replyKey);
      }, 800);
    }
    var savedDraft = loadDraft(replyKey);
    if (savedDraft && (savedDraft.subject || savedDraft.body || savedDraft.to)) {
      $("commSubject").value = savedDraft.subject || "";
      if (savedDraft.body) setCommBody(savedDraft.body);
      $("commTo").value = savedDraft.to || "";
      if (savedDraft.ccShown || savedDraft.cc) { ccField.hidden = false; ccLink.hidden = true; $("commCc").value = savedDraft.cc || ""; }
      if (savedDraft.bccShown || savedDraft.bcc) { bccField.hidden = false; bccLink.hidden = true; $("commBcc").value = savedDraft.bcc || ""; }
      if (savedDraft.checked && recipChecks.length) {
        var wanted = {};
        savedDraft.checked.forEach(function (a) { wanted[a] = 1; });
        recipChecks.forEach(function (r) { r.box.checked = !!wanted[r.email.toLowerCase()]; });
      }
      templateAttachments = (savedDraft.tplAttach || []).slice();
      docAttachments = (savedDraft.docAttach || []).slice();
      renderAttachChips();
      updateSummary();
      var note = document.createElement("div"); note.className = "sx__notice sx__draft-note";
      note.appendChild(document.createTextNode("Restored your unsent draft."));
      var fresh = document.createElement("button"); fresh.type = "button";
      fresh.className = "sx__link-btn"; fresh.textContent = "Start fresh";
      fresh.addEventListener("click", function () {
        clearDraft(replyKey);
        note.remove();
        $("commSubject").value = initialSubject;
        setCommBody("");
        markPristine("");
        if (quoteHtml) { setCommBody("<p><br></p>" + quoteHtml); markPristine(commBodyValue()); }
        seedSignature();
        $("commTo").value = extra;
        if ($("commCc")) $("commCc").value = "";
        if ($("commBcc")) $("commBcc").value = "";
        recipChecks.forEach(function (r) {
          r.box.checked = pre.forward ? false
            : (pre.to ? preKeys.indexOf(r.email.toLowerCase()) !== -1 : true);
        });
        templateAttachments = []; localAttachments = []; docAttachments = [];
        renderAttachChips(); updateSummary(); clearFootMsg();
      });
      note.appendChild(fresh);
      body.insertBefore(note, body.firstChild);
    }

    // The close-guard: Escape / × / backdrop / Cancel confirm before
    // discarding real content; a reply returns to its conversation.
    composeGuard = {
      dirty: function () { return draftHasContent(); },
      discard: function () { flushDraftCancel(); clearDraft(replyKey); },
      send: function () { doSend(); },
      backConvId: pre.backToConv || null,
    };
    function flushDraftCancel() {
      if (draftTimer) { clearTimeout(draftTimer); draftTimer = null; }
    }

    // Recipients that are neither record contacts nor CBM-internal addresses.
    function unknownRecipients(recipients) {
      var known = {};
      ((currentDetail && currentDetail.contacts) || []).forEach(function (c) {
        if (c.email) known[String(c.email).toLowerCase()] = 1;
      });
      return recipients.filter(function (a) {
        a = a.toLowerCase();
        return !known[a] && !resolvedAddresses[a] && !/@cbmentors\.org$/.test(a);
      });
    }

    // Checkbox-driven router: every non-record recipient gets an "Add to this
    // record" checkbox (checked by default). Existing CRM contacts (any type)
    // just show who they are; unknown addresses show a small create form
    // (first/last/phone/company). ONE "Add & Send" click then links/creates
    // the checked ones and sends; unchecked recipients go as a one-off (the
    // conversation still attaches here and replies follow the thread).
    var companiesPromise = null;
    function getCompanies() {
      if (!companiesPromise) {
        companiesPromise = api("/companies").catch(function () { return { companies: [] }; });
      }
      return companiesPromise;
    }
    async function buildUnknownPanel(unknown) {
      optionsPanel.innerHTML = "<p class='sx__muted'>Checking the CRM for " +
        (unknown.length === 1 ? "this address…" : "these addresses…") + "</p>";
      var lookups = {};
      for (var i = 0; i < unknown.length; i++) {
        try { lookups[unknown[i]] = await api("/contactlookup?email=" + encodeURIComponent(unknown[i])); }
        catch (e) {
          if (e.status === 401) { flushDraft(); closeComm(); showLogin(); return; }
          lookups[unknown[i]] = { found: false };
        }
      }
      optionsPanel.innerHTML = "";
      var head = document.createElement("p"); head.className = "sx__notice is-warn";
      head.textContent = (unknown.length === 1 ? "This recipient isn't" : "These recipients aren't") +
        " a contact on this record. Leave \"Add to this record\" checked to link them" +
        " (fill in the details for new people), or uncheck to send without adding." +
        " Then click Add & Send.";
      optionsPanel.appendChild(head);
      commResolvers = [];
      unknown.forEach(function (addr) {
        optionsPanel.appendChild(addressRow(addr, lookups[addr] || { found: false }));
      });
      send.textContent = "Add & Send";
      optionsPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function addressRow(addr, lookup) {
      var row = document.createElement("div"); row.className = "sx__msg-field sx__addr-row";
      var head = document.createElement("div"); head.className = "sx__opt-line";
      var checkLab = document.createElement("label"); checkLab.className = "sx__addr-check";
      var check = document.createElement("input"); check.type = "checkbox"; check.checked = true;
      checkLab.appendChild(check);
      checkLab.appendChild(document.createTextNode(" Add to this record"));
      var who = document.createElement("span"); who.className = "sx__msg-label";
      head.appendChild(who); head.appendChild(checkLab);
      row.appendChild(head);
      var err = document.createElement("p"); err.className = "form-error"; err.hidden = true;

      var resolver;
      if (lookup.found && lookup.contact) {
        // Existing CRM contact — CBM, client, or non-client alike.
        var c = lookup.contact;
        var kind = c.isCbmMember ? "a CBM member" : (c.company ? c.company : "an existing contact");
        who.textContent = addr + " — " + (c.name || "?") + " (" + kind + ", already in the CRM)";
        var asComentor = c.isCbmMember && c.mentorProfileId &&
          (config && config.supportsComentor);
        if (asComentor) checkLab.childNodes[1].textContent = " Add as CBM contact";
        if (c.isCbmMember && !asComentor) {
          // A CBM member must NEVER be linked as a client contact (that put
          // mentors under "Other Contacts"). No co-mentor path here => they
          // simply receive the email.
          check.checked = false; check.disabled = true;
          checkLab.childNodes[1].textContent = " Will receive the email";
        }
        resolver = async function () {
          if (!check.checked) return false;
          if (asComentor) {
            await api("/records/" + encodeURIComponent(currentDetail.id) + "/comentors", {
              method: "POST", body: JSON.stringify({ mentorProfileId: c.mentorProfileId }),
            });
          } else {
            await api("/records/" + encodeURIComponent(currentDetail.id) + "/contacts", {
              method: "POST", body: JSON.stringify({ contactId: c.id }),
            });
          }
          resolvedAddresses[addr.toLowerCase()] = 1;
          return true;
        };
      } else {
        // Unknown to the CRM — create form (enabled while the box is checked).
        who.textContent = addr + " — not in the CRM yet";
        var line2 = document.createElement("div"); line2.className = "sx__opt-line";
        var first = document.createElement("input"); first.type = "text"; first.placeholder = "First name"; first.className = "sx__msg-input";
        var last = document.createElement("input"); last.type = "text"; last.placeholder = "Last name"; last.className = "sx__msg-input";
        var phone = document.createElement("input"); phone.type = "tel"; phone.placeholder = "Phone (optional)"; phone.className = "sx__msg-input";
        line2.appendChild(first); line2.appendChild(last); line2.appendChild(phone);
        row.appendChild(line2);
        // Company: type-ahead over the CRM's accounts (fetched once per
        // compose, shared across rows) + a "+ New company…" escape.
        var line3 = document.createElement("div"); line3.className = "sx__opt-line";
        var companyChoice = { id: "", newName: "" };
        var newCompany = document.createElement("input"); newCompany.type = "text";
        newCompany.placeholder = "New company name"; newCompany.className = "sx__msg-input"; newCompany.hidden = true;
        var companyCombo = makeCombobox({
          placeholder: "Company… (type to search)",
          allowClear: true,
          emptyLabel: "No company",
          onSelect: function (id, o) {
            if (id === "__new__") {
              companyChoice.id = "__new__"; newCompany.hidden = false; newCompany.focus();
            } else {
              companyChoice.id = id || ""; newCompany.hidden = true; newCompany.value = "";
            }
          },
        });
        getCompanies().then(function (res) {
          var opts = (res.companies || []).map(function (a) { return { id: a.id, label: a.name || a.id }; });
          opts.push({ id: "__new__", label: "+ New company…", muted: true });
          companyCombo.setOptions(opts);
        });
        line3.appendChild(companyCombo.el); line3.appendChild(newCompany);
        row.appendChild(line3);
        function setEnabled() {
          [first, last, phone, companyCombo.input, newCompany].forEach(function (el) { el.disabled = !check.checked; });
        }
        check.addEventListener("change", setEnabled);
        resolver = async function () {
          if (!check.checked) return false;
          if (!first.value.trim() && !last.value.trim()) {
            throw new Error("Enter a name for " + addr + " (or uncheck \"Add to this record\").");
          }
          var changes = { firstName: first.value.trim(), lastName: last.value.trim(), emailAddress: addr };
          if (phone.value.trim()) changes.phoneNumber = phone.value.trim();
          var payload = { changes: changes };
          if (companyChoice.id === "__new__" && newCompany.value.trim()) payload.newCompanyName = newCompany.value.trim();
          else if (companyChoice.id && companyChoice.id !== "__new__") changes.accountId = companyChoice.id;
          await api("/records/" + encodeURIComponent(currentDetail.id) + "/contacts", {
            method: "POST", body: JSON.stringify(payload),
          });
          resolvedAddresses[addr.toLowerCase()] = 1;
          return true;
        };
      }
      row.appendChild(err);
      commResolvers.push({ addr: addr, resolve: resolver, errEl: err });
      return row;
    }

    async function doSend() {
      if (!commsOn()) {
        // No delivery in scaffold mode — communicate that plainly.
        $("commModalBody").innerHTML = "";
        var note = document.createElement("p"); note.className = "sx__notice is-success";
        note.textContent = "Sending isn't available yet — the email integration hasn't been enabled for this deployment.";
        $("commModalBody").appendChild(note);
        $("commModalFoot").innerHTML = "";
        var ok = document.createElement("button"); ok.type = "button";
        ok.className = "cbm-button"; ok.textContent = "OK"; ok.addEventListener("click", closeComm);
        $("commModalFoot").appendChild(ok);
        return;
      }
      var sets = recipientSets();
      if (sets.invalid.length) {
        footErr("These don't look like email addresses: " + sets.invalid.join(", ") +
          " — fix or remove them. Separate addresses with commas.");
        return;
      }
      var recipients = sets.to.concat(sets.cc, sets.bcc);
      if (!recipients.length) {
        footErr("Choose at least one recipient.");
        $("commTo").focus();
        return;
      }
      // A pristine body blocks the send — EXCEPT on a forward, where the
      // forwarded block alone IS the message (forwarding without comment is
      // normal email behavior).
      if (bodyPristine() && !pre.forward) {
        footErr("Write a message first.");
        var bodyEl = $("commBody");
        if (bodyEl && bodyEl._cbmRichText) bodyEl._cbmRichText.focus();
        else if (bodyEl) bodyEl.focus();
        return;
      }
      // "Send anyway" gate: a missing subject or unresolved template
      // placeholders deserve one explicit look before the email goes out.
      var holdups = [];
      if (!$("commSubject").value.trim()) holdups.push("it has no subject");
      var tokenScan = ($("commSubject").value + " " + String(commBodyValue() || ""))
        .replace(new RegExp("<blockquote[\\s\\S]*$"), "");  // quoted original may legitimately carry braces
      var leftover = tokenScan.match(/\{[A-Za-z][A-Za-z0-9]*\.[A-Za-z0-9_]+\}/g);
      if (leftover) holdups.push("it still contains unfilled placeholders (" + leftover.slice(0, 3).join(", ") + ")");
      if (holdups.length && !sendArmed) {
        sendArmed = true;
        footWarn("Before this goes out: " + holdups.join(", and ") + ". Click “Send anyway” to send it as is.");
        send.textContent = "Send anyway";
        return;
      }
      clearFootMsg();
      var unknown = unknownRecipients(recipients);
      if (unknown.length && commResolvers === null) {
        await buildUnknownPanel(unknown);   // first click: show the rows
        return;
      }
      // Process the checkbox rows: link/create the checked ones; anything
      // unchecked goes as a one-off (server needs the explicit flag).
      if (commResolvers) {
        for (var ri = 0; ri < commResolvers.length; ri++) {
          var r = commResolvers[ri];
          if (resolvedAddresses[r.addr.toLowerCase()]) continue;
          r.errEl.hidden = true;
          try {
            var did = await r.resolve();
            if (!did) allowUnknown = true;
          } catch (e) {
            if (e.status === 401) { flushDraft(); closeComm(); showLogin(); return; }
            r.errEl.textContent = e.message; r.errEl.hidden = false;
            r.errEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
            footErr("Fix the highlighted recipient above (or uncheck it), then Send again.");
            return;
          }
        }
      }
      send.disabled = true; send.textContent = "Sending…";
      var payload = {
        to: sets.to,
        cc: sets.cc,
        bcc: sets.bcc,
        subject: $("commSubject").value,
        body: commBodyValue(),
        replyToCommunicationId: pre.replyToId || null,
        allowUnknownRecipients: allowUnknown,
        attachments: attachmentPayload(),
      };
      // Attachments make the body big — show upload progress past ~300 KB.
      var showProgress = JSON.stringify(payload).length > 300 * 1024;
      try {
        var sendResult = await apiPostProgress(
          "/records/" + encodeURIComponent(currentDetail.id) + "/messages",
          payload,
          showProgress ? function (pct) { send.textContent = "Sending… " + pct + "%"; } : null
        );
        clearDraft(replyKey);
        // The message went out. If recording it in the CRM failed, say so and
        // offer a retry — a silent gap in CRM history is not acceptable (ET-142).
        if (sendResult && sendResult.writeBack && sendResult.writeBack.ok === false) {
          composeGuard = null;
          showWriteBackRetry(sendResult.writeBack);
          loadConversations();
          return;
        }
        closeComm();
        // ingestWarning: the email went OUT, but the tab may not show it yet
        // (write-through/attach failure) — say so instead of silence.
        if (sendResult && sendResult.ingestWarning) {
          notice("detailNotice", "Email sent. " + sendResult.ingestWarning, "error");
        } else {
          notice("detailNotice", "Email sent.", "success");
        }
        loadConversations();
      } catch (e) {
        if (e.status === 401) { flushDraft(); closeComm(); showLogin(); return; }
        footErr(e.message);
        send.disabled = false; send.textContent = commResolvers ? "Add & Send" : "Send";
        sendArmed = false;
        // The server is the authority: if it still refuses (contacts changed
        // under us), rebuild the rows for whatever is still unknown.
        if (e.status === 400 && /aren't contacts/.test(e.message || "")) {
          commResolvers = null;
          var still = unknownRecipients(recipientList());
          if (still.length) await buildUnknownPanel(still);
        }
      }
    }
    send.addEventListener("click", doSend);
    // Sent-but-not-recorded: swap the dialog to a retry screen (ET-142).
    function showWriteBackRetry(writeBack) {
      $("commModalBody").innerHTML = "";
      var note = document.createElement("p"); note.className = "sx__notice is-error";
      note.textContent = writeBack.error ||
        "The message WAS sent, but recording it in the CRM failed.";
      $("commModalBody").appendChild(note);
      $("commModalFoot").innerHTML = "";
      var retry = document.createElement("button"); retry.type = "button";
      retry.className = "cbm-button"; retry.textContent = "Retry recording";
      var close = document.createElement("button"); close.type = "button";
      close.className = "cbm-button cbm-button--secondary"; close.textContent = "Close";
      retry.addEventListener("click", async function () {
        retry.disabled = true; retry.textContent = "Recording…";
        try {
          await api("/emailwriteback", {
            method: "POST", body: JSON.stringify(writeBack.retryPayload || {}),
          });
          closeComm();
          notice("detailNotice", "Email sent and recorded in the CRM.", "success");
        } catch (e) {
          if (e.status === 401) { closeComm(); showLogin(); return; }
          note.textContent = (e.message || "Still couldn't record it.") + " Try again?";
          retry.disabled = false; retry.textContent = "Retry recording";
        }
      });
      close.addEventListener("click", closeComm);
      $("commModalFoot").appendChild(retry); $("commModalFoot").appendChild(close);
    }

    // Keyboard start: the first thing that still needs filling in.
    var focusTarget = null;
    if (!recipientList().length) focusTarget = $("commTo");
    else if (!$("commSubject").value.trim()) focusTarget = $("commSubject");
    if (focusTarget) focusTarget.focus();
    else {
      // Everything prefilled — write the message. The caret lands at the top
      // (above the signature / quoted original), Gmail-style.
      var be = $("commBody");
      if (be && be._cbmRichText) be._cbmRichText.focus();
      else if (be) be.focus();
    }
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
      if (res.restricted) { body.innerHTML = "<p class='sx__muted'>You don't have permission to view this record.</p>"; return; }
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
    // Sections the user's ACL can't read are OMITTED (an unassigned user
    // just sees the company information — no permission noise).
    var visible = results.filter(function (r) { return !(r.data && r.data.restricted); });
    if (!visible.length) {
      body.innerHTML = "<p class='sx__muted'>No details available.</p>"; return;
    }
    visible.forEach(function (r) {
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
    if (f.type === "email" && v) { el.appendChild(emailComposeLink(String(v))); return; }
    if (f.type === "phone" && v) { var p = document.createElement("a"); p.href = "tel:" + v; p.textContent = fmtPhone(v); p.title = String(v); el.appendChild(p); return; }
    if (f.type === "url" && v) { var u = document.createElement("a"); u.href = externalHref(v); u.target = "_blank"; u.rel = "noopener"; u.textContent = v; el.appendChild(u); return; }
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
    if (entity === "CMentorProfile") return "Mentor profile";
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

  // --- Details tab (mockup v4): engagement summary strip + composed org cards +
  //     contact tables (Client Contacts / CBM Contacts) with per-section editing ---
  async function ensureDetails() {
    if (!currentDetail) return;
    if (currentDetails && currentDetails._for === currentDetail.id) return;
    await loadDetails(currentDetail.id);
  }

  async function loadDetails(id) {
    show($("detailsLoading")); $("detailsSections").innerHTML = ""; hide($("detailsNotice"));
    detailsEditSet = {}; detailsSnapshot = {}; detailsAdd = null;
    try {
      var res = await api("/details/" + encodeURIComponent(id));
      res._for = id; currentDetails = res;
      renderDetails();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("detailsNotice", e.message, "error");
    } finally { hide($("detailsLoading")); }
  }

  // Top to bottom, single column: summary strip (the parent record) → org cards
  // (Company / profile) → Client Contacts table → CBM Contacts table. No
  // page-global Edit bar — the strip, each card, and each contact row edit
  // independently.
  function renderDetails() {
    if (!currentDetails) return;
    hide($("detailsNotice"));
    var host = $("detailsSections"); host.innerHTML = "";
    (currentDetails.sections || []).forEach(function (sec, i) {
      host.appendChild(sec.kind === "parent" ? parentStrip(sec, "parent") : orgCard(sec, "org" + i));
    });
    host.appendChild(clientContactsCard());
    if (currentDetails.cbmContacts) host.appendChild(cbmContactsCard());
  }

  // Re-render only the element owning `key` so an open edit form elsewhere keeps
  // its typed input. A contact-row key repaints its whole card (the row lives in
  // its table); an unknown/missing key falls back to a full re-render.
  function repaintDetails(key) {
    if (!currentDetails) return;
    // Row edit keys are "c<idx>" / "b<idx>" — match exactly, since the card key
    // "cbmContacts" also starts with "c" (mapping it to clientContacts left the
    // CBM card unrepainted, so its + Add menu never opened).
    if (/^c\d+$/.test(key)) key = "clientContacts";
    if (/^b\d+$/.test(key)) key = "cbmContacts";
    var host = $("detailsSections");
    var el = host.querySelector('[data-dkey="' + key + '"]');
    var next = buildDetailsKey(key);
    if (el && next) { el.parentNode.replaceChild(next, el); } else { renderDetails(); }
  }

  function buildDetailsKey(key) {
    var secs = (currentDetails && currentDetails.sections) || [];
    if (key === "parent") {
      for (var i = 0; i < secs.length; i++) if (secs[i].kind === "parent") return parentStrip(secs[i], key);
      return null;
    }
    if (key.indexOf("org") === 0) {
      var idx = Number(key.slice(3));
      return secs[idx] ? orgCard(secs[idx], key) : null;
    }
    if (key === "clientContacts") return clientContactsCard();
    if (key === "cbmContacts") return cbmContactsCard();
    return null;
  }

  // === Section edit screens (prompt v0.2 / Company mockup v3) ================
  // Each entity's edit form is a curated 12-column grid: labeled groups of rows,
  // field widths as mocked. Cell shapes: {name, span[, label]} = one field;
  // {checks:[names]} = a two-column checkbox set; {addr: prefix[, sameAs]} = the
  // shared postal address block; {ro, label} = a read-only value from the
  // section (e.g. the assigned mentor — reassignment stays in Client
  // Administration, Doug's 2026-07-13 ruling). Editable fields the layout
  // doesn't place land in an "Additional details" group so nothing the CRM
  // exposes becomes uneditable — EXCEPT layouts flagged `noExtras: true`
  // (prompt v0.2 standing rule 2: unplaced schema fields are candidates that
  // need an explicit placement/exclusion decision, never auto-rendered);
  // names in the domain's exclude set never render anywhere.
  var DETAILS_LAYOUTS = {
    // Engagement panel per the mockup-v4 process (2026-07-16): every schema
    // field placed or excluded (`noExtras`). Session statistics (totals,
    // last/next session) and the Assign-action date stamp are CRM/app-
    // maintained — excluded from EDIT (DETAILS_REMOVED_FIELDS) but still
    // shown on the summary strip; `description` is Client Administration's
    // staff-only notes (server-side exclude). Mentor stays read-only —
    // reassignment belongs to Client Administration (Doug's 2026-07-13
    // ruling).
    CEngagement: { noExtras: true, groups: [
      { label: "Engagement", grow: 2, basis: 46, rows: [
        [{ name: "engagementStatus", span: 3 }, { name: "engagementStartDate", span: 3 },
         { ro: "mentorProfileName", label: "Mentor", span: 3 }, { name: "meetingCadence", span: 3 }],
        [{ name: "holdEndDate", span: 4 }, { name: "closeDate", span: 4 }, { name: "closeReason", span: 4 }],
      ] },
      { label: "Outcomes", grow: 2, basis: 40, rows: [
        [{ checks: [{ name: "newBusinessStarted", label: "New business started" },
                    { name: "newLocationOpened", label: "New location opened" },
                    { name: "significantRevenueIncrease", label: "Significant revenue increase" },
                    { name: "significantEmploymentIncrease", label: "Significant employment increase" }] }],
        [{ name: "revenueIncreasePercentage", span: 4, label: "Revenue increase %" },
         { name: "employmentIncreasePercentage", span: 4, label: "Employment increase %" }],
      ] },
      { label: "Mentoring need & focus", grow: 3, basis: 52, rows: [
        [{ name: "mentoringFocusAreas", span: 12 }],
        [{ name: "mentoringNeedsDescription", span: 12 }],
      ] },
      { label: "Engagement notes", grow: 2, basis: 44, rows: [
        [{ name: "engagementNotes", span: 12 }],
      ] },
    ] },
    // Company form per mockup v3 (prompt v0.2): Identity / Web presence /
    // Addresses / Notes, in that order. `noExtras` — schema fields the mockup
    // doesn't place are candidates, not requirements (standing rule 2): they
    // never auto-render in an "Additional details" dump; placing one is an
    // explicit layout decision.
    Account: { noExtras: true, groups: [
      { label: "Identity", grow: 3, basis: 52, rows: [
        [{ name: "name", span: 6, label: "Company name" }, { name: "phoneNumber", span: 3 }, { name: "emailAddress", span: 3 }],
        [{ name: "cOrganizationType", span: 3 }, { name: "cBusinessStage", span: 3 },
         { name: "industry", span: 3 }, { name: "sicCode", span: 3, label: "SIC code" }],
        [{ name: "cIndustrySector", span: 6 }, { name: "cIndustrySubsector", span: 6 }],
      ] },
      { label: "Web presence", grow: 1, basis: 28, rows: [
        [{ name: "website", span: 6 }, { name: "cLinkedInPage", span: 6, label: "LinkedIn page" }],
      ] },
      // Billing left, shipping right (the shared address block includes Country).
      { label: "Addresses", grow: 3, basis: 52, rows: [
        [{ addr: "billingAddress", span: 6, title: "Billing" },
         { addr: "shippingAddress", span: 6, title: "Shipping", sameAs: "billingAddress" }],
      ] },
      { label: "Notes", grow: 2, basis: 44, rows: [
        [{ name: "description", span: 12 }],
        [{ name: "cClientNotes", span: 12, label: "Client notes" }],
      ] },
    ] },
    // Client Business Profile per the mockup-v4 process (2026-07-16): every
    // schema field explicitly placed or excluded (`noExtras`), groups sized
    // as packable panels. The previously-unplaced fields (state of formation,
    // industry sector, employees, fiscal year end, social media, local
    // licenses) now have homes; the read-only revenue figure shows inside
    // Financials; the record name + revenue Currency/Converted companions
    // are excluded (DETAILS_REMOVED_FIELDS).
    CClientProfile: { noExtras: true, groups: [
      { label: "Business structure", grow: 2, basis: 46, rows: [
        [{ name: "legalEntityType", span: 4 }, { name: "stateOfFormation", span: 4 }, { name: "formationDate", span: 4 }],
        [{ name: "industrySector", span: 6 }, { name: "numberOfEmployees", span: 3 }, { name: "fiscalYearEndMonth", span: 3 }],
        [{ checks: [{ name: "isHomeBased", label: "Home based" },
                    { name: "federalEinOnFile", label: "Federal EIN on file" },
                    { name: "ohioVendorsLicenseOnFile", label: "Ohio vendors license on file" },
                    { name: "registeredOnSamGov", label: "Registered on SAM.gov" }] }],
        [{ name: "localLicensesAndPermits", span: 12 }],
      ] },
      { label: "Financials", grow: 2, basis: 40, rows: [
        [{ name: "annualRevenueRange", span: 4 }, { name: "revenueTrend", span: 4 }, { name: "profitabilityStatus", span: 4 }],
        [{ name: "mostRecentFullYearRevenue", span: 6, label: "Most recent full-year revenue" }],
        [{ name: "fundingSourcesUsedToDate", span: 12 }],
      ] },
      { label: "Sales & market", grow: 2, basis: 44, rows: [
        [{ name: "primaryCustomerType", span: 8 }, { name: "geographicMarketReach", span: 4 }],
        [{ name: "salesChannels", span: 6 }, { name: "socialMediaPresence", span: 6 }],
        [{ checks: [{ name: "conductsBusinessOnline", label: "Conducts business online" },
                    { name: "hasGoogleBusinessProfile", label: "Has Google Business Profile" },
                    { name: "usesEmailMarketing", label: "Uses email marketing" }] }],
      ] },
      { label: "Certifications & owner demographics", grow: 2, basis: 40, rows: [
        [{ name: "certificationsHeld", span: 12 }],
        [{ name: "clientEthnicity", span: 4 }, { name: "clientRace", span: 4 }, { name: "clientVeteranStatus", span: 4 }],
      ] },
      { label: "Goals", grow: 2, basis: 44, rows: [[{ name: "description", span: 12, label: "What does the client want help with?" }]] },
    ] },
    // Partnership profile (Doug's 2026-07-18 report): a curated form instead
    // of the generic "Additional details" dump. `description` (the intake
    // form's enum-drift triage note) is excluded server-side; **Partner
    // Notes is THE notes field** — it feeds the Overview's Partner Notes
    // panel. The record name mirrors the company (excluded, header shows it).
    CPartnerProfile: { noExtras: true, groups: [
      { label: "Partnership", grow: 2, basis: 46, rows: [
        [{ name: "partnershipStatus", span: 4 }, { name: "partnershipType", span: 4 },
         { name: "partnerContactCadence", span: 4, label: "Contact cadence" }],
        [{ name: "partnershipStartDate", span: 4 }, { name: "partnershipAgreementDate", span: 4 },
         { name: "lastContacted", span: 4 }],
      ] },
      { label: "Value & goals", grow: 2, basis: 40, rows: [
        [{ name: "partnershipValue", span: 6 }, { name: "cBMValueProvided", span: 6 }],
        [{ name: "relationGoalsEst", span: 6, label: "Relationship goals established" }],
      ] },
      { label: "Partner notes", grow: 3, basis: 52, rows: [
        [{ name: "partnerNotes", span: 12 }],
      ] },
    ] },
    // Sponsorship profile (same pass as partner, Doug's 2026-07-18 ruling):
    // curated form, no generic dump. Here `description` IS the sponsor-notes
    // field (it feeds the Overview's Sponsor Notes panel), so it stays —
    // labeled "Sponsor notes". Total contribution is CRM-computed (read-only
    // on the strip); its currency companion is excluded like the client
    // profile's revenue companions.
    CSponsorProfile: { noExtras: true, groups: [
      { label: "Sponsorship", grow: 1, basis: 32, rows: [
        [{ name: "lastContribution", span: 6 }, { name: "lastContacted", span: 6 }],
      ] },
      { label: "Sponsor notes", grow: 3, basis: 52, rows: [
        [{ name: "description", span: 12, label: "Sponsor notes" }],
      ] },
    ] },
    Contact: { groups: [
      { label: "Name", rows: [
        [{ name: "salutationName", span: 2, label: "Salutation" }, { name: "firstName", span: 4 },
         { name: "lastName", span: 4 }, { name: "cPreferredName", span: 2 }],
      ] },
      { label: "Contact information", rows: [
        [{ name: "emailAddress", span: 6 }, { name: "phoneNumber", span: 3 }, { name: "cContactType", span: 3 }],
      ] },
      { label: "Address", rows: [[{ addr: "address", span: 6 }]] },
      { label: "Preferences & agreements", rows: [
        [{ name: "cPreferredContactMethod", span: 4 }, { name: "cNotificationPreference", span: 4 }, { name: "doNotCall", span: 4 }],
        [{ checks: [{ name: "cMarketingOptIn", label: "Marketing opt-in" },
                    { name: "cPrivacyPolicyAccepted", label: "Privacy policy accepted" },
                    { name: "cTermsOfUseAccepted", label: "Terms of use accepted" },
                    { name: "cCodeOfConductAccepted", label: "Code of conduct accepted" }] }],
      ] },
    ] },
  };

  // Account fields by business relationship. The system discriminators are
  // edited nowhere (intake/orchestrators own them); each domain's Company form
  // additionally excludes the OTHER domains' relationship fields (mentor-domain
  // accounts are client accounts — Doug's 2026-07-13 scoping ruling).
  var ACCOUNT_SYSTEM_FIELDS = ["cAccountType", "cClientStatus", "cCompanyType", "type"];
  // Removed from this app's forms entirely (mockup-v4 field triage — the CRM
  // fields stay untouched for other workflows). Account (prompt v0.2): the
  // sponsor pledge currency + partner-org target population, the system-
  // managed applicant timestamp, and the contact-level role attribute.
  // CClientProfile: the record name (intake-derived; the card title already
  // identifies the record) and the revenue Currency/Converted companions of
  // the read-only revenue figure.
  var DETAILS_REMOVED_FIELDS = {
    Account: ["cAnnualPledgeAmountCurrency", "cTargetPopulation",
      "cApplicantSinceTimestamp", "contactRole"],
    CClientProfile: ["name", "mostRecentFullYearRevenueCurrency",
      "mostRecentFullYearRevenueConverted"],
    // CEngagement: the record name (the page header shows it), the Assign-
    // action date stamp, and the session statistics the CRM/app maintain —
    // all still visible on the summary strip, just never hand-editable.
    CEngagement: ["name", "engagementAssignedDate", "lastSessionDate",
      "nextSessionDateTime", "totalSessions", "totalSessionsLast30Days",
      "totalSessionHours"],
    // CPartnerProfile: the record name mirrors the company (header shows it);
    // `description` is excluded server-side.
    CPartnerProfile: ["name"],
    // CSponsorProfile: name as above; the currency companion of the computed
    // total-contribution figure (the figure itself stays on the strip).
    CSponsorProfile: ["name", "totalContributionCurrency"],
  };
  var ACCOUNT_PARTNER_FIELDS = ["cPartnerStatus", "cPartnerOrganizationType", "cPartnerContactCadence",
    "cPartnerType", "cPartnershipStartDate", "cPartnershipAgreementDate", "cPartnerNotes"];
  var ACCOUNT_SPONSOR_FIELDS = ["cSponsorshipLevel", "cSponsorshipStartDate", "cSponsorshipRenewalDate", "cSponsorNotes"];
  // The other domains keep a curated group of their own relationship fields.
  var ACCOUNT_DOMAIN_GROUPS = {
    // No cPartnerNotes row: the Account-level notes twin confused edits —
    // the ONE Partner Notes field is CPartnerProfile.partnerNotes (it feeds
    // the Overview panel), edited on the Partnership strip (Doug's
    // 2026-07-18 report: notes typed here never showed on the Overview).
    partnersessions: { label: "Partnership", rows: [
      [{ name: "cPartnerStatus", span: 4 }, { name: "cPartnerOrganizationType", span: 4 }, { name: "cPartnerContactCadence", span: 4 }],
      [{ name: "cPartnerType", span: 12 }],
      [{ name: "cPartnershipStartDate", span: 4 }, { name: "cPartnershipAgreementDate", span: 4 }],
      [{ checks: ["cPublicAnnouncementAllowed"] }],
    ] },
    // No cSponsorNotes row (same fix as partner): the Account-level notes
    // twin is retired — the ONE Sponsor Notes field is
    // CSponsorProfile.description (it feeds the Overview panel), edited on
    // the Sponsorship strip.
    sponsorsessions: { label: "Sponsorship", rows: [
      [{ name: "cSponsorshipLevel", span: 4 }, { name: "cSponsorshipStartDate", span: 4 }, { name: "cSponsorshipRenewalDate", span: 4 }],
      [{ checks: ["cPublicAnnouncementAllowed"] }],
    ] },
  };

  // The exclude set for an entity's form AND view (the view must not display
  // fields the edit form doesn't manage).
  function detailsExcludes(entity) {
    var ex = {};
    (DETAILS_REMOVED_FIELDS[entity] || []).forEach(function (n) { ex[n] = 1; });
    if (entity !== "Account") return ex;
    ACCOUNT_SYSTEM_FIELDS.forEach(function (n) { ex[n] = 1; });
    if (SLUG === "mentorsessions") {
      ACCOUNT_PARTNER_FIELDS.concat(ACCOUNT_SPONSOR_FIELDS).forEach(function (n) { ex[n] = 1; });
      ex.cPublicAnnouncementAllowed = 1;
    } else if (SLUG === "partnersessions") {
      ACCOUNT_SPONSOR_FIELDS.forEach(function (n) { ex[n] = 1; });
      // Client-specific notes have no place on a partner's company (Doug's
      // 2026-07-18 report), and the Account-level partner-notes twin is
      // retired — CPartnerProfile.partnerNotes is the one notes field.
      ["description", "cClientNotes", "cPartnerNotes"].forEach(function (n) { ex[n] = 1; });
    } else if (SLUG === "sponsorsessions") {
      ACCOUNT_PARTNER_FIELDS.forEach(function (n) { ex[n] = 1; });
      // Client-specific notes have no place on a sponsor's company, and the
      // Account-level sponsor-notes twin is retired —
      // CSponsorProfile.description is the one notes field.
      ["description", "cClientNotes", "cSponsorNotes"].forEach(function (n) { ex[n] = 1; });
    }
    return ex;
  }

  function detailsLayoutFor(entity) {
    var base = DETAILS_LAYOUTS[entity];
    if (entity === "Account" && ACCOUNT_DOMAIN_GROUPS[SLUG]) {
      return { noExtras: base.noExtras, groups: base.groups.concat([ACCOUNT_DOMAIN_GROUPS[SLUG]]) };
    }
    return base || { groups: [] };
  }

  // Build one section's grouped form body. Returns the element; every editable
  // input carries data-field, so the snapshot/diff save machinery is unchanged.
  function layoutForm(sec, layout) {
    var byName = {}; (sec.fields || []).forEach(function (f) { byName[f.name] = f; });
    var exclude = detailsExcludes(sec.entity);
    var used = {};
    var body = document.createElement("div"); body.className = "sxf";

    function fieldCell(cell) {
      var f = byName[cell.name];
      used[cell.name] = 1;
      if (!f || exclude[cell.name]) return null;
      if (cell.label) f = Object.assign({}, f, { label: cell.label });
      var el = f.editable ? detailsEditField(f) : detailsReadField(f);
      el.classList.add("sxf__c" + (cell.span || 12));
      return el;
    }

    // Each layout row is ONE flex line (fields never orphan onto random
    // lines); the group's rows live in a .sxf__rows stack.
    function grid(rows) {
      var g = document.createElement("div"); g.className = "sxf__rows";
      rows.forEach(function (row) {
        var line = document.createElement("div"); line.className = "sxf__row";
        row.forEach(function (cell) {
          var el = null;
          if (cell.name) el = fieldCell(cell);
          else if (cell.checks) {
            var box = document.createElement("div"); box.className = "sxf__checks sxf__c12";
            cell.checks.forEach(function (n) {
              var nm = n.name || n;
              used[nm] = 1;
              var f = byName[nm];
              if (!f || !f.editable || exclude[nm]) return;
              if (n.label) f = Object.assign({}, f, { label: n.label });
              box.appendChild(detailsEditField(f));
            });
            el = box.childNodes.length ? box : null;
          } else if (cell.addr) {
            el = addressBlock(byName, used, cell.addr, cell.sameAs, cell.span, cell.title);
          } else if (cell.ro) {
            var v = dv(sec, cell.ro);
            if (v) {
              el = document.createElement("div"); el.className = "cbm-field sxf__c" + (cell.span || 3);
              var lab = document.createElement("label"); lab.textContent = cell.label || cell.ro;
              var inp = document.createElement("input"); inp.type = "text"; inp.value = String(v); inp.disabled = true;
              el.appendChild(lab); el.appendChild(inp);
            }
          }
          if (el) line.appendChild(el);
        });
        if (line.childNodes.length) g.appendChild(line);
      });
      return g;
    }

    // Groups are PACKABLE PANELS (mockup v4): each has a natural width
    // (`basis` rem, sized to its widest row) and a `grow` weight; panels
    // flow left-to-right and every band always fills the window width.
    (layout.groups || []).forEach(function (g) {
      var wrap = document.createElement("div"); wrap.className = "sxf__group";
      wrap.style.flex = (g.grow || 2) + " 1 " + (g.basis || 44) + "rem";
      if (g.label) {
        var h = document.createElement("div"); h.className = "sxf__glabel"; h.textContent = g.label;
        wrap.appendChild(h);
      }
      var gr = grid(g.rows || []);
      if (!gr.childNodes.length) return;  // whole group missing on this CRM — skip
      wrap.appendChild(gr);
      body.appendChild(wrap);
    });

    // Everything editable the layout didn't place (and read-only computed
    // values). Suppressed for layouts flagged `noExtras` (prompt v0.2 standing
    // rule 2): unplaced schema fields need an explicit placement decision.
    var leftovers = layout.noExtras ? []
      : (sec.fields || []).filter(function (f) { return !used[f.name] && !exclude[f.name]; });
    if (leftovers.length) {
      var wrap2 = document.createElement("div"); wrap2.className = "sxf__group";
      wrap2.style.flex = "2 1 44rem";
      if ((layout.groups || []).length) {
        var h2 = document.createElement("div"); h2.className = "sxf__glabel"; h2.textContent = "Additional details";
        wrap2.appendChild(h2);
      }
      var g2 = document.createElement("div"); g2.className = "sxf__rows";
      var line2 = document.createElement("div"); line2.className = "sxf__row";
      leftovers.forEach(function (f) {
        var wide = f.type === "text" || f.type === "wysiwyg";
        var el = f.editable ? detailsEditField(f) : detailsReadField(f);
        el.classList.add(wide ? "sxf__c12" : "sxf__c4");
        line2.appendChild(el);
      });
      g2.appendChild(line2);
      wrap2.appendChild(g2);
      body.appendChild(wrap2);
    }
    return body;
  }

  // --- Reusable address block (postal layout; built once, used everywhere) ---
  // Row 1: Address line 1 (8) | Address line 2 (4); Row 2: City (6) | State
  // (2, select) | ZIP (4). EspoCRM stores one multi-line street field — line 1
  // is its first line, line 2 the rest (rejoined on save via readField's
  // "addressStreet" handling). `sameAs` adds the "Same as billing address"
  // checkbox: checked = shipping inputs dimmed/disabled and mirrored from
  // billing (the CRM models this as copied values — there is no flag).
  var US_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY"];

  function addressBlock(byName, used, prefix, sameAs, span, title) {
    ["Street", "City", "State", "PostalCode", "Country"].forEach(function (s) { used[prefix + s] = 1; });
    if (!byName[prefix + "Street"] && !byName[prefix + "City"]) return null;  // entity has no such address
    var outer = document.createElement("div"); outer.className = "sxf__c" + (span || 12);
    var tl = null;
    if (title) {
      tl = document.createElement("div"); tl.className = "sxf__sublabel"; tl.textContent = title;
      outer.appendChild(tl);
    }
    var block = document.createElement("div"); block.className = "sxf__addr";

    function labeled(label, input, span) {
      var w = document.createElement("div"); w.className = "cbm-field sxf__c" + span;
      var l = document.createElement("label"); l.textContent = label;
      w.appendChild(l); w.appendChild(input); return w;
    }
    // Street: two visible line inputs, ONE data-field (the line-1 cell) so the
    // save/diff machinery sees one street value; readField("addressStreet")
    // finds line 2 through the shared grid and rejoins them.
    var street = String((byName[prefix + "Street"] || {}).value || "");
    var parts = street.split("\n");
    var a1 = document.createElement("input"); a1.type = "text"; a1.className = "sxf__a1"; a1.value = parts[0] || "";
    var a2 = document.createElement("input"); a2.type = "text"; a2.className = "sxf__a2"; a2.value = parts.slice(1).join(", ");
    var sw = labeled("Address line 1", a1, 8);
    sw.dataset.field = prefix + "Street"; sw.dataset.type = "addressStreet";
    block.appendChild(sw); block.appendChild(labeled("Address line 2", a2, 4));

    function plain(suffix, label, span, makeEl) {
      var f = byName[prefix + suffix];
      var input = makeEl();
      input.dataset.field = prefix + suffix; input.dataset.type = "varchar";
      input.value = f && f.value != null ? String(f.value) : "";
      block.appendChild(labeled(label, input, span));
      return input;
    }
    var city = plain("City", "City", 6, function () { var i = document.createElement("input"); i.type = "text"; return i; });
    var state = plain("State", "State", 2, function () {
      var sel = document.createElement("select");
      var cur = String((byName[prefix + "State"] || {}).value || "");
      var opts = US_STATES.slice();
      if (cur && opts.indexOf(cur) < 0) opts.unshift(cur);
      sel.appendChild(new Option("", ""));
      opts.forEach(function (s) { sel.appendChild(new Option(s, s)); });
      return sel;
    });
    state.value = String((byName[prefix + "State"] || {}).value || "");
    var zip = plain("PostalCode", "ZIP", 4, function () { var i = document.createElement("input"); i.type = "text"; return i; });
    // Country belongs with the rest of the address, not off in Additional details.
    var country = byName[prefix + "Country"]
      ? plain("Country", "Country", 6, function () { var i = document.createElement("input"); i.type = "text"; return i; })
      : null;

    if (sameAs) {
      var same = document.createElement("label"); same.className = "sxf__same";
      var cb = document.createElement("input"); cb.type = "checkbox";
      same.appendChild(cb); same.appendChild(document.createTextNode(" Same as billing"));
      // Inline in the column's sub-header (mockup v3), else on its own line.
      (tl || outer).appendChild(same);
      var mine = { City: city, State: state, PostalCode: zip, Country: country };
      function mirror() {
        if (!cb.checked) return;
        var form = outer.closest(".sxf"); if (!form) return;
        var bs = form.querySelector('[data-field="' + sameAs + 'Street"]');
        if (bs) {
          a1.value = bs.querySelector(".sxf__a1").value;
          a2.value = bs.parentNode.querySelector(".sxf__a2").value;
        }
        ["City", "State", "PostalCode", "Country"].forEach(function (s) {
          var src = form.querySelector('[data-field="' + sameAs + s + '"]');
          var dst = mine[s];
          if (!src || !dst) return;
          if (dst.tagName === "SELECT" && src.value &&
              !Array.prototype.some.call(dst.options, function (o) { return o.value === src.value; })) {
            dst.appendChild(new Option(src.value, src.value));
          }
          dst.value = src.value;
        });
      }
      function setDim(on) {
        block.classList.toggle("sxf__dim", on);
        [a1, a2, city, state, zip, country].forEach(function (i) { if (i) i.disabled = on; });
      }
      // Checking copies billing over the shipping inputs (the save then writes
      // billing values); unchecking restores what was there before.
      var stash = null;
      cb.addEventListener("change", function () {
        if (cb.checked) {
          stash = { a1: a1.value, a2: a2.value, city: city.value, state: state.value,
                    zip: zip.value, country: country ? country.value : "" };
          setDim(true); mirror();
        } else {
          setDim(false);
          if (stash) {
            a1.value = stash.a1; a2.value = stash.a2; city.value = stash.city;
            state.value = stash.state; zip.value = stash.zip;
            if (country) country.value = stash.country;
          }
        }
      });
      // Keep mirroring while checked when the billing fields are edited.
      setTimeout(function () {
        var form = outer.closest(".sxf"); if (!form) return;
        form.addEventListener("input", function (e) {
          if (!cb.checked || !e.target.closest) return;
          if (String((e.target.dataset || {}).field || "").indexOf(sameAs) === 0) { mirror(); return; }
          // The street line inputs carry no data-field of their own — match by
          // their address grid containing the billing street cell.
          var grid3 = e.target.closest(".sxf__addr");
          if (grid3 && grid3.querySelector('[data-field="' + sameAs + 'Street"]')) mirror();
        });
        // Pre-check when shipping already equals billing (and isn't empty).
        var same0 = true, any = false;
        var bs = form.querySelector('[data-field="' + sameAs + 'Street"]');
        var bvals = {
          street: bs ? (bs.querySelector(".sxf__a1").value + "\n" + bs.parentNode.querySelector(".sxf__a2").value).replace(/\n$/, "") : "",
          city: (form.querySelector('[data-field="' + sameAs + 'City"]') || {}).value || "",
          state: (form.querySelector('[data-field="' + sameAs + 'State"]') || {}).value || "",
          zip: (form.querySelector('[data-field="' + sameAs + 'PostalCode"]') || {}).value || "",
          country: (form.querySelector('[data-field="' + sameAs + 'Country"]') || {}).value || "",
        };
        var svals = {
          street: (a1.value + "\n" + a2.value).replace(/\n$/, ""),
          city: city.value, state: state.value, zip: zip.value,
          country: country ? country.value : "",
        };
        Object.keys(bvals).forEach(function (k) {
          if (bvals[k] || svals[k]) any = true;
          if (bvals[k] !== svals[k]) same0 = false;
        });
        if (any && same0) { cb.checked = true; setDim(true); }
      }, 0);
    }
    outer.appendChild(block);
    return outer;
  }

  // === Edit mode (per section): the grouped form + Save/Cancel ===
  function panelEditForm(sec, key) {
    var dkey = editDraftKey(sec.entity, sec.id);
    var draft = readEditDraft(dkey);
    // Restore (the banner's button) re-renders the form with the stashed
    // values merged in; those fields then always count as changes (their
    // snapshot is a sentinel), so Save writes exactly what was restored.
    var applying = detailsDraftApply[key];
    delete detailsDraftApply[key];
    var buildSec = sec;
    if (applying) {
      buildSec = Object.assign({}, sec, {
        fields: (sec.fields || []).map(function (f) {
          return applying[f.name] !== undefined
            ? Object.assign({}, f, { value: applying[f.name] }) : f;
        }),
      });
    }
    var body = layoutForm(buildSec, detailsLayoutFor(sec.entity));
    var snap = {};
    Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
      snap[el.dataset.field] = JSON.stringify(readField(el));
    });
    if (applying) {
      Object.keys(applying).forEach(function (fn) {
        if (fn in snap) snap[fn] = "restored-draft";  // never equals a JSON.stringify result => dirty
      });
    }
    detailsSnapshot[key] = snap;
    var notice = document.createElement("p"); notice.className = "sx__dpanel-error"; notice.hidden = true;
    // Save/Cancel render at BOTH the top of the form and the (sticky) bottom
    // (Doug's ruling 2026-07-19: the top pair means no scrolling to save on a
    // long form). Both pairs share state — one dirty scan drives them all.
    var saveBtns = [], statusEls = [];
    function countDirty() {
      var n = 0;
      Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
        if (JSON.stringify(readField(el)) !== snap[el.dataset.field]) n++;
      });
      return n;
    }
    function doSave() { savePanel(sec, key, body, saveBtns, notice); }
    function doCancel(ev) {
      var btn = ev.currentTarget;
      // Discarding typed work needs a second click (two-step, no browser
      // dialogs — the Remove-button convention). A clean form just closes.
      if (countDirty() && btn.dataset.armed !== "1") {
        btn.dataset.armed = "1"; btn.textContent = "Discard changes?";
        return;
      }
      clearEditDraft(dkey);
      delete detailsEditSet[key]; repaintDetails(key);
    }
    function actionsRow(cls) {
      var row = document.createElement("div"); row.className = "sx__dpanel-actions " + cls;
      var status = document.createElement("span"); status.className = "sxf__savestatus"; status.textContent = "No changes yet";
      var cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
      cancel.addEventListener("click", doCancel);
      var save = document.createElement("button"); save.type = "button"; save.className = "cbm-button"; save.textContent = "Save changes";
      save.disabled = true;
      save.addEventListener("click", doSave);
      row.appendChild(status); row.appendChild(cancel); row.appendChild(save);
      saveBtns.push(save); statusEls.push(status);
      return row;
    }
    // Live diff feedback: a gold dot marks each field that differs from its
    // loaded value, and the bars narrate what a Save will write. The
    // scan reuses the snapshot/readField diff the save itself runs; "click"
    // covers rich-text toolbar actions, which fire no native input event.
    // The same scan AUTOSAVES the dirty fields as the localStorage draft.
    var scanTimer = null;
    function scanDirty() {
      // The form may have been saved/cancelled while this debounce was
      // pending — never let a late scan resurrect the cleared draft.
      if (!detailsEditSet[key]) return;
      var n = 0, dirtyVals = {};
      Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
        var v = readField(el);
        var dirty = JSON.stringify(v) !== snap[el.dataset.field];
        (el.closest(".cbm-field") || el).classList.toggle("sxf__dirty", dirty);
        if (dirty) { n++; dirtyVals[el.dataset.field] = v; }
      });
      var label = n ? n + (n === 1 ? " field" : " fields") + " changed" : "No changes yet";
      saveBtns.forEach(function (b) { b.disabled = !n; });
      statusEls.forEach(function (s) { s.textContent = label; });
      if (n) saveEditDraft(dkey, dirtyVals); else clearEditDraft(dkey);
    }
    ["input", "change", "click", "keyup"].forEach(function (ev) {
      body.addEventListener(ev, function () { clearTimeout(scanTimer); scanTimer = setTimeout(scanDirty, 150); });
    });
    var wrap = document.createElement("div");
    wrap.appendChild(actionsRow("sx__dpanel-actions--top"));
    // A stashed draft from an earlier visit is OFFERED, never silently applied.
    if (draft && !applying) {
      var bar = document.createElement("div"); bar.className = "sxf__draftbar";
      var msg = document.createElement("span");
      msg.textContent = "You have unsaved changes on this form from earlier.";
      var restore = document.createElement("button"); restore.type = "button"; restore.className = "sxd__btn"; restore.textContent = "Restore them";
      restore.addEventListener("click", function () {
        detailsDraftApply[key] = draft; repaintDetails(key);
      });
      var discard = document.createElement("button"); discard.type = "button"; discard.className = "sxd__btn"; discard.textContent = "Discard";
      discard.addEventListener("click", function () { clearEditDraft(dkey); bar.remove(); });
      bar.appendChild(msg); bar.appendChild(restore); bar.appendChild(discard);
      wrap.appendChild(bar);
    }
    wrap.appendChild(body); wrap.appendChild(notice);
    wrap.appendChild(actionsRow("sx__dpanel-actions--sticky"));
    return wrap;
  }

  // A Details save can change what the read-only tabs show (Partner Notes on
  // the Overview, a renamed record in the header, contact lists) — re-fetch
  // the record payload and re-render them. Best-effort: the Details tab is
  // already refreshed, so a failed refresh here just leaves the old Overview
  // until the next full load (Doug's 2026-07-18 report: partner notes saved
  // in Details never appeared on the Overview without a page reload).
  async function refreshRecordViews() {
    if (!currentDetail) return;
    try {
      currentDetail = await api("/records/" + encodeURIComponent(currentDetail.id));
      $("detailName").textContent = currentDetail.name || "(unnamed)";
      renderOverview(currentDetail);
      renderSessions(currentDetail);
    } catch (_) { /* keep the stale Overview rather than fail the save UX */ }
  }

  // Save one section; on failure keep the edit view open and show the error inline.
  // ``saveBtn`` may be one button or the list of paired top/bottom buttons.
  async function savePanel(sec, key, body, saveBtn, errEl) {
    var btns = Array.isArray(saveBtn) ? saveBtn : [saveBtn];
    var snap = detailsSnapshot[key] || {}, changes = {};
    Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
      var v = readField(el);
      if (JSON.stringify(v) !== snap[el.dataset.field]) changes[el.dataset.field] = v;
    });
    if (!Object.keys(changes).length) { delete detailsEditSet[key]; repaintDetails(key); return; }
    btns.forEach(function (b) { b.disabled = true; }); errEl.hidden = true;
    try {
      await api("/details/" + encodeURIComponent(sec.entity) + "/" + encodeURIComponent(sec.id),
        { method: "PUT", body: JSON.stringify({ changes: changes }) });
      clearEditDraft(editDraftKey(sec.entity, sec.id));  // saved => the stashed draft is obsolete
      delete detailsEditSet[key];
      await loadDetails(currentDetail.id);  // refresh values, everything back to view
      refreshRecordViews();  // Overview (e.g. Partner Notes) reflects the save too
      notice("detailsNotice", sec.title + " saved.", "success");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      btns.forEach(function (b) { b.disabled = false; });
      errEl.textContent = e.status === 403
        ? "You don't have permission to edit " + sec.title + "."
        : "Couldn't save: " + e.message;
      errEl.hidden = false;
      errEl.scrollIntoView({ behavior: "smooth", block: "nearest" });  // visible from the TOP bar too
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

  // --- shared value helpers ---
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
  function namesOf(v) { return v && typeof v === "object" ? Object.keys(v).map(function (k) { return v[k]; }).join(", ") : ""; }
  function noDetails() { var p = document.createElement("p"); p.className = "sx__muted sxd__none"; p.textContent = "No details on file."; return p; }
  function badgeEl(cls, text) { var s = document.createElement("span"); s.className = cls; s.textContent = text; return s; }
  function bold(s) { return "<b>" + esc(s) + "</b>"; }
  var SEP = '<span class="sxd__sep">|</span>';
  function chipsNode(vals) {
    var wrap = document.createElement("span"); wrap.className = "sxd__chips";
    vals.forEach(function (o) { var c = document.createElement("span"); c.className = "sx__chip"; c.textContent = o; wrap.appendChild(c); });
    return wrap;
  }
  // A labeled card row: fixed small uppercase label, composed value. `value` is
  // a Node or a PRE-ESCAPED html string (composers escape via esc()/bold()).
  function drow(label, value) {
    var row = document.createElement("div"); row.className = "sxd__row";
    var k = document.createElement("span"); k.className = "sxd__row-k"; k.textContent = label;
    var v = document.createElement("span"); v.className = "sxd__row-v";
    if (typeof value === "string") v.innerHTML = value; else v.appendChild(value);
    row.appendChild(k); row.appendChild(v); return row;
  }
  // Edit buttons are NEVER hidden for permission reasons (Doug's ruling
  // 2026-07-19): a missing button reads as a bug ("the button is missing"),
  // so it always renders, and clicking without the CRM edit grant explains
  // exactly that. `editable` = the per-record ACL verdict from the server;
  // `what` names the record in the message ("the Partnership", "this contact").
  function detailsEditBtn(key, editable, what) {
    var b = document.createElement("button"); b.type = "button"; b.className = "sxd__btn"; b.textContent = "Edit";
    b.addEventListener("click", function () {
      if (editable === false) {
        notice("detailsNotice", "You don't have permission to edit " + (what || "this record") +
          " — ask CBM staff if you need it.", "error");
        return;
      }
      detailsEditSet[key] = true; repaintDetails(key);
    });
    return b;
  }
  function cardHeadEl(title, countText) {
    var h = document.createElement("div"); h.className = "sxd__card-h";
    var t = document.createElement("span"); t.className = "sxd__card-t"; t.textContent = title;
    h.appendChild(t);
    if (countText) { var c = document.createElement("span"); c.className = "sxd__count"; c.textContent = countText; h.appendChild(c); }
    return h;
  }

  // === 1. Summary strip: the parent record as one slim labeled bar ===========
  // Short strip labels for the known parent fields (fallback: the spec label).
  var STRIP_LABELS = {
    engagementStatus: "Status", engagementStartDate: "Started", meetingCadence: "Cadence",
    totalSessions: "Sessions", totalSessionHours: "Hours", totalSessionsLast30Days: "Last 30 days",
    lastSessionDate: "Last session", nextSessionDateTime: "Next session",
    engagementAssignedDate: "Assigned", closeDate: "Closed", closeReason: "Close reason",
    holdEndDate: "Hold ends", mentoringFocusAreas: "Focus areas",
    revenueIncreasePercentage: "Revenue growth %", employmentIncreasePercentage: "Employment growth %",
    significantRevenueIncrease: "Sig. revenue growth", significantEmploymentIncrease: "Sig. employment growth",
    newBusinessStarted: "New business", newLocationOpened: "New location",
    partnershipStatus: "Status", partnershipType: "Type", partnershipStartDate: "Started",
    partnershipAgreementDate: "Agreement", partnerContactCadence: "Cadence",
    lastContacted: "Last contacted", lastContribution: "Last contribution",
  };
  // Lead cells in mockup order; "@mentor" is the display-only mentor link.
  var STRIP_ORDER = [
    "engagementStatus", "engagementStartDate", "@mentor", "meetingCadence", "totalSessions",
    "partnershipStatus", "partnershipType", "partnershipStartDate",
  ];

  // A section the user's CRM role can't read renders as a titled card with a
  // plain explanation instead of failing the whole tab (server marks it
  // restricted — sessions/details.py).
  function restrictedCard(sec, key) {
    var card = document.createElement("div"); card.className = "sxd__card"; card.dataset.dkey = key;
    card.appendChild(cardHeadEl(sec.title, null));
    var p = document.createElement("p"); p.className = "sx__muted sxd__none";
    p.textContent = "Your CRM role can't view this (no read access to " +
      sec.entity + " records) — ask CBM staff if you need it.";
    card.appendChild(p);
    return card;
  }

  function parentStrip(sec, key) {
    if (sec.restricted) return restrictedCard(sec, key);
    if (detailsEditSet[key]) {  // editing: the strip becomes a full-form card
      var card = document.createElement("div"); card.className = "sxd__card"; card.dataset.dkey = key;
      card.appendChild(cardHeadEl(sec.title, null));
      card.appendChild(panelEditForm(sec, key));
      return card;
    }
    var strip = document.createElement("div"); strip.className = "sxd__strip"; strip.dataset.dkey = key;
    stripCells(sec).forEach(function (c) { strip.appendChild(c); });
    var b = detailsEditBtn(key, sec.editable, "the " + (sec.title || "record"));
    b.className += " sxd__strip-edit";
    strip.appendChild(b);
    return strip;
  }

  // Every parent field that carries information becomes a cell (long-form text/
  // wysiwyg stays on the Overview and in the edit form; empties and "No" omitted).
  function stripCells(sec) {
    var cells = [], done = {};
    function add(label, value) {
      var cell = document.createElement("span"); cell.className = "sxd__cell";
      var k = document.createElement("span"); k.className = "sxd__cell-k"; k.textContent = label;
      var v = document.createElement("span"); v.className = "sxd__cell-v";
      if (typeof value === "string") v.textContent = value; else v.appendChild(value);
      cell.appendChild(k); cell.appendChild(v); cells.push(cell);
    }
    function addField(f) {
      if (done[f.name] || f.name === "name") return; done[f.name] = 1;  // page header shows the name
      if (f.type === "text" || f.type === "wysiwyg") return;
      var v = f.value;
      if (v == null || v === "" || v === false || (Array.isArray(v) && !v.length)) return;
      var label = STRIP_LABELS[f.name] || f.label;
      if (f.type === "enum" && /status$/i.test(f.name)) {
        add(label, badgeEl("sxd__pill", String(v))); return;
      }
      add(label, f.type === "bool" ? "Yes"
        : f.type === "date" ? fmtLongDate(v)
        : f.type === "datetime" ? fmtSessionDate(v, "short")
        : Array.isArray(v) ? v.join(", ") : String(v));
    }
    var byName = {};
    (sec.fields || []).forEach(function (f) { byName[f.name] = f; });
    STRIP_ORDER.forEach(function (name) {
      if (name === "@mentor") {
        var m = dvs(sec, "mentorProfileName") || namesOf(dv(sec, "assignedUsersNames"));
        if (m) add("Mentor", m);
        return;
      }
      if (byName[name]) addField(byName[name]);
    });
    (sec.fields || []).forEach(addField);
    return cells;
  }

  // === 2/3. Org cards (Company / profile): two-column labeled row grid =======
  function orgCard(sec, key) {
    if (sec.restricted) return restrictedCard(sec, key);
    var card = document.createElement("div"); card.className = "sxd__card"; card.dataset.dkey = key;
    var editing = !!detailsEditSet[key];
    var head = cardHeadEl(sec.title, null);
    if (!editing) head.appendChild(detailsEditBtn(key, sec.editable, "the " + (sec.title || "record")));
    card.appendChild(head);
    card.appendChild(editing ? panelEditForm(sec, key) : orgCardBody(sec));
    return card;
  }

  function orgCardBody(sec) {
    var used = {};  // field names the composed rows consumed
    var cols = sec.entity === "Account" ? companyRows(sec, used)
      : sec.entity === "CClientProfile" ? clientProfileRows(sec, used)
      : { left: [], right: [] };
    appendLeftoverRows(sec, used, cols);
    if (!cols.left.length && !cols.right.length) return noDetails();
    var body = document.createElement("div"); body.className = "sxd__card-b";
    var grid = document.createElement("div"); grid.className = "sxd__rows2";
    [cols.left, cols.right].forEach(function (rows) {
      var col = document.createElement("div");
      rows.forEach(function (r, i) { if (i === 0) r.className += " nb"; col.appendChild(r); });
      grid.appendChild(col);
    });
    body.appendChild(grid);
    return body;
  }

  function companyRows(sec, used) {
    ["billingAddressStreet", "billingAddressCity", "billingAddressState", "billingAddressPostalCode",
     "billingAddressCountry", "phoneNumber", "website", "emailAddress",
     "cOrganizationType", "cBusinessStage", "industry", "cIndustrySector", "cIndustrySubsector",
     "shippingAddressStreet", "shippingAddressCity", "shippingAddressState",
     "shippingAddressPostalCode", "shippingAddressCountry",
     "cPartnerContactCadence", "cPublicAnnouncementAllowed",
    ].forEach(function (n) { used[n] = 1; });
    // The view must not display fields the edit form doesn't manage — the
    // domain's excluded Account fields (partnership/account group on the mentor
    // domain, the other domains' relationship fields elsewhere) never render.
    Object.keys(detailsExcludes(sec.entity)).forEach(function (n) { used[n] = 1; });
    var left = [], right = [];
    // Directory block: name, billing address, phone · website, email.
    var dir = document.createElement("div"); dir.className = "sxd__dir";
    var nm = document.createElement("div"); nm.className = "sxd__dir-name"; nm.textContent = sec.name || "Company"; dir.appendChild(nm);
    if (dvs(sec, "billingAddressStreet")) dir.appendChild(txtLine(dvs(sec, "billingAddressStreet")));
    var bcl = cityLine(dvs(sec, "billingAddressCity"), dvs(sec, "billingAddressState"), dvs(sec, "billingAddressPostalCode"));
    if (bcl) dir.appendChild(txtLine(bcl));
    var line3 = document.createElement("div");
    if (dvs(sec, "phoneNumber")) line3.appendChild(document.createTextNode(fmtPhone(dvs(sec, "phoneNumber"))));
    var web = dvs(sec, "website");
    if (web) {
      if (line3.childNodes.length) line3.appendChild(document.createTextNode(" · "));
      var a = document.createElement("a"); a.href = externalHref(web);
      a.target = "_blank"; a.rel = "noopener"; a.textContent = web.replace(/^https?:\/\//i, "");
      line3.appendChild(a);
    }
    if (line3.childNodes.length) dir.appendChild(line3);
    var email = dvs(sec, "emailAddress");
    if (email) { var ed = document.createElement("div"); ed.appendChild(emailComposeLink(email)); dir.appendChild(ed); }
    var dirRow = document.createElement("div"); dirRow.className = "sxd__row sxd__row--dir"; dirRow.appendChild(dir);
    left.push(dirRow);
    // Business: org type | stage | industry (general + sector / subsector).
    var biz = [];
    if (dvs(sec, "cOrganizationType")) biz.push(bold(dvs(sec, "cOrganizationType")));
    if (dvs(sec, "cBusinessStage")) biz.push(bold(dvs(sec, "cBusinessStage")));
    var ind = [dvs(sec, "industry"), dvs(sec, "cIndustrySector"), dvs(sec, "cIndustrySubsector")]
      .filter(Boolean).join(" / ");
    if (ind) biz.push(esc(ind));
    var bizRow = biz.length ? drow("Business", biz.join(SEP)) : null;
    // Shipping — only when it differs from billing.
    var bill = [dvs(sec, "billingAddressStreet"), bcl].filter(Boolean).join(", ");
    var ship = [dvs(sec, "shippingAddressStreet"),
                cityLine(dvs(sec, "shippingAddressCity"), dvs(sec, "shippingAddressState"), dvs(sec, "shippingAddressPostalCode"))].filter(Boolean).join(", ");
    var shipRow = (ship && ship !== bill) ? drow("Shipping", esc(ship)) : null;
    if (SLUG === "mentorsessions") {
      // Mentor domain (edit mockup v2): no Account / Cadence / Announcements
      // rows — the right column carries the Business and Shipping rows.
      if (bizRow) right.push(bizRow);
      if (shipRow) right.push(shipRow);
      return { left: left, right: right };
    }
    if (bizRow) left.push(bizRow);
    if (shipRow) left.push(shipRow);
    // Right (partner/sponsor domains): cadence, announcements (meaningful negative).
    if (dvs(sec, "cPartnerContactCadence")) right.push(drow("Cadence", bold(dvs(sec, "cPartnerContactCadence")) + " partner contact"));
    if (dv(sec, "cPublicAnnouncementAllowed") === false) right.push(drow("Announcements", badgeEl("sxd__badge-warn", "Not allowed")));
    return { left: left, right: right };
  }

  function clientProfileRows(sec, used) {
    ["legalEntityType", "formationDate", "isHomeBased", "annualRevenueRange", "revenueTrend",
     "profitabilityStatus", "primaryCustomerType", "salesChannels", "geographicMarketReach",
     "federalEinOnFile", "hasGoogleBusinessProfile", "ohioVendorsLicenseOnFile", "registeredOnSamGov",
     "certificationsHeld", "fundingSourcesUsedToDate", "description",
    ].forEach(function (n) { used[n] = 1; });
    // The view must not display fields the edit form doesn't manage.
    Object.keys(detailsExcludes(sec.entity)).forEach(function (n) { used[n] = 1; });
    var left = [], right = [];
    var ent = [];
    if (dvs(sec, "legalEntityType")) ent.push(bold(dvs(sec, "legalEntityType")));
    if (dv(sec, "formationDate")) ent.push("formed " + esc(fmtMonthYear(dv(sec, "formationDate"))));
    if (dv(sec, "isHomeBased") === true) ent.push("home-based");
    if (ent.length) left.push(drow("Entity", ent.join(", ")));
    var rev = [];
    if (dvs(sec, "annualRevenueRange")) rev.push(bold(dvs(sec, "annualRevenueRange")));
    if (dvs(sec, "revenueTrend")) rev.push(esc(dvs(sec, "revenueTrend").toLowerCase()));
    if (dvs(sec, "profitabilityStatus")) rev.push(bold(dvs(sec, "profitabilityStatus").toLowerCase()));
    if (rev.length) left.push(drow("Revenue", rev.join(SEP)));
    var sells = [];
    var ct = dvArr(sec, "primaryCustomerType"); if (ct.length) sells.push(bold(ct.join(", ")));
    var sc = dvArr(sec, "salesChannels"); if (sc.length) sells.push(esc(sc.join(", ")));
    if (dvs(sec, "geographicMarketReach")) sells.push(esc(dvs(sec, "geographicMarketReach")) + " reach");
    if (sells.length) left.push(drow("Sells", sells.join(SEP)));
    var onfile = [];
    if (dv(sec, "federalEinOnFile") === true) onfile.push("Federal EIN");
    if (dv(sec, "hasGoogleBusinessProfile") === true) onfile.push("Google Business Profile");
    if (dv(sec, "ohioVendorsLicenseOnFile") === true) onfile.push("Ohio vendor's license");
    if (dv(sec, "registeredOnSamGov") === true) onfile.push("SAM.gov registration");
    if (onfile.length) left.push(drow("On file", esc(onfile.join(" · "))));
    var certs = dvArr(sec, "certificationsHeld"); if (certs.length) right.push(drow("Certifications", chipsNode(certs)));
    var funds = dvArr(sec, "fundingSourcesUsedToDate"); if (funds.length) right.push(drow("Funding to date", chipsNode(funds)));
    var goal = dvs(sec, "description");
    if (goal) { var q = document.createElement("i"); q.textContent = "“" + goal + "”"; right.push(drow("Client goal", q)); }
    return { left: left, right: right };
  }

  // Any informative field the curated rows didn't consume still shows as a
  // labeled row (balanced across the two columns) — nothing with a value hides.
  function appendLeftoverRows(sec, used, cols) {
    (sec.fields || []).forEach(function (f) {
      if (used[f.name] || f.name === "name") return;  // the card title already shows the name
      if (f.type === "text" || f.type === "wysiwyg") return;  // long-form: edit/Overview only
      var v = f.value;
      if (v == null || v === "" || v === false || (Array.isArray(v) && !v.length)) return;
      var node = (f.type === "multiEnum" && Array.isArray(v)) ? chipsNode(v)
        : bold(f.type === "bool" ? "Yes"
          : f.type === "date" ? fmtLongDate(v)
          : f.type === "datetime" ? fmtSessionDate(v, "short") : String(v));
      (cols.left.length <= cols.right.length ? cols.left : cols.right).push(drow(f.label, node));
    });
  }

  // === 4/5. Contact tables (Client Contacts / CBM Contacts) ==================
  var CONTACT_AGREEMENTS = ["cPrivacyPolicyAccepted", "cTermsOfUseAccepted", "cCodeOfConductAccepted"];

  function clientContactsCard() {
    var contacts = currentDetails.contacts || [];
    var card = document.createElement("div"); card.className = "sxd__card"; card.dataset.dkey = "clientContacts";
    var head = cardHeadEl("Client Contacts", "(" + contacts.length + ")");
    if (currentDetails.contactsRestricted) {
      card.appendChild(head);
      var p = document.createElement("p"); p.className = "sx__muted sxd__none";
      p.textContent = "Your CRM role can't view this record's contacts " +
        "(no read access to Contact records) — ask CBM staff if you need it.";
      card.appendChild(p);
      return card;
    }
    head.appendChild(addMenuEl("client"));
    card.appendChild(head);
    if (detailsAdd === "client-existing") card.appendChild(addExistingPanel());
    if (detailsAdd === "client-new") card.appendChild(addNewPanel());
    card.appendChild(contactsTable(contacts, true));
    return card;
  }

  function cbmContactsCard() {
    var rows = currentDetails.cbmContacts || [];
    var card = document.createElement("div"); card.className = "sxd__card"; card.dataset.dkey = "cbmContacts";
    var head = cardHeadEl("CBM Contacts", "(" + rows.length + ")");
    head.appendChild(addMenuEl("cbm"));
    card.appendChild(head);
    if (detailsAdd === "cbm-pick") card.appendChild(cbmPickPanel());
    card.appendChild(contactsTable(rows, false));
    return card;
  }

  // One table for all of a card's contacts. Client rows are contact sections;
  // CBM rows wrap {role, name, contact: section|null}. A row's Edit expands a
  // full-width row holding that contact's field form. Empty cells stay empty.
  function contactsTable(items, isClient) {
    var wrap = document.createElement("div"); wrap.className = "sxd__scroll";
    if (!items.length) {
      var p = document.createElement("p"); p.className = "sx__muted sxd__none"; p.textContent = "No contacts on file.";
      wrap.appendChild(p); return wrap;
    }
    var table = document.createElement("table"); table.className = "sxd__contacts";
    var thead = document.createElement("thead"); var htr = document.createElement("tr");
    var cols = isClient
      ? ["Name", "Role", "Phone", "Email", "City", "Contact via", "Agreements", ""]
      : ["Name", "Role", "Phone", "Email", "Contact via", ""];
    cols.forEach(function (c) { var th = document.createElement("th"); th.textContent = c; htr.appendChild(th); });
    thead.appendChild(htr); table.appendChild(thead);
    var tb = document.createElement("tbody");
    items.forEach(function (item, i) {
      var sec = isClient ? item : item.contact;
      var vals = (sec && sec.values) || {};
      var editKey = (isClient ? "c" : "b") + i;
      var tr = document.createElement("tr");
      tr.appendChild(nameCell(item, sec, isClient));
      tr.appendChild(roleCell(item, vals, isClient));
      tr.appendChild(tdText(fmtPhone(vals.phoneNumber)));
      tr.appendChild(emailCell(vals.emailAddress));
      if (isClient) tr.appendChild(tdText(vals.addressCity || ""));
      tr.appendChild(tdText(vals.cPreferredContactMethod || ""));
      if (isClient) tr.appendChild(agreementsCell(vals));
      var act = document.createElement("td"); act.className = "sxd__actions";
      if (sec && !detailsEditSet[editKey]) {
        var e = document.createElement("button"); e.type = "button"; e.className = "sxd__rowedit"; e.textContent = "Edit";
        var rowEditable = sec.editable, rowName = (sec.name || "this contact");
        e.addEventListener("click", function () {
          if (rowEditable === false) {  // never hidden — explain on click
            notice("detailsNotice", "You don't have permission to edit " + rowName +
              " — ask CBM staff if you need it.", "error");
            return;
          }
          detailsEditSet[editKey] = true; repaintDetails(editKey);
        });
        act.appendChild(e);
      }
      // Remove = an unrelate on the PARENT record. The assigned Mentor row is
      // never removable here (that link is managed in Client Administration —
      // a design exclusion, not a permission hide); a user without edit on the
      // parent still SEES Remove and gets the permission message on click.
      var removable = !detailsEditSet[editKey] &&
        (isClient ? !!(sec && sec.id) : item.role !== "Mentor" && !!item.profileId);
      if (removable) act.appendChild(removeContactBtn(item, sec, isClient));
      tr.appendChild(act);
      tb.appendChild(tr);
      if (detailsEditSet[editKey] && sec) {
        var er = document.createElement("tr"); er.className = "sxd__editrow";
        var td = document.createElement("td"); td.colSpan = cols.length;
        td.appendChild(panelEditForm(sec, editKey));
        er.appendChild(td); tb.appendChild(er);
      }
    });
    table.appendChild(tb); wrap.appendChild(table);
    return wrap;
  }

  function nameCell(item, sec, isClient) {
    var td = document.createElement("td"); td.className = "sxd__cname";
    var vals = (sec && sec.values) || {};
    if (isClient && vals.salutationName) {
      var s = document.createElement("span"); s.className = "sxd__sal"; s.textContent = vals.salutationName + " ";
      td.appendChild(s);
    }
    var name = isClient
      ? ([vals.firstName, vals.lastName].filter(Boolean).join(" ") || sec.name || "(unnamed)")
      : (item.name || (sec && sec.name) || "(unnamed)");
    td.appendChild(document.createTextNode(name));
    return td;
  }
  function roleCell(item, vals, isClient) {
    var td = document.createElement("td"); td.className = "sxd__roles";
    if (isClient) {
      (Array.isArray(vals.cContactType) ? vals.cContactType : []).forEach(function (r) {
        td.appendChild(badgeEl("sxd__badge-role", r));
      });
      if (vals.title) { var t = document.createElement("span"); t.className = "sx__muted"; t.textContent = vals.title; td.appendChild(t); }
    } else if (item.role) {
      td.appendChild(badgeEl("sxd__badge-role", item.role));
    }
    return td;
  }
  function tdText(t) { var td = document.createElement("td"); td.textContent = t; return td; }
  function emailCell(email) {
    var td = document.createElement("td");
    if (email) td.appendChild(emailComposeLink(email));
    return td;
  }
  // One status badge for privacy policy + terms + code of conduct — never three
  // separate lines. Unset counts as pending.
  function agreementsCell(vals) {
    var td = document.createElement("td");
    var pending = CONTACT_AGREEMENTS.filter(function (n) { return vals[n] !== true; }).length;
    td.appendChild(pending === 0 ? badgeEl("sxd__badge-ok", "Complete") : badgeEl("sxd__badge-warn", pending + " pending"));
    return td;
  }

  // Whether the signed-in user can edit the parent record itself (its details
  // section carries the per-record ACL verdict) — gates row removal, which is a
  // relation write on the parent.
  function parentEditable() {
    var secs = (currentDetails && currentDetails.sections) || [];
    for (var i = 0; i < secs.length; i++) {
      if (secs[i].kind === "parent") return !!secs[i].editable;
    }
    return false;
  }

  // Two-step "Remove" (no browser confirm dialogs — same pattern as the
  // Communications "Not related" button). Unlinks the relation only: the
  // contact / mentor profile record itself stays in the CRM.
  function removeContactBtn(item, sec, isClient) {
    var btn = document.createElement("button"); btn.type = "button";
    btn.className = "sxd__rowedit sxd__rowremove"; btn.textContent = "Remove";
    var armed = false;
    btn.addEventListener("click", async function () {
      // The unrelate is a write on the PARENT record — without edit on it,
      // explain on click rather than hiding the button (Doug's ruling).
      if (!parentEditable()) {
        notice("detailsNotice", "You don't have permission to change this record's contacts — " +
          "ask CBM staff if you need it.", "error");
        return;
      }
      if (!armed) { armed = true; btn.textContent = "Really remove?"; return; }
      btn.disabled = true;
      var path = isClient
        ? "/records/" + encodeURIComponent(currentDetail.id) + "/contacts/" + encodeURIComponent(sec.id)
        : "/records/" + encodeURIComponent(currentDetail.id) + "/comentors/" + encodeURIComponent(item.profileId);
      try {
        await api(path, { method: "DELETE" });
        await loadDetails(currentDetail.id);
        refreshRecordViews();
        notice("detailsNotice", isClient ? "Contact removed from this record." : "CBM contact removed.", "success");
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        btn.disabled = false; armed = false; btn.textContent = "Remove";
        notice("detailsNotice", e.message, "error");
      }
    });
    return btn;
  }

  // === + Add flows ============================================================
  function addMenuEl(side) {  // side: "client" | "cbm"
    var wrap = document.createElement("span"); wrap.className = "sxd__addwrap";
    var btn = document.createElement("button"); btn.type = "button"; btn.className = "sxd__btn"; btn.textContent = "+ Add";
    var menuKey = side + "-menu", cardKey = side === "client" ? "clientContacts" : "cbmContacts";
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      detailsAdd = detailsAdd === menuKey ? null : menuKey;
      repaintDetails(cardKey);
    });
    wrap.appendChild(btn);
    if (detailsAdd === menuKey) {
      var menu = document.createElement("div"); menu.className = "sxd__menu";
      if (side === "client") {
        menu.appendChild(menuItem("Select existing contact…", function () { detailsAdd = "client-existing"; repaintDetails(cardKey); }));
        menu.appendChild(menuItem("Create new contact…", function () { detailsAdd = "client-new"; repaintDetails(cardKey); }));
      } else {
        // CBM contacts are mentor profiles; new ones are onboarded via Mentor
        // Administration, so only select-existing is offered here.
        menu.appendChild(menuItem("Select existing CBM contact…", function () { detailsAdd = "cbm-pick"; repaintDetails(cardKey); }));
      }
      wrap.appendChild(menu);
    }
    return wrap;
  }
  function menuItem(label, fn) {
    var b = document.createElement("button"); b.type = "button"; b.textContent = label;
    b.addEventListener("click", function (e) { e.stopPropagation(); fn(); });
    return b;
  }
  // Any outside click closes an open + Add menu (matches the mockup behavior).
  document.addEventListener("click", function () {
    if (!currentDetails) return;
    if (detailsAdd === "client-menu" || detailsAdd === "cbm-menu") {
      var key = detailsAdd === "client-menu" ? "clientContacts" : "cbmContacts";
      detailsAdd = null; repaintDetails(key);
    }
  });

  function addPanelShell(title) {
    var panel = document.createElement("div"); panel.className = "sxd__addpanel";
    var h = document.createElement("div"); h.className = "sxd__addpanel-h"; h.textContent = title;
    panel.appendChild(h);
    return panel;
  }
  function addCancelBtn(cardKey) {
    var cancel = document.createElement("button"); cancel.type = "button";
    cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
    cancel.addEventListener("click", function () { detailsAdd = null; repaintDetails(cardKey); });
    return cancel;
  }

  // Select existing contact: search the CRM (as the user), click a result to link
  // it to this record (engagementContacts / contacts / sponsorContacts relation).
  function addExistingPanel() {
    var panel = addPanelShell("Link an existing contact");
    var input = document.createElement("input"); input.type = "search";
    input.className = "sx__search sxd__addsearch"; input.placeholder = "Search contacts by name (2+ characters)…";
    panel.appendChild(input);
    var results = document.createElement("div"); results.className = "sxd__results"; panel.appendChild(results);
    var err = document.createElement("p"); err.className = "sx__dpanel-error"; err.hidden = true; panel.appendChild(err);
    var timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { results.innerHTML = ""; return; }
      timer = setTimeout(async function () {
        try {
          var res = await api("/contacts?q=" + encodeURIComponent(q));
          results.innerHTML = "";
          var list = res.contacts || [];
          if (!list.length) { results.innerHTML = "<p class='sx__muted'>No matching contacts.</p>"; return; }
          list.forEach(function (c) {
            var b = document.createElement("button"); b.type = "button"; b.className = "sxd__result";
            b.textContent = (c.name || "(unnamed)") + (c.email ? " — " + c.email : "") + (c.company ? " (" + c.company + ")" : "");
            b.addEventListener("click", function () { linkExistingContact(c.id, b, err); });
            results.appendChild(b);
          });
        } catch (e) {
          if (e.status === 401) { showLogin(); return; }
          err.textContent = e.message; err.hidden = false;
        }
      }, 250);
    });
    var actions = document.createElement("div"); actions.className = "sx__dpanel-actions";
    actions.appendChild(addCancelBtn("clientContacts"));
    panel.appendChild(actions);
    setTimeout(function () { input.focus(); }, 0);
    return panel;
  }

  async function linkExistingContact(id, btn, errEl) {
    btn.disabled = true; errEl.hidden = true;
    try {
      await api("/records/" + encodeURIComponent(currentDetail.id) + "/contacts",
        { method: "POST", body: JSON.stringify({ contactId: id }) });
      detailsAdd = null;
      await loadDetails(currentDetail.id);
      refreshRecordViews();
      notice("detailsNotice", "Contact linked.", "success");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      btn.disabled = false;
      errEl.textContent = e.message; errEl.hidden = false;
    }
  }

  // Create new contact: the full contact form (from the live field spec), saved
  // and linked in one operation.
  function addNewPanel() {
    var panel = addPanelShell("New contact");
    // The same grouped Contact form (Form 4) as row edits, empty.
    var emptySec = {
      entity: "Contact", values: {},
      fields: (currentDetails.contactSpec || []).filter(function (f) { return f.editable; })
        .map(function (f) { return Object.assign({}, f, { value: f.type === "multiEnum" ? [] : null }); }),
    };
    var body = layoutForm(emptySec, detailsLayoutFor("Contact"));
    panel.appendChild(body);
    var err = document.createElement("p"); err.className = "sx__dpanel-error"; err.hidden = true; panel.appendChild(err);
    var actions = document.createElement("div"); actions.className = "sx__dpanel-actions";
    var save = document.createElement("button"); save.type = "button"; save.className = "cbm-button"; save.textContent = "Create contact";
    save.addEventListener("click", async function () {
      var changes = {};
      Array.prototype.forEach.call(body.querySelectorAll("[data-field]"), function (el) {
        var v = readField(el);
        if (v == null || v === "" || v === false || (Array.isArray(v) && !v.length)) return;
        changes[el.dataset.field] = v;
      });
      if (!changes.firstName && !changes.lastName) {
        err.textContent = "A first or last name is required."; err.hidden = false; return;
      }
      save.disabled = true; err.hidden = true;
      try {
        await api("/records/" + encodeURIComponent(currentDetail.id) + "/contacts",
          { method: "POST", body: JSON.stringify({ changes: changes }) });
        detailsAdd = null;
        await loadDetails(currentDetail.id);
        refreshRecordViews();
        notice("detailsNotice", "Contact created and linked.", "success");
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        save.disabled = false;
        err.textContent = e.message; err.hidden = false;
      }
    });
    actions.appendChild(addCancelBtn("clientContacts")); actions.appendChild(save);
    panel.appendChild(actions);
    return panel;
  }

  // Add a CBM contact: pick an existing mentor profile (attached via the
  // engagement's additionalMentors relation).
  function cbmPickPanel() {
    var panel = addPanelShell("Add a CBM contact");
    var row = document.createElement("div"); row.className = "sx__inline";
    var sel = document.createElement("select"); sel.className = "sxd__addselect";
    sel.setAttribute("aria-label", "Choose a CBM contact");
    sel.appendChild(new Option("Loading…", ""));
    api("/mentors").then(function (res) {
      sel.innerHTML = "";
      sel.appendChild(new Option("Choose a CBM contact…", ""));
      (res.mentors || []).forEach(function (m) { sel.appendChild(new Option(m.name || m.id, m.id)); });
    }).catch(function (e) {
      if (e.status === 401) { showLogin(); return; }
      sel.innerHTML = ""; sel.appendChild(new Option("Couldn't load CBM contacts", ""));
    });
    var err = document.createElement("p"); err.className = "sx__dpanel-error"; err.hidden = true;
    var add = document.createElement("button"); add.type = "button"; add.className = "cbm-button"; add.textContent = "Add";
    add.addEventListener("click", async function () {
      if (!sel.value) return;
      add.disabled = true; err.hidden = true;
      try {
        var res = await api("/records/" + encodeURIComponent(currentDetail.id) + "/comentors",
          { method: "POST", body: JSON.stringify({ mentorProfileId: sel.value }) });
        detailsAdd = null;
        await loadDetails(currentDetail.id);
        refreshRecordViews();
        notice("detailsNotice", (res && res.warning) || "CBM contact added.",
          res && res.warning ? "error" : "success");
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        add.disabled = false;
        err.textContent = e.message; err.hidden = false;
      }
    });
    row.appendChild(sel); row.appendChild(add); row.appendChild(addCancelBtn("cbmContacts"));
    panel.appendChild(row); panel.appendChild(err);
    return panel;
  }

  // Sessions-grid column sorting (same interaction as the Client Administration
  // grids): first click sorts (text A→Z, dates newest-first), second reverses.
  // Server default order (most recent first) until a header is clicked.
  var sessionsSort = { key: null, dir: 1 };

  function sessionSortVal(s, k) {
    if (k === "duration") return sessionDurationSeconds(s) || 0;
    if (k === "participants") return (s.participants || []).join(", ").toLowerCase();
    if (k === "dateStart") return s.dateStart || "";  // UTC stamps compare as strings
    return (s[k] || "").toString().toLowerCase();
  }

  function updateSessionsSortIndicators() {
    Array.prototype.forEach.call(document.querySelectorAll("#sessionsTable th[data-sort]"), function (th) {
      var active = th.getAttribute("data-sort") === sessionsSort.key;
      th.setAttribute("aria-sort", active ? (sessionsSort.dir === 1 ? "ascending" : "descending") : "none");
      th.dataset.dir = active ? (sessionsSort.dir === 1 ? "asc" : "desc") : "";
    });
  }

  function renderSessions(d) {
    var list = (d.sessions || []).slice();
    var tb = $("sessionsBody"); tb.innerHTML = "";
    $("noSessions").hidden = list.length > 0;
    $("sessionsTable").hidden = list.length === 0;
    updateSessionsSortIndicators();
    if (sessionsSort.key) {
      var k = sessionsSort.key, dir = sessionsSort.dir;
      list.sort(function (a, b) {
        var va = sessionSortVal(a, k), vb = sessionSortVal(b, k);
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
    }
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
      tr.appendChild(td(fmtDuration(sessionDurationSeconds(s)) || "—"));
      tr.appendChild(td((s.participants || []).join(", ") || "—"));
      var actions = document.createElement("td");
      var edit = document.createElement("button"); edit.type = "button"; edit.className = "cbm-button cbm-button--secondary sx__sm";
      edit.textContent = "Edit"; edit.addEventListener("click", function () { openEditor(s.id); });
      actions.appendChild(edit); tr.appendChild(actions);
      tb.appendChild(tr);
    });
  }
  function td(text) { var c = document.createElement("td"); c.textContent = text; return c; }

  Array.prototype.forEach.call(
    document.querySelectorAll("#sessionsTable th[data-sort]"),
    function (th) {
      th.classList.add("sx__th-sort");
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (sessionsSort.key === key) {
          sessionsSort.dir = -sessionsSort.dir;
        } else {
          sessionsSort.key = key;
          sessionsSort.dir = key === "dateStart" ? -1 : 1;
        }
        if (currentDetail) renderSessions(currentDetail);
      });
    }
  );

  // Draggable column resizing: a slim grip on each sortable header's right
  // edge. The first drag freezes the current widths (table-layout: fixed) so
  // resizing one column doesn't reflow the rest; widths live on the th
  // elements, so they survive re-renders (only the tbody is rebuilt).
  function makeColumnsResizable(table) {
    var ths = table.querySelectorAll("thead th[data-sort]");
    var all = table.querySelectorAll("thead th");
    Array.prototype.forEach.call(ths, function (th) {
      var grip = document.createElement("span");
      grip.className = "sx__col-grip";
      grip.setAttribute("aria-hidden", "true");
      grip.addEventListener("click", function (e) { e.stopPropagation(); });  // never sort
      grip.addEventListener("mousedown", function (e) {
        e.preventDefault(); e.stopPropagation();
        if (!table.classList.contains("sx__table--resized")) {
          Array.prototype.forEach.call(all, function (t) {
            t.style.width = t.getBoundingClientRect().width + "px";
          });
          table.classList.add("sx__table--resized");
        }
        var startX = e.clientX, startW = th.getBoundingClientRect().width;
        function move(ev) { th.style.width = Math.max(60, startW + ev.clientX - startX) + "px"; }
        function up() {
          document.removeEventListener("mousemove", move);
          document.removeEventListener("mouseup", up);
          document.body.classList.remove("sx__col-resizing");
        }
        document.addEventListener("mousemove", move);
        document.addEventListener("mouseup", up);
        document.body.classList.add("sx__col-resizing");
      });
      th.appendChild(grip);
    });
  }
  makeColumnsResizable($("sessionsTable"));

  // --- Contributions tab (the funder ledger — sponsor domain only) ----------
  // prds/funder-contributions-plan.md. Panel + endpoints exist only when the
  // domain config declared the tab (the server registers nothing elsewhere).
  // Totals count Received only; Cancelled/Unsuccessful rows render dimmed and
  // are excluded server-side; soft delete = the editor's status → Cancelled.
  var ctb = {
    forId: null, rows: [], summary: null, parentName: "",
    spec: null, options: {}, required: [],
    sort: { key: null, dir: 1 }, periodMode: "half",
    editing: null,        // the row being edited (null = create)
    fieldEls: {},         // field name -> input element
    snapshot: {},         // field name -> value at render (diffed on save)
    nameAuto: "",         // last auto-generated title (user edits win)
    discardArmed: false,
    saving: false,
  };

  function ctbMoney(v, cur) {
    if (v == null || v === "") return "—";
    var n = Number(v);
    if (isNaN(n)) return String(v);
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency", currency: cur || (ctb.summary && ctb.summary.currency) || "USD",
        minimumFractionDigits: 0, maximumFractionDigits: n % 1 ? 2 : 0,
      }).format(n);
    } catch (e) { return "$" + n; }
  }

  function ctbDate(v) {
    if (!v) return "—";
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v));
    if (!m) return String(v);
    // Built from parts — new Date("YYYY-MM-DD") parses as UTC and can shift a day.
    var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  async function renderContributions() {
    if (!currentDetail) return;
    if (ctb.forId === currentDetail.id && ctb.summary) { paintContributions(); return; }
    ctb.forId = currentDetail.id;
    ctb.rows = []; ctb.summary = null;
    hide($("ctbNotice")); hide($("ctbTiles")); hide($("ctbRecency"));
    hide($("ctbTable")); hide($("noCtb")); hide($("ctbPeriods"));
    show($("ctbLoading"));
    try {
      if (!ctb.spec) {
        var f = await api("/contributionfields");
        ctb.spec = f.fields || []; ctb.options = f.options || {}; ctb.required = f.required || [];
      }
      var res = await api("/records/" + encodeURIComponent(currentDetail.id) + "/contributions");
      ctb.rows = res.records || [];
      ctb.summary = res.summary || null;
      ctb.parentName = res.parentName || (currentDetail.record && currentDetail.record.name) || "";
      paintContributions();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("ctbNotice", e.message, "error");
    } finally { hide($("ctbLoading")); }
  }

  function paintContributions() {
    paintCtbTiles();
    paintCtbRecency();
    paintCtbPeriods();
    paintCtbTable();
  }

  function ctbTile(value, label, sub) {
    var t = document.createElement("div"); t.className = "ctb__tile";
    var v = document.createElement("div"); v.className = "ctb__tile-value"; v.textContent = value;
    var l = document.createElement("div"); l.className = "ctb__tile-label"; l.textContent = label;
    t.appendChild(v); t.appendChild(l);
    if (sub) { var s = document.createElement("div"); s.className = "ctb__tile-sub"; s.textContent = sub; t.appendChild(s); }
    return t;
  }

  function paintCtbTiles() {
    var s = ctb.summary; var box = $("ctbTiles"); box.innerHTML = "";
    if (!s) { hide(box); return; }
    box.appendChild(ctbTile(String(s.totalCount), "Contributions", "received"));
    box.appendChild(ctbTile(ctbMoney(s.totalAmount), "Total received"));
    box.appendChild(ctbTile(ctbMoney(s.last12MonthsAmount), "Last 12 months", "rolling"));
    box.appendChild(ctbTile(
      ctbMoney(s.scheduledAmount), "Scheduled (upcoming)",
      s.scheduledCount ? s.scheduledCount + " pledged/committed" : "nothing scheduled"
    ));
    show(box);
  }

  function paintCtbRecency() {
    var s = ctb.summary; var el = $("ctbRecency");
    if (!s) { hide(el); return; }
    el.classList.remove("is-stale");
    if (!s.lastReceived) {
      el.textContent = "No contributions received yet.";
    } else {
      var lr = s.lastReceived;
      var ago = lr.monthsAgo === 0 ? "this month"
        : lr.monthsAgo + (lr.monthsAgo === 1 ? " month ago" : " months ago");
      var text = "Last received: " + ctbMoney(lr.amount) + " on " + ctbDate(lr.date) + " — " + ago + ".";
      if (s.nextExpected) {
        text += " Next expected: " + ctbMoney(s.nextExpected.amount) + " on " + ctbDate(s.nextExpected.date) + ".";
      }
      el.textContent = text;
      if (lr.monthsAgo > 6) el.classList.add("is-stale");  // the continuity nudge
    }
    show(el);
  }

  function paintCtbPeriods() {
    var s = ctb.summary;
    if (!s || $("ctbPeriods").hidden) return;
    $("ctbHalfBtn").classList.toggle("is-active", ctb.periodMode === "half");
    $("ctbYearBtn").classList.toggle("is-active", ctb.periodMode === "year");
    var rows = (s.periods && s.periods[ctb.periodMode]) || [];
    var tb = $("ctbPeriodBody"); tb.innerHTML = "";
    rows.forEach(function (w) {
      var tr = document.createElement("tr");
      tr.appendChild(td(ctbDate(w.start) + " – " + ctbDate(w.end)));
      tr.appendChild(td(w.count ? String(w.count) : "—"));
      tr.appendChild(td(w.count ? ctbMoney(w.total) : "—"));
      if (!w.count) tr.className = "ctb__period-empty";
      tb.appendChild(tr);
    });
  }

  function ctbSortVal(r, k) {
    if (k === "amount") return Number(r.amount) || 0;
    if (k === "acknowledgmentSent") return r.acknowledgmentSent ? 1 : 0;
    return (r[k] || "").toString().toLowerCase();
  }

  function updateCtbSortIndicators() {
    Array.prototype.forEach.call(document.querySelectorAll("#ctbTable th[data-sort]"), function (th) {
      var active = th.getAttribute("data-sort") === ctb.sort.key;
      th.setAttribute("aria-sort", active ? (ctb.sort.dir === 1 ? "ascending" : "descending") : "none");
      th.dataset.dir = active ? (ctb.sort.dir === 1 ? "asc" : "desc") : "";
    });
  }

  function paintCtbTable() {
    var list = ctb.rows.slice();
    var tb = $("ctbBody"); tb.innerHTML = "";
    $("noCtb").hidden = list.length > 0;
    $("ctbTable").hidden = list.length === 0;
    updateCtbSortIndicators();
    if (ctb.sort.key) {
      var k = ctb.sort.key, dir = ctb.sort.dir;
      list.sort(function (a, b) {
        var va = ctbSortVal(a, k), vb = ctbSortVal(b, k);
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
    }
    list.forEach(function (r) {
      var tr = document.createElement("tr");
      if (r.excluded) tr.className = "ctb__row--excluded";
      else if (r.upcoming) tr.className = "ctb__row--upcoming";
      var nameCell = document.createElement("td");
      var link = document.createElement("button"); link.type = "button"; link.className = "sx__link";
      link.textContent = r.name || "(untitled)";
      link.addEventListener("click", function () { openContribEditor(r); });
      nameCell.appendChild(link); tr.appendChild(nameCell);
      tr.appendChild(td(r.contributionType || "—"));
      var st = document.createElement("td"); st.textContent = r.status || "—";
      if (r.excluded) {
        var tag = document.createElement("span"); tag.className = "ctb__tag";
        tag.textContent = "not counted"; st.appendChild(tag);
      } else if (r.upcoming) {
        var utag = document.createElement("span"); utag.className = "ctb__tag ctb__tag--up";
        utag.textContent = "upcoming"; st.appendChild(utag);
      }
      tr.appendChild(st);
      tr.appendChild(td(ctbMoney(r.amount, r.amountCurrency)));
      tr.appendChild(td(ctbDate(r.expectedPaymentDate)));
      tr.appendChild(td(ctbDate(r.receivedDate)));
      tr.appendChild(td(r.giftType || "—"));
      tr.appendChild(td(r.acknowledgmentSent ? "✓" : "—"));
      var actions = document.createElement("td");
      var edit = document.createElement("button"); edit.type = "button";
      edit.className = "cbm-button cbm-button--secondary sx__sm"; edit.textContent = "Edit";
      edit.addEventListener("click", function () { openContribEditor(r); });
      actions.appendChild(edit); tr.appendChild(actions);
      tb.appendChild(tr);
    });
  }

  Array.prototype.forEach.call(
    document.querySelectorAll("#ctbTable th[data-sort]"),
    function (th) {
      th.classList.add("sx__th-sort");
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (ctb.sort.key === key) ctb.sort.dir = -ctb.sort.dir;
        else { ctb.sort.key = key; ctb.sort.dir = /Date$/.test(key) || key === "amount" ? -1 : 1; }
        paintCtbTable();
      });
    }
  );
  makeColumnsResizable($("ctbTable"));

  $("ctbPeriodBtn").addEventListener("click", function () {
    var p = $("ctbPeriods");
    p.hidden = !p.hidden;
    if (!p.hidden) paintCtbPeriods();
  });
  $("ctbHalfBtn").addEventListener("click", function () { ctb.periodMode = "half"; paintCtbPeriods(); });
  $("ctbYearBtn").addEventListener("click", function () { ctb.periodMode = "year"; paintCtbPeriods(); });
  $("ctbAddBtn").addEventListener("click", function () { openContribEditor(null); });

  // --- contribution editor (modal) ---
  function ctbDefaultName(type) {
    var today = new Date();
    var iso = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0")
      + "-" + String(today.getDate()).padStart(2, "0");
    return iso + " — " + (ctb.parentName || "Contribution") + (type ? " " + type : "");
  }

  function ctbFieldValue(name) {
    var el = ctb.fieldEls[name];
    if (!el) return "";
    if (el._cbmRichText) return el._cbmRichText.getValue();
    if (el.type === "checkbox") return el.checked;
    return el.value;
  }

  async function openContribEditor(row) {
    hide($("ctbFormNotice"));
    ctb.editing = row || null;
    ctb.discardArmed = false;
    $("ctbModalTitle").textContent = row ? (row.name || "Contribution") : "New contribution";
    var full = row;
    if (row) {
      // The list rows omit notes/description — fetch the full record for edit.
      try { full = await api("/contributions/" + encodeURIComponent(row.id)); }
      catch (e) { notice("ctbNotice", e.message, "error"); return; }
      ctb.editing = full;
    }
    buildContribForm(full);
    show($("ctbModal"));
  }

  function closeContribModal() {
    hide($("ctbModal"));
    ctb.editing = null; ctb.fieldEls = {}; ctb.snapshot = {};
  }

  function ctbDirty() {
    for (var name in ctb.snapshot) {
      // The auto title on a pristine NEW form is a default, not a user edit.
      if (!ctb.editing && name === "name" && ctbFieldValue("name") === ctb.nameAuto) continue;
      if (String(ctbFieldValue(name)) !== String(ctb.snapshot[name])) return true;
    }
    return false;
  }

  function requestCloseContrib() {
    if (ctbDirty() && !ctb.discardArmed) {
      ctb.discardArmed = true;
      $("ctbCancelBtn").textContent = "Discard changes?";
      notice("ctbFormNotice", "You have unsaved changes — Cancel again to discard them, or Save.", "error");
      return;
    }
    $("ctbCancelBtn").textContent = "Cancel";
    closeContribModal();
  }

  function buildContribForm(rec) {
    var form = $("ctbForm"); form.innerHTML = "";
    ctb.fieldEls = {}; ctb.snapshot = {};
    $("ctbCancelBtn").textContent = "Cancel";
    var groups = [];   // preserve spec order
    var byGroup = {};
    (ctb.spec || []).forEach(function (f) {
      if (!byGroup[f.group]) { byGroup[f.group] = []; groups.push(f.group); }
      byGroup[f.group].push(f);
    });
    groups.forEach(function (g) {
      var panel = document.createElement("fieldset"); panel.className = "ctb__group";
      var legend = document.createElement("legend"); legend.textContent = g; panel.appendChild(legend);
      var rows = [], byRow = {};
      byGroup[g].forEach(function (f) {
        var key = f.row || f.name;
        if (!byRow[key]) { byRow[key] = []; rows.push(key); }
        byRow[key].push(f);
      });
      rows.forEach(function (rk) {
        var line = document.createElement("div"); line.className = "ctb__line";
        var inkindLine = byRow[rk].every(function (f) { return f.inKindOnly; });
        if (inkindLine) line.dataset.inkind = "1";
        byRow[rk].forEach(function (f) { line.appendChild(ctbField(f, rec)); });
        panel.appendChild(line);
      });
      form.appendChild(panel);
    });
    // In-kind pair only shows for In-Kind gifts (display only — values kept).
    var gift = ctb.fieldEls.giftType;
    function syncInKind() {
      var on = gift && gift.value === "In-Kind";
      Array.prototype.forEach.call(form.querySelectorAll("[data-inkind]"), function (el) {
        el.hidden = !on;
      });
    }
    if (gift) gift.addEventListener("change", syncInKind);
    syncInKind();
    // New contributions get an auto title the user can overwrite; picking a
    // type refreshes it only while the title is still the auto value.
    if (!rec) {
      var nameEl = ctb.fieldEls.name, typeEl = ctb.fieldEls.contributionType;
      if (nameEl) { ctb.nameAuto = ctbDefaultName(""); nameEl.value = ctb.nameAuto; }
      if (typeEl && nameEl) {
        typeEl.addEventListener("change", function () {
          if (nameEl.value === ctb.nameAuto) {
            ctb.nameAuto = ctbDefaultName(typeEl.value);
            nameEl.value = ctb.nameAuto;
          }
        });
      }
    }
    // Snapshot AFTER defaults so an untouched form is clean — but the default
    // title on a create must reach the save payload, so snapshot it as empty.
    (ctb.spec || []).forEach(function (f) {
      ctb.snapshot[f.name] = rec ? String(ctbFieldValue(f.name)) : (f.name === "name" ? "" : String(ctbFieldValue(f.name)));
    });
  }

  function ctbField(f, rec) {
    var value = rec ? rec[f.name] : null;
    var wrap = document.createElement("div");
    wrap.className = "ctb__field" + (f.big ? " ctb__field--big" : "");
    var label = document.createElement("label"); label.className = "ctb__label";
    label.textContent = f.label + (ctb.required.indexOf(f.name) >= 0 ? " *" : "");
    wrap.appendChild(label);
    var el;
    if (f.type === "enum") {
      el = document.createElement("select");
      var blank = document.createElement("option"); blank.value = ""; blank.textContent = "—";
      el.appendChild(blank);
      var opts = (ctb.options[f.name] || []).slice();
      // A stored value drifted out of the live options still renders selected
      // (and re-saves unchanged) instead of silently vanishing from the form.
      if (value && opts.indexOf(value) < 0) opts.push(value);
      opts.forEach(function (o) {
        var op = document.createElement("option"); op.value = o; op.textContent = o;
        el.appendChild(op);
      });
      el.value = value || "";
    } else if (f.type === "bool") {
      el = document.createElement("input"); el.type = "checkbox"; el.checked = !!value;
    } else if (f.type === "date") {
      el = document.createElement("input"); el.type = "date";
      el.value = value ? String(value).slice(0, 10) : "";
    } else if (f.type === "currency") {
      el = document.createElement("input"); el.type = "number";
      el.step = "0.01"; el.min = "0"; el.inputMode = "decimal";
      el.value = value == null ? "" : value;
    } else if (f.type === "text") {
      el = document.createElement("textarea"); el.rows = 3; el.value = value || "";
    } else if (f.type === "wysiwyg") {
      el = window.CBMRichText && window.CBMRichText.create(value || "", { minHeight: 180 });
      if (!el) { el = document.createElement("textarea"); el.rows = 6; el.value = value || ""; }
    }
    if (!el) { el = document.createElement("input"); el.type = "text"; el.value = value || ""; }
    el.className = (el.className ? el.className + " " : "") + "ctb__input";
    ctb.fieldEls[f.name] = el;
    wrap.appendChild(el);
    return el.type === "checkbox" ? ctbCheckWrap(wrap, label, el) : wrap;
  }

  function ctbCheckWrap(wrap, label, el) {
    // Checkbox reads better with the box before the text on one line.
    wrap.innerHTML = ""; wrap.classList.add("ctb__field--check");
    var line = document.createElement("label"); line.className = "ctb__checkline";
    line.appendChild(el); line.appendChild(document.createTextNode(" " + label.textContent));
    wrap.appendChild(line);
    return wrap;
  }

  async function saveContribution() {
    if (ctb.saving) return;
    hide($("ctbFormNotice"));
    var changes = {};
    (ctb.spec || []).forEach(function (f) {
      var raw = ctbFieldValue(f.name);
      if (String(raw) === String(ctb.snapshot[f.name])) return;  // unchanged
      changes[f.name] = f.type === "currency" ? (raw === "" ? null : Number(raw)) : raw;
    });
    // Required check (from live CRM metadata): the FORM value must be present.
    var missing = [];
    (ctb.spec || []).forEach(function (f) {
      if (ctb.required.indexOf(f.name) >= 0) {
        var v = ctbFieldValue(f.name);
        if (v === "" || v == null) missing.push(f.label);
      }
    });
    if (missing.length) {
      notice("ctbFormNotice", "Please complete: " + missing.join(", ") + ".", "error");
      return;
    }
    if (ctb.editing && !Object.keys(changes).length) { closeContribModal(); return; }
    ctb.saving = true; $("ctbSaveBtn").disabled = true;
    try {
      if (ctb.editing) {
        await api("/contributions/" + encodeURIComponent(ctb.editing.id),
          { method: "PUT", body: JSON.stringify({ changes: changes }) });
      } else {
        await api("/records/" + encodeURIComponent(currentDetail.id) + "/contributions",
          { method: "POST", body: JSON.stringify({ changes: changes }) });
      }
      closeContribModal();
      ctb.forId = null;              // force a refetch (summary must recompute)
      await renderContributions();
      notice("ctbNotice", "Contribution saved.", "success");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("ctbFormNotice", e.message, "error");
    } finally { ctb.saving = false; $("ctbSaveBtn").disabled = false; }
  }

  $("ctbSaveBtn").addEventListener("click", saveContribution);
  $("ctbCancelBtn").addEventListener("click", requestCloseContrib);
  $("ctbClose").addEventListener("click", requestCloseContrib);
  $("ctbBackdrop").addEventListener("click", requestCloseContrib);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !$("ctbModal").hidden) requestCloseContrib();
  });

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

  // Session detail View (Display Standard §12, extended 2026-07-12 per Doug's
  // session-details rulings): summary header card (tinted band per §4 — now
  // carrying the TIME RANGE, so no Duration row; a video link renders as the
  // band's Join button, not a grid row) → key-value grid (each fact exactly
  // once) → ATTENDEE GRID (name/role/company/email/phone/status, contact &
  // company peeks, copy tools) → Session notes → Action items callout →
  // Transcript zone (§12.5 feature-gated: rendered only when the CRM field
  // exists; scrolls in its own allotment with find-in-transcript).
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
    var band = document.createElement("div");
    band.className = "sx__vband " + (isTodaySession(s) ? "is-today" : future ? "is-future" : "is-past");
    // Band line 1, three zones: date range (left) · STATUS (center, large —
    // it's the key value, Doug's 2026-07-12 ruling) · the join action (right).
    // The type chip only appears when it differs from the domain default —
    // "Client Session" on every mentor session says nothing.
    var l1 = document.createElement("div"); l1.className = "sx__vband-1";
    var left = document.createElement("span"); left.className = "sx__vband-side";
    var date = document.createElement("span"); date.className = "sx__vband-date";
    date.textContent = fmtSessionRange(s);
    date.title = (s.dateStart || "") + (s.dateEnd ? " → " + s.dateEnd : "");  // ISO in tooltip
    left.appendChild(date);
    if (s.sessionType && s.sessionType !== (config && config.defaultSessionType)) {
      left.appendChild(vChip("type", s.sessionType));
    }
    l1.appendChild(left);
    if (s.status) {
      var statusChip = vChip("status", s.status, scls);
      statusChip.className += " sx__vband-status";
      l1.appendChild(statusChip);
    }
    var right = document.createElement("span"); right.className = "sx__vband-side sx__vband-right";
    if (s.videoMeetingLink) {
      var join = document.createElement("a");
      join.className = "cbm-button sx__vjoin";
      join.href = externalHref(s.videoMeetingLink);
      join.target = "_blank"; join.rel = "noopener";
      join.textContent = future ? "Start Session" : "Open Meeting Link";
      right.appendChild(join);
    }
    l1.appendChild(right);
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
    addKV(grid, "Meeting link", (s.videoMeetingLink || "").trim(), "copylink");
    // The permanent Google Doc transcript (feature-gated: the value only rides
    // the payload once the CRM has transcriptDocUrl and the worker filled it).
    addKV(grid, "Transcript document", (s.transcriptDocUrl || "").trim(), "copylink");
    addKV(grid, "Next session", s.nextSessionDateTime, "datetime");
    hcard.appendChild(grid);
    body.appendChild(hcard);

    // === Attendee grid (Doug's 2026-07-12 ruling; §12.4 keeps the No Show
    // vocabulary — who was EXPECTED). One grid, all invitees.
    body.appendChild(renderViewAttendees(s, scls));

    // === §12.3.1 Session notes (full-width reading block; no clamp) ===
    // The /sessions/{id} payload carries the raw CRM name ``sessionNotes``
    // (only the Overview feed maps it to ``notes``) — reading ``s.notes`` here
    // meant the view never showed notes. ``notes`` stays as a fallback.
    var notesVal = s.sessionNotes != null ? s.sessionNotes : s.notes;
    var notesZone = vZone("SESSION NOTES");
    if (notesVal && String(notesVal).trim() !== "") {
      var nb = document.createElement("div"); nb.className = "sx__vzone-body"; nb.innerHTML = sanitizeHtml(String(notesVal));
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

    // === §12.3.3 Transcript (§12.5 feature-gated — nothing renders until the
    // CRM field exists; the zone then explains an empty transcript instead of
    // silently omitting the capability).
    var tz = renderViewTranscript(s, scls);
    if (tz) body.appendChild(tz);
  }

  // The band's one time statement (each fact exactly once — no Duration row):
  // "Wednesday, July 9 — 2:00 PM–3:00 PM" when the end is known.
  function fmtSessionRange(s) {
    var base = fmtSessionDate(s.dateStart);
    if (base === "—") return base;
    var secs = sessionDurationSeconds(s);
    var start = parseNaive(s.dateStart);
    if (!secs || !start) return base;
    var end = new Date(start.getTime() + secs * 1000);
    return base + "–" + end.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }

  // Per-person invited/attended state is not modeled (a planned CRM ruling);
  // the whole grid derives one honest status from the session itself.
  function attendeeStatusLabel(scls) {
    if (scls === "completed") return "Attended";
    if (scls === "noshow") return "Expected";
    return "Invited";
  }

  // Role from the open record's own lists: a related contact is a Client
  // contact; a co-mentor's contact is CBM; anything else is just a Contact.
  function attendeeRole(id) {
    var d = currentDetail || {};
    var list = d.contacts || [];
    for (var i = 0; i < list.length; i++) { if (list[i].id === id) return "Client"; }
    var cm = d.coMentors || [];
    for (var j = 0; j < cm.length; j++) { if (cm[j].contactId === id) return "CBM"; }
    return "Contact";
  }

  function renderViewAttendees(s, scls) {
    var zone = vZone(scls === "noshow" ? "EXPECTED ATTENDEES" : "ATTENDEES");
    var rows = s.attendeeDetails || [];
    if (!rows.length && (s.attendeeNames || []).length) {
      // Older payload shape (names only) — the grid still renders honestly.
      rows = s.attendeeNames.map(function (n) { return { name: n }; });
    }
    if (!rows.length) {
      var em = document.createElement("p"); em.className = "sx__vzone-empty";
      em.textContent = "No attendees are on this session yet — add them in Edit.";
      zone.appendChild(em); return zone;
    }
    var label = zone.querySelector(".sx__vzone-l");
    var tools = document.createElement("span"); tools.className = "sx__att-tools";
    tools.appendChild(copyTool("⧉ Copy grid", function () { return attendeeTsv(rows, scls); }));
    tools.appendChild(copyTool("⧉ Copy emails", function () {
      return rows.map(function (r) { return r.email; }).filter(Boolean).join(", ");
    }));
    label.appendChild(tools);

    var table = document.createElement("table"); table.className = "sx__table sx__attgrid";
    var thead = document.createElement("thead");
    var hr = document.createElement("tr");
    ["Name", "Role", "Company", "Email", "Phone", "Status"].forEach(function (h) {
      var th = document.createElement("th"); th.scope = "col"; th.textContent = h; hr.appendChild(th);
    });
    thead.appendChild(hr); table.appendChild(thead);
    var tbody = document.createElement("tbody");
    var status = attendeeStatusLabel(scls);
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      var nameCell = document.createElement("td");
      if (r.id) {
        var nb = document.createElement("button"); nb.type = "button"; nb.className = "sx__link";
        nb.textContent = r.name || "(unnamed)";
        nb.addEventListener("click", function () { openPeek("Contact", r.id, r.name || ""); });
        nameCell.appendChild(nb);
      } else { nameCell.textContent = r.name || "(unnamed)"; }
      tr.appendChild(nameCell);
      tr.appendChild(td(r.id ? attendeeRole(r.id) : "—"));
      var compCell = document.createElement("td");
      if (r.companyId) {
        var cb = document.createElement("button"); cb.type = "button"; cb.className = "sx__link";
        cb.textContent = r.companyName || "Company";
        cb.addEventListener("click", function () { openPeek("Account", r.companyId, r.companyName || ""); });
        compCell.appendChild(cb);
      } else { compCell.textContent = r.companyName || "—"; }
      tr.appendChild(compCell);
      tr.appendChild(emailCopyCell(r.email));
      tr.appendChild(copyableCell(r.phone, "phone"));
      var st = document.createElement("td");
      var chip = document.createElement("span"); chip.className = "sx__chip"; chip.textContent = status;
      st.appendChild(chip); tr.appendChild(st);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    // The grid's columns don't wrap (emails/phones must stay whole lines), so
    // on a narrow window the TABLE scrolls inside the card — never the page.
    var wrap = document.createElement("div"); wrap.className = "sx__attwrap";
    wrap.appendChild(table);
    zone.appendChild(wrap);
    return zone;
  }

  // A clickable link followed by a copy-to-clipboard button — so a meeting URL
  // can be opened OR copied (e.g. to paste into an email or agenda).
  function linkWithCopy(url) {
    var span = document.createElement("span"); span.className = "sx__linkcopy";
    var a = document.createElement("a");
    a.href = externalHref(url); a.target = "_blank"; a.rel = "noopener";
    a.textContent = url.replace(/^https?:\/\//, ""); a.title = url;
    span.appendChild(a);
    var b = document.createElement("button"); b.type = "button"; b.className = "sx__copycell";
    b.title = "Copy meeting link"; b.setAttribute("aria-label", "Copy meeting link"); b.textContent = "⧉";
    b.addEventListener("click", function () { copyToClipboard(url, b); });
    span.appendChild(b);
    return span;
  }

  // Attendee-grid email: compose-on-click address + the copy button.
  function emailCopyCell(email) {
    var cell = document.createElement("td");
    if (!email) { cell.textContent = "—"; return cell; }
    cell.appendChild(emailComposeLink(email));
    cell.appendChild(document.createTextNode(" "));
    var b = document.createElement("button"); b.type = "button"; b.className = "sx__copycell";
    b.title = "Copy email"; b.setAttribute("aria-label", "Copy email"); b.textContent = "⧉";
    b.addEventListener("click", function () { copyToClipboard(email, b); });
    cell.appendChild(b);
    return cell;
  }

  function copyableCell(value, what) {
    var cell = document.createElement("td");
    if (!value) { cell.textContent = "—"; return cell; }
    cell.appendChild(document.createTextNode(value + " "));
    var b = document.createElement("button"); b.type = "button"; b.className = "sx__copycell";
    b.title = "Copy " + what; b.setAttribute("aria-label", "Copy " + what); b.textContent = "⧉";
    b.addEventListener("click", function () { copyToClipboard(value, b); });
    cell.appendChild(b);
    return cell;
  }

  function copyTool(labelText, getText) {
    var b = document.createElement("button"); b.type = "button"; b.className = "sx__copybtn";
    b.textContent = labelText;
    b.addEventListener("click", function () { copyToClipboard(getText(), b); });
    return b;
  }

  function copyToClipboard(text, btn) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(function () {
      var old = btn.textContent;
      btn.textContent = "✓ Copied"; btn.disabled = true;
      setTimeout(function () { btn.textContent = old; btn.disabled = false; }, 1500);
    }).catch(function () {
      notice("viewNotice", "Copy failed — the browser blocked clipboard access.", "error");
    });
  }

  // Tab-separated with headers so a paste lands in Excel/Sheets as columns.
  function attendeeTsv(rows, scls) {
    var status = attendeeStatusLabel(scls);
    var lines = ["Name\tRole\tCompany\tEmail\tPhone\tStatus"];
    rows.forEach(function (r) {
      lines.push([
        r.name || "", r.id ? attendeeRole(r.id) : "", r.companyName || "",
        r.email || "", r.phone || "", status,
      ].join("\t"));
    });
    return lines.join("\n");
  }

  function renderViewTranscript(s, scls) {
    if (!s.transcriptFieldExists) return null;  // §12.5: no stub until the CRM field lands
    var text = s.sessionTranscription;
    if (!text || !String(text).trim()) {
      if (scls === "cancelled" || scls === "noshow") return null;  // §12.4: omit, never empty boxes
      var zone0 = vZone("TRANSCRIPT");
      var em = document.createElement("p"); em.className = "sx__vzone-empty";
      em.textContent = "No transcript is attached. Automatic transcription isn't connected yet — paste the meeting transcript into the Transcript box in Edit.";
      zone0.appendChild(em); return zone0;
    }
    var zone = vZone("TRANSCRIPT");
    // The transcript is the session's longest text: it scrolls within its own
    // allotment, so the browser's Ctrl+F can't see the clipped part — the zone
    // carries its own find with an honest match count.
    var label = zone.querySelector(".sx__vzone-l");
    var find = document.createElement("input");
    find.type = "search"; find.className = "sx__tfind";
    find.placeholder = "Find in transcript…"; find.setAttribute("aria-label", "Find in transcript");
    var count = document.createElement("span"); count.className = "sx__tcount";
    label.appendChild(find); label.appendChild(count);
    var bodyEl = document.createElement("div"); bodyEl.className = "sx__vzone-body sx__transcript";
    bodyEl.innerHTML = sanitizeHtml(String(text));
    var base = bodyEl.innerHTML;
    find.addEventListener("input", function () {
      bodyEl.innerHTML = base;
      var needle = find.value.trim();
      if (!needle) { count.textContent = ""; return; }
      var n = markMatches(bodyEl, needle);
      count.textContent = n + (n === 1 ? " match" : " matches");
      var first = bodyEl.querySelector("mark");
      if (first && first.scrollIntoView) first.scrollIntoView({ block: "nearest" });
    });
    zone.appendChild(bodyEl);
    return zone;
  }

  // Wrap every case-insensitive match in <mark>, walking TEXT nodes only —
  // never a regex over serialized HTML (attribute text must not match).
  function markMatches(root, needle) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var nodes = []; var nd;
    while ((nd = walker.nextNode())) nodes.push(nd);
    var lower = needle.toLowerCase(); var total = 0;
    nodes.forEach(function (node) {
      var text = node.nodeValue; var hay = text.toLowerCase();
      var idx = hay.indexOf(lower);
      if (idx < 0) return;
      var frag = document.createDocumentFragment(); var pos = 0;
      while (idx >= 0) {
        frag.appendChild(document.createTextNode(text.slice(pos, idx)));
        var m = document.createElement("mark"); m.textContent = text.slice(idx, idx + needle.length);
        frag.appendChild(m); total++;
        pos = idx + needle.length; idx = hay.indexOf(lower, pos);
      }
      frag.appendChild(document.createTextNode(text.slice(pos)));
      node.parentNode.replaceChild(frag, node);
    });
    return total;
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
      var a = document.createElement("a"); a.href = externalHref(value); a.target = "_blank"; a.rel = "noopener"; a.textContent = value; v.appendChild(a);
    } else if (type === "copylink") {
      v.appendChild(linkWithCopy(String(value)));
    } else { v.textContent = String(value); }
    cell.appendChild(l); cell.appendChild(v); grid.appendChild(cell);
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
  // A fresh idempotency key for one new-session editor (every save attempt of
  // that editor carries it, so the server can tell a retry from a new session).
  function newCreateToken() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "t-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
  }

  async function openEditor(sessionId) {
    editorCreateToken = sessionId ? null : newCreateToken();
    if (sessionId) {
      try { currentSession = await api("/sessions/" + encodeURIComponent(sessionId)); }
      catch (e) { if (e.status === 401) { showLogin(); return; } notice("detailNotice", e.message, "error"); return; }
      // Duration is virtual (dateEnd − dateStart) — derive the select's value.
      currentSession.duration = sessionDurationSeconds(currentSession);
      $("editorTitle").textContent = "Edit session";
    } else {
      currentSession = {
        // EVERY contact on the record — the client/engagement contacts AND the
        // CBM contacts — starts INVITED on a new session (Doug's 2026-07-13
        // ruling; widens the CBM-only default of 2026-07-12). Pre-checked here
        // so it lands in the dirty-tracking baseline and unchecking is an
        // explicit choice, never a silent default.
        id: null, attendees: defaultAttendees(),
        status: "Scheduled",
        sessionType: (config && config.defaultSessionType) || "",
        name: defaultSessionName(),
        duration: 3600,  // the CRM duration field's default (1 hour)
      };
      $("editorTitle").textContent = "New session";
    }
    hide($("editorNotice"));
    renderForm(currentSession);
    snapshotForm();
    renderAttendees();
    // A stashed draft from an earlier visit (crash, tab close, session
    // expiry) is OFFERED back, never silently applied.
    var oldBar = document.getElementById("sessionDraftBar");
    if (oldBar) oldBar.remove();
    var dkey = sessionDraftKey();
    var draft = dkey ? readEditDraft(dkey) : null;
    if (draft) offerSessionDraft(dkey, draft);
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

  // --- session-editor draft autosave (extends the v0.99.0 edit-loss
  // protection to the most-typed surface in the app). Dirty fields + a
  // changed attendee set stash to localStorage as the user types; reopening
  // the same session (or the record's New-session form) offers them back. ---
  function sessionDraftKey() {
    if (!currentDetail) return null;
    return currentSession && currentSession.id
      ? editDraftKey("CSession", currentSession.id)
      : editDraftKey("CSession", currentDetail.id, "new");
  }
  var sessionStashTimer = null;
  function stashSessionDraft() {
    if ($("editorView").hidden) return;  // saved/left — never resurrect a cleared draft
    var dk = sessionDraftKey();
    if (!dk) return;
    var fields = {}, n = 0;
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-field]"), function (el) {
      var v = readField(el);
      if (JSON.stringify(v) !== editorSnapshot[el.dataset.field]) { fields[el.dataset.field] = v; n++; }
    });
    var orig = ((currentSession && currentSession.attendees) || []).slice().sort().join(",");
    var now = chosenAttendees();
    var attendeesDirty = orig !== now.slice().sort().join(",");
    if (!n && !attendeesDirty) { clearEditDraft(dk); return; }
    var d = { fields: fields };
    if (attendeesDirty) d.attendees = now;
    saveEditDraft(dk, d);
  }

  // Re-render the editor with the stashed values merged in. Drafted fields'
  // snapshots become a sentinel (never equals a JSON.stringify result), so
  // they read as changes and an UPDATE save sends exactly what was restored.
  // Drafted attendees re-check the boxes only — the baseline
  // (currentSession.attendees) stays original, so the diff sees them too.
  function applySessionDraft(draft) {
    renderForm(Object.assign({}, currentSession, draft.fields || {}));
    snapshotForm();
    Object.keys(draft.fields || {}).forEach(function (fn) {
      if (fn in editorSnapshot) editorSnapshot[fn] = "restored-draft";
    });
    renderAttendees();
    if (draft.attendees) {
      Array.prototype.forEach.call($("attendees").querySelectorAll(".sx__attendee"), function (cb) {
        cb.checked = draft.attendees.indexOf(cb.value) >= 0;
      });
    }
  }

  function offerSessionDraft(dkey, draft) {
    var bar = document.createElement("div"); bar.className = "sxf__draftbar"; bar.id = "sessionDraftBar";
    var msg = document.createElement("span");
    msg.textContent = "You have unsaved changes to this session from earlier.";
    var restore = document.createElement("button");
    restore.type = "button"; restore.className = "sxd__btn"; restore.textContent = "Restore them";
    restore.addEventListener("click", function () { applySessionDraft(draft); bar.remove(); });
    var discard = document.createElement("button");
    discard.type = "button"; discard.className = "sxd__btn"; discard.textContent = "Discard";
    discard.addEventListener("click", function () { clearEditDraft(dkey); bar.remove(); });
    bar.appendChild(msg); bar.appendChild(restore); bar.appendChild(discard);
    var tabs = $("editorTabs");
    tabs.parentNode.insertBefore(bar, tabs);
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

  // datetime helpers: the CRM stores "YYYY-MM-DD HH:MM:SS" in UTC; the
  // datetime-local input speaks the viewer's local wall clock. Convert both
  // ways so the stored instant — not the raw digits — is what round-trips.
  function toLocalInput(v) {
    var d = parseNaive(v);
    if (!d) return "";
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) +
           "T" + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }
  function fromLocalInput(v) {
    var m = v ? v.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/) : null;
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
    return d.getUTCFullYear() + "-" + pad2(d.getUTCMonth() + 1) + "-" + pad2(d.getUTCDate()) +
           " " + pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes()) + ":00";
  }

  // --- Time picker standard (mockup v2): every time field is a Date input plus
  // a Start-time popover — a half-hour slot grid ("Morning" 8:00–11:30 AM,
  // "Afternoon & evening" 12:00–7:30 PM, 4 columns, one click to select) with a
  // free-entry "Other time" escape hatch. No 60-minute minute-pickers anywhere.
  function fmtTimeText(h, m) {
    var mer = h < 12 ? "AM" : "PM";
    var hh = h % 12; if (hh === 0) hh = 12;
    return hh + ":" + pad2(m) + " " + mer;
  }
  // Accepts "2:45 PM", "2 pm", "14:45", "9:30am"; null when unparseable.
  function parseTimeText(s) {
    var m = String(s || "").trim().match(/^(\d{1,2})(?::(\d{2}))?\s*([AaPp])?\.?\s*[Mm]?\.?$/);
    if (!m) return null;
    var h = +m[1], mm = m[2] ? +m[2] : 0;
    if (mm > 59) return null;
    if (m[3]) {
      if (h < 1 || h > 12) return null;
      h = (h % 12) + (/p/i.test(m[3]) ? 12 : 0);
    } else if (h > 23) return null;
    return { h: h, m: mm };
  }
  function timeSlots(fromH, toH) {
    var out = [];
    for (var h = fromH; h < toH; h++) { out.push(fmtTimeText(h, 0)); out.push(fmtTimeText(h, 30)); }
    return out;
  }
  function makeDateTimeInput(value) {
    var wrap = document.createElement("div"); wrap.className = "sx__dtwrap";
    var d = parseNaive(value);
    var dateEl = document.createElement("input"); dateEl.type = "date"; dateEl.className = "sx__dtdate";
    if (d) dateEl.value = d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
    var tw = document.createElement("div"); tw.className = "sx__twrap";
    var timeEl = document.createElement("input"); timeEl.type = "text"; timeEl.className = "sx__dttime";
    timeEl.readOnly = true; timeEl.placeholder = "Time";
    if (d) timeEl.value = fmtTimeText(d.getHours(), d.getMinutes());
    var pop = document.createElement("div"); pop.className = "sx__timepop";
    function slotGrid(labelText, slots) {
      var lab = document.createElement("div"); lab.className = "sx__tp-label"; lab.textContent = labelText;
      pop.appendChild(lab);
      var grid = document.createElement("div"); grid.className = "sx__timegrid";
      slots.forEach(function (t) {
        var b = document.createElement("button"); b.type = "button"; b.textContent = t;
        b.addEventListener("click", function () {
          timeEl.value = t; pop.classList.remove("open");
          timeEl.dispatchEvent(new Event("input", { bubbles: true }));
        });
        grid.appendChild(b);
      });
      pop.appendChild(grid);
    }
    slotGrid("Morning", timeSlots(8, 12));
    slotGrid("Afternoon & evening", timeSlots(12, 20));
    var foot = document.createElement("div"); foot.className = "sx__tp-foot";
    var span = document.createElement("span"); span.textContent = "Other time:";
    var other = document.createElement("input"); other.type = "text"; other.placeholder = "e.g. 2:45 PM";
    other.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      var t = parseTimeText(other.value);
      if (!t) { other.classList.add("sx__tp-bad"); return; }
      other.classList.remove("sx__tp-bad");
      timeEl.value = fmtTimeText(t.h, t.m); pop.classList.remove("open");
      timeEl.dispatchEvent(new Event("input", { bubbles: true }));
    });
    other.addEventListener("input", function () { other.classList.remove("sx__tp-bad"); });
    foot.appendChild(span); foot.appendChild(other); pop.appendChild(foot);
    timeEl.addEventListener("click", function (e) {
      e.stopPropagation();
      closeTimePops(pop);
      var opening = !pop.classList.contains("open");
      pop.classList.toggle("open", opening);
      if (opening) {
        Array.prototype.forEach.call(pop.querySelectorAll(".sx__timegrid button"), function (b) {
          b.classList.toggle("sel", b.textContent === timeEl.value);
        });
        other.value = "";
      }
    });
    pop.addEventListener("click", function (e) { e.stopPropagation(); });
    tw.appendChild(timeEl); tw.appendChild(pop);
    wrap.appendChild(dateEl); wrap.appendChild(tw);
    return wrap;
  }
  function closeTimePops(except) {
    Array.prototype.forEach.call(document.querySelectorAll(".sx__timepop.open"), function (p) {
      if (p !== except) p.classList.remove("open");
    });
  }
  document.addEventListener("click", function () { closeTimePops(null); });

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
      // Tap-to-toggle chip selector (never a multi-select list box). Options come
      // from the CRM field definitions; a stored value that has drifted out of the
      // options still renders (selected) so it isn't silently lost by a save.
      el = document.createElement("div"); el.className = "sx__chipsel";
      var sel = value || [];
      var copts = (f.options || fieldOptions[f.name] || []).filter(function (o) { return o !== ""; });
      sel.forEach(function (v) { if (copts.indexOf(v) < 0) copts.push(v); });
      copts.forEach(function (o) {
        var chip = document.createElement("button"); chip.type = "button";
        chip.className = "sx__chipopt" + (sel.indexOf(o) >= 0 ? " on" : "");
        chip.textContent = o; chip.dataset.v = o;
        chip.addEventListener("click", function () { chip.classList.toggle("on"); });
        el.appendChild(chip);
      });
      if (!copts.length) {
        var none = document.createElement("span"); none.className = "sx__muted"; none.textContent = "No options available.";
        el.appendChild(none);
      }
    } else if (f.type === "bool") {
      el = document.createElement("input"); el.type = "checkbox"; el.checked = !!value;
    } else if (f.type === "int") {
      el = document.createElement("input"); el.type = "number"; el.value = value == null ? "" : value;
    } else if (f.type === "date") {
      el = document.createElement("input"); el.type = "date"; el.value = value || "";
    } else if (f.type === "datetime") {
      el = makeDateTimeInput(value);
    } else if (f.type === "duration") {
      // Select of the CRM's preset choices (seconds); a stored duration outside
      // the presets is offered as-is so an existing value is never lost.
      el = document.createElement("select");
      var dopts = (fieldOptions[f.name] || DURATION_OPTIONS).slice();
      if (value != null && dopts.indexOf(value) < 0) { dopts.push(value); dopts.sort(function (a, b) { return a - b; }); }
      if (value == null) el.appendChild(new Option("(not set)", ""));
      dopts.forEach(function (secs) { el.appendChild(new Option(fmtDuration(secs), String(secs))); });
      el.value = value == null ? "" : String(value);
    } else if (f.type === "wysiwyg") {
      // Standard editor (shared CBMRichText/Jodit); legacy contenteditable
      // only if the vendored script failed to load. minHeight is inline in
      // Jodit, so the big-editor height rides the option, not CSS.
      el = (window.CBMRichText && window.CBMRichText.create(value, { minHeight: f.big ? 360 : 160 })) || makeWysiwyg(value);
    } else if (f.type === "text") {
      el = document.createElement("textarea"); el.rows = 3; el.value = value == null ? "" : value;
    } else {
      el = document.createElement("input"); el.type = "text"; el.value = value == null ? "" : value;
    }
    return el;
  }

  function readField(el) {
    var t = el.dataset.type;
    if (t === "multiEnum") return Array.prototype.map.call(el.querySelectorAll(".sx__chipopt.on"), function (c) { return c.dataset.v; });
    if (t === "bool") return el.checked;
    if (t === "int") return el.value === "" ? null : Number(el.value);
    if (t === "date") return el.value || null;
    if (t === "datetime") {
      // Composite Date + time-picker widget: both parts must be set to yield a
      // value (a UTC "YYYY-MM-DD HH:MM:SS" stamp, same as before).
      var dv2 = el.querySelector(".sx__dtdate"), tv2 = el.querySelector(".sx__dttime");
      if (!dv2) return fromLocalInput(el.value);  // (legacy shape)
      var tm = parseTimeText(tv2.value);
      if (!dv2.value || !tm) return null;
      return fromLocalInput(dv2.value + "T" + pad2(tm.h) + ":" + pad2(tm.m));
    }
    if (t === "addressStreet") {
      // The postal address block's two street lines rejoin into EspoCRM's single
      // multi-line street field (line 2 is stored as the second line).
      var l1 = el.querySelector(".sxf__a1").value.trim();
      var grid2 = el.parentNode, a22 = grid2 ? grid2.querySelector(".sxf__a2") : null;
      var l2 = a22 ? a22.value.trim() : "";
      return l2 ? l1 + "\n" + l2 : l1;
    }
    if (t === "duration") return el.value === "" ? null : Number(el.value);
    if (t === "wysiwyg") {
      if (el._cbmRichText) return el._cbmRichText.getValue();
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
  // The record's CBM contacts (the server-resolved set: assigned manager +
  // co-mentors, each with a real Contact id) — attendee-picker options
  // alongside the client contacts.
  function cbmAttendeeOptions() {
    return ((currentDetail && currentDetail.cbmContacts) || [])
      .filter(function (c) { return c.contactId; })
      .map(function (c) { return { id: c.contactId, name: c.name }; });
  }

  // Default invitees on a NEW session: every related contact (client/partner/
  // sponsor contacts) plus every CBM contact, deduped.
  function defaultAttendees() {
    var ids = ((currentDetail && currentDetail.contacts) || []).map(function (c) { return c.id; });
    cbmAttendeeOptions().forEach(function (c) { if (ids.indexOf(c.id) < 0) ids.push(c.id); });
    return ids;
  }

  function renderAttendees() {
    var box = $("attendees"); box.innerHTML = "";
    var contacts = (currentDetail && currentDetail.contacts) || [];
    var chosen = (currentSession && currentSession.attendees) || [];
    var seen = {};
    contacts.forEach(function (c) { seen[c.id] = true; });
    var cbm = cbmAttendeeOptions().filter(function (c) { return !seen[c.id]; });
    $("noAttendeeOptions").hidden = contacts.length + cbm.length > 0;
    function option(c, tagText) {
      var lab = document.createElement("label"); lab.className = "checkgrid__opt";
      var cb = document.createElement("input"); cb.type = "checkbox"; cb.value = c.id; cb.checked = chosen.indexOf(c.id) >= 0;
      cb.className = "sx__attendee";
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + (c.name || c.id) + (tagText ? " " + tagText : "")));
      box.appendChild(lab);
    }
    contacts.forEach(function (c) { option(c, ""); });
    cbm.forEach(function (c) { option(c, "(CBM)"); });
  }

  function chosenAttendees() {
    return Array.prototype.map.call($("attendees").querySelectorAll(".sx__attendee:checked"), function (c) { return c.value; });
  }

  // The editor form's CURRENT value for a field (changed or not).
  function editorFieldValue(name) {
    var el = $("sessionForm").querySelector('[data-field="' + name + '"]');
    return el ? readField(el) : null;
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
    openConfirm({
      title: "Unsaved changes",
      msg: "You have unsaved changes. Save them before going back?",
      saveLabel: "Save changes", discardLabel: "Discard", cancelLabel: "Keep editing",
      onSave: function () { saveSession(); },  // saveSession returns to the record on success
      onDiscard: function () {
        var dk = sessionDraftKey();  // deliberate discard clears the stash too
        if (dk) clearEditDraft(dk);
        openDetail(currentDetail.id);
      },
    });
  }

  // calendarDecision: undefined = not asked yet; "create" = auto-create the
  // Google Calendar event as usual; "skip" = the user chose to schedule the
  // meeting manually (the session still saves, no event/invitations).
  async function saveSession(calendarDecision) {
    if (!currentDetail) return;
    // A save is already in flight. Guarding here (not on the Save button) is
    // what makes this cover the dialog and calendar-prompt entry points too.
    if (savingSession) return;
    // Enforce the CRM's required fields (e.g. dateStart) client-side so the user
    // gets a clear message instead of a raw CRM 400 (validationFailure).
    var missing = [];
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-required]"), function (el) {
      var v = readField(el);
      if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) missing.push(el.dataset.label || el.dataset.field);
    });
    if (missing.length) { notice("editorNotice", "Please complete: " + missing.join(", "), "error"); return; }
    var isNew = !(currentSession && currentSession.id);
    // A NEW Scheduled session with a start time would auto-create a Google
    // Calendar event and email invitations — ask first, so the user can save
    // without an invite and schedule the meeting manually. The chosen button
    // re-enters saveSession with the decision; Keep editing just closes.
    if (isNew && calendarDecision === undefined && config && config.gcalEnabled
        && (editorFieldValue("status") || "Scheduled") === "Scheduled"
        && editorFieldValue("dateStart")) {
      show($("gcalModal"));
      $("gcalCreate").focus();
      return;
    }
    var changes = {};
    Array.prototype.forEach.call($("sessionForm").querySelectorAll("[data-field]"), function (el) {
      var v = readField(el);
      // On create send every field (it's a new record, and the pre-filled name
      // must reach the CRM verbatim). On update send only fields the user changed
      // (diff vs. the render-time snapshot) so a drifted, untouched enum isn't
      // re-sent and rejected.
      if (isNew || JSON.stringify(v) !== editorSnapshot[el.dataset.field]) changes[el.dataset.field] = v;
    });
    // Duration is virtual in the CRM (dateEnd − dateStart): when the start or the
    // duration changed, store it by sending the recomputed dateEnd instead.
    if ("dateStart" in changes || "duration" in changes) {
      var ds = editorFieldValue("dateStart"), dur = editorFieldValue("duration");
      if (ds && dur) changes.dateEnd = stampPlusSeconds(ds, dur);
    }
    delete changes.duration;
    var attendees = chosenAttendees();
    var dkey = sessionDraftKey();  // captured now — a create's "new" key is gone after
    savingSession = true;
    $("saveSessionBtn").disabled = true;
    try {
      var saved;
      if (currentSession && currentSession.id) {
        saved = await api("/sessions/" + encodeURIComponent(currentSession.id), {
          method: "PUT", body: JSON.stringify({ changes: changes, attendees: attendees })
        });
      } else {
        saved = await api("/records/" + encodeURIComponent(currentDetail.id) + "/sessions", {
          method: "POST",
          body: JSON.stringify({
            changes: changes, attendees: attendees,
            skipCalendar: calendarDecision === "skip",
            submissionToken: editorCreateToken,
          })
        });
      }
      if (dkey) clearEditDraft(dkey);  // saved => the stashed draft is obsolete
      // Await the re-fetch: openDetail hides detailNotice while rendering, so
      // showing the notice first would get it wiped a moment later.
      await openDetail(currentDetail.id);
      // The calendar hook is best-effort (the session saved either way) — the
      // notice just tells the user what happened to the Google Calendar event.
      // A completed session on a still-Assigned engagement also moves the
      // engagement to Active server-side; tell the user when that happened.
      var eng = saved && saved.engagement;
      var engExtra = "";
      if (eng && eng.activated) engExtra = " The engagement status is now Active.";
      else if (eng) engExtra = " (The engagement status could not be updated to Active: " + (eng.error || "unknown error") + ")";
      // A follow-up write failing after the session exists (attendee attach,
      // invite send) is a WARNING on a successful save — never a failure that
      // invites re-creating the session.
      var warnExtra = "";
      if (saved && saved.warning) warnExtra += " " + saved.warning;
      var cal = saved && saved.calendar;
      if (cal && cal.ok && cal.inviteError) warnExtra += " " + cal.inviteError;
      var msg, style = warnExtra ? "error" : "success";
      if (cal && cal.ok === false && !cal.disabled) {
        msg = "Session saved, but the Google Calendar invitation failed: " + (cal.error || "unknown error");
        style = "error";
      } else if (cal && cal.ok && cal.meetLink) {
        msg = cal.inviteError ? "Session saved — calendar event created." : "Session saved — calendar invitations sent.";
      } else if (cal && cal.ok && cal.cancelled) {
        msg = "Session saved — the calendar event was cancelled.";
      } else if (cal && cal.ok && cal.updated) {
        msg = "Session saved — the calendar event was updated.";
      } else if (cal && cal.ok && cal.declined) {
        msg = "Session saved — no calendar invite was created (schedule the meeting manually).";
      } else {
        msg = "Session saved.";
      }
      notice("detailNotice", msg + engExtra + warnExtra, style);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice("editorNotice", e.message, "error");
    } finally { savingSession = false; $("saveSessionBtn").disabled = false; }
  }
})();
