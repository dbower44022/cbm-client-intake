/* Campaign Calls — the Calls tab of Marketing Management (build plan § 3.4 and
 * § 7e.2).
 *
 * Who sees a row is decided per campaign: the members of the teams named on
 * it. The page asks the server and shows what comes back; the server decides.
 * A caller from another team opens Marketing Management and sees this tab
 * alone. A row opens in place: the number, a notes box and the three outcomes.
 * Every button stays visible and clickable; validation happens on click.
 *
 * On a lead's row the form also asks for an email and a website: Interested
 * converts the lead only with one of them, and the server says so when it
 * could not.
 *
 * Loaded by index.html after app.js; reaches the page through
 * window.CBMMarketing. Its own element ids are prefixed cl_.
 */
(function () {
  "use strict";
  var M = window.CBMMarketing;
  if (!M) return;
  var state = { data: null, open: null };

  function $(id) { return document.getElementById(id); }
  var show = M.show, hide = M.hide, text = M.text, el = M.el, notice = M.notice, api = M.api;
  function fmtDate(v) {
    if (!v) return "—";
    var d = new Date(v.replace(" ", "T") + (v.length === 19 ? "Z" : ""));
    return isNaN(d.getTime()) ? v : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }

  // The shared grid (frontend/shared/grid.js; prds/shared-grid-plan.md § 8).
  // The call list sorts its data, not its drawn rows: an open call's form
  // row must stay under its call.
  var CALL_COLS = ["name", "person", "phone", "stage", "campaignName", "plannedAt"];
  var callGrid = null;
  function callGridOn() {
    if (callGrid || !window.CBMGrid) return;
    var ths = document.querySelectorAll("#cl_callGrid thead th");
    CALL_COLS.forEach(function (c, i) { if (ths[i]) ths[i].setAttribute("data-col", c); });
    callGrid = CBMGrid.enhance(document.getElementById("cl_callGrid"), { key: "marketing.calls", onSort: function () { render(); } });
  }
  function busy(promise) {
    var grid = document.getElementById("cl_callGrid");
    return window.CBMBusy && CBMBusy.loading && grid ? CBMBusy.loading(grid, promise) : promise;
  }

  async function load() {
    callGridOn();
    try {
      state.data = await busy(api("/calls"));
    } catch (e) { notice(e.message, "error"); return; }
    var d = state.data;
    text($("cl_callWarning"), d.warning);
    var msg = $("cl_callMessage");
    if (d.message) { msg.textContent = d.message; show(msg); } else hide(msg);
    var sel = $("cl_campaignFilter"), keep = sel.value;
    sel.innerHTML = "<option value=\"\">All</option>";
    (d.campaigns || []).forEach(function (c) { var o = el("option", null, c.name); o.value = c.id; sel.appendChild(o); });
    sel.value = keep;
    var briefs = $("cl_briefList"); briefs.innerHTML = "";
    (d.campaigns || []).forEach(function (c) {
      if (!c.brief) return;
      briefs.appendChild(el("h4", null, c.name));
      var div = el("div", "cm__prose cm__brief");
      div.innerHTML = window.CBMRichText && CBMRichText.sanitizeHtml ? CBMRichText.sanitizeHtml(c.brief) : "";
      if (!div.innerHTML) div.textContent = c.brief.replace(/<[^>]+>/g, " ");
      briefs.appendChild(div);
    });
    $("cl_briefs").hidden = !briefs.childNodes.length;
    // The side panel layout while the server says CALLS_PANEL is on.
    var panel = !!d.panel;
    $("cl_panelWrap").hidden = !panel;
    $("cl_classicWrap").hidden = panel;
    if (panel) {
      $("cl_briefs").hidden = true;
      var top = $("cl_briefTopList"); top.innerHTML = "";
      while (briefs.firstChild) top.appendChild(briefs.firstChild);
      $("cl_briefTop").hidden = !top.childNodes.length;
      renderPanel();
      return;
    }
    render();
  }

  function render() {
    var d = state.data || { rows: [] };
    var q = ($("cl_callSearch").value || "").toLowerCase(), camp = $("cl_campaignFilter").value;
    var rows = (d.rows || []).filter(function (r) {
      if (camp && r.campaignId !== camp) return false;
      return !q || [r.name, r.person, r.phone, r.campaignName, r.city].join(" ").toLowerCase().indexOf(q) >= 0;
    });
    if (callGrid && callGrid.keys().length) rows = CBMGrid.sortBy(rows, callGrid.keys(), function (r, col) { return r[col]; });
    var body = $("cl_callRows"); body.innerHTML = "";
    rows.forEach(function (r) {
      var tr = el("tr", "cm__callrow" + (state.open === r.touchId ? " is-open" : ""));
      tr.appendChild(el("td", null, r.name || "—"));
      tr.appendChild(el("td", null, r.person || "—"));
      var ph = el("td"); if (r.phone) { var a = el("a", "cm__phone", r.phone); a.href = "tel:" + r.phone.replace(/[^0-9+]/g, ""); ph.appendChild(a); } else ph.textContent = r.error || "—"; tr.appendChild(ph);
      tr.appendChild(el("td", null, r.stage || "—")); tr.appendChild(el("td", null, r.campaignName));
      tr.appendChild(el("td", null, fmtDate(r.plannedAt)));
      var aTd = el("td"); var b = el("button", "cm__rowbtn", state.open === r.touchId ? "Close" : "Record the call"); b.type = "button";
      b.addEventListener("click", function () { state.open = state.open === r.touchId ? null : r.touchId; render(); });
      aTd.appendChild(b); tr.appendChild(aTd);
      body.appendChild(tr);
      if (state.open === r.touchId) body.appendChild(recordRow(r));
    });
    text($("cl_callCount"), rows.length + " to call");
    $("cl_callsEmpty").hidden = rows.length > 0;
  }

  function recordRow(r) {
    var tr = el("tr", "cm__callrow is-open"); var td = el("td"); td.colSpan = 7;
    var form = el("div", "cm__callform");
    var who = el("div");
    who.appendChild(el("p", null, "Ring " + (r.person || r.name || "the number") + (r.name && r.person ? " at " + r.name : "") + ":"));
    if (r.phone) { var a = el("a", "cm__phone", r.phone); a.href = "tel:" + r.phone.replace(/[^0-9+]/g, ""); who.appendChild(a); }
    if (r.doNotCall) who.appendChild(el("p", "cm__notice cm__notice--error", "This number is now marked do-not-call or opted out. Do not ring it; record Declined if they asked not to be called."));
    form.appendChild(who);
    var nf = el("div", "cm__field cm__field--wide"); var nl = el("label", null, "Call notes"); nl.htmlFor = "cn_" + r.touchId;
    var notes = el("textarea"); notes.id = "cn_" + r.touchId; notes.maxLength = 8000; nf.appendChild(nl); nf.appendChild(notes); form.appendChild(nf);
    // Interested converts a lead only with an email or a website.
    var conv = null;
    if (r.kind === "prospect") {
      conv = {};
      var box = el("div", "cm__fields");
      box.appendChild(el("p", "cm__hint cm__field--wide", "If they are interested: ask for an email" + (r.business ? " or the business's website" : "") +
        ". Either one turns this lead into a Prospect" + (r.business ? " — a Company with its Contact" : "") + "; without one, Interested is recorded and the lead stays a lead." +
        (r.email || r.website ? " What the lead already holds is filled in below; check it with them." : "")));
      [["firstName", "First name", r.firstName || ""], ["lastName", "Last name", r.lastName || ""], ["email", "Email", r.email || ""], ["website", "Website", r.website || ""]].forEach(function (f) {
        var fd = el("div", "cm__field"); var lb = el("label", null, f[1]); var id = "cv_" + f[0] + "_" + r.touchId; lb.htmlFor = id;
        var inp = el("input"); inp.type = f[0] === "email" ? "email" : "text"; inp.id = id; inp.value = f[2]; inp.autocomplete = "off"; inp.maxLength = f[0] === "email" || f[0] === "website" ? 255 : 100;
        fd.appendChild(lb); fd.appendChild(inp); box.appendChild(fd); conv[f[0]] = inp;
      });
      form.appendChild(box);
    }
    var again = el("label", "cm__check"); var cb = el("input"); cb.type = "checkbox"; again.appendChild(cb); again.appendChild(document.createTextNode(" Call again (with No answer, or with Interested when they gave no email or website)")); form.appendChild(again);
    var acts = el("div", "cm__runactions");
    [["No answer", "cbm-button cbm-button--secondary"], ["Interested", "cbm-button"], ["Declined", "cbm-button cbm-button--secondary"]].forEach(function (o) {
      var b = el("button", o[1], o[0]); b.type = "button";
      b.addEventListener("click", async function () {
        if (cb.checked && o[0] === "Declined") { notice("Call again does not go with Declined — untick it, or choose another outcome.", "warn"); return; }
        var body = { outcome: o[0], notes: notes.value, callAgain: cb.checked };
        if (conv && o[0] === "Interested") {
          var em = conv.email.value.trim();
          if (em && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(em)) { notice("\u201c" + em + "\u201d is not an email address.", "warn"); conv.email.focus(); return; }
          body.email = em; body.website = conv.website.value.trim();
          body.firstName = conv.firstName.value.trim(); body.lastName = conv.lastName.value.trim();
        }
        try {
          var res = await api("/calls/" + encodeURIComponent(r.touchId) + "/outcome", { method: "POST", body: body });
          var extra = (res.consequences || []).length ? " (" + res.consequences.join(", ") + ")" : "";
          var warn = (res.warnings || []).slice(); if (res.notConverted) warn.unshift(res.notConverted);
          notice("Recorded " + o[0] + " for " + (r.person || r.name) + extra + "." + (warn.length ? " " + warn.join(" ") : ""), warn.length ? "warn" : "ok");
          state.open = null; load();
        } catch (e) { notice(e.message, "error"); }
      });
      acts.appendChild(b);
    });
    // An accidental "Record the call" closes again with nothing written.
    var cancel = el("button", "cbm-button cbm-button--secondary", "Cancel"); cancel.type = "button";
    cancel.addEventListener("click", function () { state.open = null; notice(""); render(); });
    acts.appendChild(cancel);
    form.appendChild(acts);
    td.appendChild(form); tr.appendChild(td);
    return tr;
  }

  /* ---------- the side panel (build plan § 7e.10) ---------- */

  var PANEL_COLS = ["name", "person", "phone", "level", "lastAt", "attempts", "campaignName"];
  var panelGrid = null;
  function panelGridOn() {
    if (panelGrid || !window.CBMGrid) return;
    var ths = document.querySelectorAll("#cl_panelGrid thead th");
    PANEL_COLS.forEach(function (c, i) { if (ths[i]) ths[i].setAttribute("data-col", c); });
    panelGrid = CBMGrid.enhance(document.getElementById("cl_panelGrid"), { key: "marketing.calls.panel", onSort: function () { renderPanel(); } });
  }

  function panelRows() {
    var d = state.data || { rows: [] };
    var q = ($("cl_callSearch").value || "").toLowerCase(), camp = $("cl_campaignFilter").value;
    var rows = (d.rows || []).filter(function (r) {
      if (camp && r.campaignId !== camp) return false;
      return !q || [r.name, r.person, r.phone, r.campaignName, r.city].join(" ").toLowerCase().indexOf(q) >= 0;
    });
    if (panelGrid && panelGrid.keys().length) {
      rows = CBMGrid.sortBy(rows, panelGrid.keys(), function (r, col) {
        return col === "lastAt" ? (r.lastAttempt || {}).at || "" : r[col];
      });
    }
    return rows;
  }

  function tel(phone) { var a = el("a", "cm__phone", phone); a.href = "tel:" + phone.replace(/[^0-9+]/g, ""); return a; }

  function renderPanel() {
    panelGridOn();
    var d = state.data || {};
    var rows = panelRows();
    var body = $("cl_panelRows"); body.innerHTML = "";
    rows.forEach(function (r) {
      var tr = el("tr", (state.open === r.touchId ? "is-open" : "") + (r.later ? " is-later" : ""));
      tr.appendChild(el("td", null, r.name || "—"));
      tr.appendChild(el("td", null, r.person || "—"));
      var ph = el("td");
      if (r.phone) { var a = tel(r.phone); a.addEventListener("click", function (e) { e.stopPropagation(); }); ph.appendChild(a); }
      else ph.textContent = r.error || "—";
      tr.appendChild(ph);
      tr.appendChild(el("td", null, r.level || "—"));
      var last = r.lastAttempt;
      tr.appendChild(el("td", null, last ? fmtDate(last.at) + (last.outcome ? " · " + last.outcome : "") : "—"));
      tr.appendChild(el("td", null, String(r.attempts || 0)));
      tr.appendChild(el("td", null, r.campaignName + (r.later ? " · call again " + fmtDate(r.plannedAt) : "")));
      tr.addEventListener("click", function () { openSide(r.touchId); });
      body.appendChild(tr);
    });
    $("cl_panelEmpty").hidden = rows.length > 0;
    var c = d.counts || { left: rows.length, calledToday: 0 };
    text($("cl_callCount"), c.left + " left to call · " + c.calledToday + " called today");
    renderDoneToday();
    if (state.open && !rows.some(function (r) { return r.touchId === state.open; })) state.open = null;
    drawSide();
  }

  function renderDoneToday() {
    var done = (state.data || {}).doneToday || [];
    var body = $("cl_doneRows"); body.innerHTML = "";
    done.forEach(function (x) {
      var tr = el("tr");
      [x.name || "—", x.person || "—", x.outcome || "—", fmtDate(x.doneAt), x.campaignName || "—"].forEach(function (v) { tr.appendChild(el("td", null, v)); });
      body.appendChild(tr);
    });
    $("cl_doneEmpty").hidden = done.length > 0;
    $("cl_doneGrid").hidden = !done.length;
    text($("cl_doneSummary"), "Done today (" + done.length + ")");
  }

  function openSide(touchId) { state.open = touchId; renderPanel(); }

  function rowById(id) { return ((state.data || {}).rows || []).filter(function (r) { return r.touchId === id; })[0] || null; }

  function fact(dl, label, value) {
    if (!value) return;
    dl.appendChild(el("dt", null, label)); dl.appendChild(el("dd", null, value));
  }

  function drawSide() {
    var side = $("cl_side"); side.innerHTML = "";
    var r = state.open ? rowById(state.open) : null;
    if (!r) { side.appendChild(el("p", "cm__hint", "Choose a row to see what we know and record the call.")); return; }
    side.appendChild(el("h3", null, (r.person || r.name || "This call") + (r.person && r.name ? " at " + r.name : "")));
    if (r.phone) side.appendChild(tel(r.phone)); else side.appendChild(el("p", "cm__notice cm__notice--error", r.error || "There is no number on this record."));
    if (r.doNotCall) side.appendChild(el("p", "cm__notice cm__notice--error", "This number is now marked do-not-call or opted out. Do not ring it; record Not interested if they asked not to be called."));
    if (r.later) side.appendChild(el("p", "cm__hint", "Planned for " + fmtDate(r.plannedAt) + ". You may call earlier."));

    side.appendChild(el("h4", null, "What we know"));
    var dl = el("dl");
    fact(dl, "Business", r.name); fact(dl, "Person", r.person); fact(dl, "City", r.city);
    fact(dl, r.kind === "prospect" ? "Status" : "Stage", r.stage); fact(dl, "Level", r.level);
    fact(dl, "Email", r.email); fact(dl, "Website", r.website);
    fact(dl, "Attempts", String(r.attempts || 0));
    if (r.lastAttempt) fact(dl, "Last attempt", fmtDate(r.lastAttempt.at) + (r.lastAttempt.outcome ? " · " + r.lastAttempt.outcome : ""));
    fact(dl, "Campaign", r.campaignName);
    side.appendChild(dl);

    side.appendChild(el("h4", null, "Their personal link"));
    var lk = el("div", "cm__calllink");
    if (r.link) {
      lk.appendChild(el("span", "cm__short", r.link));
      var copy = el("button", "cm__rowbtn", "Copy"); copy.type = "button";
      copy.addEventListener("click", function () {
        (navigator.clipboard ? navigator.clipboard.writeText(r.link) : Promise.reject(new Error("no clipboard")))
          .then(function () { notice("Copied the link for " + (r.person || r.name) + ".", "ok"); })
          .catch(function () { notice("Could not copy — select the link and copy it by hand.", "warn"); });
      });
      lk.appendChild(copy);
    }
    side.appendChild(lk);
    if (r.linkNote) side.appendChild(el("p", "cm__hint", r.linkNote));

    var nl = el("label", null, "Call notes"); nl.htmlFor = "cl_sideNotes";
    var notes = el("textarea"); notes.id = "cl_sideNotes"; notes.maxLength = 8000;
    side.appendChild(nl); side.appendChild(notes);

    var conv = null;
    if (r.kind === "prospect") {
      conv = {};
      var box = el("div", "cm__fields");
      box.appendChild(el("p", "cm__hint cm__field--wide", "If they are interested: ask for an email" + (r.business ? " or the business's website" : "") +
        ". Either one turns this lead into a Prospect; without one, Interested is recorded and the lead stays a lead."));
      [["firstName", "First name", r.firstName || ""], ["lastName", "Last name", r.lastName || ""], ["email", "Email", r.email || ""], ["website", "Website", r.website || ""]].forEach(function (f) {
        var fd = el("div", "cm__field"); var id = "cl_side_" + f[0]; var lb = el("label", null, f[1]); lb.htmlFor = id;
        var inp = el("input"); inp.type = f[0] === "email" ? "email" : "text"; inp.id = id; inp.value = f[2]; inp.autocomplete = "off";
        inp.maxLength = f[0] === "email" || f[0] === "website" ? 255 : 100;
        fd.appendChild(lb); fd.appendChild(inp); box.appendChild(fd); conv[f[0]] = inp;
      });
      side.appendChild(box);
    }

    var again = el("div", "cm__callagain"); again.hidden = true;
    again.appendChild(el("p", null, "When should they be called again?"));
    var picker = window.CBMDateTime ? CBMDateTime.create({}) : el("p", "cm__notice cm__notice--error", "The time picker did not load — refresh the page.");
    again.appendChild(picker);
    var plan = el("button", "cbm-button", "Plan the call"); plan.type = "button";
    again.appendChild(plan);

    var acts = el("div", "cm__runactions");
    function btn(label, cls, fn) { var b = el("button", cls, label); b.type = "button"; b.addEventListener("click", fn); acts.appendChild(b); return b; }
    btn("No answer", "cbm-button cbm-button--secondary", function () { send(r, "No answer", notes, conv, false, ""); });
    btn("Call again", "cbm-button cbm-button--secondary", function () { again.hidden = false; });
    btn("Interested", "cbm-button", function () { send(r, "Interested", notes, conv, false, ""); });
    // Not interested is stored as Declined, the word the call record holds.
    btn("Not interested", "cbm-button cbm-button--secondary", function () { send(r, "Declined", notes, conv, false, ""); });
    plan.addEventListener("click", function () {
      var stamp = window.CBMDateTime ? CBMDateTime.read(picker) : null;
      if (!stamp) { notice("Choose the day and time to call again.", "warn"); return; }
      send(r, "No answer", notes, conv, true, stamp);
    });
    side.appendChild(acts);
    side.appendChild(again);
  }

  var OUTCOME_WORDS = { "Declined": "Not interested" };

  async function send(r, outcome, notes, conv, callAgain, when) {
    var body = { outcome: outcome, notes: notes.value, callAgain: callAgain, callAgainAt: when || "" };
    if (conv && outcome === "Interested") {
      var em = conv.email.value.trim();
      if (em && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(em)) { notice("“" + em + "” is not an email address.", "warn"); conv.email.focus(); return; }
      body.email = em; body.website = conv.website.value.trim();
      body.firstName = conv.firstName.value.trim(); body.lastName = conv.lastName.value.trim();
    }
    var order = panelRows().map(function (x) { return x.touchId; });
    var at = order.indexOf(r.touchId);
    try {
      var res = await api("/calls/" + encodeURIComponent(r.touchId) + "/outcome", { method: "POST", body: body });
      var extra = (res.consequences || []).length ? " (" + res.consequences.join(", ") + ")" : "";
      var warn = (res.warnings || []).slice(); if (res.notConverted) warn.unshift(res.notConverted);
      var word = callAgain ? "Call again " + fmtDate(when) : (OUTCOME_WORDS[outcome] || outcome);
      notice("Recorded " + word + " for " + (r.person || r.name) + extra + "." + (warn.length ? " " + warn.join(" ") : ""), warn.length ? "warn" : "ok");
    } catch (e) { notice(e.message, "error"); return; }
    // Recording one moves to the next row.
    var nextId = order[at + 1] || null;
    state.open = nextId;
    await load();
    if (state.open && !rowById(state.open)) {
      var now = panelRows(); state.open = now.length ? now[Math.min(at, now.length - 1)].touchId : null; renderPanel();
    }
  }

  $("cl_callRefreshBtn").addEventListener("click", load);
  $("cl_callSearch").addEventListener("input", function () { (state.data || {}).panel ? renderPanel() : render(); });
  $("cl_campaignFilter").addEventListener("change", function () { (state.data || {}).panel ? renderPanel() : render(); });

  // Shown by app.js when the Calls tab opens (it refused the tab when calls
  // are switched off). The list is re-read each time: another caller may have
  // taken a row since.
  M.register("calls", { onShow: function () { return load(); } });
})();
