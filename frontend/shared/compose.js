/* Shared email composer — window.CBMCompose.

   The full compose dialog the session tools' Communications tab has carried
   since the email arc (From, To with the record's address book, Cc/Bcc,
   Subject, the rich-text body with the signature, templates rendered by the
   CRM, attachments from disk / the record's Documents / a forwarded original,
   drafts that survive an accidental close, reply / reply-all / forward, the
   send, and the write-back retry screen), lifted out of
   sessions/frontend/app.js so that more than one page can serve it. Doug's
   ruling 10-25-26: the lead's page in Marketing Management gets this same
   composer, not a smaller one; one component, two hosts.

   Usage:
     var guard = CBMCompose.open(host, pre);

   ``host`` says where the dialog lives and what it may do:
     api(path, {method, body})      JSON request; ``body`` is an OBJECT; a
                                    failure rejects with .status and .message
     apiBase                        the API prefix, for the upload-progress POST
     endpoints                      mailbox, templates, parse(templateId),
                                    messages, forwardAttachments(communicationId),
                                    documents, contactLookup(email), companies,
                                    addContact, addComentor, writeBack
     features                       {cc, templates, attachments, documents,
                                    drafts, reply, addressBook}
     record                         {entity, id, name, contacts:[{name,email}],
                                    supportsComentor, fixedRecipient}
     sendingEnabled                 false => the Send button explains that
                                    email is not switched on here
     mailbox                        {get() -> {mailbox, signature}|undefined,
                                    set(mailbox, signature)} — the page's cache
     modal                          {open(kind,title), close(), body(), foot(),
                                    setTitle(t)} — the page's own dialog shell;
                                    omitted => the component builds one
     requestClose()                 the page's own close-with-discard-confirm;
                                    omitted => the component's inline confirm
     isInternal(address)            true for the chapter's own addresses
     fmtWhen(value)                 a date-time for the quoted header
     draftKey(replyKey)             the localStorage key; omitted => a default
     onSent(result)                 after a successful send and close
     onUnauthorized()               a 401: the page sends the person to sign in
     notice(text, kind)             the page's notice line ("success"/"error")

   ``pre`` is what the dialog opens with: {to, subject, replyToId, quote,
   forward, forwardCommunicationId, backToConv}.

   The returned ``guard`` is {dirty(), discard(), send(), backConvId}: the host
   wires Escape, the × and the backdrop to its requestClose, and Ctrl+Enter to
   guard.send. After the message is sent (or the retry screen shows) the guard
   reports clean and send is null.

   Every action button stays visible; a missing input is named on click. */
(function () {
  "use strict";

  var MAX_ATTACH_TOTAL = 20 * 1024 * 1024;  // matches the server cap

  function $(id) { return document.getElementById(id); }

  // "Name <email>" -> "email"; a bare address passes through.
  function extractEmail(addr) {
    var m = /<([^>]+)>/.exec(addr || "");
    return (m ? m[1] : String(addr || "")).trim();
  }

  // "a@b.c, Jane Doe <jane@x.org>; bob@y.io" -> {emails: [...], invalid: [...]}.
  // Splits on commas/semicolons/newlines (NOT bare spaces — display names
  // contain them); accepts Name <email>; validates the address shape.
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

  // Searchable dropdown (template picker, company picker): one input, a
  // filtered list below it. opts: {placeholder, options: [{id,label,muted}],
  // emptyLabel, onSelect(id|null, option), allowClear}. Returns {el, input,
  // setOptions, setText, close}.
  function makeCombobox(opts) {
    var wrap = document.createElement("div"); wrap.className = "sx__combo";
    var input = document.createElement("input");
    input.type = "text"; input.className = "sx__msg-input";
    input.placeholder = opts.placeholder || "";
    input.setAttribute("role", "combobox"); input.setAttribute("aria-expanded", "false");
    var list = document.createElement("ul"); list.className = "sx__combo-list"; list.hidden = true;
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
        var li = document.createElement("li");
        li.textContent = o.label; if (o.muted) li.className = "is-muted";
        li.addEventListener("mousedown", function (e) { e.preventDefault(); pick(i); });
        list.appendChild(li);
      });
      list.hidden = !visible.length;
      input.setAttribute("aria-expanded", String(!visible.length ? false : true));
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
      close: close,
    };
  }

  // POST with upload progress (an email with attachments is one big JSON body
  // — fetch gives no upload feedback). Mirrors the hosts' error contract.
  function postWithProgress(apiBase, path, payload, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", apiBase + path);
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

  // --- the dialog shell the component builds when the host has none --------
  var ownShell = null;   // {root, kind, title, body, foot, trap}
  var ownGuard = null;   // the guard of the compose open in the own shell
  var ownRequestClose = null;
  function buildOwnShell() {
    if (ownShell) return ownShell;
    var root = document.createElement("div");
    root.className = "sx__modal sx__modal--compose sx__modal--own";
    root.hidden = true; root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true");
    var backdrop = document.createElement("div"); backdrop.className = "sx__modal-backdrop";
    var card = document.createElement("div"); card.className = "sx__modal-card"; card.setAttribute("role", "document");
    var head = document.createElement("div"); head.className = "sx__modal-head";
    var headText = document.createElement("div");
    var kind = document.createElement("p"); kind.className = "sx__modal-kind";
    var title = document.createElement("h3"); title.className = "sx__modal-name";
    headText.appendChild(kind); headText.appendChild(title);
    var actions = document.createElement("span"); actions.className = "sx__modal-actions";
    var close = document.createElement("button"); close.type = "button"; close.className = "sx__modal-close";
    close.setAttribute("aria-label", "Close"); close.textContent = "×";
    actions.appendChild(close);
    head.appendChild(headText); head.appendChild(actions);
    var body = document.createElement("div"); body.className = "sx__modal-body";
    var foot = document.createElement("div"); foot.className = "sx__modal-foot";
    card.appendChild(head); card.appendChild(body); card.appendChild(foot);
    root.appendChild(backdrop); root.appendChild(card);
    document.body.appendChild(root);
    close.addEventListener("click", function () { if (ownRequestClose) ownRequestClose(); });
    backdrop.addEventListener("click", function () { if (ownRequestClose) ownRequestClose(); });
    document.addEventListener("keydown", function (e) {
      if (root.hidden) return;
      // Ctrl/Cmd+Enter sends from anywhere inside the open compose dialog.
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && ownGuard && ownGuard.send) {
        e.preventDefault(); ownGuard.send(); return;
      }
      // Keep keyboard focus inside the dialog while it is open (focus trap).
      if (e.key === "Tab") {
        var focusables = card.querySelectorAll(
          "button, [href], input, select, textarea, [contenteditable=true], [tabindex]:not([tabindex='-1'])"
        );
        var list = Array.prototype.filter.call(focusables, function (el) {
          return !el.hidden && el.offsetParent !== null && !el.disabled;
        });
        if (list.length) {
          var first = list[0], last = list[list.length - 1];
          if (e.shiftKey && (document.activeElement === first || !card.contains(document.activeElement))) {
            e.preventDefault(); last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault(); first.focus();
          } else if (!card.contains(document.activeElement)) {
            e.preventDefault(); first.focus();
          }
        }
      }
      if (e.key === "Escape" && ownRequestClose) ownRequestClose();
    });
    ownShell = { root: root, kind: kind, title: title, body: body, foot: foot };
    return ownShell;
  }
  function ownModal() {
    var s = buildOwnShell();
    return {
      open: function (kind, title) {
        s.kind.textContent = kind || ""; s.title.textContent = title || "";
        s.body.innerHTML = ""; s.foot.innerHTML = ""; s.root.hidden = false;
      },
      close: function () { s.root.hidden = true; ownGuard = null; ownRequestClose = null; },
      body: function () { return s.body; },
      foot: function () { return s.foot; },
      setTitle: function (t) { s.title.textContent = t || ""; },
    };
  }

  // --- the dialog ----------------------------------------------------------
  function open(host, pre) {
    pre = pre || {};
    var features = Object.assign(
      { cc: true, templates: true, attachments: true, documents: true, drafts: true, reply: true, addressBook: true },
      host.features || {}
    );
    var endpoints = host.endpoints || {};
    var record = host.record || {};
    var modal = host.modal || ownModal();
    var isInternal = host.isInternal || function () { return false; };
    var fmtWhen = host.fmtWhen || function (v) { return v || ""; };
    var hostNotice = host.notice || function () {};
    var api = host.api;
    function unauthorized() { if (host.onUnauthorized) host.onUnauthorized(); }
    var cached = host.mailbox && host.mailbox.get ? host.mailbox.get() : undefined;
    var senderMailbox = cached ? cached.mailbox : undefined;
    var senderSignature = cached ? (cached.signature || "") : "";
    function rememberMailbox(mb, sig) {
      senderMailbox = mb; senderSignature = sig || "";
      if (host.mailbox && host.mailbox.set) host.mailbox.set(mb, sig || "");
    }
    var replyKey = pre.replyToId || null;
    var draftKeyOf = host.draftKey || function (rk) {
      var seg = window.location.pathname.split("/").filter(Boolean)[0] || "";
      return "cbmDraft:" + seg + ":" + (record.id || "none") + ":" + (rk || "new");
    };
    function loadDraft(rk) {
      if (!features.drafts) return null;
      try {
        var raw = localStorage.getItem(draftKeyOf(rk));
        if (!raw) return null;
        var d = JSON.parse(raw);
        if (!d || !d.ts || Date.now() - d.ts > 7 * 24 * 3600 * 1000) return null;
        return d;
      } catch (e) { return null; }
    }
    function storeDraft(rk, state) {
      if (!features.drafts) return;
      try { localStorage.setItem(draftKeyOf(rk), JSON.stringify(state)); } catch (e) {}
    }
    function clearDraft(rk) {
      try { localStorage.removeItem(draftKeyOf(rk)); } catch (e) {}
    }

    // Header: the record name for context, the action as the title.
    modal.open(record.name || "", pre.forward ? "Forward" : (pre.replyToId ? "Reply" : "New email"));
    var body = modal.body();
    var guard = { dirty: function () { return false; }, discard: function () {}, send: null, backConvId: pre.backToConv || null };
    if (!host.modal) { ownGuard = guard; ownRequestClose = requestClose; }

    function requestClose() {
      if (host.requestClose) { host.requestClose(); return; }
      if (!guard.dirty()) { modal.close(); return; }
      // The component's own discard-confirm: the footer asks, nothing leaves
      // the dialog, and Keep writing restores the buttons.
      var foot = modal.foot();
      var kept = Array.prototype.slice.call(foot.childNodes);
      foot.innerHTML = "";
      var q = document.createElement("p"); q.className = "sx__foot-msg sx__notice is-warn";
      q.textContent = "Your message hasn't been sent. It stays saved as a draft unless you discard it.";
      var discard = document.createElement("button"); discard.type = "button";
      discard.className = "cbm-button cbm-button--secondary"; discard.textContent = "Discard draft";
      var keep = document.createElement("button"); keep.type = "button";
      keep.className = "cbm-button"; keep.textContent = "Keep writing";
      discard.addEventListener("click", function () { guard.discard(); modal.close(); });
      keep.addEventListener("click", function () {
        foot.innerHTML = ""; kept.forEach(function (n) { foot.appendChild(n); });
      });
      foot.appendChild(q); foot.appendChild(discard); foot.appendChild(keep);
    }

    // From: the signed-in user's own chapter mailbox — the address the message
    // actually goes out as. Fetched once and cached by the page.
    var fromRow = document.createElement("div"); fromRow.className = "sx__fact sx__compose-from";
    var fromL = document.createElement("span"); fromL.className = "sx__fact-l"; fromL.textContent = "From";
    var fromV = document.createElement("span"); fromV.className = "sx__fact-v"; fromV.textContent = senderMailbox || "…";
    fromRow.appendChild(fromL); fromRow.appendChild(fromV);
    body.appendChild(fromRow);
    var NO_MAILBOX = "no {{abbr}} email on your profile — sending won't work";
    function setFrom(text) { fromV.textContent = text; }
    if (senderMailbox === undefined && endpoints.mailbox) {
      api(endpoints.mailbox).then(function (r) {
        rememberMailbox((r && r.mailbox) || null, (r && r.signature) || "");
        setFrom(senderMailbox || (r && r.reason) || NO_MAILBOX);
        seedSignature();
      }).catch(function () { setFrom("your {{abbr}} email address"); });
    } else if (senderMailbox === null) {
      setFrom(NO_MAILBOX);
    }

    // To: every record contact with an email address as a checkbox — ALL
    // checked by default on a fresh compose (uncheck to leave someone off);
    // a reply pre-checks only the addresses it's replying to. A host with a
    // fixed recipient (the lead's page: one person to one person) shows the
    // address as a fact and offers no free entry.
    var contactRecips = (record.contacts || []).filter(function (c) { return c.email; });
    var preAddrs = String(pre.to || "").split(/[,;\s]+/).filter(Boolean)
      .map(function (a) { return extractEmail(a); });
    var preKeys = preAddrs.map(function (a) { return a.toLowerCase(); });
    var recipChecks = [];   // {email, box} per listed contact
    var fixed = !!record.fixedRecipient;
    if (fixed) {
      var toRow = document.createElement("div"); toRow.className = "sx__fact sx__compose-from";
      var toL = document.createElement("span"); toL.className = "sx__fact-l"; toL.textContent = "To";
      var toV = document.createElement("span"); toV.className = "sx__fact-v";
      var fixedTo = contactRecips.length ? contactRecips[0] : { email: preAddrs[0] || "", name: "" };
      toV.textContent = (fixedTo.name ? fixedTo.name + " — " : "") + (fixedTo.email || "(no email address)");
      toRow.appendChild(toL); toRow.appendChild(toV); body.appendChild(toRow);
      if (fixedTo.email) recipChecks.push({ email: fixedTo.email, box: { checked: true } });
    } else if (contactRecips.length) {
      var toWrap = document.createElement("div"); toWrap.className = "sx__msg-field";
      var toHead = document.createElement("div"); toHead.className = "sx__to-head";
      var toLab = document.createElement("span"); toLab.className = "sx__msg-label"; toLab.textContent = "To";
      toHead.appendChild(toLab);
      if (contactRecips.length > 5) {
        var allBtn = document.createElement("button"); allBtn.type = "button";
        allBtn.className = "sx__link-btn"; allBtn.textContent = "All";
        var noneBtn = document.createElement("button"); noneBtn.type = "button";
        noneBtn.className = "sx__link-btn"; noneBtn.textContent = "None";
        allBtn.addEventListener("click", function () {
          recipChecks.forEach(function (r) { r.box.checked = true; }); onRecipientsChanged();
        });
        noneBtn.addEventListener("click", function () {
          recipChecks.forEach(function (r) { r.box.checked = false; }); onRecipientsChanged();
        });
        toHead.appendChild(allBtn); toHead.appendChild(noneBtn);
      }
      toWrap.appendChild(toHead);
      var listEl = document.createElement("div"); listEl.className = "sx__to-list";
      contactRecips.forEach(function (c) {
        var lab = document.createElement("label"); lab.className = "sx__addr-check";
        var box = document.createElement("input"); box.type = "checkbox";
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
    // Free-entry field for anyone not on the record; reply addresses that
    // aren't record contacts land here so they stay on the thread. Cc/Bcc
    // reveal on demand from the label line.
    var knownEmails = {};
    recipChecks.forEach(function (r) { knownEmails[r.email.toLowerCase()] = 1; });
    var extra = preAddrs.filter(function (a) { return !knownEmails[a.toLowerCase()]; }).join(", ");
    var addrPlaceholder = "name@example.com, another@example.com";
    var ccField = null, bccField = null, ccLink = null, bccLink = null;
    if (!fixed) {
      var otherWrap = field(contactRecips.length ? "Other recipients" : "To",
        "commTo", extra, false, { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
      if (features.cc) {
        var otherLab = otherWrap.querySelector(".sx__msg-label");
        var toggles = document.createElement("span"); toggles.className = "sx__ccbcc-toggles";
        ccLink = document.createElement("button"); ccLink.type = "button";
        ccLink.className = "sx__link-btn"; ccLink.textContent = "Cc";
        bccLink = document.createElement("button"); bccLink.type = "button";
        bccLink.className = "sx__link-btn"; bccLink.textContent = "Bcc";
        toggles.appendChild(ccLink); toggles.appendChild(bccLink);
        var labLine = document.createElement("div"); labLine.className = "sx__to-head";
        otherWrap.insertBefore(labLine, otherLab);
        labLine.appendChild(otherLab); labLine.appendChild(toggles);
      }
      body.appendChild(otherWrap);
      if (features.cc) {
        ccField = field("Cc", "commCc", "", false, { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
        bccField = field("Bcc", "commBcc", "", false, { placeholder: addrPlaceholder, onInput: onRecipientsChanged });
        ccField.hidden = true; bccField.hidden = true;
        body.appendChild(ccField); body.appendChild(bccField);
        ccLink.addEventListener("click", function () { ccField.hidden = false; ccLink.hidden = true; $("commCc").focus(); });
        bccLink.addEventListener("click", function () { bccField.hidden = false; bccLink.hidden = true; $("commBcc").focus(); });
      }
    }

    // Checked contacts + whatever was typed, deduped case-insensitively.
    function fieldAddrs(id) {
      var el = $(id);
      return el && !el.closest(".sx__msg-field").hidden ? parseAddrList(el.value) : { emails: [], invalid: [] };
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
      var toParsed = fieldAddrs("commTo"), ccParsed = fieldAddrs("commCc"), bccParsed = fieldAddrs("commBcc");
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

    // --- Email template picker. EspoCRM renders the template server-side
    // (placeholders resolved against this record + the first recipient); the
    // result loads here as a plain editable draft. Selecting over a non-empty
    // draft asks before replacing; a parse failure leaves the draft untouched;
    // "No template" restores the pre-template draft.
    var templateAttachments = [];   // {id, name} chips from the selected template
    var localAttachments = [];      // {filename, contentType, dataBase64, size} uploads
    var docAttachments = [];        // {documentId, filename}
    var fwdAttachments = [];        // {communicationId, partIndex, filename, size}
    var tplAll = [], tplConfirmEl = null, preTplSnapshot = null;
    var tplWrap = document.createElement("div"); tplWrap.className = "sx__msg-field";
    tplWrap.hidden = true;
    var tplLab = document.createElement("span"); tplLab.className = "sx__msg-label"; tplLab.textContent = "Template";
    var tplLine = document.createElement("div"); tplLine.className = "sx__opt-line";
    var tplCombo = makeCombobox({
      placeholder: "Search templates…",
      allowClear: true,
      emptyLabel: "No template",
      onSelect: function (id) { onTemplatePicked(id); },
    });
    tplLine.appendChild(tplCombo.el);
    var tplNotice = document.createElement("p"); tplNotice.className = "sx__notice"; tplNotice.hidden = true;
    tplWrap.appendChild(tplLab); tplWrap.appendChild(tplLine); tplWrap.appendChild(tplNotice);
    body.appendChild(tplWrap);
    if (features.templates && host.sendingEnabled && endpoints.templates) {
      api(endpoints.templates).then(function (r) {
        tplAll = (r && r.templates) || [];
        if (tplAll.length) {
          tplCombo.setOptions(tplAll.map(function (t) { return { id: t.id, label: t.name }; }));
          tplWrap.hidden = false;
        }
      }).catch(function () { /* no picker — compose works without it */ });
    }
    // Signature (the user's EspoCRM Preferences signature, riding /mailbox):
    // seeded into a PRISTINE body when the dialog opens — from there it's
    // plain editable text. A body still equal to any auto-generated state
    // counts as empty/untouched, so a template pick right after opening
    // doesn't ask to "replace" and closing doesn't ask to discard.
    var quoteHtml = pre.quote ? buildQuoteHtml(pre.quote)
      : (pre.forward ? buildForwardHtml(pre.forward) : "");
    var initialSubject = pre.subject || "";
    var pristineBodies = {};   // every auto-generated body state we've set
    function markPristine(v) { pristineBodies[String(v || "")] = 1; }
    function bodyPristine() { return !!pristineBodies[String(bodyValue() || "")]; }
    function seedSignature() {
      if (!senderSignature) return;
      if (!bodyPristine()) return;  // the user already typed — never overwrite
      setBody("<p><br></p><p><br></p>" + senderSignature +
        (quoteHtml ? "<p><br></p>" + quoteHtml : ""));
      markPristine(bodyValue());
    }
    function draftHasContent() {
      return !!($("commSubject").value.trim() !== initialSubject.trim() && $("commSubject").value.trim()) ||
        !bodyPristine() ||
        localAttachments.length > 0 ||
        docAttachments.length > 0 ||
        fwdAttachments.length > 0;
    }
    // The compose body's current value: HTML from the rich editor, or the
    // plain textarea's text when the editor script didn't load (the send
    // path accepts both — plain text is upconverted server-side).
    function bodyValue() {
      var el = $("commBody");
      if (!el) return "";
      return el._cbmRichText ? el._cbmRichText.getValue() : el.value;
    }
    function setBody(html) {
      var el = $("commBody");
      if (!el) return;
      if (el._cbmRichText) el._cbmRichText.setValue(html);
      else el.value = html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/p\s*>/gi, "\n\n").replace(/<[^>]+>/g, "");
    }
    function buildQuoteHtml(q) {
      var head = "On " + (q.date ? fmtWhen(q.date) : "an earlier date") +
        ", " + (q.from || "they") + " wrote:";
      var p = document.createElement("p"); p.textContent = head;  // escapes the name
      return "<blockquote class=\"quoted-reply\">" + p.outerHTML + (q.html || "") + "</blockquote>";
    }
    // Gmail-style forwarded block: header lines, then the original message.
    function buildForwardHtml(f) {
      var lines = [
        "---------- Forwarded message ----------",
        "From: " + (f.from || "?"),
        f.date ? "Date: " + fmtWhen(f.date) : "",
        f.subject ? "Subject: " + f.subject : "",
        f.to ? "To: " + f.to : "",
      ].filter(Boolean);
      var headHtml = lines.map(function (t) {
        var p = document.createElement("p"); p.textContent = t;  // escapes everything
        return p.outerHTML;
      }).join("");
      return "<blockquote class=\"quoted-reply\">" + headHtml + (f.html || "") + "</blockquote>";
    }
    function onTemplatePicked(id) {
      if (tplConfirmEl) { tplConfirmEl.remove(); tplConfirmEl = null; }
      if (!id) {
        // "No template": restore whatever the draft was before the last apply.
        if (preTplSnapshot) {
          $("commSubject").value = preTplSnapshot.subject;
          setBody(preTplSnapshot.body);
          if (preTplSnapshot.pristine) markPristine(bodyValue());
          templateAttachments = preTplSnapshot.tplAttach.slice();
          renderAttachChips();
          preTplSnapshot = null;
          tplNotice.hidden = true;
          markEdited();
        }
        return;
      }
      if (!draftHasContent()) { applyTemplate(id); return; }
      // Never silently overwrite an edited draft.
      tplConfirmEl = document.createElement("div"); tplConfirmEl.className = "sx__notice is-warn";
      tplConfirmEl.appendChild(document.createTextNode("Replace current content? "));
      var yes = document.createElement("button"); yes.type = "button";
      yes.className = "cbm-button"; yes.textContent = "Replace";
      var no = document.createElement("button"); no.type = "button";
      no.className = "cbm-button cbm-button--secondary"; no.textContent = "Keep my draft";
      yes.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; applyTemplate(id);
      });
      no.addEventListener("click", function () {
        tplConfirmEl.remove(); tplConfirmEl = null; tplCombo.setText("");
      });
      tplConfirmEl.appendChild(yes); tplConfirmEl.appendChild(document.createTextNode(" "));
      tplConfirmEl.appendChild(no);
      tplWrap.appendChild(tplConfirmEl);
    }
    async function applyTemplate(id) {
      tplNotice.hidden = true;
      preTplSnapshot = {
        subject: $("commSubject").value,
        body: String(bodyValue() || ""),
        pristine: bodyPristine(),
        tplAttach: templateAttachments.slice(),
      };
      try {
        var r = await api(endpoints.parse(id), {
          method: "POST",
          body: { emailAddress: recipientList()[0] || "" },
        });
        $("commSubject").value = r.subject || "";
        // The rendered draft replaces the body; the signature re-appends
        // below it (EspoCRM's own compose behavior) — templates shouldn't
        // carry their own sign-off. A reply keeps its quoted original at
        // the bottom.
        setBody((r.bodyHtml || "") +
          (senderSignature ? "<p><br></p>" + senderSignature : "") +
          (quoteHtml ? "<p><br></p>" + quoteHtml : ""));
        templateAttachments = (r.attachments || []).slice();
        renderAttachChips();
        if ((r.leftoverTokens || []).length) {
          tplNotice.textContent = "Some placeholders couldn't be filled: " +
            r.leftoverTokens.join(", ") + " — review the draft before sending.";
          tplNotice.className = "sx__notice is-warn"; tplNotice.hidden = false;
        }
        markEdited();
      } catch (e) {
        if (e.status === 401) { flushDraft(); modal.close(); unauthorized(); return; }
        // Non-destructive — the existing draft stays untouched.
        preTplSnapshot = null;
        tplNotice.textContent = e.message || "Couldn't apply the template.";
        tplNotice.className = "sx__notice is-error"; tplNotice.hidden = false;
        tplCombo.setText("");
      }
    }

    body.appendChild(field("Subject", "commSubject", pre.subject, false, { onInput: markEdited }));
    body.appendChild(field("Message", "commBody", "", true, { onInput: markEdited }));
    markPristine("");
    if (quoteHtml) {
      setBody("<p><br></p>" + quoteHtml);
      markPristine(bodyValue());
    }
    // Cached signature seeds now; a first-ever compose seeds when the
    // mailbox fetch above resolves.
    if (senderSignature) seedSignature();

    // --- Attachments: template chips (bytes stay in the CRM until send) plus
    // the user's own files, with sizes and a running total against the cap.
    var attachWrap = document.createElement("div"); attachWrap.className = "sx__msg-field";
    var attachLab = document.createElement("span"); attachLab.className = "sx__msg-label"; attachLab.textContent = "Attachments";
    var chipsEl = document.createElement("div"); chipsEl.className = "sx__attach-chips";
    var attachTotalEl = document.createElement("p"); attachTotalEl.className = "sx__attach-total"; attachTotalEl.hidden = true;
    var attachLine = document.createElement("div"); attachLine.className = "sx__opt-line";
    var fileBtn = document.createElement("button"); fileBtn.type = "button";
    fileBtn.className = "cbm-button cbm-button--secondary"; fileBtn.textContent = "Attach files…";
    var fileInput = document.createElement("input"); fileInput.type = "file";
    fileInput.multiple = true; fileInput.hidden = true;
    fileBtn.addEventListener("click", function () { fileInput.click(); });
    attachLine.appendChild(fileBtn); attachLine.appendChild(fileInput);
    // "Attach from documents…" — the record's Google Drive documents, without
    // a round-trip through the user's disk. Chips carry {documentId}; the
    // SERVER fetches the original bytes at send time.
    var docPickWrap = null, docPickList = null, docsCache = null;
    if (features.documents && endpoints.documents && record.id) {
      docPickWrap = document.createElement("div"); docPickWrap.className = "sx__combo";
      var docBtn = document.createElement("button"); docBtn.type = "button";
      docBtn.className = "cbm-button cbm-button--secondary"; docBtn.textContent = "Attach from documents…";
      docPickList = document.createElement("ul"); docPickList.className = "sx__combo-list"; docPickList.hidden = true;
      docPickWrap.appendChild(docBtn); docPickWrap.appendChild(docPickList);
      attachLine.appendChild(docPickWrap);
      docBtn.addEventListener("click", async function () {
        if (!docPickList.hidden) { docPickList.hidden = true; return; }
        if (docsCache === null) {
          docBtn.disabled = true;
          try {
            var res = await api(endpoints.documents);
            docsCache = res.documents || [];
          } catch (e) {
            docsCache = null;
            if (e.status === 401) { flushDraft(); modal.close(); unauthorized(); return; }
            footErr(e.status === 503
              ? "The document integration isn't enabled — attach a file from your computer instead."
              : (e.message || "Couldn't load this record's documents."));
            return;
          } finally { docBtn.disabled = false; }
        }
        renderDocPick();
      });
      document.addEventListener("click", function (e) {
        if (docPickWrap && !docPickWrap.contains(e.target)) docPickList.hidden = true;
      });
    }
    function renderDocPick() {
      docPickList.innerHTML = "";
      var chosen = {};
      docAttachments.forEach(function (d) { chosen[d.documentId] = 1; });
      var avail = (docsCache || []).filter(function (d) {
        return !chosen[d.id] && (d.status || "active") === "active";
      });
      if (!avail.length) {
        var li = document.createElement("li"); li.className = "is-muted";
        li.textContent = (docsCache || []).length
          ? "Every document is already attached."
          : "No documents on this record yet.";
        docPickList.appendChild(li);
      }
      avail.forEach(function (d) {
        var li = document.createElement("li");
        li.textContent = d.filename + (d.docType ? " — " + d.docType : "");
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          docAttachments.push({ documentId: d.id, filename: d.filename });
          docPickList.hidden = true;
          renderAttachChips(); markEdited();
        });
        docPickList.appendChild(li);
      });
      docPickList.hidden = false;
    }
    attachWrap.appendChild(attachLab); attachWrap.appendChild(chipsEl);
    attachWrap.appendChild(attachTotalEl); attachWrap.appendChild(attachLine);
    if (features.attachments) body.appendChild(attachWrap);
    function attachTotal() {
      return localAttachments.reduce(function (n, f) { return n + (f.size || 0); }, 0) +
        fwdAttachments.reduce(function (n, f) { return n + (f.size || 0); }, 0);
    }
    function renderAttachChips() {
      chipsEl.innerHTML = "";
      function chip(name, size, onRemove) {
        var c = document.createElement("span"); c.className = "sx__attach-chip";
        c.appendChild(document.createTextNode(name + " "));
        if (size) {
          var s = document.createElement("span"); s.className = "sx__attach-size";
          s.textContent = "(" + fmtBytes(size) + ") ";
          c.appendChild(s);
        }
        var x = document.createElement("button"); x.type = "button";
        x.className = "sx__chip-x"; x.textContent = "✕"; x.title = "Remove attachment";
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
      docAttachments.forEach(function (d, i) {
        chip("📄 " + d.filename, 0, function () {
          docAttachments.splice(i, 1); renderAttachChips(); markEdited();
        });
      });
      fwdAttachments.forEach(function (f, i) {
        chip("↪ " + f.filename, f.size || 0, function () {
          fwdAttachments.splice(i, 1); renderAttachChips(); markEdited();
        });
      });
      var total = attachTotal();
      attachTotalEl.hidden = !(localAttachments.length || fwdAttachments.length);
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
      })).concat(docAttachments.map(function (d) {
        return { documentId: d.documentId, filename: d.filename };
      })).concat(fwdAttachments.map(function (f) {
        return { forwardCommunicationId: f.communicationId, partIndex: f.partIndex, filename: f.filename };
      }));
    }

    var allowUnknown = false;
    var resolvedAddresses = {};   // addresses handled (linked/created) this compose
    var commResolvers = null;     // one entry per non-record recipient, built once
    var optionsPanel = document.createElement("div");
    body.appendChild(optionsPanel);

    // --- footer: status line + Cancel + Send (Send rightmost, the app's
    // primary-action slot; the message/summary stays pinned and visible).
    var foot = modal.foot(); foot.innerHTML = "";
    var footMsg = document.createElement("p"); footMsg.className = "sx__foot-msg form-error"; footMsg.hidden = true;
    var footSummary = document.createElement("p"); footSummary.className = "sx__foot-summary";
    var cancel = document.createElement("button"); cancel.type = "button";
    cancel.className = "cbm-button cbm-button--secondary"; cancel.textContent = "Cancel";
    cancel.addEventListener("click", requestClose);
    var send = document.createElement("button"); send.type = "button";
    send.className = "cbm-button"; send.textContent = "Send";
    foot.appendChild(footSummary); foot.appendChild(footMsg);
    foot.appendChild(cancel); foot.appendChild(send);

    function footErr(text) {
      footMsg.textContent = text; footMsg.className = "sx__foot-msg form-error";
      footMsg.hidden = false; footSummary.hidden = true;
    }
    function footWarn(text) {
      footMsg.textContent = text; footMsg.className = "sx__foot-msg sx__notice is-warn";
      footMsg.hidden = false; footSummary.hidden = true;
    }
    function clearFootMsg() {
      footMsg.hidden = true; footSummary.hidden = false;
    }
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

    // Any recipient change invalidates a built add-to-record panel and any
    // armed "send anyway" state — the user changed the question.
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

    // --- draft persistence: an accidental close, tab crash, or session
    // expiry never loses a typed message. Saved (debounced) on every edit;
    // cleared on send or an explicit "Discard draft".
    var draftTimer = null;
    function draftState() {
      return {
        ts: Date.now(),
        subject: $("commSubject").value,
        body: String(bodyValue() || ""),
        to: $("commTo") ? $("commTo").value : "",
        cc: $("commCc") ? $("commCc").value : "",
        bcc: $("commBcc") ? $("commBcc").value : "",
        ccShown: !!(ccField && !ccField.hidden), bccShown: !!(bccField && !bccField.hidden),
        checked: recipChecks.filter(function (r) { return r.box.checked; })
          .map(function (r) { return r.email.toLowerCase(); }),
        tplAttach: templateAttachments,
        docAttach: docAttachments,
        fwdAttach: fwdAttachments,
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
      $("commSubject").value = savedDraft.subject || "";
      if (savedDraft.body) setBody(savedDraft.body);
      if ($("commTo")) $("commTo").value = savedDraft.to || "";
      if (ccField && (savedDraft.ccShown || savedDraft.cc)) { ccField.hidden = false; ccLink.hidden = true; $("commCc").value = savedDraft.cc || ""; }
      if (bccField && (savedDraft.bccShown || savedDraft.bcc)) { bccField.hidden = false; bccLink.hidden = true; $("commBcc").value = savedDraft.bcc || ""; }
      if (savedDraft.checked && recipChecks.length && !fixed) {
        var wanted = {};
        savedDraft.checked.forEach(function (a) { wanted[a] = 1; });
        recipChecks.forEach(function (r) { r.box.checked = !!wanted[r.email.toLowerCase()]; });
      }
      templateAttachments = (savedDraft.tplAttach || []).slice();
      docAttachments = (savedDraft.docAttach || []).slice();
      fwdAttachments = (savedDraft.fwdAttach || []).slice();
      renderAttachChips();
      updateSummary();
      var note = document.createElement("div"); note.className = "sx__notice sx__draft-note";
      note.appendChild(document.createTextNode("Restored your unsent draft."));
      var fresh = document.createElement("button"); fresh.type = "button";
      fresh.className = "sx__link-btn"; fresh.textContent = "Start fresh";
      fresh.addEventListener("click", function () {
        clearDraft(replyKey);
        note.remove();
        $("commSubject").value = initialSubject;
        setBody("");
        markPristine("");
        if (quoteHtml) { setBody("<p><br></p>" + quoteHtml); markPristine(bodyValue()); }
        seedSignature();
        if ($("commTo")) $("commTo").value = extra;
        if ($("commCc")) $("commCc").value = "";
        if ($("commBcc")) $("commBcc").value = "";
        if (!fixed) {
          recipChecks.forEach(function (r) {
            r.box.checked = pre.forward ? false
              : (pre.to ? preKeys.indexOf(r.email.toLowerCase()) !== -1 : true);
          });
        }
        templateAttachments = []; localAttachments = []; docAttachments = [];
        fwdAttachments = pre.forward ? fwdAttachments : [];
        renderAttachChips(); updateSummary(); clearFootMsg();
      });
      note.appendChild(fresh);
      body.insertBefore(note, body.firstChild);
    }

    // Forwarding: pull the original's real attachments as pre-selected chips
    // (unless a restored draft already carried them). The bytes stay in the
    // source mailbox until send — the server fetches them then.
    if (pre.forward && pre.forwardCommunicationId && !fwdAttachments.length &&
        record.id && host.sendingEnabled && endpoints.forwardAttachments) {
      api(endpoints.forwardAttachments(pre.forwardCommunicationId))
        .then(function (r) {
          var items = (r && r.attachments) || [];
          if (!items.length) return;
          fwdAttachments = items.map(function (a) {
            return {
              communicationId: pre.forwardCommunicationId,
              partIndex: a.partIndex,
              filename: a.filename,
              size: a.size,
            };
          });
          renderAttachChips();
        })
        .catch(function (e) {
          if (e && e.status === 401) { flushDraft(); modal.close(); unauthorized(); return; }
          footWarn("Couldn't attach the forwarded files (" +
            (e && e.message ? e.message : "the original may be gone") +
            ") — the message text will still forward.");
        });
    }

    // The close-guard: Escape / × / backdrop / Cancel confirm before
    // discarding real content; a reply returns to its conversation.
    guard.dirty = function () { return draftHasContent(); };
    guard.discard = function () { flushDraftCancel(); clearDraft(replyKey); };
    guard.send = function () { doSend(); };
    function flushDraftCancel() {
      if (draftTimer) { clearTimeout(draftTimer); draftTimer = null; }
    }
    function retireGuard() {
      guard.dirty = function () { return false; };
      guard.send = null;
    }

    // Recipients that are neither record contacts nor the chapter's own addresses.
    function unknownRecipients(recipients) {
      var known = {};
      (record.contacts || []).forEach(function (c) {
        if (c.email) known[String(c.email).toLowerCase()] = 1;
      });
      return recipients.filter(function (a) {
        a = a.toLowerCase();
        return !known[a] && !resolvedAddresses[a] && !isInternal(a);
      });
    }

    // Checkbox-driven router: every non-record recipient gets an "Add to this
    // record" checkbox (checked by default). Existing CRM contacts (any type)
    // just show who they are; unknown addresses show a small create form
    // (first/last/phone/company). ONE "Add & Send" click then links/creates
    // the checked ones and sends; unchecked recipients go as a one-off (the
    // conversation still attaches here and replies follow the thread).
    var companiesPromise = null;
    function getCompanies() {
      if (!companiesPromise) {
        companiesPromise = api(endpoints.companies).catch(function () { return { companies: [] }; });
      }
      return companiesPromise;
    }
    async function buildUnknownPanel(unknown) {
      optionsPanel.innerHTML = "<p class='sx__muted'>Checking the CRM for " +
        (unknown.length === 1 ? "this address…" : "these addresses…") + "</p>";
      var lookups = {};
      for (var i = 0; i < unknown.length; i++) {
        try { lookups[unknown[i]] = await api(endpoints.contactLookup(unknown[i])); }
        catch (e) {
          if (e.status === 401) { flushDraft(); modal.close(); unauthorized(); return; }
          lookups[unknown[i]] = { found: false };
        }
      }
      optionsPanel.innerHTML = "";
      var head = document.createElement("p"); head.className = "sx__notice is-warn";
      head.textContent = (unknown.length === 1 ? "This recipient isn't" : "These recipients aren't") +
        " a contact on this record. Leave \"Add to this record\" checked to link them" +
        " (fill in the details for new people), or uncheck to send without adding." +
        " Then click Add & Send.";
      optionsPanel.appendChild(head);
      commResolvers = [];
      unknown.forEach(function (addr) {
        optionsPanel.appendChild(addressRow(addr, lookups[addr] || { found: false }));
      });
      send.textContent = "Add & Send";
      optionsPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function addressRow(addr, lookup) {
      var row = document.createElement("div"); row.className = "sx__msg-field sx__addr-row";
      var head = document.createElement("div"); head.className = "sx__opt-line";
      var checkLab = document.createElement("label"); checkLab.className = "sx__addr-check";
      var check = document.createElement("input"); check.type = "checkbox"; check.checked = true;
      checkLab.appendChild(check);
      checkLab.appendChild(document.createTextNode(" Add to this record"));
      var who = document.createElement("span"); who.className = "sx__msg-label";
      head.appendChild(who); head.appendChild(checkLab);
      row.appendChild(head);
      var err = document.createElement("p"); err.className = "form-error"; err.hidden = true;

      var resolver;
      if (lookup.found && lookup.contact) {
        // Existing CRM contact — a member, a client, or a non-client alike.
        var c = lookup.contact;
        var kind = c.isCbmMember ? "a {{abbr}} member" : (c.company ? c.company : "an existing contact");
        who.textContent = addr + " — " + (c.name || "?") + " (" + kind + ", already in the CRM)";
        var asComentor = c.isCbmMember && c.mentorProfileId && record.supportsComentor && endpoints.addComentor;
        if (asComentor) checkLab.childNodes[1].textContent = " Add as {{abbr}} contact";
        if (c.isCbmMember && !asComentor) {
          // A member must NEVER be linked as a client contact (that put
          // mentors under "Other Contacts"). No co-mentor path here => they
          // simply receive the email.
          check.checked = false; check.disabled = true;
          checkLab.childNodes[1].textContent = " Will receive the email";
        }
        resolver = async function () {
          if (!check.checked) return false;
          if (asComentor) {
            await api(endpoints.addComentor, { method: "POST", body: { mentorProfileId: c.mentorProfileId } });
          } else {
            await api(endpoints.addContact, { method: "POST", body: { contactId: c.id } });
          }
          resolvedAddresses[addr.toLowerCase()] = 1;
          return true;
        };
      } else {
        // Unknown to the CRM — create form (enabled while the box is checked).
        who.textContent = addr + " — not in the CRM yet";
        var line2 = document.createElement("div"); line2.className = "sx__opt-line";
        var first = document.createElement("input"); first.type = "text"; first.placeholder = "First name"; first.className = "sx__msg-input";
        var last = document.createElement("input"); last.type = "text"; last.placeholder = "Last name"; last.className = "sx__msg-input";
        var phone = document.createElement("input"); phone.type = "tel"; phone.placeholder = "Phone (optional)"; phone.className = "sx__msg-input";
        line2.appendChild(first); line2.appendChild(last); line2.appendChild(phone);
        row.appendChild(line2);
        // Company: type-ahead over the CRM's accounts (fetched once per
        // compose, shared across rows) + a "+ New company…" escape.
        var line3 = document.createElement("div"); line3.className = "sx__opt-line";
        var companyChoice = { id: "", newName: "" };
        var newCompany = document.createElement("input"); newCompany.type = "text";
        newCompany.placeholder = "New company name"; newCompany.className = "sx__msg-input"; newCompany.hidden = true;
        var companyCombo = makeCombobox({
          placeholder: "Company… (type to search)",
          allowClear: true,
          emptyLabel: "No company",
          onSelect: function (id) {
            if (id === "__new__") {
              companyChoice.id = "__new__"; newCompany.hidden = false; newCompany.focus();
            } else {
              companyChoice.id = id || ""; newCompany.hidden = true; newCompany.value = "";
            }
          },
        });
        getCompanies().then(function (res) {
          var opts = (res.companies || []).map(function (a) { return { id: a.id, label: a.name || a.id }; });
          opts.push({ id: "__new__", label: "+ New company…", muted: true });
          companyCombo.setOptions(opts);
        });
        line3.appendChild(companyCombo.el); line3.appendChild(newCompany);
        row.appendChild(line3);
        function setEnabled() {
          [first, last, phone, companyCombo.input, newCompany].forEach(function (el) { el.disabled = !check.checked; });
        }
        check.addEventListener("change", setEnabled);
        resolver = async function () {
          if (!check.checked) return false;
          if (!first.value.trim() && !last.value.trim()) {
            throw new Error("Enter a name for " + addr + " (or uncheck \"Add to this record\").");
          }
          var changes = { firstName: first.value.trim(), lastName: last.value.trim(), emailAddress: addr };
          if (phone.value.trim()) changes.phoneNumber = phone.value.trim();
          var payload = { changes: changes };
          if (companyChoice.id === "__new__" && newCompany.value.trim()) payload.newCompanyName = newCompany.value.trim();
          else if (companyChoice.id && companyChoice.id !== "__new__") changes.accountId = companyChoice.id;
          await api(endpoints.addContact, { method: "POST", body: payload });
          resolvedAddresses[addr.toLowerCase()] = 1;
          return true;
        };
      }
      row.appendChild(err);
      commResolvers.push({ addr: addr, resolve: resolver, errEl: err });
      return row;
    }

    async function doSend() {
      if (!host.sendingEnabled) {
        // No delivery in scaffold mode — communicate that plainly.
        modal.body().innerHTML = "";
        var note = document.createElement("p"); note.className = "sx__notice is-success";
        note.textContent = "Sending isn't available yet — the email integration hasn't been enabled for this deployment.";
        modal.body().appendChild(note);
        modal.foot().innerHTML = "";
        var ok = document.createElement("button"); ok.type = "button";
        ok.className = "cbm-button"; ok.textContent = "OK"; ok.addEventListener("click", function () { modal.close(); });
        modal.foot().appendChild(ok);
        retireGuard();
        return;
      }
      var sets = recipientSets();
      if (sets.invalid.length) {
        footErr("These don't look like email addresses: " + sets.invalid.join(", ") +
          " — fix or remove them. Separate addresses with commas.");
        return;
      }
      var recipients = sets.to.concat(sets.cc, sets.bcc);
      if (!recipients.length) {
        footErr(fixed ? "This person has no email address to send to." : "Choose at least one recipient.");
        if ($("commTo")) $("commTo").focus();
        return;
      }
      // A pristine body blocks the send — EXCEPT on a forward, where the
      // forwarded block alone IS the message (forwarding without comment is
      // normal email behavior).
      if (bodyPristine() && !pre.forward) {
        footErr("Write a message first.");
        var bodyEl = $("commBody");
        if (bodyEl && bodyEl._cbmRichText) bodyEl._cbmRichText.focus();
        else if (bodyEl) bodyEl.focus();
        return;
      }
      // "Send anyway" gate: a missing subject or unresolved template
      // placeholders deserve one explicit look before the email goes out.
      var holdups = [];
      if (!$("commSubject").value.trim()) holdups.push("it has no subject");
      var tokenScan = ($("commSubject").value + " " + String(bodyValue() || ""))
        .replace(new RegExp("<blockquote[\\s\\S]*$"), "");  // quoted original may legitimately carry braces
      var leftover = tokenScan.match(/\{[A-Za-z][A-Za-z0-9]*\.[A-Za-z0-9_]+\}/g);
      if (leftover) holdups.push("it still contains unfilled placeholders (" + leftover.slice(0, 3).join(", ") + ")");
      if (holdups.length && !sendArmed) {
        sendArmed = true;
        footWarn("Before this goes out: " + holdups.join(", and ") + ". Click “Send anyway” to send it as is.");
        send.textContent = "Send anyway";
        return;
      }
      clearFootMsg();
      var unknown = features.addressBook && endpoints.contactLookup ? unknownRecipients(recipients) : [];
      if (unknown.length && commResolvers === null) {
        await buildUnknownPanel(unknown);   // first click: show the rows
        return;
      }
      // Process the checkbox rows: link/create the checked ones; anything
      // unchecked goes as a one-off (server needs the explicit flag).
      if (commResolvers) {
        for (var ri = 0; ri < commResolvers.length; ri++) {
          var r = commResolvers[ri];
          if (resolvedAddresses[r.addr.toLowerCase()]) continue;
          r.errEl.hidden = true;
          try {
            var did = await r.resolve();
            if (!did) allowUnknown = true;
          } catch (e) {
            if (e.status === 401) { flushDraft(); modal.close(); unauthorized(); return; }
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
        subject: $("commSubject").value,
        body: bodyValue(),
        replyToCommunicationId: pre.replyToId || null,
        allowUnknownRecipients: allowUnknown,
        attachments: attachmentPayload(),
      };
      // Attachments make the body big — show upload progress past ~300 KB.
      var showProgress = JSON.stringify(payload).length > 300 * 1024;
      try {
        var sendResult = await postWithProgress(
          host.apiBase || "", endpoints.messages, payload,
          showProgress ? function (pct) { send.textContent = "Sending… " + pct + "%"; } : null
        );
        clearDraft(replyKey);
        // The message went out. If recording it in the CRM failed, say so and
        // offer a retry — a silent gap in CRM history is not acceptable.
        if (sendResult && sendResult.writeBack && sendResult.writeBack.ok === false) {
          retireGuard();
          showWriteBackRetry(sendResult.writeBack);
          if (host.onSent) host.onSent(sendResult);
          return;
        }
        retireGuard();
        modal.close();
        // ingestWarning: the email went OUT, but the page may not show it yet
        // (write-through/attach failure) — say so instead of silence.
        if (sendResult && sendResult.ingestWarning) {
          hostNotice("Email sent. " + sendResult.ingestWarning, "error");
        } else {
          hostNotice("Email sent.", "success");
        }
        if (host.onSent) host.onSent(sendResult);
      } catch (e) {
        if (e.status === 401) { flushDraft(); modal.close(); unauthorized(); return; }
        footErr(e.message);
        send.disabled = false; send.textContent = commResolvers ? "Add & Send" : "Send";
        sendArmed = false;
        // The server is the authority: if it still refuses (contacts changed
        // under us), rebuild the rows for whatever is still unknown.
        if (e.status === 400 && /aren't contacts/.test(e.message || "") && features.addressBook && endpoints.contactLookup) {
          commResolvers = null;
          var still = unknownRecipients(recipientList());
          if (still.length) await buildUnknownPanel(still);
        }
      }
    }
    send.addEventListener("click", doSend);
    // Sent-but-not-recorded: swap the dialog to a retry screen.
    function showWriteBackRetry(writeBack) {
      modal.body().innerHTML = "";
      var note = document.createElement("p"); note.className = "sx__notice is-error";
      note.textContent = writeBack.error ||
        "The message WAS sent, but recording it in the CRM failed.";
      modal.body().appendChild(note);
      modal.foot().innerHTML = "";
      var retry = document.createElement("button"); retry.type = "button";
      retry.className = "cbm-button"; retry.textContent = "Retry recording";
      var close = document.createElement("button"); close.type = "button";
      close.className = "cbm-button cbm-button--secondary"; close.textContent = "Close";
      retry.addEventListener("click", async function () {
        retry.disabled = true; retry.textContent = "Recording…";
        try {
          await api(endpoints.writeBack, { method: "POST", body: writeBack.retryPayload || {} });
          modal.close();
          hostNotice("Email sent and recorded in the CRM.", "success");
        } catch (e) {
          if (e.status === 401) { modal.close(); unauthorized(); return; }
          note.textContent = (e.message || "Still couldn't record it.") + " Try again?";
          retry.disabled = false; retry.textContent = "Retry recording";
        }
      });
      close.addEventListener("click", function () { modal.close(); });
      modal.foot().appendChild(retry); modal.foot().appendChild(close);
    }

    // Keyboard start: the first thing that still needs filling in.
    var focusTarget = null;
    if (!recipientList().length && $("commTo")) focusTarget = $("commTo");
    else if (!$("commSubject").value.trim()) focusTarget = $("commSubject");
    if (focusTarget) focusTarget.focus();
    else {
      // Everything prefilled — write the message. The caret lands at the top
      // (above the signature / quoted original), Gmail-style.
      var be = $("commBody");
      if (be && be._cbmRichText) be._cbmRichText.focus();
      else if (be) be.focus();
    }
    return guard;
  }

  // One labelled field. The message body is the standard rich-text editor
  // (CBMRichText/Jodit) — the send path is HTML-native. A div wrapper, not
  // label: wrapping a whole editor in a <label> re-routes clicks to its first
  // input, and the recipients row carries the Cc/Bcc BUTTONS on its label
  // line (a button inside a <label> becomes the label's implicit control).
  function field(label, id, value, isTextarea, opts) {
    opts = opts || {};
    if (isTextarea && window.CBMRichText) {
      // The dialog is a 90% workspace — give the editor real height (roughly
      // the space left after the recipient/subject/attachment rows).
      var minH = opts.minHeight || Math.max(240, Math.floor(window.innerHeight * 0.32));
      var rich = window.CBMRichText.create(value || "", { minHeight: minH, onInput: opts.onInput });
      if (rich) {
        var rwrap = document.createElement("div"); rwrap.className = "sx__msg-field";
        var rl = document.createElement("span"); rl.className = "sx__msg-label"; rl.textContent = label;
        rich.id = id; rich.classList.add("sx__msg-rich");
        rwrap.appendChild(rl); rwrap.appendChild(rich); return rwrap;
      }
    }
    var wrap = document.createElement("div"); wrap.className = "sx__msg-field";
    var l = document.createElement("label"); l.className = "sx__msg-label"; l.textContent = label;
    l.htmlFor = id;
    var input = isTextarea ? document.createElement("textarea") : document.createElement("input");
    input.id = id; input.className = "sx__msg-input";
    if (isTextarea) { input.rows = 10; } else { input.type = "text"; }
    if (opts.placeholder) input.placeholder = opts.placeholder;
    input.value = value || "";
    if (opts.onInput) input.addEventListener("input", opts.onInput);
    wrap.appendChild(l); wrap.appendChild(input); return wrap;
  }

  window.CBMCompose = {
    open: open,
    field: field,
    parseAddrList: parseAddrList,
    extractEmail: extractEmail,
    fmtBytes: fmtBytes,
    makeCombobox: makeCombobox,
  };
})();
