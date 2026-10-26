/* Campaign lists (build plan § 7c.6, reshaped by § 7e.8) — the Lists tab of
   Marketing Management (build plan § 7e.2). The lists on the left, the open
   list on the right.

   A dynamic list is a search: "Who is on it" says so in sentences, and Edit
   opens the builder — an Include panel and a Leave out panel, each with
   + Group. Its member grid says which Include group brought each person in,
   and Exclude keeps one person off by adding them to a static exclusion list
   the dynamic list leaves out. A static list holds the people added to it:
   Add people (a name or email box, or conditions) and Remove. A list's kind
   is fixed; Copy makes a static list of the current members.

   Vanilla JS, no build step. Buttons are never disabled: each one checks on
   click and says what is missing. Loaded by index.html after app.js; it
   reaches the page through window.CBMMarketing, and its own element ids are
   prefixed ls_ so nothing collides with the other tabs. */
(function () {
  "use strict";
  var M = window.CBMMarketing;
  if (!M) return;
  var API_BASE = "/campaigns/api";
  var state = { cat: null, lists: [], open: null, detail: null, editing: false,
                recipe: { include: [], exclude: [] }, counts: {}, offset: 0, limit: 50, total: 0,
                sort: "", dir: "asc", q: "", dirty: false, loaded: false,
                find: { type: "lead", conditions: [] }, found: [], foundKeys: [], ticked: {} };

  function $(id) { return document.getElementById(id); }
  var show = M.show, hide = M.hide, text = M.text, el = M.el, fmtDate = M.fmtDate, notice = M.notice, ask = M.ask;
  // The lists' reads are the slow ones (a run can take minutes): a longer wait
  // than the page's default before the "did not answer" message.
  function api(path, opts) { opts = opts || {}; if (!opts.timeoutMs) opts.timeoutMs = 120000; return M.api(path, opts); }
  function listPath(suffix) { return "/lists/" + encodeURIComponent(state.open) + (suffix || ""); }
  function plural(n, one, many) { return n.toLocaleString() + " " + (n === 1 ? one : (many || one + "s")); }

  // --- the field catalogue -------------------------------------------------------------

  function fieldsFor(type) { return ((state.cat && state.cat.types[type]) || { fields: [] }).fields; }
  function fieldInfo(type, name) {
    var f = fieldsFor(type);
    for (var i = 0; i < f.length; i++) if (f[i].field === name) return f[i];
    return null;
  }
  var TYPE_ONE = { lead: "Lead", contact: "Contact", client: "Client", partner: "Partner", funder: "Funder" };
  function typeOptions() {
    return Object.keys(state.cat.types).map(function (t) { return [t, state.cat.types[t].label.toLowerCase()]; });
  }
  function noTypeLabel(f, opt) { return opt === "__none__" ? (f.noTypeLabel || "No type") : opt; }
  function blankCondition() { return { field: "", op: "", value: null }; }

  function select(options, value, onChange) {
    var sel = document.createElement("select");
    options.forEach(function (o) {
      var opt = document.createElement("option");
      opt.value = o[0]; opt.textContent = o[1];
      if (o[0] === value) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", function () { onChange(sel.value); });
    return sel;
  }

  // --- leaving an unsaved list: the page's dialog, never the browser's -----------------

  // Leaving discards: the list is re-read from the server, so coming back to
  // the tab shows what is saved, never the abandoned edit.
  async function leaveUnsaved() {
    if (!state.dirty) return true;
    var leave = !!(await ask("Unsaved changes", "The open list has changes that are not saved. Leave them?", { ok: "Leave them" }));
    if (leave) { state.dirty = false; if (state.open) await openList(state.open, true); }
    return leave;
  }

  // --- the lists ---------------------------------------------------------------------

  async function loadLists() {
    var res = await api("/lists");
    state.lists = res.lists || [];
    renderLists();
  }

  function membersText(l) {
    if (l.members == null) return l.kind === "dynamic" ? "not run yet" : "0";
    return l.members.toLocaleString();
  }

  function renderLists() {
    var showRetired = $("ls_showRetired").checked;
    var rows = state.lists.filter(function (l) { return showRetired || l.status !== "retired"; });
    var tb = $("ls_listRows");
    tb.textContent = "";
    rows.forEach(function (l) {
      var tr = el("tr");
      if (state.open === l.id) tr.className = "is-open";
      var name = el("td");
      name.appendChild(el("strong", null, l.name));
      if (l.status === "retired") { name.appendChild(document.createTextNode(" ")); name.appendChild(el("span", "cm__badge cm__badge--cancelled", "Retired")); }
      if (l.needsRebuild) { name.appendChild(document.createTextNode(" ")); name.appendChild(el("span", "cm__badge cm__badge--awaiting", "Check and save")); }
      tr.appendChild(name);
      tr.appendChild(el("td", null, l.kind === "static" ? "Static" : "Dynamic"));
      tr.appendChild(el("td", null, membersText(l)));
      tr.appendChild(el("td", null, l.lastUsed ? fmtDate(l.lastUsed) : "never"));
      tr.addEventListener("click", function () { openList(l.id); });
      tb.appendChild(tr);
    });
    text($("ls_listCount"), plural(rows.length, "list"));
    $("ls_listsEmpty").hidden = rows.length > 0;
  }

  function staticLists(exceptId) {
    return state.lists.filter(function (l) { return l.kind === "static" && l.status !== "retired" && l.id !== exceptId; });
  }

  // The new-list dialog: a name, the kind (fixed from then on), and for a
  // dynamic list an exclusion list to leave out from the start.
  async function newList() {
    if (!(await leaveUnsaved())) return;
    var body = el("div");
    var nameLab = el("label", "cm__field cm__field--wide"); nameLab.appendChild(el("span", null, "Name (for example: Downtown manufacturers)"));
    var nameIn = el("input"); nameIn.type = "text"; nameIn.maxLength = 200; nameLab.appendChild(nameIn); body.appendChild(nameLab);
    var kinds = el("fieldset", "ls__kinds");
    kinds.appendChild(el("legend", null, "Kind — fixed once the list is created"));
    [["dynamic", "Dynamic — a search: who to include and who to leave out, run again before every send"],
     ["static", "Static — exactly the people you add to it, by name or by conditions"]].forEach(function (k, i) {
      var lab = el("label", "cm__check");
      var r = el("input"); r.type = "radio"; r.name = "ls_newKind"; r.value = k[0]; r.checked = i === 0;
      lab.appendChild(r); lab.appendChild(document.createTextNode(" " + k[1]));
      kinds.appendChild(lab);
    });
    body.appendChild(kinds);
    var exLab = el("label", "cm__field cm__field--wide");
    exLab.appendChild(el("span", null, "Leave out an exclusion list (optional)"));
    var exSel = select([["", "— none —"]].concat(staticLists(null).map(function (l) { return [l.id, l.name]; })), "", function () {});
    exLab.appendChild(exSel); body.appendChild(exLab);
    body.appendChild(el("p", "cm__hint", "An exclusion list is a static list of people a dynamic list must never reach — for example, Do not invite. You can add one later with Exclude on any member."));
    function kindNow() { var c = body.querySelector('input[name="ls_newKind"]:checked'); return c ? c.value : "dynamic"; }
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
      await openList(res.list.id, true);
      if (kind === "dynamic") {
        startEdit();
        addGroup("include");
        notice("List created. Build who it includes, Count to check, then Save and Run now.", "ok");
      } else {
        notice("List created. Find people by name or by conditions, tick them and press Add ticked.", "ok");
        $("ls_searchBox").focus();
      }
    }, "Create");
    setTimeout(function () { nameIn.focus(); }, 0);
  }

  // --- one list -------------------------------------------------------------------------

  async function openList(id, force) {
    if (!force && state.open !== id && !(await leaveUnsaved())) return;
    try {
      var res = await api("/lists/" + encodeURIComponent(id));
      state.open = id;
      writeHash();
      state.detail = res;
      state.recipe = JSON.parse(JSON.stringify(res.list.recipe || { include: [], exclude: [] }));
      state.counts = {};
      state.editing = false;
      state.offset = 0; state.q = ""; state.sort = ""; state.dir = "asc";
      $("ls_memberSearch").value = "";
      state.found = []; state.foundKeys = []; state.ticked = {};
      state.dirty = false;
      renderLists();
      renderDetail();
      loadCounts();
      loadUsedBy();
      await loadMembers();
    } catch (e) { notice(e.message, "error"); }
  }

  function isDynamic() { return state.detail && state.detail.list.kind === "dynamic"; }

  function renderDetail() {
    var d = state.detail, l = d.list, dynamic = isDynamic();
    show($("ls_detail"));
    text($("ls_title"), l.name);
    var kb = $("ls_kindBadge");
    kb.textContent = dynamic ? "Dynamic" : "Static";
    kb.className = "cm__badge ls__kind ls__kind--" + l.kind;
    $("ls_lName").value = l.name;
    $("ls_lNotes").value = l.notes || "";
    var badge = $("ls_lStatus");
    badge.textContent = (l.status === "retired" ? "Retired" : "Active") + " · version " + l.version;
    badge.className = "cm__badge" + (l.status === "retired" ? " cm__badge--cancelled" : "");
    text($("ls_retireBtn"), l.status === "retired" ? "Reactivate" : "Retire");
    $("ls_rebuild").hidden = !l.needsRebuild;
    // The kind decides which card applies — the search, or Add people. Run now
    // stays on both, and on a static list says why it does not run.
    $("ls_whoCard").hidden = !dynamic;
    $("ls_addCard").hidden = dynamic;
    var run = l.lastRun || {};
    text($("ls_runNote"), !dynamic ? "A static list holds exactly the people added to it. It never runs."
      : l.lastRunAt
        ? "Last run " + fmtDate(l.lastRunAt) + " by " + (l.lastRunBy || "—") + ": " + plural(run.total || 0, "member") +
          " as of then. A campaign build runs it again." +
          (run.version && run.version !== l.version ? " The list has changed since: press Run now." : "")
        : "Not run yet — press Run now to see who it holds today.");
    renderCopy(l);
    renderProblems();
    renderSentences();
    $("ls_builder").hidden = !state.editing;
    text($("ls_editBtn"), state.editing ? "Editing…" : "Edit");
    if (!dynamic) renderFind();
    var vs = $("ls_versions");
    vs.textContent = "";
    (d.versions || []).forEach(function (v) {
      vs.appendChild(el("li", null, "Version " + v.version + " — " + (v.savedBy || "—") + ", " + fmtDate(v.savedAt)));
    });
  }

  // --- the copy in Constant Contact (build plan § 7e.9) -------------------------------

  function copyOn() { var s = M.session(); return !!(s && s.listSyncOn); }

  function renderCopy(l) {
    $("ls_copyRow").hidden = !copyOn();
    if (!copyOn()) return;
    $("ls_ccTick").checked = !!l.ccSync;
    var st = $("ls_ccStatus");
    var failed = l.ccLastSync && l.ccLastSync.ok === false;
    st.className = "ls__copystatus" + (failed ? " ls__copystatus--error" : "");
    text(st, (l.ccStatus || "") + (l.ccLastSyncAt && l.ccSync ? " Last sync " + fmtDate(l.ccLastSyncAt) + "." : ""));
  }

  async function setCopy() {
    if (!state.open) return;
    var tick = $("ls_ccTick"), on = tick.checked, l = state.detail.list;
    if (state.dirty) { tick.checked = !on; notice("Save the list first — the copy follows the saved list.", "warn"); return; }
    if (on && l.status === "retired") { tick.checked = false; notice("A retired list keeps no copy — reactivate it first.", "warn"); return; }
    try {
      var res = await api(listPath("/cc-copy"), { method: "PUT", body: { on: on } });
      state.detail.list = res.list;
      notice(on ? "The list now keeps a copy in Constant Contact. Press Sync now to make it at once, or the next mailing pass makes it."
                : "The list no longer keeps a copy. The copy at Constant Contact is kept as it was.", "ok");
      renderCopy(res.list);
      await loadLists();
    } catch (e) { tick.checked = !on; notice(e.message, "error"); }
  }

  async function syncNow() {
    if (!state.open) return;
    var l = state.detail.list;
    if (!l.ccSync) { notice("Tick Keep a copy in Constant Contact first — this list keeps no copy.", "warn"); return; }
    if (state.dirty) { notice("Save the list first — Sync now uses the saved list.", "warn"); return; }
    if (l.status === "retired") { notice("A retired list is not synced — reactivate it first.", "warn"); return; }
    try {
      var res = await api(listPath("/sync-now"), { method: "POST", timeoutMs: 70000 });
      var sm = res.summary || {};
      notice("Synced: " + plural(sm.audience || 0, "person", "people") + " on the copy — " +
             (sm.added || 0).toLocaleString() + " added, " + (sm.removed || 0).toLocaleString() + " removed" +
             (sm.withheld ? ", " + sm.withheld.toLocaleString() + " withheld as unsubscribed" : "") + ".", "ok");
      state.detail.list = res.list;
      renderCopy(res.list);
    } catch (e) {
      notice(e.message, "error");
      try { await openList(state.open, true); } catch (e2) { /* the notice already says why */ }
    }
  }

  function renderProblems() {
    var p = $("ls_problems"), d = state.detail;
    if (isDynamic() && !state.editing && (d.problems || []).length) {
      p.textContent = "";
      p.appendChild(el("strong", null, "The saved list cannot run yet:"));
      var ul = el("ul");
      d.problems.forEach(function (x) { ul.appendChild(el("li", null, x.message)); });
      p.appendChild(ul);
      show(p);
    } else hide(p);
  }

  function renderSentences() {
    var host = $("ls_sentences");
    host.textContent = "";
    var s = state.detail.sentences || { include: [], exclude: [] };
    host.appendChild(el("p", "ls__lead", "On this list:"));
    var inc = el("ul", "ls__sentences");
    if (!s.include.length) inc.appendChild(el("li", "cm__hint", "Nobody yet — press Edit and add an Include group."));
    s.include.forEach(function (t) { inc.appendChild(el("li", null, t)); });
    host.appendChild(inc);
    if (s.exclude.length) {
      host.appendChild(el("p", "ls__lead", "Left out, whatever else matches:"));
      var exc = el("ul", "ls__sentences ls__sentences--out");
      s.exclude.forEach(function (t) { exc.appendChild(el("li", null, t)); });
      host.appendChild(exc);
    }
  }

  // --- the top line: members per channel ----------------------------------------------

  async function loadCounts() {
    var box = $("ls_counts"), at = state.open;
    text(box, "Counting who it reaches…");
    try {
      var res = await api(listPath("/counts"), { timeoutMs: 180000 });
      if (state.open !== at) return;
      if (res.neverRun) { text(box, "Run the list to count who it reaches."); return; }
      box.textContent = "";
      box.appendChild(el("strong", null, plural(res.members, "member")));
      (res.counts || []).forEach(function (c) {
        box.appendChild(document.createTextNode(" · "));
        var s = el("span", null, c.label + " " + c.count.toLocaleString());
        s.title = c.skipped ? c.skipped.toLocaleString() + " cannot be reached by " + c.label.toLowerCase() + " (no consent, no address or a stop)" : "";
        box.appendChild(s);
      });
    } catch (e) { if (state.open === at) text(box, "The per-channel counts could not be read: " + e.message); }
  }

  // --- the builder: Include and Leave out ---------------------------------------------

  function markDirty() { state.dirty = true; hide($("ls_problems")); }

  function startEdit() {
    if (!isDynamic()) return;
    if (state.detail.list.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    state.editing = true;
    $("ls_builder").hidden = false;
    text($("ls_editBtn"), "Editing…");
    hide($("ls_problems"));
    renderGroups();
  }

  async function cancelEdit() {
    if (state.dirty && !(await ask("Discard the changes", "Throw away the changes to who is on this list?", { ok: "Discard" }))) return;
    state.dirty = false;
    await openList(state.open, true);
  }

  function addGroup(side) {
    if (!state.editing) startEdit();
    state.recipe[side].push({ kind: "match", type: "lead", conditions: [blankCondition()] });
    markDirty();
    renderGroups();
  }

  function renderGroups() {
    ["include", "exclude"].forEach(function (side) {
      var host = $(side === "include" ? "ls_incGroups" : "ls_excGroups");
      host.textContent = "";
      if (!state.recipe[side].length) {
        host.appendChild(el("p", "cm__hint", side === "include" ? "No groups yet — press + Group." : "Nobody is left out."));
      }
      state.recipe[side].forEach(function (g, i) { host.appendChild(groupCard(side, g, i)); });
    });
  }

  function groupCard(side, g, i) {
    var card = el("div", "ls__group");
    var head = el("div", "ls__grouphead");
    head.appendChild(el("span", "ls__groupno", "Group " + (i + 1)));
    head.appendChild(select((state.cat.groupKinds || []).map(function (k) { return [k.kind, k.label]; }), g.kind, function (v) {
      g.kind = v;
      if (v === "list") { g.listId = g.listId || ""; delete g.conditions; delete g.values; }
      else if (v === "import") { g.values = g.values || []; g.type = g.type || "lead"; delete g.conditions; }
      else { g.type = g.type || "lead"; g.conditions = [blankCondition()]; delete g.values; }
      markDirty(); renderGroups();
    }));
    if (g.kind === "list") {
      var lists = [["", "— choose a list —"]].concat(state.lists.filter(function (l) {
        return l.id !== state.open && (l.status !== "retired" || l.id === g.listId);
      }).map(function (l) { return [l.id, l.name + " (" + (l.kind === "static" ? "static" : "dynamic") + ")"]; }));
      head.appendChild(select(lists, g.listId || "", function (v) { g.listId = v; markDirty(); }));
    } else {
      head.appendChild(select(typeOptions(), g.type, function (v) {
        g.type = v; if (g.kind === "match") g.conditions = [blankCondition()]; markDirty(); renderGroups();
      }));
      if (g.kind === "match") head.appendChild(el("span", null, "where"));
    }
    var c = state.counts[side + (i + 1)];
    head.appendChild(el("span", "ls__groupcount", c ? (side === "include" ? plural(c.count, "match", "matches") : plural(c.count, "left out", "left out")) +
      (c.unmatched ? " — " + plural(c.unmatched, "row") + " matched nothing" : "") : ""));
    var del = el("button", "cm__rowbtn", "Remove group"); del.type = "button";
    del.addEventListener("click", function () { state.recipe[side].splice(i, 1); state.counts = {}; markDirty(); renderGroups(); });
    head.appendChild(del);
    card.appendChild(head);
    if (g.kind === "list") return card;
    if (g.kind === "import") { card.appendChild(importBox(g)); return card; }
    conditionRows(g, card, markDirty, renderGroups);
    if (side === "include" && g.type === "contact") {
      card.appendChild(el("p", "cm__hint ls__cond", "A group of contacts must name the contact types it reaches: add a condition \"Contact type includes any of …\"."));
    }
    return card;
  }

  // Conditions for a match group — shared by the builder and Add people.
  function conditionRows(g, host, changed, redraw) {
    g.conditions.forEach(function (cond, j) { host.appendChild(condRow(g, cond, j, changed, redraw)); });
    var add = el("button", "cm__rowbtn", "+ Condition (and)"); add.type = "button";
    add.addEventListener("click", function () { g.conditions.push(blankCondition()); changed(); redraw(); });
    var wrap = el("div", "ls__cond"); wrap.appendChild(add);
    host.appendChild(wrap);
  }

  function condRow(g, cond, j, changed, redraw) {
    var row = el("div", "ls__cond");
    var fields = fieldsFor(g.type);
    var fOpts = [["", "— choose a field —"]].concat(fields.map(function (f) { return [f.field, f.label]; }));
    var known = fieldInfo(g.type, cond.field);
    if (cond.field && !known) fOpts.push([cond.field, cond.field + " (no longer offered)"]);
    row.appendChild(select(fOpts, cond.field, function (v) {
      cond.field = v; var f = fieldInfo(g.type, v);
      cond.op = f ? f.operators[0].op : ""; cond.value = null; changed(); redraw();
    }));
    if (known) {
      row.appendChild(select(known.operators.map(function (o) { return [o.op, o.label]; }), cond.op, function (v) {
        cond.op = v; cond.value = null; changed(); redraw();
      }));
      row.appendChild(valueInput(known, cond, changed));
    } else if (cond.field) {
      row.appendChild(el("span", "ls__missing", "This field is no longer offered — choose another or remove the condition."));
    }
    var x = el("button", "cm__rowbtn", "Remove"); x.type = "button";
    x.addEventListener("click", function () {
      if (g.conditions.length === 1) { notice("A group needs at least one condition — remove the group instead.", "warn"); return; }
      g.conditions.splice(j, 1); changed(); redraw();
    });
    row.appendChild(x);
    return row;
  }

  function valueInput(f, cond, changed) {
    var op = cond.op;
    if (["isEmpty", "isNotEmpty", "isTrue", "isFalse"].indexOf(op) >= 0) return el("span");
    if (f.options && ["in", "notIn", "anyOf", "noneOf"].indexOf(op) >= 0) {
      var box = el("div", "ls__ticks");
      var chosen = Array.isArray(cond.value) ? cond.value.slice() : [];
      f.options.forEach(function (o) {
        var val = typeof o === "object" ? o.value : o, name = typeof o === "object" ? o.label : noTypeLabel(f, o);
        var lab = el("label");
        var cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = chosen.indexOf(val) >= 0;
        cb.addEventListener("change", function () {
          var at = chosen.indexOf(val);
          if (cb.checked && at < 0) chosen.push(val);
          if (!cb.checked && at >= 0) chosen.splice(at, 1);
          cond.value = chosen.slice(); changed();
        });
        lab.appendChild(cb); lab.appendChild(document.createTextNode(name));
        box.appendChild(lab);
      });
      if (!f.options.length) box.appendChild(el("span", "cm__hint", "The CRM offers no values to choose from."));
      return box;
    }
    var input = document.createElement("input");
    if (op === "after" || op === "before") input.type = "date";
    else if (["lastDays", "olderDays", "atLeast", "atMost"].indexOf(op) >= 0) { input.type = "number"; input.min = "0"; input.style.width = "7em"; }
    else { input.type = "text"; input.placeholder = op === "in" ? "e.g. 44113, 44114" : ""; }
    input.value = cond.value == null ? "" : String(cond.value);
    input.addEventListener("input", function () { cond.value = input.value; changed(); });
    return input;
  }

  // The file group: CRM ids, or email addresses for leads and contacts,
  // pasted or read from a file in the browser; nothing is created.
  function importBox(g) {
    var wrap = el("div", "ls__cond ls__import");
    var ta = document.createElement("textarea");
    ta.rows = 4; ta.placeholder = "One CRM id or email address per line";
    ta.value = (g.values || []).join("\n");
    ta.addEventListener("input", function () { g.values = ta.value.split(/[\s,;]+/).filter(Boolean); markDirty(); });
    var file = document.createElement("input"); file.type = "file"; file.accept = ".csv,.txt,text/csv,text/plain";
    file.addEventListener("change", function () {
      var f = file.files && file.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () {
        var vals = String(reader.result || "").split(/[\s,;]+/).map(function (v) { return v.replace(/^"|"$/g, ""); })
          .filter(function (v) { return v && (v.indexOf("@") >= 0 || /^[0-9a-f]{12,24}$/i.test(v)); });
        g.values = vals; ta.value = vals.join("\n"); markDirty();
        notice("Read " + vals.length + " ids or email addresses from " + f.name + ". Count to see how many match.", "ok");
      };
      reader.readAsText(f);
    });
    wrap.appendChild(ta);
    wrap.appendChild(file);
    wrap.appendChild(el("p", "cm__hint", "Leads and contacts match by CRM id or email address; clients, partners and funders by CRM id. A row matching nothing is counted, never created — new leads come in through Imports."));
    return wrap;
  }

  async function preview() {
    if (!state.editing) startEdit();
    if (!state.recipe.include.length) { notice("Add an Include group first.", "warn"); return; }
    try {
      var res = await api("/lists/preview", { method: "POST", body: { recipe: state.recipe, listId: state.open } });
      state.counts = {};
      (res.groups || []).forEach(function (g) { state.counts[g.side + g.group] = g; });
      renderGroups();
      text($("ls_previewNote"), plural(res.included, "record") + " included, " + res.leftOut.toLocaleString() + " left out: " +
        plural(res.total, "member") + ". Nothing is saved until you press Save.");
    } catch (e) { notice(e.message, "error"); }
  }

  async function save() {
    if (!state.open) return;
    var name = $("ls_lName").value.trim();
    if (!name) { notice("Give the list a name.", "error"); return; }
    var l = state.detail.list;
    if (l.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    try {
      var res = await api(listPath(), { method: "PUT",
        body: { name: name, notes: $("ls_lNotes").value, kind: l.kind, recipe: state.recipe } });
      state.dirty = false;
      var changed = res.list.version !== l.version;
      notice("Saved" + (changed ? " — version " + res.list.version + "." : ".") +
             (changed && l.kind === "dynamic" ? " Press Run now to see who it holds." : "") +
             (res.copyNote ? " " + res.copyNote : ""), res.copyNote && res.copyNote.indexOf("keeps its old name") >= 0 ? "warn" : "ok");
      await loadLists();
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function runList() {
    if (!state.open) return;
    if (!isDynamic()) { notice("A static list never runs — it holds exactly the people added to it.", "warn"); return; }
    if (state.dirty) { notice("Save the list first — Run now uses the saved list.", "warn"); return; }
    if ((state.detail.problems || []).length) { notice(state.detail.problems[0].message, "error"); return; }
    if (state.detail.list.status === "retired") { notice("A retired list does not run — reactivate it first.", "warn"); return; }
    try {
      var res = await api(listPath("/run"), { method: "POST", timeoutMs: 300000 });
      notice("Ran: " + plural(res.run.total, "member") + " (" + res.run.included.toLocaleString() + " included, " +
             res.run.leftOut.toLocaleString() + " left out).", "ok");
      await loadLists();
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function copyList() {
    if (!state.open) return;
    if (state.dirty) { notice("Save the list first — Copy takes the saved list's members.", "warn"); return; }
    var stamp = new Date().toISOString().slice(0, 10);
    var name = await ask("Copy to a new static list",
      "The members as they are now — a dynamic list is run for it — become a static list that never changes by itself. Campaigns stay on this list.",
      { input: "Name of the new static list", value: state.detail.list.name + " — " + stamp, required: true, ok: "Copy" });
    if (name == null) return;
    try {
      var res = await api(listPath("/copy"), { method: "POST", body: { name: name }, timeoutMs: 300000 });
      notice("Copied " + plural(res.members, "member") + " to the static list \"" + res.list.name + "\".", "ok");
      await loadLists();
      await openList(res.list.id, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function retireOrReactivate() {
    if (!state.open) return;
    var retired = state.detail.list.status === "retired";
    if (!retired && !(await ask("Retire the list", "Campaigns that used it keep their record; no new campaign can choose it. You can reactivate it later.", { ok: "Retire" }))) return;
    try {
      await api(listPath(retired ? "/reactivate" : "/retire"), { method: "POST" });
      await loadLists();
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function deleteList() {
    if (!state.open) return;
    if (!(await ask("Delete the list", "Only a list no campaign has used, and no other list names, can be deleted. Deleting it cannot be undone.", { ok: "Delete" }))) return;
    try {
      await api(listPath(), { method: "DELETE" });
      state.open = null; state.dirty = false; hide($("ls_detail")); writeHash();
      await loadLists();
      notice("List deleted.", "ok");
    } catch (e) { notice(e.message, "error"); }
  }

  // --- used by -------------------------------------------------------------------------

  async function loadUsedBy() {
    var at = state.open;
    try {
      var res = await api(listPath("/used-by"));
      if (state.open !== at) return;
      var tb = $("ls_usedRows");
      tb.textContent = "";
      (res.usedBy || []).forEach(function (u) {
        var tr = el("tr"), td = el("td");
        var a = el("a", "cm__link", u.name);
        a.href = "/campaigns/record/" + encodeURIComponent(u.campaignId);
        a.target = "cbm-rec-campaigns-" + u.campaignId;
        td.appendChild(a); tr.appendChild(td);
        tr.appendChild(el("td", null, u.kind || "—"));
        tr.appendChild(el("td", null, u.status || "—"));
        tr.appendChild(el("td", null, u.date ? fmtDate(u.date) : "—"));
        tr.appendChild(el("td", null, u.reach == null ? "not built yet" : Number(u.reach).toLocaleString()));
        tb.appendChild(tr);
      });
      $("ls_usedEmpty").hidden = (res.usedBy || []).length > 0;
    } catch (e) { notice(e.message, "error"); }
  }

  // --- a static list: Add people (by name or email, or by conditions) -----------------

  function renderFind() {
    if (!$("ls_findType").options.length) {
      typeOptions().forEach(function (o) { var opt = document.createElement("option"); opt.value = o[0]; opt.textContent = o[1]; $("ls_findType").appendChild(opt); });
    }
    $("ls_findType").value = state.find.type;
    var host = $("ls_findConds");
    host.textContent = "";
    if (!state.find.conditions.length) state.find.conditions.push(blankCondition());
    state.find.conditions.forEach(function (cond, j) { host.appendChild(condRow(state.find, cond, j, function () {}, renderFind)); });
    renderFound();
  }

  function renderFound() {
    var tb = $("ls_findRows");
    tb.textContent = "";
    state.found.forEach(function (r) {
      var tr = el("tr");
      var td = el("td");
      var cb = el("input"); cb.type = "checkbox"; cb.checked = !!state.ticked[r.key];
      cb.addEventListener("change", function () { if (cb.checked) state.ticked[r.key] = true; else delete state.ticked[r.key]; $("ls_findAll").checked = false; updateFindCount(); });
      td.appendChild(cb); tr.appendChild(td);
      tr.appendChild(el("td", null, TYPE_ONE[r.type] || r.type));
      tr.appendChild(el("td", r.missing ? "ls__missing" : null, r.name || r.key));
      tr.appendChild(el("td", "cm__hint", r.onList ? "already on the list" : ""));
      tb.appendChild(tr);
    });
    updateFindCount();
  }

  function updateFindCount() {
    var n = Object.keys(state.ticked).length;
    var total = state.foundKeys.length;
    text($("ls_findCount"), !total ? "" : (total > state.found.length ? "Showing " + state.found.length + " of " + plural(total, "match", "matches") + ". " : plural(total, "match", "matches") + ". ") + n.toLocaleString() + " ticked.");
  }

  var searchTimer = null;
  function onNameSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async function () {
      var q = $("ls_searchBox").value.trim();
      if (q.length < 2) return;
      try {
        var res = await api("/lists/search/records?type=all&q=" + encodeURIComponent(q));
        state.found = res.records || [];
        state.foundKeys = state.found.map(function (r) { return r.key; });
        state.ticked = {}; $("ls_findAll").checked = false;
        renderFound();
        if (!state.found.length) text($("ls_findCount"), "Nothing matches \"" + q + "\".");
      } catch (e) { notice(e.message, "error"); }
    }, 400);
  }

  async function findByConditions() {
    try {
      var res = await api(listPath("/find"), { method: "POST", body: { group: state.find }, timeoutMs: 180000 });
      state.found = res.records || [];
      state.foundKeys = res.keys || [];
      state.ticked = {}; $("ls_findAll").checked = false;
      renderFound();
      if (!state.foundKeys.length) text($("ls_findCount"), "Nothing matches those conditions.");
    } catch (e) { notice(e.message, "error"); }
  }

  function selectAll() {
    state.ticked = {};
    if ($("ls_findAll").checked) state.foundKeys.forEach(function (k) { state.ticked[k] = true; });
    renderFound();
  }

  async function addTicked() {
    var keys = Object.keys(state.ticked);
    if (!keys.length) { notice("Tick at least one person to add — find them by name or by conditions first.", "warn"); return; }
    if (state.detail.list.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    try {
      var res = await api(listPath("/add-people"), { method: "POST", body: { keys: keys } });
      notice("Added " + plural(res.added, "person", "people") + (res.alreadyOn ? "; " + res.alreadyOn.toLocaleString() + " already on the list." : "."), "ok");
      state.ticked = {}; state.found = []; state.foundKeys = []; $("ls_findAll").checked = false; $("ls_searchBox").value = "";
      renderFound();
      await loadLists();
      await reloadMembers();
    } catch (e) { notice(e.message, "error"); }
  }

  async function removePerson(m) {
    if (!(await ask("Remove from the list", "Take " + (m.name || "this person") + " off \"" + state.detail.list.name + "\"?", { ok: "Remove" }))) return;
    try {
      await api(listPath("/unmark"), { method: "POST", body: { key: m.key } });
      await loadLists();
      await reloadMembers();
    } catch (e) { notice(e.message, "error"); }
  }

  // --- a dynamic list: Exclude into a static exclusion list -------------------------

  async function excludePerson(m) {
    var l = state.detail.list;
    if (l.status === "retired") { notice("A retired list cannot be changed — reactivate it first.", "warn"); return; }
    var body = el("div");
    body.appendChild(el("p", null, "Keep " + (m.name || "this person") + " off \"" + l.name + "\" by adding them to a static exclusion list this list leaves out. The list itself stays a search."));
    var lab = el("label", "cm__field cm__field--wide"); lab.appendChild(el("span", null, "Add them to"));
    var options = staticLists(l.id).map(function (x) { return [x.id, x.name]; });
    // A list it already leaves out comes first.
    var already = (state.recipe.exclude || []).filter(function (g) { return g.kind === "list"; }).map(function (g) { return g.listId; });
    options.sort(function (a, b) { return (already.indexOf(b[0]) >= 0) - (already.indexOf(a[0]) >= 0); });
    var sel = select(options.concat([["__new", "+ New list"]]), options.length ? options[0][0] : "__new", function () { newLab.hidden = sel.value !== "__new"; });
    lab.appendChild(sel); body.appendChild(lab);
    var newLab = el("label", "cm__field cm__field--wide"); newLab.appendChild(el("span", null, "Name of the new exclusion list"));
    var newIn = el("input"); newIn.type = "text"; newIn.maxLength = 200; newIn.value = l.name + " — do not include";
    newLab.appendChild(newIn); body.appendChild(newLab);
    newLab.hidden = sel.value !== "__new";
    M.openModal("Exclude from this list", body, async function () {
      var payload = { key: m.key };
      if (sel.value === "__new") {
        if (!newIn.value.trim()) { M.modalMsg("Name the new exclusion list.", "error"); return; }
        payload.newName = newIn.value.trim();
      } else payload.targetListId = sel.value;
      var res = await api(listPath("/exclude"), { method: "POST", body: payload });
      M.closeModal();
      notice((m.name || "The person") + " is on \"" + res.exclusionList.name + "\"" +
             (res.linked ? ", which this list now leaves out." : " and stays off this list."), "ok");
      await loadLists();
      await openList(state.open, true);
    }, "Exclude");
  }

  // --- members ------------------------------------------------------------------------

  async function reloadMembers() { state.offset = 0; await loadMembers(); loadCounts(); }

  async function loadMembers() {
    if (!state.open) return;
    var qs = "?offset=" + state.offset + "&limit=" + state.limit +
             (state.q ? "&q=" + encodeURIComponent(state.q) : "") +
             (state.sort ? "&sort=" + state.sort + "&dir=" + state.dir : "");
    try {
      var res = await api(listPath("/members") + qs);
      state.total = res.total;
      renderMembers(res);
    } catch (e) { notice(e.message, "error"); }
  }

  function sortHead(label, key) {
    var th = el("th", "ls__sortable", label);
    if (state.sort === key) th.appendChild(el("span", "cm__sortind", state.dir === "asc" ? " ▲" : " ▼"));
    th.addEventListener("click", function () {
      if (state.sort === key) state.dir = state.dir === "asc" ? "desc" : "asc"; else { state.sort = key; state.dir = "asc"; }
      state.offset = 0; loadMembers();
    });
    return th;
  }

  function renderMembers(res) {
    var dynamic = isDynamic();
    text($("ls_membersTitle"), dynamic ? "Members as of the last run" : "Members");
    $("ls_staleNote").hidden = !res.changedSinceRun;
    var cols = [];
    (res.members || []).forEach(function (m) { Object.keys(m.values || {}).forEach(function (k) { if (cols.indexOf(k) < 0) cols.push(k); }); });
    var head = $("ls_memberHead");
    head.textContent = "";
    var tr = el("tr");
    tr.appendChild(sortHead("Type", "type"));
    tr.appendChild(sortHead("Name", "name"));
    if (dynamic) tr.appendChild(sortHead("Brought in by", "broughtInBy"));
    cols.forEach(function (c) { tr.appendChild(el("th", null, c)); });
    tr.appendChild(el("th"));
    head.appendChild(tr);
    var tb = $("ls_memberRows");
    tb.textContent = "";
    (res.members || []).forEach(function (m) {
      var r = el("tr");
      r.appendChild(el("td", null, TYPE_ONE[m.type] || m.type));
      r.appendChild(el("td", m.missing ? "ls__missing" : null, m.name));
      if (dynamic) r.appendChild(el("td", "ls__by", m.broughtInBy || "—"));
      cols.forEach(function (c) { var v = (m.values || {})[c]; r.appendChild(el("td", null, v == null || v === "" ? "—" : String(v))); });
      var td = el("td");
      var b = el("button", "cm__rowbtn", dynamic ? "Exclude" : "Remove"); b.type = "button";
      b.addEventListener("click", function () { if (dynamic) excludePerson(m); else removePerson(m); });
      td.appendChild(b); r.appendChild(td);
      tb.appendChild(r);
    });
    var end = Math.min(state.offset + state.limit, res.total);
    text($("ls_memberCount"), res.total ? (state.offset + 1) + "–" + end + " of " + res.total.toLocaleString() : "");
    var empty = $("ls_membersEmpty");
    if (!res.total) {
      empty.textContent = state.q ? "No member's name contains \"" + state.q + "\"."
        : res.neverRun ? "Not run yet — save the list, then press Run now."
        : dynamic ? "Nobody is on this list." : "Nobody yet — use Add people.";
      show(empty);
    } else hide(empty);
  }

  var memberTimer = null;
  function onMemberSearch() {
    clearTimeout(memberTimer);
    memberTimer = setTimeout(function () { state.q = $("ls_memberSearch").value.trim(); state.offset = 0; loadMembers(); }, 400);
  }

  function exportMembers() {
    if (!state.open) return;
    if (!state.total) { notice("Nobody is on this list to export.", "warn"); return; }
    var a = document.createElement("a"); a.href = API_BASE + listPath("/export"); a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
    notice("Exporting " + plural(state.total, "member") + " as a CSV file — your browser saves it.", "ok");
  }

  // --- the tab ----------------------------------------------------------------------

  function writeHash() {
    if (M.recordId) return;
    try { history.replaceState(null, "", "#lists" + (state.open ? "?list=" + encodeURIComponent(state.open) : "")); } catch (_) {}
  }

  // Shown by app.js when the Lists tab opens (the switch itself already asked
  // about unsaved changes, and refused the tab when lists are switched off).
  async function onShow(params) {
    if (!state.loaded) {
      try {
        state.cat = await api("/lists/catalogue");
      } catch (e) { notice(e.message, "error"); return; }
      state.loaded = true;
      show($("ls_listsView"));
      await loadLists();
    }
    var want = params && params.list;
    if (want && want !== state.open) await openList(want);
    else writeHash();
  }
  M.register("lists", { onShow: onShow, onLeave: leaveUnsaved });

  $("ls_newListBtn").addEventListener("click", newList);
  $("ls_showRetired").addEventListener("change", renderLists);
  $("ls_saveBtn").addEventListener("click", save);
  $("ls_runBtn").addEventListener("click", runList);
  $("ls_copyBtn").addEventListener("click", copyList);
  $("ls_retireBtn").addEventListener("click", retireOrReactivate);
  $("ls_deleteBtn").addEventListener("click", deleteList);
  $("ls_ccTick").addEventListener("change", setCopy);
  $("ls_syncNowBtn").addEventListener("click", syncNow);
  $("ls_editBtn").addEventListener("click", startEdit);
  $("ls_cancelEditBtn").addEventListener("click", cancelEdit);
  $("ls_addIncBtn").addEventListener("click", function () { addGroup("include"); });
  $("ls_addExcBtn").addEventListener("click", function () { addGroup("exclude"); });
  $("ls_previewBtn").addEventListener("click", preview);
  $("ls_lName").addEventListener("input", markDirty);
  $("ls_lNotes").addEventListener("input", markDirty);
  $("ls_searchBox").addEventListener("input", onNameSearch);
  $("ls_findType").addEventListener("change", function () { state.find = { type: $("ls_findType").value, conditions: [blankCondition()] }; renderFind(); });
  $("ls_findAddCondBtn").addEventListener("click", function () { state.find.conditions.push(blankCondition()); renderFind(); });
  $("ls_findBtn").addEventListener("click", findByConditions);
  $("ls_findAll").addEventListener("change", selectAll);
  $("ls_addTickedBtn").addEventListener("click", addTicked);
  $("ls_memberSearch").addEventListener("input", onMemberSearch);
  $("ls_exportBtn").addEventListener("click", exportMembers);
  $("ls_prevBtn").addEventListener("click", function () {
    if (state.offset === 0) { notice("This is the first page.", "warn"); return; }
    state.offset = Math.max(0, state.offset - state.limit); loadMembers();
  });
  $("ls_nextBtn").addEventListener("click", function () {
    if (state.offset + state.limit >= state.total) { notice("This is the last page.", "warn"); return; }
    state.offset += state.limit; loadMembers();
  });
  window.addEventListener("beforeunload", function (e) { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();
