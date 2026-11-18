/* The new home page (HOME_V2, phase 1: the frame). Plan:
   prds/home-page-plan.md § 4 and § 8; look: /shared/panel.css.

   app.js keeps sign-in, the session, the ?next= redirect and the birthday
   overlay, and calls CBMHome.render(data, hooks) instead of drawing today's
   tiles when the session payload says `homeV2`. Today's events rail and
   analytics panel are MOVED into At the chapter by element id, so their code
   in app.js runs unchanged. Nothing today's page offers disappears.

   Sections (§ 4.1, in order): Today, Needs you, My clients, At the chapter,
   then the public pages. The server says which ones this member is entitled
   to (`home.sections`); each frame stands or fails on its own. A member may
   collapse any frame from its header and hide it; the choice is the
   preference `home.sections` = {collapsed: [...], hidden: [...]}. */
(function () {
  "use strict";

  var PREF_URL = "/api/portal/preferences/home.sections";

  //: The frames, in the plan's order. `note` is the one plain line a frame
  //: shows while it has nothing to show yet.
  var FRAMES = [
    { key: "today", title: "Today", pair: true,
      note: "Your sessions for today will show here." },
    { key: "needs", title: "Needs you", pair: true,
      note: "What needs you will show here. Until then, the counts stay on the applications in the bar above." },
    { key: "clients", title: "My clients",
      note: "Your active clients will show here." },
    { key: "chapter", title: "At the chapter",
      note: "Chapter numbers and upcoming events will show here." },
    { key: "pages", title: "Public pages",
      note: "There are no public pages on this deployment." },
  ];

  var state = { prefs: { collapsed: [], hidden: [] }, view: null, hooks: {} };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function org() {
    var m = document.querySelector('meta[name="cbm-org"]');
    return (m && m.content) || "";
  }

  // --- the greeting -----------------------------------------------------------
  function greeting(now) {
    var h = now.getHours();
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  }
  function today(now) {
    return now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  }

  // --- the header bar -----------------------------------------------------------
  function appLink(entry) {
    var a = el("a", "home2__app", entry.title);
    a.href = entry.url;
    a.dataset.url = entry.url;      // the attention badges find their app by this
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      state.hooks.openWindow(entry.url, entry.target || null);
    });
    return a;
  }
  function header(data) {
    var bar = el("header", "home2__bar");
    bar.appendChild(el("span", "home2__org", org()));

    var menu = el("button", "cbm-action--second home2__menu", "Applications");
    menu.type = "button";
    menu.setAttribute("aria-expanded", "false");
    menu.setAttribute("aria-controls", "home2Nav");
    menu.addEventListener("click", function () {
      var open = !bar.classList.contains("home2__bar--open");
      bar.classList.toggle("home2__bar--open", open);
      menu.setAttribute("aria-expanded", open ? "true" : "false");
    });
    bar.appendChild(menu);

    var nav = el("nav", "home2__nav");
    nav.id = "home2Nav";
    nav.setAttribute("aria-label", "Applications");
    (data.apps || []).forEach(function (a) { nav.appendChild(appLink(a)); });
    if ((data.directories || []).length) {
      if ((data.apps || []).length) {
        var sep = el("span", "home2__sep"); sep.setAttribute("aria-hidden", "true");
        nav.appendChild(sep);
      }
      data.directories.forEach(function (d) { nav.appendChild(appLink(d)); });
    }
    if (!nav.children.length) nav.appendChild(el("span", "home2__who", "No applications are open to you yet."));
    bar.appendChild(nav);

    var me = el("div", "home2__me");
    function outLink(title, url) {
      var a = el("a", null, title);
      a.href = url; a.target = "_blank"; a.rel = "noopener";
      me.appendChild(a);
    }
    if (data.crmUrl) outLink("{{abbr}} CRM", data.crmUrl);
    if (data.docsUrl) outLink("{{abbr}} Documentation", data.docsUrl);
    me.appendChild(el("span", "home2__who", data.user.name || data.user.userName));
    var out = el("button", "cbm-action--second", "Sign out");
    out.type = "button";
    out.addEventListener("click", function () { state.hooks.signOut(); });
    me.appendChild(out);
    bar.appendChild(me);
    return bar;
  }

  // --- a frame ----------------------------------------------------------------
  function frame(f) {
    var sec = el("section", "cbm-panel home2__frame");
    sec.dataset.section = f.key;
    var hid = "home2h-" + f.key, bid = "home2b-" + f.key;
    sec.setAttribute("aria-labelledby", hid);

    var head = el("div", "cbm-panel__head");
    var h = el("h2", "cbm-label", f.title); h.id = hid;
    head.appendChild(h);

    var fold = el("button", "cbm-action--quiet");
    fold.type = "button";
    fold.setAttribute("aria-controls", bid);
    fold.appendChild(el("span", "home2__caret", "▾")).setAttribute("aria-hidden", "true");
    fold.appendChild(el("span", "home2__foldword"));
    fold.addEventListener("click", function () {
      toggleList("collapsed", f.key, !sec.classList.contains("cbm-panel--collapsed"));
      apply(); save();
    });
    head.appendChild(fold);

    var hide = el("button", "cbm-action--quiet", "Hide");
    hide.type = "button";
    hide.setAttribute("aria-label", "Hide " + f.title);
    hide.addEventListener("click", function () {
      toggleList("hidden", f.key, true);
      apply(); save();
    });
    head.appendChild(hide);
    sec.appendChild(head);

    var body = el("div", "cbm-panel__body"); body.id = bid;
    sec.appendChild(body);
    sec._body = body; sec._fold = fold; sec._def = f;
    return sec;
  }
  function note(body, text) {
    var p = body.querySelector(".cbm-panel__note");
    if (!p) { p = el("p", "cbm-panel__note"); body.appendChild(p); }
    p.textContent = text;
    return p;
  }

  function fillPages(body, forms) {
    if (!(forms || []).length) { note(body, "There are no public pages on this deployment."); return; }
    var ul = el("ul", "cbm-rows home2__pages");
    forms.forEach(function (p) {
      var li = el("li", "cbm-row");
      var a = el("a", null, p.title);
      a.href = p.url; a.target = "_blank"; a.rel = "noopener";
      li.appendChild(a);
      if (p.url.indexOf("/") === 0) {
        li.appendChild(el("code", "shortcut", "/" + p.url.replace(/[^a-z0-9]/gi, "").toLowerCase()));
      }
      ul.appendChild(li);
    });
    body.appendChild(ul);
  }

  // At the chapter: today's analytics panel and events rail, moved in by id.
  function fillChapter(body) {
    var box = el("div", "home2__chapter");
    ["analyticsSection", "eventsRail"].forEach(function (id) {
      var node = document.getElementById(id);
      if (node) box.appendChild(node);
    });
    body.appendChild(box);
    note(body, FRAMES[3].note);
  }

  // --- collapse and hide --------------------------------------------------------
  function toggleList(which, key, on) {
    var list = state.prefs[which].filter(function (k) { return k !== key; });
    if (on) list.push(key);
    state.prefs[which] = list;
  }
  function clean(v) {
    var keys = FRAMES.map(function (f) { return f.key; });
    function pick(a) {
      return Array.isArray(a) ? a.filter(function (k) { return keys.indexOf(k) >= 0; }) : [];
    }
    return { collapsed: pick(v && v.collapsed), hidden: pick(v && v.hidden) };
  }
  function apply() {
    var view = state.view;
    if (!view) return;
    var hiddenNames = [];
    view.querySelectorAll(".home2__frame").forEach(function (sec) {
      var key = sec.dataset.section;
      var collapsed = state.prefs.collapsed.indexOf(key) >= 0;
      var hidden = state.prefs.hidden.indexOf(key) >= 0;
      sec.classList.toggle("cbm-panel--collapsed", collapsed);
      sec._fold.setAttribute("aria-expanded", collapsed ? "false" : "true");
      sec._fold.querySelector(".home2__foldword").textContent = collapsed ? "Expand" : "Collapse";
      sec._fold.setAttribute("aria-label", (collapsed ? "Expand " : "Collapse ") + sec._def.title);
      sec.hidden = hidden;
      if (hidden) hiddenNames.push(sec._def);
    });
    var bar = view.querySelector(".home2__hidden");
    bar.innerHTML = "";
    if (!hiddenNames.length) { bar.hidden = true; return; }
    bar.appendChild(el("span", null, "Hidden sections:"));
    hiddenNames.forEach(function (f) {
      var b = el("button", "cbm-action--second", "Show " + f.title);
      b.type = "button";
      b.addEventListener("click", function () {
        toggleList("hidden", f.key, false);
        apply(); save();
      });
      bar.appendChild(b);
    });
    bar.hidden = false;
  }
  function message(text) {
    var m = state.view && state.view.querySelector(".home2__msg");
    if (!m) return;
    m.textContent = text || "";
    m.hidden = !text;
  }
  function save() {
    message("");
    fetch(PREF_URL, {
      method: "PUT", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value: state.prefs }),
    }).then(function (r) {
      if (r.ok) return;
      return r.json().catch(function () { return null; }).then(function (d) {
        message("Your choice applies on this screen but was not saved: "
          + ((d && d.detail) || ("the server answered " + r.status)) + ".");
      });
    }).catch(function () {
      message("Your choice applies on this screen but was not saved: the server did not answer.");
    });
  }
  function loadPrefs() {
    return fetch(PREF_URL, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.value) state.prefs = clean(d.value); apply(); })
      .catch(function () { /* the frames show expanded; nothing is lost */ });
  }

  // --- render -------------------------------------------------------------------
  function render(data, hooks) {
    state.hooks = hooks || {};
    // A second sign-in in the same tab: put the moved pieces back first, so
    // the rebuild can move them in again.
    leave();
    var home = data.home || {};
    var allowed = home.sections || [];
    var now = new Date();

    var view = el("div", "home2"); view.id = "home2View";
    view.appendChild(header(data));
    var main = el("div", "home2__main");
    var greet = el("div", "home2__greet");
    greet.appendChild(el("h1", null, greeting(now) + ", " + (home.firstName || data.user.name || "")));
    greet.appendChild(el("p", null, today(now)));
    main.appendChild(greet);

    var pair = el("div", "home2__pair");
    main.appendChild(pair);
    var frames = {};
    FRAMES.forEach(function (f) {
      if (allowed.indexOf(f.key) < 0) return;
      var sec = frame(f);
      frames[f.key] = sec;
      (f.pair ? pair : main).appendChild(sec);
    });
    ["today", "needs", "clients"].forEach(function (k) {
      if (frames[k]) note(frames[k]._body, frames[k]._def.note);
    });
    if (frames.chapter) fillChapter(frames.chapter._body);
    if (frames.pages) fillPages(frames.pages._body, data.forms);

    var msg = el("p", "home2__msg"); msg.setAttribute("role", "status"); msg.hidden = true;
    main.appendChild(msg);
    var hiddenBar = el("p", "home2__hidden"); hiddenBar.hidden = true;
    main.appendChild(hiddenBar);
    view.appendChild(main);

    var host = document.querySelector("main.portal");
    host.parentNode.insertBefore(view, host);
    document.body.classList.add("home2-on");
    state.view = view;
    apply();
    var waiting = loadPrefs();
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(main, waiting);
    return { chapterBody: frames.chapter ? frames.chapter._body : null };
  }

  // The At the chapter frame says its one plain line only when neither piece
  // it holds came up (the analytics panel and the rail self-gate).
  function chapterSettled(body) {
    if (!body) return;
    var shown = ["analyticsSection", "eventsRail"].some(function (id) {
      var n = document.getElementById(id);
      return n && !n.hidden && body.contains(n);
    });
    var p = body.querySelector(".cbm-panel__note");
    if (p) p.hidden = shown;
  }

  // Back to the signed-out page: the moved pieces return to today's page, so
  // a later render (or today's page, if the switch went off) finds them.
  function leave() {
    var view = document.getElementById("home2View");
    var main = document.querySelector("#homeView .portal__main");
    var body = document.getElementById("homeBody");
    var rail = document.getElementById("eventsRail");
    var ana = document.getElementById("analyticsSection");
    if (rail && body && !body.contains(rail)) body.insertBefore(rail, body.firstChild);
    if (ana && main && !main.contains(ana)) main.insertBefore(ana, main.firstChild);
    if (view) view.parentNode.removeChild(view);
    document.body.classList.remove("home2-on");
    state.view = null;
  }

  window.CBMHome = { render: render, chapterSettled: chapterSettled, leave: leave };
})();
