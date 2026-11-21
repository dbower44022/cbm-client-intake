/* Ambassador Review — the program team's list (PRD § 5.2; decision AM4).

   One list, two kinds of row: a follow-up to mark done (a note required),
   and a contact to place (link it to a partner, funder or client's
   engagement, create it as a new referral, or dismiss it), plus a mention
   when an ambassador corrected our records. Opening a row shows it in full.
   ?activity=<id> opens one row directly (the Needs you row links here).
   Buttons are never disabled for validation: a click says what is missing. */
(function () {
  "use strict";

  var API = "/ambassador/api";
  var $ = function (id) { return document.getElementById(id); };
  var S = { rows: [], current: null, linkKind: "", grid: null };
  var KIND_WORDS = { "follow-up": "Follow-up", "contact": "Contact to place",
                     "correction": "Correction" };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function api(path, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    if (opts.body && !opts.headers) opts.headers = { "Content-Type": "application/json" };
    return fetch(API + path, opts).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) {
          var e = new Error((d && typeof d.detail === "string" && d.detail) || ("The server answered " + r.status + "."));
          e.status = r.status;
          throw e;
        }
        return d;
      });
    });
  }

  function say(p, text) { p.textContent = text || ""; p.hidden = !text; }

  function fail(text) {
    say($("msgText"), text);
    $("msgView").hidden = false;
    $("listView").hidden = true; $("detailView").hidden = true;
  }

  function start() {
    api("/session").then(function (s) {
      $("signin").hidden = true;
      $("userBar").hidden = false;
      $("whoName").textContent = s.user.name || s.user.userName;
      if (!s.isReviewer) { fail("Your account is not on the Ambassador Program team."); return; }
      if (!s.built) { fail("The Ambassador Program is not set up in the CRM yet."); return; }
      load();
    }).catch(function (e) {
      if (e.status === 401) {
        $("signin").hidden = false;
        CBMSignIn.mount($("signin"), { title: "Sign in to the review list", onSignedIn: start });
        return;
      }
      fail(e.status === 404 ? "The Ambassador Program is not switched on." : e.message);
    });
  }

  function shown(stamp) {
    if (!stamp) return "";
    var d = new Date(String(stamp).replace(" ", "T") + (String(stamp).length > 10 ? "Z" : "T12:00:00"));
    return isNaN(d) ? stamp : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function load() {
    var p = api("/review").then(function (res) {
      S.rows = res.rows || [];
      draw();
      var want = new URLSearchParams(window.location.search).get("activity");
      if (want) {
        var row = S.rows.filter(function (r) { return r.id === want; })[0];
        if (row) open(row);
      }
    }).catch(function (e) { fail(e.message); });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading($("listView"), p);
  }

  function draw() {
    $("listView").hidden = false;
    $("detailView").hidden = true;
    var body = $("reviewBody"); body.textContent = "";
    $("countText").textContent = S.rows.length + (S.rows.length === 1 ? " item to review" : " items to review");
    $("emptyText").hidden = S.rows.length > 0;
    $("reviewTable").hidden = S.rows.length === 0;
    S.rows.forEach(function (r) {
      var tr = el("tr");
      tr.tabIndex = 0;
      var td = el("td", null, shown(r.receivedAt)); td.setAttribute("data-sort", r.receivedAt); tr.appendChild(td);
      var needs = el("td");
      r.kinds.forEach(function (k) {
        needs.appendChild(el("span", "amr__chip" + (k === "follow-up" ? " amr__chip--fu" : ""), KIND_WORDS[k] || k));
      });
      tr.appendChild(needs);
      tr.appendChild(el("td", null, r.ambassador));
      tr.appendChild(el("td", null, r.activityType));
      tr.appendChild(el("td", null, r.contactName || r.name || "—"));
      tr.appendChild(el("td", null, r.organization || "—"));
      tr.addEventListener("click", function () { open(r); });
      tr.addEventListener("keydown", function (ev) { if (ev.key === "Enter") open(r); });
      body.appendChild(tr);
    });
    if (window.CBMGrid && !S.grid && S.rows.length) {
      S.grid = CBMGrid.enhance($("reviewTable"), { key: "ambassador.review", sort: [{ col: "received", dir: "asc" }] });
    } else if (S.grid) S.grid.refresh();
  }

  function addFact(dl, label, value) {
    if (!value) return;
    dl.appendChild(el("dt", null, label));
    dl.appendChild(el("dd", null, value));
  }

  function open(r) {
    S.current = r; S.linkKind = "";
    $("listView").hidden = true;
    $("detailView").hidden = false;
    $("detailTitle").textContent = r.activityType + " — " + r.ambassador;
    var dl = $("detailList"); dl.textContent = "";
    addFact(dl, "Date", shown(r.activityDate));
    addFact(dl, "Reference", r.reference);
    addFact(dl, "This person is", r.personKind);
    addFact(dl, "Name", r.name);
    addFact(dl, "Email", r.email);
    addFact(dl, "Organization", r.organization);
    addFact(dl, "Title", r.title);
    addFact(dl, "Phone", r.phone);
    addFact(dl, "Matched to", r.contactName);
    addFact(dl, "What the system found", r.matchStatus);
    addFact(dl, "Recorded on", r.routedTo);
    addFact(dl, "Corrections", r.corrections);
    addFact(dl, "Note", r.note);
    $("fuSection").hidden = r.kinds.indexOf("follow-up") === -1;
    $("contactSection").hidden = r.kinds.indexOf("contact") === -1;
    $("correctionSection").hidden = r.kinds.indexOf("correction") === -1;
    $("fuNote").value = ""; $("dismissNote").value = ""; $("linkSearch").value = "";
    $("linkResults").textContent = "";
    Array.prototype.forEach.call(document.querySelectorAll("#linkKinds .am__choice"), function (b) {
      b.setAttribute("aria-pressed", "false");
    });
    say($("detailError"), ""); say($("detailOk"), "");
    window.scrollTo(0, 0);
  }

  function act(btn, path, body, okText) {
    say($("detailError"), ""); say($("detailOk"), "");
    var done = window.CBMBusy ? CBMBusy.start(btn) : function () {};
    return api("/review/" + encodeURIComponent(S.current.id) + path,
               { method: "POST", body: JSON.stringify(body || {}) })
      .then(function () { say($("detailOk"), okText); setTimeout(load, 900); })
      .catch(function (e) { say($("detailError"), e.message); })
      .then(done, done);
  }

  $("fuDone").addEventListener("click", function () {
    if (!$("fuNote").value.trim()) { say($("detailError"), "Write what was done before marking it done."); return; }
    act($("fuDone"), "/done", { note: $("fuNote").value.trim() }, "Marked done. The ambassador has been told.");
  });

  $("linkKinds").addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-kind]");
    if (!b) return;
    S.linkKind = b.getAttribute("data-kind");
    Array.prototype.forEach.call(document.querySelectorAll("#linkKinds .am__choice"), function (x) {
      x.setAttribute("aria-pressed", x === b ? "true" : "false");
    });
    search();
  });

  var timer = null;
  function search() {
    clearTimeout(timer);
    var q = $("linkSearch").value.trim();
    var list = $("linkResults");
    if (!S.linkKind || q.length < 2) { list.textContent = ""; return; }
    timer = setTimeout(function () {
      api("/review/targets?kind=" + encodeURIComponent(S.linkKind) + "&q=" + encodeURIComponent(q))
        .then(function (res) {
          list.textContent = "";
          if (!res.targets.length) { list.appendChild(el("li", "cbm-help", "No record by that name.")); return; }
          res.targets.forEach(function (t) {
            var li = el("li");
            var b = el("button", "am__choice", t.name);
            b.type = "button";
            b.addEventListener("click", function () {
              act(b, "/link", { kind: S.linkKind, recordId: t.id },
                  "Linked. The session is recorded on " + t.name + " and its manager or mentor told.");
            });
            li.appendChild(b);
            list.appendChild(li);
          });
        }).catch(function (e) { say($("detailError"), e.message); });
    }, 250);
  }
  $("linkSearch").addEventListener("input", function () {
    if (!S.linkKind) { say($("detailError"), "First choose whether it is a partner, a funder or a client's engagement."); return; }
    say($("detailError"), "");
    search();
  });

  Array.prototype.forEach.call(document.querySelectorAll("[data-create]"), function (b) {
    b.addEventListener("click", function () {
      var kind = b.getAttribute("data-create");
      act(b, "/create", { kind: kind }, "Created as a new " + kind + " referral, credited to the ambassador.");
    });
  });

  $("dismissBtn").addEventListener("click", function () {
    if (!$("dismissNote").value.trim()) { say($("detailError"), "Say why it is dismissed."); return; }
    act($("dismissBtn"), "/dismiss", { note: $("dismissNote").value.trim() }, "Dismissed.");
  });
  $("seenBtn").addEventListener("click", function () { act($("seenBtn"), "/seen", {}, "Marked as read."); });
  $("backBtn").addEventListener("click", function () { draw(); });
  $("refreshBtn").addEventListener("click", load);

  start();
})();
