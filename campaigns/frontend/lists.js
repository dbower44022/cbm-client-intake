/* Campaign lists (build plan § 7c.6; rulings 58–68). One page: the lists on
   the left, the open list on the right — its recipe, its hand edits or
   standing entries, its members. Vanilla JS, no build step. Buttons are never
   disabled: each one checks on click and says what is missing. */
(function () {
  "use strict";
  var API = "/campaigns/api";
  var state = { session: null, cat: null, lists: [], open: null, detail: null,
                recipe: { steps: [] }, counts: {}, offset: 0, limit: 50, total: 0, dirty: false };

  function $(id) { return document.getElementById(id); }
  function show(el) { if (el) el.hidden = false; }
  function hide(el) { if (el) el.hidden = true; }
  function text(el, v) { if (el) el.textContent = v == null ? "" : String(v); }
  function el(tag, cls, content) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (content != null) e.textContent = content;
    return e;
  }
  function fmtDate(v) {
    if (!v) return "—";
    var d = new Date(v);
    return isNaN(d) ? String(v) : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }
  function notice(msg, kind) {
    var n = $("notice");
    if (!msg) { hide(n); return; }
    n.textContent = msg;
    n.className = "cm__notice" + (kind ? " cm__notice--" + kind : "");
    show(n);
    if (kind === "ok") setTimeout(function () { if (n.textContent === msg) hide(n); }, 6000);
  }

  async function api(path, opts) {
    opts = opts || {};
    var ctrl = new AbortController();
    var waitMs = opts.timeoutMs || 120000;
    var timer = setTimeout(function () { ctrl.abort(); }, waitMs);
    var init = { method: opts.method || "GET", headers: { Accept: "application/json" }, signal: ctrl.signal, credentials: "same-origin" };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    var res;
    try { res = await fetch(API + path, init); }
    catch (e) {
      if (e && e.name === "AbortError") throw Object.assign(new Error("The server did not answer within " + Math.round(waitMs / 1000) + " seconds. It may still be working: wait a minute, then reload to see whether it finished."), { status: 0 });
      throw Object.assign(new Error("The server could not be reached — check the connection, then try again."), { status: 0 });
    }
    finally { clearTimeout(timer); }
    if (res.status === 401) { location.assign("/?next=" + encodeURIComponent("/campaigns/lists.html")); throw Object.assign(new Error("Signed out"), { status: 401 }); }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      var err = new Error((data && data.detail) || ("Request failed (" + res.status + ")"));
      err.status = res.status;
      throw err;
    }
    return data;
  }

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

  // --- the page's own dialog (never the browser's) ----------------------------------------

  var dialog = { resolve: null, required: false };
  function ask(title, message, opts) {
    opts = opts || {};
    text($("modalTitle"), title);
    text($("modalText"), message || "");
    text($("modalMsg"), "");
    var wrap = $("modalInputWrap");
    if (opts.input) {
      text($("modalInputLabel"), opts.input);
      $("modalInput").value = opts.value || "";
      show(wrap);
    } else hide(wrap);
    dialog.required = !!opts.required;
    text($("modalOk"), opts.ok || "OK");
    show($("modal"));
    if (opts.input) setTimeout(function () { $("modalInput").focus(); }, 0);
    return new Promise(function (resolve) { dialog.resolve = resolve; });
  }
  function closeDialog(value) {
    hide($("modal"));
    var r = dialog.resolve; dialog.resolve = null;
    if (r) r(value);
  }
  $("modalOk").addEventListener("click", function () {
    if ($("modalInputWrap").hidden) { closeDialog(true); return; }
    var v = $("modalInput").value.trim();
    if (dialog.required && !v) { text($("modalMsg"), "This cannot be empty."); return; }
    closeDialog(v);
  });
  $("modalCancel").addEventListener("click", function () { closeDialog(null); });
  $("modalClose").addEventListener("click", function () { closeDialog(null); });
  $("modalInput").addEventListener("keydown", function (e) { if (e.key === "Enter") $("modalOk").click(); });

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
    var showRetired = $("showRetired").checked;
    var rows = state.lists.filter(function (l) { return showRetired || l.status !== "retired"; });
    var tb = $("listRows");
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
    text($("listCount"), rows.length + " list" + (rows.length === 1 ? "" : "s"));
    $("listsEmpty").hidden = rows.length > 0;
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
    show($("detail"));
    $("lName").value = l.name;
    $("lKind").value = l.kind;
    $("lNotes").value = l.notes || "";
    var badge = $("lStatus");
    badge.textContent = (l.status === "retired" ? "Retired" : "Active") + " · version " + l.version;
    badge.className = "cm__badge" + (l.status === "retired" ? " cm__badge--cancelled" : "");
    text($("retireBtn"), l.status === "retired" ? "Reactivate" : "Retire");
    renderKindHint();
    var run = l.lastRun || {};
    text($("runNote"), l.lastRunAt
      ? "Last run " + fmtDate(l.lastRunAt) + " by " + (l.lastRunBy || "—") + ": " + run.total + " members" +
        (l.kind === "static" ? " (frozen)." : " as of then — a campaign build runs it again.") +
        (run.version && run.version !== l.version ? " The recipe has changed since: run it again." : "")
      : "Never run.");
    var p = $("problems");
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
    var used = $("usedBy");
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
    var vs = $("versions");
    vs.textContent = "";
    (d.versions || []).forEach(function (v) {
      vs.appendChild(el("li", null, "Version " + v.version + " (" + v.kind + ") — " + (v.savedBy || "—") + ", " + fmtDate(v.savedAt)));
    });
  }

  function renderKindHint() {
    var k = $("lKind").value;
    text($("kindHint"), k === "static"
      ? "Static: Run builds the list once and freezes it. Ticking a member out, or adding one by hand, changes the frozen list; Run again keeps those changes."
      : "Dynamic: the recipe runs again at the start of every campaign build, so the list is always as of that day. A hand change is a standing entry — always include or always exclude — applied after the recipe.");
    text($("runBtn"), k === "static" ? (state.detail && state.detail.list.lastRunAt ? "Run again" : "Run and freeze") : "Run now");
  }

  // --- the recipe -------------------------------------------------------------------------

  // The amber box describes the SAVED recipe; once the recipe is being edited it
  // is out of date, so it goes until the next Save re-checks (live pass 10-21-26:
  // a new list's "needs at least one step" stayed up while its steps were built).
  function markDirty() { state.dirty = true; hide($("problems")); }

  function addStep() {
    var first = !state.recipe.steps.length;
    state.recipe.steps.push({ action: first ? "add" : "keep", type: "lead", conditions: [{ field: "", op: "", value: null }] });
    markDirty();
    renderSteps();
  }

  function renderSteps() {
    var host = $("steps");
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
      card.appendChild(el("p", "cm__hint ls__cond", "Adding contacts must name the contact types it reaches: add a condition \"Contact type includes any of …\" (ruling 60)."));
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
    var name = $("lName").value.trim();
    if (!name) { notice("Give the list a name.", "error"); return; }
    try {
      var res = await api("/lists/" + encodeURIComponent(state.open), { method: "PUT",
        body: { name: name, notes: $("lNotes").value, kind: $("lKind").value, recipe: state.recipe } });
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
      state.open = null; state.dirty = false; hide($("detail"));
      await loadLists();
      notice("List deleted.", "ok");
    } catch (e) { notice(e.message, "error"); }
  }

  // --- hand edits and standing entries ------------------------------------------------

  function renderHand() {
    var d = state.detail, dynamic = d.list.kind === "dynamic";
    text($("handTitle"), dynamic ? "Standing entries" : "Changed by hand");
    text($("handHint"), dynamic
      ? "Always include or always exclude, applied after the recipe on every run (ruling 65). Not a Do Not Contact — for a person no campaign may contact, use the lead's Do Not Contact."
      : "Records added or taken out by hand. Run again keeps them.");
    text($("handModeHead"), dynamic ? "Entry" : "Change");
    var rows = dynamic ? d.entries : d.hand;
    var tb = $("handRows");
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
    $("handEmpty").hidden = (rows || []).length > 0;
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
      var q = $("searchBox").value.trim();
      var ul = $("searchResults");
      ul.textContent = "";
      if (q.length < 2) return;
      try {
        var res = await api("/lists/search/records?type=" + encodeURIComponent($("searchType").value) + "&q=" + encodeURIComponent(q));
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
    text($("membersTitle"), dynamic ? "Members as of the last run" : "Members (frozen)");
    var cols = [];
    (res.members || []).forEach(function (m) { Object.keys(m.values || {}).forEach(function (k) { if (cols.indexOf(k) < 0) cols.push(k); }); });
    var head = $("memberHead");
    head.textContent = "";
    var tr = el("tr");
    ["Type", "Name"].concat(cols).concat([""]).forEach(function (h) { tr.appendChild(el("th", null, h)); });
    head.appendChild(tr);
    var tb = $("memberRows");
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
    text($("memberCount"), res.total ? (state.offset + 1) + "–" + end + " of " + res.total : "");
    var empty = $("membersEmpty");
    if (!res.total) {
      empty.textContent = res.neverRun ? "Never run — save the recipe, then press " + $("runBtn").textContent + "." : "Nobody is on this list.";
      show(empty);
    } else hide(empty);
  }

  // --- start ------------------------------------------------------------------------

  async function start() {
    try {
      state.session = await api("/session");
    } catch (e) {
      text($("offReason"), e.status === 404 ? "Marketing Management is switched off on this deployment." : e.message);
      show($("offPanel"));
      return;
    }
    if (state.session.user) { text($("whoName"), state.session.user.name || state.session.user.userName); show($("userCorner")); }
    if (!state.session.listsOn) {
      text($("offReason"), "Campaign lists are switched off on this deployment (System Settings → Features → Campaign lists).");
      show($("offPanel"));
      return;
    }
    try {
      state.cat = await api("/lists/catalogue");
    } catch (e) {
      text($("offReason"), e.message);
      show($("offPanel"));
      return;
    }
    show($("listsView"));
    await loadLists();
    var want = new URLSearchParams(location.search).get("list");
    if (want) openList(want, true);
  }

  $("newListBtn").addEventListener("click", newList);
  $("showRetired").addEventListener("change", renderLists);
  $("saveBtn").addEventListener("click", save);
  $("runBtn").addEventListener("click", runList);
  $("retireBtn").addEventListener("click", retireOrReactivate);
  $("deleteBtn").addEventListener("click", deleteList);
  $("addStepBtn").addEventListener("click", addStep);
  $("previewBtn").addEventListener("click", function () { preview(null); });
  $("lKind").addEventListener("change", function () { markDirty(); renderKindHint(); });
  $("lName").addEventListener("input", markDirty);
  $("lNotes").addEventListener("input", markDirty);
  $("searchBox").addEventListener("input", onSearch);
  $("searchType").addEventListener("change", onSearch);
  $("prevBtn").addEventListener("click", function () {
    if (state.offset === 0) { notice("This is the first page.", "warn"); return; }
    state.offset = Math.max(0, state.offset - state.limit); loadMembers();
  });
  $("nextBtn").addEventListener("click", function () {
    if (state.offset + state.limit >= state.total) { notice("This is the last page.", "warn"); return; }
    state.offset += state.limit; loadMembers();
  });
  window.addEventListener("beforeunload", function (e) { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });
  start();
})();
