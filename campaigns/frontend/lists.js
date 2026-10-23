/* Campaign lists (build plan § 7c.6) — the Lists tab of Marketing Management
   (build plan § 7e.2). The lists on the left, the open list on the right — its
   recipe, its hand edits or standing entries, its members. Vanilla JS, no build
   step. Buttons are never disabled: each one checks on click and says what is
   missing.

   This script is loaded by index.html after app.js and reaches the page through
   window.CBMMarketing: one api, one notice, one modal, one session. Its own
   element ids are prefixed ls_ so nothing collides with the other tabs. */
(function () {
  "use strict";
  var M = window.CBMMarketing;
  if (!M) return;
  var state = { cat: null, lists: [], open: null, detail: null,
                recipe: { steps: [] }, counts: {}, offset: 0, limit: 50, total: 0, dirty: false, loaded: false };

  function $(id) { return document.getElementById(id); }
  var show = M.show, hide = M.hide, text = M.text, el = M.el, fmtDate = M.fmtDate, notice = M.notice, ask = M.ask;
  // The lists' reads are the slow ones (a run can take minutes): a longer wait
  // than the page's default before the "did not answer" message.
  function api(path, opts) { opts = opts || {}; if (!opts.timeoutMs) opts.timeoutMs = 120000; return M.api(path, opts); }

  // --- the field catalogue -------------------------------------------------------------

  function fieldsFor(type) { return ((state.cat && state.cat.types[type]) || { fields: [] }).fields; }
  function fieldInfo(type, name) {
    var f = fieldsFor(type);
    for (var i = 0; i < f.length; i++) if (f[i].field === name) return f[i];
    return null;
  }
  var CONDITION_ACTIONS = ["add", "keep", "remove"], LIST_ACTIONS = ["addList", "removeList"];
  var TYPE_ONE = { lead: "Lead", contact: "Contact", client: "Client", partner: "Partner", funder: "Funder" };

  // The import step (§ 7c.4): CRM ids, or email addresses for leads and
  // contacts, pasted or read from a file in the browser; nothing is created.
  function importBox(s) {
    var wrap = el("div", "ls__cond ls__import");
    var ta = document.createElement("textarea");
    ta.rows = 4; ta.placeholder = "One CRM id or email address per line";
    ta.value = (s.values || []).join("\n");
    ta.addEventListener("input", function () { s.values = ta.value.split(/[\s,;]+/).filter(Boolean); markDirty(); });
    var file = document.createElement("input"); file.type = "file"; file.accept = ".csv,.txt,text/csv,text/plain";
    file.addEventListener("change", function () {
      var f = file.files && file.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () {
        var vals = String(reader.result || "").split(/[\s,;]+/).map(function (v) { return v.replace(/^"|"$/g, ""); })
          .filter(function (v) { return v && (v.indexOf("@") >= 0 || /^[0-9a-f]{12,24}$/i.test(v)); });
        s.values = vals; ta.value = vals.join("\n"); markDirty();
        notice("Read " + vals.length + " ids or email addresses from " + f.name + ". Count to see how many match.", "ok");
      };
      reader.readAsText(f);
    });
    wrap.appendChild(ta);
    wrap.appendChild(file);
    wrap.appendChild(el("p", "cm__hint", "Leads and contacts match by CRM id or email address; clients, partners and funders by CRM id. A row matching nothing is counted, never created — new leads come in through Imports."));
    return wrap;
  }

  function typeLabel(t) { return ((state.cat && state.cat.types[t]) || {}).label || t; }
  function noTypeLabel(f, opt) { return opt === "__none__" ? (f.noTypeLabel || "No type") : opt; }

  // --- leaving an unsaved list: the page's dialog, never the browser's -----------------

  async function leaveUnsaved() {
    if (!state.dirty) return true;
    return !!(await ask("Unsaved changes", "The open list has changes that are not saved. Leave them?", { ok: "Leave them" }));
  }

  // --- the lists ---------------------------------------------------------------------

  async function loadLists() {
    var res = await api("/lists");
    state.lists = res.lists || [];
    renderLists();
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
      tr.appendChild(name);
      tr.appendChild(el("td", null, l.kind === "static" ? "Static" : "Dynamic"));
      tr.appendChild(el("td", null, l.members == null ? "never run" : String(l.members)));
      tr.appendChild(el("td", null, l.usedBy ? l.usedBy + " campaign" + (l.usedBy === 1 ? "" : "s") : "—"));
      tr.appendChild(el("td", null, fmtDate(l.lastRunAt)));
      tr.addEventListener("click", function () { openList(l.id); });
      tb.appendChild(tr);
    });
    text($("ls_listCount"), rows.length + " list" + (rows.length === 1 ? "" : "s"));
    $("ls_listsEmpty").hidden = rows.length > 0;
  }

  async function newList() {
    if (!(await leaveUnsaved())) return;
    var name = await ask("New list", "A list is a set of leads and contacts a campaign sends to.",
                         { input: "Name (for example: Downtown manufacturers)", required: true, ok: "Create" });
    if (name == null) return;
    try {
      var res = await api("/lists", { method: "POST", body: { name: name.trim(), kind: "static", recipe: { steps: [] } } });
      await loadLists();
      await openList(res.list.id, true);
      addStep();
      notice("List created. Build its recipe, save, then run it.", "ok");
    } catch (e) { notice(e.message, "error"); }
  }

  // --- one list -------------------------------------------------------------------------

  async function openList(id, force) {
    if (!force && state.open !== id && !(await leaveUnsaved())) return;
    try {
      var res = await api("/lists/" + encodeURIComponent(id));
      state.open = id;
      writeHash();
      state.detail = res;
      state.recipe = JSON.parse(JSON.stringify(res.list.recipe || { steps: [] }));
      state.counts = {};
      ((res.list.lastRun || {}).steps || []).forEach(function (s) { state.counts[s.step] = s; });
      state.offset = 0;
      state.dirty = false;
      renderLists();
      renderDetail();
      await loadMembers();
    } catch (e) { notice(e.message, "error"); }
  }

  function renderDetail() {
    var d = state.detail, l = d.list;
    show($("ls_detail"));
    $("ls_lName").value = l.name;
    $("ls_lKind").value = l.kind;
    $("ls_lNotes").value = l.notes || "";
    var badge = $("ls_lStatus");
    badge.textContent = (l.status === "retired" ? "Retired" : "Active") + " · version " + l.version;
    badge.className = "cm__badge" + (l.status === "retired" ? " cm__badge--cancelled" : "");
    text($("ls_retireBtn"), l.status === "retired" ? "Reactivate" : "Retire");
    renderKindHint();
    var run = l.lastRun || {};
    text($("ls_runNote"), l.lastRunAt
      ? "Last run " + fmtDate(l.lastRunAt) + " by " + (l.lastRunBy || "—") + ": " + run.total + " members" +
        (l.kind === "static" ? " (frozen)." : " as of then — a campaign build runs it again.") +
        (run.version && run.version !== l.version ? " The recipe has changed since: run it again." : "")
      : "Never run.");
    var p = $("ls_problems");
    if ((d.problems || []).length) {
      p.textContent = "";
      p.appendChild(el("strong", null, "The saved recipe cannot run yet:"));
      var ul = el("ul");
      d.problems.forEach(function (x) { ul.appendChild(el("li", null, x.message)); });
      p.appendChild(ul);
      show(p);
    } else hide(p);
    renderSteps();
    renderHand();
    var used = $("ls_usedBy");
    used.textContent = "";
    if (!(d.usedBy || []).length) used.appendChild(el("li", "cm__hint", "No campaign uses this list yet."));
    (d.usedBy || []).forEach(function (u) {
      var li = el("li");
      var a = el("a", "cm__link", "Campaign");
      a.href = "/campaigns/record/" + encodeURIComponent(u.campaignId);
      a.target = "cbm-rec-campaigns-" + u.campaignId;
      li.appendChild(a);
      li.appendChild(document.createTextNode(u.builtVersion ? " — last built from version " + u.builtVersion + ", " + fmtDate(u.builtAt) : " — not built yet"));
      used.appendChild(li);
    });
    var vs = $("ls_versions");
    vs.textContent = "";
    (d.versions || []).forEach(function (v) {
      vs.appendChild(el("li", null, "Version " + v.version + " (" + v.kind + ") — " + (v.savedBy || "—") + ", " + fmtDate(v.savedAt)));
    });
  }

  function renderKindHint() {
    var k = $("ls_lKind").value;
    text($("ls_kindHint"), k === "static"
      ? "Static: Run builds the list once and freezes it. Ticking a member out, or adding one by hand, changes the frozen list; Run again keeps those changes."
      : "Dynamic: the recipe runs again at the start of every campaign build, so the list is always as of that day. A hand change is a standing entry — always include or always exclude — applied after the recipe.");
    text($("ls_runBtn"), k === "static" ? (state.detail && state.detail.list.lastRunAt ? "Run again" : "Run and freeze") : "Run now");
  }

  // --- the recipe -------------------------------------------------------------------------

  // The amber box describes the SAVED recipe; once the recipe is being edited it
  // is out of date, so it goes until the next Save re-checks (live pass 10-21-26:
  // a new list's "needs at least one step" stayed up while its steps were built).
  function markDirty() { state.dirty = true; hide($("ls_problems")); }

  function addStep() {
    var first = !state.recipe.steps.length;
    state.recipe.steps.push({ action: first ? "add" : "keep", type: "lead", conditions: [{ field: "", op: "", value: null }] });
    markDirty();
    renderSteps();
  }

  function renderSteps() {
    var host = $("ls_steps");
    host.textContent = "";
    if (!state.recipe.steps.length) host.appendChild(el("p", "cm__hint", "No steps yet — start with + Add step."));
    state.recipe.steps.forEach(function (s, i) { host.appendChild(stepCard(s, i)); });
  }

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

  function stepCard(s, i) {
    var card = el("div", "ls__step");
    var head = el("div", "ls__stephead");
    head.appendChild(el("span", "ls__stepno", "Step " + (i + 1)));
    head.appendChild(select((state.cat.actions || []).map(function (a) { return [a.action, a.label]; }), s.action,
      function (v) {
        var wasCond = CONDITION_ACTIONS.indexOf(s.action) >= 0, isCond = CONDITION_ACTIONS.indexOf(v) >= 0;
        s.action = v;
        if (LIST_ACTIONS.indexOf(v) >= 0) { s.listId = s.listId || ""; s.conditions = []; }
        else if (v === "import") { s.values = s.values || []; s.conditions = []; s.type = s.type || "lead"; }
        else if (!wasCond && isCond) { s.type = s.type || "lead"; s.conditions = [{ field: "", op: "", value: null }]; }
        markDirty(); renderSteps();
      }));
    var isList = LIST_ACTIONS.indexOf(s.action) >= 0;
    if (isList) {
      var lists = [["", "— choose a list —"]].concat(state.lists.filter(function (l) {
        return l.id !== state.open && (l.status !== "retired" || l.id === s.listId);
      }).map(function (l) { return [l.id, l.name + " (" + l.kind + ")"]; }));
      head.appendChild(select(lists, s.listId || "", function (v) { s.listId = v; markDirty(); }));
    } else {
      var types = Object.keys(state.cat.types).map(function (t) { return [t, state.cat.types[t].label.toLowerCase()]; });
      head.appendChild(select(types, s.type, function (v) {
        s.type = v; if (s.action !== "import") s.conditions = [{ field: "", op: "", value: null }]; markDirty(); renderSteps();
      }));
      if (s.action !== "import") head.appendChild(el("span", null, "where"));
    }
    var c = state.counts[i + 1];
    head.appendChild(el("span", "ls__stepcount", c ? (c.after + " after this step (" + (c.added ? "+" + c.added : "") + (c.dropped ? "−" + c.dropped : "") + (c.added || c.dropped ? "" : "no change") + ")" + (c.unmatched ? " — " + c.unmatched + " rows matched nothing" : "")) : ""));
    var up = el("button", "cm__rowbtn", "↑"); up.type = "button"; up.title = "Move this step up";
    up.addEventListener("click", function () {
      if (i === 0) { notice("This is already the first step.", "warn"); return; }
      var x = state.recipe.steps.splice(i, 1)[0]; state.recipe.steps.splice(i - 1, 0, x); state.counts = {}; markDirty(); renderSteps();
    });
    var down = el("button", "cm__rowbtn", "↓"); down.type = "button"; down.title = "Move this step down";
    down.addEventListener("click", function () {
      if (i === state.recipe.steps.length - 1) { notice("This is already the last step.", "warn"); return; }
      var x = state.recipe.steps.splice(i, 1)[0]; state.recipe.steps.splice(i + 1, 0, x); state.counts = {}; markDirty(); renderSteps();
    });
    var count = el("button", "cm__rowbtn", "Count to here"); count.type = "button";
    count.addEventListener("click", function () { preview(i + 1); });
    var del = el("button", "cm__rowbtn", "Remove step"); del.type = "button";
    del.addEventListener("click", function () { state.recipe.steps.splice(i, 1); state.counts = {}; markDirty(); renderSteps(); });
    [up, down, count, del].forEach(function (b) { head.appendChild(b); });
    card.appendChild(head);
    if (isList) return card;
    if (s.action === "import") { card.appendChild(importBox(s)); return card; }
    s.conditions.forEach(function (cond, j) { card.appendChild(condRow(s, cond, j)); });
    var add = el("button", "cm__rowbtn", "+ Condition (and)"); add.type = "button";
    add.addEventListener("click", function () { s.conditions.push({ field: "", op: "", value: null }); markDirty(); renderSteps(); });
    var wrap = el("div", "ls__cond"); wrap.appendChild(add);
    card.appendChild(wrap);
    if (s.type === "contact" && s.action === "add") {
      card.appendChild(el("p", "cm__hint ls__cond", "Adding contacts must name the contact types it reaches: add a condition \"Contact type includes any of …\"."));
    }
    return card;
  }

  function condRow(s, cond, j) {
    var row = el("div", "ls__cond");
    var fields = fieldsFor(s.type);
    var fOpts = [["", "— choose a field —"]].concat(fields.map(function (f) { return [f.field, f.label]; }));
    var known = fieldInfo(s.type, cond.field);
    if (cond.field && !known) fOpts.push([cond.field, cond.field + " (no longer offered)"]);
    row.appendChild(select(fOpts, cond.field, function (v) {
      cond.field = v; var f = fieldInfo(s.type, v);
      cond.op = f ? f.operators[0].op : ""; cond.value = null; markDirty(); renderSteps();
    }));
    if (known) {
      row.appendChild(select(known.operators.map(function (o) { return [o.op, o.label]; }), cond.op, function (v) {
        cond.op = v; cond.value = null; markDirty(); renderSteps();
      }));
      row.appendChild(valueInput(known, cond));
    } else if (cond.field) {
      row.appendChild(el("span", "ls__missing", "This field is no longer offered — choose another or remove the condition."));
    }
    var x = el("button", "cm__rowbtn", "Remove"); x.type = "button";
    x.addEventListener("click", function () {
      if (s.conditions.length === 1) { notice("A step needs at least one condition — remove the step instead.", "warn"); return; }
      s.conditions.splice(j, 1); markDirty(); renderSteps();
    });
    row.appendChild(x);
    return row;
  }

  function valueInput(f, cond) {
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
          cond.value = chosen.slice(); markDirty();
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
    input.addEventListener("input", function () { cond.value = input.value; markDirty(); });
    return input;
  }

  async function preview(upTo) {
    if (!state.recipe.steps.length) { notice("Add a step first.", "warn"); return; }
    try {
      var res = await api("/lists/preview", { method: "POST", body: { recipe: state.recipe, upTo: upTo || null, listId: state.open } });
      state.counts = {};
      (res.steps || []).forEach(function (s) { state.counts[s.step] = s; });
      renderSteps();
      notice((upTo ? "Up to step " + upTo : "Every step") + ": " + res.total + " members. Nothing is saved until you press Save.", "ok");
    } catch (e) { notice(e.message, "error"); }
  }

  async function save() {
    if (!state.open) return;
    var name = $("ls_lName").value.trim();
    if (!name) { notice("Give the list a name.", "error"); return; }
    try {
      var res = await api("/lists/" + encodeURIComponent(state.open), { method: "PUT",
        body: { name: name, notes: $("ls_lNotes").value, kind: $("ls_lKind").value, recipe: state.recipe } });
      state.dirty = false;
      notice("Saved — version " + res.list.version + ".", "ok");
      await loadLists();
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function runList() {
    if (!state.open) return;
    if (state.dirty) { notice("Save the list first — Run uses the saved recipe.", "warn"); return; }
    if ((state.detail.problems || []).length) { notice(state.detail.problems[0].message, "error"); return; }
    var l = state.detail.list;
    if (l.status === "retired") { notice("A retired list does not run — reactivate it first.", "warn"); return; }
    if (l.kind === "static" && l.lastRunAt && !(await ask("Run again", "Run the recipe again and replace the frozen list? Changes made by hand are kept.", { ok: "Run again" }))) return;
    try {
      var res = await api("/lists/" + encodeURIComponent(state.open) + "/run", { method: "POST", timeoutMs: 300000 });
      notice("Ran: " + res.run.total + " members.", "ok");
      await loadLists();
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function retireOrReactivate() {
    if (!state.open) return;
    var retired = state.detail.list.status === "retired";
    if (!retired && !(await ask("Retire the list", "Campaigns that used it keep their record; no new campaign can choose it. You can reactivate it later.", { ok: "Retire" }))) return;
    try {
      await api("/lists/" + encodeURIComponent(state.open) + (retired ? "/reactivate" : "/retire"), { method: "POST" });
      await loadLists();
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function deleteList() {
    if (!state.open) return;
    if ((state.detail.usedBy || []).length) { notice("A campaign uses this list, so it cannot be deleted — retire it instead.", "warn"); return; }
    if (!(await ask("Delete the list", "No campaign has used this list. Deleting it cannot be undone.", { ok: "Delete" }))) return;
    try {
      await api("/lists/" + encodeURIComponent(state.open), { method: "DELETE" });
      state.open = null; state.dirty = false; hide($("ls_detail")); writeHash();
      await loadLists();
      notice("List deleted.", "ok");
    } catch (e) { notice(e.message, "error"); }
  }

  // --- hand edits and standing entries ------------------------------------------------

  function renderHand() {
    var d = state.detail, dynamic = d.list.kind === "dynamic";
    text($("ls_handTitle"), dynamic ? "Standing entries" : "Changed by hand");
    text($("ls_handHint"), dynamic
      ? "Always include or always exclude, applied after the recipe on every run. Not a Do Not Contact — for a person no campaign may contact, use the lead's Do Not Contact."
      : "Records added or taken out by hand. Run again keeps them.");
    text($("ls_handModeHead"), dynamic ? "Entry" : "Change");
    var rows = dynamic ? d.entries : d.hand;
    var tb = $("ls_handRows");
    tb.textContent = "";
    (rows || []).forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(el("td", null, r.name || r.key));
      var mode = dynamic ? (r.mode === "include" ? "Always include" : "Always exclude") : (r.state === "in" ? "Added by hand" : "Taken out by hand");
      tr.appendChild(el("td", null, mode + (r.note ? " — " + r.note : "")));
      tr.appendChild(el("td", null, (r.by || "—") + ", " + fmtDate(r.at)));
      var td = el("td");
      var b = el("button", "cm__rowbtn", dynamic ? "Remove" : "Undo"); b.type = "button";
      b.addEventListener("click", function () { unmark(r.key); });
      td.appendChild(b); tr.appendChild(td);
      tb.appendChild(tr);
    });
    $("ls_handEmpty").hidden = (rows || []).length > 0;
  }

  async function mark(key, stateIn) {
    var dynamic = state.detail.list.kind === "dynamic";
    var note = "";
    if (dynamic) {
      note = await ask(stateIn ? "Always include" : "Always exclude",
                       "Applied after the recipe on every run, until someone removes it.",
                       { input: "A note for whoever reads this later (optional)", ok: stateIn ? "Always include" : "Always exclude" });
      if (note == null) return;
    }
    try {
      await api("/lists/" + encodeURIComponent(state.open) + "/mark", { method: "POST", body: { key: key, state: stateIn ? "in" : "out", note: note } });
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  async function unmark(key) {
    try {
      await api("/lists/" + encodeURIComponent(state.open) + "/unmark", { method: "POST", body: { key: key } });
      await openList(state.open, true);
    } catch (e) { notice(e.message, "error"); }
  }

  var searchTimer = null;
  function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async function () {
      var q = $("ls_searchBox").value.trim();
      var ul = $("ls_searchResults");
      ul.textContent = "";
      if (q.length < 2) return;
      try {
        var res = await api("/lists/search/records?type=" + encodeURIComponent($("ls_searchType").value) + "&q=" + encodeURIComponent(q));
        if (!(res.records || []).length) ul.appendChild(el("li", "cm__hint", "Nothing matches."));
        (res.records || []).forEach(function (r) {
          var li = el("li");
          li.appendChild(el("span", null, r.name || r.key));
          var inc = el("button", "cm__rowbtn", state.detail.list.kind === "dynamic" ? "Always include" : "Add"); inc.type = "button";
          inc.addEventListener("click", function () { mark(r.key, true); });
          var exc = el("button", "cm__rowbtn", state.detail.list.kind === "dynamic" ? "Always exclude" : "Take out"); exc.type = "button";
          exc.addEventListener("click", function () { mark(r.key, false); });
          li.appendChild(inc); li.appendChild(exc);
          ul.appendChild(li);
        });
      } catch (e) { notice(e.message, "error"); }
    }, 400);
  }

  // --- members ------------------------------------------------------------------------

  async function loadMembers() {
    if (!state.open) return;
    try {
      var res = await api("/lists/" + encodeURIComponent(state.open) + "/members?offset=" + state.offset + "&limit=" + state.limit);
      state.total = res.total;
      renderMembers(res);
    } catch (e) { notice(e.message, "error"); }
  }

  function renderMembers(res) {
    var dynamic = state.detail.list.kind === "dynamic";
    text($("ls_membersTitle"), dynamic ? "Members as of the last run" : "Members (frozen)");
    var cols = [];
    (res.members || []).forEach(function (m) { Object.keys(m.values || {}).forEach(function (k) { if (cols.indexOf(k) < 0) cols.push(k); }); });
    var head = $("ls_memberHead");
    head.textContent = "";
    var tr = el("tr");
    ["Type", "Name"].concat(cols).concat([""]).forEach(function (h) { tr.appendChild(el("th", null, h)); });
    head.appendChild(tr);
    var tb = $("ls_memberRows");
    tb.textContent = "";
    (res.members || []).forEach(function (m) {
      var r = el("tr");
      r.appendChild(el("td", null, TYPE_ONE[m.type] || m.type));
      var name = el("td", m.missing ? "ls__missing" : null, m.name + (m.entry === "include" ? " (always included)" : m.hand ? " (added by hand)" : ""));
      r.appendChild(name);
      cols.forEach(function (c) { var v = (m.values || {})[c]; r.appendChild(el("td", null, v == null || v === "" ? "—" : String(v))); });
      var td = el("td");
      var b = el("button", "cm__rowbtn", dynamic ? "Always exclude" : "Take out"); b.type = "button";
      b.addEventListener("click", function () { mark(m.key, false); });
      td.appendChild(b); r.appendChild(td);
      tb.appendChild(r);
    });
    var end = Math.min(state.offset + state.limit, res.total);
    text($("ls_memberCount"), res.total ? (state.offset + 1) + "–" + end + " of " + res.total : "");
    var empty = $("ls_membersEmpty");
    if (!res.total) {
      empty.textContent = res.neverRun ? "Never run — save the recipe, then press " + $("ls_runBtn").textContent + "." : "Nobody is on this list.";
      show(empty);
    } else hide(empty);
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
  $("ls_retireBtn").addEventListener("click", retireOrReactivate);
  $("ls_deleteBtn").addEventListener("click", deleteList);
  $("ls_addStepBtn").addEventListener("click", addStep);
  $("ls_previewBtn").addEventListener("click", function () { preview(null); });
  $("ls_lKind").addEventListener("change", function () { markDirty(); renderKindHint(); });
  $("ls_lName").addEventListener("input", markDirty);
  $("ls_lNotes").addEventListener("input", markDirty);
  $("ls_searchBox").addEventListener("input", onSearch);
  $("ls_searchType").addEventListener("change", onSearch);
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
