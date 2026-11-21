/* The shared sign-in box (Ambassador Program PRD § 3.1, decision AM1).

   A page that finds no valid sign-in draws this box in place, signs the
   member in through the portal's own /api/portal/login, and carries on —
   no trip to the portal and back. The cookie it sets is the one every
   application reads, so signing in here signs the member in everywhere.
   "Forgot your password?" uses the portal's /api/portal/forgot-password,
   which hands the request to the CRM's own recovery email.

     var box = CBMSignIn.mount(container, {
       title: "Sign in", help: "…",
       ids: { username: "username", password: "password" },  // optional
       autofocus: true,                                       // optional
       onSignedIn: function (reply) { … }   // the portal's sign-in reply
     });
     box.reset();          // back to the sign-in form, password cleared and hidden
     box.error("…");       // a message under the password box

   The portal uses it too (since v0.361.0), with its own field ids, so a
   browser's saved password keeps matching. The fields are always named
   "username" and "password" for the same reason. The Show button is out of
   the tab order (Doug, 10-11-26) and never sticky: it resets whenever the
   form is shown or a sign-in completes.

   The box is built with DOM calls, never innerHTML from data. Buttons are
   never disabled for validation: a click with an empty box says what is
   missing. Load busy.js first, as on every page. */
(function () {
  "use strict";

  var API = "/api/portal";

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "class") e.className = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function post(path, body) {
    var opts = { method: "POST", credentials: "same-origin",
                 headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    // Timeout-wrapped where busy.js offers it: a hung request ends in words.
    var send = window.CBMBusy && CBMBusy.fetch ? CBMBusy.fetch(API + path, opts) : fetch(API + path, opts);
    return send.then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) {
          var detail = d && d.detail;
          if (Array.isArray(detail)) detail = "Fill in every box.";
          throw new Error(detail || ("The server answered " + r.status + "."));
        }
        return d;
      });
    });
  }

  function field(id, label, type, autocomplete, name) {
    var wrap = el("div", { "class": "cbm-field" });
    var line = el("div", { "class": "cbm-signin__lab-line" });
    line.appendChild(el("label", { "for": id }, label));
    wrap.appendChild(line);
    var input = el("input", { type: type, id: id, name: name || id, autocomplete: autocomplete });
    wrap.appendChild(input);
    return { wrap: wrap, line: line, input: input };
  }

  function mount(container, opts) {
    opts = opts || {};
    var uid = "cbmsi" + Math.random().toString(36).slice(2, 8);
    container.textContent = "";

    // --- sign in ---
    var box = el("section", { "class": "cbm-signin" });
    box.appendChild(el("h2", null, opts.title || "Sign in"));
    box.appendChild(el("p", { "class": "cbm-help" }, opts.help || "Use your CRM username and password."));
    var form = el("form", { autocomplete: "on", novalidate: "novalidate" });
    var ids = opts.ids || {};
    var user = field(ids.username || uid + "u", "Username", "text", "username", "username");
    var pass = field(ids.password || uid + "p", "Password", "password", "current-password", "password");
    var toggle = el("button", { type: "button", "class": "cbm-signin__link-btn", tabindex: "-1",
                                "aria-pressed": "false", "aria-label": "Show password" }, "Show");
    pass.line.appendChild(toggle);
    var err = el("p", { "class": "cbm-signin__error", role: "alert" });
    err.hidden = true;
    var btn = el("button", { type: "submit", "class": "cbm-button" }, "Sign in");
    var forgotP = el("p", { "class": "cbm-signin__forgot" });
    var forgotA = el("a", { href: "#" }, "Forgot your password?");
    forgotP.appendChild(forgotA);
    [user.wrap, pass.wrap, err, btn, forgotP].forEach(function (n) { form.appendChild(n); });
    box.appendChild(form);

    // --- forgot password ---
    var fbox = el("section", { "class": "cbm-signin" });
    fbox.hidden = true;
    fbox.appendChild(el("h2", null, "Reset your password"));
    fbox.appendChild(el("p", { "class": "cbm-help" },
      "Enter your username and the email address on your account, and we'll email you a link to choose a new password."));
    var fform = el("form", { autocomplete: "on", novalidate: "novalidate" });
    var fuser = field(uid + "fu", "Username", "text", "username", "username");
    var femail = field(uid + "fe", "Email address", "email", "email", "email");
    var ferr = el("p", { "class": "cbm-signin__error", role: "alert" });
    ferr.hidden = true;
    var fok = el("p", { "class": "cbm-signin__ok", role: "status" });
    fok.hidden = true;
    var fbtn = el("button", { type: "submit", "class": "cbm-button" }, "Email me a reset link");
    var backP = el("p", { "class": "cbm-signin__forgot" });
    var backA = el("a", { href: "#" }, "← Back to sign in");
    backP.appendChild(backA);
    [fuser.wrap, femail.wrap, ferr, fok, fbtn, backP].forEach(function (n) { fform.appendChild(n); });
    fbox.appendChild(fform);

    container.appendChild(box);
    container.appendChild(fbox);

    function say(p, text) { p.textContent = text; p.hidden = !text; }

    function reveal(on) {
      pass.input.type = on ? "text" : "password";
      toggle.textContent = on ? "Hide" : "Show";
      toggle.setAttribute("aria-pressed", on ? "true" : "false");
      toggle.setAttribute("aria-label", on ? "Hide password" : "Show password");
    }
    toggle.addEventListener("click", function () {
      // Read the caret BEFORE the type change: changing `type` moves it.
      var at = pass.input.selectionStart;
      reveal(pass.input.type === "password");
      pass.input.focus();
      if (at !== null && at !== undefined) {
        try { pass.input.setSelectionRange(at, at); } catch (e) {}
      }
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      say(err, "");
      if (!user.input.value.trim()) { say(err, "Enter your username."); user.input.focus(); return; }
      if (!pass.input.value) { say(err, "Enter your password."); pass.input.focus(); return; }
      var done = window.CBMBusy ? CBMBusy.start(btn) : function () {};
      post("/login", { username: user.input.value.trim(), password: pass.input.value })
        .then(function (reply) {
          pass.input.value = "";
          reveal(false);
          if (opts.onSignedIn) opts.onSignedIn(reply);
        })
        .catch(function (e) { say(err, e.message); })
        .then(done, done);
    });

    forgotA.addEventListener("click", function (ev) {
      ev.preventDefault();
      box.hidden = true; fbox.hidden = false; say(ferr, ""); say(fok, "");
      if (!fuser.input.value) fuser.input.value = user.input.value;
      (fuser.input.value ? femail.input : fuser.input).focus();
    });
    backA.addEventListener("click", function (ev) {
      ev.preventDefault();
      fbox.hidden = true; box.hidden = false; user.input.focus();
    });

    fform.addEventListener("submit", function (ev) {
      ev.preventDefault();
      say(ferr, ""); say(fok, "");
      if (!fuser.input.value.trim()) { say(ferr, "Enter your username."); return; }
      if (!femail.input.value.trim()) { say(ferr, "Enter the email address on your account."); return; }
      var done = window.CBMBusy ? CBMBusy.start(fbtn) : function () {};
      post("/forgot-password", { username: fuser.input.value.trim(), emailAddress: femail.input.value.trim() })
        .then(function (d) { say(fok, (d && d.message) || "A password reset email is on its way."); })
        .catch(function (e) { say(ferr, e.message); })
        .then(done, done);
    });

    if (opts.autofocus !== false) setTimeout(function () { user.input.focus(); }, 0);
    return {
      el: box,
      reset: function () {
        fbox.hidden = true; box.hidden = false;
        pass.input.value = ""; reveal(false); say(err, "");
        user.input.focus();
      },
      error: function (text) { say(err, text); }
    };
  }

  window.CBMSignIn = { mount: mount };
})();
