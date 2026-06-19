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
    if (ev.key === "Escape") {
      var details = $("statusFilter");
      if (details && details.open) details.open = false;
    }
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
    try {
      var results = await Promise.all([api("/mentors"), fetchEngagements()]);
      mentors = results[0].mentors || [];
      var eng = results[1];
      selectedStatuses = eng.selectedStatuses || selectedStatuses;
      buildStatusFilter(eng.allStatuses || []);
      renderTable(eng.engagements || []);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
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
    var name = document.createElement("span");
    name.className = "eng-name";
    name.textContent = eng.name || "(unnamed engagement)";
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
      notice(
        "Assigned “" + (eng.name || "engagement") + "” to " + res.mentorName +
        " — status now Pending Acceptance (" + res.contactsUpdated + " contact(s)" +
        (res.clientProfileUpdated ? ", client profile" : "") +
        (res.accountUpdated ? ", account" : "") + " reassigned).",
        "success"
      );
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
      showLogin();
    }
  })();
})();
