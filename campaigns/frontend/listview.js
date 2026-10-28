/* The Lists tab redesigned (build plan § 7e.14) — one screen per job.

   The list view is what the tab opens on: a search over every list's name
   and notes, filters, and a grid with the full name, type, members, last
   used, updated, the Constant Contact copy and the notes. Preview is a
   switch: the row a click or an arrow key selects shows in a panel on the
   right. Edit replaces the list view on the same page — the settings, and
   who is on the list: the Include and Leave out builder, recounted after
   each change, for a dynamic list; the members, Add people and Remove for a
   static one. View opens the members in a browser tab of its own
   (list-members.html).

   Loaded by index.html before lists.js, which hands this file the tab while
   the session says listScreensOn. Reaches the page only through
   window.CBMMarketing; its element ids are prefixed lv_. Buttons are never
   disabled: each checks on click and says what is missing. */
(function () {
  "use strict";
  var M = window.CBMMarketing;
  if (!M) return;
  var API_BASE = "/campaigns/api";
  var PREVIEW_KEY = "cbm.lists.preview";
  var show = M.show, hide = M.hide, text = M.text, el = M.el, fmtDate = M.fmtDate, notice = M.notice, ask = M.ask;
  function $(id) { return document.getElementById(id); }
  // A run or a count can take minutes: a longer wait than the page's default.
  function api(path, opts) { opts = opts || {}; if (!opts.timeoutMs) opts.timeoutMs = 120000; return M.api(path, opts); }
  function enc(v) { return encodeURIComponent(v); }
  function plural(n, one, many) { return Number(n || 0).toLocaleString() + " " + (n === 1 ? one : (many || one + "s")); }
  function num(n) { return n == null ? "—" : Number(n).toLocaleString(); }
  var TYPE_ONE = { lead: "Lead", contact: "Contact", client: "Client", partner: "Partner", funder: "Funder" };
  function copyOn() { var s = M.session(); return !!(s && s.listSyncOn); }
  function viewUrl(id) { return "/campaigns/lists/" + enc(id) + "/members"; }
  function viewTab(id) { return "cbm-list-" + id; }
  function openView(id) { window.open(viewUrl(id), viewTab(id)); }

  var st = {
    loaded: false, cat: null, lists: [], q: "", kind: "", cc: false, retired: false,
    sortKeys: [{ col: "name", dir: "asc" }], grid: null, memGrid: null, sel: null, preview: false, screen: "index",
    details: {}, previewSeq: 0,
    edit: null
  };
  try { st.preview = localStorage.getItem(PREVIEW_KEY) === "1"; } catch (_) { st.preview = false; }

  // --- the hash ----------------------------------------------------------------------

  function writeHash() {
    if (M.recordId) return;
    var h = "#lists";
    if (st.screen === "edit" && st.edit) h += "?list=" + enc(st.edit.id) + "&edit=1";
    else if (st.sel) h += "?list=" + enc(st.sel);
    try { history.replaceState(null, "", h); } catch (_) {}
  }

  // --- the lists ---------------------------------------------------------------------

  async function loadLists() {
    var res = await busy(st.screen === "index" ? $("lv_listbox") : null, api("/lists"));
    st.lists = res.lists || [];
    renderIndex();
  }

  function listById(id) { for (var i = 0; i < st.lists.length; i++) if (st.lists[i].id === id) return st.lists[i]; return null; }

  // The members a row shows: the stored count when there is one, else the
  // rows on the list (a static list's people, a dynamic list's last run).
  function membersOf(l) {
    if (l.counts && l.counts.people != null) return l.counts.people;
    if (l.members != null) return l.members;
    return null;
  }

  function matches(l) {
    if (!st.retired && l.status === "retired") return false;
    if (st.retired && l.status !== "retired") return false;
    if (st.kind && l.kind !== st.kind) return false;
    if (st.cc && !l.ccSync) return false;
    if (!st.q) return true;
    var hay = (l.name + " " + (l.notes || "")).toLowerCase();
    return st.q.toLowerCase().split(/\s+/).every(function (w) { return !w || hay.indexOf(w) >= 0; });
  }

  // What each column sorts by, for the shared grid's multi-column sort.
  function sortValue(l, col) {
    if (col === "members") return membersOf(l);
    if (col === "kind") return l.kind === "dynamic" ? "Dynamic" : "Static";
    if (col === "lastUsed") return l.lastUsed || "";
    if (col === "updatedAt") return l.updatedAt || "";
    if (col === "cc") return l.ccSync ? "Linked" : "";
    if (col === "notes") return l.notes || "";
    return l.name || "";
  }

  function visibleLists() {
    var rows = st.lists.filter(matches);
    var keys = st.sortKeys.length ? st.sortKeys : [{ col: "name", dir: "asc" }];
    return window.CBMGrid ? CBMGrid.sortBy(rows, keys, sortValue) : rows;
  }

  // The shared loading spinner over a grid or panel while it waits.
  function busy(target, promise) { return window.CBMBusy && CBMBusy.loading && target ? CBMBusy.loading(target, promise) : promise; }

  function kindBadge(kind) {
    return el("span", "lv__kind lv__kind--" + kind, kind === "dynamic" ? "Dynamic" : "Static");
  }

  function renderIndex() {
    var rows = visibleLists();
    var tb = $("lv_rows");
    tb.textContent = "";
    var cc = copyOn();
    $("lv_ccHead").hidden = !cc;
    $("lv_ccChip").hidden = !cc;
    if (st.sel && !rows.some(function (l) { return l.id === st.sel; })) st.sel = null;
    rows.forEach(function (l) {
      var tr = el("tr");
      tr.setAttribute("data-id", l.id);
      tr.tabIndex = l.id === st.sel ? 0 : -1;
      if (l.id === st.sel) tr.className = "is-sel";
      var name = el("td", "lv__name");
      name.appendChild(el("span", "lv__nm", l.name));
      if (l.system) name.appendChild(el("span", "lv__tag lv__tag--ready", "Ready-made"));
      if (l.status === "retired") name.appendChild(el("span", "lv__tag", "Retired"));
      if (l.needsRebuild) name.appendChild(el("span", "lv__tag lv__tag--warn", "Check and save"));
      tr.appendChild(name);
      var kt = el("td"); kt.appendChild(kindBadge(l.kind)); tr.appendChild(kt);
      var m = membersOf(l);
      tr.appendChild(el("td", "lv__num", m == null ? "Not counted yet" : num(m)));
      tr.appendChild(el("td", "lv__date", l.lastUsed ? fmtDate(l.lastUsed) : "Never"));
      tr.appendChild(el("td", "lv__date", l.updatedAt ? fmtDate(l.updatedAt) : "—"));
      if (cc) {
        var ct = el("td");
        if (l.ccSync) { var s = el("span", "lv__cc"); s.appendChild(el("span", "lv__ccdot")); s.appendChild(document.createTextNode("Linked")); ct.appendChild(s); }
        else ct.textContent = "—";
        tr.appendChild(ct);
      }
      tr.appendChild(el("td", "lv__notes", l.notes || ""));
      tr.addEventListener("click", function () { select(l.id, false); });
      tr.addEventListener("dblclick", function () { openEdit(l.id); });
      tb.appendChild(tr);
    });
    var total = st.lists.filter(function (l) { return st.retired ? l.status === "retired" : l.status !== "retired"; }).length;
    text($("lv_matches"), rows.length === total ? plural(total, "list") : rows.length + " of " + total);
    var empty = $("lv_empty");
    if (!rows.length) {
      text(empty, !st.lists.length ? "No lists yet — start with + New list."
        : st.q ? "No list's name or notes contain \"" + st.q + "\"." : "No list matches these filters.");
      show(empty);
    } else hide(empty);
    if (st.grid) st.grid.refresh();
    renderPreview();
  }

  function rowFor(id) { return document.querySelector('#lv_rows tr[data-id="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]'); }

  function select(id, focus) {
    st.sel = id;
    Array.prototype.forEach.call(document.querySelectorAll("#lv_rows tr"), function (tr) {
      var on = tr.getAttribute("data-id") === id;
      tr.classList.toggle("is-sel", on);
      tr.tabIndex = on ? 0 : -1;
    });
    var tr = rowFor(id);
    if (tr && focus) { tr.focus(); tr.scrollIntoView({ block: "nearest" }); }
    writeHash();
    renderPreview();
  }

  function move(step) {
    var rows = visibleLists();
    if (!rows.length) return;
    var at = -1;
    for (var i = 0; i < rows.length; i++) if (rows[i].id === st.sel) at = i;
    var next = at < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, at + step));
    select(rows[next].id, true);
  }

  function onGridKey(e) {
    if (e.target && e.target.tagName === "INPUT") return;
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter" && st.sel) { e.preventDefault(); openEdit(st.sel); }
    else if ((e.key === "v" || e.key === "V") && st.sel && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); openView(st.sel); }
  }

  // "/" puts the cursor in the search — only while the list view is showing
  // and nobody is typing somewhere else.
  function onPageKey(e) {
    if (e.key !== "/" || st.screen !== "index" || $("lv_root").hidden || $("listsPanel").hidden) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
    e.preventDefault();
    $("lv_q").focus();
  }

  // --- Preview -------------------------------------------------------------------------

  function setPreview(on) {
    st.preview = on;
    try { localStorage.setItem(PREVIEW_KEY, on ? "1" : "0"); } catch (_) {}
    $("lv_previewSwitch").setAttribute("aria-checked", on ? "true" : "false");
    renderPreview();
  }

  async function detailOf(id, fresh) {
    if (!fresh && st.details[id]) return st.details[id];
    var both = await Promise.all([api("/lists/" + enc(id)), api("/lists/" + enc(id) + "/used-by")]);
    st.details[id] = { detail: both[0], usedBy: both[1].usedBy || [] };
    return st.details[id];
  }

  function figures(counts) {
    var box = el("div", "lv__figs");
    [["people", counts ? counts.people : null, "people"], ["email", counts ? counts.email : null, "by email"],
     ["text", counts ? counts.text : null, "by text"], ["postcard", counts ? counts.postcard : null, "by postcard"]].forEach(function (f) {
      var d = el("div", "lv__fig");
      d.appendChild(el("div", "lv__figv", num(f[1])));
      d.appendChild(el("div", "lv__figl", f[2]));
      box.appendChild(d);
    });
    return box;
  }

  function sentencesBlock(detail) {
    var wrap = el("div");
    var l = detail.list;
    if (l.kind === "static") { wrap.appendChild(el("p", "lv__plain", "Exactly the people added by hand. Nothing changes unless someone adds or removes them.")); return wrap; }
    var s = detail.sentences || { include: [], exclude: [] };
    if (!s.include.length) wrap.appendChild(el("p", "lv__plain", "Nobody yet — open Edit and add an Include group."));
    s.include.forEach(function (t, i) {
      if (i) wrap.appendChild(el("div", "lv__or", "or"));
      wrap.appendChild(el("div", "lv__rule", t));
    });
    s.exclude.forEach(function (t) { wrap.appendChild(el("div", "lv__rule lv__rule--out", "Leaving out: " + t)); });
    return wrap;
  }

  function usedBlock(usedBy) {
    var wrap = el("div");
    if (!usedBy.length) { wrap.appendChild(el("p", "lv__plain", "No campaign uses this list yet.")); return wrap; }
    var dl = el("dl", "lv__kv");
    usedBy.forEach(function (u) {
      dl.appendChild(el("dt", null, u.date ? fmtDate(u.date) : "—"));
      var dd = el("dd");
      var a = el("a", "cm__link", u.name);
      a.href = "/campaigns/record/" + enc(u.campaignId); a.target = "cbm-rec-campaigns-" + u.campaignId;
      dd.appendChild(a);
      dd.appendChild(document.createTextNode(" · " + (u.status || "—") + (u.reach == null ? "" : " · " + num(u.reach) + " reached")));
      dl.appendChild(dd);
    });
    wrap.appendChild(dl);
    return wrap;
  }

  function section(title, body) {
    var s = el("div", "lv__ps");
    s.appendChild(el("h4", null, title));
    s.appendChild(body);
    return s;
  }

  async function renderPreview() {
    var box = $("lv_preview");
    if (!st.preview) { hide(box); return; }
    show(box);
    var l = st.sel ? listById(st.sel) : null;
    box.textContent = "";
    if (!l) { box.appendChild(el("p", "lv__plain lv__pad", "Click a list, or move with the arrow keys, to see it here.")); return; }
    var seq = ++st.previewSeq;
    var head = el("div", "lv__ph");
    head.appendChild(kindBadge(l.kind));
    head.appendChild(el("h3", "lv__ptitle", l.name));
    var acts = el("div", "lv__pacts");
    var edit = el("button", "cbm-button", "Edit"); edit.type = "button";
    edit.addEventListener("click", function () { openEdit(l.id); });
    var view = el("a", "cbm-button cbm-button--secondary", "View members ↗");
    view.href = viewUrl(l.id); view.target = viewTab(l.id); view.rel = "noopener";
    var refresh = el("button", "cm__rowbtn", "Refresh"); refresh.type = "button";
    refresh.addEventListener("click", function () { refreshList(l.id); });
    acts.appendChild(edit); acts.appendChild(view); acts.appendChild(refresh);
    head.appendChild(acts);
    box.appendChild(head);
    var body = el("div", "lv__pb");
    var reach = el("div");
    reach.appendChild(figures(l.counts));
    reach.appendChild(el("div", "lv__muted lv__small", l.countedAt ? "Counted " + fmtDate(l.countedAt) +
      (l.counts && l.counts.notReachable ? " · " + num(l.counts.notReachable) + " by none of email, text or postcard" : "")
      : "Not counted yet — press Refresh, or wait for tonight's count."));
    body.appendChild(section("Reaches", reach));
    var who = el("div", "lv__muted", "Reading the list…");
    var used = el("div", "lv__muted", "Reading…");
    body.appendChild(section("Who is on it", who));
    body.appendChild(section("Used by", used));
    var dl = el("dl", "lv__kv");
    function kv(k, v) { dl.appendChild(el("dt", null, k)); dl.appendChild(el("dd", null, v)); }
    if (copyOn()) kv("Constant Contact", l.ccSync ? (l.ccStatus || "Linked") + (l.ccLastSyncAt ? " · synced " + fmtDate(l.ccLastSyncAt) : "") : "No copy kept");
    kv("Created by", l.createdBy || "—");
    kv("Updated", (l.updatedAt ? fmtDate(l.updatedAt) : "—") + (l.updatedBy ? " by " + l.updatedBy : ""));
    kv("Version", String(l.version));
    kv("Notes", l.notes || "—");
    body.appendChild(section("Details", dl));
    box.appendChild(body);
    try {
      var d = await busy(body, detailOf(l.id));
      if (seq !== st.previewSeq) return;
      who.replaceWith(sentencesBlock(d.detail));
      used.replaceWith(usedBlock(d.usedBy));
    } catch (e) {
      if (seq !== st.previewSeq) return;
      text(who, "Could not read the list: " + e.message);
      text(used, "");
    }
  }

  async function refreshList(id) {
    var l = listById(id);
    if (!l) return;
    if (l.status === "retired") { notice("A retired list is not counted — reactivate it first.", "warn"); return; }
    notice("Counting \"" + l.name + "\" — a large list takes a minute.", "ok");
    try {
      var res = await api("/lists/" + enc(id) + "/refresh", { method: "POST", timeoutMs: 300000 });
      var c = res.counts || {};
      notice("\"" + l.name + "\": " + plural(c.people, "person", "people") + " — email " + num(c.email) +
             ", text " + num(c.text) + ", postcard " + num(c.postcard) + ".", "ok");
      delete st.details[id];
      await loadLists();
      if (st.screen === "edit" && st.edit && st.edit.id === id) await reopenEdit();
    } catch (e) { notice(e.message, "error"); }
  }

  // --- New list -------------------------------------------------------------------------

  function staticLists(exceptId) {
    return st.lists.filter(function (l) { return l.kind === "static" && l.status !== "retired" && l.id !== exceptId; });
  }

  function selectBox(options, value, onChange, label) {
    var sel = document.createElement("select");
    if (label) sel.setAttribute("aria-label", label);
    options.forEach(function (o) {
      var opt = document.createElement("option");
      opt.value = o[0]; opt.textContent = o[1];
      if (o[0] === value) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", function () { onChange(sel.value); });
    return sel;
  }

  async function newList() {
    if (!(await leaveEdit())) return;
    var body = el("div");
    var nameLab = el("label", "cm__field cm__field--wide");
    nameLab.appendChild(el("span", null, "Name — say who is on it, for example: Downtown manufacturers with 10 or more staff"));
    var nameIn = el("input"); nameIn.type = "text"; nameIn.maxLength = 200; nameLab.appendChild(nameIn); body.appendChild(nameLab);
    var kinds = el("fieldset", "ls__kinds");
    kinds.appendChild(el("legend", null, "Kind — fixed once the list is created"));
    [["dynamic", "Dynamic — a search: who to include and who to leave out, run again before every send"],
     ["static", "Static — exactly the people you add to it, by name or by conditions"]].forEach(function (k, i) {
      var lab = el("label", "cm__check");
      var r = el("input"); r.type = "radio"; r.name = "lv_newKind"; r.value = k[0]; r.checked = i === 0;
      lab.appendChild(r); lab.appendChild(document.createTextNode(" " + k[1]));
      kinds.appendChild(lab);
    });
    body.appendChild(kinds);
    var exLab = el("label", "cm__field cm__field--wide");
    exLab.appendChild(el("span", null, "Leave out an exclusion list (optional)"));
    var exSel = selectBox([["", "— none —"]].concat(staticLists(null).map(function (l) { return [l.id, l.name]; })), "", function () {});
    exLab.appendChild(exSel); body.appendChild(exLab);
    body.appendChild(el("p", "cm__hint", "An exclusion list is a static list of people a dynamic list must never reach — for example, Do not invite."));
    function kindNow() { var c = body.querySelector('input[name="lv_newKind"]:checked'); return c ? c.value : "dynamic"; }
    body.addEventListener("change", function () { exLab.hidden = kindNow() !== "dynamic"; });
    M.openModal("New list", body, async function () {
      var name = nameIn.value.trim();
      if (!name) { M.modalMsg("Give the list a name.", "error"); return; }
      var kind = kindNow();
      var recipe = { include: [], exclude: [] };
      if (kind === "dynamic" && exSel.value) recipe.exclude.push({ kind: "list", listId: exSel.value });
      var res = await api("/lists", { method: "POST", body: { name: name, kind: kind, recipe: recipe } });
      M.closeModal();
      await loadLists();
      await openEdit(res.list.id, true);
      if (kind === "dynamic") { addGroup("include", "match"); notice("List created. Build who it includes — the count updates as you go — then Save list.", "ok"); }
      else { openDrawer(); notice("List created. Find people by name or by conditions, tick them and press Add.", "ok"); }
    }, "Create");
    setTimeout(function () { nameIn.focus(); }, 0);
  }

  // --- Edit -----------------------------------------------------------------------------

  function fieldsFor(type) { return ((st.cat && st.cat.types[type]) || { fields: [] }).fields; }
  function fieldInfo(type, name) {
    var f = fieldsFor(type);
    for (var i = 0; i < f.length; i++) if (f[i].field === name) return f[i];
    return null;
  }
  function typeOptions() { return Object.keys(st.cat.types).map(function (t) { return [t, st.cat.types[t].label]; }); }
  function blankCondition() { return { field: "", op: "", value: null }; }
  function noTypeLabel(f, opt) { return opt === "__none__" ? (f.noTypeLabel || "No type") : opt; }

  function showScreen(name) {
    st.screen = name;
    $("lv_index").hidden = name !== "index";
    $("lv_edit").hidden = name !== "edit";
    if (name !== "edit") closeDrawer();
    writeHash();
  }

  async function openEdit(id, force) {
    if (!force && !(await leaveEdit())) return;
    try {
      var d = await busy($("lv_root"), api("/lists/" + enc(id)));
      st.details[id] = null;
      st.edit = {
        id: id, detail: d, recipe: JSON.parse(JSON.stringify(d.list.recipe || { include: [], exclude: [] })),
        dirty: false, counts: {}, liveSeq: 0, liveTimer: null, live: null,
        mem: { offset: 0, limit: 50, total: 0, q: "", ticked: {}, rows: [] },
        drawer: { type: "all", found: [], keys: [], ticked: {}, find: { type: "lead", conditions: [blankCondition()] } }
      };
      st.sel = id;
      showScreen("edit");
      renderEdit();
      loadUsed();
      if (d.list.kind === "static") await loadEditMembers();
      window.scrollTo(0, 0);
    } catch (e) { notice(e.message, "error"); }
  }

  async function reopenEdit() { if (st.edit) await openEdit(st.edit.id, true); }

  async function leaveEdit() {
    if (!st.edit || !st.edit.dirty) return true;
    var leave = !!(await ask("Unsaved changes", "\"" + st.edit.detail.list.name + "\" has changes that are not saved. Leave them?", { ok: "Leave them" }));
    if (leave) st.edit.dirty = false;
    return leave;
  }

  async function backToIndex() {
    if (!(await leaveEdit())) return;
    st.edit = null;
    showScreen("index");
    await loadLists();
    var tr = st.sel && rowFor(st.sel);
    if (tr) tr.focus();
  }

  function isDynamic() { return st.edit && st.edit.detail.list.kind === "dynamic"; }

  function renderEdit() {
    var d = st.edit.detail, l = d.list, dynamic = isDynamic();
    var kb = $("lv_eKind"); kb.textContent = ""; kb.appendChild(kindBadge(l.kind));
    $("lv_eName").value = l.name;
    $("lv_eNotes").value = l.notes || "";
    $("lv_eView").href = viewUrl(l.id); $("lv_eView").target = viewTab(l.id);
    text($("lv_retireBtn"), l.status === "retired" ? "Reactivate" : "Retire");
    var note = $("lv_eNote"), msgs = [];
    if (l.system) msgs.push("A ready-made list comes with the system and cannot be changed. Copy it to a new list to make your own.");
    if (l.status === "retired") msgs.push("This list is retired: no campaign can choose it, and it cannot be changed. Reactivate it under More.");
    if (l.needsRebuild) msgs.push("This list was built with steps the new builder does not have. Check who is on it, then Save list.");
    (d.problems || []).forEach(function (p) { msgs.push(p.message); });
    note.textContent = "";
    msgs.forEach(function (m) { note.appendChild(el("p", null, m)); });
    note.hidden = !msgs.length;
    renderCopy(l);
    $("lv_eWho").hidden = !dynamic;
    $("lv_eMembers").hidden = dynamic;
    $("lv_eDiff").hidden = true;
    if (dynamic) renderGroups();
    renderLive();
    setDirty(false);
  }

  function renderCopy(l) {
    $("lv_eCc").hidden = !copyOn();
    if (!copyOn()) return;
    $("lv_eCcSwitch").setAttribute("aria-checked", l.ccSync ? "true" : "false");
    var failed = l.ccLastSync && l.ccLastSync.ok === false;
    var s = $("lv_eCcStatus");
    s.className = failed ? "lv__error" : "lv__muted";
    text(s, (l.ccStatus || "") + (l.ccLastSyncAt && l.ccSync ? " Last sync " + fmtDate(l.ccLastSyncAt) + "." : ""));
  }

  function setDirty(on, what) {
    st.edit.dirty = on;
    $("lv_saveBar").hidden = !on;
    if (on) text($("lv_saveText"), what || "Unsaved changes");
  }

  function changed(what) { setDirty(true, what); scheduleLive(); }

  // --- the builder -----------------------------------------------------------------

  function addGroup(side, kind) {
    var l = st.edit.detail.list;
    if (l.status === "retired" || l.system) { notice(l.system ? "A ready-made list cannot be changed — Copy it under More." : "A retired list cannot be changed — reactivate it first.", "warn"); return; }
    var g = kind === "list" ? { kind: "list", listId: "" } : kind === "import" ? { kind: "import", type: "lead", values: [] }
      : { kind: "match", type: "lead", conditions: [blankCondition()] };
    st.edit.recipe[side].push(g);
    changed("Unsaved changes — a group added");
    renderGroups();
  }

  function renderGroups() {
    ["include", "exclude"].forEach(function (side) {
      var host = $(side === "include" ? "lv_eInc" : "lv_eExc");
      host.textContent = "";
      var gs = st.edit.recipe[side];
      if (!gs.length) host.appendChild(el("p", "lv__plain", side === "include" ? "No groups yet — add one below." : "Nobody is left out."));
      gs.forEach(function (g, i) {
        if (i) host.appendChild(el("div", "lv__or", "or"));
        host.appendChild(groupCard(side, g, i));
      });
    });
  }

  function groupCount(side, i) {
    var c = st.edit.counts[side + (i + 1)];
    if (!c) return "";
    return (side === "include" ? num(c.count) : "− " + num(c.count)) + (c.unmatched ? " · " + plural(c.unmatched, "row") + " matched nothing" : "");
  }

  function groupCard(side, g, i) {
    var card = el("div", "lv__group" + (side === "exclude" ? " lv__group--out" : ""));
    var head = el("div", "lv__ghead");
    head.appendChild(selectBox((st.cat.groupKinds || []).map(function (k) { return [k.kind, k.label]; }), g.kind, function (v) {
      g.kind = v;
      if (v === "list") { g.listId = g.listId || ""; delete g.conditions; delete g.values; delete g.type; }
      else if (v === "import") { g.values = g.values || []; g.type = g.type || "lead"; delete g.conditions; }
      else { g.type = g.type || "lead"; g.conditions = [blankCondition()]; delete g.values; }
      changed(); renderGroups();
    }, "Kind of group"));
    if (g.kind === "list") {
      var lists = [["", "— choose a list —"]].concat(st.lists.filter(function (l) {
        return l.id !== st.edit.id && (l.status !== "retired" || l.id === g.listId);
      }).map(function (l) { return [l.id, l.name + (l.kind === "static" ? " (static)" : " (dynamic)")]; }));
      head.appendChild(selectBox(lists, g.listId || "", function (v) { g.listId = v; changed(); }, "Which list"));
    } else {
      head.appendChild(selectBox(typeOptions(), g.type, function (v) {
        g.type = v; if (g.kind === "match") g.conditions = [blankCondition()]; changed(); renderGroups();
      }, "Record type"));
      if (g.kind === "match") head.appendChild(el("span", "lv__muted", "where"));
    }
    var cnt = el("span", "lv__gcount", groupCount(side, i));
    cnt.setAttribute("data-count", side + (i + 1));
    head.appendChild(cnt);
    var del = el("button", "cm__rowbtn", "Remove group"); del.type = "button";
    del.addEventListener("click", function () { st.edit.recipe[side].splice(i, 1); st.edit.counts = {}; changed("Unsaved changes — a group removed"); renderGroups(); });
    head.appendChild(del);
    card.appendChild(head);
    if (g.kind === "list") return card;
    if (g.kind === "import") { card.appendChild(importBox(g)); return card; }
    conditionRows(g, card, function () { changed(); }, renderGroups);
    if (side === "include" && g.type === "contact") {
      card.appendChild(el("p", "lv__hint lv__indent", "A group of contacts must name the contact types it reaches: add a condition \"Contact type includes any of …\"."));
    }
    return card;
  }

  function conditionRows(g, host, onChange, redraw) {
    g.conditions.forEach(function (cond, j) { host.appendChild(condRow(g, cond, j, onChange, redraw)); });
    var add = el("button", "cm__rowbtn", "+ Condition"); add.type = "button";
    add.addEventListener("click", function () { g.conditions.push(blankCondition()); onChange(); redraw(); });
    var wrap = el("div", "lv__indent"); wrap.appendChild(add);
    host.appendChild(wrap);
  }

  function condRow(g, cond, j, onChange, redraw) {
    var row = el("div", "lv__cond");
    if (j) row.appendChild(el("span", "lv__and", "and"));
    var fields = fieldsFor(g.type);
    var fOpts = [["", "— choose a field —"]].concat(fields.map(function (f) { return [f.field, f.label]; }));
    var known = fieldInfo(g.type, cond.field);
    if (cond.field && !known) fOpts.push([cond.field, cond.field + " (no longer offered)"]);
    row.appendChild(selectBox(fOpts, cond.field, function (v) {
      cond.field = v; var f = fieldInfo(g.type, v);
      cond.op = f ? f.operators[0].op : ""; cond.value = null; onChange(); redraw();
    }, "Field"));
    if (known) {
      row.appendChild(selectBox(known.operators.map(function (o) { return [o.op, o.label]; }), cond.op, function (v) {
        cond.op = v; cond.value = null; onChange(); redraw();
      }, "Test"));
      row.appendChild(valueInput(known, cond, onChange));
    } else if (cond.field) {
      row.appendChild(el("span", "lv__error", "This field is no longer offered — choose another or remove the condition."));
    }
    var x = el("button", "cm__rowbtn", "Remove"); x.type = "button";
    x.setAttribute("aria-label", "Remove this condition");
    x.addEventListener("click", function () {
      if (g.conditions.length === 1) { notice("A group needs at least one condition — remove the group instead.", "warn"); return; }
      g.conditions.splice(j, 1); onChange(); redraw();
    });
    row.appendChild(x);
    return row;
  }

  function valueInput(f, cond, onChange) {
    var op = cond.op;
    if (["isEmpty", "isNotEmpty", "isTrue", "isFalse"].indexOf(op) >= 0) return el("span");
    if (f.options && ["in", "notIn", "anyOf", "noneOf"].indexOf(op) >= 0) {
      var box = el("div", "lv__ticks");
      var chosen = Array.isArray(cond.value) ? cond.value.slice() : [];
      f.options.forEach(function (o) {
        var val = typeof o === "object" ? o.value : o, name = typeof o === "object" ? o.label : noTypeLabel(f, o);
        var lab = el("label", "lv__tick" + (chosen.indexOf(val) >= 0 ? " is-on" : ""));
        var cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = chosen.indexOf(val) >= 0;
        cb.addEventListener("change", function () {
          var at = chosen.indexOf(val);
          if (cb.checked && at < 0) chosen.push(val);
          if (!cb.checked && at >= 0) chosen.splice(at, 1);
          lab.classList.toggle("is-on", cb.checked);
          cond.value = chosen.slice(); onChange();
        });
        lab.appendChild(cb); lab.appendChild(document.createTextNode(name));
        box.appendChild(lab);
      });
      if (!f.options.length) box.appendChild(el("span", "lv__muted", "The CRM offers no values to choose from."));
      return box;
    }
    var input = document.createElement("input");
    input.setAttribute("aria-label", "Value");
    if (op === "after" || op === "before") input.type = "date";
    else if (["lastDays", "olderDays", "atLeast", "atMost"].indexOf(op) >= 0) { input.type = "number"; input.min = "0"; input.className = "lv__numin"; }
    else { input.type = "text"; input.placeholder = op === "in" ? "e.g. 44113, 44114" : ""; }
    input.value = cond.value == null ? "" : String(cond.value);
    input.addEventListener("input", function () { cond.value = input.value; onChange(); });
    return input;
  }

  function importBox(g) {
    var wrap = el("div", "lv__indent lv__import");
    var ta = document.createElement("textarea");
    ta.rows = 4; ta.placeholder = "One CRM id or email address per line";
    ta.setAttribute("aria-label", "CRM ids or email addresses");
    ta.value = (g.values || []).join("\n");
    ta.addEventListener("input", function () { g.values = ta.value.split(/[\s,;]+/).filter(Boolean); changed(); });
    var file = document.createElement("input"); file.type = "file"; file.accept = ".csv,.txt,text/csv,text/plain";
    file.setAttribute("aria-label", "Read the ids or addresses from a file");
    file.addEventListener("change", function () {
      var f = file.files && file.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () {
        var vals = String(reader.result || "").split(/[\s,;]+/).map(function (v) { return v.replace(/^"|"$/g, ""); })
          .filter(function (v) { return v && (v.indexOf("@") >= 0 || /^[0-9a-f]{12,24}$/i.test(v)); });
        g.values = vals; ta.value = vals.join("\n"); changed();
        notice("Read " + vals.length + " ids or email addresses from " + f.name + ".", "ok");
      };
      reader.readAsText(f);
    });
    wrap.appendChild(ta);
    wrap.appendChild(file);
    wrap.appendChild(el("p", "lv__hint", "Leads and contacts match by CRM id or email address; clients, partners and funders by CRM id. A row matching nothing is counted, never created."));
    return wrap;
  }

  // --- the live count and who the change moves -------------------------------------

  function savedPeople() {
    var l = st.edit.detail.list;
    if (l.counts && l.counts.people != null) return l.counts.people;
    var row = listById(l.id);
    return row ? row.members : null;
  }

  function renderLive() {
    var box = $("lv_eLive"), l = st.edit.detail.list, live = st.edit.live;
    box.textContent = "";
    if (live && live.error) {
      box.appendChild(el("span", "lv__livel", "With these changes"));
      box.appendChild(el("span", "lv__livemsg", live.error));
      return;
    }
    if (live && live.counting) {
      box.appendChild(el("span", "lv__livel", "With these changes"));
      box.appendChild(el("span", "lv__liveb", "Counting…"));
      return;
    }
    if (live) {
      box.appendChild(el("span", "lv__livel", "With these changes"));
      box.appendChild(el("span", "lv__liveb", plural(live.total, "person", "people")));
      var saved = savedPeople();
      if (saved != null) {
        var d = live.total - saved;
        box.appendChild(el("span", "lv__delta", d === 0 ? "the same as the saved list" : (d > 0 ? "+ " : "− ") + num(Math.abs(d)) + " compared with the saved list"));
      }
      box.appendChild(el("span", "lv__livel", num(live.included) + " included · " + num(live.leftOut) + " left out"));
      return;
    }
    box.appendChild(el("span", "lv__livel", l.kind === "dynamic" ? "Who it reaches now" : "Who it reaches"));
    box.appendChild(el("span", "lv__liveb", savedPeople() == null ? "Not counted yet" : plural(savedPeople(), "person", "people")));
    var c = l.counts;
    box.appendChild(el("span", "lv__livel", c ? "Email " + num(c.email) + " · Text " + num(c.text) + " · Postcard " + num(c.postcard) : "Press Refresh to count it."));
    if (l.countedAt) box.appendChild(el("span", "lv__livel", "Counted " + fmtDate(l.countedAt)));
  }

  // Recounted a moment after each change; an older answer never overwrites a newer one.
  function scheduleLive() {
    if (!isDynamic()) return;
    clearTimeout(st.edit.liveTimer);
    st.edit.liveTimer = setTimeout(runLive, 700);
  }

  function recipeReady(r) {
    if (!r.include.length) return "Add an Include group to count who it reaches.";
    var all = r.include.concat(r.exclude);
    for (var i = 0; i < all.length; i++) {
      var g = all[i];
      if (g.kind === "list" && !g.listId) return "Choose the list each list group names.";
      if (g.kind === "match") for (var j = 0; j < g.conditions.length; j++) if (!g.conditions[j].field) return "Choose a field for each condition.";
    }
    return "";
  }

  async function runLive() {
    var e = st.edit;
    if (!e) return;
    var why = recipeReady(e.recipe);
    if (why) { e.live = { error: why }; renderLive(); $("lv_eDiff").hidden = true; return; }
    var seq = ++e.liveSeq;
    e.live = { counting: true }; renderLive();
    try {
      var res = await busy($("lv_eDiff"), api("/lists/preview", { method: "POST", body: { recipe: e.recipe, listId: e.id }, timeoutMs: 300000 }));
      if (st.edit !== e || seq !== e.liveSeq) return;
      e.counts = {};
      (res.groups || []).forEach(function (g) { e.counts[g.side + g.group] = g; });
      Array.prototype.forEach.call(document.querySelectorAll("#lv_edit [data-count]"), function (s) {
        var key = s.getAttribute("data-count");
        text(s, groupCount(key.indexOf("include") === 0 ? "include" : "exclude", Number(key.replace(/\D/g, "")) - 1));
      });
      e.live = { total: res.total, included: res.included, leftOut: res.leftOut };
      renderLive();
      renderDiff(res.diff);
    } catch (err) {
      if (st.edit !== e || seq !== e.liveSeq) return;
      e.live = { error: err.message }; renderLive();
    }
  }

  function renderDiff(diff) {
    var box = $("lv_eDiff"), body = $("lv_eDiffBody");
    if (!diff) { box.hidden = true; return; }
    box.hidden = false;
    body.textContent = "";
    if (!diff.comesOn && !diff.dropsOff) { body.appendChild(el("p", "lv__plain", "Nobody comes on or drops off compared with the last run.")); return; }
    body.appendChild(el("p", "lv__muted lv__small", num(diff.comesOn) + " come on · " + num(diff.dropsOff) + " drop off, compared with the run of " + fmtDate(diff.lastRunAt) + "."));
    var t = el("table", "lv__grid lv__grid--tight");
    var th = el("thead"), hr = el("tr"); hr.appendChild(el("th", null, "Person")); hr.appendChild(el("th", null, "Change")); th.appendChild(hr); t.appendChild(th);
    var tb = el("tbody");
    diff.comingOn.forEach(function (m) { var r = el("tr"); r.appendChild(el("td", null, m.name)); r.appendChild(el("td", "lv__plus", "Comes on")); tb.appendChild(r); });
    diff.droppingOff.forEach(function (m) { var r = el("tr"); r.appendChild(el("td", null, m.name)); r.appendChild(el("td", "lv__minus", "Drops off")); tb.appendChild(r); });
    t.appendChild(tb);
    var scroll = el("div", "lv__difflist"); scroll.appendChild(t);
    body.appendChild(scroll);
    if (window.CBMGrid) CBMGrid.enhance(t, { key: "lists.diff" });
    var more = (diff.comesOn - diff.comingOn.length) + (diff.dropsOff - diff.droppingOff.length);
    if (more > 0) body.appendChild(el("p", "lv__muted lv__small", "… and " + plural(more, "more person", "more people") + " not named here."));
  }

  // --- used by ---------------------------------------------------------------------

  async function loadUsed() {
    var e = st.edit, host = $("lv_eUsed");
    text(host, "Reading…");
    try {
      var res = await api("/lists/" + enc(e.id) + "/used-by");
      if (st.edit !== e) return;
      host.textContent = "";
      host.appendChild(usedBlock(res.usedBy || []));
      if ((res.usedBy || []).length && e.detail.list.kind === "dynamic") host.appendChild(el("p", "lv__muted lv__small", "Saving changes who each of these sends to at its next send. A campaign already signed off keeps the list it was signed off with."));
    } catch (err) { text(host, err.message); }
  }

  // --- save, discard, More -------------------------------------------------------

  async function save() {
    var e = st.edit;
    if (!e) return;
    var l = e.detail.list;
    var name = $("lv_eName").value.trim();
    if (!name) { notice("Give the list a name.", "error"); $("lv_eName").focus(); return; }
    if (l.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    var recipe = l.kind === "dynamic" ? e.recipe : { include: [], exclude: [] };
    try {
      var res = await api("/lists/" + enc(e.id), { method: "PUT", body: { name: name, notes: $("lv_eNotes").value, kind: l.kind, recipe: recipe } });
      setDirty(false);
      var newVersion = res.list.version !== l.version;
      notice("Saved" + (newVersion ? " — version " + res.list.version + "." : ".") + (res.copyNote ? " " + res.copyNote : ""),
             res.copyNote && res.copyNote.indexOf("keeps its old name") >= 0 ? "warn" : "ok");
      delete st.details[e.id];
      if (newVersion && l.kind === "dynamic") { await refreshList(e.id); return; }
      await loadLists();
      await reopenEdit();
    } catch (err) { notice(err.message, "error"); }
  }

  async function discard() {
    if (!st.edit) return;
    if (!(await ask("Discard the changes", "Throw away the changes to \"" + st.edit.detail.list.name + "\"?", { ok: "Discard" }))) return;
    st.edit.dirty = false;
    await reopenEdit();
  }

  function toggleMenu(open) {
    var menu = $("lv_moreMenu");
    var on = open == null ? menu.hidden : open;
    menu.hidden = !on;
    $("lv_moreBtn").setAttribute("aria-expanded", on ? "true" : "false");
    if (on) { var first = menu.querySelector("button"); if (first) first.focus(); }
  }

  async function copyList() {
    toggleMenu(false);
    var e = st.edit;
    if (e.dirty) { notice("Save the list first — Copy takes the saved list's members.", "warn"); return; }
    var stamp = new Date().toISOString().slice(0, 10);
    var name = await ask("Copy to a new static list",
      "The members as they are now — a dynamic list is run for it — become a static list that never changes by itself. Campaigns stay on this list.",
      { input: "Name of the new static list", value: e.detail.list.name + " — " + stamp, required: true, ok: "Copy" });
    if (name == null) return;
    try {
      var res = await api("/lists/" + enc(e.id) + "/copy", { method: "POST", body: { name: name }, timeoutMs: 300000 });
      notice("Copied " + plural(res.members, "member") + " to the static list \"" + res.list.name + "\".", "ok");
      await loadLists();
      await openEdit(res.list.id, true);
      refreshList(res.list.id);
    } catch (err) { notice(err.message, "error"); }
  }

  async function retireOrReactivate() {
    toggleMenu(false);
    var e = st.edit, retired = e.detail.list.status === "retired";
    if (!retired && !(await ask("Retire the list", "Campaigns that used it keep their record; no new campaign can choose it. You can reactivate it later.", { ok: "Retire" }))) return;
    try {
      await api("/lists/" + enc(e.id) + (retired ? "/reactivate" : "/retire"), { method: "POST" });
      await loadLists();
      await reopenEdit();
    } catch (err) { notice(err.message, "error"); }
  }

  async function deleteList() {
    toggleMenu(false);
    var e = st.edit;
    if (!(await ask("Delete the list", "Only a list no campaign has used, and no other list names, can be deleted. Deleting \"" + e.detail.list.name + "\" cannot be undone.", { ok: "Delete" }))) return;
    try {
      await api("/lists/" + enc(e.id), { method: "DELETE" });
      e.dirty = false; st.edit = null; st.sel = null;
      showScreen("index");
      await loadLists();
      notice("List deleted.", "ok");
    } catch (err) { notice(err.message, "error"); }
  }

  async function setCopy() {
    var e = st.edit, l = e.detail.list, on = $("lv_eCcSwitch").getAttribute("aria-checked") !== "true";
    if (e.dirty) { notice("Save the list first — the copy follows the saved list.", "warn"); return; }
    if (on && l.status === "retired") { notice("A retired list keeps no copy — reactivate it first.", "warn"); return; }
    try {
      var res = await api("/lists/" + enc(e.id) + "/cc-copy", { method: "PUT", body: { on: on } });
      e.detail.list = res.list;
      renderCopy(res.list);
      notice(on ? "The list now keeps a copy in Constant Contact. Press Sync now to make it at once, or tonight's mailing pass makes it."
                : "The list no longer keeps a copy. The copy at Constant Contact is kept as it was.", "ok");
      await loadLists();
    } catch (err) { notice(err.message, "error"); }
  }

  async function syncNow() {
    var e = st.edit, l = e.detail.list;
    if (!l.ccSync) { notice("Switch on Keep a copy in Constant Contact first — this list keeps no copy.", "warn"); return; }
    if (e.dirty) { notice("Save the list first — Sync now uses the saved list.", "warn"); return; }
    try {
      var res = await api("/lists/" + enc(e.id) + "/sync-now", { method: "POST", timeoutMs: 70000 });
      var sm = res.summary || {};
      notice("Synced: " + plural(sm.audience || 0, "person", "people") + " on the copy — " + num(sm.added || 0) + " added, " + num(sm.removed || 0) + " removed" +
             (sm.withheld ? ", " + num(sm.withheld) + " withheld as unsubscribed" : "") + ".", "ok");
      e.detail.list = res.list;
      renderCopy(res.list);
    } catch (err) { notice(err.message, "error"); }
  }

  // --- a static list: its members, Remove ---------------------------------------

  async function loadEditMembers() {
    var e = st.edit, m = e.mem;
    var sort = st.memGrid ? st.memGrid.sortParam() : "";
    var qs = "?offset=" + m.offset + "&limit=" + m.limit + (m.q ? "&q=" + enc(m.q) : "") + (sort ? "&sort=" + enc(sort) : "");
    try {
      var res = await busy($("lv_eMembers"), api("/lists/" + enc(e.id) + "/members" + qs));
      if (st.edit !== e) return;
      m.total = res.total; m.rows = res.members || [];
      renderEditMembers();
    } catch (err) { notice(err.message, "error"); }
  }

  function reachCell(reach, letter) {
    if (reach == null) return el("td", "lv__muted", "?");
    return reach.indexOf(letter) >= 0 ? el("td", "lv__yes", "✓") : el("td", "lv__no", "—");
  }

  function renderEditMembers() {
    var m = st.edit.mem, tb = $("lv_eMemRows");
    tb.textContent = "";
    m.rows.forEach(function (r) {
      var tr = el("tr");
      if (m.ticked[r.key]) tr.className = "is-ticked";
      var td = el("td");
      var cb = el("input"); cb.type = "checkbox"; cb.checked = !!m.ticked[r.key];
      cb.setAttribute("aria-label", "Select " + (r.name || "this person"));
      cb.addEventListener("change", function () { if (cb.checked) m.ticked[r.key] = r.name || r.key; else delete m.ticked[r.key]; tr.classList.toggle("is-ticked", cb.checked); renderBulk(); });
      td.appendChild(cb); tr.appendChild(td);
      tr.appendChild(el("td", r.missing ? "lv__error" : null, r.name));
      tr.appendChild(el("td", "lv__muted", TYPE_ONE[r.type] || r.type));
      tr.appendChild(reachCell(r.reach, "e")); tr.appendChild(reachCell(r.reach, "t")); tr.appendChild(reachCell(r.reach, "p"));
      tb.appendChild(tr);
    });
    text($("lv_eMemCount"), "· " + plural(m.total, "person", "people") + (m.q ? " match" : ", added by hand"));
    var end = Math.min(m.offset + m.limit, m.total);
    text($("lv_eMemRange"), m.total ? (m.offset + 1) + "–" + end + " of " + num(m.total) : "");
    var empty = $("lv_eMemEmpty");
    if (!m.total) { text(empty, m.q ? "No member's name contains \"" + m.q + "\"." : "Nobody yet — press + Add people."); show(empty); } else hide(empty);
    $("lv_eAll").checked = m.rows.length > 0 && m.rows.every(function (r) { return m.ticked[r.key]; });
    renderBulk();
  }

  function renderBulk() {
    var n = Object.keys(st.edit.mem.ticked).length;
    $("lv_eBulk").hidden = !n;
    text($("lv_eBulkCount"), plural(n, "person", "people") + " selected");
  }

  async function removeTicked() {
    var e = st.edit, keys = Object.keys(e.mem.ticked);
    if (!keys.length) { notice("Tick the people to remove first.", "warn"); return; }
    if (e.detail.list.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    if (!(await ask("Remove from the list", "Take " + plural(keys.length, "person", "people") + " off \"" + e.detail.list.name + "\"?", { ok: "Remove" }))) return;
    var done = 0;
    try {
      for (var i = 0; i < keys.length; i++) {
        await api("/lists/" + enc(e.id) + "/unmark", { method: "POST", body: { key: keys[i] } });
        done++;
      }
      notice("Removed " + plural(done, "person", "people") + ".", "ok");
    } catch (err) { notice((done ? "Removed " + plural(done, "person", "people") + ", then: " : "") + err.message, "error"); }
    e.mem.ticked = {};
    await loadEditMembers();
    recountQuietly(e.id);
  }

  // A static list's count after an add or a remove, without holding the page.
  function recountQuietly(id) {
    api("/lists/" + enc(id) + "/refresh", { method: "POST", timeoutMs: 300000 }).then(async function (res) {
      if (st.edit && st.edit.id === id) {
        st.edit.detail.list.counts = res.counts; st.edit.detail.list.countedAt = res.countedAt;
        renderLive();
        await loadEditMembers();
      }
      delete st.details[id];
      try { await loadLists(); } catch (_) {}
    }).catch(function () { /* the next count catches up */ });
  }

  // --- Add people: the drawer ------------------------------------------------------

  function openDrawer() {
    var e = st.edit;
    if (!e || isDynamic()) return;
    if (e.detail.list.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    text($("lv_drawerH"), "Add people to " + e.detail.list.name);
    renderDrawerTypes();
    renderFindForm();
    renderFound();
    show($("lv_drawer"));
    $("lv_dQ").focus();
  }

  function closeDrawer() { hide($("lv_drawer")); }

  function renderDrawerTypes() {
    var host = $("lv_dTypes"), d = st.edit.drawer;
    host.textContent = "";
    [["all", "Everyone"]].concat(typeOptions()).forEach(function (o) {
      var b = el("button", "lv__chip" + (d.type === o[0] ? " is-on" : ""), o[1]); b.type = "button";
      b.setAttribute("aria-pressed", d.type === o[0] ? "true" : "false");
      b.addEventListener("click", function () { d.type = o[0]; renderDrawerTypes(); searchNames(); });
      host.appendChild(b);
    });
  }

  function renderFindForm() {
    var d = st.edit.drawer, sel = $("lv_dFindType");
    if (!sel.options.length) typeOptions().forEach(function (o) { var opt = document.createElement("option"); opt.value = o[0]; opt.textContent = o[1]; sel.appendChild(opt); });
    sel.value = d.find.type;
    var host = $("lv_dConds");
    host.textContent = "";
    d.find.conditions.forEach(function (cond, j) { host.appendChild(condRow(d.find, cond, j, function () {}, renderFindForm)); });
  }

  function renderFound() {
    var d = st.edit.drawer, host = $("lv_dRows");
    host.textContent = "";
    d.found.forEach(function (r) {
      var on = !!r.onList;
      var row = el("label", "lv__res" + (d.ticked[r.key] ? " is-ticked" : "") + (on ? " is-on" : ""));
      var cb = el("input"); cb.type = "checkbox"; cb.checked = on || !!d.ticked[r.key];
      if (on) { cb.setAttribute("aria-label", (r.name || "This person") + " is already on the list"); cb.addEventListener("click", function (ev) { ev.preventDefault(); notice((r.name || "This person") + " is already on the list.", "ok"); }); }
      else cb.addEventListener("change", function () { if (cb.checked) d.ticked[r.key] = true; else delete d.ticked[r.key]; row.classList.toggle("is-ticked", cb.checked); $("lv_dAll").checked = false; renderTicked(); });
      row.appendChild(cb);
      var txt = el("span", "lv__restext");
      txt.appendChild(el("span", "lv__resname", r.name || r.key));
      txt.appendChild(el("span", "lv__muted lv__small", TYPE_ONE[r.type] || r.type));
      row.appendChild(txt);
      if (on) row.appendChild(el("span", "lv__already", "On the list"));
      host.appendChild(row);
    });
    var total = d.keys.length;
    text($("lv_dCount"), !total ? "" : (total > d.found.length ? "Showing " + d.found.length + " of " + plural(total, "match", "matches") : plural(total, "match", "matches")));
    renderTicked();
  }

  function renderTicked() {
    var n = Object.keys(st.edit.drawer.ticked).length;
    text($("lv_dTicked"), plural(n, "ticked", "ticked"));
    text($("lv_dAdd"), n ? "Add " + plural(n, "person", "people") : "Add people");
  }

  var nameTimer = null;
  function searchNames() {
    clearTimeout(nameTimer);
    nameTimer = setTimeout(async function () {
      var e = st.edit; if (!e) return;
      var q = $("lv_dQ").value.trim();
      if (q.length < 2) return;
      try {
        var res = await busy($("lv_dRows"), api("/lists/search/records?type=" + enc(e.drawer.type) + "&q=" + enc(q) + "&listId=" + enc(e.id)));
        if (st.edit !== e) return;
        e.drawer.found = res.records || [];
        e.drawer.keys = e.drawer.found.filter(function (r) { return !r.onList; }).map(function (r) { return r.key; });
        e.drawer.ticked = {}; $("lv_dAll").checked = false;
        renderFound();
        if (!e.drawer.found.length) text($("lv_dCount"), "Nothing matches \"" + q + "\".");
      } catch (err) { notice(err.message, "error"); }
    }, 350);
  }

  async function findByConditions() {
    var e = st.edit;
    try {
      var res = await busy($("lv_dRows"), api("/lists/" + enc(e.id) + "/find", { method: "POST", body: { group: e.drawer.find }, timeoutMs: 180000 }));
      e.drawer.found = res.records || [];
      e.drawer.keys = res.keys || [];
      e.drawer.ticked = {}; $("lv_dAll").checked = false;
      renderFound();
      if (!e.drawer.keys.length) text($("lv_dCount"), "Nothing matches those conditions.");
    } catch (err) { notice(err.message, "error"); }
  }

  function selectAllFound() {
    var d = st.edit.drawer;
    d.ticked = {};
    if ($("lv_dAll").checked) d.keys.forEach(function (k) { d.ticked[k] = true; });
    renderFound();
  }

  async function addTicked() {
    var e = st.edit, keys = Object.keys(e.drawer.ticked);
    if (!keys.length) { notice("Tick at least one person to add — find them by name or by conditions first.", "warn"); return; }
    try {
      var res = await api("/lists/" + enc(e.id) + "/add-people", { method: "POST", body: { keys: keys } });
      notice("Added " + plural(res.added, "person", "people") + " to \"" + e.detail.list.name + "\"" + (res.alreadyOn ? "; " + num(res.alreadyOn) + " were already on it." : "."), "ok");
      e.drawer = { type: e.drawer.type, found: [], keys: [], ticked: {}, find: e.drawer.find };
      $("lv_dQ").value = ""; $("lv_dAll").checked = false;
      closeDrawer();
      e.mem.offset = 0;
      await loadEditMembers();
      recountQuietly(e.id);
    } catch (err) { notice(err.message, "error"); }
  }

  // --- the tab ------------------------------------------------------------------------

  async function onShow(params) {
    show($("lv_root"));
    if (!st.loaded) {
      try { st.cat = await api("/lists/catalogue"); } catch (e) { notice(e.message, "error"); return; }
      st.loaded = true;
      setPreview(st.preview);
    }
    try { await loadLists(); } catch (e) { notice(e.message, "error"); return; }
    var want = params && params.list;
    if (want && params.edit) { await openEdit(want, true); return; }
    if (st.screen === "edit" && st.edit && !want) { writeHash(); return; }
    showScreen("index");
    if (want && listById(want)) select(want, true);
    else writeHash();
  }

  async function onLeave() { return leaveEdit(); }

  window.CBMListView = { onShow: onShow, onLeave: onLeave };

  // --- wiring -------------------------------------------------------------------------

  $("lv_q").addEventListener("input", function () { st.q = $("lv_q").value.trim(); renderIndex(); });
  $("lv_q").addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); move(st.sel ? 0 : 1); }
    else if (e.key === "Enter" && st.sel) { e.preventDefault(); openEdit(st.sel); }
  });
  Array.prototype.forEach.call(document.querySelectorAll("#lv_index .lv__chip[data-kind]"), function (b) {
    b.addEventListener("click", function () {
      st.kind = b.getAttribute("data-kind");
      Array.prototype.forEach.call(document.querySelectorAll("#lv_index .lv__chip[data-kind]"), function (x) {
        var on = x === b; x.classList.toggle("is-on", on); x.setAttribute("aria-pressed", on ? "true" : "false");
      });
      renderIndex();
    });
  });
  function toggleChip(id, key) {
    $(id).addEventListener("click", function () {
      st[key] = !st[key];
      $(id).classList.toggle("is-on", st[key]); $(id).setAttribute("aria-pressed", st[key] ? "true" : "false");
      renderIndex();
    });
  }
  toggleChip("lv_ccChip", "cc");
  toggleChip("lv_retiredChip", "retired");
  $("lv_previewSwitch").addEventListener("click", function () { setPreview(!st.preview); });
  $("lv_newBtn").addEventListener("click", newList);
  // The shared grid (frontend/shared/grid.js): resizable columns, the
  // stripe, multi-column sorting done here in the browser; and the divider
  // between the grid and Preview (frontend/shared/splitpane.js).
  if (window.CBMGrid) {
    st.grid = CBMGrid.enhance($("lv_grid"), {
      key: "lists.index", sort: [{ col: "name", dir: "asc" }],
      onSort: function (keys) { st.sortKeys = keys; renderIndex(); }
    });
    st.sortKeys = st.grid.keys();
    st.memGrid = CBMGrid.enhance($("lv_eMemGrid"), {
      key: "lists.editMembers",
      onSort: function () { if (st.edit) { st.edit.mem.offset = 0; loadEditMembers(); } }
    });
  }
  if (window.CBMSplit) CBMSplit.attach($("lv_listbox"), $("lv_preview"), { key: "lists.preview", initial: 440, min: 300, max: 900 });
  $("lv_rows").addEventListener("keydown", onGridKey);
  document.addEventListener("keydown", onPageKey);

  $("lv_back").addEventListener("click", function (e) { e.preventDefault(); backToIndex(); });
  $("lv_eRefreshBtn").addEventListener("click", function () {
    if (st.edit && st.edit.dirty) { notice("Save the list first — Refresh counts the saved list.", "warn"); return; }
    if (st.edit) refreshList(st.edit.id);
  });
  $("lv_eName").addEventListener("input", function () { setDirty(true, "Unsaved changes — the name"); });
  $("lv_eNotes").addEventListener("input", function () { setDirty(true, "Unsaved changes — the notes"); });
  Array.prototype.forEach.call(document.querySelectorAll("#lv_eWho [data-add]"), function (b) {
    b.addEventListener("click", function () { addGroup(b.getAttribute("data-add"), b.getAttribute("data-kind")); });
  });
  $("lv_saveBtn").addEventListener("click", save);
  $("lv_discardBtn").addEventListener("click", discard);
  $("lv_moreBtn").addEventListener("click", function () { toggleMenu(); });
  $("lv_moreMenu").addEventListener("keydown", function (e) { if (e.key === "Escape") { toggleMenu(false); $("lv_moreBtn").focus(); } });
  document.addEventListener("click", function (e) {
    if (!$("lv_moreMenu").hidden && !e.target.closest(".lv__menu")) toggleMenu(false);
  });
  $("lv_copyBtn").addEventListener("click", copyList);
  $("lv_retireBtn").addEventListener("click", retireOrReactivate);
  $("lv_deleteBtn").addEventListener("click", deleteList);
  $("lv_eCcSwitch").addEventListener("click", setCopy);
  $("lv_eSyncBtn").addEventListener("click", syncNow);

  $("lv_addBtn").addEventListener("click", openDrawer);
  $("lv_eAll").addEventListener("change", function () {
    var m = st.edit.mem, on = $("lv_eAll").checked;
    m.rows.forEach(function (r) { if (on) m.ticked[r.key] = r.name || r.key; else delete m.ticked[r.key]; });
    renderEditMembers();
  });
  $("lv_removeBtn").addEventListener("click", removeTicked);
  $("lv_clearBtn").addEventListener("click", function () { st.edit.mem.ticked = {}; renderEditMembers(); });
  var memTimer = null;
  $("lv_eMemQ").addEventListener("input", function () {
    clearTimeout(memTimer);
    memTimer = setTimeout(function () { st.edit.mem.q = $("lv_eMemQ").value.trim(); st.edit.mem.offset = 0; loadEditMembers(); }, 350);
  });
  $("lv_eMemPrev").addEventListener("click", function () {
    var m = st.edit.mem;
    if (m.offset === 0) { notice("This is the first page.", "warn"); return; }
    m.offset = Math.max(0, m.offset - m.limit); loadEditMembers();
  });
  $("lv_eMemNext").addEventListener("click", function () {
    var m = st.edit.mem;
    if (m.offset + m.limit >= m.total) { notice("This is the last page.", "warn"); return; }
    m.offset += m.limit; loadEditMembers();
  });

  $("lv_drawerClose").addEventListener("click", closeDrawer);
  $("lv_dCancel").addEventListener("click", closeDrawer);
  $("lv_drawer").addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
  $("lv_dQ").addEventListener("input", searchNames);
  $("lv_dFindType").addEventListener("change", function () { st.edit.drawer.find = { type: $("lv_dFindType").value, conditions: [blankCondition()] }; renderFindForm(); });
  $("lv_dAddCond").addEventListener("click", function () { st.edit.drawer.find.conditions.push(blankCondition()); renderFindForm(); });
  $("lv_dFind").addEventListener("click", findByConditions);
  $("lv_dAll").addEventListener("change", selectAllFound);
  $("lv_dAdd").addEventListener("click", addTicked);

  window.addEventListener("beforeunload", function (e) { if (st.edit && st.edit.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();
