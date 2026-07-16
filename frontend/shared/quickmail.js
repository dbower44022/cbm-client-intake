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
 * The session tools do NOT use this widget — their record-scoped compose
 * (contact linking, reply threading) already covers every email they show.
 */
(function () {
  "use strict";

  // "/assignments/…" -> "/assignments/api"; override via CBMQuickMail.apiBase.
  var seg = window.location.pathname.split("/").filter(Boolean)[0] || "";
  var state = {
    apiBase: "/" + seg + "/api",
    mailbox: undefined,      // undefined = not asked yet; null = can't send
    enabled: undefined,
    probe: null,             // in-flight mailbox fetch
  };

  function probeMailbox() {
    if (state.probe) return state.probe;
    state.probe = fetch(state.apiBase + "/mailbox", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { mailbox: null, sendEnabled: false }; })
      .then(function (d) {
        state.mailbox = d.mailbox || null;
        state.enabled = !!d.sendEnabled;
        return state;
      })
      .catch(function () {
        state.mailbox = null; state.enabled = false;
        return state;
      });
    return state.probe;
  }

  function injectStyles() {
    if (document.getElementById("qm-styles")) return;
    var css = "" +
      ".qm-overlay{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;" +
      "align-items:flex-start;justify-content:center;padding:6vh 16px;z-index:1000}" +
      ".qm-box{background:var(--cbm-surface,#fff);color:var(--cbm-text,#1a202c);border-radius:10px;" +
      "box-shadow:0 18px 50px rgba(0,0,0,.28);width:min(640px,100%);padding:20px 22px;" +
      "font-family:var(--cbm-font-body,system-ui,sans-serif)}" +
      ".qm-box h2{margin:0 0 12px;font-size:1.15rem}" +
      ".qm-row{margin:0 0 10px}" +
      ".qm-row label{display:block;font-size:.8rem;font-weight:600;margin-bottom:3px;color:var(--cbm-muted,#4a5568)}" +
      ".qm-row input,.qm-row textarea{width:100%;box-sizing:border-box;padding:7px 9px;" +
      "border:1px solid var(--cbm-border,#cbd5e0);border-radius:6px;font:inherit}" +
      ".qm-row textarea{min-height:9em;resize:vertical}" +
      ".qm-from{font-size:.85rem;color:var(--cbm-muted,#4a5568);margin:0 0 10px}" +
      ".qm-from strong{color:inherit}" +
      ".qm-err{color:var(--cbm-danger,#c53030);font-size:.85rem;margin:6px 0 0}" +
      ".qm-ok{color:#2f855a;font-size:.9rem;margin:6px 0 0}" +
      ".qm-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}" +
      ".qm-actions button{font:inherit;padding:7px 16px;border-radius:6px;cursor:pointer;border:1px solid transparent}" +
      ".qm-send{background:var(--cbm-btn-bg,var(--cbm-blue,#2b6cb0));color:var(--cbm-btn-color,#fff)}" +
      ".qm-send[disabled]{opacity:.6;cursor:default}" +
      ".qm-cancel{background:transparent;border-color:var(--cbm-border,#cbd5e0);color:inherit}";
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

  function openDialog(toAddress) {
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
      var input = document.createElement(multiline ? "textarea" : "input");
      input.id = id; if (!multiline) input.type = "text";
      input.value = value || "";
      row.appendChild(lab); row.appendChild(input);
      box.appendChild(row);
      return input;
    }
    var toInput = field("To", "qmTo", toAddress, false);
    var subjInput = field("Subject", "qmSubject", "", false);
    var bodyInput = field("Message", "qmBody", "", true);

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

    send.addEventListener("click", function () {
      err.hidden = true;
      var to = toInput.value.split(/[,;\s]+/).filter(Boolean);
      if (!to.length) { err.textContent = "Add at least one recipient."; err.hidden = false; return; }
      if (!bodyInput.value.trim()) { err.textContent = "Write a message first."; err.hidden = false; return; }
      send.disabled = true; send.textContent = "Sending…";
      fetch(state.apiBase + "/sendmail", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to: to, subject: subjInput.value.trim(), body: bodyInput.value }),
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok) throw new Error(d.detail || "Couldn't send the message — try again.");
        });
      }).then(function () {
        var ok = document.createElement("p"); ok.className = "qm-ok"; ok.textContent = "Sent.";
        box.insertBefore(ok, actions);
        setTimeout(closeDialog, 900);
      }).catch(function (e) {
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
