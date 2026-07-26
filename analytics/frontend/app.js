/* Analytics app (Phase A viewer + Phase B authoring). Vanilla JS, no build.
 * Viewer: the code-seeded + authored system pages with the four CBMCharts
 * renderers, a time-range selector, and Refresh. Manage (admins/authors):
 * a metric builder + a page composer over /analytics/api/admin/*.
 */
(function () {
  "use strict";

  var API = "/analytics/api";
  var RANGE_LABELS = {
    last7d: "Last 7 days", last30d: "Last 30 days", last90d: "Last 90 days",
    quarter: "This quarter", ytd: "Year to date", last12mo: "Last 12 months",
    all: "All time",
  };
  var SHAPE_BY_KIND = { count: "scalar", sum: "scalar", avg: "scalar",
    group_by: "breakdown", bucket: "series", list: "rows" };
  var KIND_OPTS = [["count", "Count of records"], ["sum", "Sum of a field"],
    ["avg", "Average of a field"], ["group_by", "Group by a field"],
    ["bucket", "Over time (monthly)"], ["list", "List of records"]];
  var VIZ_BY_SHAPE = { scalar: [["stat", "Number"]],
    series: [["line", "Line"], ["area", "Area"], ["bar", "Bars"]],
    breakdown: [["bar", "Bars"], ["pie", "Pie"]], rows: [["table", "Table"]] };
  var OPERATORS = [["equals", "="], ["notEquals", "≠"], ["in", "in (comma list)"],
    ["greaterThan", ">"], ["lessThan", "<"],
    ["relativeAfter", "in the last…"], ["relativeBefore", "older than…"],
    ["isNull", "is empty"], ["isNotNull", "is not empty"]];
  var REL_OPS = { relativeAfter: 1, relativeBefore: 1 };
  var DATE_UNITS = [["day", "days"], ["week", "weeks"], ["month", "months"]];

  var $ = function (id) { return document.getElementById(id); };
  var state = { crmUrl: null, pages: [], pageKey: null, range: null,
    canAuthor: false, authoringAvailable: false, metricShapes: {}, allMetrics: [] };

  function show(node, on) { if (node) node.hidden = !on; }

  function h(tag, props) {
    var e = document.createElement(tag);
    props = props || {};
    for (var k in props) {
      if (!props.hasOwnProperty(k) || props[k] == null) continue;
      if (k === "class") e.className = props[k];
      else if (k === "html") e.innerHTML = props[k];
      else if (k === "text") e.textContent = props[k];
      else if (k.slice(0, 2) === "on") e[k.toLowerCase()] = props[k];
      else e.setAttribute(k, props[k]);
    }
    for (var i = 2; i < arguments.length; i++) {
      var kids = arguments[i];
      (Array.isArray(kids) ? kids : [kids]).forEach(function (c) {
        if (c == null) return;
        e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      });
    }
    return e;
  }
  function opt(v, label, sel) { var o = h("option", { value: v }, label); if (sel) o.selected = true; return o; }

  function fail(msg) { show($("dashView"), false); show($("manageView"), false); show($("msgView"), true); $("msgText").textContent = msg; }
  function notice(msg) { var n = $("notice"); if (!msg) { show(n, false); return; } n.textContent = msg; show(n, true); }

  async function api(path, opts) {
    var r = await (window.CBMBusy ? CBMBusy.fetch(API + path, opts) : fetch(API + path, opts));
    if (r.status === 401) { location.href = "/?next=/analytics/"; throw new Error("unauth"); }
    var body = null;
    try { body = await r.json(); } catch (e) { /* non-JSON */ }
    if (!r.ok) throw new Error((body && body.detail) || ("Request failed (" + r.status + ")"));
    return body;
  }
  function jsonBody(obj) { return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) }; }

  function fmtWhen(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  // ========================================================================
  // Viewer
  // ========================================================================
  function renderTabs() {
    var tabs = $("pageTabs"); tabs.innerHTML = "";
    if (state.pages.length < 2) { show(tabs, false); return; }
    show(tabs, true);
    state.pages.forEach(function (p) {
      tabs.appendChild(h("button", {
        class: "an__tab" + (p.key === state.pageKey ? " is-active" : ""),
        role: "tab", onClick: function () { state.pageKey = p.key; loadPage(); },
      }, p.title));
    });
  }
  function renderRangeSelect(tr) {
    var sel = $("rangeSelect"); sel.innerHTML = "";
    (tr.presets || []).forEach(function (key) { sel.appendChild(opt(key, RANGE_LABELS[key] || key, key === tr.key)); });
    state.range = tr.key;
  }
  function panelCard(panel) {
    var span = Math.max(3, Math.min(12, panel.width || 4));
    var meta = "", res = panel.result || {};
    if (!res.error) meta = res.cached ? "as of " + fmtWhen(res.computedAt) : "live";
    var body = h("div", { class: "an-panel__body" });
    var art = h("article", { class: "an-panel" },
      h("header", { class: "an-panel__head" }, h("h3", {}, panel.title), h("span", { class: "an-panel__meta" }, meta)),
      body);
    art.style.setProperty("--span", span);
    try { CBMCharts.renderPanel(body, panel, { crmUrl: state.crmUrl }); }
    catch (e) { body.innerHTML = '<p class="anc-err">Could not render this panel.</p>'; }
    return art;
  }
  function renderPanels(body) {
    var grid = $("panelGrid"); grid.innerHTML = "";
    $("pageSubtitle").textContent = (body.page && body.page.subtitle) || "";
    (body.panels || []).forEach(function (p) { grid.appendChild(panelCard(p)); });
    if (!(body.panels || []).length) grid.innerHTML = '<p class="an__empty">No panels on this page yet.</p>';
  }
  async function loadPage(force) {
    if (!state.pageKey) return;
    show($("loadingState"), true); notice(""); renderTabs();
    try {
      var qs = state.range ? "?range=" + encodeURIComponent(state.range) : "";
      var body = force ? await api("/pages/" + state.pageKey + "/refresh" + qs, { method: "POST" })
        : await api("/pages/" + state.pageKey + qs);
      renderRangeSelect(body.timeRange); renderPanels(body);
    } catch (e) { if (e.message !== "unauth") notice(e.message); }
    finally { show($("loadingState"), false); }
  }
  async function reloadPageList() {
    try { state.pages = (await api("/pages")).pages || []; } catch (e) { /* keep */ }
    if (state.pages.length && !state.pages.some(function (p) { return p.key === state.pageKey; }))
      state.pageKey = state.pages[0].key;
  }

  // ========================================================================
  // Manage (Phase B authoring)
  // ========================================================================
  function showManage() {
    show($("dashView"), false); show($("manageView"), true);
    switchMTab("metrics");
  }
  function showViewer() {
    show($("manageView"), false); show($("dashView"), true);
    reloadPageList().then(function () { renderTabs(); loadPage(); });
  }
  function switchMTab(tab) {
    document.querySelectorAll(".an__mtab").forEach(function (b) { b.classList.toggle("is-active", b.dataset.mtab === tab); });
    show($("mPanelMetrics"), tab === "metrics"); show($("mPanelPages"), tab === "pages");
    if (tab === "metrics") loadMetrics(); else loadPagesAdmin();
  }

  // --- metrics list ---
  async function loadMetrics() {
    var host = $("metricList"); host.innerHTML = "Loading…";
    var data;
    try { data = await api("/admin/metrics"); } catch (e) { host.innerHTML = ""; host.appendChild(h("p", { class: "an__empty" }, e.message)); return; }
    state.metricShapes = {}; state.allMetrics = [];
    (data.builtins || []).forEach(function (m) { state.metricShapes[m.key] = m.result_shape; state.allMetrics.push({ key: m.key, name: m.name, builtin: true, applies_to: m.applies_to || ["system"] }); });
    (data.metrics || []).forEach(function (m) { state.metricShapes[m.key] = m.result_shape; state.allMetrics.push({ key: m.key, name: m.name, applies_to: m.applies_to || ["system"] }); });
    state.recordTypes = data.recordTypes || [];
    host.innerHTML = "";
    var table = h("table", { class: "an__mtable" }, h("thead", {}, h("tr", {},
      h("th", {}, "Name"), h("th", {}, "Key"), h("th", {}, "Shape"), h("th", {}, "Used by"), h("th", {}, ""))));
    var tb = h("tbody");
    (data.metrics || []).forEach(function (m) {
      tb.appendChild(h("tr", {},
        h("td", {}, m.name), h("td", { class: "an__mono" }, m.key), h("td", {}, m.result_shape),
        h("td", {}, (m.usedBy || []).join(", ") || "—"),
        h("td", { class: "an__row-actions" },
          h("button", { class: "an__link-btn", onClick: function () { openMetricEditor(m); } }, "Edit"),
          h("button", { class: "an__link-btn an__danger", onClick: function () { deleteMetric(m); } }, "Delete"))));
    });
    (data.builtins || []).forEach(function (m) {
      tb.appendChild(h("tr", { class: "an__builtin" },
        h("td", {}, m.name), h("td", { class: "an__mono" }, m.key), h("td", {}, m.result_shape),
        h("td", {}, "—"), h("td", {}, h("span", { class: "an__tag" }, "built-in"))));
    });
    table.appendChild(tb); host.appendChild(table);
    if (!(data.metrics || []).length) host.appendChild(h("p", { class: "an__hint" }, "No custom metrics yet — create one to build a panel."));
  }

  async function deleteMetric(m) {
    if (!confirm('Delete metric "' + m.name + '"?')) return;
    try { await api("/admin/metrics/" + m.id, { method: "DELETE" }); loadMetrics(); }
    catch (e) { alert(e.message); }
  }

  // --- metric editor ---
  function openMetricEditor(metric) {
    var editing = !!metric;
    var def = (metric && metric.definition) || {};
    var agg = def.aggregation || {};
    var fieldsCache = {};
    var form = h("div", { class: "an__form" });

    var nameInput = h("input", { type: "text", value: (metric && metric.name) || "", placeholder: "e.g. Active partners" });
    var entitySel = h("select", {});
    var kindSel = h("select", {});
    KIND_OPTS.forEach(function (k) { kindSel.appendChild(opt(k[0], k[1], agg.kind === k[0])); });
    var fieldWrap = h("div", { class: "an__field-row" });
    var fieldSel = h("select", {});
    var filtersHost = h("div", { class: "an__filters" });
    var vizSel = h("select", {});
    var cacheSel = h("select", {}, opt("cached", "Cached (refreshed hourly)", (metric && metric.cache_mode) !== "live"), opt("live", "Live (every view)", (metric && metric.cache_mode) === "live"));
    var linksCache = {};
    var appliesHost = h("div", { class: "an__applies" });
    var ctxInput = h("input", { type: "text", list: "anCtxList", value: (metric && metric.context_param) || "", placeholder: "e.g. mentorProfileId" });
    var ctxList = h("datalist", { id: "anCtxList" });
    var ctxWrap = h("div", { class: "an__field-row" }, h("label", { class: "an__field-label" }, "Record link field"),
      h("span", { class: "an__hint" }, "The field that equals the record's id (for record-scoped metrics)."), ctxInput, ctxList);
    var previewHost = h("div", { class: "an__preview" });

    function chosenApplies() {
      var out = [];
      appliesHost.querySelectorAll("input[type=checkbox]:checked").forEach(function (cb) { out.push(cb.value); });
      return out.length ? out : ["system"];
    }
    function syncCtx() { show(ctxWrap, chosenApplies().some(function (a) { return a !== "system"; })); }

    function fieldOptions(kind) {
      var flds = fieldsCache[entitySel.value] || [];
      if (kind === "sum" || kind === "avg") return flds.filter(function (f) { return f.numeric; });
      if (kind === "bucket") return flds.filter(function (f) { return f.date; });
      return flds; // group_by: any
    }
    function refreshFieldSel() {
      var kind = kindSel.value;
      var needs = ["sum", "avg", "group_by", "bucket"].indexOf(kind) >= 0;
      show(fieldWrap, needs);
      fieldSel.innerHTML = "";
      if (!needs) return;
      var chosen = agg.field || def.time_field;
      fieldOptions(kind).forEach(function (f) { fieldSel.appendChild(opt(f.name, f.label + " (" + f.type + ")", f.name === chosen)); });
      fieldWrap.querySelector(".an__field-label").textContent = kind === "bucket" ? "Date field" : (kind === "group_by" ? "Group by field" : "Numeric field");
    }
    function refreshViz() {
      var shape = SHAPE_BY_KIND[kindSel.value];
      vizSel.innerHTML = "";
      (VIZ_BY_SHAPE[shape] || []).forEach(function (v) { vizSel.appendChild(opt(v[0], v[1], (metric && metric.default_viz) === v[0])); });
    }
    async function loadFields() {
      var ent = entitySel.value;
      if (!fieldsCache[ent]) {
        try {
          var resp = await api("/admin/fields?entity=" + encodeURIComponent(ent));
          fieldsCache[ent] = resp.fields || []; linksCache[ent] = resp.links || [];
        } catch (e) { fieldsCache[ent] = []; linksCache[ent] = []; notice(e.message); }
      }
      refreshFieldSel();
      // context-param datalist (belongsTo link ids)
      ctxList.innerHTML = "";
      (linksCache[ent] || []).forEach(function (ln) { ctxList.appendChild(opt(ln.param, ln.label + " → " + ln.foreign)); });
      // rebuild filter field selects
      filtersHost.querySelectorAll("select.an__f-field").forEach(function (sel) {
        var cur = sel.value; sel.innerHTML = "";
        (fieldsCache[ent] || []).forEach(function (f) { sel.appendChild(opt(f.name, f.label, f.name === cur)); });
      });
    }

    function filterRow(clause) {
      clause = clause || {};
      var fsel = h("select", { class: "an__f-field" });
      (fieldsCache[entitySel.value] || []).forEach(function (f) { fsel.appendChild(opt(f.name, f.label, f.name === clause.attribute)); });
      var osel = h("select", { class: "an__f-op" });
      OPERATORS.forEach(function (o) { osel.appendChild(opt(o[0], o[1], o[0] === clause.type)); });
      var val = h("input", { type: "text", class: "an__f-val", value: Array.isArray(clause.value) ? clause.value.join(", ") : (clause.value != null ? clause.value : "") });
      var usel = h("select", { class: "an__f-unit" });
      DATE_UNITS.forEach(function (u) { usel.appendChild(opt(u[0], u[1], u[0] === clause.unit)); });
      var valWrap = h("span", { class: "an__f-valwrap" }, val, usel);
      function syncVal() {
        var op = osel.value;
        var rel = !!REL_OPS[op];
        var noVal = op === "isNull" || op === "isNotNull";
        valWrap.style.visibility = noVal ? "hidden" : "visible";
        usel.style.display = rel ? "" : "none";
        val.type = rel ? "number" : "text";
        if (rel && !val.value) val.value = "30";
      }
      osel.onchange = syncVal; syncVal();
      var row = h("div", { class: "an__filter" }, fsel, osel, valWrap, h("button", { class: "an__link-btn an__danger", onClick: function () { row.remove(); } }, "×"));
      return row;
    }

    function collectDefinition() {
      var kind = kindSel.value;
      var filters = [];
      filtersHost.querySelectorAll(".an__filter").forEach(function (row) {
        var attr = row.querySelector(".an__f-field").value;
        var type = row.querySelector(".an__f-op").value;
        var raw = row.querySelector(".an__f-val").value;
        var clause = { type: type, attribute: attr };
        if (type === "in") clause.value = raw.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
        else if (REL_OPS[type]) {
          clause.value = parseInt(raw, 10) || 0;
          clause.unit = row.querySelector(".an__f-unit").value;
        }
        else if (type !== "isNull" && type !== "isNotNull") clause.value = raw;
        filters.push(clause);
      });
      var aggregation = { kind: kind };
      if (["sum", "avg", "group_by"].indexOf(kind) >= 0) aggregation.field = fieldSel.value;
      var definition = { filters: filters, aggregation: aggregation };
      if (kind === "bucket") definition.time_field = fieldSel.value || "createdAt";
      return definition;
    }
    function payload() {
      return { name: nameInput.value.trim(), entity: entitySel.value, definition: collectDefinition(),
        default_viz: vizSel.value, cache_mode: cacheSel.value,
        applies_to: chosenApplies(), context_param: ctxInput.value.trim() || null };
    }

    async function preview() {
      previewHost.innerHTML = "Computing…";
      try {
        var out = await api("/admin/preview", jsonBody({ entity: entitySel.value, definition: collectDefinition() }));
        previewHost.innerHTML = "";
        CBMCharts.renderPanel(previewHost, { viz: vizSel.value, result: out.result }, { crmUrl: state.crmUrl });
      } catch (e) { previewHost.innerHTML = ""; previewHost.appendChild(h("p", { class: "anc-err" }, e.message)); }
    }
    async function save() {
      var p = payload();
      if (!p.name) { notice("Give the metric a name."); return; }
      try {
        await api(editing ? "/admin/metrics/" + metric.id : "/admin/metrics", editing ? { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) } : jsonBody(p));
        closeModal(); loadMetrics();
      } catch (e) { notice(e.message); }
    }

    // assemble
    form.appendChild(labeled("Name", nameInput));
    form.appendChild(labeled("Record type", entitySel));
    form.appendChild(labeled("Measure", kindSel));
    fieldWrap.appendChild(h("label", { class: "an__field-label" }, "Field"));
    fieldWrap.appendChild(fieldSel);
    form.appendChild(fieldWrap);
    var filtersBox = h("div", {}, h("div", { class: "an__form-label" }, "Filters"), filtersHost,
      h("button", { class: "an__link-btn", onClick: function () { filtersHost.appendChild(filterRow()); } }, "+ Add filter"));
    form.appendChild(filtersBox);
    form.appendChild(labeled("Show as", vizSel));
    form.appendChild(labeled("Data freshness", cacheSel));
    form.appendChild(h("div", { class: "an__form-label" }, "Applies to"));
    form.appendChild(appliesHost);
    form.appendChild(ctxWrap);
    form.appendChild(h("div", { class: "an__form-label" }, "Preview"));
    form.appendChild(previewHost);

    kindSel.onchange = function () { refreshFieldSel(); refreshViz(); };
    entitySel.onchange = loadFields;

    // load entities, build the applies-to checkboxes, then fields + filters
    api("/admin/entities").then(function (d) {
      (d.entities || []).forEach(function (e) { entitySel.appendChild(opt(e.entity, e.label, metric && metric.entity === e.entity)); });
      if (!metric) entitySel.value = (d.entities[0] || {}).entity;
      var applies = [{ v: "system", l: "System (org-wide)" }].concat((d.entities || []).map(function (e) { return { v: e.entity, l: e.label }; }));
      var cur = (metric && metric.applies_to) || ["system"];
      applies.forEach(function (o) {
        var cb = h("input", { type: "checkbox", value: o.v });
        if (cur.indexOf(o.v) >= 0) cb.checked = true;
        cb.onchange = syncCtx;
        appliesHost.appendChild(h("label", { class: "an__chk" }, cb, h("span", {}, o.l)));
      });
      syncCtx();
      return loadFields();
    }).then(function () {
      (def.filters || []).forEach(function (cl) { filtersHost.appendChild(filterRow(cl)); });
      refreshFieldSel(); refreshViz();
    });

    openModal(editing ? "Edit metric" : "New metric", form, [
      h("button", { class: "cbm-button cbm-button--secondary", onClick: preview }, "Preview"),
      h("button", { class: "cbm-button", onClick: save }, "Save metric"),
    ]);
  }

  // --- pages list ---
  async function loadPagesAdmin() {
    var host = $("pageList"); host.innerHTML = "Loading…";
    // ensure the metric map is populated (for the page editor's viz options)
    if (!state.allMetrics.length) { try { await primeMetrics(); } catch (e) { /* ignore */ } }
    var data;
    try { data = await api("/admin/pages"); } catch (e) { host.innerHTML = ""; host.appendChild(h("p", { class: "an__empty" }, e.message)); return; }
    host.innerHTML = "";
    var table = h("table", { class: "an__mtable" }, h("thead", {}, h("tr", {}, h("th", {}, "Title"), h("th", {}, "Key"), h("th", {}, "Panels"), h("th", {}, ""))));
    var tb = h("tbody");
    (data.pages || []).forEach(function (p) {
      tb.appendChild(h("tr", {},
        h("td", {}, p.title), h("td", { class: "an__mono" }, p.key), h("td", {}, String((p.panels || []).length)),
        h("td", { class: "an__row-actions" },
          h("button", { class: "an__link-btn", onClick: function () { openPageEditor(p); } }, "Edit"),
          h("button", { class: "an__link-btn an__danger", onClick: function () { deletePage(p); } }, "Delete"))));
    });
    (data.builtins || []).forEach(function (p) {
      tb.appendChild(h("tr", { class: "an__builtin" }, h("td", {}, p.title), h("td", { class: "an__mono" }, p.key), h("td", {}, "—"), h("td", {}, h("span", { class: "an__tag" }, "built-in"))));
    });
    table.appendChild(tb); host.appendChild(table);
    if (!(data.pages || []).length) host.appendChild(h("p", { class: "an__hint" }, "No custom pages yet — create one and add panels."));
  }
  async function primeMetrics() {
    var data = await api("/admin/metrics");
    state.metricShapes = {}; state.allMetrics = [];
    (data.builtins || []).concat(data.metrics || []).forEach(function (m) {
      state.metricShapes[m.key] = m.result_shape;
      state.allMetrics.push({ key: m.key, name: m.name, applies_to: m.applies_to || ["system"] });
    });
    state.recordTypes = data.recordTypes || [];
  }
  async function deletePage(p) {
    if (!confirm('Delete page "' + p.title + '"?')) return;
    try { await api("/admin/pages/" + p.id, { method: "DELETE" }); loadPagesAdmin(); } catch (e) { alert(e.message); }
  }

  // --- page editor ---
  function openPageEditor(page) {
    var editing = !!page;
    var form = h("div", { class: "an__form" });
    var titleInput = h("input", { type: "text", value: (page && page.title) || "", placeholder: "e.g. Fundraising" });
    var subInput = h("input", { type: "text", value: (page && page.subtitle) || "", placeholder: "Optional subtitle" });
    var scopeSel = h("select", {});
    var curScope = (page && page.scope) || "system";
    scopeSel.appendChild(opt("system", "System (org-wide dashboard)", curScope === "system"));
    (state.recordTypes || []).forEach(function (rt) { scopeSel.appendChild(opt(rt.entity, "Record tab: " + rt.label, curScope === rt.entity)); });
    function metricsForScope() {
      var s = scopeSel.value;
      return state.allMetrics.filter(function (m) {
        var a = m.applies_to || ["system"];
        return s === "system" ? a.indexOf("system") >= 0 : a.indexOf(s) >= 0;
      });
    }
    function rebuildPanelMetrics() {
      panelsHost.querySelectorAll(".an__p-metric").forEach(function (sel) {
        var cur = sel.value; sel.innerHTML = "";
        metricsForScope().forEach(function (m) { sel.appendChild(opt(m.key, m.name, m.key === cur)); });
        sel.dispatchEvent(new Event("change"));
      });
    }
    scopeSel.onchange = rebuildPanelMetrics;
    var rangeSel = h("select", {});
    var curRange = (page && page.default_range) || "last12mo";
    ["last7d", "last30d", "last90d", "quarter", "ytd", "last12mo", "all"].forEach(function (k) { rangeSel.appendChild(opt(k, RANGE_LABELS[k], curRange === k)); });
    var teamInput = h("input", { type: "text", value: (page && (page.team_gate || []).join(", ")) || "", placeholder: "Teams (comma) — blank = default view team" });
    var portalBox = h("input", { type: "checkbox" });
    if (page && page.portal_dashboard) portalBox.checked = true;
    var portalWrap = h("label", { class: "an__chk" }, portalBox, h("span", {}, "Show this dashboard on the portal home page"));
    function syncPortalOption() { show(portalWrap, scopeSel.value === "system"); }
    scopeSel.addEventListener("change", syncPortalOption);
    var panelsHost = h("div", { class: "an__panels" });

    function panelRow(p) {
      p = p || {};
      var msel = h("select", { class: "an__p-metric" });
      metricsForScope().forEach(function (m) { msel.appendChild(opt(m.key, m.name, m.key === p.metric_key)); });
      var title = h("input", { type: "text", class: "an__p-title", value: p.title || "", placeholder: "Panel title" });
      var vsel = h("select", { class: "an__p-viz" });
      function fillViz() { var shape = state.metricShapes[msel.value] || "scalar"; vsel.innerHTML = ""; (VIZ_BY_SHAPE[shape] || [["stat", "Number"]]).forEach(function (v) { vsel.appendChild(opt(v[0], v[1], v[0] === p.viz)); }); }
      msel.onchange = fillViz; fillViz();
      var width = h("input", { type: "number", class: "an__p-width", min: "3", max: "12", value: p.width || 4, title: "Width (3–12)" });
      var vis = h("input", { type: "text", class: "an__p-vis", value: (p.visibility || []).join(", "), placeholder: "Visible to teams (comma) — blank = all" });
      var row = h("div", { class: "an__panel-row" },
        h("div", { class: "an__panel-grid" },
          labeled("Metric", msel), labeled("Title", title), labeled("Show as", vsel), labeled("Width", width), labeled("Visible to", vis)),
        h("div", { class: "an__panel-ops" },
          h("button", { class: "an__link-btn", title: "Move up", onClick: function () { if (row.previousElementSibling) panelsHost.insertBefore(row, row.previousElementSibling); } }, "↑"),
          h("button", { class: "an__link-btn", title: "Move down", onClick: function () { if (row.nextElementSibling) panelsHost.insertBefore(row.nextElementSibling, row); } }, "↓"),
          h("button", { class: "an__link-btn an__danger", onClick: function () { row.remove(); } }, "Remove")));
      return row;
    }
    function collect() {
      var panels = [];
      panelsHost.querySelectorAll(".an__panel-row").forEach(function (row) {
        panels.push({
          metric_key: row.querySelector(".an__p-metric").value,
          title: row.querySelector(".an__p-title").value,
          viz: row.querySelector(".an__p-viz").value,
          width: parseInt(row.querySelector(".an__p-width").value, 10) || 4,
          visibility: row.querySelector(".an__p-vis").value.split(",").map(function (s) { return s.trim(); }).filter(Boolean),
        });
      });
      return { title: titleInput.value.trim(), subtitle: subInput.value.trim(),
        scope: scopeSel.value, portal_dashboard: portalBox.checked,
        default_range: rangeSel.value, team_gate: teamInput.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean),
        panels: panels };
    }
    async function save() {
      var p = collect();
      if (!p.title) { notice("Give the page a title."); return; }
      if (!p.panels.length) { notice("Add at least one panel."); return; }
      try {
        await api(editing ? "/admin/pages/" + page.id : "/admin/pages", editing ? { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) } : jsonBody(p));
        closeModal(); loadPagesAdmin();
      } catch (e) { notice(e.message); }
    }

    form.appendChild(labeled("Title", titleInput));
    form.appendChild(labeled("Subtitle", subInput));
    form.appendChild(labeled("Where it appears", scopeSel));
    form.appendChild(labeled("Default time range", rangeSel));
    form.appendChild(labeled("Who can view", teamInput));
    form.appendChild(portalWrap);
    syncPortalOption();
    form.appendChild(h("div", { class: "an__form-label" }, "Panels"));
    form.appendChild(panelsHost);
    form.appendChild(h("button", { class: "an__link-btn", onClick: function () { if (!state.allMetrics.length) { notice("Create a metric first."); return; } panelsHost.appendChild(panelRow()); } }, "+ Add panel"));

    (page && page.panels || []).forEach(function (pn) { panelsHost.appendChild(panelRow(pn)); });

    openModal(editing ? "Edit page" : "New page", form, [h("button", { class: "cbm-button", onClick: save }, "Save page")]);
  }

  // --- modal + small helpers ---
  function labeled(label, control) { return h("label", { class: "an__lbl" }, h("span", {}, label), control); }
  function openModal(title, bodyEl, actions) {
    $("editorTitle").textContent = title;
    var body = $("editorBody"); body.innerHTML = ""; body.appendChild(bodyEl);
    var act = $("editorActions"); act.innerHTML = "";
    (actions || []).forEach(function (a) { act.appendChild(a); });
    act.appendChild(h("button", { class: "cbm-button cbm-button--secondary", onClick: closeModal }, "Cancel"));
    show($("editorModal"), true);
  }
  function closeModal() { show($("editorModal"), false); notice(""); }

  // ========================================================================
  // Boot
  // ========================================================================
  async function boot() {
    var session;
    try { session = await api("/session"); }
    catch (e) { if (e.message === "unauth") return; return fail(e.message); }
    state.crmUrl = session.crmUrl;
    state.pages = session.pages || [];
    state.canAuthor = !!session.canAuthor;
    state.authoringAvailable = !!session.authoringAvailable;
    $("whoName").textContent = session.name || session.userName;
    show($("userCorner"), true);

    if (state.canAuthor && state.authoringAvailable) show($("manageBtn"), true);
    $("manageBtn").onclick = showManage;
    $("backToView").onclick = showViewer;
    document.querySelectorAll(".an__mtab").forEach(function (b) { b.onclick = function () { switchMTab(b.dataset.mtab); }; });
    $("newMetricBtn").onclick = function () { openMetricEditor(null); };
    $("newPageBtn").onclick = function () { openPageEditor(null); };
    $("editorBackdrop").onclick = closeModal;
    $("editorClose").onclick = closeModal;
    $("rangeSelect").onchange = function () { state.range = this.value; loadPage(); };
    $("refreshBtn").onclick = function () { loadPage(true); };
    $("logoutBtn").onclick = async function () { try { await api("/logout", { method: "POST" }); } catch (e) {} location.href = "/"; };

    if (!state.pages.length && !(state.canAuthor && state.authoringAvailable)) {
      return fail("You don't have access to any analytics pages yet.");
    }
    show($("dashView"), true);
    if (state.pages.length) { state.pageKey = state.pages[0].key; loadPage(); }
    else { $("panelGrid").innerHTML = '<p class="an__empty">No pages yet — use Manage to create one.</p>'; }
  }

  boot();
})();
