/* View Contact page — /directory/contacts/record/{id}. Its own tab (opened
   from the Contacts/Mentors directory grids via a stable named window), two
   tabs: Overview (the contact's CRM-layout-driven panels, shared with the
   grid pop-up via detail-render.js) and Communications (the signed-in user's
   own email conversations with THIS contact — list, thread view, reply /
   reply-all / forward, compose with templates + signature + attachments,
   Add emails, Remove). The comms UI is a port of the session tools'
   Communications tab scoped to one contact; the server enforces the
   only-my-conversations rule. Fresh single IIFE — helpers are ported ONCE
   (the known shared-scope collision burn). */
(function () {
  "use strict";

  var segs = location.pathname.split("/"); // ["", "directory", "contacts", "record", "<id>"]
  var KIND = (segs[2] || "contacts").toLowerCase();
  var RECORD_ID = segs[4] || "";
  var API = "/directory/" + KIND + "/api";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function show(e) { if (e) e.hidden = false; }
  function hide(e) { if (e) e.hidden = true; }

  var R = window.CBMDirRender;

  var session = null;          // /session payload (commsEnabled etc.)
  var detail = null;           // /records/{id} payload (name + panels)
  var contactEmails = [];      // [{name, email}] — the contact's own addresses
  var convRows = [];
  var convSort = { key: null, dir: 1 };
  var senderMailbox;           // undefined = not fetched; null = none
  var senderSignature = "";
  var composeGuard = null;     // {dirty(), discard(), backConvId}
  var confirmOnDiscard = null;

  // ---- API helpers ---------------------------------------------------------
  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
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

  // POST with upload progress (an email with attachments is one big JSON
  // body — fetch gives no upload feedback). Mirrors api()'s error contract.
  function apiPostProgress(path, payload, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", API + path);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.withCredentials = true;
      if (xhr.upload && onProgress) {
        xhr.upload.addEventListener("progress", function (ev) {
          if (ev.lengthComputable) onProgress(Math.round((ev.loaded / ev.total) * 100));
        });
      }
      xhr.onload = function () {
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e) {}
        if (xhr.status >= 200 && xhr.status < 300) { resolve(data); return; }
        var msg = (data && data.detail) || ("Request failed (" + xhr.status + ")");
        var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        err.status = xhr.status;
        reject(err);
      };
      xhr.onerror = xhr.onabort = xhr.ontimeout = function () {
        reject(new Error("The send was interrupted — check your connection and try again."));
      };
      xhr.send(JSON.stringify(payload));
    });
  }

  function goLogin() {
    location.href = "/?next=" + encodeURIComponent(location.pathname);
  }

  function fail(e) {
    if (e && e.status === 401) { goLogin(); return; }
    hide($("crMainView"));
    $("crMsgText").textContent = (e && e.message) || "Something went wrong.";
    show($("crMsgView"));
  }

  function notify(msg) {
    var n = $("crNotice");
    n.textContent = msg; show(n);
    clearTimeout(notify._t);
    notify._t = setTimeout(function () { hide(n); }, 6000);
  }

  // ---- small text helpers --------------------------------------------------
  function fmtWhen(v) { return R.fmtDateTime(v); }
  function sanitizeHtml(html) {
    if (window.CBMRichText && window.CBMRichText.sanitizeHtml) return window.CBMRichText.sanitizeHtml(String(html || ""));
    var d = el("div"); d.textContent = String(html || "").replace(/<[^>]*>/g, " "); return d.innerHTML;
  }
  function partyName(addr) {
    var m = /^\s*"?([^"<]+?)"?\s*</.exec(addr || "");
    return (m ? m[1] : (addr || "")).trim() || "(unknown)";
  }
  function extractEmail(addr) {
    var m = /<([^>]+)>/.exec(addr || "");
    return (m ? m[1] : String(addr || "")).trim();
  }
  function snippet(body, n) {
    var t = String(body || "").replace(/\s+/g, " ").trim();
    n = n || 90;
    return t.length > n ? t.slice(0, n - 1) + "…" : t;
  }
  function replySubject(subj) {
    var s = String(subj || "");
    return /^re:/i.test(s) ? s : "Re: " + s;
  }
  function fmtBytes(n) {
    if (!n && n !== 0) return "";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }
  // "a@b.c, Jane Doe <jane@x.org>; bob@y.io" -> {emails, invalid}.
  function parseAddrList(str) {
    var emails = [], invalid = [], seen = {};
    String(str || "").split(/[,;\n]+/).forEach(function (tok) {
      tok = tok.trim();
      if (!tok) return;
      var m = /<([^>]+)>/.exec(tok);
      var addr = (m ? m[1] : tok).trim();
      if (!m && /\s/.test(addr)) {
        var parts = addr.split(/\s+/).filter(function (p) { return p.indexOf("@") !== -1; });
        if (parts.length === 1) addr = parts[0];
      }
      if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)) {
        var k = addr.toLowerCase();
        if (!seen[k]) { seen[k] = 1; emails.push(addr); }
      } else {
        invalid.push(tok);
      }
    });
    return { emails: emails, invalid: invalid };
  }

  function commsOn() { return !!(session && session.commsEnabled); }

  // ---- styled confirm (discard-draft guard) --------------------------------
  function openConfirm(opts) {
    $("crConfirmTitle").textContent = opts.title || "Are you sure?";
    $("crConfirmMsg").textContent = opts.msg || "";
    $("crConfirmDiscard").textContent = opts.discardLabel || "Discard";
    $("crConfirmCancel").textContent = opts.cancelLabel || "Cancel";
    confirmOnDiscard = opts.onDiscard || null;
    show($("crConfirmModal"));
    $("crConfirmCancel").focus();
  }
  function closeConfirm() { confirmOnDiscard = null; hide($("crConfirmModal")); }

  // ---- single-tab guard (the sessions record-page pattern) -----------------
  function acquireRecordLock(key) {
    return new Promise(function (resolve) {
      var BC = window.BroadcastChannel;
      if (!BC) { resolve(true); return; }
      var ch;
      try { ch = new BC("cbm-record-lock"); } catch (_) { resolve(true); return; }
      var me = { openedAt: Date.now(), tabId: Math.random().toString(36).slice(2) + "-" + Date.now() };
      var decided = false, owner = true;
      function isOlder(a, b) {
        return a.openedAt < b.openedAt || (a.openedAt === b.openedAt && a.tabId < b.tabId);
      }
      ch.onmessage = function (ev) {
        var m = ev.data || {};
        if (!m || m.key !== key || m.tabId === me.tabId) return;
        if (m.type === "hello") {
          try { ch.postMessage({ type: "present", key: key, openedAt: me.openedAt, tabId: me.tabId }); } catch (_) {}
        }
        if ((m.type === "hello" || m.type === "present") && isOlder(m, me) && !decided) {
          decided = true; owner = false; resolve(false);
        }
        if (m.type === "bye" && m.owner && !owner) {
          location.reload();
        }
      };
      try { ch.postMessage({ type: "hello", key: key, openedAt: me.openedAt, tabId: me.tabId }); } catch (_) {}
      window.__cbmRecordLock = ch;
      window.addEventListener("pagehide", function () {
        try { ch.postMessage({ type: "bye", key: key, tabId: me.tabId, owner: owner }); } catch (_) {}
      });
      setTimeout(function () { if (!decided) { decided = true; resolve(true); } }, 350);
    });
  }

  // ---- tabs ----------------------------------------------------------------
  var commsLoaded = false;
  function switchTab(key) {
    document.querySelectorAll("#crTabs .cr__tab").forEach(function (b) {
      b.classList.toggle("is-active", b.dataset.crtab === key);
    });
    document.querySelectorAll(".cr__panel").forEach(function (p) {
      p.hidden = p.dataset.crpanel !== key;
    });
    if (key === "communications" && !commsLoaded) {
      commsLoaded = true;
      renderComms();
    }
  }

  // ---- Overview ------------------------------------------------------------
  function renderOverview() {
    var body = $("crOverviewBody");
    body.innerHTML = "";
    R.panelsInto(body, detail.panels);
    if (!body.children.length) body.appendChild(el("p", "dir__restricted", "No details to show."));
  }

  // The contact's own email addresses, pulled from the detail panels (fields
  // the CRM types as email) — the compose checklist + known-recipient set.
  function collectContactEmails() {
    var seen = {}, out = [];
    (detail.panels || []).forEach(function (p) {
      (p.fields || []).forEach(function (f) {
        if (f.type !== "email" || !f.value) return;
        (Array.isArray(f.value) ? f.value : [f.value]).forEach(function (v) {
          var a = String(v).trim();
          var k = a.toLowerCase();
          if (a && !seen[k]) { seen[k] = 1; out.push({ name: detail.name || a, email: a }); }
        });
      });
    });
    return out;
  }

  // ---- Communications: conversation list ----------------------------------
  var CONV_COLUMNS = [
    { key: "status", label: "Status" },
    { key: "participants", label: "Participants" },
    { key: "subject", label: "Conversation" },
    { key: "lastMessageAt", label: "Last activity" }
  ];

  function buildConvHead() {
    var head = $("crInboxHead");
    if (head.dataset.built === "conv") return;
    head.dataset.built = "conv";
    head.innerHTML = "";
    var tr = el("tr");
    CONV_COLUMNS.forEach(function (c) {
      var th = el("th", "cr__th-sort", c.label);
      th.setAttribute("data-sort", c.key);
      th.addEventListener("click", function () {
        if (convSort.key === c.key) convSort.dir = -convSort.dir;
        else { convSort.key = c.key; convSort.dir = c.key === "lastMessageAt" ? -1 : 1; }
        renderConversationRows(convRows);
      });
      tr.appendChild(th);
    });
    head.appendChild(tr);
  }

  function renderComms() {
    if (!commsOn()) {
      // Buttons stay visible (they explain on click) — only the list area
      // carries the why-empty message.
      $("crNoMessages").textContent = "The email integration isn't enabled on this deployment, so conversations can't be shown here.";
      show($("crNoMessages"));
      return;
    }
    buildConvHead();
    loadConversations();
  }

  async function loadConversations() {
    // Warm the mailbox/signature cache (Reply All + the compose signature).
    if (senderMailbox === undefined && commsOn()) {
      api("/mailbox").then(function (r) {
        senderMailbox = (r && r.mailbox) || null;
        senderSignature = (r && r.signature) || "";
      }).catch(function () { /* compose refetches on open */ });
    }
    var body = $("crInboxBody"); body.innerHTML = "";
    hide($("crCommError"));
    $("crNoMessages").textContent = "Loading conversations…";
    show($("crNoMessages")); hide($("crInboxTable"));
    try {
      var res = await api("/records/" + encodeURIComponent(RECORD_ID) + "/conversations");
      if (res.notice) {
        convRows = [];
        $("crNoMessages").textContent = res.notice;
        show($("crNoMessages"));
        updateCommTabBadge();
        return;
      }
      convRows = res.conversations || [];
      renderConversationRows(convRows);
    } catch (e) {
      if (e.status === 401) { goLogin(); return; }
      hide($("crNoMessages"));
      $("crCommError").textContent = e.message; show($("crCommError"));
    }
  }

  function convSortVal(c, k) {
    if (k === "lastMessageAt") return c.lastMessageAt || "";
    return (c[k] || "").toString().toLowerCase();
  }

  function renderConversationRows(rows) {
    var body = $("crInboxBody"); body.innerHTML = "";
    Array.prototype.forEach.call(document.querySelectorAll("#crInboxTable th[data-sort]"), function (th) {
      var active = th.getAttribute("data-sort") === convSort.key;
      th.setAttribute("aria-sort", active ? (convSort.dir === 1 ? "ascending" : "descending") : "none");
      th.dataset.dir = active ? (convSort.dir === 1 ? "asc" : "desc") : "";
    });
    if (!rows.length) {
      $("crNoMessages").textContent = "No email conversations between you and " +
        ((detail && detail.name) || "this contact") +
        " yet. Compose to start one, or use “Add emails…” to attach an existing thread from your mailbox.";
      show($("crNoMessages")); hide($("crInboxTable"));
      updateCommTabBadge();
      return;
    }
    hide($("crNoMessages")); show($("crInboxTable"));
    rows = rows.slice();
    if (convSort.key) {
      var k = convSort.key, dir = convSort.dir;
      rows.sort(function (a, b) {
        var va = convSortVal(a, k), vb = convSortVal(b, k);
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
    }
    rows.forEach(function (c) {
      var tr = el("tr", "cr__inbox-row" + (c.unread ? " is-unread" : ""));
      tr.tabIndex = 0; tr.setAttribute("role", "button");

      var c0 = el("td", "cr__inbox-dir");
      if (c.status) c0.appendChild(el("span", "cr__tag", c.status));
      if (c.bounced) {
        var bn = el("span", "cr__chip-bounced", "✕ delivery failed");
        bn.title = "The newest message is a bounce — the last email did NOT reach the recipient.";
        c0.appendChild(bn);
      } else if (c.awaitingReply) {
        var aw = el("span", "cr__chip-awaiting", "Awaiting reply");
        aw.title = "The last message is from them — the ball is in your court.";
        c0.appendChild(aw);
      }

      var c1 = el("td", "cr__inbox-party", c.participants || "—");

      var c2 = el("td", "cr__inbox-subj");
      c2.appendChild(el("span", "cr__inbox-subject",
        (c.subject || "(no subject)") + (c.messageCount ? " (" + c.messageCount + ")" : "")));
      c2.appendChild(el("span", "cr__inbox-snippet", snippet(c.summary || "", 110)));

      var c3 = el("td", "cr__inbox-date", fmtWhen(c.lastMessageAt));

      tr.appendChild(c0); tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3);
      tr.addEventListener("click", function () { viewConversation(c.id); });
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); viewConversation(c.id); } });
      body.appendChild(tr);
    });
    updateCommTabBadge();
  }

  function updateCommTabBadge() {
    var btn = document.querySelector('[data-crtab="communications"]');
    if (!btn) return;
    var n = convRows.filter(function (c) { return c.unread; }).length;
    btn.textContent = n ? "Communications (" + n + ")" : "Communications";
  }

  // ---- comm modal shell ----------------------------------------------------
  function openComm(kind, title) {
    composeGuard = null;
    $("crCommKind").textContent = kind || "";
    $("crCommTitle").textContent = title || "";
    $("crCommBody").innerHTML = ""; $("crCommFoot").innerHTML = "";
    show($("crCommModal"));
  }
  function closeComm() { composeGuard = null; hide($("crCommModal")); }

  function requestCloseComm() {
    if (!composeGuard || !composeGuard.dirty()) {
      var back = composeGuard && composeGuard.backConvId;
      closeComm();
      if (back) viewConversation(back);
      return;
    }
    var g = composeGuard;
    openConfirm({
      title: "Discard this draft?",
      msg: "Your message hasn't been sent. It stays saved as a draft unless you discard it.",
      discardLabel: "Discard draft",
      cancelLabel: "Keep writing",
      onDiscard: function () {
        g.discard();
        closeComm();
        if (g.backConvId) viewConversation(g.backConvId);
      },
    });
  }

  function commHeaderRow(label, value) {
    var row = el("div", "cr__fact");
    row.appendChild(el("span", "cr__fact-l", label));
    row.appendChild(el("span", "cr__fact-v", value || "—"));
    return row;
  }

  function commField(label, id, value, isTextarea, opts) {
    opts = opts || {};
    if (isTextarea && window.CBMRichText) {
      var minH = opts.minHeight || Math.max(240, Math.floor(window.innerHeight * 0.32));
      var rich = window.CBMRichText.create(value || "", { minHeight: minH, onInput: opts.onInput });
      if (rich) {
        var rwrap = el("div", "cr__msg-field");
        rwrap.appendChild(el("span", "cr__msg-label", label));
        rich.id = id; rich.classList.add("cr__msg-rich");
        rwrap.appendChild(rich); return rwrap;
      }
    }
    var wrap = el("div", "cr__msg-field");
    var l = el("label", "cr__msg-label", label);
    l.htmlFor = id;
    var input = isTextarea ? el("textarea") : el("input");
    input.id = id; input.className = "cr__msg-input";
    if (isTextarea) { input.rows = 10; } else { input.type = "text"; }
    if (opts.placeholder) input.placeholder = opts.placeholder;
    input.value = value || "";
    if (opts.onInput) input.addEventListener("input", opts.onInput);
    wrap.appendChild(l); wrap.appendChild(input); return wrap;
  }

  function commBodyValue() {
    var e = $("crMsgBody");
    if (!e) return "";
    return e._cbmRichText ? e._cbmRichText.getValue() : e.value;
  }

  // Searchable dropdown (template picker). opts: {placeholder, emptyLabel,
  // onSelect(id, option), allowClear}. Returns {el, input, setOptions, setText}.
  function makeCombobox(opts) {
    var wrap = el("div", "cr__combo");
    var input = el("input");
    input.type = "text"; input.className = "cr__msg-input";
    input.placeholder = opts.placeholder || "";
    input.setAttribute("role", "combobox"); input.setAttribute("aria-expanded", "false");
    var list = el("ul", "cr__combo-list"); list.hidden = true;
    wrap.appendChild(input); wrap.appendChild(list);
    var options = opts.options || [];
    var active = -1, visible = [];
    function close() { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; }
    function render(filter) {
      list.innerHTML = ""; visible = []; active = -1;
      if (opts.allowClear) visible.push({ id: null, label: opts.emptyLabel || "(none)", muted: true });
      options.forEach(function (o) {
        if (filter && String(o.label || "").toLowerCase().indexOf(filter.toLowerCase()) === -1) return;
        visible.push(o);
      });
      visible.forEach(function (o, i) {
        var li = el("li", o.muted ? "is-muted" : null, o.label);
        li.addEventListener("mousedown", function (e) { e.preventDefault(); pick(i); });
        list.appendChild(li);
      });
      list.hidden = !visible.length;
      input.setAttribute("aria-expanded", String(!!visible.length));
    }
    function highlight() {
      Array.prototype.forEach.call(list.children, function (li, i) {
        li.className = (visible[i] && visible[i].muted ? "is-muted" : "") + (i === active ? " is-active" : "");
        if (i === active) li.scrollIntoView({ block: "nearest" });
      });
    }
    function pick(i) {
      var o = visible[i];
      if (!o) return;
      input.value = o.id === null ? "" : o.label;
      close();
      opts.onSelect(o.id, o);
    }
    input.addEventListener("input", function () { render(input.value); });
    input.addEventListener("focus", function () { render(input.value); });
    input.addEventListener("blur", function () { setTimeout(close, 150); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { if (list.hidden) render(input.value); active = Math.min(active + 1, visible.length - 1); highlight(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); highlight(); e.preventDefault(); }
      else if (e.key === "Enter") { if (!list.hidden && active >= 0) { pick(active); e.preventDefault(); } else if (!list.hidden && visible.length === 1) { pick(0); e.preventDefault(); } }
      else if (e.key === "Escape" && !list.hidden) { close(); e.stopPropagation(); }
    });
    return {
      el: wrap,
      input: input,
      setOptions: function (o) { options = o || []; },
      setText: function (t) { input.value = t || ""; },
    };
  }

  // ---- compose draft persistence -------------------------------------------
  function draftKey(replyToId) {
    return "cbmDraft:contact:" + RECORD_ID + ":" + (replyToId || "new");
  }
  function loadDraft(replyToId) {
    try {
      var raw = localStorage.getItem(draftKey(replyToId));
      if (!raw) return null;
      var d = JSON.parse(raw);
      if (!d || !d.ts || Date.now() - d.ts > 7 * 24 * 3600 * 1000) return null;
      return d;
    } catch (e) { return null; }
  }
  function storeDraft(replyToId, state) {
    try { localStorage.setItem(draftKey(replyToId), JSON.stringify(state)); } catch (e) {}
  }
  function clearDraft(replyToId) {
    try { localStorage.removeItem(draftKey(replyToId)); } catch (e) {}
  }

  // ---- thread view ---------------------------------------------------------
  async function viewConversation(convId) {
    openComm("Conversation", "Loading…");
    var body = $("crCommBody");
    try {
      var c = await api("/conversations/" + encodeURIComponent(convId));
    } catch (e) {
      if (e.status === 401) { goLogin(); return; }
      body.innerHTML = ""; body.appendChild(el("p", "form-error", e.message)); return;
    }
    $("crCommTitle").textContent = c.subject || "(no subject)";
    body.innerHTML = "";
    // The server stamped this thread read on the fetch — reflect it locally.
    convRows.forEach(function (r) { if (r.id === convId) r.unread = false; });
    renderConversationRows(convRows);

    if (c.summary || (c.actionItems || []).length) {
      var sum = el("div", "cr__conv-summary");
      if (c.status) sum.appendChild(el("span", "cr__tag", c.status));
      if (c.summary) sum.appendChild(el("p", null, c.summary));
      if ((c.actionItems || []).length) {
        var ul = el("ul");
        c.actionItems.forEach(function (a) { ul.appendChild(el("li", null, a)); });
        sum.appendChild(ul);
      }
      body.appendChild(sum);
    }

    var lastInbound = null;
    (c.messages || []).forEach(function (m) {
      if (m.direction === "Inbound" && !m.bounce) lastInbound = m;
      var card = el("div", "cr__msg-card" + (m.bounce ? " cr__msg-card--bounce" : ""));
      var head = el("div", "cr__msg-head");
      var who = el("span", "cr__msg-who",
        (m.from || m.fromAddress || "") + (m.direction === "Outbound" && m.to ? " → " + m.to : ""));
      var when = el("span", "cr__msg-when", fmtWhen(m.sentAt));
      head.appendChild(who); head.appendChild(when);
      if (m.id && m.gmailMessageId && m.sourceMailbox) {
        var orig = el("a", "cr__msg-gmail", "View original");
        orig.href = "#";
        orig.title = "The complete message as it arrived — real formatting, inline images.";
        orig.addEventListener("click", function (e) { e.preventDefault(); viewOriginal(m, c, convId); });
        head.appendChild(orig);
      }
      if (m.rfcMessageId) {
        var a = el("a", "cr__msg-gmail", "Open in Gmail");
        a.href = "https://mail.google.com/mail/u/" +
          (senderMailbox ? encodeURIComponent(senderMailbox) : "0") +
          "/#search/rfc822msgid:" + encodeURIComponent(m.rfcMessageId);
        a.target = "_blank"; a.rel = "noopener";
        a.title = "Opens your own Gmail. If the message isn't in your mailbox, use View original instead.";
        head.appendChild(a);
      }
      card.appendChild(head);
      if (m.bounce) {
        card.appendChild(el("div", "cr__msg-bounce-note",
          "✕ Delivery failed — the address rejected the message. The email was not delivered."));
      }
      var mb = el("div", "cr__msg-html");
      mb.innerHTML = sanitizeHtml(m.bodyHtml || "");
      card.appendChild(mb);
      body.appendChild(card);
    });
    if (!(c.messages || []).length) {
      body.appendChild(el("p", "dir__restricted", "No messages stored for this conversation."));
    }

    var foot = $("crCommFoot"); foot.innerHTML = "";
    var lastMsg = (c.messages || [])[(c.messages || []).length - 1] || null;
    var quoteSrc = lastInbound || lastMsg;
    function quoteOf(m) {
      if (!m || !m.bodyHtml) return null;
      return { html: m.bodyHtml, from: m.from || m.fromAddress || "", date: m.sentAt || "" };
    }
    function threadParticipants() {
      var seen = {}, out = [];
      (c.messages || []).forEach(function (m) {
        [m.fromAddress].concat(
          String(m.to || "").split(/[,;]+/),
          String(m.cc || "").split(/[,;]+/)
        ).forEach(function (a) {
          a = extractEmail(a || "").toLowerCase();
          if (!a || a.indexOf("@") === -1 || seen[a]) return;
          if (senderMailbox && a === String(senderMailbox).toLowerCase()) return;
          seen[a] = 1; out.push(a);
        });
      });
      return out;
    }
    function openReply(toList) {
      composeMessage({
        to: toList.join(", "),
        subject: replySubject(c.subject),
        replyToId: lastInbound ? lastInbound.id : null,
        quote: quoteOf(quoteSrc),
        backToConv: convId,
      });
    }
    var reply = el("button", "cbm-button", "↩ Reply"); reply.type = "button";
    reply.addEventListener("click", function () {
      openReply(lastInbound && lastInbound.fromAddress ? [lastInbound.fromAddress] : []);
    });
    foot.appendChild(reply);
    var participants = threadParticipants();
    if (participants.length > 1) {
      var replyAll = el("button", "cbm-button cbm-button--secondary", "↩ Reply all (" + participants.length + ")");
      replyAll.type = "button";
      replyAll.addEventListener("click", function () { openReply(participants); });
      foot.appendChild(replyAll);
    }
    if (lastMsg && lastMsg.bodyHtml) {
      var fwd = el("button", "cbm-button cbm-button--secondary", "↪ Forward"); fwd.type = "button";
      fwd.addEventListener("click", function () {
        var s = String(c.subject || "");
        composeMessage({
          subject: /^fwd:/i.test(s) ? s : "Fwd: " + s,
          forward: {
            html: lastMsg.bodyHtml,
            from: lastMsg.from || lastMsg.fromAddress || "",
            date: lastMsg.sentAt || "",
            to: lastMsg.to || "",
            subject: c.subject || "",
          },
          backToConv: convId,
        });
      });
      foot.appendChild(fwd);
    }
    foot.appendChild(removeConversationBtn(convId));
    var close = el("button", "cbm-button cbm-button--secondary", "Close"); close.type = "button";
    close.addEventListener("click", closeComm);
    foot.appendChild(close);
  }

  async function viewOriginal(m, c, convId) {
    var body = $("crCommBody");
    $("crCommTitle").textContent = (c.subject || "(no subject)") + " — original";
    body.innerHTML = "";
    body.appendChild(el("p", "dir__restricted", "Loading the original message…"));
    var foot = $("crCommFoot"); foot.innerHTML = "";
    var back = el("button", "cbm-button cbm-button--secondary", "← Back to conversation"); back.type = "button";
    back.addEventListener("click", function () { viewConversation(convId); });
    foot.appendChild(back);
    try {
      var o = await api("/communications/" + encodeURIComponent(m.id) + "/original");
    } catch (e) {
      if (e.status === 401) { goLogin(); return; }
      body.innerHTML = ""; body.appendChild(el("p", "form-error", e.message)); return;
    }
    body.innerHTML = "";
    var meta = el("div", "cr__orig-meta");
    [["From", o.from || o.fromAddress], ["To", o.to], ["Cc", o.cc],
     ["Date", fmtWhen(o.sentAt)], ["Subject", o.subject]
    ].forEach(function (pair) {
      if (!pair[1]) return;
      var row = el("div");
      row.appendChild(el("span", "cr__orig-l", pair[0] + ": "));
      row.appendChild(el("span", null, pair[1]));
      meta.appendChild(row);
    });
    body.appendChild(meta);
    var atts = (o.attachments || []).filter(function (a) { return !a.inline; });
    if (atts.length) {
      body.appendChild(el("div", "cr__orig-atts", "Attachments: " + atts.map(function (a) {
        return (a.filename || "attachment") + (a.size ? " (" + fmtBytes(a.size) + ")" : "");
      }).join(", ")));
    }
    var frame = el("iframe", "cr__orig-frame");
    frame.setAttribute("sandbox", "allow-same-origin allow-popups allow-popups-to-escape-sandbox");
    frame.srcdoc = "<!doctype html><html><head><style>" +
      "body{margin:12px;font-family:Arial,Helvetica,sans-serif;color:#222;background:#fff;word-break:break-word}" +
      "img{max-width:100%}" +
      "</style><base target=\"_blank\"></head><body>" +
      (o.bodyHtml || "<p>(no content)</p>") + "</body></html>";
    body.appendChild(frame);
  }

  // Two-step "Remove from this contact" (no browser confirm dialogs).
  function removeConversationBtn(convId) {
    var btn = el("button", "cbm-button cbm-button--secondary", "Not related — remove"); btn.type = "button";
    var armed = false;
    btn.addEventListener("click", async function () {
      if (!armed) { armed = true; btn.textContent = "Really remove from this contact?"; return; }
      btn.disabled = true;
      try {
        await api("/records/" + encodeURIComponent(RECORD_ID) +
                  "/conversations/" + encodeURIComponent(convId) + "/exclude", { method: "POST" });
        closeComm(); loadConversations();
      } catch (e) {
        if (e.status === 401) { goLogin(); return; }
        btn.disabled = false; btn.textContent = e.message;
      }
    });
    return btn;
  }

  // ---- "Add emails…" — mailbox search, attach a thread to this contact -----
  function addEmailsDialog() {
    openComm("Add emails", "Find a conversation in your mailbox");
    var body = $("crCommBody");
    var row = el("div", "cr__msg-field cr__search-row");
    var input = el("input"); input.type = "text"; input.className = "cr__msg-input";
    input.placeholder = "Search your mailbox (sender, subject, words…)";
    var go = el("button", "cbm-button", "Search"); go.type = "button";
    row.appendChild(input); row.appendChild(go); body.appendChild(row);
    var results = el("div"); body.appendChild(results);

    async function run() {
      var q = input.value.trim(); if (!q) return;
      results.innerHTML = "";
      results.appendChild(el("p", "dir__restricted", "Searching…"));
      try {
        var res = await api("/mailsearch?q=" + encodeURIComponent(q));
        results.innerHTML = "";
        var threads = res.threads || [];
        if (!threads.length) { results.appendChild(el("p", "dir__restricted", "No matching conversations.")); return; }
        threads.forEach(function (t) {
          var card = el("div", "cr__msg-card");
          var head = el("div", "cr__msg-head");
          head.appendChild(el("span", "cr__msg-who", (t.from || "") + " — " + (t.subject || "(no subject)")));
          head.appendChild(el("span", "cr__msg-when", fmtWhen(t.date)));
          var add = el("button", "cbm-button dir__sm", "Add to this contact"); add.type = "button";
          add.addEventListener("click", async function () {
            add.disabled = true; add.textContent = "Adding…";
            try {
              await api("/records/" + encodeURIComponent(RECORD_ID) + "/conversations/include", {
                method: "POST", body: JSON.stringify({ gmailThreadId: t.gmailThreadId })
              });
              add.textContent = "Added ✓"; loadConversations();
            } catch (e) {
              if (e.status === 401) { goLogin(); return; }
              add.disabled = false; add.textContent = e.message;
            }
          });
          head.appendChild(add);
          card.appendChild(head);
          card.appendChild(el("p", "dir__restricted", t.snippet || ""));
          results.appendChild(card);
        });
      } catch (e) {
        if (e.status === 401) { goLogin(); return; }
        results.innerHTML = ""; results.appendChild(el("p", "form-error", e.message));
      }
    }
    go.addEventListener("click", run);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") run(); });
    var foot = $("crCommFoot"); foot.innerHTML = "";
    var close = el("button", "cbm-button cbm-button--secondary", "Close"); close.type = "button";
    close.addEventListener("click", closeComm);
    foot.appendChild(close);
    input.focus();
  }

  // ---- compose -------------------------------------------------------------
  function composeMessage(pre) {
    pre = pre || {};
    var replyKey = pre.replyToId || null;
    openComm((detail && detail.name) || "",
      pre.forward ? "Forward" : (pre.replyToId ? "Reply" : "New email"));
    var body = $("crCommBody");

    var fromRow = commHeaderRow("From", senderMailbox || "…");
    body.appendChild(fromRow);
    function setFrom(text) { fromRow.querySelector(".cr__fact-v").textContent = text; }
    function seedIfReady() { if (senderSignature) seedSignature(); }
    if (senderMailbox === undefined) {
      api("/mailbox").then(function (r) {
        senderMailbox = (r && r.mailbox) || null;
        senderSignature = (r && r.signature) || "";
        setFrom(senderMailbox || "no CBM email on your profile — sending won't work");
        seedIfReady();
      }).catch(function () { setFrom("your CBM email address"); });
    } else if (senderMailbox === null) {
      setFrom("no CBM email on your profile — sending won't work");
    }

    // To: the contact's own addresses as checkboxes — all checked on a fresh
    // compose; a reply pre-checks only the replied-to addresses; a forward
    // starts with nobody selected.
    var preAddrs = String(pre.to || "").split(/[,;\s]+/).filter(Boolean)
      .map(function (a) { return extractEmail(a); });
    var preKeys = preAddrs.map(function (a) { return a.toLowerCase(); });
    var recipChecks = [];
    if (contactEmails.length) {
      var toWrap = el("div", "cr__msg-field");
      var toHead = el("div", "cr__to-head");
      toHead.appendChild(el("span", "cr__msg-label", "To"));
      toWrap.appendChild(toHead);
      var listEl = el("div", "cr__to-list");
      contactEmails.forEach(function (c) {
        var lab = el("label", "cr__addr-check");
        var box = el("input"); box.type = "checkbox";
        box.checked = pre.forward ? false
          : (pre.to ? preKeys.indexOf(c.email.toLowerCase()) !== -1 : true);
        box.addEventListener("change", onRecipientsChanged);
        lab.appendChild(box);
        lab.appendChild(document.createTextNode(" " + (c.name || c.email) + " — " + c.email));
        listEl.appendChild(lab);
        recipChecks.push({ email: c.email, box: box });
      });
      toWrap.appendChild(listEl);
      body.appendChild(toWrap);
    }
    var knownEmails = {};
    recipChecks.forEach(function (r) { knownEmails[r.email.toLowerCase()] = 1; });
    var extra = preAddrs.filter(function (a) { return !knownEmails[a.toLowerCase()]; }).join(", ");
    var addrPlaceholder = "name@example.com, another@example.com";
    var otherWrap = commField(contactEmails.length ? "Other recipients" : "To",
      "crMsgTo", extra, false, { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
    var otherLab = otherWrap.querySelector(".cr__msg-label");
    var toggles = el("span", "cr__ccbcc-toggles");
    var ccLink = el("button", "cr__link-btn", "Cc"); ccLink.type = "button";
    var bccLink = el("button", "cr__link-btn", "Bcc"); bccLink.type = "button";
    toggles.appendChild(ccLink); toggles.appendChild(bccLink);
    var labLine = el("div", "cr__to-head");
    otherWrap.insertBefore(labLine, otherLab);
    labLine.appendChild(otherLab); labLine.appendChild(toggles);
    body.appendChild(otherWrap);
    var ccField = commField("Cc", "crMsgCc", "", false, { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
    var bccField = commField("Bcc", "crMsgBcc", "", false, { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
    ccField.hidden = true; bccField.hidden = true;
    body.appendChild(ccField); body.appendChild(bccField);
    ccLink.addEventListener("click", function () { ccField.hidden = false; ccLink.hidden = true; $("crMsgCc").focus(); });
    bccLink.addEventListener("click", function () { bccField.hidden = false; bccLink.hidden = true; $("crMsgBcc").focus(); });

    function fieldAddrs(id) {
      var e = $(id);
      return e && !e.closest(".cr__msg-field").hidden ? parseAddrList(e.value) : { emails: [], invalid: [] };
    }
    function recipientSets() {
      var seen = {};
      function dedupe(list) {
        var out = [];
        list.forEach(function (a) {
          var k = a.toLowerCase();
          if (!seen[k]) { seen[k] = 1; out.push(a); }
        });
        return out;
      }
      var toParsed = fieldAddrs("crMsgTo"), ccParsed = fieldAddrs("crMsgCc"), bccParsed = fieldAddrs("crMsgBcc");
      var checked = [];
      recipChecks.forEach(function (r) { if (r.box.checked) checked.push(r.email); });
      return {
        to: dedupe(checked.concat(toParsed.emails)),
        cc: dedupe(ccParsed.emails),
        bcc: dedupe(bccParsed.emails),
        invalid: toParsed.invalid.concat(ccParsed.invalid, bccParsed.invalid),
      };
    }
    function recipientList() {
      var s = recipientSets();
      return s.to.concat(s.cc, s.bcc);
    }

    // --- template picker (ET): EspoCRM renders server-side; the parse feeds
    // this contact as the {Parent.*}/{Contact.*} context.
    var templateAttachments = [];   // {id, name} chips from the selected template
    var localAttachments = [];      // {filename, contentType, dataBase64, size}
    var tplConfirmEl = null, preTplSnapshot = null;
    var tplWrap = el("div", "cr__msg-field");
    tplWrap.hidden = true;
    var tplLab = el("span", "cr__msg-label", "Template");
    var tplCombo = makeCombobox({
      placeholder: "Search templates…",
      allowClear: true,
      emptyLabel: "No template",
      onSelect: function (id) { onTemplatePicked(id); },
    });
    var tplNotice = el("p", "cr__notice-line"); tplNotice.hidden = true;
    tplWrap.appendChild(tplLab); tplWrap.appendChild(tplCombo.el); tplWrap.appendChild(tplNotice);
    body.appendChild(tplWrap);
    if (commsOn()) {
      api("/emailtemplates").then(function (r) {
        var tpls = (r && r.templates) || [];
        if (tpls.length) {
          tplCombo.setOptions(tpls.map(function (t) { return { id: t.id, label: t.name }; }));
          tplWrap.hidden = false;
        }
      }).catch(function () { /* no picker — compose works without it */ });
    }

    var quoteHtml = pre.quote ? buildQuoteHtml(pre.quote)
      : (pre.forward ? buildForwardHtml(pre.forward) : "");
    var initialSubject = pre.subject || "";
    var pristineBodies = {};
    function markPristine(v) { pristineBodies[String(v || "")] = 1; }
    function bodyPristine() { return !!pristineBodies[String(commBodyValue() || "")]; }
    function seedSignature() {
      if (!senderSignature) return;
      if (!bodyPristine()) return;  // the user already typed — never overwrite
      setMsgBody("<p><br></p><p><br></p>" + senderSignature +
        (quoteHtml ? "<p><br></p>" + quoteHtml : ""));
      markPristine(commBodyValue());
    }
    function draftHasContent() {
      return !!($("crMsgSubject").value.trim() !== initialSubject.trim() && $("crMsgSubject").value.trim()) ||
        !bodyPristine() ||
        localAttachments.length > 0;
    }
    function setMsgBody(html) {
      var e = $("crMsgBody");
      if (!e) return;
      if (e._cbmRichText) e._cbmRichText.setValue(html);
      else e.value = html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/p\s*>/gi, "\n\n").replace(/<[^>]+>/g, "");
    }
    function buildQuoteHtml(q) {
      var head = "On " + (q.date ? fmtWhen(q.date) : "an earlier date") +
        ", " + (q.from || "they") + " wrote:";
      var p = el("p", null, head);  // textContent escapes the name
      return "<blockquote class=\"quoted-reply\">" + p.outerHTML + (q.html || "") + "</blockquote>";
    }
    function buildForwardHtml(f) {
      var lines = [
        "---------- Forwarded message ----------",
        "From: " + (f.from || "?"),
        f.date ? "Date: " + fmtWhen(f.date) : "",
        f.subject ? "Subject: " + f.subject : "",
        f.to ? "To: " + f.to : "",
      ].filter(Boolean);
      var headHtml = lines.map(function (t) { return el("p", null, t).outerHTML; }).join("");
      return "<blockquote class=\"quoted-reply\">" + headHtml + (f.html || "") + "</blockquote>";
    }
    function onTemplatePicked(id) {
      if (tplConfirmEl) { tplConfirmEl.remove(); tplConfirmEl = null; }
      if (!id) {
        if (preTplSnapshot) {
          $("crMsgSubject").value = preTplSnapshot.subject;
          setMsgBody(preTplSnapshot.body);
          if (preTplSnapshot.pristine) markPristine(commBodyValue());
          templateAttachments = preTplSnapshot.tplAttach.slice();
          renderAttachChips();
          preTplSnapshot = null;
          tplNotice.hidden = true;
          markEdited();
        }
        return;
      }
      if (!draftHasContent()) { applyTemplate(id); return; }
      tplConfirmEl = el("div", "cr__notice-line is-warn");
      tplConfirmEl.appendChild(document.createTextNode("Replace current content? "));
      var yes = el("button", "cbm-button", "Replace"); yes.type = "button";
      var no = el("button", "cbm-button cbm-button--secondary", "Keep my draft"); no.type = "button";
      yes.addEventListener("click", function () { tplConfirmEl.remove(); tplConfirmEl = null; applyTemplate(id); });
      no.addEventListener("click", function () { tplConfirmEl.remove(); tplConfirmEl = null; tplCombo.setText(""); });
      tplConfirmEl.appendChild(yes); tplConfirmEl.appendChild(document.createTextNode(" "));
      tplConfirmEl.appendChild(no);
      tplWrap.appendChild(tplConfirmEl);
    }
    async function applyTemplate(id) {
      tplNotice.hidden = true;
      preTplSnapshot = {
        subject: $("crMsgSubject").value,
        body: String(commBodyValue() || ""),
        pristine: bodyPristine(),
        tplAttach: templateAttachments.slice(),
      };
      try {
        var r = await api("/records/" + encodeURIComponent(RECORD_ID) +
          "/emailtemplates/" + encodeURIComponent(id) + "/parse", {
          method: "POST",
          body: JSON.stringify({ emailAddress: recipientList()[0] || "" }),
        });
        $("crMsgSubject").value = r.subject || "";
        setMsgBody((r.bodyHtml || "") +
          (senderSignature ? "<p><br></p>" + senderSignature : "") +
          (quoteHtml ? "<p><br></p>" + quoteHtml : ""));
        templateAttachments = (r.attachments || []).slice();
        renderAttachChips();
        if ((r.leftoverTokens || []).length) {
          tplNotice.textContent = "Some placeholders couldn't be filled: " +
            r.leftoverTokens.join(", ") + " — review the draft before sending.";
          tplNotice.className = "cr__notice-line is-warn"; tplNotice.hidden = false;
        }
        markEdited();
      } catch (e) {
        if (e.status === 401) { flushDraft(); goLogin(); return; }
        preTplSnapshot = null;
        tplNotice.textContent = e.message || "Couldn't apply the template.";
        tplNotice.className = "cr__notice-line is-error"; tplNotice.hidden = false;
        tplCombo.setText("");
      }
    }

    body.appendChild(commField("Subject", "crMsgSubject", pre.subject, false, { onInput: markEdited }));
    body.appendChild(commField("Message", "crMsgBody", "", true, { onInput: markEdited }));
    markPristine("");
    if (quoteHtml) {
      setMsgBody("<p><br></p>" + quoteHtml);
      markPristine(commBodyValue());
    }
    if (senderSignature) seedSignature();

    // --- attachments: template chips + local uploads (20 MB total cap).
    var attachWrap = el("div", "cr__msg-field");
    var chipsEl = el("div", "cr__attach-chips");
    var attachTotalEl = el("p", "cr__attach-total"); attachTotalEl.hidden = true;
    var attachLine = el("div", "cr__opt-line");
    var fileBtn = el("button", "cbm-button cbm-button--secondary", "Attach files…"); fileBtn.type = "button";
    var fileInput = el("input"); fileInput.type = "file"; fileInput.multiple = true; fileInput.hidden = true;
    fileBtn.addEventListener("click", function () { fileInput.click(); });
    attachLine.appendChild(fileBtn); attachLine.appendChild(fileInput);
    attachWrap.appendChild(el("span", "cr__msg-label", "Attachments"));
    attachWrap.appendChild(chipsEl); attachWrap.appendChild(attachTotalEl); attachWrap.appendChild(attachLine);
    body.appendChild(attachWrap);
    var MAX_ATTACH_TOTAL = 20 * 1024 * 1024;
    function attachTotal() {
      return localAttachments.reduce(function (n, f) { return n + (f.size || 0); }, 0);
    }
    function renderAttachChips() {
      chipsEl.innerHTML = "";
      function chip(name, size, onRemove) {
        var c = el("span", "cr__attach-chip");
        c.appendChild(document.createTextNode(name + " "));
        if (size) c.appendChild(el("span", "cr__attach-size", "(" + fmtBytes(size) + ") "));
        var x = el("button", "cr__chip-x", "✕"); x.type = "button"; x.title = "Remove attachment";
        x.addEventListener("click", onRemove);
        c.appendChild(x); chipsEl.appendChild(c);
      }
      templateAttachments.forEach(function (a, i) {
        chip(a.name || "attachment", a.size || 0, function () {
          templateAttachments.splice(i, 1); renderAttachChips(); markEdited();
        });
      });
      localAttachments.forEach(function (f, i) {
        chip(f.filename, f.size || 0, function () {
          localAttachments.splice(i, 1); renderAttachChips(); markEdited();
        });
      });
      var total = attachTotal();
      attachTotalEl.hidden = !localAttachments.length;
      attachTotalEl.textContent = "Total " + fmtBytes(total) + " of 20 MB";
    }
    fileInput.addEventListener("change", function () {
      Array.prototype.forEach.call(fileInput.files || [], function (file) {
        if (attachTotal() + file.size > MAX_ATTACH_TOTAL) {
          footErr("“" + file.name + "” would push the attachments over 20 MB — remove something first.");
          return;
        }
        var reader = new FileReader();
        reader.onload = function () {
          var b64 = String(reader.result || "").split(",")[1] || "";
          localAttachments.push({
            filename: file.name,
            contentType: file.type || "application/octet-stream",
            dataBase64: b64,
            size: file.size,
          });
          renderAttachChips();
          markEdited();
        };
        reader.readAsDataURL(file);
      });
      fileInput.value = "";
    });
    function attachmentPayload() {
      return templateAttachments.map(function (a) {
        return { espoId: a.id, filename: a.name };
      }).concat(localAttachments.map(function (f) {
        return { filename: f.filename, contentType: f.contentType, dataBase64: f.dataBase64 };
      }));
    }

    var allowUnknown = false;
    var resolvedAddresses = {};   // addresses handled (added) this compose
    var commResolvers = null;     // one entry per unknown recipient, built once
    var optionsPanel = el("div");
    body.appendChild(optionsPanel);

    // --- footer: status line + Cancel + Send.
    var foot = $("crCommFoot"); foot.innerHTML = "";
    var footMsg = el("p", "cr__foot-msg form-error"); footMsg.hidden = true;
    var footSummary = el("p", "cr__foot-summary");
    var cancel = el("button", "cbm-button cbm-button--secondary", "Cancel"); cancel.type = "button";
    cancel.addEventListener("click", requestCloseComm);
    var send = el("button", "cbm-button", "Send"); send.type = "button";
    foot.appendChild(footSummary); foot.appendChild(footMsg);
    foot.appendChild(cancel); foot.appendChild(send);

    function footErr(text) {
      footMsg.textContent = text; footMsg.className = "cr__foot-msg form-error";
      footMsg.hidden = false; footSummary.hidden = true;
    }
    function footWarn(text) {
      footMsg.textContent = text; footMsg.className = "cr__foot-msg cr__notice-line is-warn";
      footMsg.hidden = false; footSummary.hidden = true;
    }
    function clearFootMsg() { footMsg.hidden = true; footSummary.hidden = false; }
    function updateSummary() {
      var s = recipientSets();
      var n = s.to.length + s.cc.length + s.bcc.length;
      if (!n) { footSummary.textContent = "No recipients selected."; return; }
      var parts = [];
      if (s.cc.length || s.bcc.length) {
        parts.push(s.to.length + " To");
        if (s.cc.length) parts.push(s.cc.length + " Cc");
        if (s.bcc.length) parts.push(s.bcc.length + " Bcc");
      }
      footSummary.textContent = "Sending to " + n + (n === 1 ? " recipient" : " recipients") +
        (parts.length ? " (" + parts.join(", ") + ")" : "");
    }

    var sendArmed = false;
    function disarmSend() {
      if (sendArmed) { sendArmed = false; send.textContent = commResolvers ? "Add & Send" : "Send"; }
    }
    function onRecipientsChanged() {
      if (commResolvers) {
        commResolvers = null; allowUnknown = false;
        optionsPanel.innerHTML = "";
        send.textContent = "Send";
      }
      disarmSend(); clearFootMsg(); updateSummary(); markEdited();
    }
    updateSummary();

    // --- draft persistence.
    var draftTimer = null;
    function draftState() {
      return {
        ts: Date.now(),
        subject: $("crMsgSubject").value,
        body: String(commBodyValue() || ""),
        to: $("crMsgTo").value,
        cc: $("crMsgCc") ? $("crMsgCc").value : "",
        bcc: $("crMsgBcc") ? $("crMsgBcc").value : "",
        ccShown: !ccField.hidden, bccShown: !bccField.hidden,
        checked: recipChecks.filter(function (r) { return r.box.checked; })
          .map(function (r) { return r.email.toLowerCase(); }),
        tplAttach: templateAttachments,
      };
    }
    function flushDraft() {
      if (draftTimer) { clearTimeout(draftTimer); draftTimer = null; }
      if (draftHasContent()) storeDraft(replyKey, draftState());
    }
    function markEdited() {
      disarmSend();
      if (draftTimer) clearTimeout(draftTimer);
      draftTimer = setTimeout(function () {
        draftTimer = null;
        if (draftHasContent()) storeDraft(replyKey, draftState());
        else clearDraft(replyKey);
      }, 800);
    }
    var savedDraft = loadDraft(replyKey);
    if (savedDraft && (savedDraft.subject || savedDraft.body || savedDraft.to)) {
      $("crMsgSubject").value = savedDraft.subject || "";
      if (savedDraft.body) setMsgBody(savedDraft.body);
      $("crMsgTo").value = savedDraft.to || "";
      if (savedDraft.ccShown || savedDraft.cc) { ccField.hidden = false; ccLink.hidden = true; $("crMsgCc").value = savedDraft.cc || ""; }
      if (savedDraft.bccShown || savedDraft.bcc) { bccField.hidden = false; bccLink.hidden = true; $("crMsgBcc").value = savedDraft.bcc || ""; }
      if (savedDraft.checked && recipChecks.length) {
        var wanted = {};
        savedDraft.checked.forEach(function (a) { wanted[a] = 1; });
        recipChecks.forEach(function (r) { r.box.checked = !!wanted[r.email.toLowerCase()]; });
      }
      templateAttachments = (savedDraft.tplAttach || []).slice();
      renderAttachChips();
      updateSummary();
      var note = el("div", "cr__notice-line cr__draft-note");
      note.appendChild(document.createTextNode("Restored your unsent draft."));
      var fresh = el("button", "cr__link-btn", "Start fresh"); fresh.type = "button";
      fresh.addEventListener("click", function () {
        clearDraft(replyKey);
        note.remove();
        $("crMsgSubject").value = initialSubject;
        setMsgBody("");
        markPristine("");
        if (quoteHtml) { setMsgBody("<p><br></p>" + quoteHtml); markPristine(commBodyValue()); }
        seedSignature();
        $("crMsgTo").value = extra;
        if ($("crMsgCc")) $("crMsgCc").value = "";
        if ($("crMsgBcc")) $("crMsgBcc").value = "";
        recipChecks.forEach(function (r) {
          r.box.checked = pre.forward ? false
            : (pre.to ? preKeys.indexOf(r.email.toLowerCase()) !== -1 : true);
        });
        templateAttachments = []; localAttachments = [];
        renderAttachChips(); updateSummary(); clearFootMsg();
      });
      note.appendChild(fresh);
      body.insertBefore(note, body.firstChild);
    }

    composeGuard = {
      dirty: function () { return draftHasContent(); },
      discard: function () {
        if (draftTimer) { clearTimeout(draftTimer); draftTimer = null; }
        clearDraft(replyKey);
      },
      backConvId: pre.backToConv || null,
    };

    // Recipients that are neither this contact's addresses nor CBM-internal.
    function unknownRecipients(recipients) {
      var known = {};
      contactEmails.forEach(function (c) { known[c.email.toLowerCase()] = 1; });
      return recipients.filter(function (a) {
        a = a.toLowerCase();
        return !known[a] && !resolvedAddresses[a] && !/@cbmentors\.org$/.test(a);
      });
    }

    // The unknown-recipient panel, contact-scoped: an address the CRM doesn't
    // know can be ADDED TO THIS CONTACT (their second address — common case);
    // an address that belongs to someone else just receives the email. No
    // create-contact/company branch here — that lives on the record pages.
    async function buildUnknownPanel(unknown) {
      optionsPanel.innerHTML = "";
      optionsPanel.appendChild(el("p", "dir__restricted", "Checking the CRM for " +
        (unknown.length === 1 ? "this address…" : "these addresses…")));
      var lookups = {};
      for (var i = 0; i < unknown.length; i++) {
        try { lookups[unknown[i]] = await api("/contactlookup?email=" + encodeURIComponent(unknown[i])); }
        catch (e) {
          if (e.status === 401) { flushDraft(); goLogin(); return; }
          lookups[unknown[i]] = { found: false };
        }
      }
      optionsPanel.innerHTML = "";
      var head = el("p", "cr__notice-line is-warn",
        (unknown.length === 1 ? "This recipient isn't" : "These recipients aren't") +
        " one of " + ((detail && detail.name) || "this contact") + "'s known addresses." +
        " Leave the box checked to save a new address on this contact, or uncheck to just send." +
        " Then click Add & Send.");
      optionsPanel.appendChild(head);
      commResolvers = [];
      unknown.forEach(function (addr) {
        optionsPanel.appendChild(addressRow(addr, lookups[addr] || { found: false }));
      });
      send.textContent = "Add & Send";
      optionsPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function addressRow(addr, lookup) {
      var row = el("div", "cr__msg-field cr__addr-row");
      var head = el("div", "cr__opt-line");
      var who = el("span", "cr__msg-label");
      var checkLab = el("label", "cr__addr-check");
      var check = el("input"); check.type = "checkbox";
      checkLab.appendChild(check);
      var checkText = document.createTextNode("");
      checkLab.appendChild(checkText);
      head.appendChild(who); head.appendChild(checkLab);
      row.appendChild(head);
      var err = el("p", "form-error"); err.hidden = true;

      var resolver;
      if (lookup.found && lookup.contact) {
        // Belongs to someone else in the CRM — never graft their address onto
        // THIS contact; they simply receive the email.
        var c = lookup.contact;
        var kind = c.isCbmMember ? "a CBM member" : (c.company ? c.company : "an existing contact");
        who.textContent = addr + " — " + (c.name || "?") + " (" + kind + ", already in the CRM)";
        check.checked = false; check.disabled = true;
        checkText.textContent = " Will receive the email";
        resolver = async function () { return false; };
      } else {
        who.textContent = addr + " — not one of this contact's saved addresses";
        check.checked = true;
        checkText.textContent = " Add this address to " + ((detail && detail.name) || "the contact");
        resolver = async function () {
          if (!check.checked) return false;
          await api("/contacts/" + encodeURIComponent(RECORD_ID) + "/addresses", {
            method: "POST", body: JSON.stringify({ address: addr }),
          });
          resolvedAddresses[addr.toLowerCase()] = 1;
          contactEmails.push({ name: (detail && detail.name) || addr, email: addr });
          return true;
        };
      }
      row.appendChild(err);
      commResolvers.push({ addr: addr, resolve: resolver, errEl: err });
      return row;
    }

    async function doSend() {
      var sets = recipientSets();
      if (sets.invalid.length) {
        footErr("These don't look like email addresses: " + sets.invalid.join(", ") +
          " — fix or remove them. Separate addresses with commas.");
        return;
      }
      var recipients = sets.to.concat(sets.cc, sets.bcc);
      if (!recipients.length) {
        footErr("Choose at least one recipient.");
        $("crMsgTo").focus();
        return;
      }
      if (bodyPristine() && !pre.forward) {
        footErr("Write a message first.");
        var bodyEl = $("crMsgBody");
        if (bodyEl && bodyEl._cbmRichText) bodyEl._cbmRichText.focus();
        else if (bodyEl) bodyEl.focus();
        return;
      }
      var holdups = [];
      if (!$("crMsgSubject").value.trim()) holdups.push("it has no subject");
      var tokenScan = ($("crMsgSubject").value + " " + String(commBodyValue() || ""))
        .replace(new RegExp("<blockquote[\\s\\S]*$"), "");
      var leftover = tokenScan.match(/\{[A-Za-z][A-Za-z0-9]*\.[A-Za-z0-9_]+\}/g);
      if (leftover) holdups.push("it still contains unfilled placeholders (" + leftover.slice(0, 3).join(", ") + ")");
      if (holdups.length && !sendArmed) {
        sendArmed = true;
        footWarn("Before this goes out: " + holdups.join(", and ") + ". Click “Send anyway” to send it as is.");
        send.textContent = "Send anyway";
        return;
      }
      clearFootMsg();
      var unknown = unknownRecipients(recipients);
      if (unknown.length && commResolvers === null) {
        await buildUnknownPanel(unknown);   // first click: show the rows
        return;
      }
      if (commResolvers) {
        for (var ri = 0; ri < commResolvers.length; ri++) {
          var r = commResolvers[ri];
          if (resolvedAddresses[r.addr.toLowerCase()]) continue;
          r.errEl.hidden = true;
          try {
            var did = await r.resolve();
            if (!did) allowUnknown = true;
          } catch (e) {
            if (e.status === 401) { flushDraft(); goLogin(); return; }
            r.errEl.textContent = e.message; r.errEl.hidden = false;
            r.errEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
            footErr("Fix the highlighted recipient above (or uncheck it), then Send again.");
            return;
          }
        }
      }
      send.disabled = true; send.textContent = "Sending…";
      var payload = {
        to: sets.to,
        cc: sets.cc,
        bcc: sets.bcc,
        subject: $("crMsgSubject").value,
        body: commBodyValue(),
        replyToCommunicationId: pre.replyToId || null,
        allowUnknownRecipients: allowUnknown,
        attachments: attachmentPayload(),
      };
      var showProgress = JSON.stringify(payload).length > 300 * 1024;
      try {
        var sendResult = await apiPostProgress(
          "/records/" + encodeURIComponent(RECORD_ID) + "/messages",
          payload,
          showProgress ? function (pct) { send.textContent = "Sending… " + pct + "%"; } : null
        );
        clearDraft(replyKey);
        if (sendResult && sendResult.writeBack && sendResult.writeBack.ok === false) {
          composeGuard = null;
          showWriteBackRetry(sendResult.writeBack);
          loadConversations();
          return;
        }
        closeComm();
        if (sendResult && sendResult.ingestWarning) {
          notify("Email sent. " + sendResult.ingestWarning);
        } else {
          notify("Email sent.");
        }
        loadConversations();
      } catch (e) {
        if (e.status === 401) { flushDraft(); goLogin(); return; }
        footErr(e.message);
        send.disabled = false; send.textContent = commResolvers ? "Add & Send" : "Send";
        sendArmed = false;
        if (e.status === 400 && /aren't contacts/.test(e.message || "")) {
          commResolvers = null;
          var still = unknownRecipients(recipientList());
          if (still.length) await buildUnknownPanel(still);
        }
      }
    }
    send.addEventListener("click", doSend);

    // Sent-but-not-recorded: swap the dialog to a retry screen (ET-142).
    function showWriteBackRetry(writeBack) {
      $("crCommBody").innerHTML = "";
      var note = el("p", "cr__notice-line is-error",
        writeBack.error || "The message WAS sent, but recording it in the CRM failed.");
      $("crCommBody").appendChild(note);
      $("crCommFoot").innerHTML = "";
      var retry = el("button", "cbm-button", "Retry recording"); retry.type = "button";
      var close = el("button", "cbm-button cbm-button--secondary", "Close"); close.type = "button";
      retry.addEventListener("click", async function () {
        retry.disabled = true; retry.textContent = "Recording…";
        try {
          await api("/emailwriteback", {
            method: "POST", body: JSON.stringify(writeBack.retryPayload || {}),
          });
          closeComm();
          notify("Email sent and recorded in the CRM.");
        } catch (e) {
          if (e.status === 401) { goLogin(); return; }
          note.textContent = (e.message || "Still couldn't record it.") + " Try again?";
          retry.disabled = false; retry.textContent = "Retry recording";
        }
      });
      close.addEventListener("click", closeComm);
      $("crCommFoot").appendChild(retry); $("crCommFoot").appendChild(close);
    }

    // Keyboard start: the first thing that still needs filling in.
    var focusTarget = null;
    if (!recipientList().length) focusTarget = $("crMsgTo");
    else if (!$("crMsgSubject").value.trim()) focusTarget = $("crMsgSubject");
    if (focusTarget) focusTarget.focus();
    else {
      var be = $("crMsgBody");
      if (be && be._cbmRichText) be._cbmRichText.focus();
      else if (be) be.focus();
    }
  }

  // ---- wiring --------------------------------------------------------------
  function wire() {
    document.querySelectorAll("#crTabs .cr__tab").forEach(function (b) {
      b.addEventListener("click", function () { switchTab(b.dataset.crtab); });
    });
    $("crComposeBtn").addEventListener("click", function () {
      if (!commsOn()) { notify("The email integration isn't enabled on this deployment."); return; }
      composeMessage({});
    });
    $("crAddEmailsBtn").addEventListener("click", function () {
      if (!commsOn()) { notify("The email integration isn't enabled on this deployment."); return; }
      addEmailsDialog();
    });
    $("crRefreshBtn").addEventListener("click", function () {
      if (commsOn()) loadConversations();
    });
    $("crCommClose").addEventListener("click", requestCloseComm);
    $("crCommModal").addEventListener("click", function (e) { if (e.target === $("crCommModal")) requestCloseComm(); });
    $("crConfirmCancel").addEventListener("click", closeConfirm);
    $("crConfirmDiscard").addEventListener("click", function () {
      var fn = confirmOnDiscard; closeConfirm();
      if (fn) fn();
    });
    $("crConfirmModal").addEventListener("click", function (e) { if (e.target === $("crConfirmModal")) closeConfirm(); });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!$("crConfirmModal").hidden) closeConfirm();
      else if (!$("crCommModal").hidden) requestCloseComm();
    });
    $("crReloadBtn").addEventListener("click", function () { location.reload(); });
    $("crLogoutBtn").addEventListener("click", async function () {
      try { await api("/logout", { method: "POST" }); } catch (e) {}
      location.href = "/";
    });
  }

  (async function init() {
    try { if (window.CBMQuickMail) window.CBMQuickMail.apiBase = API; } catch (e) {}
    if (!RECORD_ID) { fail(new Error("No contact id in the address.")); return; }
    var owner = await acquireRecordLock("contact:" + RECORD_ID);
    if (!owner) { hide($("crMainView")); show($("crBlockedView")); wire(); return; }
    try {
      session = await api("/session");
      detail = await api("/records/" + encodeURIComponent(RECORD_ID));
      document.title = "CBM — " + (detail.name || "Contact");
      $("crTitle").textContent = detail.name || "(no name)";
      $("crWhoName").textContent = session.name || session.userName;
      contactEmails = collectContactEmails();
      renderOverview();
      wire();
      show($("crMainView"));
    } catch (e) { fail(e); }
  })();
})();
