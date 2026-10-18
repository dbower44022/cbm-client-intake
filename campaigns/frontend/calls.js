/* Campaign Calls — the call screen (prds/prospect-marketing/build-plan.md § 3.4).
 *
 * Who sees a row is ruling 36: the members of the teams named on its campaign.
 * The page asks the server and shows what comes back; the server decides.
 * A row opens in place: the number, a notes box and the three outcomes. Every
 * button stays visible and clickable; validation happens on click.
 */
(function () {
  "use strict";
  var API = "/campaigns/api";
  var state = { data: null, open: null };

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
    var d = new Date(v.replace(" ", "T") + (v.length === 19 ? "Z" : ""));
    return isNaN(d.getTime()) ? v : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
  function notice(msg, kind) {
    var n = $("notice");
    if (!msg) { hide(n); return; }
    n.textContent = msg; n.className = "cm__notice" + (kind ? " cm__notice--" + kind : ""); show(n);
  }

  async function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: { Accept: "application/json" }, credentials: "same-origin" };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    var res = await fetch(API + path, init);
    if (res.status === 401) { location.assign("/?next=" + encodeURIComponent("/campaigns/calls.html")); throw Object.assign(new Error("Signed out"), { status: 401 }); }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) { var err = new Error((data && data.detail) || ("Request failed (" + res.status + ")")); err.status = res.status; throw err; }
    return data;
  }

  async function load() {
    try {
      state.data = await api("/calls");
    } catch (e) { notice(e.message, "error"); return; }
    var d = state.data;
    text($("callWarning"), d.warning);
    var msg = $("callMessage");
    if (d.message) { msg.textContent = d.message; show(msg); } else hide(msg);
    var sel = $("campaignFilter"), keep = sel.value;
    sel.innerHTML = "<option value=\"\">All</option>";
    (d.campaigns || []).forEach(function (c) { var o = el("option", null, c.name); o.value = c.id; sel.appendChild(o); });
    sel.value = keep;
    var briefs = $("briefList"); briefs.innerHTML = "";
    (d.campaigns || []).forEach(function (c) {
      if (!c.brief) return;
      briefs.appendChild(el("h4", null, c.name));
      var div = el("div", "cm__prose cm__brief");
      div.innerHTML = window.CBMRichText && CBMRichText.sanitizeHtml ? CBMRichText.sanitizeHtml(c.brief) : "";
      if (!div.innerHTML) div.textContent = c.brief.replace(/<[^>]+>/g, " ");
      briefs.appendChild(div);
    });
    $("briefs").hidden = !briefs.childNodes.length;
    render();
  }

  function render() {
    var d = state.data || { rows: [] };
    var q = ($("callSearch").value || "").toLowerCase(), camp = $("campaignFilter").value;
    var rows = (d.rows || []).filter(function (r) {
      if (camp && r.campaignId !== camp) return false;
      return !q || [r.name, r.person, r.phone, r.campaignName, r.city].join(" ").toLowerCase().indexOf(q) >= 0;
    });
    var body = $("callRows"); body.innerHTML = "";
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
    text($("callCount"), rows.length + " to call");
    $("callsEmpty").hidden = rows.length > 0;
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
    var again = el("label", "cm__check"); var cb = el("input"); cb.type = "checkbox"; again.appendChild(cb); again.appendChild(document.createTextNode(" Call again (with No answer)")); form.appendChild(again);
    var acts = el("div", "cm__runactions");
    [["No answer", "cbm-button cbm-button--secondary"], ["Interested", "cbm-button"], ["Declined", "cbm-button cbm-button--secondary"]].forEach(function (o) {
      var b = el("button", o[1], o[0]); b.type = "button";
      b.addEventListener("click", async function () {
        if (cb.checked && o[0] !== "No answer") { notice("Call again goes with No answer only — untick it, or choose No answer.", "warn"); return; }
        try {
          var res = await api("/calls/" + encodeURIComponent(r.touchId) + "/outcome", { method: "POST", body: { outcome: o[0], notes: notes.value, callAgain: cb.checked } });
          var extra = (res.consequences || []).length ? " (" + res.consequences.join(", ") + ")" : "";
          notice("Recorded " + o[0] + " for " + (r.person || r.name) + extra + "." + ((res.warnings || []).length ? " " + res.warnings.join(" ") : ""), (res.warnings || []).length ? "warn" : "ok");
          state.open = null; load();
        } catch (e) { notice(e.message, "error"); }
      });
      acts.appendChild(b);
    });
    form.appendChild(acts);
    td.appendChild(form); tr.appendChild(td);
    return tr;
  }

  $("callRefreshBtn").addEventListener("click", load);
  $("callSearch").addEventListener("input", render);
  $("campaignFilter").addEventListener("change", render);

  (async function init() {
    var s;
    try { s = await api("/calls/session"); }
    catch (e) {
      if (e.status === 404) { text($("offReason"), e.message); show($("offPanel")); }
      else notice(e.message, "error");
      return;
    }
    text($("whoName"), s.name || s.userName); show($("userCorner"));
    if (s.campaignsTeam) show($("campaignsLink"));
    show($("callsPanel"));
    await load();
  })();
})();
