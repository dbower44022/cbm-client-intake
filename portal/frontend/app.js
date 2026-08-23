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

  // --- Show/hide the typed password ---------------------------------------
  // Reveal is opt-in and never sticky: it resets to hidden whenever the form is
  // shown or a sign-in completes, so a revealed password can't be left on
  // screen for the next person at the machine.
  function setPasswordVisible(on) {
    var input = $("password"), btn = $("pwToggle");
    input.type = on ? "text" : "password";
    btn.textContent = on ? "Hide" : "Show";
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.setAttribute("aria-label", on ? "Hide password" : "Show password");
  }

  function showLogin() {
    hide($("homeView")); hide($("forgotView")); show($("loginView"));
    setPasswordVisible(false);
    $("username").focus();
  }

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
    a.dataset.url = entry.url;
    a.appendChild(function () { var s = document.createElement("span"); s.className = "portal__tile-title"; s.textContent = entry.title; return s; }());
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      openWindow(entry.url, entry.target || null);
    });
    return a;
  }

  // Tile count badge — no badge for a zero count, and never a second badge on
  // a tile that already has one.
  function badgeTile(url, n, title) {
    if (!n) return;
    var tile = document.querySelector('.portal__tile[data-url="' + url + '"]');
    if (!tile || tile.querySelector(".portal__tile-badge")) return;
    var b = document.createElement("span");
    b.className = "portal__tile-badge";
    b.textContent = n > 99 ? "99+" : String(n);
    if (title) b.title = title;
    tile.appendChild(b);
  }

  // My Email tile unread badge (§4.2.2): fetched after the tiles render so a
  // slow count never delays the portal. Best-effort — no badge on any failure
  // or a zero count.
  function badgeMyEmailTile() {
    fetch("/myemail/api/unread-count", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var n = d && d.total;
        if (n) badgeTile("/myemail/", n, n + " unread conversation" + (n === 1 ? "" : "s"));
      })
      .catch(function () {});
  }

  // Awaiting-processing badges (Doug, 2026-07-26): per-app counts of new items
  // needing attention — unassigned clients, mentor/partner applications,
  // unmanaged funders, open submissions. The API returns only the apps this
  // user's teams entitle them to, so every badge lands on a rendered tile.
  // Best-effort like the My Email badge.
  function badgeAttentionTiles() {
    fetch(API + "/attention", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        ((d && d.items) || []).forEach(function (it) {
          badgeTile(it.url, it.count, (it.label || "Items awaiting processing") + ": " + it.count);
        });
      })
      .catch(function () {});
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
    badgeMyEmailTile();
    badgeAttentionTiles();
    fillList("crmSection", "crmList",
      data.crmUrl ? [{ title: "CBM CRM", url: data.crmUrl }] : [], true);
    fillList("docsSection", "docsList",
      data.docsUrl ? [{ title: "CBM Documentation", url: data.docsUrl }] : [], true);
    fillList("formsSection", "formsList", data.forms || [], true);
    show($("homeView"));
    if (data.analyticsEnabled) loadPortalDashboard();
  }

  // Analytics dashboard on the home page (Phase D). Self-gating endpoint: a
  // user without analytics access gets available:false and the section stays
  // hidden. Best-effort — never blocks the home render.
  function anFmtWhen(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function loadPortalDashboard() {
    var sec = $("analyticsSection"), grid = $("portalDash");
    if (!grid || typeof CBMCharts === "undefined") return;
    fetch("/analytics/api/portal")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (body) {
        if (!body || !body.available || !(body.panels || []).length) return;
        grid.innerHTML = "";
        body.panels.forEach(function (p) {
          var span = Math.max(3, Math.min(12, p.width || 4));
          var art = document.createElement("article"); art.className = "an-panel"; art.style.setProperty("--span", span);
          var head = document.createElement("header"); head.className = "an-panel__head";
          var h3 = document.createElement("h3"); h3.textContent = p.title; head.appendChild(h3);
          var meta = document.createElement("span"); meta.className = "an-panel__meta";
          var res = p.result || {};
          if (!res.error) meta.textContent = res.cached ? "as of " + anFmtWhen(res.computedAt) : "live";
          head.appendChild(meta);
          var bd = document.createElement("div"); bd.className = "an-panel__body";
          art.appendChild(head); art.appendChild(bd); grid.appendChild(art);
          try { CBMCharts.renderPanel(bd, p, { crmUrl: body.crmUrl }); }
          catch (e) { bd.innerHTML = '<p class="anc-err">Could not render this panel.</p>'; }
        });
        show(sec);
      })
      .catch(function () { /* home renders fine without the dashboard */ });
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

  // Birthdays (payload `birthdays` = {date, own, others}): fireworks over the
  // whole window before the user's screen — "Happy Birthday, <you>!" on your
  // own, otherwise "Wish <colleague> a Happy Birthday!" so the whole of CBM
  // knows. Shown once per day per browser: the portal is re-entered on every
  // refresh and every ?next= sign-in, and nobody wants the overlay each time.
  // The date comes from the server (Cleveland's calendar day), so a traveller's
  // clock can't re-trigger it.
  function birthdaySeenKey(data) {
    return "cbmBirthday:" + ((data.user && data.user.userName) || "");
  }
  function shouldCelebrate(data) {
    var b = data.birthdays;
    if (!b || !b.date || !window.CBMBirthday) return false;
    if (!b.own && !(b.others || []).length) return false;
    try { return localStorage.getItem(birthdaySeenKey(data)) !== b.date; }
    catch (e) { return true; }   // no localStorage: greet rather than stay silent
  }
  function markCelebrated(data) {
    try { localStorage.setItem(birthdaySeenKey(data), data.birthdays.date); } catch (e) {}
  }

  function enter(data) {
    var go = function () {
      var next = nextTarget(data);
      if (next) { location.replace(next); return; }
      renderHome(data);
    };
    if (!shouldCelebrate(data)) { go(); return; }
    markCelebrated(data);
    hide($("loginView"));          // don't leave the sign-in form behind the overlay
    CBMBirthday.celebrate({
      own: data.birthdays.own ? data.birthdays.own.firstName : null,
      others: (data.birthdays.others || []).map(function (p) { return p.name; }),
      onDone: go,
    });
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
      setPasswordVisible(false);
      enter(data);
    } catch (e) {
      var le = $("loginError"); le.textContent = e.message; show(le);
    } finally { $("loginBtn").disabled = false; }
  });

  $("pwToggle").addEventListener("click", function () {
    var input = $("password"), on = input.type === "password";
    // Read the caret BEFORE the type change — changing `type` moves it.
    var at = input.selectionStart;
    setPasswordVisible(on);
    input.focus();
    if (at !== null && at !== undefined) {
      try { input.setSelectionRange(at, at); } catch (e) {}
    }
  });
  setPasswordVisible(false);

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
