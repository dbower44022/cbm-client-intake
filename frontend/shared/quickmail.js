/* Quick-email compose — the product-wide replacement for bare mailto: links
 * (Doug's ruling 2026-07-16: an email address shown anywhere in the staff
 * UIs opens the app's own compose dialog).
 *
 * Usage: include this script, then render addresses with
 *   CBMQuickMail.emailLink("person@example.com")
 * The returned <a> keeps a real mailto: href (middle-click / copy-link still
 * behave), but a plain click opens a small compose modal that sends as the
 * signed-in user's own CBM mailbox via the app (`GET  <app>/api/mailbox`,
 * `POST <app>/api/sendmail` — see comms/quicksend.py). When sending isn't
 * available (Gmail integration off, or no CBM mailbox on the user's profile)
 * the click falls back to the browser's mailto: handler.
 *
 * Email templates (ET): the dialog offers the EspoCRM templates the signed-in
 * user may see (`GET <app>/api/emailtemplates`); selecting one loads the
 * server-rendered draft (`POST <app>/api/emailtemplates/{id}/parse`, the To
 * address resolves {Person.*}). The body is the standard CBMRichText editor
 * when its script is on the page (all staff pages load it), else a plain
 * textarea. Attachments: template chips (bytes fetched by the server at send
 * time) + local file uploads. A failed CRM write-back after a confirmed send
 * offers a retry (`POST <app>/api/emailwriteback`) — never silent.
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

  function injectStyles() {
    if (document.getElementById("qm-styles")) return;
    var css = "" +
      ".qm-overlay{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;" +
      "align-items:flex-start;justify-content:center;padding:6vh 16px;z-index:1000}" +
      ".qm-box{background:var(--cbm-surface,#fff);color:var(--cbm-text,#1a202c);border-radius:10px;" +
      "box-shadow:0 18px 50px rgba(0,0,0,.28);width:min(760px,100%);padding:20px 22px;" +
      "max-height:88vh;overflow-y:auto;" +
      "font-family:var(--cbm-font-body,system-ui,sans-serif)}" +
      ".qm-box h2{margin:0 0 12px;font-size:1.15rem}" +
      ".qm-row{margin:0 0 10px}" +
      ".qm-row label{display:block;font-size:.8rem;font-weight:600;margin-bottom:3px;color:var(--cbm-muted,#4a5568)}" +
      ".qm-row input,.qm-row textarea,.qm-row select{width:100%;box-sizing:border-box;padding:7px 9px;" +
      "border:1px solid var(--cbm-border,#cbd5e0);border-radius:6px;font:inherit}" +
      ".qm-row textarea{min-height:9em;resize:vertical}" +
      ".qm-tpl-line{display:flex;gap:8px}" +
      ".qm-tpl-line select{flex:1 1 60%}.qm-tpl-line input{flex:1 1 40%}" +
      ".qm-from{font-size:.85rem;color:var(--cbm-muted,#4a5568);margin:0 0 10px}" +
      ".qm-from strong{color:inherit}" +
      ".qm-note{font-size:.85rem;background:#f7f9fb;border:1px solid var(--cbm-border,#cbd5e0);" +
      "border-radius:6px;padding:6px 9px;margin:6px 0 0}" +
      ".qm-note button{margin-left:6px}" +
      ".qm-chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 6px}" +
      ".qm-chips:empty{display:none}" +
      ".qm-chip{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;font-size:.85rem;" +
      "border:1px solid var(--cbm-border,#cbd5e0);border-radius:999px;background:#f7f9fb}" +
      ".qm-chip button{border:0;background:none;cursor:pointer;color:var(--cbm-muted,#4a5568);padding:0}" +
      ".qm-chip button:hover{color:var(--cbm-danger,#c53030)}" +
      ".qm-err{color:var(--cbm-danger,#c53030);font-size:.85rem;margin:6px 0 0}" +
      ".qm-ok{color:#2f855a;font-size:.9rem;margin:6px 0 0}" +
      ".qm-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}" +
      ".qm-actions button,.qm-note button{font:inherit;padding:7px 16px;border-radius:6px;cursor:pointer;border:1px solid transparent}" +
      ".qm-send{background:var(--cbm-btn-bg,var(--cbm-blue,#2b6cb0));color:var(--cbm-btn-color,#fff)}" +
      ".qm-send[disabled]{opacity:.6;cursor:default}" +
      ".qm-cancel,.qm-note button{background:transparent;border-color:var(--cbm-border,#cbd5e0);color:inherit}" +
      ".qm-attach-btn{background:transparent;border:1px solid var(--cbm-border,#cbd5e0);border-radius:6px;" +
      "font:inherit;padding:5px 12px;cursor:pointer}";
    var el = document.createElement("style");
    el.id = "qm-styles"; el.textContent = css;
    document.head.appendChild(el);
  }

  function closeDialog() {
    var ov = document.getElementById("qmOverlay");
    if (ov) ov.remove();
    document.removeEventListener("keydown", onEsc);
  }
  function onEsc(e) { if (e.key === "Escape") closeDialog(); }

  // opts (optional): { template: "Name" } pre-selects + applies that EspoCRM
  // template once the list loads. Silent best-effort: an unknown name or a
  // failed parse just leaves the blank compose (no error note).
  function openDialog(toAddress, opts) {
    opts = opts || {};
    injectStyles();
    closeDialog();
    var ov = document.createElement("div"); ov.className = "qm-overlay"; ov.id = "qmOverlay";
    ov.addEventListener("mousedown", function (e) { if (e.target === ov) closeDialog(); });
    var box = document.createElement("div"); box.className = "qm-box";
    box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "New email");

    var h = document.createElement("h2"); h.textContent = "New email"; box.appendChild(h);

    var from = document.createElement("p"); from.className = "qm-from";
    from.innerHTML = "From <strong></strong>";
    from.querySelector("strong").textContent = state.mailbox || "…";
    box.appendChild(from);

    function field(labelText, id, value, multiline) {
      var row = document.createElement("div"); row.className = "qm-row";
      var lab = document.createElement("label"); lab.textContent = labelText; lab.htmlFor = id;
      row.appendChild(lab);
      var input;
      if (multiline && window.CBMRichText) {
        input = window.CBMRichText.create(value || "", { minHeight: 180 });
      }
      if (!input) {
        input = document.createElement(multiline ? "textarea" : "input");
        input.id = id; if (!multiline) input.type = "text";
        input.value = value || "";
      }
      row.appendChild(input);
      box.appendChild(row);
      return input;
    }
    var toInput = field("To", "qmTo", toAddress, false);

    // --- Template picker (ET): EspoCRM renders, the draft stays editable.
    var tplRow = document.createElement("div"); tplRow.className = "qm-row"; tplRow.hidden = true;
    var tplLab = document.createElement("label"); tplLab.textContent = "Template";
    var tplLine = document.createElement("div"); tplLine.className = "qm-tpl-line";
    var tplSel = document.createElement("select");
    var tplFilter = document.createElement("input"); tplFilter.type = "text";
    tplFilter.placeholder = "Type to filter templates…";
    tplLine.appendChild(tplSel); tplLine.appendChild(tplFilter);
    var tplNote = document.createElement("p"); tplNote.className = "qm-note"; tplNote.hidden = true;
    tplRow.appendChild(tplLab); tplRow.appendChild(tplLine); tplRow.appendChild(tplNote);
    box.appendChild(tplRow);

    var subjInput = field("Subject", "qmSubject", "", false);
    var bodyInput = field("Message", "qmBody", "", true);

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
      return !!(subjInput.value.trim() || !bodyIsEmpty());
    }

    var tplAll = [];
    function renderTplOptions(filter) {
      tplSel.innerHTML = "";
      tplSel.appendChild(new Option("No template", ""));
      tplAll.forEach(function (t) {
        if (filter && String(t.name || "").toLowerCase().indexOf(filter.toLowerCase()) === -1) return;
        tplSel.appendChild(new Option(t.name, t.id));
      });
    }
    fetch(state.apiBase + "/emailtemplates", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { templates: [] }; })
      .then(function (d) {
        tplAll = d.templates || [];
        if (tplAll.length) { renderTplOptions(""); tplRow.hidden = false; }
        if (opts.template) {
          var want = String(opts.template).trim().toLowerCase();
          var match = tplAll.filter(function (t) {
            return String(t.name || "").trim().toLowerCase() === want;
          })[0];
          // The draft is untouched at this point (signature seed counts as
          // empty), so apply directly — no replace-prompt needed.
          if (match) { tplSel.value = match.id; applyTemplate(match.id, true); }
        }
      })
      .catch(function () { /* no picker — compose works without it */ });
    tplFilter.addEventListener("input", function () { renderTplOptions(this.value); });

    var tplConfirmEl = null;
    tplSel.addEventListener("change", function () {
      var id = tplSel.value;
      if (tplConfirmEl) { tplConfirmEl.remove(); tplConfirmEl = null; }
      if (!id) return;
      if (!draftHasContent()) { applyTemplate(id); return; }
      // ET-113/ET-B1: never silently overwrite an edited draft.
      tplConfirmEl = document.createElement("p"); tplConfirmEl.className = "qm-note";
      tplConfirmEl.appendChild(document.createTextNode("Replace current content?"));
      var yes = document.createElement("button"); yes.type = "button"; yes.textContent = "Replace";
      var no = document.createElement("button"); no.type = "button"; no.textContent = "Keep my draft";
      yes.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; applyTemplate(id);
      });
      no.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; tplSel.value = "";
      });
      tplConfirmEl.appendChild(yes); tplConfirmEl.appendChild(no);
      tplRow.appendChild(tplConfirmEl);
    });

    function applyTemplate(id, silent) {
      tplNote.hidden = true; tplSel.disabled = true;
      var firstTo = toInput.value.split(/[,;\s]+/).filter(Boolean)[0] || "";
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
            tplNote.hidden = false;
          }
        })
        .catch(function (e) {
          // ET-114: non-destructive — the existing draft stays untouched.
          // A silent (auto-applied) template failure just leaves the blank
          // compose; a user-picked one explains itself.
          if (!silent) {
            tplNote.textContent = e.message || "Couldn't apply the template.";
            tplNote.hidden = false;
          }
          tplSel.value = "";
        })
        .then(function () { tplSel.disabled = false; });
    }

    // --- Attachments: template chips + the user's own files.
    var templateAttachments = [];  // {id, name}
    var localAttachments = [];     // {filename, contentType, dataBase64, size}
    var attachRow = document.createElement("div"); attachRow.className = "qm-row";
    var attachLab = document.createElement("label"); attachLab.textContent = "Attachments";
    var chipsEl = document.createElement("div"); chipsEl.className = "qm-chips";
    var fileBtn = document.createElement("button"); fileBtn.type = "button";
    fileBtn.className = "qm-attach-btn"; fileBtn.textContent = "Attach files…";
    var fileInput = document.createElement("input"); fileInput.type = "file";
    fileInput.multiple = true; fileInput.hidden = true;
    fileBtn.addEventListener("click", function () { fileInput.click(); });
    attachRow.appendChild(attachLab); attachRow.appendChild(chipsEl);
    attachRow.appendChild(fileBtn); attachRow.appendChild(fileInput);
    box.appendChild(attachRow);

    function renderChips() {
      chipsEl.innerHTML = "";
      function chip(name, onRemove) {
        var c = document.createElement("span"); c.className = "qm-chip";
        c.appendChild(document.createTextNode(name));
        var x = document.createElement("button"); x.type = "button";
        x.textContent = "✕"; x.title = "Remove attachment";
        x.addEventListener("click", onRemove);
        c.appendChild(x); chipsEl.appendChild(c);
      }
      templateAttachments.forEach(function (a, i) {
        chip(a.name || "attachment", function () { templateAttachments.splice(i, 1); renderChips(); });
      });
      localAttachments.forEach(function (f, i) {
        chip(f.filename, function () { localAttachments.splice(i, 1); renderChips(); });
      });
    }
    fileInput.addEventListener("change", function () {
      Array.prototype.forEach.call(fileInput.files || [], function (file) {
        var total = localAttachments.reduce(function (n, f) { return n + (f.size || 0); }, 0);
        if (total + file.size > MAX_ATTACH_TOTAL) {
          err.textContent = "Attachments are too large — keep the total under 20 MB per message.";
          err.hidden = false;
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
        };
        reader.readAsDataURL(file);
      });
      fileInput.value = "";
    });

    var err = document.createElement("p"); err.className = "qm-err"; err.hidden = true;
    box.appendChild(err);

    var actions = document.createElement("div"); actions.className = "qm-actions";
    var cancel = document.createElement("button"); cancel.type = "button";
    cancel.className = "qm-cancel"; cancel.textContent = "Cancel";
    cancel.addEventListener("click", closeDialog);
    var send = document.createElement("button"); send.type = "button";
    send.className = "qm-send"; send.textContent = "Send";
    actions.appendChild(cancel); actions.appendChild(send);
    box.appendChild(actions);

    // Sent-but-not-recorded: swap the dialog to a retry screen (ET-142).
    function showWriteBackRetry(writeBack) {
      box.innerHTML = "";
      var note = document.createElement("p"); note.className = "qm-err";
      note.textContent = writeBack.error ||
        "The message WAS sent, but recording it in the CRM failed.";
      note.hidden = false;
      box.appendChild(note);
      var acts = document.createElement("div"); acts.className = "qm-actions";
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
      acts.appendChild(retry); acts.appendChild(close);
      box.appendChild(acts);
    }

    send.addEventListener("click", function () {
      err.hidden = true;
      var to = toInput.value.split(/[,;\s]+/).filter(Boolean);
      if (!to.length) { err.textContent = "Add at least one recipient."; err.hidden = false; return; }
      var body = bodyValue();
      if (bodyIsEmpty()) {  // an untouched seeded signature isn't a message
        err.textContent = "Write a message first."; err.hidden = false; return;
      }
      send.disabled = true; send.textContent = "Sending…";
      var attachments = templateAttachments.map(function (a) {
        return { espoId: a.id, filename: a.name };
      }).concat(localAttachments.map(function (f) {
        return { filename: f.filename, contentType: f.contentType, dataBase64: f.dataBase64 };
      }));
      post("/sendmail", { to: to, subject: subjInput.value.trim(), body: body, attachments: attachments })
        .then(function (d) {
          if (d && d.writeBack && d.writeBack.ok === false) { showWriteBackRetry(d.writeBack); return; }
          var ok = document.createElement("p"); ok.className = "qm-ok"; ok.textContent = "Sent.";
          box.insertBefore(ok, actions);
          setTimeout(closeDialog, 900);
        })
        .catch(function (e) {
          err.textContent = e.message || "Couldn't send the message — try again.";
          err.hidden = false;
          send.disabled = false; send.textContent = "Send";
        });
    });

    ov.appendChild(box);
    document.body.appendChild(ov);
    document.addEventListener("keydown", onEsc);
    (subjInput).focus();
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
