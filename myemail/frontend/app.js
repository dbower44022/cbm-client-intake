/* My Email — the unified inbox across every record the signed-in manager
   handles. Read-only view + read-state curation; replying happens on the
   record page (deep-linked from the thread), where the full record-scoped
   compose lives. */
(function () {
  "use strict";

  var API = "/myemail/api";
  var rows = [];            // inbox rows from the server
  var filter = "all";       // all | unread | awaiting
  var search = "";

  function $(id) { return document.getElementById(id); }
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

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

  function showLogin() { location.href = "/?next=" + encodeURIComponent("/myemail/"); }
  function showMessage(text) {
    hide($("inboxView")); $("msgText").textContent = text; show($("msgView"));
  }

  function notice(text, kind) {
    var n = $("notice");
    n.textContent = text;
    n.className = "me__notice" + (kind === "error" ? " is-error" : "");
    show(n);
  }

  // Minimal sanitizer for stored (already server-cleaned) message HTML.
  function sanitizeHtml(html) {
    var tpl = document.createElement("template");
    tpl.innerHTML = String(html || "");
    tpl.content.querySelectorAll("script, style, iframe, object, embed").forEach(function (el) { el.remove(); });
    tpl.content.querySelectorAll("*").forEach(function (el) {
      Array.prototype.slice.call(el.attributes).forEach(function (a) {
        var n = a.name.toLowerCase();
        if (n.indexOf("on") === 0) el.removeAttribute(a.name);
        if ((n === "href" || n === "src") && /^\s*javascript:/i.test(a.value)) el.removeAttribute(a.name);
      });
    });
    return tpl.innerHTML;
  }

  function fmtWhen(stamp) {
    if (!stamp) return "—";
    // CRM stamps are UTC "YYYY-MM-DD HH:MM:SS"; render viewer-local.
    var d = new Date(String(stamp).replace(" ", "T") + "Z");
    if (isNaN(d)) return stamp;
    var today = new Date();
    var sameDay = d.toDateString() === today.toDateString();
    if (sameDay) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) +
      " " + d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  // --- boot ---
  (async function init() {
    try {
      var s = await api("/session");
      $("whoName").textContent = s.name || s.userName;
      if (!s.commsEnabled) {
        showMessage("The email integration isn't enabled on this deployment.");
        return;
      }
      show($("inboxView"));
      await loadInbox();
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      showMessage(e.message || "The server isn't responding right now.");
    }
  })();

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) {}
    location.href = "/";
  });
  $("refreshBtn").addEventListener("click", loadInbox);
  $("search").addEventListener("input", function () { search = this.value; renderRows(); });
  Array.prototype.forEach.call(document.querySelectorAll(".me__filter"), function (b) {
    b.addEventListener("click", function () {
      filter = b.dataset.filter;
      Array.prototype.forEach.call(document.querySelectorAll(".me__filter"), function (x) {
        x.classList.toggle("is-active", x === b);
      });
      renderRows();
    });
  });
  $("markAllBtn").addEventListener("click", async function () {
    var unreadIds = rows.filter(function (r) { return r.unread; }).map(function (r) { return r.id; });
    if (!unreadIds.length) { notice("Nothing unread — you're all caught up."); return; }
    try {
      await api("/markallread", { method: "POST", body: JSON.stringify({ conversationIds: unreadIds }) });
      rows.forEach(function (r) { r.unread = false; });
      renderRows();
      notice("Marked " + unreadIds.length + " conversation" + (unreadIds.length === 1 ? "" : "s") + " as read.");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    }
  });
  $("threadClose").addEventListener("click", closeThread);
  $("threadBackdrop").addEventListener("click", closeThread);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !$("threadModal").hidden) closeThread();
  });

  async function loadInbox() {
    hide($("notice"));
    show($("loadingState")); hide($("inboxTable")); hide($("emptyState"));
    try {
      var res = await api("/inbox");
      rows = res.conversations || [];
      hide($("loadingState"));
      if (res.profileFound === false) {
        $("emptyState").textContent =
          "Your login isn't linked to a CBM Mentor profile yet, so there is no email to show. " +
          "Ask an administrator to link your profile in the CRM, then Refresh.";
        show($("emptyState"));
        return;
      }
      renderRows();
    } catch (e) {
      hide($("loadingState"));
      if (e.status === 401) { showLogin(); return; }
      if (e.status === 503) { showMessage(e.message); return; }
      notice(e.message, "error");
    }
  }

  function matchesSearch(r, q) {
    if (!q) return true;
    var hay = [
      r.subject, r.participants, r.summary,
      (r.records || []).map(function (x) { return x.name; }).join(" "),
    ].join(" ").toLowerCase();
    return hay.indexOf(q.toLowerCase()) !== -1;
  }

  function renderRows() {
    var unread = rows.filter(function (r) { return r.unread; }).length;
    var awaiting = rows.filter(function (r) { return r.awaitingReply; }).length;
    var uc = $("unreadCount"), ac = $("awaitingCount");
    uc.textContent = unread; uc.hidden = !unread;
    ac.textContent = awaiting; ac.hidden = !awaiting;

    var visible = rows.filter(function (r) {
      if (filter === "unread" && !r.unread) return false;
      if (filter === "awaiting" && !r.awaitingReply) return false;
      return matchesSearch(r, search);
    });
    var body = $("inboxBody"); body.innerHTML = "";
    if (!visible.length) {
      $("emptyState").textContent = rows.length
        ? "No conversations match this view."
        : "No conversations found on your records yet.";
      show($("emptyState")); hide($("inboxTable"));
      return;
    }
    hide($("emptyState")); show($("inboxTable"));
    visible.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.className = "me__row" + (r.unread ? " is-unread" : "");
      tr.tabIndex = 0; tr.setAttribute("role", "button");

      var c0 = document.createElement("td");
      if (r.unread) {
        var dot = document.createElement("span"); dot.className = "me__dot"; dot.title = "Unread";
        c0.appendChild(dot);
      }
      if (r.bounced) {
        var bchip = document.createElement("span"); bchip.className = "me__chip me__chip--bounced";
        bchip.textContent = "✕ delivery failed";
        bchip.title = "The newest message is a bounce — the last email did NOT reach the recipient.";
        c0.appendChild(bchip);
      } else if (r.awaitingReply) {
        var chip = document.createElement("span"); chip.className = "me__chip me__chip--awaiting";
        chip.textContent = "Awaiting reply";
        c0.appendChild(chip);
      }

      var c1 = document.createElement("td");
      (r.records || []).forEach(function (rec) {
        var a = document.createElement("a");
        a.className = "me__rec";
        a.href = "/" + rec.slug + "/record/" + encodeURIComponent(rec.id);
        a.target = "_blank"; a.rel = "noopener";
        a.title = "Open " + (rec.name || "the record");
        a.textContent = rec.name || rec.id;
        a.addEventListener("click", function (e) { e.stopPropagation(); });
        c1.appendChild(a);
      });

      var c2 = document.createElement("td"); c2.className = "me__party";
      c2.textContent = r.participants || "—";

      var c3 = document.createElement("td");
      var subj = document.createElement("span"); subj.className = "me__subject";
      subj.textContent = (r.subject || "(no subject)") +
        (r.messageCount ? " (" + r.messageCount + ")" : "");
      c3.appendChild(subj);
      if (r.summary) {
        var sn = document.createElement("span"); sn.className = "me__snippet";
        sn.textContent = r.summary;
        c3.appendChild(sn);
      }

      var c4 = document.createElement("td"); c4.className = "me__date";
      c4.textContent = fmtWhen(r.lastMessageAt);

      tr.appendChild(c0); tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3); tr.appendChild(c4);
      tr.addEventListener("click", function () { openThread(r); });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openThread(r); }
      });
      body.appendChild(tr);
    });
  }

  async function openThread(row) {
    $("threadKind").textContent = (row.records || []).map(function (x) { return x.name; }).join(" · ");
    $("threadTitle").textContent = row.subject || "(no subject)";
    $("threadBody").innerHTML = "<p class='me__muted' style='padding:0 1rem'>Loading…</p>";
    $("threadFoot").innerHTML = "";
    show($("threadModal"));
    var c;
    try {
      c = await api("/conversations/" + encodeURIComponent(row.id));
    } catch (e) {
      if (e.status === 401) { closeThread(); showLogin(); return; }
      $("threadBody").innerHTML = "";
      var p = document.createElement("p"); p.className = "form-error"; p.textContent = e.message;
      $("threadBody").appendChild(p);
      return;
    }
    // Opening marks it read server-side — reflect that immediately.
    row.unread = false;
    renderRows();

    var body = $("threadBody"); body.innerHTML = "";
    var msgs = c.messages || [];
    msgs.forEach(function (m, i) {
      if (i === 0) body.appendChild(CBMConversation.startedDivider(m, { fmtWhen: fmtWhen }));
      body.appendChild(CBMConversation.messageCard(m, {
        sanitizeHtml: sanitizeHtml,
        fmtWhen: fmtWhen,
      }));
    });
    if (!msgs.length) {
      var none = document.createElement("p"); none.className = "me__muted";
      none.style.padding = "0 1rem";
      none.textContent = "No messages stored for this conversation.";
      body.appendChild(none);
    }

    var foot = $("threadFoot");
    var recWrap = document.createElement("div"); recWrap.className = "me__openrec";
    (c.records && c.records.length ? c.records : row.records || []).forEach(function (rec) {
      if (!rec.slug) return;
      var a = document.createElement("a");
      a.className = "cbm-button";
      a.href = "/" + rec.slug + "/record/" + encodeURIComponent(rec.id);
      a.target = "_blank"; a.rel = "noopener";
      a.textContent = "Open " + (rec.name || "record") + " — reply there";
      recWrap.appendChild(a);
    });
    foot.appendChild(recWrap);
    var close = document.createElement("button"); close.type = "button";
    close.className = "cbm-button cbm-button--secondary"; close.textContent = "Close";
    close.addEventListener("click", closeThread);
    foot.appendChild(close);
  }

  function closeThread() { hide($("threadModal")); }
})();
