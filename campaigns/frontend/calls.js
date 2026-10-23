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

  async function load() {
    try {
      state.data = await api("/calls");
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
    render();
  }

  function render() {
    var d = state.data || { rows: [] };
    var q = ($("cl_callSearch").value || "").toLowerCase(), camp = $("cl_campaignFilter").value;
    var rows = (d.rows || []).filter(function (r) {
      if (camp && r.campaignId !== camp) return false;
      return !q || [r.name, r.person, r.phone, r.campaignName, r.city].join(" ").toLowerCase().indexOf(q) >= 0;
    });
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

  $("cl_callRefreshBtn").addEventListener("click", load);
  $("cl_callSearch").addEventListener("input", render);
  $("cl_campaignFilter").addEventListener("change", render);

  // Shown by app.js when the Calls tab opens (it refused the tab when calls
  // are switched off). The list is re-read each time: another caller may have
  // taken a row since.
  M.register("calls", { onShow: function () { return load(); } });
})();
