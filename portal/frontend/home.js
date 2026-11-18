/* The new home page (HOME_V2; phase 1 the frame, phase 2 Today and My
   clients, phase 3 Needs you). Plan:
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
      note: "Nothing needs you right now." },
    { key: "clients", title: "My clients", link: { title: "Open Client Management", url: "/mentorsessions/", target: "cbm-mentorsessions" },
      note: "Your active clients will show here." },
    { key: "chapter", title: "At the chapter", pair2: true,
      note: "Chapter numbers will show here." },
    { key: "events", title: "Upcoming events", pair2: true,
      note: "There are no upcoming events to show." },
    { key: "pages", title: "Public pages",
      note: "There are no public pages on this deployment." },
  ];

  var state = { prefs: { collapsed: [], hidden: [] }, view: null, hooks: {},
                greet: { line: null, now: null, sessions: null, needs: null } };

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
  // The directories, as one "Directories" menu in the bar (Doug, 11-18-26:
  // four links took too much room). On a narrow screen the menu opens in
  // place inside the Applications list.
  function directoriesMenu(dirs) {
    var wrap = el("div", "home2__dirs");
    var btn = el("button", "home2__app home2__dirbtn");
    btn.type = "button";
    btn.appendChild(document.createTextNode("Directories "));
    btn.appendChild(el("span", "home2__caret", "▾")).setAttribute("aria-hidden", "true");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", "home2Dirs");
    var menu = el("div", "home2__dirmenu");
    menu.id = "home2Dirs";
    menu.hidden = true;
    dirs.forEach(function (d) {
      var a = appLink(d);
      a.addEventListener("click", function () { shut(); });
      menu.appendChild(a);
    });
    function shut() { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); }
    btn.addEventListener("click", function () {
      var open = menu.hidden;
      menu.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (ev) { if (!wrap.contains(ev.target)) shut(); });
    wrap.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !menu.hidden) { shut(); btn.focus(); }
    });
    wrap.appendChild(btn);
    wrap.appendChild(menu);
    return wrap;
  }

  // The member's text size (Doug, 11-18-26, option A): /shared/textsize.js
  // applies it on every application page; this is where it is chosen.
  function textSizeControl() {
    var ts = window.CBMTextSize;
    if (!ts) return null;
    var label = el("label", "home2__textsize");
    label.appendChild(document.createTextNode("Text size "));
    var sel = el("select");
    sel.id = "home2TextSize";
    ts.sizes.forEach(function (o) {
      var opt = el("option", null, o.label);
      opt.value = o.key;
      sel.appendChild(opt);
    });
    sel.value = ts.get();
    sel.addEventListener("change", function () {
      message("");
      ts.set(sel.value).catch(function (e) {
        message("Your text size applies on this screen but was not saved: " + e.message + ".");
      });
    });
    label.appendChild(sel);
    return label;
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
    if ((data.directories || []).length) nav.appendChild(directoriesMenu(data.directories));
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
    var size = textSizeControl();
    if (size) me.appendChild(size);
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

    if (f.link) {
      var go = el("a", "home2__headlink", f.link.title);
      go.href = f.link.url;
      go.addEventListener("click", function (ev) {
        ev.preventDefault();
        state.hooks.openWindow(f.link.url, f.link.target);
      });
      head.appendChild(go);
    }

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

  // --- Today and My clients (phase 2) -------------------------------------------
  // One read as the member (GET /api/portal/home/mentoring: Client
  // Management's own list). CRM stamps are UTC; "today" is the member's own
  // day in this browser, as Client Management's grid decides it.
  var MENTORING_URL = "/api/portal/home/mentoring";
  var CM = "/mentorsessions/";
  //: The status pill's colour for each active status (plan § 5.3; phase 2
  //: question 1: Pending Acceptance waits on the mentor, so amber).
  var PILL = { "Active": "green", "Assigned": "navy",
               "Pending Acceptance": "amber", "On-Hold": "amber" };

  function utc(stamp) {
    if (!stamp) return null;
    var s = String(stamp);
    var d = new Date(s.length <= 10 ? s + "T00:00:00" : s.replace(" ", "T") + "Z");
    return isNaN(d.getTime()) ? null : d;
  }
  function dayKey(d) { return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate(); }
  function timeText(d) { return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }); }
  function dateText(d) { return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }); }
  function whenText(d, now) {
    if (dayKey(d) === dayKey(now)) return "Today " + timeText(d);
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) + ", " + timeText(d);
  }
  function recordUrl(id, tab) {
    return CM + "record/" + encodeURIComponent(id) + (tab ? "?tab=" + tab : "");
  }
  function openRecord(id, tab) {
    state.hooks.openWindow(recordUrl(id, tab), "cbm-rec-mentorsessions-" + id);
  }
  function recordLink(text, id, tab, cls) {
    var a = el("a", cls || null, text);
    a.href = recordUrl(id, tab);
    a.addEventListener("click", function (ev) { ev.preventDefault(); openRecord(id, tab); });
    return a;
  }
  function clearBody(body) { while (body.firstChild) body.removeChild(body.firstChild); }

  function profileLine(data) {
    if (data.profile === "none") {
      return "No mentor profile is linked to your sign-in, so your clients and sessions cannot be shown. "
        + "Ask an administrator to link your profile in Mentor Administration.";
    }
    if (data.profile === "blocked") {
      return "Your sign-in is linked to more than one mentor profile, so your clients and sessions are not shown. "
        + "Ask an administrator to remove the extra links in Mentor Administration.";
    }
    return "";
  }

  function fillToday(body, data, now) {
    clearBody(body);
    var why = profileLine(data);
    if (why) { note(body, why); return 0; }
    var today = [], later = [];
    var weekEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 8);
    (data.sessions || []).forEach(function (s) {
      var d = utc(s.dateStart);
      if (!d) return;
      if (dayKey(d) === dayKey(now)) today.push({ s: s, d: d });
      else if (d > now && d < weekEnd) later.push({ s: s, d: d });
    });
    if (!today.length) note(body, "You have no sessions today.");
    else {
      var ul = el("ul", "cbm-rows home2__today");
      var goldGiven = false;
      today.forEach(function (t) {
        var s = t.s;
        var li = el("li", "cbm-row");
        li.appendChild(el("span", "home2__time", timeText(t.d)));
        var what = el("div", "home2__what");
        what.appendChild(el("div", "cbm-row__name", s.client));
        var sub = [s.name, s.sessionType].filter(function (x) { return x; });
        if (sub.length) what.appendChild(el("div", "home2__sub", sub.join(" · ")));
        li.appendChild(what);
        var acts = el("div", "home2__acts");
        if (s.videoMeetingLink) {
          // The next session to start gets the main button (phase 2 question 3).
          var main = !goldGiven && t.d.getTime() > now.getTime() - 3600 * 1000;
          if (main) goldGiven = true;
          var join = el("a", main ? "cbm-action" : "cbm-action--second", "Join");
          join.href = s.videoMeetingLink; join.target = "_blank"; join.rel = "noopener";
          join.setAttribute("aria-label", "Join the session with " + s.client);
          acts.appendChild(join);
        }
        var open = recordLink("Open", s.recordId, "sessions", "cbm-action--second");
        open.setAttribute("aria-label", "Open " + s.client + " in Client Management");
        acts.appendChild(open);
        li.appendChild(acts);
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
    if (later.length) {
      var p = el("p", "cbm-panel__note home2__later");
      p.appendChild(document.createTextNode("Coming up: "));
      later.forEach(function (t, i) {
        if (i) p.appendChild(document.createTextNode(" · "));
        p.appendChild(document.createTextNode(
          t.d.toLocaleDateString(undefined, { weekday: "short" }) + " " + timeText(t.d) + " "));
        p.appendChild(recordLink(t.s.client, t.s.recordId, "sessions"));
      });
      body.appendChild(p);
    }
    return today.length;
  }

  function nextSession(c, now) {
    var best = null;
    (c.sessions || []).forEach(function (stamp) {
      var d = utc(stamp);
      if (!d || (d < now && dayKey(d) !== dayKey(now))) return;
      if (!best || d < best) best = d;
    });
    return best;
  }
  function cell(tr, content, sortValue) {
    var td = el("td");
    if (typeof content === "string") td.textContent = content; else td.appendChild(content);
    if (sortValue !== undefined) td.dataset.sort = sortValue;
    tr.appendChild(td);
    return td;
  }

  function fillClients(body, data, now) {
    clearBody(body);
    var why = profileLine(data);
    if (why) { note(body, why); return; }
    var clients = data.clients || [];
    if (!clients.length) { note(body, "You have no active clients."); return; }
    var wrap = el("div", "home2__tablewrap");
    var table = el("table", "home2__clients");
    var thead = el("thead"), hr = el("tr");
    [["client", "Client"], ["status", "Status"], ["last", "Last contact"], ["next", "Next session"]]
      .forEach(function (h) { var th = el("th", null, h[1]); th.dataset.col = h[0]; th.scope = "col"; hr.appendChild(th); });
    thead.appendChild(hr); table.appendChild(thead);
    var tbody = el("tbody");
    clients.forEach(function (c) {
      var tr = el("tr");
      var who = el("span");
      who.appendChild(recordLink(c.name, c.id, null, "home2__client"));
      if (c.coMentor) who.appendChild(el("span", "home2__co", "co-mentor"));
      cell(tr, who, c.name);
      cell(tr, el("span", "cbm-pill cbm-tone--" + (PILL[c.status] || "navy"), c.status || "—"), c.status || "");
      var last = utc(c.lastContact);
      cell(tr, last ? dateText(last) : "—", last ? last.toISOString() : "");
      var nxt = nextSession(c, now);
      cell(tr, nxt ? whenText(nxt, now) : "—", nxt ? nxt.toISOString() : "");
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    body.appendChild(wrap);
    if (window.CBMGrid && CBMGrid.enhance) {
      CBMGrid.enhance(table, { key: "home.clients", sort: [{ col: "client", dir: "asc" }] });
    }
  }

  function loadMentoring(frames, greetLine, now) {
    var bodies = ["today", "clients"].filter(function (k) { return frames[k]; })
      .map(function (k) { return frames[k]._body; });
    if (!bodies.length) return;
    var read = fetch(MENTORING_URL, { credentials: "same-origin" }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) throw new Error((d && d.detail) || ("the server answered " + r.status));
        return d;
      });
    });
    bodies.forEach(function (b) { if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(b, read); });
    read.then(function (data) {
      if (frames.today) {
        var n = fillToday(frames.today._body, data, now);
        if (data.profile === "found") { state.greet.sessions = n; greetText(); }
      }
      if (frames.clients) fillClients(frames.clients._body, data, now);
    }).catch(function (e) {
      // A failed read empties only these two sections, with a line; the
      // rest of the page stands (§ 4.1).
      bodies.forEach(function (b) {
        clearBody(b);
        note(b, "Your clients and sessions could not be read just now: " + e.message
          + ". Reload the page to try again.");
      });
    });
  }

  // The greeting's line (§ 4.1): the date, then "2 sessions today", then
  // "5 items need you", each part as its read arrives.
  function greetText() {
    var g = state.greet;
    if (!g.line) return;
    var parts = [today(g.now)];
    if (g.sessions !== null) parts.push(g.sessions + (g.sessions === 1 ? " session" : " sessions") + " today");
    if (g.needs) parts.push(g.needs + (g.needs === 1 ? " item needs you" : " items need you"));
    g.line.textContent = parts.join(" · ");
  }

  // --- Needs you (phase 3) --------------------------------------------------------
  // One read (GET /api/portal/home/needs), sorted by the server: most urgent
  // kind first, then the oldest. Each row's link opens the owning
  // application on the record, in its own named tab (ruling 1). Nothing is
  // acted on here: an item leaves when its application resolves it.
  var NEEDS_URL = "/api/portal/home/needs";

  function needRow(it) {
    var li = el("li", "cbm-row home2__need" + (it.urgent ? " cbm-row--urgent" : ""));
    li.appendChild(el("span", "cbm-kind-chip cbm-tone--" + it.tone, it.chip));
    var what = el("div", "home2__what");
    var a = el("a", "cbm-row__name", it.name);
    a.href = it.url;
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      state.hooks.openWindow(it.url, it.target || null);
    });
    what.appendChild(a);
    what.appendChild(el("div", "home2__sub", it.reason));
    li.appendChild(what);
    return li;
  }

  function fillNeeds(body, data) {
    clearBody(body);
    var items = data.items || [];
    if (!items.length) note(body, "Nothing needs you right now.");
    else {
      var ul = el("ul", "cbm-rows home2__needs");
      items.forEach(function (it) { ul.appendChild(needRow(it)); });
      body.appendChild(ul);
    }
    if ((data.unavailable || []).length) {
      var p = el("p", "cbm-panel__note home2__partial",
        "Some items could not be read just now and are not shown. Reload the page to try again.");
      body.appendChild(p);
    }
    return items.length;
  }

  function loadNeeds(frames) {
    if (!frames.needs) { if (state.hooks.badgesFallback) state.hooks.badgesFallback(); return; }
    var body = frames.needs._body;
    var read = fetch(NEEDS_URL, { credentials: "same-origin" }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) throw new Error((d && d.detail) || ("the server answered " + r.status));
        return d;
      });
    });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(body, read);
    read.then(function (data) {
      state.greet.needs = fillNeeds(body, data);
      greetText();
      // My Email's unread count came from the same inbox run.
      var n = data.unreadTotal;
      if (n && state.hooks.badge) state.hooks.badge("/myemail/", n, n + " unread conversation" + (n === 1 ? "" : "s"));
    }).catch(function (e) {
      // The panel says one line; the rest of the page stands (§ 4.1). The
      // counts go back on the applications in the bar, so none is lost.
      clearBody(body);
      note(body, "What needs you could not be read just now: " + e.message + ". Reload the page to try again.");
      if (state.hooks.badgesFallback) state.hooks.badgesFallback();
    });
  }

  // At the chapter holds today's analytics panel and Upcoming events holds
  // the events rail, each moved in by id (Doug, 11-18-26: separate panels).
  function moveIn(body, id, def) {
    var box = el("div", "home2__chapter");
    var node = document.getElementById(id);
    if (node) box.appendChild(node);
    body.appendChild(box);
    note(body, def.note);
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
    var greetLine = el("p", null, today(now));
    greet.appendChild(greetLine);
    state.greet = { line: greetLine, now: now, sessions: null, needs: null };
    main.appendChild(greet);

    var pair = el("div", "home2__pair");
    main.appendChild(pair);
    var pair2 = el("div", "home2__pair home2__pair--chapter");
    var frames = {};
    FRAMES.forEach(function (f) {
      if (allowed.indexOf(f.key) < 0) return;
      var sec = frame(f);
      frames[f.key] = sec;
      if (f.pair2 && !pair2.parentNode) main.appendChild(pair2);
      (f.pair ? pair : f.pair2 ? pair2 : main).appendChild(sec);
    });
    if (frames.chapter) moveIn(frames.chapter._body, "analyticsSection", frames.chapter._def);
    if (frames.events) moveIn(frames.events._body, "eventsRail", frames.events._def);
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
    loadMentoring(frames, greetLine, now);
    loadNeeds(frames);
    return { chapterBody: frames.chapter ? frames.chapter._body : null,
             eventsBody: frames.events ? frames.events._body : null };
  }

  // At the chapter and Upcoming events each say their one plain line only
  // when the piece they hold did not come up (the analytics panel and the
  // rail self-gate).
  function chapterSettled() {
    [["chapter", "analyticsSection"], ["events", "eventsRail"]].forEach(function (pair) {
      var sec = state.view && state.view.querySelector('.home2__frame[data-section="' + pair[0] + '"]');
      if (!sec) return;
      var n = document.getElementById(pair[1]);
      var shown = !!(n && !n.hidden && sec._body.contains(n));
      var p = sec._body.querySelector(".cbm-panel__note");
      if (p) p.hidden = shown;
    });
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
