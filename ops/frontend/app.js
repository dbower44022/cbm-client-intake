/* Submission Operations console — vanilla JS. Auth + table + re-drive. */
(function () {
  "use strict";

  var API = "/ops/api";
  var STATUSES = ["pending", "processing", "retry", "completed", "needs_attention", "held_honeypot"];
  var FORMS = ["client-intake", "volunteer", "info-request", "partner", "sponsor"];
  var REDRIVABLE = { held_honeypot: 1, needs_attention: 1, retry: 1 };
  var state = { status: "", form: "" };

  function $(id) { return document.getElementById(id); }
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    var resp = await fetch(API + path, opts);
    var data = null;
    try { data = await resp.json(); } catch (e) { /* none */ }
    if (!resp.ok) {
      var msg = (data && data.detail) || ("Request failed (" + resp.status + ")");
      var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function showLogin() { hide($("dashView")); show($("loginView")); $("username").focus(); }
  function showDash(user) { hide($("loginView")); $("whoName").textContent = user.name || user.userName; show($("dashView")); loadData(); }
  function notice(text, kind) { var n = $("notice"); n.textContent = text; n.className = "ops__notice " + (kind === "error" ? "is-error" : "is-success"); show(n); }
  function clearNotice() { hide($("notice")); }

  function fillSelect(sel, values, placeholder) {
    sel.innerHTML = "";
    sel.appendChild(new Option(placeholder, ""));
    values.forEach(function (v) { sel.appendChild(new Option(v, v)); });
  }

  // --- login ---
  $("loginForm").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    hide($("loginError"));
    $("loginBtn").disabled = true;
    try {
      var user = await api("/login", { method: "POST", body: JSON.stringify({ username: $("username").value, password: $("password").value }) });
      $("password").value = "";
      showDash(user);
    } catch (e) {
      var le = $("loginError"); le.textContent = e.message; show(le);
    } finally { $("loginBtn").disabled = false; }
  });
  $("logoutBtn").addEventListener("click", async function () { try { await api("/logout", { method: "POST" }); } catch (e) {} showLogin(); });
  $("refreshBtn").addEventListener("click", loadData);
  $("statusFilter").addEventListener("change", function () { state.status = this.value; loadData(); });
  $("formFilter").addEventListener("change", function () { state.form = this.value; loadData(); });

  // --- data ---
  async function loadData() {
    clearNotice();
    show($("loadingState")); hide($("subTable")); hide($("emptyState"));
    var qs = [];
    if (state.status) qs.push("status=" + encodeURIComponent(state.status));
    if (state.form) qs.push("form=" + encodeURIComponent(state.form));
    try {
      var data = await api("/submissions" + (qs.length ? "?" + qs.join("&") : ""));
      renderCounts(data.counts || {});
      renderTable(data.submissions || []);
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    } finally { hide($("loadingState")); }
  }

  function renderCounts(counts) {
    var box = $("counts"); box.innerHTML = "";
    var total = 0;
    STATUSES.forEach(function (s) {
      var n = counts[s] || 0; total += n;
      if (!n) return;
      var chip = document.createElement("span");
      chip.className = "count-chip status-" + s;
      chip.textContent = s.replace("_", " ") + ": " + n;
      box.appendChild(chip);
    });
    var t = document.createElement("span"); t.className = "count-chip"; t.textContent = "total: " + total; box.appendChild(t);
  }

  function fmtDate(s) {
    if (!s) return "—";
    var d = new Date(s.indexOf("T") < 0 ? s.replace(" ", "T") + "Z" : s);
    return isNaN(d) ? s : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function renderTable(rows) {
    var body = $("subBody"); body.innerHTML = "";
    if (!rows.length) { show($("emptyState")); return; }
    rows.forEach(function (r) { body.appendChild(buildRow(r)); });
    show($("subTable"));
  }

  function cell(text, cls) { var td = document.createElement("td"); if (cls) td.className = cls; td.textContent = text == null ? "—" : text; return td; }

  function buildRow(r) {
    var tr = document.createElement("tr");

    var ref = document.createElement("td");
    var link = document.createElement("button");
    link.type = "button"; link.className = "ref-link";
    link.textContent = (r.id || "").slice(0, 8);
    link.addEventListener("click", function () { openDetail(r.id); });
    ref.appendChild(link);
    tr.appendChild(ref);

    tr.appendChild(cell(r.form_slug));

    var st = document.createElement("td");
    var badge = document.createElement("span");
    badge.className = "status-badge status-" + r.status;
    badge.textContent = (r.status || "").replace("_", " ");
    st.appendChild(badge);
    tr.appendChild(st);

    tr.appendChild(cell(r.email));
    tr.appendChild(cell(fmtDate(r.received_at)));
    tr.appendChild(cell(r.attempt_count, "num"));
    tr.appendChild(cell(r.last_error ? r.last_error.slice(0, 80) : "—", "err"));

    var act = document.createElement("td");
    if (REDRIVABLE[r.status]) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "cbm-button cbm-button--secondary redrive-btn";
      btn.textContent = "Re-drive";
      btn.addEventListener("click", function () { redrive(r); });
      act.appendChild(btn);
    }
    tr.appendChild(act);
    return tr;
  }

  async function redrive(r) {
    if (!window.confirm("Re-drive " + (r.id || "").slice(0, 8) + " (" + r.form_slug + ")? The worker will re-run it.")) return;
    try {
      await api("/submissions/" + encodeURIComponent(r.id) + "/redrive", { method: "POST" });
      notice("Re-queued " + r.id.slice(0, 8) + " — the worker will pick it up.", "success");
      loadData();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    }
  }

  // --- detail modal ---
  function closeModal() { hide($("detailModal")); }
  $("detailModal").addEventListener("click", function (ev) { if (ev.target.hasAttribute("data-close")) closeModal(); });
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !$("detailModal").hidden) closeModal(); });

  function field(label, value) {
    var wrap = document.createElement("div"); wrap.className = "detail-field";
    var h = document.createElement("h3"); h.textContent = label; wrap.appendChild(h);
    var pre = document.createElement("pre"); pre.textContent = value; wrap.appendChild(pre);
    return wrap;
  }

  async function openDetail(id) {
    $("detailTitle").textContent = "Submission " + id.slice(0, 8);
    $("detailBody").textContent = "Loading…";
    show($("detailModal"));
    try {
      var d = await api("/submissions/" + encodeURIComponent(id));
      var body = $("detailBody"); body.innerHTML = "";
      body.appendChild(field("Status", d.status + "  (attempts: " + (d.attempt_count || 0) + ")"));
      if (d.last_error) body.appendChild(field("Last error", d.last_error));
      body.appendChild(field("Payload", JSON.stringify(d.payload, null, 2)));
      if (d.progress) body.appendChild(field("Progress (created so far)", JSON.stringify(d.progress, null, 2)));
      if (d.result) body.appendChild(field("Result", JSON.stringify(d.result, null, 2)));
    } catch (e) {
      if (e.status === 401) { closeModal(); showLogin(); return; }
      $("detailBody").textContent = e.message;
    }
  }

  // --- boot ---
  fillSelect($("statusFilter"), STATUSES, "All statuses");
  fillSelect($("formFilter"), FORMS, "All forms");
  (async function init() {
    try { showDash(await api("/session")); } catch (e) { showLogin(); }
  })();
})();
