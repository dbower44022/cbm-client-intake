/* The activity page (mentor login integrity step 6, plan § 4.5): every
 * change by one person, or in a date range, across every record. The list
 * is the shared History panel (frontend/shared/history.js) with a Record
 * column; the export writes what the filters show as CSV. */
(function () {
  "use strict";

  var API = "/activity/api";
  var panel = null;

  function $(id) { return document.getElementById(id); }

  async function api(path, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    var resp = await (window.CBMBusy && CBMBusy.fetch ? CBMBusy.fetch(API + path, opts) : fetch(API + path, opts));
    var data = null;
    try { data = await resp.json(); } catch (e) {}
    if (!resp.ok) {
      var err = new Error((data && typeof data.detail === "string" && data.detail) || ("Request failed (" + resp.status + ")"));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function showLogin() { location.href = "/?next=" + encodeURIComponent("/activity/"); }
  function showMessage(text) {
    $("pageView").hidden = true; $("msgText").textContent = text; $("msgView").hidden = false;
  }
  function notice(text) { var n = $("notice"); n.textContent = text || ""; n.hidden = !text; }

  /* A local day as the CRM's UTC stamp: the start of `ymd`, or the start of
   * the day after it (`end`). */
  function utcStamp(ymd, end) {
    var p = ymd.split("-").map(Number);
    var d = new Date(p[0], p[1] - 1, p[2] + (end ? 1 : 0));
    return d.toISOString().slice(0, 19).replace("T", " ");
  }

  function exportCsv() {
    if (!panel) return;
    var shown = panel.filtered();
    if (!shown.length) { notice("There is nothing to export — no change matches the filters."); return; }
    var blob = new Blob(["﻿" + CBMHistory.toCsv(shown)], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "activity-" + new Date().toISOString().slice(0, 10) + ".csv";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function ask(ev) {
    if (ev) ev.preventDefault();
    notice("");
    var person = $("askPerson").value, from = $("askFrom").value, to = $("askTo").value;
    if (!person && !(from && to)) { notice("Choose a person, or both a From and a To date."); return; }
    if (from && to && from > to) { notice("The From date is after the To date."); return; }
    var q = [];
    if (person) q.push("person=" + encodeURIComponent(person));
    if (from) q.push("since=" + encodeURIComponent(utcStamp(from, false)));
    if (to) q.push("until=" + encodeURIComponent(utcStamp(to, true)));
    panel.load(API + "/changes?" + q.join("&"), true);
  }

  async function boot() {
    try {
      var user = await api("/session");
      $("whoName").textContent = user.name || user.userName;
      $("pageView").hidden = false;
      panel = CBMHistory.mount($("results"), {
        key: "activity", withRecord: true,
        emptyText: "No changes found for that person and those dates.",
        extraControls: function (bar) {
          var b = document.createElement("button");
          b.type = "button"; b.className = "cbm-hist__export"; b.textContent = "Export CSV";
          b.addEventListener("click", exportCsv);
          bar.appendChild(b);
        },
      });
      var people = (await api("/people")).people || [];
      people.forEach(function (p) {
        var o = document.createElement("option");
        o.value = p.id; o.textContent = p.name + (p.active ? "" : " (no longer active)");
        $("askPerson").appendChild(o);
      });
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      showMessage(e.message);
    }
  }

  $("askForm").addEventListener("submit", ask);
  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) {}
    location.href = "/";
  });
  boot();
})();
