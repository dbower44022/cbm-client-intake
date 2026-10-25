/* The import tool — the Imports tab of Marketing Management (build plan
 * § 7e.7), on when the deployment's Import templates switch is on.
 *
 * Templates and history share the tab, and Import… is the one way in. The
 * flow is: choose the file → (which sheet) → the closest template is suggested
 * with every difference shown, or the columns are mapped by hand with a fix
 * picker beside each one → the preview, which the delivery worker computes
 * while this page polls → the walk-through with the spreadsheet values beside
 * the lead fields, each problem row's reason and an Exclude box → confirm →
 * the summary with Show these leads. History rows gain Undo this import.
 *
 * Every button stays visible and clickable; validation happens on click. The
 * file travels as base64 inside the JSON post, like the CSV text always has.
 *
 * Loaded by index.html after app.js; reaches the page through
 * window.CBMMarketing. Its own element ids are prefixed im_.
 */
(function () {
  "use strict";
  var M = window.CBMMarketing;
  if (!M) return;

  function $(id) { return document.getElementById(id); }
  var show = M.show, hide = M.hide, text = M.text, el = M.el, notice = M.notice, api = M.api, fmtDate = M.fmtDate;
  var openModal = M.openModal, closeModal = M.closeModal, modalMsg = M.modalMsg, ask = M.ask;

  var state = { templates: [], fields: [], entersAt: ["Unqualified", "Qualified"], sources: [], batches: [], partners: null, armed: null };
  var POLL_MS = 3000, STALL_MS = 120000, PART = 100;
  var RIDE = "", IGNORE = "__ignore", SPLIT = "__split";
  var OUTCOME_WORDS = { create: "New lead", fills: "Fills a lead", already_known: "Duplicate of a company or contact", known_row: "Repeat row", duplicate: "Repeat row (in this file)", invalid: "Invalid" };
  var LEAD_LABELS = { businessName: "Business", firstName: "First name", lastName: "Last name", mailingAddressStreet: "Street", mailingAddressCity: "City", mailingAddressState: "State", mailingAddressPostalCode: "ZIP", website: "Website", email: "Email", phone: "Phone", externalReference: "Reference" };
  var ROW_TO_LEAD = { business_name: "businessName", contact_first_name: "firstName", contact_last_name: "lastName", mailing_street: "mailingAddressStreet", mailing_city: "mailingAddressCity", mailing_state: "mailingAddressState", mailing_zip: "mailingAddressPostalCode", website: "website", email: "email", phone: "phone", external_reference: "externalReference" };

  function on() { var s = M.session(); return !!(s && s.importTemplatesOn); }
  function fieldLabel(name) { var f = state.fields.filter(function (x) { return x.name === name; })[0]; return f ? f.label : name; }
  function btn(label, cls, onClick) { var b = el("button", "cbm-button " + (cls || ""), label); b.type = "button"; b.addEventListener("click", onClick); return b; }
  function option(sel, value, label) { var o = el("option", null, label); o.value = value; sel.appendChild(o); return o; }
  function field(host, label, input, wide) { var f = el("div", "cm__field" + (wide ? " cm__field--wide" : "")); var l = el("label", null, label); if (input.id) l.htmlFor = input.id; f.appendChild(l); f.appendChild(input); host.appendChild(f); return input; }

  // --- loading -------------------------------------------------------------------------------------
  async function load() {
    if (!on()) return;
    document.body.classList.add("cm--import-tool");
    try {
      var t = await api("/import-templates");
      state.templates = t.templates || []; state.fields = t.fields || []; state.entersAt = t.entersAt || state.entersAt; state.sources = t.sources || [];
      var h = await api("/prospects/imports");
      state.batches = h.batches || [];
    } catch (e) { notice(e.message, "error"); return; }
    renderTemplates(); renderHistory();
    if (M.batchOptions) M.batchOptions(state.batches);
  }

  function renderTemplates() {
    var body = $("im_templateRows"); if (!body) return; body.innerHTML = "";
    state.templates.forEach(function (t) {
      var tr = el("tr");
      var nTd = el("td"); var a = el("a", "cm__link", t.name); a.href = "#imports"; a.addEventListener("click", function (ev) { ev.preventDefault(); openTemplateEditor(t, null); }); nTd.appendChild(a); tr.appendChild(nTd);
      tr.appendChild(el("td", null, t.source));
      tr.appendChild(el("td", null, t.entersAt + (t.entersAt === "Qualified" && t.qualifiedBy ? " · by " + t.qualifiedBy : "")));
      tr.appendChild(el("td", null, t.listSource || "—"));
      tr.appendChild(el("td", null, t.referrerPartnerName || "—"));
      tr.appendChild(el("td", null, String(sourceColumns(t.mapping).length) + " columns, " + t.mapping.filter(function (e) { return e.fixed != null || e.join || e.split_name; }).length + " fixes"));
      tr.appendChild(el("td", null, (t.updatedBy || t.createdBy || "") + (t.updatedAt ? " · " + fmtDate(t.updatedAt) : "")));
      var act = el("td", "cm__rowactions");
      act.appendChild(btn("Edit", "cbm-button--secondary cm__smallbtn", function () { openTemplateEditor(t, null); }));
      act.appendChild(btn("Delete", "cbm-button--secondary cm__smallbtn", async function () {
        var ok = await ask("Delete this template?", "\"" + t.name + "\" is shared by the whole team. Imports already made with it are unchanged.", { ok: "Delete" });
        if (!ok) return;
        try { await api("/import-templates/" + encodeURIComponent(t.id), { method: "DELETE" }); notice("Template deleted.", "ok"); load(); } catch (e) { notice(e.message, "error"); }
      }));
      tr.appendChild(act);
      body.appendChild(tr);
    });
    text($("im_templateCount"), state.templates.length + (state.templates.length === 1 ? " template" : " templates"));
    $("im_templateEmpty").hidden = state.templates.length > 0;
  }

  function resultWords(b) {
    var r = b.result || b.counts || {};
    var parts = [];
    if (r.created != null) parts.push(r.created + " created");
    if (r.create != null && r.created == null) parts.push(r.create + " to create");
    if (r.filled) parts.push(r.filled + " filled"); else if (r.fills) parts.push(r.fills + " to fill");
    if (r.duplicates) parts.push(r.duplicates + " duplicates"); else if (r.alreadyKnown) parts.push(r.alreadyKnown + " duplicates");
    if (r.excluded) parts.push(r.excluded + " excluded");
    if (r.invalid) parts.push(r.invalid + " invalid");
    if (r.errors) parts.push(r.errors + " errors");
    return parts.join(", ") || "—";
  }

  function renderHistory() {
    var body = $("im_historyRows"); if (!body) return; body.innerHTML = "";
    state.batches.forEach(function (b) {
      var tr = el("tr");
      tr.appendChild(el("td", null, b.name));
      tr.appendChild(el("td", null, b.source + (b.templateName ? " · " + b.templateName : "")));
      tr.appendChild(el("td", null, b.fileName || "—"));
      tr.appendChild(el("td", "num", b.rowCount));
      var preview = b.planStatus || "ready";
      tr.appendChild(el("td", null, { queued: "waiting for the worker", running: "being checked", ready: "ready", failed: "failed" }[preview] || preview));
      var st = b.undoneAt ? "undone" : b.status;
      tr.appendChild(el("td", null, st));
      tr.appendChild(el("td", null, fmtDate(b.createdAt)));
      tr.appendChild(el("td", null, b.appliedAt ? fmtDate(b.appliedAt) : "—"));
      var res = el("td", null, resultWords(b));
      if (b.undoneAt) {
        var u = b.undoResult || {};
        var line = el("div", "cm__hint", "Undone " + fmtDate(b.undoneAt) + " by " + (b.undoneBy || "") + ": " + (u.deleted || []).length + " deleted, " + (u.touched || []).length + " left");
        if ((u.touched || []).length) { var which = el("a", "cm__link", " — which were left?"); which.href = "#imports"; which.addEventListener("click", function (ev) { ev.preventDefault(); showTouched(b, u); }); line.appendChild(which); }
        res.appendChild(line);
      }
      tr.appendChild(res);
      var act = el("td", "cm__rowactions");
      if (b.status === "applied") act.appendChild(btn("Show these leads", "cbm-button--secondary cm__smallbtn", function () { showLeads(b.name); }));
      if (b.status === "applied" && !b.undoneAt) act.appendChild(undoButton(b));
      if (b.status !== "applied" && preview !== "failed") act.appendChild(btn("Open preview", "cbm-button--secondary cm__smallbtn", function () { openPreview(b.id, b.name); }));
      if (b.status !== "applied" && preview === "failed") act.appendChild(btn("Why it failed", "cbm-button--secondary cm__smallbtn", async function () { var p = await api("/prospects/import/" + encodeURIComponent(b.id)); await ask("The preview failed", p.planError || "No reason was recorded.", { ok: "Close" }); }));
      tr.appendChild(act);
      body.appendChild(tr);
    });
    text($("im_historyCount"), state.batches.length + " recent");
    $("im_historyEmpty").hidden = state.batches.length > 0;
  }

  function showLeads(batchName) {
    location.hash = "#prospects?batch=" + encodeURIComponent(batchName);
  }

  function showTouched(b, u) {
    var body = el("div", "cm__plan");
    body.appendChild(el("p", "cm__hint", "These leads were left because someone had worked on them since the import. Decide about each one by hand."));
    var tbl = el("table", "cm__grid"); var tb = el("tbody");
    (u.touched || []).forEach(function (t) { var tr = el("tr"); var td = el("td"); var a = el("a", "cm__link", t.name || t.id); a.href = "/campaigns/lead/" + encodeURIComponent(t.id); a.target = "cbm-lead-" + t.id; td.appendChild(a); tr.appendChild(td); tr.appendChild(el("td", null, t.why)); tb.appendChild(tr); });
    tbl.appendChild(tb); body.appendChild(tbl);
    openModal("Leads left after undoing \"" + b.name + "\"", body, null);
  }

  // Undo takes two presses, as New code does: the first arms the button and
  // names what it will do, the second runs it in parts of 100.
  function undoButton(b) {
    var button = btn("Undo this import", "cbm-button--secondary cm__smallbtn", async function () {
      if (state.armed !== b.id) {
        state.armed = b.id; text(button, "Press again to undo");
        notice("Undo deletes every lead this import created that nobody has worked on since; leads with a touch, a list, a conversation, a changed status or level, or an edit are listed and left. Fields it filled on older leads stay. Press the button again to go ahead.", "warn");
        setTimeout(function () { if (state.armed === b.id) { state.armed = null; text(button, "Undo this import"); } }, 15000);
        return;
      }
      state.armed = null; text(button, "Undoing…");
      try {
        var total = null;
        while (true) {
          var part = (await api("/prospects/import/" + encodeURIComponent(b.id) + "/undo", { method: "POST", timeoutMs: 180000, body: { maxLeads: PART } })).result;
          total = part.total;
          if (part.errors && part.errors.length) { notice(part.errors.length + " lead(s) could not be deleted: " + part.errors[0].error + " The rest are done; press Undo again to retry.", "error"); break; }
          if (!part.remaining) { notice("Undone: " + (total.deleted || []).length + " leads deleted, " + (total.touched || []).length + " left for a person to decide.", "ok"); break; }
        }
      } catch (e) { notice(e.message, "error"); }
      load();
    });
    return button;
  }

  // --- the mapping grid: one row per file column, a fix picker beside each -----------------------
  function sourceColumns(mapping) {
    var cols = [];
    (mapping || []).forEach(function (e) { ([].concat(e.column ? [e.column] : e.join ? e.join : e.split_name ? [e.split_name] : [])).forEach(function (c) { if (c && cols.indexOf(c) < 0) cols.push(c); }); });
    return cols;
  }
  function mappingGrid(columns, mapping) {
    var byColumn = {}, fixed = [], joins = [];
    (mapping || []).forEach(function (e) {
      if (e.ignore) byColumn[e.ignore] = IGNORE;
      else if (e.split_name) byColumn[e.split_name] = SPLIT;
      else if (e.column) byColumn[e.column] = e.field;
      else if (e.fixed != null) fixed.push({ field: e.field, value: e.fixed });
      else if (e.join) joins.push({ field: e.field, columns: e.join.slice(), with: e.with == null ? " " : e.with });
    });
    var all = columns.slice();
    sourceColumns(mapping).forEach(function (c) { if (all.indexOf(c) < 0) all.push(c); });
    Object.keys(byColumn).forEach(function (c) { if (all.indexOf(c) < 0) all.push(c); });
    var host = el("div", "cm__plan");
    var tbl = el("table", "cm__grid cm__mapgrid"); var thead = el("thead"); var hr = el("tr");
    ["Column in the file", "Becomes", ""].forEach(function (h) { hr.appendChild(el("th", null, h)); }); thead.appendChild(hr); tbl.appendChild(thead);
    var tb = el("tbody"); var selects = {};
    all.forEach(function (c) {
      var tr = el("tr");
      var nameTd = el("td", null, c); if (columns.indexOf(c) < 0) { nameTd.appendChild(el("span", "cm__badge cm__badge--late", "not in this file")); }
      tr.appendChild(nameTd);
      var sel = el("select"); sel.setAttribute("aria-label", "What the column " + c + " becomes");
      option(sel, RIDE, "Rides along as text on the lead"); option(sel, IGNORE, "Ignore this column"); option(sel, SPLIT, "Split into first and last name");
      state.fields.forEach(function (f) { option(sel, f.name, f.label); });
      sel.value = byColumn[c] != null ? byColumn[c] : (state.fields.some(function (f) { return f.name === c; }) ? c : RIDE);
      if (sel.value !== (byColumn[c] != null ? byColumn[c] : sel.value)) sel.value = RIDE;
      selects[c] = sel;
      var selTd = el("td"); selTd.appendChild(sel); tr.appendChild(selTd);
      tr.appendChild(el("td", "cm__hint", ""));
      tb.appendChild(tr);
    });
    tbl.appendChild(tb); host.appendChild(tbl);
    // Fixed values: a field the file lacks.
    var fixedBox = el("div", "cm__plan"); fixedBox.appendChild(el("p", "cm__hint", "Fixed values — a field every row gets that the file lacks (for example the state)."));
    var fixedRows = el("div", "cm__fixrows"); fixedBox.appendChild(fixedRows);
    function addFixed(f) {
      var row = el("div", "cm__fixrow"); var sel = el("select"); option(sel, "", "Choose a field"); state.fields.forEach(function (x) { option(sel, x.name, x.label); }); sel.value = f.field || "";
      var inp = el("input"); inp.type = "text"; inp.maxLength = 255; inp.placeholder = "Value"; inp.value = f.value || "";
      row.appendChild(sel); row.appendChild(inp); row.appendChild(btn("Remove", "cbm-button--secondary cm__smallbtn", function () { row.remove(); }));
      row._read = function () { return { fixed: inp.value, field: sel.value }; };
      fixedRows.appendChild(row);
    }
    fixed.forEach(addFixed);
    fixedBox.appendChild(btn("Add a fixed value", "cbm-button--secondary cm__smallbtn", function () { addFixed({}); }));
    host.appendChild(fixedBox);
    // Joins: two or more columns into one field.
    var joinBox = el("div", "cm__plan"); joinBox.appendChild(el("p", "cm__hint", "Joined columns — two columns into one field, with a separator (for example an area code and a number)."));
    var joinRows = el("div", "cm__fixrows"); joinBox.appendChild(joinRows);
    function addJoin(j) {
      var row = el("div", "cm__fixrow"); var sel = el("select"); option(sel, "", "Choose a field"); state.fields.forEach(function (x) { option(sel, x.name, x.label); }); sel.value = j.field || "";
      var a = el("select"), b = el("select"); [a, b].forEach(function (s, i) { option(s, "", i ? "and column" : "Column"); all.forEach(function (c) { option(s, c, c); }); s.value = (j.columns || [])[i] || ""; });
      var w = el("input"); w.type = "text"; w.maxLength = 5; w.placeholder = "Between"; w.value = j.with == null ? " " : j.with; w.className = "cm__joinwith";
      row.appendChild(sel); row.appendChild(a); row.appendChild(b); row.appendChild(w); row.appendChild(btn("Remove", "cbm-button--secondary cm__smallbtn", function () { row.remove(); }));
      row._read = function () { return { join: [a.value, b.value].filter(Boolean), field: sel.value, with: w.value }; };
      joinRows.appendChild(row);
    }
    joins.forEach(addJoin);
    joinBox.appendChild(btn("Add a join", "cbm-button--secondary cm__smallbtn", function () { addJoin({}); }));
    host.appendChild(joinBox);
    function read() {
      var out = [];
      Object.keys(selects).forEach(function (c) {
        var v = selects[c].value;
        if (v === RIDE) return;
        if (v === IGNORE) out.push({ ignore: c }); else if (v === SPLIT) out.push({ split_name: c }); else out.push({ column: c, field: v });
      });
      Array.prototype.forEach.call(fixedRows.children, function (r) { var e = r._read(); if (e.field || e.fixed) out.push(e); });
      Array.prototype.forEach.call(joinRows.children, function (r) { var e = r._read(); if (e.field || e.join.length) out.push(e); });
      return out;
    }
    return { node: host, read: read };
  }

  async function partnerOptions() {
    if (state.partners) return state.partners;
    try { state.partners = (await api("/prospects/partner-options")).options || []; } catch (e) { state.partners = []; notice("The partner list could not be read: " + e.message, "warn"); }
    return state.partners;
  }

  // The template's settings (also the one-off import's): how its rows enter.
  async function settingsForm(host, t) {
    var fields = el("div", "cm__fields");
    var src = el("select"); src.id = "im_t_source"; state.sources.forEach(function (s) { option(src, s, s); }); src.value = t.source || state.sources[0] || ""; field(fields, "Lead Source", src);
    var enters = el("select"); enters.id = "im_t_enters"; state.entersAt.forEach(function (s) { option(enters, s, s === "Qualified" ? "Qualified (its rows are real businesses worth working)" : "Unqualified (its rows wait in Review)"); }); enters.value = t.entersAt || "Unqualified"; field(fields, "Enters at", enters);
    var qb = el("input"); qb.id = "im_t_qb"; qb.type = "text"; qb.maxLength = 255; qb.placeholder = "Who or what qualifies these rows"; qb.value = t.qualifiedBy || ""; field(fields, "Qualified by (for Qualified)", qb);
    var ls = el("input"); ls.id = "im_t_ls"; ls.type = "text"; ls.maxLength = 255; ls.placeholder = "Vendor, chamber or partner"; ls.value = t.listSource || ""; field(fields, "List source", ls);
    var ref = el("select"); ref.id = "im_t_ref"; option(ref, "", "No referrer"); (await partnerOptions()).forEach(function (p) { option(ref, p.id, p.name); }); ref.value = t.referrerPartnerId || ""; field(fields, "Referrer partner (makes a reachable row Referred)", ref);
    host.appendChild(fields);
    return function read() {
      return { source: src.value, entersAt: enters.value, qualifiedBy: qb.value.trim(), listSource: ls.value.trim(),
               referrerPartnerId: ref.value, referrerPartnerName: ref.value ? ref.options[ref.selectedIndex].textContent : "" };
    };
  }

  async function openTemplateEditor(t, fileColumns) {
    t = t || { mapping: [] };
    var body = el("div", "cm__plan");
    var top = el("div", "cm__fields");
    var name = el("input"); name.id = "im_t_name"; name.type = "text"; name.maxLength = 200; name.placeholder = "e.g. Chamber member list"; name.value = t.name || ""; field(top, "Template name", name, true);
    body.appendChild(top);
    var readSettings = await settingsForm(body, t);
    body.appendChild(el("p", "cm__hint", "Columns are the file's headings, lower-cased with underscores. Business name and the four address parts must each come from somewhere — a column, a join or a fixed value."));
    var grid = mappingGrid(fileColumns || t.headerSignature || sourceColumns(t.mapping), t.mapping || []);
    body.appendChild(grid.node);
    openModal(t.id ? "Edit template" : "New template", body, async function () {
      if (!name.value.trim()) { modalMsg("Name the template.", "error"); return; }
      var payload = Object.assign({ name: name.value.trim(), mapping: grid.read(), headerSignature: fileColumns || t.headerSignature || [] }, readSettings());
      var res = t.id ? await api("/import-templates/" + encodeURIComponent(t.id), { method: "PUT", body: payload }) : await api("/import-templates", { method: "POST", body: payload });
      closeModal(); notice("Template \"" + res.template.name + "\" saved.", "ok"); load();
    }, "Save template");
  }

  // --- the import flow ---------------------------------------------------------------------------------
  function readFileBase64(f) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { var s = String(r.result || ""); resolve(s.slice(s.indexOf(",") + 1)); };
      r.onerror = function () { reject(new Error("The file could not be read.")); };
      r.readAsDataURL(f);
    });
  }
  function renamed(mapping, pairs) {
    var map = {}; pairs.forEach(function (p) { map[p.to] = p.from; });
    function r(c) { return map[c] || c; }
    return mapping.map(function (e) {
      if (e.column) return Object.assign({}, e, { column: r(e.column) });
      if (e.join) return Object.assign({}, e, { join: e.join.map(r) });
      if (e.split_name) return Object.assign({}, e, { split_name: r(e.split_name) });
      if (e.ignore) return Object.assign({}, e, { ignore: r(e.ignore) });
      return Object.assign({}, e);
    });
  }

  function openImport() {
    var body = el("div", "cm__plan");
    var fields = el("div", "cm__fields");
    var name = el("input"); name.id = "im_name"; name.type = "text"; name.maxLength = 255; name.placeholder = "e.g. Chamber members, October 2026"; field(fields, "Batch name", name, true);
    var file = el("input"); file.id = "im_file"; file.type = "file"; file.accept = ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; field(fields, "Spreadsheet (.xlsx or .csv)", file, true);
    body.appendChild(fields);
    var sheetBox = el("div", "cm__fields"); hide(sheetBox); body.appendChild(sheetBox);
    var recBox = el("div", "cm__plan"); body.appendChild(recBox);
    var flow = { base64: null, fileName: "", sheet: "", rec: null, choice: null, grid: null, readSettings: null, saveAs: null, useRenames: null, saveRenames: null };

    async function recognise() {
      recBox.innerHTML = ""; sheetBox.innerHTML = ""; hide(sheetBox);
      var f = file.files && file.files[0]; if (!f) return;
      flow.fileName = f.name; flow.base64 = await readFileBase64(f);
      modalMsg("Reading the file…", "ok");
      var rec;
      try {
        rec = await api("/prospects/import/recognise", { method: "POST", timeoutMs: 120000, body: { fileBase64: flow.base64, fileName: flow.fileName, sheet: flow.sheet } });
      } catch (e) {
        var d = e.data && e.data.detail;
        if (d && d.sheets) {
          var sel = el("select"); sel.id = "im_sheet"; option(sel, "", "Choose the sheet"); d.sheets.forEach(function (s) { option(sel, s, s); });
          field(sheetBox, "Which sheet?", sel, true); show(sheetBox);
          sel.addEventListener("change", function () { flow.sheet = sel.value; if (sel.value) recognise(); });
          modalMsg("The workbook has several sheets. Choose one.", "warn"); return;
        }
        modalMsg(e.message, "error"); return;
      }
      flow.rec = rec; modalMsg("", "");
      if (!name.value.trim()) name.value = f.name.replace(/\.(xlsx|csv)$/i, "");
      renderRecognition(rec);
    }
    file.addEventListener("change", function () { flow.sheet = ""; recognise().catch(function (e) { modalMsg(e.message, "error"); }); });

    function renderRecognition(rec) {
      recBox.innerHTML = "";
      recBox.appendChild(el("p", "cm__hint", rec.rowCount + " rows" + (rec.sheet ? " on the sheet " + rec.sheet : "") + "; columns: " + rec.columns.join(", ") + "."));
      if (rec.priorBatch) recBox.appendChild(el("p", "cm__hint", "This exact file was applied before (" + fmtDate(rec.priorBatch.appliedAt) + ")."));
      var pick = el("div", "cm__fields");
      var sel = el("select"); sel.id = "im_template";
      (rec.candidates || []).forEach(function (c) { option(sel, c.id, c.name + (rec.suggested && rec.suggested.id === c.id ? " — suggested, " : " — ") + Math.round(c.score * 100) + "% of its columns present"); });
      option(sel, "__new", "Map the columns myself");
      sel.value = rec.suggested ? rec.suggested.id : "__new";
      field(pick, "Template", sel, true);
      recBox.appendChild(pick);
      var detail = el("div", "cm__plan"); recBox.appendChild(detail);
      async function drawChoice() {
        detail.innerHTML = ""; flow.choice = sel.value; flow.grid = null; flow.readSettings = null; flow.useRenames = null; flow.saveRenames = null; flow.saveAs = null;
        if (sel.value === "__new") {
          flow.readSettings = await settingsForm(detail, {});
          detail.appendChild(el("p", "cm__hint", "Beside each column, choose the lead field it becomes, or a fix: ignore it, split a full name, add a fixed value, or join two columns."));
          flow.grid = mappingGrid(rec.columns, rec.identityMapping || []);
          detail.appendChild(flow.grid.node);
          var saveRow = el("div", "cm__fields");
          var saveAs = el("input"); saveAs.id = "im_saveas"; saveAs.type = "text"; saveAs.maxLength = 200; saveAs.placeholder = "Leave empty to import without saving a template";
          field(saveRow, "Save as a template named", saveAs, true); detail.appendChild(saveRow); flow.saveAs = saveAs;
          return;
        }
        var t = state.templates.filter(function (x) { return x.id === sel.value; })[0];
        if (!t) return;
        var diff = rec.suggested && rec.suggested.id === t.id ? rec.suggested : differences(t, rec.columns);
        var facts = el("dl", "cm__facts");
        [["Lead Source", t.source], ["Enters at", t.entersAt + (t.qualifiedBy ? " · by " + t.qualifiedBy : "")], ["List source", t.listSource || "—"], ["Referrer", t.referrerPartnerName || "—"]].forEach(function (p) { facts.appendChild(el("dt", null, p[0])); facts.appendChild(el("dd", null, p[1])); });
        detail.appendChild(facts);
        var list = el("ul", "cm__difflist");
        if (!diff.new.length && !diff.missing.length && !diff.renamed.length) list.appendChild(el("li", null, "The file's columns match this template exactly."));
        diff.new.forEach(function (c) { list.appendChild(el("li", null, "New column \"" + c + "\" — not in the template; it rides along as text on each lead.")); });
        diff.missing.forEach(function (c) { list.appendChild(el("li", "cm__diff--missing", "Missing column \"" + c + "\" — the template expects it and the file has no such column. Its field will be empty" + (requiredColumn(t, c) ? ", and it is required: the import will stop" : "") + ".")); });
        if (diff.renamed.length) {
          var li = el("li");
          var lab = el("label", "cm__check"); var cb = el("input"); cb.type = "checkbox"; cb.checked = true; cb.id = "im_userenames"; lab.appendChild(cb);
          lab.appendChild(el("span", null, " Likely renamed: " + diff.renamed.map(function (r) { return "\"" + r.from + "\" for \"" + r.to + "\""; }).join(", ") + ". Read the columns as the template's."));
          li.appendChild(lab); list.appendChild(li); flow.useRenames = cb;
          var li2 = el("li"); var lab2 = el("label", "cm__check"); var cb2 = el("input"); cb2.type = "checkbox"; cb2.id = "im_saverenames"; lab2.appendChild(cb2); lab2.appendChild(el("span", null, " Save the renames to the template, so next month's file is recognised as it is.")); li2.appendChild(lab2); list.appendChild(li2); flow.saveRenames = cb2;
        }
        detail.appendChild(list);
        detail.appendChild(btn("Edit this template", "cbm-button--secondary cm__smallbtn", function () { openTemplateEditor(t, rec.columns); }));
        flow.diff = diff;
      }
      sel.addEventListener("change", function () { drawChoice().catch(function (e) { modalMsg(e.message, "error"); }); });
      drawChoice().catch(function (e) { modalMsg(e.message, "error"); });
    }
    function requiredColumn(t, c) {
      var req = { business_name: 1, mailing_street: 1, mailing_city: 1, mailing_state: 1, mailing_zip: 1 };
      return (t.mapping || []).some(function (e) { return (e.column === c || (e.join || []).indexOf(c) >= 0) && req[e.field]; });
    }
    function differences(t, columns) {
      var cols = sourceColumns(t.mapping); var present = {}; columns.forEach(function (c) { present[c] = 1; });
      return { new: columns.filter(function (c) { return cols.indexOf(c) < 0; }), missing: cols.filter(function (c) { return !present[c]; }), renamed: [] };
    }

    openModal("Import leads", body, async function () {
      if (!name.value.trim()) { modalMsg("Name the batch.", "error"); return; }
      if (!flow.base64 || !flow.rec) { modalMsg("Choose a spreadsheet first.", "error"); return; }
      var req = { name: name.value.trim(), fileBase64: flow.base64, fileName: flow.fileName, sheet: flow.sheet };
      if (flow.choice === "__new") {
        var s = flow.readSettings(); Object.assign(req, s, { mapping: flow.grid.read() });
        if (flow.saveAs && flow.saveAs.value.trim()) {
          var saved = await api("/import-templates", { method: "POST", body: Object.assign({ name: flow.saveAs.value.trim(), mapping: req.mapping, headerSignature: flow.rec.columns }, s) });
          notice("Template \"" + saved.template.name + "\" saved.", "ok"); req = { name: req.name, fileBase64: req.fileBase64, fileName: req.fileName, sheet: req.sheet, templateId: saved.template.id };
        }
      } else {
        var t = state.templates.filter(function (x) { return x.id === flow.choice; })[0];
        var pairs = flow.useRenames && flow.useRenames.checked ? (flow.diff.renamed || []) : [];
        if (pairs.length) {
          var mapping = renamed(t.mapping, pairs);
          if (flow.saveRenames && flow.saveRenames.checked) {
            var upd = await api("/import-templates/" + encodeURIComponent(t.id), { method: "PUT", body: { name: t.name, source: t.source, listSource: t.listSource, qualifiedBy: t.qualifiedBy, entersAt: t.entersAt, referrerPartnerId: t.referrerPartnerId, referrerPartnerName: t.referrerPartnerName, mapping: mapping, headerSignature: flow.rec.columns } });
            notice("Template \"" + upd.template.name + "\" updated with the renames.", "ok"); req.templateId = t.id;
          } else {
            Object.assign(req, { source: t.source, listSource: t.listSource, qualifiedBy: t.qualifiedBy, entersAt: t.entersAt, referrerPartnerId: t.referrerPartnerId, referrerPartnerName: t.referrerPartnerName, mapping: mapping });
          }
        } else req.templateId = t.id;
      }
      modalMsg("Queuing the preview…", "ok");
      var planned = await api("/prospects/import/plan", { method: "POST", timeoutMs: 120000, body: req });
      load();
      await openPreview(planned.batchId, planned.name, planned);
    }, "Preview");
  }

  // --- the preview: poll the worker, then the walk-through ------------------------------------------
  async function openPreview(batchId, batchName, first) {
    var body = el("div", "cm__plan");
    var progress = el("p", "cm__hint", "Waiting for the delivery worker to pick the preview up…"); body.appendChild(progress);
    var box = el("div", "cm__plan"); body.appendChild(box);
    var plan = first && first.planStatus === "ready" ? first : null;
    var excluded = {}, filter = "all";
    openModal("Preview — " + batchName, body, null);
    var lastChecked = -1, lastMove = Date.now(), stopped = false;
    M.onModalCancel(function () { stopped = true; });
    while (!plan && !stopped) {
      var p;
      try { p = await api("/prospects/import/" + encodeURIComponent(batchId)); } catch (e) { modalMsg(e.message, "error"); await wait(POLL_MS); continue; }
      if (p.planStatus === "ready") { plan = p; break; }
      if (p.planStatus === "failed") { progress.textContent = "The preview failed: " + (p.planError || "no reason was recorded") + ". Fix the file or the template and import again."; progress.className = "cm__hint cm__diff--missing"; return; }
      var checked = p.progress ? p.progress.checked : -1;
      if (checked !== lastChecked) { lastChecked = checked; lastMove = Date.now(); }
      progress.textContent = p.planStatus === "queued" ? "Waiting for the delivery worker to pick the preview up…"
        : "Checking every row against the companies, contacts and leads the CRM already holds — " + (p.progress ? p.progress.checked + " of " + p.progress.of + " checked" : "starting") + "…";
      if (Date.now() - lastMove > STALL_MS) progress.textContent += " Nothing has moved for two minutes: the delivery worker may be down, or its import poll is off (the setting Import plan poll seconds at /setup).";
      await wait(POLL_MS);
    }
    if (!plan) return;
    (plan.excludedRows || []).forEach(function (h) { excluded[h] = true; });
    progress.textContent = plan.priorBatch ? "This exact file was applied before (" + fmtDate(plan.priorBatch.appliedAt) + ")." : "";
    renderPlan();

    function renderPlan() {
      box.innerHTML = "";
      var c = plan.counts || {};
      var excludedN = Object.keys(excluded).filter(function (h) { return excluded[h]; }).length;
      var chips = el("div", "cm__counts");
      [["all", "All rows", c.rows], ["create", "New leads", c.create], ["fills", "Fill a lead", c.fills], ["already_known", "Duplicates", c.alreadyKnown], ["repeat", "Repeat rows", (c.knownRow || 0) + (c.duplicate || 0)], ["invalid", "Invalid", c.invalid], ["excluded", "Excluded", excludedN]].forEach(function (k) {
        var b = el("button", "cm__countchip" + (filter === k[0] ? " is-active" : "")); b.type = "button"; b.appendChild(el("strong", null, k[2] == null ? 0 : k[2])); b.appendChild(el("span", null, k[1]));
        b.addEventListener("click", function () { filter = k[0]; renderPlan(); }); chips.appendChild(b);
      });
      box.appendChild(chips);
      if (plan.ladder && c.qualified) box.appendChild(el("p", "cm__hint", c.qualified + " enter Qualified — " + (c.identified || 0) + " Identified, " + (c.contactable || 0) + " Contactable, " + (c.referred || 0) + " Referred; " + (c.unqualified || 0) + " enter Unqualified."));
      else box.appendChild(el("p", "cm__hint", (c.qualified || 0) + " enter Qualified, " + (c.unqualified || 0) + " enter Unqualified."));
      var rows = (plan.rows || []).filter(function (r) {
        if (filter === "all") return true;
        if (filter === "excluded") return excluded[r.hash];
        if (filter === "repeat") return r.outcome === "known_row" || r.outcome === "duplicate";
        return r.outcome === filter;
      });
      var tbl = el("table", "cm__grid cm__walk"); var thead = el("thead"); var hr = el("tr");
      ["Exclude", "Business", "Outcome", "Enters", "Spreadsheet → lead", "Note"].forEach(function (h) { hr.appendChild(el("th", null, h)); }); thead.appendChild(hr); tbl.appendChild(thead);
      var tb = el("tbody");
      rows.forEach(function (r) {
        var tr = el("tr" , excluded[r.hash] ? "cm__row--excluded" : "");
        var tick = el("td", "cm__tick");
        var writes = r.outcome === "create" || r.outcome === "already_known" || r.outcome === "fills";
        if (writes) { var cb = el("input"); cb.type = "checkbox"; cb.checked = !!excluded[r.hash]; cb.setAttribute("aria-label", "Exclude " + r.name); cb.addEventListener("change", function () { excluded[r.hash] = cb.checked; saveExcluded(); renderPlan(); }); tick.appendChild(cb); }
        tr.appendChild(tick);
        tr.appendChild(el("td", null, r.name || "(no name)"));
        tr.appendChild(el("td", null, OUTCOME_WORDS[r.outcome] || r.outcome));
        tr.appendChild(el("td", null, r.outcome === "create" ? (r.status || "") + (r.level ? " · " + r.level : "") : (r.outcome === "fills" ? "unchanged" : "—")));
        var vals = el("td"); var dl = el("dl", "cm__pairs");
        if (r.outcome === "fills") { Object.keys(r.fill || {}).forEach(function (k) { dl.appendChild(el("dt", null, LEAD_LABELS[k] || k)); dl.appendChild(el("dd", null, r.fill[k])); }); }
        else { Object.keys(ROW_TO_LEAD).forEach(function (k) { if (r.row && r.row[k]) { dl.appendChild(el("dt", null, LEAD_LABELS[ROW_TO_LEAD[k]])); dl.appendChild(el("dd", null, r.row[k])); } }); }
        vals.appendChild(dl); tr.appendChild(vals);
        tr.appendChild(el("td", "cm__hint", r.note || ""));
        tb.appendChild(tr);
      });
      tbl.appendChild(tb); box.appendChild(tbl);
      if ((plan.rows || []).length < (c.rows || 0)) box.appendChild(el("p", "cm__hint", "The walk-through shows the first " + plan.rows.length + " of " + c.rows + " rows; the counts and the write cover every row."));
      var toWrite = (c.create || 0) + (c.alreadyKnown || 0) + (c.fills || 0) - excludedN;
      var foot = el("div", "cm__actions");
      if (plan.status === "applied") foot.appendChild(el("p", "cm__hint", "This import has been written."));
      else foot.appendChild(btn(toWrite > 0 ? "Confirm and write " + toWrite + " row" + (toWrite === 1 ? "" : "s") : "Nothing to write", "", function () { confirmWrite(toWrite); }));
      box.appendChild(foot);
    }
    var saveTimer = null;
    function saveExcluded() {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(async function () {
        try { await api("/prospects/import/" + encodeURIComponent(batchId) + "/excluded", { method: "PUT", body: { hashes: Object.keys(excluded).filter(function (h) { return excluded[h]; }) } }); }
        catch (e) { modalMsg("The exclusions were not saved: " + e.message, "error"); }
      }, 400);
    }
    async function confirmWrite(toWrite) {
      if (toWrite <= 0) { modalMsg("Nothing to write — every row is known, invalid or excluded.", "warn"); return; }
      clearTimeout(saveTimer);
      try { await api("/prospects/import/" + encodeURIComponent(batchId) + "/excluded", { method: "PUT", body: { hashes: Object.keys(excluded).filter(function (h) { return excluded[h]; }) } }); }
      catch (e) { modalMsg("The exclusions were not saved: " + e.message, "error"); return; }
      var r = { created: 0, filled: 0, qualified: 0, unqualified: 0, duplicates: 0, excluded: 0, errors: 0 };
      try {
        while (true) {
          modalMsg("Writing — " + (r.created + r.duplicates + r.filled).toLocaleString() + " of " + toWrite.toLocaleString() + "…", "ok");
          var part = (await api("/prospects/import/apply", { method: "POST", timeoutMs: 180000, body: { batchId: batchId, maxRows: PART } })).result;
          ["created", "filled", "qualified", "unqualified", "duplicates", "errors"].forEach(function (k) { r[k] += part[k] || 0; });
          r.excluded = part.excluded || 0;
          if (part.errors) break;
          if (!part.remaining) break;
        }
      } catch (e) { modalMsg(e.message, "error"); return; }
      if (r.errors) { modalMsg(r.errors + " row(s) could not be written; the rest are saved. Press Confirm again to retry them — nothing is written twice.", "error"); load(); return; }
      box.innerHTML = ""; modalMsg("", "");
      progress.textContent = "Written.";
      var tilesHost = el("div", "cm__tiles");
      [["New leads", r.created], ["Enter Qualified", r.qualified], ["Enter Unqualified", r.unqualified], ["Leads filled", r.filled], ["Duplicates", r.duplicates], ["Excluded", r.excluded]].forEach(function (p) { var t = el("div", "cm__tile"); t.appendChild(el("div", "cm__tile-value", p[1])); t.appendChild(el("div", "cm__tile-label", p[0])); tilesHost.appendChild(t); });
      box.appendChild(tilesHost);
      var acts = el("div", "cm__actions");
      acts.appendChild(btn("Show these leads", "", function () { closeModal(); showLeads(batchName); }));
      acts.appendChild(btn("Close", "cbm-button--secondary", closeModal));
      box.appendChild(acts);
      load();
    }
  }

  function wait(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }

  if ($("im_newTemplateBtn")) $("im_newTemplateBtn").addEventListener("click", function () { if (!on()) { notice("Import templates are switched off on this deployment (Import templates at /setup).", "warn"); return; } openTemplateEditor(null, null); });

  // No onShow here: the page's own Imports loader hands the tab to this script
  // (loadImports delegates), so registering one would load it twice.
  window.CBMImports = { load: load, openImport: openImport, openPreview: openPreview };
})();
