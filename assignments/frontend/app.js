/* Mentor assignment dashboard — vanilla JS, no build step.
 *
 * Flow: check session -> show login or dashboard. The dashboard lists Submitted
 * engagements, each with a dropdown of eligible mentors; choosing one and
 * confirming POSTs the assignment, which the server performs as the logged-in
 * EspoCRM user.
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
  function showLogin() {
    hide($("dashView"));
    show($("loginView"));
    $("username").focus();
  }

  // On boot, a 401 just means "not signed in" (show the form silently). A 5xx or
  // network failure means the server is down — say so, rather than implying the
  // user needs to re-authenticate.
  function bootFail(e) {
    showLogin();
    if (!e || !e.status || e.status >= 500) {
      var le = $("loginError");
      le.textContent = "The server isn't responding right now. Please try again in a moment.";
      show(le);
    }
  }

  function showDashboard(user) {
    hide($("loginView"));
    $("whoName").textContent = user.name || user.userName;
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

  // --- login ---
  $("loginForm").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    hide($("loginError"));
    var btn = $("loginBtn");
    btn.disabled = true;
    try {
      var user = await api("/login", {
        method: "POST",
        body: JSON.stringify({ username: $("username").value, password: $("password").value }),
      });
      $("password").value = "";
      showDashboard(user);
    } catch (e) {
      var le = $("loginError");
      le.textContent = e.message;
      show(le);
    } finally {
      btn.disabled = false;
    }
  });

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) { /* ignore */ }
    showLogin();
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

  function updateStatusSummary() {
    var s = $("statusSummary");
    if (!selectedStatuses.length) s.textContent = "Status: none selected";
    else if (selectedStatuses.length <= 2) s.textContent = "Status: " + selectedStatuses.join(", ");
    else s.textContent = "Status: " + selectedStatuses.length + " selected";
  }

  function buildStatusFilter(allStatuses) {
    var panel = $("statusPanel");
    panel.innerHTML = "";
    allStatuses.forEach(function (st) {
      var label = document.createElement("label");
      label.className = "statusfilter__opt";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = st;
      cb.checked = selectedStatuses.indexOf(st) >= 0;
      cb.addEventListener("change", onStatusChange);
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + st));
      panel.appendChild(label);
    });
    statusFilterBuilt = true;
    updateStatusSummary();
  }

  function onStatusChange() {
    var cbs = $("statusPanel").querySelectorAll("input[type=checkbox]");
    selectedStatuses = Array.prototype.filter.call(cbs, function (c) { return c.checked; })
      .map(function (c) { return c.value; });
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

  function renderTable(engagements) {
    var body = $("engBody");
    body.innerHTML = "";
    if (!engagements.length) {
      show($("emptyState"));
      return;
    }
    engagements.forEach(function (eng) { body.appendChild(buildRow(eng)); });
    show($("engTable"));
  }

  function buildRow(eng) {
    var tr = document.createElement("tr");
    tr.dataset.engId = eng.id;

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
    var cell = document.createElement("div");
    cell.className = "assign-cell";

    var select = document.createElement("select");
    select.appendChild(new Option("Select a mentor…", ""));
    mentors.forEach(function (m) {
      var label = m.name;
      if (typeof m.availableCapacity === "number" && m.availableCapacity >= 0) {
        label += " (capacity " + m.availableCapacity + ")";
      }
      select.appendChild(new Option(label, m.id));
    });

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cbm-button";
    btn.textContent = "Assign";
    btn.disabled = true;

    select.addEventListener("change", function () { btn.disabled = !select.value; });
    btn.addEventListener("click", function () {
      doAssign(tr, eng, select.value, select.options[select.selectedIndex].text);
    });

    cell.appendChild(select);
    cell.appendChild(btn);
    tdAssign.appendChild(cell);
    tr.appendChild(tdAssign);
    return tr;
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
    addContactField(left, "Email", c.email, c.email ? "mailto:" + c.email : null);
    addContactField(left, "Phone", c.phone, c.phone ? "tel:" + c.phone : null);

    var right = document.createElement("dl");
    right.className = "contact-dl";
    addContactField(right, "Meeting", d.meetingCadence);
    addContactField(right, "Created", formatDateTime(d.createdAt));

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
  }

  async function openDetail(id) {
    $("modalTitle").textContent = "Loading…";
    $("modalStatus").hidden = true;
    $("modalContact").innerHTML = "";
    $("modalFocus").innerHTML = "";
    $("modalNeeds").textContent = "";
    $("modalNotes").textContent = "";
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
  // Default to Active mentors, most available capacity first (best fit to take a
  // new client); the admin can widen to other statuses.
  var mentorFilter = { q: "", status: "Active", industry: "", focus: "", availOnly: false,
                       sortKey: "availableCapacity", sortDir: -1 };

  function mentorAvail(m) {
    return m.availableCapacity === -1 ? Infinity
      : (typeof m.availableCapacity === "number" ? m.availableCapacity : -Infinity);
  }
  function mentorHasCapacity(m) { return mentorAvail(m) > 0; }

  function mentorHaystack(m) {
    return [m.name, m.industrySector, (m.expertise || []).join(" "),
            (m.focusAreas || []).join(" ")].join(" ").toLowerCase();
  }

  function sortVal(m, k) {
    if (k === "availableCapacity") return mentorAvail(m);
    if (k === "assignedClients") return m.assignedClients == null ? -Infinity : m.assignedClients;
    return (m[k] || "").toString().toLowerCase();
  }

  function distinct(getList) {
    var set = {};
    reviewMentors.forEach(function (m) {
      getList(m).forEach(function (v) { if (v) set[v] = true; });
    });
    return Object.keys(set).sort();
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
      if (mentorFilter.industry && m.industrySector !== mentorFilter.industry) return false;
      if (mentorFilter.focus && (m.focusAreas || []).indexOf(mentorFilter.focus) < 0) return false;
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
      "Showing " + rows.length + " of " + reviewMentors.length + " mentors";
    updateSortIndicators();
  }

  function renderMentorRows(rows) {
    var tb = $("mentorTbody");
    tb.innerHTML = "";
    if (!rows.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 7;
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
      tr.appendChild(cell(m.assignedClients == null ? "—" : String(m.assignedClients), "num"));
      tr.appendChild(cell(m.availableCapacity === -1 ? "Unlimited"
        : (m.availableCapacity == null ? "—" : String(m.availableCapacity)), "num"));
      tr.appendChild(cell(m.industrySector || "—"));
      var exTd = document.createElement("td"); exTd.appendChild(chipRow(m.expertise)); tr.appendChild(exTd);
      var faTd = document.createElement("td"); faTd.appendChild(chipRow(m.focusAreas)); tr.appendChild(faTd);
      tb.appendChild(tr);
    });
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = text;
    return td;
  }

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
        reviewMentors = (await api("/mentors?all=true")).mentors || [];
      }
      fillFilterSelect($("mentorStatusFilter"),
        distinct(function (m) { return [m.status]; }), "All statuses");
      // Reflect the default/persisted status filter in the dropdown.
      $("mentorStatusFilter").value = mentorFilter.status;
      fillFilterSelect($("mentorIndustryFilter"),
        distinct(function (m) { return [m.industrySector]; }), "All industries");
      fillFilterSelect($("mentorFocusFilter"),
        distinct(function (m) { return m.focusAreas || []; }), "All focus areas");
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
  $("mentorIndustryFilter").addEventListener("change", function () {
    mentorFilter.industry = this.value; applyMentorFilter();
  });
  $("mentorFocusFilter").addEventListener("change", function () {
    mentorFilter.focus = this.value; applyMentorFilter();
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
          mentorFilter.sortDir = (key === "name" || key === "industrySector") ? 1 : -1;
        }
        applyMentorFilter();
      });
    }
  );

  async function doAssign(tr, eng, mentorProfileId, mentorLabel) {
    if (!mentorProfileId) return;
    var ok = window.confirm(
      "Assign \"" + (eng.name || "this engagement") + "\" to " + mentorLabel + "?\n\n" +
      "This sets the engagement to “Pending Acceptance” and reassigns its " +
      "contact(s) and client records to the mentor's user."
    );
    if (!ok) return;

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
      var summary =
        "Assigned “" + (eng.name || "engagement") + "” to " + res.mentorName +
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
    } catch (e) {
      tr.classList.remove("row-busy");
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    }
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
