/* Portal — single sign-on home page: login, then the links your teams allow.
   Staff apps redirect here when unauthenticated (`/?next=/mentoradmin/`);
   after login the portal sends the user straight back to where they were
   headed — but only to a target the API says they're entitled to. */
(function () {
  "use strict";

  var API = "/api/portal";

  function $(id) { return document.getElementById(id); }
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    var resp = await fetch(API + path, opts);
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

  function showLogin() { hide($("homeView")); hide($("forgotView")); show($("loginView")); $("username").focus(); }

  function showForgot() {
    hide($("loginView")); hide($("homeView"));
    hide($("forgotError")); hide($("forgotSuccess"));
    // Carry a username already typed on the login form over to the reset form.
    if (!$("forgotUsername").value) $("forgotUsername").value = $("username").value;
    show($("forgotView"));
    ($("forgotUsername").value ? $("forgotEmail") : $("forgotUsername")).focus();
  }

  // A shortcut chip like the old index page: /mentoradmin, /clientintake, …
  function shortcut(url) {
    var alias = url.replace(/[^a-z0-9]/gi, "").toLowerCase();
    var c = document.createElement("code");
    c.className = "shortcut";
    c.textContent = "/" + alias;
    return c;
  }

  function linkItem(entry, newTab) {
    var li = document.createElement("li");
    var a = document.createElement("a");
    a.href = entry.url;
    a.textContent = entry.title;
    if (newTab) { a.target = "_blank"; a.rel = "noopener"; }
    li.appendChild(a);
    if (entry.url.indexOf("/") === 0) { li.appendChild(document.createTextNode(" ")); li.appendChild(shortcut(entry.url)); }
    return li;
  }

  function fillList(sectionId, listId, entries, newTab) {
    var ul = $(listId); ul.innerHTML = "";
    entries.forEach(function (e) { ul.appendChild(linkItem(e, newTab)); });
    if (entries.length) show($(sectionId)); else hide($(sectionId));
  }

  // Open a workspace window in a STABLE, named browser tab: re-clicking a tile
  // reuses/navigates that tab instead of opening a duplicate (the browser may
  // or may not bring it to the foreground — that part is best-effort).
  function openWindow(url, name) {
    var w = window.open(url, name || "_blank");
    try { if (w) w.focus(); } catch (e) {}
  }

  function tileItem(entry) {
    var a = document.createElement("a");
    a.className = "portal__tile";
    a.href = entry.url;
    a.appendChild(function () { var s = document.createElement("span"); s.className = "portal__tile-title"; s.textContent = entry.title; return s; }());
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      openWindow(entry.url, entry.target || null);
    });
    return a;
  }

  function fillTiles(sectionId, listId, entries) {
    var box = $(listId); box.innerHTML = "";
    entries.forEach(function (e) { box.appendChild(tileItem(e)); });
    if (entries.length) show($(sectionId)); else hide($(sectionId));
  }

  function renderHome(data) {
    hide($("loginView"));
    $("whoName").textContent = data.user.name || data.user.userName;
    fillTiles("directoriesSection", "directoriesList", data.directories || []);
    fillTiles("appsSection", "appsList", data.apps || []);
    fillList("crmSection", "crmList",
      data.crmUrl ? [{ title: "CBM CRM", url: data.crmUrl }] : [], true);
    fillList("docsSection", "docsList",
      data.docsUrl ? [{ title: "CBM Documentation", url: data.docsUrl }] : [], true);
    fillList("formsSection", "formsList", data.forms || [], true);
    show($("homeView"));
  }

  // ?next= deep-link: staff apps send users here to sign in, then we forward
  // them back — but only to a URL the session payload actually offers (an
  // entitled staff app or a public form), never an arbitrary redirect target.
  function nextTarget(data) {
    var next = new URLSearchParams(location.search).get("next");
    if (!next) return null;
    var ok = (data.apps || []).some(function (a) { return a.url === next; })
      || (data.directories || []).some(function (d) { return d.url === next; })
      || (data.forms || []).some(function (f) { return f.url === next; });
    return ok ? next : null;
  }

  function enter(data) {
    var next = nextTarget(data);
    if (next) { location.replace(next); return; }
    renderHome(data);
  }

  $("loginForm").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    hide($("loginError")); $("loginBtn").disabled = true;
    try {
      var data = await api("/login", {
        method: "POST",
        body: JSON.stringify({ username: $("username").value, password: $("password").value }),
      });
      $("password").value = "";
      enter(data);
    } catch (e) {
      var le = $("loginError"); le.textContent = e.message; show(le);
    } finally { $("loginBtn").disabled = false; }
  });

  $("forgotLink").addEventListener("click", function (ev) { ev.preventDefault(); showForgot(); });
  $("backToLogin").addEventListener("click", function (ev) { ev.preventDefault(); showLogin(); });

  $("forgotForm").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    hide($("forgotError")); hide($("forgotSuccess")); $("forgotBtn").disabled = true;
    try {
      var data = await api("/forgot-password", {
        method: "POST",
        body: JSON.stringify({
          username: $("forgotUsername").value,
          emailAddress: $("forgotEmail").value,
        }),
      });
      var fs = $("forgotSuccess"); fs.textContent = data.message; show(fs);
    } catch (e) {
      var fe = $("forgotError"); fe.textContent = e.message; show(fe);
    } finally { $("forgotBtn").disabled = false; }
  });

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) {}
    showLogin();
  });

  (async function init() {
    try { enter(await api("/session")); }
    catch (e) {
      showLogin();
      if (!e || !e.status || e.status >= 500) {
        var le = $("loginError");
        le.textContent = "The server isn't responding right now. Please try again in a moment.";
        show(le);
      }
    }
  })();
})();
