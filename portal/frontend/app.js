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

  function showLogin() { hide($("homeView")); show($("loginView")); $("username").focus(); }

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

  function renderHome(data) {
    hide($("loginView"));
    $("whoName").textContent = data.user.name || data.user.userName;
    fillList("appsSection", "appsList", data.apps || [], false);
    fillList("crmSection", "crmList",
      data.crmUrl ? [{ title: "CBM CRM", url: data.crmUrl }] : [], true);
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
