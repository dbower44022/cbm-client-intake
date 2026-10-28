/* View (build plan § 7e.14): one list's members, in a browser tab of its own.

   Served at /campaigns/lists/{id}/members. The reach summary comes from the
   list's stored counts; the grid pages the members with their reach per
   channel and the extra columns (read as the signed-in user, so the CRM's
   own field rules decide what shows). Filters: reachable by a channel, and
   on a dynamic list the Include group that brought each person in. *Leave
   out…* puts a person on a static exclusion list the dynamic list leaves out
   — the list itself stays a search. Buttons are never disabled. */
(function () {
  "use strict";
  var API = "/campaigns/api";
  var COLS_KEY = "cbm.listMembers.columns";
  var segs = location.pathname.split("/");
  var LIST_ID = decodeURIComponent(segs[3] || "");
  var TYPE_ONE = { lead: "Lead", contact: "Contact", client: "Client", partner: "Partner", funder: "Funder" };
  var COLUMNS = [
    { key: "name", label: "Name", fixed: true },
    { key: "company", label: "Company" },
    { key: "type", label: "Type" },
    { key: "status", label: "Status" },
    { key: "email", label: "Email address" },
    { key: "phone", label: "Phone" },
    { key: "city", label: "City" },
    { key: "rE", label: "Email" },
    { key: "rT", label: "Text" },
    { key: "rP", label: "Post" },
    { key: "by", label: "Brought in by", dynamicOnly: true },
    { key: "activity", label: "Last changed" }
  ];
  var st = { list: null, detail: null, offset: 0, limit: 50, total: 0, q: "", channel: "", group: 0, hidden: {}, lists: [] };
  try { st.hidden = JSON.parse(localStorage.getItem(COLS_KEY) || "{}") || {}; } catch (_) { st.hidden = {}; }

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, content) { var e = document.createElement(tag); if (cls) e.className = cls; if (content != null) e.textContent = content; return e; }
  function num(n) { return n == null ? "—" : Number(n).toLocaleString(); }
  function plural(n, one, many) { return num(n) + " " + (n === 1 ? one : (many || one + "s")); }
  function fmtDate(v) {
    if (!v) return "—";
    var d = new Date(v.length === 19 ? v.replace(" ", "T") + "Z" : v);
    return isNaN(d.getTime()) ? v : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
  function fmtDay(v) {
    if (!v) return "—";
    var d = new Date(v.length === 19 ? v.replace(" ", "T") + "Z" : v);
    return isNaN(d.getTime()) ? v : d.toLocaleDateString([], { dateStyle: "medium" });
  }
  var noticeTimer = null;
  function notice(msg, kind) {
    var n = $("lm_notice");
    n.textContent = msg; n.className = "lm__notice lm__notice--" + (kind || "ok"); n.hidden = false;
    clearTimeout(noticeTimer);
    if (kind !== "error") noticeTimer = setTimeout(function () { n.hidden = true; }, 9000);
  }

  async function api(path, opts) {
    opts = opts || {};
    var ctrl = new AbortController(), waitMs = opts.timeoutMs || 120000;
    var timer = setTimeout(function () { ctrl.abort(); }, waitMs);
    var init = { method: opts.method || "GET", headers: { Accept: "application/json" }, signal: ctrl.signal, credentials: "same-origin" };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    var res;
    try { res = await fetch(API + path, init); }
    catch (e) {
      if (e && e.name === "AbortError") throw new Error("The server did not answer within " + Math.round(waitMs / 1000) + " seconds. It may still be working: wait a minute, then press Refresh.");
      throw new Error("The server could not be reached — check the connection, then try again.");
    }
    finally { clearTimeout(timer); }
    if (res.status === 401) { location.assign("/?next=" + encodeURIComponent(location.pathname)); throw new Error("Signed out"); }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) { var err = new Error((data && data.detail) || ("Request failed (" + res.status + ")")); err.status = res.status; throw err; }
    return data;
  }
  function listPath(suffix) { return "/lists/" + encodeURIComponent(LIST_ID) + (suffix || ""); }
  function isDynamic() { return st.list && st.list.kind === "dynamic"; }

  // --- the list ------------------------------------------------------------------------

  async function loadList() {
    st.detail = await api(listPath());
    st.list = st.detail.list;
    document.title = st.list.name + " — members";
    $("lm_title").textContent = st.list.name;
    var k = $("lm_kind"); k.textContent = isDynamic() ? "Dynamic" : "Static"; k.className = "lm__kind lm__kind--" + st.list.kind;
    $("lm_editLink").href = "/campaigns/#lists?list=" + encodeURIComponent(LIST_ID) + "&edit=1";
    renderSummary();
    renderGroups();
    renderColumnsMenu();
  }

  function renderSummary() {
    var box = $("lm_sum"), l = st.list, c = l.counts;
    box.textContent = "";
    [[c && c.people, "people"], [c && c.email, "by email"], [c && c.text, "by text"], [c && c.postcard, "by postcard"], [c && c.notReachable, "reach nobody"]].forEach(function (f) {
      var s = el("span", "lm__fig"); s.appendChild(el("b", null, num(f[0]))); s.appendChild(document.createTextNode(" " + f[1])); box.appendChild(s);
    });
    box.appendChild(el("span", "lm__grow"));
    box.appendChild(el("span", "lm__small", (l.countedAt ? "Counted " + fmtDate(l.countedAt) + "." : "Not counted yet — press Refresh.") +
      (isDynamic() ? " The list is a search, so it is run again before every send." : " Exactly the people added by hand.")));
  }

  function renderGroups() {
    var wrap = $("lm_groupWrap"), sel = $("lm_group");
    var inc = (st.detail.sentences && st.detail.sentences.include) || [];
    wrap.hidden = !isDynamic() || inc.length < 2;
    sel.textContent = "";
    var all = el("option", null, "Any group"); all.value = "0"; sel.appendChild(all);
    inc.forEach(function (t, i) { var o = el("option", null, "Group " + (i + 1) + ": " + t); o.value = String(i + 1); sel.appendChild(o); });
    sel.value = String(st.group);
  }

  // --- columns ---------------------------------------------------------------------------

  function visibleColumns() {
    return COLUMNS.filter(function (c) { return !st.hidden[c.key] && (!c.dynamicOnly || isDynamic()); });
  }

  function renderColumnsMenu() {
    var menu = $("lm_cols");
    menu.textContent = "";
    COLUMNS.forEach(function (c) {
      if (c.fixed || (c.dynamicOnly && !isDynamic())) return;
      var lab = el("label", "lm__colopt");
      var cb = el("input"); cb.type = "checkbox"; cb.checked = !st.hidden[c.key];
      cb.addEventListener("change", function () {
        if (cb.checked) delete st.hidden[c.key]; else st.hidden[c.key] = true;
        try { localStorage.setItem(COLS_KEY, JSON.stringify(st.hidden)); } catch (_) {}
        loadMembers();
      });
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + c.label));
      menu.appendChild(lab);
    });
  }

  // --- members ---------------------------------------------------------------------------

  async function loadMembers() {
    // A name search reads every member's name, so it is the only time the
    // page asks for the name order; paging otherwise reads one page alone.
    var qs = "?detail=true&offset=" + st.offset + "&limit=" + st.limit +
      (st.q ? "&q=" + encodeURIComponent(st.q) + "&sort=name" : "") +
      (st.channel ? "&channel=" + st.channel : "") + (st.group ? "&group=" + st.group : "");
    try {
      var res = await api(listPath("/members") + qs);
      st.total = res.total;
      renderMembers(res);
    } catch (e) { notice(e.message, "error"); }
  }

  function recordLink(m) {
    if (m.missing) return null;
    if (m.type === "lead") return { href: "/campaigns/lead/" + encodeURIComponent(m.id), target: "cbm-lead-" + m.id };
    if (m.type === "contact") return { href: "/directory/contacts/record/" + encodeURIComponent(m.id), target: "cbm-contact-" + m.id };
    return null;
  }

  function reachCell(reach, letter) {
    if (reach == null) return el("td", "lm__muted", "?");
    return reach.indexOf(letter) >= 0 ? el("td", "lm__yes", "✓") : el("td", "lm__no", "—");
  }

  function renderMembers(res) {
    var cols = visibleColumns(), dynamic = isDynamic(), system = st.list && st.list.system;
    var head = $("lm_head");
    head.textContent = "";
    cols.forEach(function (c) { head.appendChild(el("th", null, c.label)); });
    if (dynamic && !system) { var th = el("th"); th.appendChild(el("span", "lm__sr", "Actions")); head.appendChild(th); }
    var tb = $("lm_rows");
    tb.textContent = "";
    (res.members || []).forEach(function (m) {
      var d = m.details || {}, tr = el("tr");
      cols.forEach(function (c) {
        if (c.key === "name") {
          var td = el("td", m.missing ? "lm__missing" : null), link = recordLink(m);
          if (link) { var a = el("a", null, m.name); a.href = link.href; a.target = link.target; a.rel = "noopener"; td.appendChild(a); }
          else td.textContent = m.name;
          tr.appendChild(td);
        }
        else if (c.key === "type") tr.appendChild(el("td", "lm__muted", TYPE_ONE[m.type] || m.type));
        else if (c.key === "rE") tr.appendChild(reachCell(m.reach, "e"));
        else if (c.key === "rT") tr.appendChild(reachCell(m.reach, "t"));
        else if (c.key === "rP") tr.appendChild(reachCell(m.reach, "p"));
        else if (c.key === "by") { var bt = el("td"); if (m.broughtInBy) bt.appendChild(el("span", "lm__src", m.broughtInBy)); else bt.textContent = "—"; tr.appendChild(bt); }
        else if (c.key === "activity") tr.appendChild(el("td", "lm__muted", d.activity ? fmtDay(d.activity) : "—"));
        else { var v = d[c.key]; tr.appendChild(el("td", c.key === "company" ? null : "lm__muted", v == null || v === "" ? "—" : String(v))); }
      });
      if (dynamic && !system) {
        var act = el("td", "lm__act");
        var b = el("button", "lm__rowbtn", "Leave out…"); b.type = "button";
        b.addEventListener("click", function () { openExclude(m); });
        act.appendChild(b); tr.appendChild(act);
      }
      tb.appendChild(tr);
    });
    var end = Math.min(st.offset + st.limit, res.total);
    $("lm_range").textContent = res.total ? (st.offset + 1) + "–" + end + " of " + num(res.total) : "";
    var empty = $("lm_empty");
    if (!res.total) {
      empty.textContent = st.q ? "No member's name contains \"" + st.q + "\"." : (st.channel || st.group) ? "Nobody on this list matches these filters."
        : res.neverRun ? "Not run yet — press Refresh to see who it holds today." : "Nobody is on this list.";
      empty.hidden = false;
    } else empty.hidden = true;
    var un = $("lm_uncounted");
    un.hidden = !(res.uncounted && st.channel);
    un.textContent = res.uncounted ? plural(res.uncounted, "member has", "members have") + " not been counted since joining, so the channel filter leaves them out. Press Refresh to count them." : "";
  }

  // --- Refresh and Export ---------------------------------------------------------------

  async function refresh() {
    if (st.list.status === "retired") { notice("A retired list is not counted — reactivate it first.", "warn"); return; }
    notice("Counting — a large list takes a minute.", "ok");
    try {
      var res = await api(listPath("/refresh"), { method: "POST", timeoutMs: 300000 });
      var c = res.counts || {};
      notice("Counted: " + plural(c.people, "person", "people") + " — email " + num(c.email) + ", text " + num(c.text) + ", postcard " + num(c.postcard) + ".", "ok");
      await loadList();
      st.offset = 0;
      await loadMembers();
    } catch (e) { notice(e.message, "error"); }
  }

  function exportCsv() {
    if (!st.total && !st.channel && !st.q && !st.group) { notice("Nobody is on this list to export.", "warn"); return; }
    var a = document.createElement("a"); a.href = API + listPath("/export"); a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
    notice("Exporting every member as a CSV file — your browser saves it. The filters on this page do not apply to the file.", "ok");
  }

  // --- Leave out… -------------------------------------------------------------------------

  var excluding = null;

  async function openExclude(m) {
    if (st.list.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    excluding = m;
    try { st.lists = (await api("/lists")).lists || []; } catch (e) { notice(e.message, "error"); return; }
    $("lm_exText").textContent = "Keep " + (m.name || "this person") + " off \"" + st.list.name + "\" by adding them to a static exclusion list this list leaves out. The list itself stays a search.";
    var already = ((st.list.recipe && st.list.recipe.exclude) || []).filter(function (g) { return g.kind === "list"; }).map(function (g) { return g.listId; });
    var opts = st.lists.filter(function (l) { return l.kind === "static" && l.status !== "retired" && l.id !== LIST_ID; })
      .sort(function (a, b) { return (already.indexOf(b.id) >= 0) - (already.indexOf(a.id) >= 0); });
    var sel = $("lm_exTarget");
    sel.textContent = "";
    opts.forEach(function (l) { var o = el("option", null, l.name); o.value = l.id; sel.appendChild(o); });
    var n = el("option", null, "+ New list"); n.value = "__new"; sel.appendChild(n);
    sel.value = opts.length ? opts[0].id : "__new";
    $("lm_exNew").value = st.list.name + " — do not include";
    $("lm_exNewWrap").hidden = sel.value !== "__new";
    $("lm_exMsg").textContent = "";
    $("lm_excludeDlg").showModal();
  }

  async function confirmExclude() {
    var sel = $("lm_exTarget"), payload = { key: excluding.key };
    if (sel.value === "__new") {
      var name = $("lm_exNew").value.trim();
      if (!name) { $("lm_exMsg").textContent = "Name the new exclusion list."; return; }
      payload.newName = name;
    } else payload.targetListId = sel.value;
    try {
      var res = await api(listPath("/exclude"), { method: "POST", body: payload });
      $("lm_excludeDlg").close();
      notice((excluding.name || "The person") + " is on \"" + res.exclusionList.name + "\"" + (res.linked ? ", which this list now leaves out." : " and stays off this list."), "ok");
      await loadList();
      await loadMembers();
    } catch (e) { $("lm_exMsg").textContent = e.message; }
  }

  // --- wiring -------------------------------------------------------------------------

  var qTimer = null;
  $("lm_q").addEventListener("input", function () {
    clearTimeout(qTimer);
    qTimer = setTimeout(function () { st.q = $("lm_q").value.trim(); st.offset = 0; loadMembers(); }, 350);
  });
  Array.prototype.forEach.call(document.querySelectorAll("#lm_channels .lm__chip"), function (b) {
    b.addEventListener("click", function () {
      st.channel = b.getAttribute("data-channel"); st.offset = 0;
      Array.prototype.forEach.call(document.querySelectorAll("#lm_channels .lm__chip"), function (x) {
        var on = x === b; x.classList.toggle("is-on", on); x.setAttribute("aria-pressed", on ? "true" : "false");
      });
      loadMembers();
    });
  });
  $("lm_group").addEventListener("change", function () { st.group = Number($("lm_group").value) || 0; st.offset = 0; loadMembers(); });
  $("lm_colsBtn").addEventListener("click", function () {
    var m = $("lm_cols"); m.hidden = !m.hidden; $("lm_colsBtn").setAttribute("aria-expanded", m.hidden ? "false" : "true");
  });
  document.addEventListener("click", function (e) { if (!$("lm_cols").hidden && !e.target.closest(".lm__menu")) { $("lm_cols").hidden = true; $("lm_colsBtn").setAttribute("aria-expanded", "false"); } });
  $("lm_limit").addEventListener("change", function () { st.limit = Number($("lm_limit").value) || 50; st.offset = 0; loadMembers(); });
  $("lm_prev").addEventListener("click", function () {
    if (st.offset === 0) { notice("This is the first page.", "warn"); return; }
    st.offset = Math.max(0, st.offset - st.limit); loadMembers();
  });
  $("lm_next").addEventListener("click", function () {
    if (st.offset + st.limit >= st.total) { notice("This is the last page.", "warn"); return; }
    st.offset += st.limit; loadMembers();
  });
  $("lm_refreshBtn").addEventListener("click", refresh);
  $("lm_exportBtn").addEventListener("click", exportCsv);
  $("lm_exTarget").addEventListener("change", function () { $("lm_exNewWrap").hidden = $("lm_exTarget").value !== "__new"; });
  $("lm_exCancel").addEventListener("click", function () { $("lm_excludeDlg").close(); });
  $("lm_exOk").addEventListener("click", confirmExclude);

  (async function init() {
    if (!LIST_ID) { notice("This address names no list.", "error"); return; }
    try { await loadList(); } catch (e) { $("lm_title").textContent = "This list could not be opened"; notice(e.message, "error"); return; }
    await loadMembers();
  })();
})();
