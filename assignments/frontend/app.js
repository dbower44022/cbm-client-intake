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

  // --- data + rendering ---
  async function loadData() {
    clearNotice();
    show($("loadingState"));
    hide($("engTable"));
    hide($("emptyState"));
    try {
      var results = await Promise.all([api("/mentors"), api("/engagements")]);
      mentors = results[0].mentors || [];
      renderTable(results[1].engagements || []);
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
    var meta = document.createElement("span");
    meta.className = "eng-meta";
    var bits = [];
    if (eng.clientName) bits.push(eng.clientName);
    if (eng.contactName) bits.push(eng.contactName);
    if (eng.createdAt) bits.push("submitted " + eng.createdAt.slice(0, 10));
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
      tr.remove();
      if (!$("engBody").children.length) {
        hide($("engTable"));
        show($("emptyState"));
      }
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
