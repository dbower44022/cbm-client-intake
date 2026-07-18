/* Mentor assignment dashboard — vanilla JS, no build step.
 *
 * Flow: check session -> dashboard (sign-in happens once at the portal `/`;
 * unauthenticated visits are sent there and come back after login). The
 * dashboard lists Submitted engagements, each with a dropdown of eligible
 * mentors; choosing one and confirming POSTs the assignment, which the server
 * performs as the logged-in EspoCRM user.
 */
(function () {
  "use strict";

  var API = "/assignments/api";
  var mentors = [];
  var selectedStatuses = [];   // engagementStatus values currently filtered to
  var statusFilterBuilt = false;

  // --- tiny DOM helpers ---
  function $(id) { return document.getElementById(id); }
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    var resp = await fetch(API + path, opts);
    var data = null;
    try { data = await resp.json(); } catch (e) { /* no body */ }
    if (!resp.ok) {
      var msg = (data && (data.detail || data.message)) || ("Request failed (" + resp.status + ")");
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
    location.href = "/?next=" + encodeURIComponent("/assignments/");
  }

  function showMessage(text) {
    hide($("dashView"));
    var m = $("msgView");
    $("msgText").textContent = text;
    show(m);
  }

  // On boot: 401 = not signed in (go sign in at the portal); 403 = signed in
  // but not entitled to this app (show the exact reason); anything else = the
  // server is down — say so.
  function bootFail(e) {
    if (e && e.status === 401) { showLogin(); return; }
    if (e && e.status === 403) { showMessage(e.message); return; }
    showMessage("The server isn't responding right now. Please try again in a moment.");
  }

  function showDashboard(user) {
    hide($("msgView"));
    $("whoName").textContent = user.name || user.userName;
    show($("userChip"));
    show($("dashView"));
    loadData();
  }

  function notice(text, kind) {
    var n = $("notice");
    n.textContent = text;
    n.className = "assign__notice " + (kind === "error" ? "is-error" : "is-success");
    show(n);
    // Bring the confirmation into view — the user may have assigned from a row
    // far down the grid, leaving the notice off-screen at the top.
    n.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function clearNotice() { hide($("notice")); }

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) { /* ignore */ }
    location.href = "/";  // back to the portal sign-in
  });

  $("refreshBtn").addEventListener("click", loadData);

  // Close the status dropdown when clicking outside it (the selection is already
  // applied live on each change, so closing just dismisses the panel). Escape
  // closes it too.
  document.addEventListener("click", function (ev) {
    var details = $("statusFilter");
    if (details && details.open && !details.contains(ev.target)) {
      details.open = false;
    }
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    var openModal = document.querySelector(".modal:not([hidden])");
    if (openModal) { hide(openModal); return; }
    var details = $("statusFilter");
    if (details && details.open) details.open = false;
  });

  // --- status filter ---
  function statusQuery() {
    return selectedStatuses
      .map(function (s) { return "status=" + encodeURIComponent(s); })
      .join("&");
  }

  function statusOptionBoxes() {
    return $("statusPanel").querySelectorAll("input[type=checkbox][data-status]");
  }

  function updateStatusSummary() {
    var s = $("statusSummary");
    var total = statusOptionBoxes().length;
    if (!selectedStatuses.length) s.textContent = "Status: none selected";
    else if (total && selectedStatuses.length === total) s.textContent = "Status: All";
    else if (selectedStatuses.length <= 2) s.textContent = "Status: " + selectedStatuses.join(", ");
    else s.textContent = "Status: " + selectedStatuses.length + " selected";
  }

  function syncStatusAllToggle() {
    var all = $("statusAllToggle");
    if (!all) return;
    var total = statusOptionBoxes().length;
    all.checked = total > 0 && selectedStatuses.length === total;
    all.indeterminate = selectedStatuses.length > 0 && selectedStatuses.length < total;
  }

  function buildStatusFilter(allStatuses) {
    var panel = $("statusPanel");
    panel.innerHTML = "";
    // "All" master toggle — one click to see engagements in every status.
    var allLabel = document.createElement("label");
    allLabel.className = "statusfilter__opt statusfilter__opt--all";
    var allCb = document.createElement("input");
    allCb.type = "checkbox";
    allCb.id = "statusAllToggle";
    allCb.addEventListener("change", onStatusAllChange);
    allLabel.appendChild(allCb);
    allLabel.appendChild(document.createTextNode(" All"));
    panel.appendChild(allLabel);
    allStatuses.forEach(function (st) {
      var label = document.createElement("label");
      label.className = "statusfilter__opt";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = st;
      cb.dataset.status = st;
      cb.checked = selectedStatuses.indexOf(st) >= 0;
      cb.addEventListener("change", onStatusChange);
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + st));
      panel.appendChild(label);
    });
    statusFilterBuilt = true;
    syncStatusAllToggle();
    updateStatusSummary();
  }

  function onStatusAllChange() {
    var check = this.checked;
    Array.prototype.forEach.call(statusOptionBoxes(), function (c) { c.checked = check; });
    onStatusChange();
  }

  function onStatusChange() {
    var cbs = statusOptionBoxes();
    selectedStatuses = Array.prototype.filter.call(cbs, function (c) { return c.checked; })
      .map(function (c) { return c.value; });
    syncStatusAllToggle();
    updateStatusSummary();
    reloadEngagements();
  }

  // --- data + rendering ---
  async function fetchEngagements() {
    var qs = statusQuery();
    return api("/engagements" + (qs ? "?" + qs : ""));
  }

  async function loadData() {
    clearNotice();
    show($("loadingState"));
    hide($("engTable"));
    hide($("emptyState"));
    // Load each independently with a labeled error, so a failure tells the user
    // which part broke (mentors vs. engagements) instead of one generic message.
    try {
      var mres, eng;
      try { mres = await api("/mentors"); }
      catch (e) { if (e.status === 401) { showLogin(); return; } notice("Couldn't load mentors: " + e.message, "error"); return; }
      try { eng = await fetchEngagements(); }
      catch (e) { if (e.status === 401) { showLogin(); return; } notice("Couldn't load engagements: " + e.message, "error"); return; }
      mentors = mres.mentors || [];
      selectedStatuses = eng.selectedStatuses || selectedStatuses;
      buildStatusFilter(eng.allStatuses || []);
      renderTable(eng.engagements || []);
    } finally {
      hide($("loadingState"));
    }
  }

  async function reloadEngagements() {
    clearNotice();
    if (!selectedStatuses.length) {
      renderTable([]);
      notice("Select at least one status to view engagements.", "error");
      return;
    }
    show($("loadingState"));
    hide($("engTable"));
    hide($("emptyState"));
    try {
      var eng = await fetchEngagements();
      renderTable(eng.engagements || []);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    } finally {
      hide($("loadingState"));
    }
  }

  // --- engagement grid sorting + search (client-side, like the mentors grid) ---
  var engRows = [];                     // last-loaded rows, in server order (newest first)
  var engSort = { key: null, dir: 1 }; // key null = keep the server order
  var engQuery = "";                    // full-text search over the loaded rows

  function renderTable(engagements) {
    engRows = engagements;
    repaintEngagements();
  }

  function engHaystack(e) {
    return [
      e.name, e.status, e.clientName, e.contactName, e.mentorName, e.notes,
      (e.createdAt || "").slice(0, 10), (e.assignedDate || "").slice(0, 10),
    ].join(" ").toLowerCase();
  }

  $("engSearch").addEventListener("input", function () {
    engQuery = this.value;
    repaintEngagements();
  });

  function engSortVal(e, k) {
    // UTC "YYYY-MM-DD HH:MM:SS" stamps compare correctly as strings; a row
    // without one ("") sorts before any date ascending, after it descending.
    if (k === "assignedDate") return e.assignedDate || "";
    // Numeric: unassigned rows (-1) sort below any real day count.
    if (k === "daysPending") { var d = daysPending(e); return d == null ? -1 : d; }
    return (e[k] || "").toString().toLowerCase();
  }

  function repaintEngagements() {
    var body = $("engBody");
    body.innerHTML = "";
    updateEngSortIndicators();
    var rows = engRows.slice();
    var q = engQuery.trim().toLowerCase();
    if (q) {
      rows = rows.filter(function (e) { return engHaystack(e).indexOf(q) >= 0; });
    }
    if (!rows.length) {
      $("emptyState").textContent = engRows.length
        ? "No engagements match your search."
        : "No submitted engagements awaiting assignment. 🎉";
      hide($("engTable"));
      show($("emptyState"));
      return;
    }
    hide($("emptyState"));
    if (engSort.key) {
      var k = engSort.key, dir = engSort.dir;
      rows.sort(function (a, b) {
        var va = engSortVal(a, k), vb = engSortVal(b, k);
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
    }
    rows.forEach(function (eng) { body.appendChild(buildRow(eng)); });
    show($("engTable"));
  }

  function updateEngSortIndicators() {
    Array.prototype.forEach.call($("engTable").querySelectorAll("th[data-sort]"), function (th) {
      var active = th.getAttribute("data-sort") === engSort.key;
      th.setAttribute("aria-sort", active ? (engSort.dir === 1 ? "ascending" : "descending") : "none");
      th.dataset.dir = active ? (engSort.dir === 1 ? "asc" : "desc") : "";
    });
  }

  Array.prototype.forEach.call(
    document.querySelectorAll("#engTable th[data-sort]"),
    function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (engSort.key === key) {
          engSort.dir = -engSort.dir;
        } else {
          engSort.key = key;
          // Dates most-recent-first and day counts longest-waiting-first on
          // the first click; text columns A→Z.
          engSort.dir = (key === "assignedDate" || key === "daysPending") ? -1 : 1;
        }
        repaintEngagements();
      });
    }
  );

  // --- row selection (click) + context menu (right-click) ---
  var selectedEngId = null;

  function selectRow(engId) {
    selectedEngId = engId;
    Array.prototype.forEach.call(document.querySelectorAll("#engBody tr"), function (tr) {
      tr.classList.toggle("is-selected", tr.dataset.engId === engId);
    });
  }

  function selectedEngagement() {
    if (!selectedEngId) return null;
    return engRows.filter(function (e) { return e.id === selectedEngId; })[0] || null;
  }

  function buildRow(eng) {
    var tr = document.createElement("tr");
    tr.dataset.engId = eng.id;
    if (eng.id === selectedEngId) tr.classList.add("is-selected");

    // Click anywhere non-interactive selects the row (toggle); right-click
    // selects it AND opens the row's context menu.
    tr.addEventListener("click", function (ev) {
      if (ev.target.closest("button, select, a, input, textarea, label")) return;
      selectRow(eng.id === selectedEngId ? null : eng.id);
    });
    tr.addEventListener("contextmenu", function (ev) {
      ev.preventDefault();
      selectRow(eng.id);
      showContextMenu(ev.clientX, ev.clientY, rowMenuItems(tr, eng));
    });

    var tdEng = document.createElement("td");
    var name = document.createElement("button");
    name.type = "button";
    name.className = "eng-name eng-name--link";
    name.textContent = eng.name || "(unnamed engagement)";
    name.addEventListener("click", function () { openDetail(eng.id); });
    tdEng.appendChild(name);
    if (eng.status) {
      var badge = document.createElement("span");
      badge.className = "eng-status";
      badge.textContent = eng.status;
      tdEng.appendChild(badge);
    }
    var meta = document.createElement("span");
    meta.className = "eng-meta";
    var bits = [];
    if (eng.clientName) bits.push(eng.clientName);
    if (eng.contactName) bits.push(eng.contactName);
    if (eng.createdAt) bits.push("created " + eng.createdAt.slice(0, 10));
    meta.textContent = bits.join(" · ");
    tdEng.appendChild(meta);
    tr.appendChild(tdEng);

    var tdAssign = document.createElement("td");
    if (eng.mentorId) {
      // Already assigned — show the mentor; no picker/Assign button.
      var assigned = document.createElement("span");
      assigned.className = "assigned-mentor";
      assigned.textContent = eng.mentorName || "Assigned";
      tdAssign.appendChild(assigned);
      tr.appendChild(tdAssign);
      tr.appendChild(buildAssignedDateCell(eng));
      tr.appendChild(buildDaysCell(eng));
      tr.appendChild(buildNotesCell(eng));
      return tr;
    }

    var cell = document.createElement("div");
    cell.className = "assign-cell";

    var select = document.createElement("select");
    select.appendChild(new Option("Select a mentor…", ""));
    mentors.forEach(function (m) {
      var label = m.name;
      // availableCapacity is app-computed (Max Clients − Active Clients);
      // -1 = unlimited, shown with no suffix.
      if (typeof m.availableCapacity === "number" && m.availableCapacity >= 0) {
        label += " (capacity " + m.availableCapacity + ")";
      }
      select.appendChild(new Option(label, m.id));
    });

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cbm-button";
    btn.textContent = "Assign";

    // Never disabled (Doug's ruling: buttons stay active) — clicking without a
    // mentor chosen explains what's needed instead of being grayed out.
    btn.addEventListener("click", function () {
      if (!select.value) {
        notice(
          "Select a mentor for “" + (eng.name || "this engagement") +
          "” from its dropdown before clicking Assign.",
          "error"
        );
        select.focus();
        return;
      }
      doAssign(tr, eng, select.value, select.options[select.selectedIndex].text);
    });

    cell.appendChild(select);
    cell.appendChild(btn);
    tdAssign.appendChild(cell);
    tr.appendChild(tdAssign);
    tr.appendChild(buildAssignedDateCell(eng));
    tr.appendChild(buildDaysCell(eng));
    tr.appendChild(buildNotesCell(eng));
    return tr;
  }

  // When the mentor was assigned (engagementAssignedDate — stamped by the
  // Assign action; pre-0.27.0 assignments have none, unassigned rows show —).
  function buildAssignedDateCell(eng) {
    var td = document.createElement("td");
    td.className = "assigned-date-cell";
    td.textContent = formatDate(eng.assignedDate) || "—";
    return td;
  }

  // Whole calendar days between the assigned date and today (local calendar,
  // matching the date shown in the Assigned Date column); null when unassigned.
  function daysSinceAssigned(stamp) {
    if (!stamp) return null;
    var d;
    if (stamp.length <= 10) {          // date-only "YYYY-MM-DD" — no TZ shift
      var p = stamp.split("-");
      d = new Date(+p[0], +p[1] - 1, +p[2]);
    } else {                           // UTC datetime -> local calendar date
      var utc = new Date(stamp.replace(" ", "T") + "Z");
      if (isNaN(utc.getTime())) return null;
      d = new Date(utc.getFullYear(), utc.getMonth(), utc.getDate());
    }
    if (isNaN(d.getTime())) return null;
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((today - d) / 86400000);
  }

  // Days the engagement has been waiting in "Pending Acceptance". The Assign
  // action is what sets that status, stamping engagementAssignedDate at the
  // same moment — so for a row still pending, days-since-stamp IS days pending.
  // Any other status (or a hand-set pending row with no stamp) shows —.
  function daysPending(eng) {
    if (eng.status !== "Pending Acceptance") return null;
    return daysSinceAssigned(eng.assignedDate);
  }

  function buildDaysCell(eng) {
    var td = document.createElement("td");
    td.className = "days-cell";
    var days = daysPending(eng);
    td.textContent = days == null ? "—" : String(days);
    return td;
  }

  // --- notes column (internal process notes -> CEngagement.description) ---
  // Click the cell to edit; Save PUTs /engagements/{id}/notes, Cancel/Escape
  // reverts. These are staff-only triage notes — the description field is not
  // shown in any other tool.
  function buildNotesCell(eng) {
    var td = document.createElement("td");
    td.className = "notes-cell";
    renderNotesView(td, eng);
    return td;
  }

  function renderNotesView(td, eng) {
    td.innerHTML = "";
    var view = document.createElement("button");
    view.type = "button";
    view.className = "notes-view" + (eng.notes ? "" : " notes-view--empty");
    view.textContent = eng.notes || "Add notes…";
    view.title = "Click to edit internal notes";
    view.addEventListener("click", function () { openNotesEditor(td, eng); });
    td.appendChild(view);
  }

  function openNotesEditor(td, eng) {
    td.innerHTML = "";
    var ta = document.createElement("textarea");
    ta.className = "notes-input";
    ta.rows = 3;
    ta.value = eng.notes || "";
    ta.placeholder = "Internal notes about this client assignment…";

    var actions = document.createElement("div");
    actions.className = "notes-actions";
    var save = document.createElement("button");
    save.type = "button";
    save.className = "cbm-button";
    save.textContent = "Save";
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "cbm-button cbm-button--secondary";
    cancel.textContent = "Cancel";

    function closeEditor() { renderNotesView(td, eng); }
    cancel.addEventListener("click", closeEditor);
    ta.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); closeEditor(); }
    });
    save.addEventListener("click", async function () {
      var value = ta.value.trim();
      save.disabled = true;
      cancel.disabled = true;
      try {
        var res = await api("/engagements/" + encodeURIComponent(eng.id) + "/notes", {
          method: "PUT",
          body: JSON.stringify({ notes: value }),
        });
        eng.notes = res.notes || "";
        renderNotesView(td, eng);
      } catch (e) {
        save.disabled = false;
        cancel.disabled = false;
        if (e.status === 401) { showLogin(); return; }
        notice("Couldn't save notes: " + e.message, "error");
      }
    });

    actions.appendChild(save);
    actions.appendChild(cancel);
    td.appendChild(ta);
    td.appendChild(actions);
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  }

  // --- engagement detail modal ---
  function closeModal() { hide($("engModal")); }

  // Rich-text (wysiwyg) rendering. Formatting tags are kept; everything risky is
  // stripped (scripts, event handlers, styles, unknown tags), so CRM/intake HTML
  // renders safely without a build step or external sanitizer.
  var RICH_ALLOWED = {
    A: 1, B: 1, STRONG: 1, I: 1, EM: 1, U: 1, S: 1, STRIKE: 1, P: 1, BR: 1,
    UL: 1, OL: 1, LI: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, BLOCKQUOTE: 1,
    SPAN: 1, DIV: 1, PRE: 1, CODE: 1, HR: 1, TABLE: 1, THEAD: 1, TBODY: 1,
    TR: 1, TD: 1, TH: 1, SUB: 1, SUP: 1,
  };
  var RICH_DROP = {
    SCRIPT: 1, STYLE: 1, IFRAME: 1, OBJECT: 1, EMBED: 1, LINK: 1, META: 1,
    SVG: 1, MATH: 1, FORM: 1, INPUT: 1, BUTTON: 1, TEXTAREA: 1, IMG: 1,
  };

  function sanitizeBody(body) {
    var els = Array.prototype.slice.call(body.querySelectorAll("*"));
    var drop = [], unwrap = [];
    els.forEach(function (el) {
      var tag = el.tagName;
      if (RICH_DROP[tag]) { drop.push(el); return; }
      Array.prototype.slice.call(el.attributes).forEach(function (a) {
        var keep = tag === "A" && a.name.toLowerCase() === "href" &&
          /^(https?:|mailto:|tel:)/i.test(a.value.trim());
        if (!keep) el.removeAttribute(a.name);
      });
      if (!RICH_ALLOWED[tag]) {
        unwrap.push(el);
      } else if (tag === "A") {
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener noreferrer");
      }
    });
    drop.forEach(function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
    unwrap.forEach(function (n) {
      if (!n.parentNode) return;
      while (n.firstChild) n.parentNode.insertBefore(n.firstChild, n);
      n.parentNode.removeChild(n);
    });
  }

  function renderRichText(target, html) {
    target.innerHTML = "";
    var raw = (html || "").trim();
    if (!raw) { target.textContent = "—"; return; }
    var doc = new DOMParser().parseFromString(raw, "text/html");
    sanitizeBody(doc.body);
    if (!doc.body.textContent.trim() && !doc.body.querySelector("br,hr")) {
      target.textContent = "—";
      return;
    }
    // Import the cleaned nodes (no scripts remain) rather than re-parsing a string.
    Array.prototype.slice.call(doc.body.childNodes).forEach(function (n) {
      target.appendChild(document.importNode(n, true));
    });
  }

  function formatDateTime(s) {
    if (!s) return null;
    // EspoCRM datetimes are UTC "YYYY-MM-DD HH:MM:SS".
    var d = new Date(s.replace(" ", "T") + "Z");
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  }

  // Date-only display. A UTC datetime stamp shows as the LOCAL calendar date;
  // a date-only value ("YYYY-MM-DD") is a plain calendar date — no shift.
  function formatDate(s) {
    if (!s) return null;
    var opts = { year: "numeric", month: "short", day: "numeric" };
    if (s.length <= 10) {
      var p = s.split("-");
      var cal = new Date(+p[0], +p[1] - 1, +p[2]);
      return isNaN(cal.getTime()) ? s : cal.toLocaleDateString(undefined, opts);
    }
    var d = new Date(s.replace(" ", "T") + "Z");
    if (isNaN(d.getTime())) return s.slice(0, 10);
    return d.toLocaleDateString(undefined, opts);
  }

  // US display phone "(216)-555-1234" — the product-wide shared formatter
  // (/shared/phone-format.js); tel: hrefs keep the raw stored value.
  function formatPhone(raw) {
    if (!raw) return raw;
    return window.CBM && CBM.formatPhone ? CBM.formatPhone(raw) : raw;
  }

  function addContactField(dl, label, value, href) {
    if (!value) return;
    var dt = document.createElement("dt");
    dt.textContent = label;
    var dd = document.createElement("dd");
    if (href) {
      var a = document.createElement("a");
      a.href = href;
      a.textContent = value;
      dd.appendChild(a);
    } else {
      dd.textContent = value;
    }
    dl.appendChild(dt);
    dl.appendChild(dd);
  }

  function fillDetail(d) {
    $("modalTitle").textContent = d.name || "Engagement";
    var st = $("modalStatus");
    if (d.status) { st.textContent = d.status; st.hidden = false; } else { st.hidden = true; }

    // Top panel split into two columns: contact identity on the left, the
    // engagement meta (meeting cadence + create date) on the right.
    var c = d.contact || {};
    var left = document.createElement("dl");
    left.className = "contact-dl";
    addContactField(left, "Name", c.name);
    addContactField(left, "Title", c.title);
    addContactField(left, "Company", c.company || d.clientName);
    // Email opens the quick-compose dialog (mailto: fallback) — /shared/quickmail.js.
    if (c.email && window.CBMQuickMail) {
      var edt = document.createElement("dt"); edt.textContent = "Email";
      var edd = document.createElement("dd"); edd.appendChild(CBMQuickMail.emailLink(c.email));
      left.appendChild(edt); left.appendChild(edd);
    } else {
      addContactField(left, "Email", c.email, c.email ? "mailto:" + c.email : null);
    }
    addContactField(left, "Phone", formatPhone(c.phone), c.phone ? "tel:" + c.phone : null);

    var right = document.createElement("dl");
    right.className = "contact-dl";
    addContactField(right, "Meeting", d.meetingCadence);
    addContactField(right, "Created", formatDateTime(d.createdAt));
    // Requested mentor (DAT-026), when set. A linked-but-nameless value means the
    // referenced mentor profile was deleted — surface that rather than hide it.
    if (d.requestedMentor) {
      addContactField(right, "Requested mentor", d.requestedMentor.name || "(no longer in the system)");
    }

    var contact = $("modalContact");
    contact.innerHTML = "";
    contact.appendChild(left);
    contact.appendChild(right);

    var focus = $("modalFocus");
    focus.innerHTML = "";
    if (d.focusAreas && d.focusAreas.length) {
      d.focusAreas.forEach(function (f) {
        var chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = f;
        focus.appendChild(chip);
      });
    } else {
      focus.textContent = "—";
    }

    renderRichText($("modalNeeds"), d.needs);
    renderRichText($("modalNotes"), d.notes);
    // The grid's internal process notes (CEngagement.description) — plain text.
    $("modalInternalNotes").textContent = d.internalNotes || "—";
  }

  async function openDetail(id) {
    $("modalTitle").textContent = "Loading…";
    $("modalStatus").hidden = true;
    $("modalContact").innerHTML = "";
    $("modalFocus").innerHTML = "";
    $("modalNeeds").textContent = "";
    $("modalNotes").textContent = "";
    $("modalInternalNotes").textContent = "";
    show($("engModal"));
    try {
      fillDetail(await api("/engagements/" + encodeURIComponent(id)));
    } catch (e) {
      closeModal();
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    }
  }

  // Generic modal close: clicking a [data-close] element (backdrop or ×) closes
  // its containing modal.
  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (t && t.hasAttribute && t.hasAttribute("data-close")) {
      var m = t.closest(".modal");
      if (m) hide(m);
    }
  });

  // --- mentor review ---
  function chipRow(values) {
    var wrap = document.createElement("div");
    wrap.className = "chips";
    if (!values || !values.length) { wrap.textContent = "—"; return wrap; }
    values.forEach(function (v) {
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = v;
      wrap.appendChild(chip);
    });
    return wrap;
  }

  // The review list is the full roster (any status), distinct from the eligible
  // `mentors` used by the assign dropdown.
  var reviewMentors = [];
  // False when the server couldn't read CEngagement (metric columns come back
  // blank) — surfaced on the count line so blanks aren't mistaken for zeros.
  var reviewMetricsAvailable = true;
  // The CRM's full mentorType enum — the filter offers every type, not just the
  // ones present in the current roster.
  var reviewMentorTypes = [];
  // Default to Active mentors, highest capacity first (best fit to take a
  // new client); the admin can widen to other statuses.
  var mentorFilter = { q: "", status: "Active", type: "", industry: "", expertise: "", availOnly: false,
                       sortKey: "maxCapacity", sortDir: -1 };

  // mentorType may be a single enum (string) or a multi-enum (array); normalize
  // to a list so the column/filter/search handle both.
  function mentorTypes(m) {
    if (Array.isArray(m.mentorType)) return m.mentorType.filter(Boolean);
    return m.mentorType ? [m.mentorType] : [];
  }

  function mentorAvail(m) {
    return m.availableCapacity === -1 ? Infinity
      : (typeof m.availableCapacity === "number" ? m.availableCapacity : -Infinity);
  }
  function mentorHasCapacity(m) { return mentorAvail(m) > 0; }

  function mentorHaystack(m) {
    return [m.name, (m.industryExperience || []).join(" "), mentorTypes(m).join(" "),
            (m.expertise || []).join(" ")].join(" ").toLowerCase();
  }

  function sortVal(m, k) {
    if (k === "maxCapacity" || k === "activeClients" || k === "assignedLast30" || k === "lifetimeClients")
      return m[k] == null ? -Infinity : m[k];
    if (k === "availableCapacity") return mentorAvail(m);
    if (k === "acceptingNewClients") return m.acceptingNewClients ? 1 : 0;
    if (k === "mentorType") return mentorTypes(m).join(", ").toLowerCase();
    if (k === "industryExperience") return (m.industryExperience || []).join(", ").toLowerCase();
    return (m[k] || "").toString().toLowerCase();
  }

  function distinct(getList) {
    var set = {};
    reviewMentors.forEach(function (m) {
      getList(m).forEach(function (v) { if (v) set[v] = true; });
    });
    return Object.keys(set).sort();
  }

  // CRM-declared options first (their order), then any row values not in the
  // declared list (e.g. a since-removed enum value still stored on a mentor).
  function withOptions(declared, found) {
    var out = (declared || []).slice();
    found.forEach(function (v) { if (out.indexOf(v) < 0) out.push(v); });
    return out;
  }

  function fillFilterSelect(sel, values, placeholder) {
    var current = sel.value;
    sel.innerHTML = "";
    sel.appendChild(new Option(placeholder, ""));
    values.forEach(function (v) { sel.appendChild(new Option(v, v)); });
    sel.value = current;  // preserve selection across re-fills
  }

  function applyMentorFilter() {
    var q = mentorFilter.q.trim().toLowerCase();
    var rows = reviewMentors.filter(function (m) {
      if (q && mentorHaystack(m).indexOf(q) < 0) return false;
      if (mentorFilter.status && m.status !== mentorFilter.status) return false;
      if (mentorFilter.type && mentorTypes(m).indexOf(mentorFilter.type) < 0) return false;
      if (mentorFilter.industry && (m.industryExperience || []).indexOf(mentorFilter.industry) < 0) return false;
      if (mentorFilter.expertise && (m.expertise || []).indexOf(mentorFilter.expertise) < 0) return false;
      if (mentorFilter.availOnly && !mentorHasCapacity(m)) return false;
      return true;
    });
    var k = mentorFilter.sortKey, dir = mentorFilter.sortDir;
    rows.sort(function (a, b) {
      var va = sortVal(a, k), vb = sortVal(b, k);
      return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
    });
    renderMentorRows(rows);
    $("mentorCount").textContent =
      "Showing " + rows.length + " of " + reviewMentors.length + " mentors" +
      (reviewMetricsAvailable ? "" :
        " — client counts unavailable (your account can't read engagements)");
    updateSortIndicators();
  }

  function renderMentorRows(rows) {
    var tb = $("mentorTbody");
    tb.innerHTML = "";
    if (!rows.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 11;
      td.className = "mentor-empty";
      td.textContent = "No mentors match the current filters.";
      tr.appendChild(td);
      tb.appendChild(tr);
      return;
    }
    rows.forEach(function (m) {
      var tr = document.createElement("tr");
      tr.appendChild(cell(m.name || "(unnamed)", "mentor-name-cell"));
      tr.appendChild(cell(m.status || "—"));
      var types = mentorTypes(m);
      tr.appendChild(cell(types.length ? types.join(", ") : "—"));
      tr.appendChild(cell(m.acceptingNewClients ? "Yes" : "No"));
      // Client counts are app-computed from CEngagement (Active/Assigned/Pending
      // Acceptance = active); Available = Max − Active; Max is the stored
      // maximumClientCapacity exactly as on the CRM record (blank there = blank here).
      tr.appendChild(cell(numText(m.activeClients), "num"));
      tr.appendChild(cell(numText(m.maxCapacity), "num"));
      tr.appendChild(cell(m.availableCapacity === -1 ? "Unlimited" : numText(m.availableCapacity), "num"));
      tr.appendChild(cell(numText(m.assignedLast30), "num"));
      tr.appendChild(cell(numText(m.lifetimeClients), "num"));
      var ieTd = document.createElement("td"); ieTd.appendChild(chipRow(m.industryExperience)); tr.appendChild(ieTd);
      var exTd = document.createElement("td"); exTd.appendChild(chipRow(m.expertise)); tr.appendChild(exTd);
      tb.appendChild(tr);
    });
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = text;
    return td;
  }

  function numText(v) { return v == null ? "—" : String(v); }

  function updateSortIndicators() {
    Array.prototype.forEach.call($("mentorTable").querySelectorAll("th[data-sort]"), function (th) {
      var active = th.getAttribute("data-sort") === mentorFilter.sortKey;
      th.setAttribute("aria-sort", active ? (mentorFilter.sortDir === 1 ? "ascending" : "descending") : "none");
      th.dataset.dir = active ? (mentorFilter.sortDir === 1 ? "asc" : "desc") : "";
    });
  }

  async function openMentorReview() {
    clearNotice();
    try {
      if (!reviewMentors.length) {
        var res = await api("/mentors?all=true");
        reviewMentors = res.mentors || [];
        reviewMetricsAvailable = res.metricsAvailable !== false;
        reviewMentorTypes = res.mentorTypeOptions || [];
      }
      fillFilterSelect($("mentorStatusFilter"),
        distinct(function (m) { return [m.status]; }), "All statuses");
      // Reflect the default/persisted status filter in the dropdown.
      $("mentorStatusFilter").value = mentorFilter.status;
      fillFilterSelect($("mentorTypeFilter"),
        withOptions(reviewMentorTypes, distinct(function (m) { return mentorTypes(m); })),
        "All types");
      $("mentorTypeFilter").value = mentorFilter.type;
      fillFilterSelect($("mentorIndustryFilter"),
        distinct(function (m) { return m.industryExperience || []; }), "All industry experience");
      fillFilterSelect($("mentorExpertiseFilter"),
        distinct(function (m) { return m.expertise || []; }), "All areas of expertise");
      applyMentorFilter();
      show($("mentorModal"));
      $("mentorSearch").focus();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    }
  }

  $("reviewMentorsBtn").addEventListener("click", openMentorReview);
  $("mentorSearch").addEventListener("input", function () {
    mentorFilter.q = this.value; applyMentorFilter();
  });
  $("mentorStatusFilter").addEventListener("change", function () {
    mentorFilter.status = this.value; applyMentorFilter();
  });
  $("mentorTypeFilter").addEventListener("change", function () {
    mentorFilter.type = this.value; applyMentorFilter();
  });
  $("mentorIndustryFilter").addEventListener("change", function () {
    mentorFilter.industry = this.value; applyMentorFilter();
  });
  $("mentorExpertiseFilter").addEventListener("change", function () {
    mentorFilter.expertise = this.value; applyMentorFilter();
  });
  $("mentorAvailOnly").addEventListener("change", function () {
    mentorFilter.availOnly = this.checked; applyMentorFilter();
  });
  Array.prototype.forEach.call(
    document.querySelectorAll("#mentorTable th[data-sort]"),
    function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (mentorFilter.sortKey === key) {
          mentorFilter.sortDir = -mentorFilter.sortDir;
        } else {
          mentorFilter.sortKey = key;
          // numbers default high→low, text low→high
          mentorFilter.sortDir = (key === "name" || key === "industryExperience" || key === "mentorType") ? 1 : -1;
        }
        applyMentorFilter();
      });
    }
  );

  function doAssign(tr, eng, mentorProfileId, mentorLabel) {
    if (!mentorProfileId) return;
    showConfirmModal({
      title: "Assign “" + (eng.name || "this engagement") + "” to " + mentorLabel + "?",
      body: "This sets the engagement to “Pending Acceptance” and reassigns its " +
        "contact(s) and client records to the mentor's user.",
      confirmLabel: "Assign",
    }, function () { performAssign(tr, eng, mentorProfileId); });
  }

  async function performAssign(tr, eng, mentorProfileId) {
    clearNotice();
    tr.classList.add("row-busy");
    try {
      var res = await api("/engagements/" + encodeURIComponent(eng.id) + "/assign", {
        method: "POST",
        body: JSON.stringify({ mentorProfileId: mentorProfileId }),
      });
      // Re-fetch so the grid reflects the current filter (the engagement is now
      // Pending Acceptance — it stays if that status is selected, else drops off).
      await reloadEngagements();
      // repaired = the engagement already had THIS mentor (a previous attempt
      // died mid re-homing); the server re-ran the re-homing instead of a 400.
      var summary = res.repaired
        ? "Finished the earlier assignment of “" + (eng.name || "engagement") +
          "” to " + res.mentorName + " (repair run — " + res.contactsUpdated +
          " contact(s)" +
          (res.clientProfileUpdated ? ", client profile" : "") +
          (res.accountUpdated ? ", account" : "") + " re-homed)."
        : "Assigned “" + (eng.name || "engagement") + "” to " + res.mentorName +
          " — status now Pending Acceptance (" + res.contactsUpdated + " contact(s)" +
          (res.clientProfileUpdated ? ", client profile" : "") +
          (res.accountUpdated ? ", account" : "") + " reassigned).";
      var errs = res.reassignmentErrors || [];
      if (errs.length) {
        // The engagement WAS assigned, but some related records didn't re-home —
        // tell the staffer exactly which, so they can fix them in the CRM.
        notice(
          summary + " ⚠ " + errs.length + " related record(s) could not be reassigned: " +
          errs.map(function (e) { return e.entity; }).join(", ") +
          ". The assignment itself succeeded; reassign those records in the CRM.",
          "error"
        );
      } else {
        notice(summary, "success");
      }
      // Offer the assignment-notice email to the mentor: the standard compose
      // dialog, To = the mentor's CBM address, with the MentorAssignmentNotice
      // template pre-applied. Best-effort — a missing/erroring template just
      // leaves the blank compose, and when app-sending is unavailable
      // (Gmail integration off / no mailbox) nothing opens.
      if (window.CBMQuickMail) {
        var mentor = mentors.filter(function (m) { return m.id === mentorProfileId; })[0];
        CBMQuickMail.composeIfEnabled(
          (mentor && mentor.cbmEmail) || "",
          { template: "MentorAssignmentNotice" }
        );
      }
    } catch (e) {
      tr.classList.remove("row-busy");
      if (e.status === 401) { showLogin(); return; }
      if (e.status === 400) {
        // Rejected as stale (already assigned / no longer Submitted) or an
        // ineligible mentor — re-fetch so this grid stops showing the old state.
        try { await reloadEngagements(); } catch (_) { /* keep the error notice */ }
      }
      notice(e.message, "error");
    }
  }

  // --- Reassign Mentor -------------------------------------------------------

  function rowFor(engId) {
    return document.querySelector('#engBody tr[data-eng-id="' + engId + '"]');
  }

  // The toolbar button acts on the selected row; never disabled — a click
  // without the needed state explains itself (Doug's ruling).
  $("reassignBtn").addEventListener("click", function () {
    var eng = selectedEngagement();
    if (!eng) {
      notice("Click an engagement row to select it, then press Reassign Mentor "
        + "(or right-click the row).", "error");
      return;
    }
    if (!eng.mentorId) {
      notice("“" + (eng.name || "This engagement") + "” has no mentor yet — "
        + "use its Assign dropdown (or right-click → Assign mentor) instead.", "error");
      return;
    }
    openMentorPicker(rowFor(eng.id), eng, "reassign");
  });

  // Mentor picker dialog (assign for unassigned rows, reassign for assigned).
  function openMentorPicker(tr, eng, mode) {
    var overlay = document.createElement("div");
    overlay.className = "modal-overlay"; overlay.id = "mentorPickModal";
    var card = document.createElement("div"); card.className = "modal-card";

    var h = document.createElement("h3");
    h.textContent = (mode === "reassign" ? "Reassign" : "Assign") + " “" +
      (eng.name || "this engagement") + "”";
    card.appendChild(h);
    var p = document.createElement("p");
    p.textContent = mode === "reassign"
      ? "Current mentor: " + (eng.mentorName || "unknown") + ". Choose the new " +
        "primary mentor — the engagement, its contacts, client records, and " +
        "sessions all move to them, and the change is recorded in the " +
        "engagement's history."
      : "Choose the mentor for this engagement.";
    card.appendChild(p);

    var select = document.createElement("select");
    select.className = "mentor-pick-select";
    select.appendChild(new Option("Select a mentor…", ""));
    mentors.forEach(function (m) {
      if (mode === "reassign" && m.id === eng.mentorId) return;
      var label = m.name;
      if (typeof m.availableCapacity === "number" && m.availableCapacity >= 0) {
        label += " (capacity " + m.availableCapacity + ")";
      }
      select.appendChild(new Option(label, m.id));
    });
    card.appendChild(select);

    var err = document.createElement("p");
    err.className = "form-error"; err.hidden = true;
    card.appendChild(err);

    var actions = document.createElement("div"); actions.className = "modal-actions";
    var cancel = document.createElement("button"); cancel.type = "button";
    cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
    var ok = document.createElement("button"); ok.type = "button";
    ok.className = "cbm-button";
    ok.textContent = mode === "reassign" ? "Reassign" : "Assign";
    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    cancel.addEventListener("click", close);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
    ok.addEventListener("click", function () {
      if (!select.value) {
        err.textContent = "Select a mentor first.";
        err.hidden = false;
        select.focus();
        return;
      }
      var mentorId = select.value;
      close();
      if (mode === "reassign") performReassign(tr, eng, mentorId);
      else performAssign(tr, eng, mentorId);
    });
    actions.appendChild(cancel); actions.appendChild(ok); card.appendChild(actions);
    overlay.appendChild(card); document.body.appendChild(overlay);
    select.focus();
  }

  async function performReassign(tr, eng, mentorProfileId) {
    clearNotice();
    if (tr) tr.classList.add("row-busy");
    try {
      var res = await api("/engagements/" + encodeURIComponent(eng.id) + "/reassign", {
        method: "POST",
        body: JSON.stringify({ mentorProfileId: mentorProfileId }),
      });
      await reloadEngagements();
      var summary =
        "Reassigned “" + (eng.name || "engagement") + "” from " +
        (res.oldMentorName || "the previous mentor") + " to " + res.mentorName +
        " (" + res.contactsUpdated + " contact(s)" +
        (res.clientProfileUpdated ? ", client profile" : "") +
        (res.accountUpdated ? ", company" : "") +
        ", " + res.sessionsUpdated + " of " + res.sessionsTotal + " session(s) moved).";
      var errs = res.reassignmentErrors || [];
      if (errs.length) {
        notice(
          summary + " ⚠ " + errs.length + " related record(s) could not be re-homed: " +
          errs.map(function (e) { return e.entity; }).join(", ") +
          ". The mentor change itself succeeded; fix those records in the CRM.",
          "error"
        );
      } else {
        notice(summary, "success");
      }
      // Same follow-up as an initial assignment: offer the assignment-notice
      // email to the NEW mentor (silent fallbacks — see performAssign).
      if (window.CBMQuickMail) {
        var mentor = mentors.filter(function (m) { return m.id === mentorProfileId; })[0];
        CBMQuickMail.composeIfEnabled(
          (mentor && mentor.cbmEmail) || "",
          { template: "MentorAssignmentNotice" }
        );
      }
    } catch (e) {
      if (tr) tr.classList.remove("row-busy");
      if (e.status === 401) { showLogin(); return; }
      if (e.status === 400) {
        try { await reloadEngagements(); } catch (_) { /* keep the error notice */ }
      }
      notice(e.message, "error");
    }
  }

  // --- row context menu ------------------------------------------------------
  // Right-click covers everything the buttons can do for a row.
  function rowMenuItems(tr, eng) {
    var items = [
      { label: "View details", action: function () { openDetail(eng.id); } },
    ];
    if (eng.mentorId) {
      items.push({
        label: "Reassign mentor…",
        action: function () { openMentorPicker(tr, eng, "reassign"); },
      });
    } else {
      items.push({
        label: "Assign mentor…",
        action: function () { openMentorPicker(tr, eng, "assign"); },
      });
    }
    items.push({
      label: "Edit notes",
      action: function () {
        var view = tr.querySelector(".notes-view");
        if (view) view.click();
      },
    });
    items.push({ label: "Refresh list", action: loadData });
    return items;
  }

  function closeContextMenu() {
    var m = document.getElementById("ctxMenu");
    if (m) m.remove();
  }

  function showContextMenu(x, y, items) {
    closeContextMenu();
    var menu = document.createElement("div");
    menu.id = "ctxMenu"; menu.className = "ctx-menu";
    menu.setAttribute("role", "menu");
    items.forEach(function (it) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "ctx-menu__item";
      b.setAttribute("role", "menuitem");
      b.textContent = it.label;
      b.addEventListener("click", function () { closeContextMenu(); it.action(); });
      menu.appendChild(b);
    });
    document.body.appendChild(menu);
    // Keep the menu inside the viewport.
    var mw = menu.offsetWidth, mh = menu.offsetHeight;
    menu.style.left = Math.min(x, window.innerWidth - mw - 8) + "px";
    menu.style.top = Math.min(y, window.innerHeight - mh - 8) + "px";
  }

  document.addEventListener("click", closeContextMenu);
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeContextMenu();
  });

  // Styled confirm dialog — matches the modal-card popups used elsewhere in the
  // app (e.g. Mentor Administration) instead of the browser's native confirm().
  function showConfirmModal(opts, onConfirm) {
    var prev = document.getElementById("confirmModal");
    if (prev) prev.remove();
    var overlay = document.createElement("div");
    overlay.id = "confirmModal"; overlay.className = "modal-overlay";
    var card = document.createElement("div"); card.className = "modal-card";
    var h = document.createElement("h3"); h.textContent = opts.title; card.appendChild(h);
    if (opts.body) { var p = document.createElement("p"); p.textContent = opts.body; card.appendChild(p); }
    var actions = document.createElement("div"); actions.className = "modal-actions";
    var cancel = document.createElement("button"); cancel.type = "button";
    cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = opts.cancelLabel || "Cancel";
    var ok = document.createElement("button"); ok.type = "button";
    ok.className = "cbm-button"; ok.textContent = opts.confirmLabel || "Confirm";
    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    cancel.addEventListener("click", close);
    ok.addEventListener("click", function () { close(); onConfirm(); });
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
    actions.appendChild(cancel); actions.appendChild(ok); card.appendChild(actions);
    overlay.appendChild(card); document.body.appendChild(overlay);
    ok.focus();
  }

  // --- boot ---
  (async function init() {
    try {
      var user = await api("/session");
      showDashboard(user);
    } catch (e) {
      bootFail(e);
    }
  })();
})();
