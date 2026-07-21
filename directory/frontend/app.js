/* Workspace Directory — one shared frontend for all three kinds. Derives its
   kind (companies / contacts / mentors) and API base from its own URL. Grid
   (toolbar: Filter left, Search center, View/Edit right) + preview pane +
   detail pop-up (all data in view mode, switch to edit for owned records). */
(function () {
  "use strict";

  var segs = location.pathname.split("/");           // ["", "directory", "<kind>", ...]
  var KIND = (segs[2] || "companies").toLowerCase();
  var API = "/directory/" + KIND + "/api";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function show(e) { if (e) e.hidden = false; }
  function hide(e) { if (e) e.hidden = true; }

  var state = {
    session: null, columns: [], rows: [], selectedId: null,
    page: 1, pageSize: 50, total: 0, hasMore: false,
    orderBy: "", order: "asc", q: "", applied: {}, detailCache: {},
  };

  // ---- API helper ---------------------------------------------------------
  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    // Timeout-wrapped (CBMBusy.fetch): a hung request ends in a readable
    // message instead of silence. Falls back to plain fetch if busy.js
    // somehow did not load.
    var resp = await (window.CBMBusy && CBMBusy.fetch
      ? CBMBusy.fetch(API + path, opts)
      : fetch(API + path, opts));
    var data = null;
    try { data = await resp.json(); } catch (e) {}
    if (!resp.ok) {
      var msg = (data && data.detail) || ("Request failed (" + resp.status + ")");
      var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function fail(e) {
    if (e && e.status === 401) { location.href = "/?next=" + encodeURIComponent("/directory/" + KIND + "/"); return; }
    hide($("mainView"));
    $("msgText").textContent = (e && e.message) || "Something went wrong.";
    show($("msgView"));
  }

  function notify(msg) {
    var n = $("notice");
    n.textContent = msg; show(n);
    clearTimeout(notify._t);
    notify._t = setTimeout(function () { hide(n); }, 6000);
  }

  // ---- value rendering (type-aware, shared by grid/preview/view) ----------
  function fmtDate(v) { if (!v) return ""; var s = String(v).slice(0, 10); return s; }
  function fmtDateTime(v) {
    if (!v) return "";
    var d = new Date(String(v).replace(" ", "T") + (/[Zz]|[+\-]\d\d:?\d\d$/.test(String(v)) ? "" : "Z"));
    if (isNaN(d)) return String(v);
    return d.toLocaleString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function fmtPhone(v) { try { return (window.CBM && window.CBM.formatPhone) ? window.CBM.formatPhone(v) : v; } catch (e) { return v; } }

  function emailLink(addr) {
    try {
      if (window.CBMQuickMail && window.CBMQuickMail.emailLink) return window.CBMQuickMail.emailLink(addr);
    } catch (e) {}
    var a = el("a", null, addr); a.href = "mailto:" + addr; return a;
  }

  // Render a value into a container node (used by preview + view modal cells).
  function renderValue(node, type, value) {
    if (value == null || value === "" || (Array.isArray(value) && !value.length)) { node.textContent = "—"; return; }
    if (type === "email") { node.appendChild(emailLink(String(value))); return; }
    if (type === "phone") { var a = el("a", null, fmtPhone(String(value))); a.href = "tel:" + String(value).replace(/[^0-9+]/g, ""); node.appendChild(a); return; }
    if (type === "url") { var u = String(value); var href = /^https?:\/\//i.test(u) ? u : "https://" + u; var l = el("a", null, u); l.href = href; l.target = "_blank"; l.rel = "noopener"; node.appendChild(l); return; }
    if (type === "array") { var wrap = el("div", "dir__cell-chips"); (Array.isArray(value) ? value : [value]).forEach(function (v) { wrap.appendChild(el("span", "dir__pill", String(v))); }); node.appendChild(wrap); return; }
    if (type === "bool") { node.textContent = value ? "Yes" : "No"; return; }
    if (type === "date") { node.textContent = fmtDate(value); return; }
    if (type === "datetime") { node.textContent = fmtDateTime(value); return; }
    if (type === "html") { var d = el("div", "dir__val-html"); d.innerHTML = (window.CBMRichText && window.CBMRichText.sanitizeHtml) ? window.CBMRichText.sanitizeHtml(String(value)) : ""; node.appendChild(d); return; }
    if (type === "address") { node.style.whiteSpace = "pre-line"; node.textContent = String(value); return; }
    node.textContent = String(value);   // text / longtext / int / currency
  }

  // Compact grid-cell rendering (single-line-ish).
  function cellInto(td, type, value) {
    if (value == null || value === "" || (Array.isArray(value) && !value.length)) { td.textContent = ""; return; }
    if (type === "array") { td.textContent = (Array.isArray(value) ? value : [value]).join(", "); return; }
    if (type === "email") { td.appendChild(emailLink(String(value))); return; }
    if (type === "phone") { td.textContent = fmtPhone(String(value)); return; }
    if (type === "bool") { td.textContent = value ? "Yes" : "No"; return; }
    if (type === "date") { td.textContent = fmtDate(value); return; }
    if (type === "datetime") { td.textContent = fmtDateTime(value); return; }
    if (type === "url") { var u = String(value); var l = el("a", null, u); l.href = /^https?:\/\//i.test(u) ? u : "https://" + u; l.target = "_blank"; l.rel = "noopener"; td.appendChild(l); return; }
    if (type === "html") { td.textContent = String(value).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(); return; }
    td.textContent = String(value);
  }

  // ---- grid ---------------------------------------------------------------
  function setSort(key) {
    if (state.orderBy === key) { state.order = state.order === "asc" ? "desc" : "asc"; }
    else { state.orderBy = key; state.order = "asc"; }
    state.page = 1; loadRecords();
  }

  function renderGrid() {
    var head = $("gridHead"), body = $("gridBody");
    head.innerHTML = ""; body.innerHTML = "";
    var tr = el("tr");
    state.columns.forEach(function (c) {
      var th = el("th", null, c.label);
      if (c.sortable) {
        th.addEventListener("click", function () { setSort(c.key); });
        if (state.orderBy === c.key) { var ar = el("span", "dir__sortarrow", state.order === "asc" ? "▲" : "▼"); th.appendChild(ar); }
      } else { th.style.cursor = "default"; }
      tr.appendChild(th);
    });
    head.appendChild(tr);

    state.rows.forEach(function (r) {
      var row = el("tr");
      row.dataset.id = r.id;
      if (r.id === state.selectedId) row.classList.add("is-selected");
      state.columns.forEach(function (c, i) {
        var td = el("td");
        if (i === 0) {  // name column: link opens View
          var a = el("a", null, r[c.key] || "(no name)");
          a.href = "#";
          a.addEventListener("click", function (ev) { ev.preventDefault(); ev.stopPropagation(); selectRow(r.id); openView(r.id); });
          td.appendChild(a);
        } else { cellInto(td, c.type, r[c.key]); }
        row.appendChild(td);
      });
      row.addEventListener("click", function () { selectRow(r.id); });
      row.addEventListener("dblclick", function () { openView(r.id); });
      body.appendChild(row);
    });
    makeColumnsResizable($("grid"));

    var from = state.total ? (state.page - 1) * state.pageSize + 1 : 0;
    var to = (state.page - 1) * state.pageSize + state.rows.length;
    $("pageInfo").textContent = state.total ? ("Showing " + from + "–" + to + " of " + state.total) : "No records";
    $("prevBtn").disabled = state.page <= 1;
    $("nextBtn").disabled = !state.hasMore;
  }

  function makeColumnsResizable(table) {
    var ths = table.querySelectorAll("thead th");
    ths.forEach(function (th) {
      if (th.querySelector(".dir__grip")) return;
      var grip = el("span", "dir__grip");
      grip.addEventListener("click", function (e) { e.stopPropagation(); });
      grip.addEventListener("mousedown", function (e) {
        e.preventDefault(); e.stopPropagation();
        table.classList.add("dir__table--resized");
        table.querySelectorAll("thead th").forEach(function (h) { if (!h.style.width) h.style.width = h.offsetWidth + "px"; });
        var startX = e.pageX, startW = th.offsetWidth;
        function mv(ev) { th.style.width = Math.max(60, startW + ev.pageX - startX) + "px"; }
        function up() { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); }
        document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
      });
      th.appendChild(grip);
    });
  }

  function selectRow(id) {
    state.selectedId = id;
    $("gridBody").querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.id === id); });
    renderPreview(id);
  }

  async function loadRecords() {
    var params = new URLSearchParams({ q: state.q, page: String(state.page), pageSize: String(state.pageSize), order: state.order });
    if (state.orderBy) params.set("orderBy", state.orderBy);
    if (Object.keys(state.applied).length) params.set("filters", JSON.stringify(state.applied));
    try {
      var data = await api("/records?" + params.toString());
      state.columns = data.columns; state.rows = data.rows;
      state.total = data.total; state.hasMore = data.hasMore;
      renderGrid();
    } catch (e) { if (e.status === 401) return fail(e); notify(e.message); }
  }

  // ---- preview pane -------------------------------------------------------
  async function getDetail(id) {
    if (state.detailCache[id]) return state.detailCache[id];
    var d = await api("/records/" + id);
    state.detailCache[id] = d; return d;
  }

  function panelsInto(container, panels) {
    panels.forEach(function (p) {
      var block = el("div", "dir__panel");
      if (p.title) block.appendChild(el("h3", null, p.title));
      var dl = el("dl", "dir__kv");
      p.fields.forEach(function (f) {
        if (f.value == null || f.value === "" || (Array.isArray(f.value) && !f.value.length)) return; // hide empty in view
        dl.appendChild(el("dt", null, f.label));
        var dd = el("dd"); renderValue(dd, f.type, f.value); dl.appendChild(dd);
      });
      if (dl.children.length) { block.appendChild(dl); container.appendChild(block); }
    });
  }

  async function renderPreview(id) {
    var pane = $("preview");
    pane.innerHTML = "";
    pane.appendChild(el("p", "dir__preview-empty", "Loading…"));
    try {
      var d = await getDetail(id);
      pane.innerHTML = "";
      pane.appendChild(el("h2", null, d.name || "(no name)"));
      panelsInto(pane, d.panels);
    } catch (e) { pane.innerHTML = ""; pane.appendChild(el("p", "dir__restricted", e.message)); }
  }

  // ---- detail pop-up (view + edit) ---------------------------------------
  var editing = null;   // { id, snapshot: {name:value}, fields: [{name,type,options,getVal}] }

  function openModal() { show($("modal")); }
  function closeModal() { hide($("modal")); editing = null; hide($("modalFoot")); }

  function contactsInto(container, contacts) {
    if (!contacts || !contacts.length) return;
    var block = el("div", "dir__panel");
    block.appendChild(el("h3", null, "Company Contacts"));
    var table = el("table", "dir__contacts");
    var thead = el("thead"); var htr = el("tr");
    ["Name", "Phone", "Email"].forEach(function (h) { htr.appendChild(el("th", null, h)); });
    thead.appendChild(htr); table.appendChild(thead);
    var tbody = el("tbody");
    contacts.forEach(function (c) {
      var tr = el("tr");
      var nameTd = el("td");
      var a = el("a", null, c.name || "(no name)"); a.href = "#";
      a.addEventListener("click", function (ev) { ev.preventDefault(); openContactPeek(c.id); });
      nameTd.appendChild(a); tr.appendChild(nameTd);
      var phoneTd = el("td"); renderValue(phoneTd, "phone", c.phone); tr.appendChild(phoneTd);
      var emailTd = el("td"); renderValue(emailTd, "email", c.email); tr.appendChild(emailTd);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody); block.appendChild(table); container.appendChild(block);
  }

  async function openView(id) {
    try {
      var d = await getDetail(id);
      $("modalTitle").textContent = d.name || "(no name)";
      var body = $("modalBody"); body.innerHTML = "";
      panelsInto(body, d.panels);
      contactsInto(body, d.contacts);
      editing = null; hide($("modalFoot"));
      var eb = $("modalEditBtn"); eb.textContent = "Edit"; show(eb);
      eb.onclick = function () { openEdit(id); };
      openModal();
    } catch (e) { notify(e.message); }
  }

  async function openContactPeek(contactId) {
    var body = $("peekBody"); body.innerHTML = "";
    $("peekTitle").textContent = "Loading…";
    show($("peekModal"));
    try {
      var d = await api("/contactdetail/" + contactId);
      $("peekTitle").textContent = d.name || "Contact";
      panelsInto(body, d.panels);
      if (!body.children.length) body.appendChild(el("p", "dir__restricted", "No details to show."));
    } catch (e) { $("peekTitle").textContent = "Contact"; body.appendChild(el("p", "dir__restricted", e.message)); }
  }

  function fieldInput(f) {
    var wrap = el("div", "dir__field");
    if (f.type === "longtext" || f.type === "html") wrap.classList.add("dir__field--wide");
    var lab = el("label", null, f.label); wrap.appendChild(lab);
    var getVal, ctrl, richt = null;
    var opts = f.options || null;
    if (f.type === "array" && opts) {
      var grid = el("div", "dir__checkgrid");
      var cur = Array.isArray(f.value) ? f.value.slice() : [];
      opts.forEach(function (o) {
        var l = el("label"); var cb = el("input"); cb.type = "checkbox"; cb.value = o; cb.checked = cur.indexOf(o) >= 0;
        cb.addEventListener("change", markChanged); l.appendChild(cb); l.appendChild(document.createTextNode(o)); grid.appendChild(l);
      });
      wrap.appendChild(grid);
      getVal = function () { return Array.prototype.slice.call(grid.querySelectorAll("input:checked")).map(function (c) { return c.value; }); };
    } else if (opts) {  // single enum
      ctrl = el("select");
      ctrl.appendChild(el("option", null, "—")).value = "";
      opts.forEach(function (o) { var op = el("option", null, o); op.value = o; if (f.value === o) op.selected = true; ctrl.appendChild(op); });
      if (opts.indexOf(f.value) < 0 && f.value) { var ex = el("option", null, f.value + " (current)"); ex.value = f.value; ex.selected = true; ctrl.insertBefore(ex, ctrl.children[1]); }
      ctrl.addEventListener("change", markChanged); wrap.appendChild(ctrl);
      getVal = function () { return ctrl.value; };
    } else if (f.type === "bool") {
      ctrl = el("input"); ctrl.type = "checkbox"; ctrl.checked = !!f.value; ctrl.addEventListener("change", markChanged);
      lab.insertBefore(ctrl, lab.firstChild); lab.insertBefore(document.createTextNode(" "), ctrl.nextSibling);
      getVal = function () { return ctrl.checked; };
    } else if (f.type === "html") {
      var holder = el("div"); wrap.appendChild(holder);
      richt = (window.CBMRichText && window.CBMRichText.create) ? window.CBMRichText.create(f.value || "", { onInput: markChanged }) : null;
      if (richt) { holder.appendChild(richt); getVal = function () { return richt._cbmRichText.getValue(); }; }
      else { ctrl = el("textarea"); ctrl.value = f.value || ""; ctrl.addEventListener("input", markChanged); wrap.appendChild(ctrl); getVal = function () { return ctrl.value; }; }
    } else if (f.type === "longtext") {
      ctrl = el("textarea"); ctrl.value = f.value || ""; ctrl.addEventListener("input", markChanged); wrap.appendChild(ctrl);
      getVal = function () { return ctrl.value; };
    } else {
      ctrl = el("input"); ctrl.type = f.type === "int" ? "number" : (f.type === "date" ? "date" : (f.type === "datetime" ? "datetime-local" : "text"));
      ctrl.value = f.value == null ? "" : (f.type === "datetime" ? String(f.value).replace(" ", "T").slice(0, 16) : (f.type === "date" ? String(f.value).slice(0, 10) : f.value));
      ctrl.addEventListener("input", markChanged); wrap.appendChild(ctrl);
      getVal = function () { var v = ctrl.value; return f.type === "int" ? (v === "" ? null : Number(v)) : v; };
    }
    return { wrap: wrap, name: f.key, type: f.type, getVal: getVal };
  }

  function sameVal(a, b) {
    if (Array.isArray(a) || Array.isArray(b)) { a = a || []; b = b || []; return a.length === b.length && a.every(function (x) { return b.indexOf(x) >= 0; }); }
    if (a == null) a = ""; if (b == null) b = "";
    return String(a) === String(b);
  }

  function markChanged() {
    if (!editing) return;
    var changed = 0;
    editing.fields.forEach(function (f) {
      var now = f.getVal();
      var was = editing.snapshot[f.name];
      var dirty = !sameVal(now, was);
      f.control.wrap.classList.toggle("is-changed", dirty);
      if (dirty) changed++;
    });
    $("saveInfo").textContent = changed ? (changed + (changed === 1 ? " field changed" : " fields changed")) : "No changes yet";
    $("modalSaveBtn").disabled = !changed;
  }

  async function openEdit(id) {
    var d;
    try { d = await getDetail(id); } catch (e) { return notify(e.message); }
    // Mentors (and any handoff kind) edit in their own tool — own record only.
    if (d.editHandoff) {
      if (d.isOwn) { openWindow(d.editHandoff, "cbm-mentorprofile"); closeModal(); }
      else notify("You can only edit your own profile here. Open the CRM to edit other mentors, or ask CBM staff.");
      return;
    }
    if (!d.editable) { notify("You can only edit records you own — ask CBM staff if you need access."); return; }

    $("modalTitle").textContent = d.name || "(no name)";
    var body = $("modalBody"); body.innerHTML = "";
    editing = { id: id, snapshot: {}, fields: [] };
    function registerField(grid, f) {
      var ctl = fieldInput(f);
      ctl.control = ctl;   // self-ref used by markChanged toggling
      grid.appendChild(ctl.wrap);
      editing.snapshot[f.key] = f.value == null ? (f.type === "array" ? [] : "") : f.value;
      editing.fields.push({ name: f.key, type: f.type, getVal: ctl.getVal, control: ctl });
    }
    d.panels.forEach(function (p) {
      // An address field is editable via its sub-fields (Street/City/…).
      var editable = p.fields.filter(function (f) {
        return f.editable && (f.type !== "address" || (f.subFields && f.subFields.length));
      });
      if (!editable.length) return;
      var panel = el("div", "dir__form-panel");
      if (p.title) panel.appendChild(el("h3", null, p.title));
      var grid = el("div", "dir__form-grid");
      editable.forEach(function (f) {
        if (f.type === "address") { f.subFields.forEach(function (sf) { registerField(grid, sf); }); }
        else { registerField(grid, f); }
      });
      panel.appendChild(grid); body.appendChild(panel);
    });
    hide($("modalEditBtn"));
    show($("modalFoot"));
    $("saveInfo").textContent = "No changes yet"; $("modalSaveBtn").disabled = true;
    openModal();
  }

  async function saveEdit() {
    if (!editing) return;
    var changes = {};
    editing.fields.forEach(function (f) {
      var now = f.getVal();
      if (!sameVal(now, editing.snapshot[f.name])) changes[f.name] = now;
    });
    if (!Object.keys(changes).length) { closeModal(); return; }
    $("modalSaveBtn").disabled = true; $("saveInfo").textContent = "Saving…";
    try {
      await api("/records/" + editing.id, { method: "PUT", body: JSON.stringify({ changes: changes }) });
      delete state.detailCache[editing.id];
      var id = editing.id; closeModal();
      notify("Saved.");
      loadRecords();                    // refresh grid values
      if (state.selectedId === id) renderPreview(id);
    } catch (e) { $("saveInfo").textContent = e.message; $("modalSaveBtn").disabled = false; }
  }

  // ---- tab de-duplication (workspace windowing) ---------------------------
  function openWindow(url, name) {
    var w = window.open(url, name);
    try { if (w) w.focus(); } catch (e) {}
    return w;
  }

  // ---- filters ------------------------------------------------------------
  function renderChips() {
    var box = $("filterChips"); box.innerHTML = "";
    (state.session.filters || []).forEach(function (f) {
      var v = state.applied[f.key];
      if (v == null || v === "" || (Array.isArray(v) && !v.length)) return;
      var label = f.label + ": " + (Array.isArray(v) ? v.join(", ") : (f.type === "bool" ? (v ? "Yes" : "No") : v));
      var chip = el("span", "dir__chip"); chip.appendChild(document.createTextNode(label));
      var x = el("button", null, "×"); x.title = "Remove filter";
      x.addEventListener("click", function () { delete state.applied[f.key]; renderChips(); renderFilterPanel(); state.page = 1; loadRecords(); });
      chip.appendChild(x); box.appendChild(chip);
    });
  }

  function renderFilterPanel() {
    var panel = $("filterPanel"); panel.innerHTML = "";
    (state.session.filters || []).forEach(function (f) {
      var g = el("div", "dir__filtergroup");
      g.appendChild(el("span", null, f.label));
      if (f.type === "bool") {
        var l = el("label", "dir__filteropt"); var cb = el("input"); cb.type = "checkbox"; cb.checked = !!state.applied[f.key];
        cb.addEventListener("change", function () { if (cb.checked) state.applied[f.key] = true; else delete state.applied[f.key]; });
        l.appendChild(cb); l.appendChild(document.createTextNode(" " + f.label)); g.appendChild(l);
      } else {
        var cur = state.applied[f.key] || [];
        f.options.forEach(function (o) {
          var l = el("label", "dir__filteropt"); var cb = el("input"); cb.type = "checkbox"; cb.value = o; cb.checked = cur.indexOf(o) >= 0;
          cb.dataset.key = f.key; l.appendChild(cb); l.appendChild(document.createTextNode(" " + o)); g.appendChild(l);
        });
      }
      panel.appendChild(g);
    });
    var actions = el("div", "dir__filteractions");
    var apply = el("button", "cbm-button dir__sm", "Apply");
    apply.addEventListener("click", applyFilters);
    var clear = el("button", "cbm-button cbm-button--secondary dir__sm", "Clear");
    clear.addEventListener("click", function () { state.applied = {}; renderFilterPanel(); renderChips(); state.page = 1; loadRecords(); });
    actions.appendChild(apply); actions.appendChild(clear); panel.appendChild(actions);
  }

  function applyFilters() {
    var panel = $("filterPanel");
    (state.session.filters || []).forEach(function (f) {
      if (f.type === "bool") return; // handled live on the checkbox above
      var checked = Array.prototype.slice.call(panel.querySelectorAll('input[data-key="' + f.key + '"]:checked')).map(function (c) { return c.value; });
      if (checked.length) state.applied[f.key] = checked; else delete state.applied[f.key];
    });
    renderChips(); hide(panel); $("filterBtn").setAttribute("aria-expanded", "false");
    state.page = 1; loadRecords();
  }

  // ---- splitter -----------------------------------------------------------
  function initSplitter() {
    var split = $("split"), preview = $("preview");
    split.addEventListener("mousedown", function (e) {
      e.preventDefault();
      var startX = e.pageX, startW = preview.offsetWidth;
      function mv(ev) { preview.style.flexBasis = Math.max(180, startW - (ev.pageX - startX)) + "px"; }
      function up() { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); }
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
    });
  }

  // ---- wiring -------------------------------------------------------------
  function wire() {
    var t = null;
    $("search").addEventListener("input", function () { clearTimeout(t); t = setTimeout(function () { state.q = $("search").value.trim(); state.page = 1; loadRecords(); }, 300); });
    $("filterBtn").addEventListener("click", function () {
      var p = $("filterPanel"); var open = p.hidden; if (open) renderFilterPanel();
      p.hidden = !open; $("filterBtn").setAttribute("aria-expanded", String(open));
    });
    $("viewBtn").addEventListener("click", function () { if (state.selectedId) openView(state.selectedId); else notify("Select a record first, then click View."); });
    $("editBtn").addEventListener("click", function () { if (state.selectedId) openEdit(state.selectedId); else notify("Select a record first, then click Edit."); });
    $("prevBtn").addEventListener("click", function () { if (state.page > 1) { state.page--; loadRecords(); } });
    $("nextBtn").addEventListener("click", function () { if (state.hasMore) { state.page++; loadRecords(); } });
    $("modalClose").addEventListener("click", closeModal);
    $("modalCancelBtn").addEventListener("click", closeModal);
    $("modalSaveBtn").addEventListener("click", saveEdit);
    $("modal").addEventListener("click", function (e) { if (e.target === $("modal")) closeModal(); });
    $("peekClose").addEventListener("click", function () { hide($("peekModal")); });
    $("peekModal").addEventListener("click", function (e) { if (e.target === $("peekModal")) hide($("peekModal")); });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!$("peekModal").hidden) hide($("peekModal"));   // close the nested one first
      else if (!$("modal").hidden) closeModal();
    });
    $("logoutBtn").addEventListener("click", async function () { try { await api("/logout", { method: "POST" }); } catch (e) {} location.href = "/"; });
    initSplitter();
  }

  (async function init() {
    try { if (window.CBMQuickMail) window.CBMQuickMail.apiBase = API; } catch (e) {}
    try {
      var s = await api("/session");
      state.session = s;
      document.title = "CBM — " + s.title;
      $("title").textContent = s.title;
      $("whoName").textContent = s.name || s.userName;
      show($("mainView"));
      wire();
      renderChips();
      await loadRecords();
    } catch (e) { fail(e); }
  })();
})();
