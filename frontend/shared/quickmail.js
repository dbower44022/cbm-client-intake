/* Quick-email compose — the product-wide replacement for bare mailto: links
 * (Doug's ruling 2026-07-16: an email address shown anywhere in the staff
 * UIs opens the app's own compose dialog).
 *
 * Usage: include this script, then render addresses with
 *   CBMQuickMail.emailLink("person@example.com")
 * The returned <a> keeps a real mailto: href (middle-click / copy-link still
 * behave), but a plain click opens a compose dialog that sends as the
 * signed-in user's own CBM mailbox via the app (`GET  <app>/api/mailbox`,
 * `POST <app>/api/sendmail` — see comms/quicksend.py). When sending isn't
 * available (Gmail integration off, or no CBM mailbox on the user's profile)
 * the click falls back to the browser's mailto: handler.
 *
 * The dialog is a resizable workspace (90% of the window, pinned footer) with
 * To/Cc/Bcc (validated address lists), an email-template picker (searchable;
 * EspoCRM renders server-side, "no template" restores the prior draft),
 * attachments with sizes and a 20 MB running total, upload progress on big
 * sends, Ctrl+Enter to send, a discard-confirm on close, and a localStorage
 * draft (keyed by app + first recipient) so an accidental close never loses
 * a typed message. A failed CRM write-back after a confirmed send offers a
 * retry (`POST <app>/api/emailwriteback`) — never silent (ET-142).
 *
 * The session tools' RECORD pages don't use this widget — their record-scoped
 * compose (contact linking, reply threading) covers every email they show;
 * their grid pages (peeks) do.
 */
(function () {
  "use strict";

  // "/assignments/…" -> "/assignments/api"; override via CBMQuickMail.apiBase.
  var seg = window.location.pathname.split("/").filter(Boolean)[0] || "";
  var state = {
    apiBase: "/" + seg + "/api",
    mailbox: undefined,      // undefined = not asked yet; null = can't send
    enabled: undefined,
    signature: "",           // the user's EspoCRM Preferences signature (HTML)
    probe: null,             // in-flight mailbox fetch
  };

  var MAX_ATTACH_TOTAL = 20 * 1024 * 1024;  // matches the server cap

  function probeMailbox() {
    if (state.probe) return state.probe;
    state.probe = fetch(state.apiBase + "/mailbox", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { mailbox: null, sendEnabled: false }; })
      .then(function (d) {
        state.mailbox = d.mailbox || null;
        state.enabled = !!d.sendEnabled;
        state.signature = d.signature || "";
        return state;
      })
      .catch(function () {
        state.mailbox = null; state.enabled = false;
        return state;
      });
    return state.probe;
  }

  function post(path, payload) {
    return fetch(state.apiBase + path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) { var e = new Error(d.detail || "Request failed."); e.status = r.status; throw e; }
        return d;
      });
    });
  }

  // POST with upload progress (attachments make one big JSON body; fetch
  // gives no upload feedback). Same error contract as post().
  function postProgress(path, payload, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", state.apiBase + path);
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
        var e = new Error((data && data.detail) || "Request failed.");
        e.status = xhr.status;
        reject(e);
      };
      xhr.onerror = xhr.onabort = xhr.ontimeout = function () {
        reject(new Error("The send was interrupted — check your connection and try again."));
      };
      xhr.send(JSON.stringify(payload));
    });
  }

  // "a@b.c, Jane Doe <jane@x.org>" -> {emails: [...], invalid: [...]}.
  // Splits on commas/semicolons/newlines (display names contain spaces);
  // accepts Name <email>; validates the address shape.
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

  function fmtBytes(n) {
    if (!n && n !== 0) return "";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  function draftKey(toAddress) {
    return "cbmQuickDraft:" + state.apiBase + ":" + String(toAddress || "").toLowerCase();
  }
  function loadDraft(toAddress) {
    try {
      var raw = localStorage.getItem(draftKey(toAddress));
      if (!raw) return null;
      var d = JSON.parse(raw);
      if (!d || !d.ts || Date.now() - d.ts > 7 * 24 * 3600 * 1000) return null;
      return d;
    } catch (e) { return null; }
  }
  function storeDraft(toAddress, stateObj) {
    try { localStorage.setItem(draftKey(toAddress), JSON.stringify(stateObj)); } catch (e) {}
  }
  function clearDraft(toAddress) {
    try { localStorage.removeItem(draftKey(toAddress)); } catch (e) {}
  }

  function injectStyles() {
    if (document.getElementById("qm-styles")) return;
    var css = "" +
      ".qm-overlay{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;" +
      "align-items:center;justify-content:center;padding:16px;z-index:1000}" +
      // A resizable 90% workspace: flex column, pinned footer, body scrolls.
      ".qm-box{background:var(--cbm-surface,#fff);color:var(--cbm-text,#1a202c);border-radius:10px;" +
      "box-shadow:0 18px 50px rgba(0,0,0,.28);width:90vw;height:90vh;" +
      "max-width:96vw;max-height:94vh;min-width:320px;min-height:260px;" +
      "resize:both;overflow:hidden;display:flex;flex-direction:column;" +
      "font-family:var(--cbm-font-body,system-ui,sans-serif)}" +
      ".qm-head{padding:16px 22px 10px;border-bottom:1px solid var(--cbm-border,#e6eaef)}" +
      ".qm-head h2{margin:0;font-size:1.15rem}" +
      ".qm-body{flex:1 1 auto;overflow-y:auto;padding:12px 22px}" +
      ".qm-row{margin:0 0 10px}" +
      ".qm-row label,.qm-lab{display:block;font-size:.8rem;font-weight:600;margin-bottom:3px;color:var(--cbm-muted,#4a5568)}" +
      ".qm-row input,.qm-row textarea,.qm-row select{width:100%;box-sizing:border-box;padding:7px 9px;" +
      "border:1px solid var(--cbm-border,#cbd5e0);border-radius:6px;font:inherit}" +
      ".qm-row textarea{min-height:9em;resize:vertical}" +
      ".qm-lab-line{display:flex;align-items:baseline;gap:10px}" +
      ".qm-lab-line .qm-links{margin-left:auto;display:inline-flex;gap:10px}" +
      ".qm-link-btn{background:none;border:none;padding:0;font:inherit;font-size:.8rem;" +
      "color:var(--cbm-blue,#2b6cb0);cursor:pointer;text-decoration:underline}" +
      ".qm-from{font-size:.85rem;color:var(--cbm-muted,#4a5568);margin:0 0 10px}" +
      ".qm-from strong{color:inherit}" +
      ".qm-note{font-size:.85rem;background:#f7f9fb;border:1px solid var(--cbm-border,#cbd5e0);" +
      "border-radius:6px;padding:6px 9px;margin:6px 0 0}" +
      ".qm-note.qm-warn{background:#fdf6e7;border-color:#ecc94b;color:#744210}" +
      ".qm-note button{margin-left:6px}" +
      ".qm-chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 6px}" +
      ".qm-chips:empty{display:none}" +
      ".qm-chip{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;font-size:.85rem;" +
      "border:1px solid var(--cbm-border,#cbd5e0);border-radius:999px;background:#f7f9fb}" +
      ".qm-chip .qm-size{color:var(--cbm-muted,#4a5568);font-size:.78rem}" +
      ".qm-chip button{border:0;background:none;cursor:pointer;color:var(--cbm-muted,#4a5568);padding:0}" +
      ".qm-chip button:hover{color:var(--cbm-danger,#c53030)}" +
      ".qm-attach-total{margin:2px 0 0;color:var(--cbm-muted,#4a5568);font-size:.8rem}" +
      ".qm-err{color:var(--cbm-danger,#c53030);font-size:.85rem;margin:0}" +
      ".qm-warn-msg{color:#744210;font-size:.85rem;margin:0}" +
      ".qm-ok{color:#2f855a;font-size:.9rem;margin:6px 0 0}" +
      ".qm-foot{flex:0 0 auto;display:flex;gap:10px;align-items:center;justify-content:flex-end;" +
      "padding:10px 22px 14px;border-top:1px solid var(--cbm-border,#e6eaef)}" +
      ".qm-foot .qm-slot{flex:1 1 auto;text-align:left}" +
      ".qm-actions button,.qm-note button{font:inherit;padding:7px 16px;border-radius:6px;cursor:pointer;border:1px solid transparent}" +
      ".qm-foot button{font:inherit;padding:7px 16px;border-radius:6px;cursor:pointer;border:1px solid transparent}" +
      ".qm-send{background:var(--cbm-btn-bg,var(--cbm-blue,#2b6cb0));color:var(--cbm-btn-color,#fff)}" +
      ".qm-send[disabled]{opacity:.6;cursor:default}" +
      ".qm-cancel,.qm-note button{background:transparent;border-color:var(--cbm-border,#cbd5e0);color:inherit}" +
      ".qm-attach-btn{background:transparent;border:1px solid var(--cbm-border,#cbd5e0);border-radius:6px;" +
      "font:inherit;padding:5px 12px;cursor:pointer}" +
      // Searchable template dropdown.
      ".qm-combo{position:relative}" +
      ".qm-combo ul{position:absolute;left:0;right:0;top:calc(100% + 2px);z-index:40;max-height:14rem;" +
      "overflow:auto;background:var(--cbm-surface,#fff);border:1px solid var(--cbm-border,#cbd5e0);" +
      "border-radius:6px;box-shadow:0 8px 24px rgba(15,23,42,.18);margin:0;padding:4px 0;list-style:none}" +
      ".qm-combo li{padding:6px 10px;cursor:pointer}" +
      ".qm-combo li:hover,.qm-combo li.is-active{background:#eef4fb}" +
      ".qm-combo li.is-muted{color:var(--cbm-muted,#4a5568);font-style:italic}";
    var el = document.createElement("style");
    el.id = "qm-styles"; el.textContent = css;
    document.head.appendChild(el);
  }

  var activeGuard = null;   // {dirty(), discard()} for the open dialog
  var activeKeydown = null;

  function closeDialog() {
    var ov = document.getElementById("qmOverlay");
    if (ov) ov.remove();
    if (activeKeydown) { document.removeEventListener("keydown", activeKeydown); activeKeydown = null; }
    activeGuard = null;
  }

  // opts (optional): { template: "Name" } pre-selects + applies that EspoCRM
  // template once the list loads. Silent best-effort: an unknown name or a
  // failed parse just leaves the blank compose (no error note).
  function openDialog(toAddress, opts) {
    opts = opts || {};
    injectStyles();
    closeDialog();
    var ov = document.createElement("div"); ov.className = "qm-overlay"; ov.id = "qmOverlay";
    ov.addEventListener("mousedown", function (e) { if (e.target === ov) requestClose(); });
    var box = document.createElement("div"); box.className = "qm-box";
    box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "New email");

    var head = document.createElement("div"); head.className = "qm-head";
    var h = document.createElement("h2"); h.textContent = "New email"; head.appendChild(h);
    box.appendChild(head);
    var body = document.createElement("div"); body.className = "qm-body";
    box.appendChild(body);

    var from = document.createElement("p"); from.className = "qm-from";
    from.innerHTML = "From <strong></strong>";
    from.querySelector("strong").textContent = state.mailbox || "…";
    body.appendChild(from);

    function field(labelText, id, value, multiline, placeholder) {
      var row = document.createElement("div"); row.className = "qm-row";
      var lab = document.createElement("label"); lab.textContent = labelText; lab.htmlFor = id;
      row.appendChild(lab);
      var input;
      if (multiline && window.CBMRichText) {
        input = window.CBMRichText.create(value || "", {
          minHeight: Math.max(220, Math.floor(window.innerHeight * 0.3)),
          onInput: markEdited,
        });
      }
      if (!input) {
        input = document.createElement(multiline ? "textarea" : "input");
        input.id = id; if (!multiline) input.type = "text";
        input.value = value || "";
        input.addEventListener("input", markEdited);
      }
      if (placeholder && input.tagName) input.placeholder = placeholder;
      row.appendChild(input);
      body.appendChild(row);
      return { row: row, input: input, lab: lab };
    }
    var addrPlaceholder = "name@example.com, another@example.com";
    var toField = field("To", "qmTo", toAddress, false, addrPlaceholder);
    var toInput = toField.input;
    // Cc/Bcc reveal from the To label line (Gmail-style).
    var labLine = document.createElement("div"); labLine.className = "qm-lab-line";
    toField.row.insertBefore(labLine, toField.lab);
    labLine.appendChild(toField.lab);
    var links = document.createElement("span"); links.className = "qm-links";
    var ccLink = document.createElement("button"); ccLink.type = "button";
    ccLink.className = "qm-link-btn"; ccLink.textContent = "Cc";
    var bccLink = document.createElement("button"); bccLink.type = "button";
    bccLink.className = "qm-link-btn"; bccLink.textContent = "Bcc";
    links.appendChild(ccLink); links.appendChild(bccLink);
    labLine.appendChild(links);
    var ccField = field("Cc", "qmCc", "", false, addrPlaceholder);
    var bccField = field("Bcc", "qmBcc", "", false, addrPlaceholder);
    ccField.row.hidden = true; bccField.row.hidden = true;
    ccLink.addEventListener("click", function () {
      ccField.row.hidden = false; ccLink.hidden = true; ccField.input.focus();
    });
    bccLink.addEventListener("click", function () {
      bccField.row.hidden = false; bccLink.hidden = true; bccField.input.focus();
    });

    // --- Template picker (ET): searchable; EspoCRM renders, the draft stays
    // editable; "No template" restores the pre-template draft.
    var tplRow = document.createElement("div"); tplRow.className = "qm-row"; tplRow.hidden = true;
    var tplLab = document.createElement("label"); tplLab.textContent = "Template";
    var combo = document.createElement("div"); combo.className = "qm-combo";
    var tplInput = document.createElement("input"); tplInput.type = "text";
    tplInput.placeholder = "Search templates…";
    var tplList = document.createElement("ul"); tplList.hidden = true;
    combo.appendChild(tplInput); combo.appendChild(tplList);
    var tplNote = document.createElement("p"); tplNote.className = "qm-note"; tplNote.hidden = true;
    tplRow.appendChild(tplLab); tplRow.appendChild(combo); tplRow.appendChild(tplNote);
    body.appendChild(tplRow);

    var subjField = field("Subject", "qmSubject", "", false);
    var subjInput = subjField.input;
    var bodyField = field("Message", "qmBody", "", true);
    var bodyInput = bodyField.input;

    function bodyValue() {
      return bodyInput._cbmRichText ? bodyInput._cbmRichText.getValue() : bodyInput.value;
    }
    function setBody(html) {
      if (bodyInput._cbmRichText) bodyInput._cbmRichText.setValue(html);
      else bodyInput.value = html.replace(/<br\s*\/?>/gi, "\n")
        .replace(/<\/p\s*>/gi, "\n\n").replace(/<[^>]+>/g, "");
    }
    // Signature: seeded into the empty body on open; a body still equal to
    // the seed counts as empty (template picks don't nag, Send still insists
    // on a real message).
    var sigSeed = "";
    function seedSignature() {
      if (!state.signature) return;
      if (String(bodyValue() || "").replace(/<[^>]*>/g, "").trim()) return;
      setBody("<p><br></p><p><br></p>" + state.signature);
      sigSeed = String(bodyValue() || "");
    }
    seedSignature();
    probeMailbox().then(function () {
      from.querySelector("strong").textContent = state.mailbox || "…";
      seedSignature();
    });
    function bodyIsEmpty() {
      var raw = String(bodyValue() || "");
      var stripped = raw.replace(/<[^>]*>/g, "").trim();
      return !stripped || (sigSeed && raw === sigSeed);
    }
    function draftHasContent() {
      return !!(subjInput.value.trim() || !bodyIsEmpty() || localAttachments.length);
    }

    // --- template combobox behavior ---
    var tplAll = [], tplVisible = [], tplActive = -1, preTplSnapshot = null;
    function tplClose() { tplList.hidden = true; tplActive = -1; }
    function tplRender(filter) {
      tplList.innerHTML = ""; tplVisible = []; tplActive = -1;
      tplVisible.push({ id: null, name: "No template", muted: true });
      tplAll.forEach(function (t) {
        if (filter && String(t.name || "").toLowerCase().indexOf(filter.toLowerCase()) === -1) return;
        tplVisible.push(t);
      });
      tplVisible.forEach(function (t, i) {
        var li = document.createElement("li");
        li.textContent = t.name; if (t.muted) li.className = "is-muted";
        li.addEventListener("mousedown", function (e) { e.preventDefault(); tplPick(i); });
        tplList.appendChild(li);
      });
      tplList.hidden = !tplVisible.length;
    }
    function tplHighlight() {
      Array.prototype.forEach.call(tplList.children, function (li, i) {
        li.className = (tplVisible[i] && tplVisible[i].muted ? "is-muted" : "") + (i === tplActive ? " is-active" : "");
        if (i === tplActive) li.scrollIntoView({ block: "nearest" });
      });
    }
    var tplConfirmEl = null;
    function tplPick(i) {
      var t = tplVisible[i];
      if (!t) return;
      tplInput.value = t.id === null ? "" : t.name;
      tplClose();
      if (tplConfirmEl) { tplConfirmEl.remove(); tplConfirmEl = null; }
      if (t.id === null) {
        if (preTplSnapshot) {
          subjInput.value = preTplSnapshot.subject;
          setBody(preTplSnapshot.body);
          templateAttachments = preTplSnapshot.tplAttach.slice();
          renderChips();
          preTplSnapshot = null; tplNote.hidden = true;
          markEdited();
        }
        return;
      }
      if (!draftHasContent()) { applyTemplate(t.id); return; }
      // ET-113/ET-B1: never silently overwrite an edited draft.
      tplConfirmEl = document.createElement("p"); tplConfirmEl.className = "qm-note qm-warn";
      tplConfirmEl.appendChild(document.createTextNode("Replace current content?"));
      var yes = document.createElement("button"); yes.type = "button"; yes.textContent = "Replace";
      var no = document.createElement("button"); no.type = "button"; no.textContent = "Keep my draft";
      yes.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; applyTemplate(t.id);
      });
      no.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; tplInput.value = "";
      });
      tplConfirmEl.appendChild(yes); tplConfirmEl.appendChild(no);
      tplRow.appendChild(tplConfirmEl);
    }
    tplInput.addEventListener("input", function () { tplRender(tplInput.value); });
    tplInput.addEventListener("focus", function () { tplRender(tplInput.value); });
    tplInput.addEventListener("blur", function () { setTimeout(tplClose, 150); });
    tplInput.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { if (tplList.hidden) tplRender(tplInput.value); tplActive = Math.min(tplActive + 1, tplVisible.length - 1); tplHighlight(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { tplActive = Math.max(tplActive - 1, 0); tplHighlight(); e.preventDefault(); }
      else if (e.key === "Enter") { if (!tplList.hidden && tplActive >= 0) { tplPick(tplActive); e.preventDefault(); } }
      else if (e.key === "Escape" && !tplList.hidden) { tplClose(); e.stopPropagation(); }
    });
    fetch(state.apiBase + "/emailtemplates", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { templates: [] }; })
      .then(function (d) {
        tplAll = d.templates || [];
        if (tplAll.length) tplRow.hidden = false;
        if (opts.template && !restoredDraft) {
          var want = String(opts.template).trim().toLowerCase();
          var match = tplAll.filter(function (t) {
            return String(t.name || "").trim().toLowerCase() === want;
          })[0];
          // The draft is untouched at this point (signature seed counts as
          // empty), so apply directly — no replace-prompt needed. A RESTORED
          // draft is real content — never auto-overwrite it.
          if (match) { tplInput.value = match.name; applyTemplate(match.id, true); }
        }
      })
      .catch(function () { /* no picker — compose works without it */ });

    function applyTemplate(id, silent) {
      tplNote.hidden = true;
      preTplSnapshot = {
        subject: subjInput.value,
        body: String(bodyValue() || ""),
        tplAttach: templateAttachments.slice(),
      };
      var firstTo = parseAddrList(toInput.value).emails[0] || "";
      post("/emailtemplates/" + encodeURIComponent(id) + "/parse", { emailAddress: firstTo })
        .then(function (r) {
          subjInput.value = r.subject || "";
          // Rendered draft + the signature re-appended below it (EspoCRM's
          // own behavior) — templates shouldn't carry their own sign-off.
          setBody((r.bodyHtml || "") +
            (state.signature ? "<p><br></p>" + state.signature : ""));
          templateAttachments = (r.attachments || []).slice();
          renderChips();
          if ((r.leftoverTokens || []).length) {
            tplNote.textContent = "Some placeholders couldn't be filled: " +
              r.leftoverTokens.join(", ") + " — review the draft before sending.";
            tplNote.className = "qm-note qm-warn";
            tplNote.hidden = false;
          }
          markEdited();
        })
        .catch(function (e) {
          // ET-114: non-destructive — the existing draft stays untouched.
          // A silent (auto-applied) template failure just leaves the blank
          // compose; a user-picked one explains itself.
          preTplSnapshot = null;
          if (!silent) {
            tplNote.textContent = e.message || "Couldn't apply the template.";
            tplNote.className = "qm-note";
            tplNote.hidden = false;
          }
          tplInput.value = "";
        });
    }

    // --- Attachments: template chips + the user's own files, with sizes.
    var templateAttachments = [];  // {id, name}
    var localAttachments = [];     // {filename, contentType, dataBase64, size}
    var attachRow = document.createElement("div"); attachRow.className = "qm-row";
    var attachLab = document.createElement("span"); attachLab.className = "qm-lab"; attachLab.textContent = "Attachments";
    var chipsEl = document.createElement("div"); chipsEl.className = "qm-chips";
    var totalEl = document.createElement("p"); totalEl.className = "qm-attach-total"; totalEl.hidden = true;
    var fileBtn = document.createElement("button"); fileBtn.type = "button";
    fileBtn.className = "qm-attach-btn"; fileBtn.textContent = "Attach files…";
    var fileInput = document.createElement("input"); fileInput.type = "file";
    fileInput.multiple = true; fileInput.hidden = true;
    fileBtn.addEventListener("click", function () { fileInput.click(); });
    attachRow.appendChild(attachLab); attachRow.appendChild(chipsEl);
    attachRow.appendChild(totalEl);
    attachRow.appendChild(fileBtn); attachRow.appendChild(fileInput);
    body.appendChild(attachRow);

    function attachTotal() {
      return localAttachments.reduce(function (n, f) { return n + (f.size || 0); }, 0);
    }
    function renderChips() {
      chipsEl.innerHTML = "";
      function chip(name, size, onRemove) {
        var c = document.createElement("span"); c.className = "qm-chip";
        c.appendChild(document.createTextNode(name));
        if (size) {
          var s = document.createElement("span"); s.className = "qm-size";
          s.textContent = " (" + fmtBytes(size) + ")";
          c.appendChild(s);
        }
        var x = document.createElement("button"); x.type = "button";
        x.textContent = "✕"; x.title = "Remove attachment";
        x.addEventListener("click", onRemove);
        c.appendChild(x); chipsEl.appendChild(c);
      }
      templateAttachments.forEach(function (a, i) {
        chip(a.name || "attachment", a.size || 0, function () { templateAttachments.splice(i, 1); renderChips(); markEdited(); });
      });
      localAttachments.forEach(function (f, i) {
        chip(f.filename, f.size || 0, function () { localAttachments.splice(i, 1); renderChips(); markEdited(); });
      });
      totalEl.hidden = !localAttachments.length;
      totalEl.textContent = "Total " + fmtBytes(attachTotal()) + " of 20 MB";
    }
    fileInput.addEventListener("change", function () {
      Array.prototype.forEach.call(fileInput.files || [], function (file) {
        if (attachTotal() + file.size > MAX_ATTACH_TOTAL) {
          footErr("“" + file.name + "” would push the attachments over 20 MB — remove something first.");
          return;
        }
        var reader = new FileReader();
        reader.onload = function () {
          localAttachments.push({
            filename: file.name,
            contentType: file.type || "application/octet-stream",
            dataBase64: String(reader.result || "").split(",")[1] || "",
            size: file.size,
          });
          renderChips();
          markEdited();
        };
        reader.readAsDataURL(file);
      });
      fileInput.value = "";
    });

    // --- footer: status slot + Cancel + Send (Send rightmost).
    var foot = document.createElement("div"); foot.className = "qm-foot";
    var slot = document.createElement("div"); slot.className = "qm-slot";
    var err = document.createElement("p"); err.className = "qm-err"; err.hidden = true;
    var warn = document.createElement("p"); warn.className = "qm-warn-msg"; warn.hidden = true;
    slot.appendChild(err); slot.appendChild(warn);
    var cancel = document.createElement("button"); cancel.type = "button";
    cancel.className = "qm-cancel"; cancel.textContent = "Cancel";
    cancel.addEventListener("click", requestClose);
    var send = document.createElement("button"); send.type = "button";
    send.className = "qm-send"; send.textContent = "Send";
    foot.appendChild(slot); foot.appendChild(cancel); foot.appendChild(send);
    box.appendChild(foot);
    function footErr(text) { err.textContent = text; err.hidden = false; warn.hidden = true; }
    function footWarn(text) { warn.textContent = text; warn.hidden = false; err.hidden = true; }
    function clearFootMsg() { err.hidden = true; warn.hidden = true; }

    // --- draft persistence + edit tracking ---
    var sendArmed = false, draftTimer = null;
    function disarmSend() {
      if (sendArmed) { sendArmed = false; send.textContent = "Send"; }
    }
    function draftState() {
      return {
        ts: Date.now(),
        to: toInput.value,
        cc: ccField.input.value, bcc: bccField.input.value,
        ccShown: !ccField.row.hidden, bccShown: !bccField.row.hidden,
        subject: subjInput.value,
        body: String(bodyValue() || ""),
        tplAttach: templateAttachments,
      };
    }
    function markEdited() {
      disarmSend(); clearFootMsg();
      if (draftTimer) clearTimeout(draftTimer);
      draftTimer = setTimeout(function () {
        draftTimer = null;
        if (draftHasContent()) storeDraft(toAddress, draftState());
        else clearDraft(toAddress);
      }, 800);
    }
    var savedDraft = loadDraft(toAddress);
    var restoredDraft = !!(savedDraft && (savedDraft.subject || savedDraft.body));
    if (restoredDraft) {
      toInput.value = savedDraft.to || toInput.value;
      if (savedDraft.ccShown || savedDraft.cc) { ccField.row.hidden = false; ccLink.hidden = true; ccField.input.value = savedDraft.cc || ""; }
      if (savedDraft.bccShown || savedDraft.bcc) { bccField.row.hidden = false; bccLink.hidden = true; bccField.input.value = savedDraft.bcc || ""; }
      subjInput.value = savedDraft.subject || "";
      if (savedDraft.body) setBody(savedDraft.body);
      templateAttachments = (savedDraft.tplAttach || []).slice();
      renderChips();
      var note = document.createElement("p"); note.className = "qm-note";
      note.appendChild(document.createTextNode("Restored your unsent draft."));
      var fresh = document.createElement("button"); fresh.type = "button"; fresh.textContent = "Start fresh";
      fresh.addEventListener("click", function () {
        clearDraft(toAddress);
        note.remove();
        toInput.value = toAddress || "";
        ccField.input.value = ""; bccField.input.value = "";
        subjInput.value = ""; setBody(""); sigSeed = "";
        seedSignature();
        templateAttachments = []; localAttachments = [];
        renderChips(); clearFootMsg();
      });
      note.appendChild(fresh);
      body.insertBefore(note, body.firstChild);
    }
    activeGuard = {
      dirty: draftHasContent,
      discard: function () {
        if (draftTimer) { clearTimeout(draftTimer); draftTimer = null; }
        clearDraft(toAddress);
      },
    };

    // Sent-but-not-recorded: swap the dialog to a retry screen (ET-142).
    function showWriteBackRetry(writeBack) {
      activeGuard = null;
      body.innerHTML = "";
      var note = document.createElement("p"); note.className = "qm-err";
      note.textContent = writeBack.error ||
        "The message WAS sent, but recording it in the CRM failed.";
      note.hidden = false;
      body.appendChild(note);
      foot.innerHTML = "";
      var retry = document.createElement("button"); retry.type = "button";
      retry.className = "qm-send"; retry.textContent = "Retry recording";
      var close = document.createElement("button"); close.type = "button";
      close.className = "qm-cancel"; close.textContent = "Close";
      retry.addEventListener("click", function () {
        retry.disabled = true; retry.textContent = "Recording…";
        post("/emailwriteback", writeBack.retryPayload || {})
          .then(function () { closeDialog(); })
          .catch(function (e) {
            note.textContent = (e.message || "Still couldn't record it.") + " Try again?";
            retry.disabled = false; retry.textContent = "Retry recording";
          });
      });
      close.addEventListener("click", closeDialog);
      foot.appendChild(retry); foot.appendChild(close);
    }

    function doSend() {
      clearFootMsg();
      var toParsed = parseAddrList(toInput.value);
      var ccParsed = ccField.row.hidden ? { emails: [], invalid: [] } : parseAddrList(ccField.input.value);
      var bccParsed = bccField.row.hidden ? { emails: [], invalid: [] } : parseAddrList(bccField.input.value);
      var invalid = toParsed.invalid.concat(ccParsed.invalid, bccParsed.invalid);
      if (invalid.length) {
        footErr("These don't look like email addresses: " + invalid.join(", ") +
          " — fix or remove them. Separate addresses with commas.");
        return;
      }
      if (!toParsed.emails.length && !ccParsed.emails.length && !bccParsed.emails.length) {
        footErr("Add at least one recipient."); toInput.focus(); return;
      }
      if (bodyIsEmpty()) {  // an untouched seeded signature isn't a message
        footErr("Write a message first.");
        if (bodyInput._cbmRichText) bodyInput._cbmRichText.focus(); else bodyInput.focus();
        return;
      }
      // "Send anyway" gate: missing subject / unresolved placeholders get one
      // explicit look before the email goes out.
      var holdups = [];
      if (!subjInput.value.trim()) holdups.push("it has no subject");
      var leftover = (subjInput.value + " " + String(bodyValue() || ""))
        .match(/\{[A-Za-z][A-Za-z0-9]*\.[A-Za-z0-9_]+\}/g);
      if (leftover) holdups.push("it still contains unfilled placeholders (" + leftover.slice(0, 3).join(", ") + ")");
      if (holdups.length && !sendArmed) {
        sendArmed = true;
        footWarn("Before this goes out: " + holdups.join(", and ") + ". Click “Send anyway” to send it as is.");
        send.textContent = "Send anyway";
        return;
      }
      send.disabled = true; send.textContent = "Sending…";
      var attachments = templateAttachments.map(function (a) {
        return { espoId: a.id, filename: a.name };
      }).concat(localAttachments.map(function (f) {
        return { filename: f.filename, contentType: f.contentType, dataBase64: f.dataBase64 };
      }));
      var payload = {
        to: toParsed.emails, cc: ccParsed.emails, bcc: bccParsed.emails,
        subject: subjInput.value.trim(), body: bodyValue(), attachments: attachments,
      };
      var showProgress = JSON.stringify(payload).length > 300 * 1024;
      postProgress("/sendmail", payload,
        showProgress ? function (pct) { send.textContent = "Sending… " + pct + "%"; } : null)
        .then(function (d) {
          clearDraft(toAddress);
          activeGuard = null;
          if (d && d.writeBack && d.writeBack.ok === false) { showWriteBackRetry(d.writeBack); return; }
          var ok = document.createElement("p"); ok.className = "qm-ok"; ok.textContent = "Sent.";
          slot.appendChild(ok);
          setTimeout(closeDialog, 900);
        })
        .catch(function (e) {
          footErr(e.message || "Couldn't send the message — try again.");
          send.disabled = false; send.textContent = "Send";
          sendArmed = false;
        });
    }
    send.addEventListener("click", doSend);

    function requestClose() {
      if (!activeGuard || !activeGuard.dirty()) { closeDialog(); return; }
      // Styled two-step confirm inside the dialog (no browser confirm).
      if (foot.querySelector(".qm-discard-note")) return;
      var note = document.createElement("span"); note.className = "qm-discard-note qm-warn-msg";
      note.textContent = "Discard this draft? It stays saved unless you discard it. ";
      var discard = document.createElement("button"); discard.type = "button";
      discard.className = "qm-cancel"; discard.textContent = "Discard draft";
      var keep = document.createElement("button"); keep.type = "button";
      keep.className = "qm-cancel"; keep.textContent = "Keep writing";
      discard.addEventListener("click", function () {
        if (activeGuard) activeGuard.discard();
        closeDialog();
      });
      keep.addEventListener("click", function () { note.remove(); });
      note.appendChild(discard); note.appendChild(keep);
      slot.innerHTML = ""; slot.appendChild(err); slot.appendChild(warn); slot.appendChild(note);
    }

    activeKeydown = function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); doSend(); return; }
      if (e.key === "Escape") { requestClose(); return; }
      // Minimal focus trap: keep Tab inside the dialog.
      if (e.key === "Tab") {
        var focusables = box.querySelectorAll(
          "button, [href], input, select, textarea, [contenteditable=true], [tabindex]:not([tabindex='-1'])"
        );
        var list = Array.prototype.filter.call(focusables, function (el) {
          return !el.hidden && el.offsetParent !== null && !el.disabled;
        });
        if (!list.length) return;
        var first = list[0], last = list[list.length - 1];
        if (e.shiftKey && (document.activeElement === first || !box.contains(document.activeElement))) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        } else if (!box.contains(document.activeElement)) {
          e.preventDefault(); first.focus();
        }
      }
    };

    ov.appendChild(box);
    document.body.appendChild(ov);
    document.addEventListener("keydown", activeKeydown);
    // Focus the first thing still missing: recipients, then subject, then body.
    if (!parseAddrList(toInput.value).emails.length) toInput.focus();
    else if (!subjInput.value.trim()) subjInput.focus();
    else if (bodyInput._cbmRichText) bodyInput._cbmRichText.focus();
    else bodyInput.focus();
  }

  function handleClick(e, email) {
    if (state.enabled === false) return; // fall through to mailto:
    e.preventDefault();
    if (state.enabled === true) { openDialog(email); return; }
    // First click: find out whether app-sending works, then act accordingly.
    probeMailbox().then(function () {
      if (state.enabled) openDialog(email);
      else window.location.href = "mailto:" + email;
    });
  }

  window.CBMQuickMail = {
    get apiBase() { return state.apiBase; },
    set apiBase(v) { state.apiBase = v; },
    // Programmatic open (e.g. after an action, not an address click): compose
    // only when app-sending actually works — silently a no-op otherwise (no
    // surprise mailto: launch the user didn't click for).
    composeIfEnabled: function (email, opts) {
      probeMailbox().then(function () {
        if (state.enabled) openDialog(email, opts);
      });
    },
    // <a> for an email address: compose-on-click, mailto: fallback.
    emailLink: function (email) {
      if (!email) return document.createTextNode("—");
      var a = document.createElement("a");
      a.className = "email-link qm-link";
      a.href = "mailto:" + email;
      a.textContent = email;
      a.title = "Send email";
      a.addEventListener("click", function (e) { handleClick(e, email); });
      return a;
    },
    compose: openDialog,
  };
})();
