/* Analytics app (Analytics Phase A). Vanilla JS, no build step. Signs in via the
 * shared portal session; renders the code-seeded System Analytics page with a
 * time-range selector, per-page Refresh, and the four CBMCharts renderers.
 */
(function () {
  "use strict";

  var API = "/analytics/api";
  var RANGE_LABELS = {
    last7d: "Last 7 days", last30d: "Last 30 days", last90d: "Last 90 days",
    quarter: "This quarter", ytd: "Year to date", last12mo: "Last 12 months",
    all: "All time",
  };

  var $ = function (id) { return document.getElementById(id); };
  var state = { crmUrl: null, pages: [], pageKey: null, range: null };

  function show(node, on) { node.hidden = !on; }

  function fail(msg) {
    show($("dashView"), false);
    show($("msgView"), true);
    $("msgText").textContent = msg;
  }

  function notice(msg) {
    var n = $("notice");
    if (!msg) { show(n, false); return; }
    n.textContent = msg; show(n, true);
  }

  async function api(path, opts) {
    var r = await (window.CBMBusy ? CBMBusy.fetch(API + path, opts) : fetch(API + path, opts));
    if (r.status === 401) { location.href = "/?next=/analytics/"; throw new Error("unauth"); }
    var body = null;
    try { body = await r.json(); } catch (e) { /* non-JSON */ }
    if (!r.ok) {
      var detail = (body && body.detail) || ("Request failed (" + r.status + ")");
      throw new Error(detail);
    }
    return body;
  }

  function fmtWhen(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  }

  // --- rendering -------------------------------------------------------------
  function renderTabs() {
    var tabs = $("pageTabs");
    tabs.innerHTML = "";
    if (state.pages.length < 2) { show(tabs, false); return; }
    show(tabs, true);
    state.pages.forEach(function (p) {
      var b = document.createElement("button");
      b.className = "an__tab" + (p.key === state.pageKey ? " is-active" : "");
      b.textContent = p.title;
      b.setAttribute("role", "tab");
      b.onclick = function () { state.pageKey = p.key; loadPage(); };
      tabs.appendChild(b);
    });
  }

  function renderRangeSelect(timeRange) {
    var sel = $("rangeSelect");
    sel.innerHTML = "";
    (timeRange.presets || []).forEach(function (key) {
      var o = document.createElement("option");
      o.value = key;
      o.textContent = RANGE_LABELS[key] || key;
      if (key === timeRange.key) o.selected = true;
      sel.appendChild(o);
    });
    state.range = timeRange.key;
  }

  function panelCard(panel) {
    var art = document.createElement("article");
    art.className = "an-panel";
    var span = Math.max(3, Math.min(12, panel.width || 4));
    art.style.setProperty("--span", span);

    var head = document.createElement("header");
    head.className = "an-panel__head";
    var h = document.createElement("h3");
    h.textContent = panel.title;
    head.appendChild(h);
    var meta = document.createElement("span");
    meta.className = "an-panel__meta";
    var res = panel.result || {};
    if (res.error) meta.textContent = "";
    else if (res.cached) meta.textContent = "as of " + fmtWhen(res.computedAt);
    else meta.textContent = "live";
    head.appendChild(meta);
    art.appendChild(head);

    var body = document.createElement("div");
    body.className = "an-panel__body";
    art.appendChild(body);
    try {
      CBMCharts.renderPanel(body, panel, { crmUrl: state.crmUrl });
    } catch (e) {
      body.innerHTML = '<p class="anc-err">Could not render this panel.</p>';
    }
    return art;
  }

  function renderPanels(body) {
    var grid = $("panelGrid");
    grid.innerHTML = "";
    $("pageSubtitle").textContent = (body.page && body.page.subtitle) || "";
    (body.panels || []).forEach(function (p) { grid.appendChild(panelCard(p)); });
    if (!(body.panels || []).length) {
      grid.innerHTML = '<p class="an__empty">No panels on this page yet.</p>';
    }
  }

  // --- flows -----------------------------------------------------------------
  async function loadPage(force) {
    if (!state.pageKey) return;
    show($("loadingState"), true);
    notice("");
    renderTabs();
    try {
      var qs = state.range ? "?range=" + encodeURIComponent(state.range) : "";
      var body = force
        ? await api("/pages/" + state.pageKey + "/refresh" + qs, { method: "POST" })
        : await api("/pages/" + state.pageKey + qs);
      renderRangeSelect(body.timeRange);
      renderPanels(body);
    } catch (e) {
      if (e.message !== "unauth") notice(e.message);
    } finally {
      show($("loadingState"), false);
    }
  }

  async function boot() {
    var session;
    try {
      session = await api("/session");
    } catch (e) {
      if (e.message === "unauth") return;
      return fail(e.message);
    }
    state.crmUrl = session.crmUrl;
    state.pages = session.pages || [];
    $("whoName").textContent = session.name || session.userName;
    show($("userCorner"), true);
    if (!state.pages.length) {
      return fail("You don't have access to any analytics pages yet.");
    }
    show($("dashView"), true);
    state.pageKey = state.pages[0].key;

    $("rangeSelect").onchange = function () {
      state.range = this.value; loadPage();
    };
    $("refreshBtn").onclick = function () { loadPage(true); };
    $("logoutBtn").onclick = async function () {
      try { await api("/logout", { method: "POST" }); } catch (e) { /* ignore */ }
      location.href = "/";
    };

    loadPage();
  }

  boot();
})();
