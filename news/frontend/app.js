/* Chapter News — the publishers' page (prds/home-page-plan.md § 6.2;
   phase 5). The list of every item, the editor (CBMRichText with images),
   a live preview drawn by /shared/news.js exactly as a member sees it, and
   Withdraw. Everything is stored in the CRM through /news/api. */
(function () {
  "use strict";

  var API = "/news/api";
  var $ = function (id) { return document.getElementById(id); };
  var state = { teams: [], items: [], current: null, body: null, publishEl: null, expiresEl: null,
                grid: null, saving: false, selectedId: null };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function api(path, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    if (opts.body && !opts.headers) opts.headers = { "Content-Type": "application/json" };
    return fetch(API + path, opts).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (r.status === 401) { window.location.href = "/?next=" + encodeURIComponent("/news/"); throw new Error("Not signed in."); }
        if (!r.ok) {
          var e = new Error((d && d.detail) || ("the server answered " + r.status));
          e.status = r.status;
          throw e;
        }
        return d;
      });
    });
  }

  function fail(text) {
    $("msgText").textContent = text;
    $("msgView").hidden = false;
    $("pageView").hidden = true;
  }
  function say(text, bad) {
    var m = $("editorMsg");
    m.textContent = text || "";
    m.hidden = !text;
    m.classList.toggle("nw__msg--bad", !!bad);
  }

  // --- inline images ------------------------------------------------------------
  // Stored HTML references an image the EspoCRM way (?entryPoint=attachment&amp;id=X)
  // so the CRM binds it to the item; the browser cannot reach the CRM, so the
  // editor shows it through this page's proxy and a save turns it back.
  var STORED_RE = /\?entryPoint=attachment&(?:amp;)?id=([A-Za-z0-9_-]+)/g;
  var PROXY_RE = /\/news\/api\/attachments\/([A-Za-z0-9_-]+)/g;
  function toDisplay(html) { return String(html || "").replace(STORED_RE, API + "/attachments/$1"); }
  function toStored(html) { return String(html || "").replace(PROXY_RE, "?entryPoint=attachment&amp;id=$1"); }

  // A picture larger than this on its longest side, or heavier than SHRINK_BYTES,
  // is redrawn smaller before upload (Doug, 11-20-26: a phone photo was over
  // the 5 MB image limit, refused, and vanished from the editor).
  var MAX_SIDE = 1600, SHRINK_BYTES = 1024 * 1024;

  function shrink(dataUri) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var w = img.naturalWidth, h = img.naturalHeight;
        var bytes = Math.floor((dataUri.length - dataUri.indexOf(",") - 1) * 3 / 4);
        if (Math.max(w, h) <= MAX_SIDE && bytes <= SHRINK_BYTES) { resolve(dataUri); return; }
        var k = Math.min(1, MAX_SIDE / Math.max(w, h));
        var c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(w * k)); c.height = Math.max(1, Math.round(h * k));
        var g = c.getContext("2d");
        g.fillStyle = "#FFFFFF";              // a transparent PNG becomes white-backed JPEG
        g.fillRect(0, 0, c.width, c.height);
        g.drawImage(img, 0, 0, c.width, c.height);
        resolve(c.toDataURL("image/jpeg", 0.85));
      };
      img.onerror = function () {
        reject(new Error("This picture's format cannot be shown in a browser. "
          + "Save it as a JPEG or PNG and add it again."));
      };
      img.src = dataUri;
    });
  }

  function uploadImage(dataUri) {
    if (!/^data:([^;,]+);base64,(.+)$/.test(dataUri || "")) return Promise.resolve(null);
    return shrink(dataUri).then(send);
  }

  function send(dataUri) {
    var m = /^data:([^;,]+);base64,(.+)$/.exec(dataUri || "");
    if (!m) return null;
    return api("/inlineimages", {
      method: "POST",
      body: JSON.stringify({ filename: "news-image", contentType: m[1], dataBase64: m[2] }),
    }).then(function (r) { return API + "/attachments/" + r.id; });
  }

  // --- the grid (stop 1 of prds/news-publisher-redesign-plan.md) ---------------
  // Filter (left) · Search (centre) · Create, Edit, Actions (right), as in the
  // Workspace Directories. A click selects a row; a double-click views it.
  var STATUS_TONE = { "Draft": "navy", "Scheduled": "amber", "Published": "green",
                      "Expired": "purple", "Withdrawn": "red" };
  var SHOWN_STATUSES = ["Draft", "Scheduled", "Published", "Expired", "Withdrawn"];
  var EVERY = "Every member";

  /* The status a publisher reads. The CRM holds Draft, Published and
   * Withdrawn; Scheduled and Expired are worked out from the two dates. */
  function shownStatus(it, now) {
    now = now || new Date();
    var st = it.status || "Draft";
    if (st !== "Published") return st;
    var pub = CBMNews.utc(it.publishAt), exp = CBMNews.utc(it.expiresAt);
    if (pub && pub > now) return "Scheduled";
    if (exp && exp <= now) return "Expired";
    return "Published";
  }

  var filters = { status: ["Draft", "Scheduled", "Published", "Expired"], importance: [],
                  audience: [], from: "", to: "" };
  var FILTERS_DEFAULT = JSON.stringify(filters);
  var FILTER_KEY = "cbm.news.filters";
  try {
    var kept = JSON.parse(window.localStorage.getItem(FILTER_KEY) || "null");
    if (kept && Array.isArray(kept.status)) filters = kept;
  } catch (e) { /* no storage: the defaults stand */ }
  function keepFilters() {
    try { window.localStorage.setItem(FILTER_KEY, JSON.stringify(filters)); } catch (e) { /* fine */ }
  }

  function when(stamp) {
    var d = CBMNews.utc(stamp);
    if (!d) return "—";
    var o = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" };
    if (d.getFullYear() !== new Date().getFullYear()) o.year = "numeric";
    return d.toLocaleString(undefined, o);
  }
  function cell(tr, content, sortValue, col) {
    var td = el("td");
    if (typeof content === "string") td.textContent = content; else td.appendChild(content);
    if (sortValue !== undefined) td.dataset.sort = sortValue;
    if (col) td.dataset.col = col;
    tr.appendChild(td);
  }
  function localDay(stamp) {
    var d = CBMNews.utc(stamp);
    if (!d) return "";
    var m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (day < 10 ? "0" : "") + day;
  }

  function matches(it, q, now) {
    if (filters.status.length && filters.status.indexOf(shownStatus(it, now)) < 0) return false;
    if (filters.importance.length && filters.importance.indexOf(it.importance || "Normal") < 0) return false;
    if (filters.audience.length) {
      var teams = (it.audienceTeams || []).length ? it.audienceTeams : [EVERY];
      if (!teams.some(function (t) { return filters.audience.indexOf(t) >= 0; })) return false;
    }
    var day = localDay(it.publishAt);
    if (filters.from && (!day || day < filters.from)) return false;
    if (filters.to && (!day || day > filters.to)) return false;
    if (q) {
      var hay = ((it.title || "") + " " + (it.summary || "")).toLowerCase();
      if (q.split(/\s+/).some(function (w) { return w && hay.indexOf(w) < 0; })) return false;
    }
    return true;
  }

  function selected() {
    return state.items.filter(function (i) { return i.id === state.selectedId; })[0] || null;
  }
  function select(id) {
    state.selectedId = id;
    // "Select a news item first" has been answered once a row is chosen.
    if (id && $("listMsg").classList.contains("nw__msg--bad") && /^Select a news item/.test($("listMsg").textContent)) listSay("");
    $("listBody").querySelectorAll("tbody tr").forEach(function (tr) {
      var on = tr.dataset.id === id;
      tr.classList.toggle("is-selected", on);
      tr.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  var COLUMNS = [["title", "Title"], ["status", "Status"], ["importance", "Importance"],
                 ["audience", "Audience"], ["publish", "Publish at"], ["expires", "Expires"],
                 ["read", "Read"], ["changed", "Last changed"]];

  function readCell(it) {
    var rc = it.readCount, box = el("span", "nw__read");
    if (!rc) {
      box.textContent = state.readUnavailable && it.status !== "Draft" ? "?" : "—";
      if (box.textContent === "?") box.title = "The read counts could not be worked out just now.";
      return box;
    }
    box.appendChild(el("span", "nw__nowrap", rc.read + " of " + rc.of));
    var bar = el("span", "nw__bar");
    var fillEl = el("span", "nw__barfill");
    fillEl.style.width = (rc.of ? Math.round(100 * rc.read / rc.of) : 0) + "%";
    bar.appendChild(fillEl);
    box.appendChild(bar);
    return box;
  }

  function drawList() {
    var body = $("listBody");
    body.innerHTML = "";
    drawChips();
    var now = new Date();
    var q = ($("search").value || "").trim().toLowerCase();
    var rows = state.items.filter(function (it) { return matches(it, q, now); });
    var total = state.items.length;
    $("listCount").textContent = total
      ? (rows.length === total ? total + (total === 1 ? " item" : " items")
                               : rows.length + " of " + total + " items shown — the filters or the search hide the rest")
      : "";
    if (!total) {
      body.appendChild(el("p", "nw__empty", "No news yet. Choose Create to write the first item."));
      return;
    }
    if (!rows.length) {
      body.appendChild(el("p", "nw__empty", "No item matches the filters and the search. Clear a filter chip, or the search, to see more."));
      return;
    }
    var table = el("table", "nw__table");
    table.setAttribute("aria-label", "News items");
    var hr = el("tr");
    COLUMNS.forEach(function (h) {
      var th = el("th", null, h[1]); th.dataset.col = h[0]; th.scope = "col"; hr.appendChild(th);
    });
    var thead = el("thead"); thead.appendChild(hr); table.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (it) {
      var tr = el("tr");
      tr.dataset.id = it.id;
      tr.tabIndex = 0;
      var shown = shownStatus(it, now);
      var t = el("div", "nw__titlecell");
      t.appendChild(el("span", "nw__title", it.title || "(no title)"));
      if (it.summary) t.appendChild(el("span", "nw__summary", it.summary));
      cell(tr, t, it.title || "", "title");
      cell(tr, el("span", "cbm-pill cbm-tone--" + (STATUS_TONE[shown] || "navy"), shown), shown);
      cell(tr, it.importance || "Normal");
      cell(tr, (it.audienceTeams || []).length ? it.audienceTeams.join(", ") : EVERY);
      cell(tr, el("span", "nw__nowrap", when(it.publishAt)), it.publishAt || "");
      cell(tr, el("span", "nw__nowrap", it.expiresAt ? when(it.expiresAt) : "—"), it.expiresAt || "");
      var rc = it.readCount;
      cell(tr, readCell(it), rc ? String(rc.of ? rc.read / rc.of : 0) : "");
      cell(tr, el("span", "nw__nowrap", when(it.modifiedAt || it.createdAt)), it.modifiedAt || it.createdAt || "");
      tr.addEventListener("click", function () { select(it.id); });
      tr.addEventListener("dblclick", function () { select(it.id); viewItem(it.id); });
      tr.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { select(it.id); viewItem(it.id); }
        else if (ev.key === " ") { ev.preventDefault(); select(it.id); }
        else if (ev.key === "ArrowDown" && tr.nextElementSibling) { tr.nextElementSibling.focus(); select(tr.nextElementSibling.dataset.id); ev.preventDefault(); }
        else if (ev.key === "ArrowUp" && tr.previousElementSibling) { tr.previousElementSibling.focus(); select(tr.previousElementSibling.dataset.id); ev.preventDefault(); }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    body.appendChild(table);
    if (window.CBMGrid && CBMGrid.enhance) {
      CBMGrid.enhance(table, { key: "news.items", sort: [{ col: "publish", dir: "desc" }] });
    }
    if (state.selectedId && !rows.some(function (r) { return r.id === state.selectedId; })) state.selectedId = null;
    select(state.selectedId);
  }

  function loadList() {
    var read = api("/items").then(function (d) {
      state.items = d.items || [];
      state.readUnavailable = !!d.readUnavailable;
      drawList();
    });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading($("listBody"), read);
    return read.catch(function (e) {
      $("listBody").innerHTML = "";
      $("listBody").appendChild(el("p", "nw__empty", "The news could not be read just now: " + e.message + "."));
    });
  }

  // --- the filters ------------------------------------------------------------------
  function optionGroup(title, key, values) {
    var g = el("fieldset", "nw__filtergroup");
    g.appendChild(el("legend", null, title));
    values.forEach(function (v) {
      var lab = el("label", "nw__filteropt");
      var cb = el("input"); cb.type = "checkbox"; cb.value = v;
      cb.checked = filters[key].indexOf(v) >= 0;
      cb.addEventListener("change", function () {
        var at = filters[key].indexOf(v);
        if (cb.checked && at < 0) filters[key].push(v);
        if (!cb.checked && at >= 0) filters[key].splice(at, 1);
        keepFilters(); drawList();
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + v));
      g.appendChild(lab);
    });
    return g;
  }
  function dateGroup() {
    var g = el("fieldset", "nw__filtergroup");
    g.appendChild(el("legend", null, "Publish date"));
    [["from", "From"], ["to", "To"]].forEach(function (p) {
      var lab = el("label", "nw__filterdate");
      lab.appendChild(el("span", null, p[1]));
      var inp = el("input"); inp.type = "date"; inp.value = filters[p[0]] || "";
      inp.addEventListener("change", function () { filters[p[0]] = inp.value; keepFilters(); drawList(); });
      lab.appendChild(inp);
      g.appendChild(lab);
    });
    return g;
  }
  function drawFilterPanel() {
    var p = $("filterPanel");
    p.innerHTML = "";
    p.appendChild(optionGroup("Status", "status", SHOWN_STATUSES));
    p.appendChild(optionGroup("Importance", "importance", ["Normal", "Pinned", "Must acknowledge"]));
    p.appendChild(optionGroup("Audience", "audience", [EVERY].concat(state.teams)));
    p.appendChild(dateGroup());
    var acts = el("div", "nw__filteractions");
    var reset = el("button", "cbm-action--quiet", "Reset filters");
    reset.type = "button";
    reset.addEventListener("click", function () {
      filters = JSON.parse(FILTERS_DEFAULT); keepFilters(); drawFilterPanel(); drawList();
    });
    var close = el("button", "cbm-action--second", "Done");
    close.type = "button";
    close.addEventListener("click", function () { toggleFilters(false); });
    acts.appendChild(reset); acts.appendChild(close);
    p.appendChild(acts);
  }
  function toggleFilters(open) {
    var p = $("filterPanel");
    if (open === undefined) open = p.hidden;
    if (open) drawFilterPanel();
    p.hidden = !open;
    $("filterBtn").setAttribute("aria-expanded", open ? "true" : "false");
  }
  function chip(text, clear) {
    var c = el("span", "nw__chip", text + " ");
    var x = el("button", null, "×");
    x.type = "button";
    x.setAttribute("aria-label", "Remove the filter: " + text);
    x.addEventListener("click", function () {
      clear(); keepFilters(); if (!$("filterPanel").hidden) drawFilterPanel(); drawList();
    });
    c.appendChild(x);
    return c;
  }
  function drawChips() {
    var box = $("filterChips");
    box.innerHTML = "";
    var allButWithdrawn = JSON.stringify(filters.status.slice().sort()) ===
      JSON.stringify(["Draft", "Expired", "Published", "Scheduled"]);
    if (filters.status.length && !allButWithdrawn && filters.status.length < SHOWN_STATUSES.length) {
      box.appendChild(chip("Status: " + filters.status.join(", "), function () { filters.status = []; }));
    } else if (allButWithdrawn) {
      box.appendChild(chip("Withdrawn hidden", function () { filters.status = []; }));
    }
    if (filters.importance.length) box.appendChild(chip("Importance: " + filters.importance.join(", "), function () { filters.importance = []; }));
    if (filters.audience.length) box.appendChild(chip("Audience: " + filters.audience.join(", "), function () { filters.audience = []; }));
    if (filters.from || filters.to) {
      box.appendChild(chip("Published " + (filters.from ? "from " + filters.from : "") +
        (filters.from && filters.to ? " " : "") + (filters.to ? "to " + filters.to : ""),
        function () { filters.from = ""; filters.to = ""; }));
    }
  }

  // --- the Actions menu -------------------------------------------------------------
  /* The grid's Actions menu, or the View screen's (``prefix`` "view"). */
  function menu(open, prefix) {
    prefix = prefix || "";
    var m = $(prefix ? prefix + "ActionsMenu" : "actionsMenu");
    var btn = $(prefix ? prefix + "ActionsBtn" : "actionsBtn");
    if (open === undefined) open = m.hidden;
    m.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { var first = m.querySelector("button"); if (first) first.focus(); }
  }
  function closeMenus() { menu(false); menu(false, "view"); }
  function wireMenu(prefix) {
    var m = $(prefix ? prefix + "ActionsMenu" : "actionsMenu");
    var btn = $(prefix ? prefix + "ActionsBtn" : "actionsBtn");
    btn.addEventListener("click", function (ev) { ev.stopPropagation(); menu(undefined, prefix); });
    m.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-act]");
      if (b) act(b.dataset.act, b);
    });
    m.addEventListener("keydown", function (ev) {
      var items = Array.prototype.slice.call(m.querySelectorAll("button"));
      var at = items.indexOf(document.activeElement);
      if (ev.key === "Escape") { ev.stopPropagation(); menu(false, prefix); btn.focus(); }
      else if (ev.key === "ArrowDown") { ev.preventDefault(); items[(at + 1) % items.length].focus(); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); items[(at - 1 + items.length) % items.length].focus(); }
    });
  }

  /* After an action, the View screen (when it is showing) is drawn again. */
  function afterAction(saved) {
    return loadList().then(function () {
      select(saved.id);
      if (!$("workView").hidden) return viewItem(saved.id, true);
    });
  }

  function needSelection(what) {
    var it = selected();
    if (!it) listSay("Select a news item in the grid first, then choose " + what + ".", true);
    return it;
  }

  /* Change one item's status from the grid: the item is read in full and
   * saved back with only the status changed. */
  function setStatus(it, status, btn) {
    var done = window.CBMBusy && CBMBusy.start ? CBMBusy.start(btn) : function () {};
    api("/items/" + encodeURIComponent(it.id)).then(function (full) {
      var d = {
        title: full.title, summary: full.summary, body: full.body, importance: full.importance,
        audienceTeams: full.audienceTeams || [], publishAt: full.publishAt || null,
        expiresAt: full.expiresAt || null, ctaLabel: full.ctaLabel, ctaUrl: full.ctaUrl, status: status,
      };
      return api("/items/" + encodeURIComponent(it.id), { method: "PUT", body: JSON.stringify(d) });
    }).then(function (saved) {
      done();
      return afterAction(saved).then(function () {
        listSay(status === "Published"
          ? "“" + saved.title + "” is published" + (shownStatus(saved) === "Scheduled"
              ? ", and goes live on " + when(saved.publishAt) + "." : ". Members see it on their home page.")
          : "“" + saved.title + "” is back to a draft. Members no longer see it.");
      });
    }).catch(function (e) { done(); listSay("Not changed: " + e.message, true); });
  }

  function confirmWithdraw(it) {
    $("confirmText").textContent = "Withdraw “" + (it.title || "(no title)") + "”? It disappears for every member at once, past news included.";
    $("confirmBar").hidden = false;
    $("confirmNo").focus();
    $("confirmYes").onclick = function () {
      var done = window.CBMBusy && CBMBusy.start ? CBMBusy.start($("confirmYes")) : function () {};
      api("/items/" + encodeURIComponent(it.id) + "/withdraw", { method: "POST" }).then(function (saved) {
        done(); $("confirmBar").hidden = true;
        return afterAction(saved).then(function () {
          listSay("“" + saved.title + "” is withdrawn. It has gone from every member's home page and past news."
            + ($("workView").hidden && filters.status.indexOf("Withdrawn") < 0 ? " The Status filter hides withdrawn items." : ""));
        });
      }).catch(function (e) { done(); listSay("Not withdrawn: " + e.message, true); });
    };
  }

  function act(name, btn) {
    closeMenus();
    listSay("");
    var it;
    if (name === "digest") { testDigest(btn || $("actionsBtn")); return; }
    if (name === "view") { if ((it = needSelection("View"))) viewItem(it.id); return; }
    if (name === "duplicate") { if ((it = needSelection("Duplicate"))) duplicate(it.id); return; }
    if (name === "publish") {
      if (!(it = needSelection("Publish"))) return;
      if (it.status === "Published") { listSay("“" + it.title + "” is already published.", true); return; }
      if (it.status === "Withdrawn") { listSay("A withdrawn item cannot be published again. Duplicate it as a new draft and publish that.", true); return; }
      setStatus(it, "Published", $("actionsBtn"));
      return;
    }
    if (name === "draft") {
      if (!(it = needSelection("Move back to draft"))) return;
      if (it.status !== "Published") { listSay("Only a published item can move back to a draft; “" + it.title + "” is " + shownStatus(it).toLowerCase() + ".", true); return; }
      setStatus(it, "Draft", $("actionsBtn"));
      return;
    }
    if (name === "withdraw") {
      if (!(it = needSelection("Withdraw"))) return;
      if (it.status === "Withdrawn") { listSay("“" + it.title + "” is already withdrawn.", true); return; }
      confirmWithdraw(it);
    }
  }

  // --- the create and edit pop-up (stop 2; ruling R1) ----------------------------
  // One form for Create, Edit and Duplicate. A save closes it and returns to
  // the grid with the row selected; closing with changes asks first.
  function drawTeams(chosen) {
    var box = $("fTeams");
    box.innerHTML = "";
    var every = el("button", "nw__teamchip", EVERY);
    every.type = "button"; every.dataset.every = "1";
    box.appendChild(every);
    state.teams.forEach(function (t) {
      var b = el("button", "nw__teamchip", t);
      b.type = "button"; b.dataset.team = t;
      box.appendChild(b);
    });
    setTeams(chosen);
    if (!state.teams.length) {
      box.appendChild(el("p", "nw__hint", "The CRM offers no teams, so the item goes to every member."));
    }
  }
  function setTeams(chosen) {
    $("fTeams").querySelectorAll(".nw__teamchip").forEach(function (b) {
      var on = b.dataset.every ? !chosen.length : chosen.indexOf(b.dataset.team) >= 0;
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function chosenTeams() {
    var out = [];
    $("fTeams").querySelectorAll(".nw__teamchip[data-team][aria-pressed='true']").forEach(function (b) {
      out.push(b.dataset.team);
    });
    return out;
  }
  function onTeamClick(ev) {
    var b = ev.target.closest(".nw__teamchip");
    if (!b) return;
    if (b.dataset.every) { setTeams([]); }
    else {
      var now = chosenTeams(), at = now.indexOf(b.dataset.team);
      if (at >= 0) now.splice(at, 1); else now.push(b.dataset.team);
      setTeams(now);
    }
    preview();
  }

  function dateControl(hostId, value) {
    var host = $(hostId);
    host.innerHTML = "";
    var c = CBMDateTime.create({ value: value || null });
    host.appendChild(c);
    return c;
  }

  function counts() {
    $("titleCount").textContent = $("fTitle").value.length + " of 150";
    $("summaryCount").textContent = $("fSummary").value.length + " of 500";
  }

  /* ``copy`` fills the form from an item without opening it: Duplicate. */
  function fill(item, copy) {
    state.current = copy ? null : item;
    var it = item || {};
    var st = state.current ? (it.status || "Draft") : "Draft";
    $("editorTitle").textContent = copy ? "Duplicate news item" : state.current ? "Edit news item" : "New news item";
    var shown = state.current ? shownStatus(it) : "Draft";
    $("editorStatus").textContent = copy ? "New draft" : shown;
    $("editorStatus").className = "cbm-pill cbm-tone--" + (STATUS_TONE[shown] || "navy");
    $("fTitle").value = it.title || "";
    $("fSummary").value = it.summary || "";
    var imp = it.importance || "Normal";
    $("fImportance").querySelectorAll("input").forEach(function (r) { r.checked = r.value === imp; });
    $("fCtaLabel").value = it.ctaLabel || "";
    $("fCtaUrl").value = it.ctaUrl || "";
    drawTeams(it.audienceTeams || []);
    state.publishEl = dateControl("fPublish", it.publishAt);
    state.expiresEl = dateControl("fExpires", it.expiresAt);
    var host = $("fBody");
    host.innerHTML = "";
    var editor = window.CBMRichText && CBMRichText.create(toDisplay(it.body), {
      onInput: preview, uploadImage: uploadImage,
    });
    if (editor) { host.appendChild(editor); state.body = editor; }
    else {
      var ta = el("textarea"); ta.rows = 8; ta.value = it.body || "";
      ta.addEventListener("input", preview);
      host.appendChild(ta); state.body = ta;
    }
    $("publishBtn").textContent = st === "Published" ? "Save changes" : "Publish";
    $("draftBtn").textContent = st === "Published" ? "Move back to draft" : "Save draft";
    say("");
    counts();
    previewTab(false);
    preview();
  }

  function bodyValue() {
    var b = state.body;
    if (!b) return "";
    return b._cbmRichText ? b._cbmRichText.getValue() : b.value;
  }

  function read() {
    var imp = $("fImportance").querySelector("input:checked");
    return {
      title: $("fTitle").value.trim(),
      summary: $("fSummary").value.trim(),
      body: toStored(bodyValue()),
      importance: imp ? imp.value : "Normal",
      audienceTeams: chosenTeams(),
      publishAt: state.publishEl ? CBMDateTime.read(state.publishEl) : null,
      expiresAt: state.expiresEl ? CBMDateTime.read(state.expiresEl) : null,
      ctaLabel: $("fCtaLabel").value.trim(),
      ctaUrl: $("fCtaUrl").value.trim(),
    };
  }

  // The preview is the member's own drawing (CBMNews.item), closed or opened.
  function memberDrawing(d, open) {
    var it = {
      id: "preview", title: d.title || "(no title yet)", summary: d.summary,
      body: toDisplay(d.body), importance: d.importance,
      publishAt: d.publishAt || null,
      cta: d.ctaLabel && d.ctaUrl ? { label: d.ctaLabel, url: d.ctaUrl } : null,
    };
    var node = CBMNews.item(it, open ? { open: true } : {});
    if (open) node.querySelector(".news-item__body").id = "news-body-preview-open";
    return node;
  }
  function preview() {
    if ($("editorOverlay").hidden) return;
    var d = read();
    counts();
    // A "not saved yet" message goes once what it named has been put right.
    if ($("editorMsg").classList.contains("nw__msg--bad") && /^Not saved yet/.test($("editorMsg").textContent)
        && !problems(d).length) say("");
    $("previewClosed").innerHTML = ""; $("previewOpen").innerHTML = "";
    $("previewClosed").appendChild(memberDrawing(d, false));
    $("previewOpen").appendChild(memberDrawing(d, true));
  }
  function previewTab(open) {
    $("tabClosed").setAttribute("aria-selected", open ? "false" : "true");
    $("tabOpen").setAttribute("aria-selected", open ? "true" : "false");
    $("previewClosed").hidden = open;
    $("previewOpen").hidden = !open;
  }

  // --- opening and closing the pop-up ----------------------------------------------
  var lastFocus = null;
  function openEditor(item, copy) {
    lastFocus = document.activeElement;
    $("discardBar").hidden = true;
    $("editorOverlay").hidden = false;
    document.body.classList.add("nw--modal");
    fill(item, copy);
    state.snapshot = JSON.stringify(read());
    $("fTitle").focus();
  }
  function dirty() { return state.snapshot !== JSON.stringify(read()); }
  function closeEditor(force) {
    if ($("editorOverlay").hidden) return;
    if (!force && dirty()) {
      $("discardBar").hidden = false;
      $("discardNo").focus();
      return;
    }
    $("editorOverlay").hidden = true;
    document.body.classList.remove("nw--modal");
    state.body = null;
    $("fBody").innerHTML = "";
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  // Keep the keyboard inside the pop-up while it is open.
  function trapFocus(ev) {
    if (ev.key === "Escape") {
      if (document.querySelector(".jodit-popup, .jodit-dialog_active-true")) return; // the editor's own pop-up first
      ev.preventDefault(); closeEditor(false); return;
    }
    if (ev.key !== "Tab") return;
    var f = Array.prototype.filter.call(
      $("editor").querySelectorAll("button, [href], input, select, textarea, [contenteditable='true'], [tabindex]:not([tabindex='-1'])"),
      function (n) { return !n.disabled && n.offsetParent !== null; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  }

  /* Every missing or mismatched input is named at once, with focus on the first. */
  function problems(d) {
    var out = [];
    if (!d.title) out.push(["fTitle", "a title"]);
    if (d.ctaLabel && !d.ctaUrl) out.push(["fCtaUrl", "the button's address (it has text but nowhere to go)"]);
    if (d.ctaUrl && !d.ctaLabel) out.push(["fCtaLabel", "the button's text (it has an address but no words)"]);
    if (d.ctaUrl && !/^(https?:\/\/|\/(?!\/))/.test(d.ctaUrl)) out.push(["fCtaUrl", "a button address that starts with https://, http:// or /"]);
    if (d.publishAt && d.expiresAt && d.expiresAt <= d.publishAt) out.push(["fExpires", "an expiry time after the publish time"]);
    return out;
  }

  function save(status, btn) {
    if (state.saving) return;
    var d = read();
    var miss = problems(d);
    if (miss.length) {
      say("Not saved yet. It needs " + miss.map(function (m) { return m[1]; }).join("; and ") + ".", true);
      var f = $(miss[0][0]);
      var target = f && f.tagName !== "INPUT" ? (f.querySelector("input") || f) : f;
      if (target && target.focus) target.focus();
      return;
    }
    d.status = status;
    state.saving = true;
    var done = window.CBMBusy && CBMBusy.start ? CBMBusy.start(btn) : function () {};
    var cur = state.current;
    var call = cur ? api("/items/" + encodeURIComponent(cur.id), { method: "PUT", body: JSON.stringify(d) })
                   : api("/items", { method: "POST", body: JSON.stringify(d) });
    call.then(function (saved) {
      done(); state.saving = false;
      closeEditor(true);
      showGrid();
      return loadList().then(function () {
        select(saved.id);
        var shown = shownStatus(saved);
        var text = "“" + saved.title + "” " + (shown === "Scheduled"
          ? "is published, and goes live on " + when(saved.publishAt) + "."
          : status === "Published" ? (cur && cur.status === "Published" ? "is saved. Members see the change at once."
                                                                       : "is published. Members see it on their home page.")
          : "is saved as a draft. Members do not see it.");
        if (state.selectedId !== saved.id) text += " The filters or the search hide it in the grid.";
        listSay(text);
      });
    }).catch(function (e) {
      done(); state.saving = false;
      say("Not saved: " + e.message, true);
    });
  }

  function testAddress() {
    var u = $("fCtaUrl").value.trim();
    if (!u) { say("Type the button's address first, then open it.", true); $("fCtaUrl").focus(); return; }
    if (!/^(https?:\/\/|\/(?!\/))/.test(u)) { say("The address must start with https://, http:// or /.", true); $("fCtaUrl").focus(); return; }
    window.open(u, "_blank", "noopener");
  }

  // --- the read report (phase 6) -----------------------------------------------
  // § 6.2: how many of the audience have read the item, out of how many, and
  // who has not; for an item to acknowledge, who acknowledged and when.
  function people(title, rows, withWhen) {
    var box = el("div", "nw__people");
    box.appendChild(el("h3", "cbm-label nw__peoplehead", title + " (" + rows.length + ")"));
    if (!rows.length) { box.appendChild(el("p", "nw__hint", "No one.")); return box; }
    var ul = el("ul", "nw__names");
    rows.forEach(function (r) {
      var li = el("li", null, r.name);
      if (withWhen && r.at) li.appendChild(el("span", "nw__when", " " + when(r.at)));
      ul.appendChild(li);
    });
    box.appendChild(ul);
    return box;
  }

  function loadReport() {
    var cur = state.viewing, body = $("reportBody");
    body.innerHTML = "";
    if (!cur) return;
    if (cur.status === "Draft") {
      body.appendChild(el("p", "nw__readnote", "A draft is seen by no member, so nobody has read it yet. "
        + "Who has read it shows here once it is published."));
      return;
    }
    var read = api("/items/" + encodeURIComponent(cur.id) + "/report");
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(body, read);
    read.then(function (r) {
      if (state.viewing !== cur) return;
      body.innerHTML = "";
      var pct = r.of ? Math.round(100 * r.read / r.of) : 0;
      var stat = el("div", "nw__readstat");
      var big = el("p", "nw__readbig");
      big.appendChild(el("strong", null, r.read + " of " + r.of));
      big.appendChild(document.createTextNode(" " + (r.mustAcknowledge ? "have read or acknowledged it" : "have read it")
        + (r.of ? " (" + pct + "%)" : "")));
      stat.appendChild(big);
      var bar = el("span", "nw__bar nw__bar--big");
      var fillEl = el("span", "nw__barfill");
      fillEl.style.width = pct + "%";
      bar.appendChild(fillEl);
      stat.appendChild(bar);
      if (cur.status === "Withdrawn") stat.appendChild(el("p", "nw__readnote", "Withdrawn: members no longer see it. The counts stop where they were."));
      body.appendChild(stat);
      var cols = el("div", "nw__peoplecols");
      if (r.mustAcknowledge) cols.appendChild(people("Acknowledged", r.acknowledged, true));
      cols.appendChild(people(r.mustAcknowledge ? "Not acknowledged yet" : "Not read yet", r.notRead, false));
      if (r.dismissed.length || !r.mustAcknowledge) cols.appendChild(people("Dismissed", r.dismissed, true));
      body.appendChild(cols);
    }).catch(function (e) {
      body.innerHTML = "";
      body.appendChild(el("p", "cbm-panel__note", "Who has read it could not be read just now: " + e.message + "."));
    });
  }


  // --- Send me a test digest (phase 7) --------------------------------------------
  function listSay(text, bad) {
    var m = $("listMsg");
    m.textContent = text || ""; m.hidden = !text;
    m.classList.toggle("nw__msg--bad", !!bad);
  }
  function testDigest(btn) {
    var done = window.CBMBusy && CBMBusy.start ? CBMBusy.start(btn) : function () {};
    listSay("");
    api("/digest/test", { method: "POST" }).then(function (r) {
      done();
      listSay("Sent to " + r.to + ": " + r.items + (r.items === 1 ? " item" : " items")
        + (r.unread ? "." : " (you have nothing unread, so it lists every live item you may see)."));
    }).catch(function (e) { done(); listSay("Not sent: " + e.message, true); });
  }

  // --- switching between the grid and the View screen --------------------------------
  // Stop 3 replaces the View screen with the full reading screen.
  // The grid's message and confirm bar follow the screen that is showing.
  function showWork() {
    $("confirmBar").hidden = true;
    $("viewMsgSlot").appendChild($("msgBox"));
    $("gridView").hidden = true;
    $("workView").hidden = false;
    window.scrollTo(0, 0);
  }
  function showGrid() {
    $("confirmBar").hidden = true;
    $("gridMsgSlot").appendChild($("msgBox"));
    closeMenus();
    $("workView").hidden = true;
    $("gridView").hidden = false;
    state.viewing = null;
    document.title = state.pageTitle || document.title;
    if (window.location.hash) history.replaceState(null, "", window.location.pathname);
  }

  function fetchItem(id) {
    var read = api("/items/" + encodeURIComponent(id));
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading($("gridView").hidden ? $("workView") : $("listBody"), read);
    read.catch(function (e) { listSay("That item could not be opened: " + e.message, true); });
    return read;
  }
  function fact(dl, term, value) {
    var wrap = el("div", "nw__fact");
    wrap.appendChild(el("dt", null, term));
    var dd = el("dd");
    if (typeof value === "string") dd.textContent = value; else dd.appendChild(value);
    wrap.appendChild(dd);
    dl.appendChild(wrap);
  }
  function byWhen(name, stamp) {
    return when(stamp) + (name ? " by " + name : "");
  }
  function drawView(it) {
    var shown = shownStatus(it);
    $("viewTitle").textContent = it.title || "(no title)";
    var pills = $("viewPills");
    pills.innerHTML = "";
    pills.appendChild(el("span", "cbm-pill cbm-tone--" + (STATUS_TONE[shown] || "navy"), shown));
    if (it.importance && it.importance !== "Normal") pills.appendChild(el("span", "cbm-pill cbm-tone--amber", it.importance));
    $("viewSummary").textContent = it.summary || "";
    $("viewSummary").hidden = !it.summary;
    var dl = $("viewFacts");
    dl.innerHTML = "";
    fact(dl, "Audience", (it.audienceTeams || []).length ? it.audienceTeams.join(", ") : EVERY);
    fact(dl, shown === "Scheduled" ? "Goes live" : "Published",
         it.status === "Draft" ? (it.publishAt ? "Set for " + when(it.publishAt) + ", once published" : "When it is published")
                               : when(it.publishAt));
    fact(dl, shown === "Expired" ? "Expired" : "Expires", it.expiresAt ? when(it.expiresAt) : "Never");
    if (it.ctaLabel && it.ctaUrl) {
      var a = el("a", null, it.ctaLabel);
      a.href = it.ctaUrl; a.target = "_blank"; a.rel = "noopener";
      var box = el("span");
      box.appendChild(a);
      box.appendChild(el("span", "nw__factnote", " " + it.ctaUrl));
      fact(dl, "Button", box);
    } else {
      fact(dl, "Button", "None");
    }
    fact(dl, "Created", byWhen(it.createdByName, it.createdAt));
    fact(dl, "Last changed", byWhen(it.modifiedByName, it.modifiedAt || it.createdAt));
    var ul = $("viewOpen");
    ul.innerHTML = "";
    ul.appendChild(memberDrawing(it, true));
    document.title = (it.title || "News item") + " — Chapter News";
  }
  /* ``quiet`` keeps the message on screen (a redraw after an action). */
  function viewItem(id, quiet) {
    return fetchItem(id).then(function (it) {
      state.viewing = it;
      select(id);
      if (!quiet) listSay("");
      drawView(it);
      showWork();
      history.replaceState(null, "", "#" + id);
      loadReport();
      if (!quiet) $("backBtn").focus();
    });
  }
  function editItem(id) {
    return fetchItem(id).then(function (it) {
      if (it.status === "Withdrawn") {
        var text = "\u201c" + it.title + "\u201d is withdrawn, so it cannot be edited. Choose Actions, then Duplicate as a new draft, to reuse it.";
        if ($("gridView").hidden) showGrid();
        listSay(text, true);
        return;
      }
      openEditor(it, false);
    });
  }
  function duplicate(id) {
    return fetchItem(id).then(function (it) {
      openEditor(Object.assign({}, it, { title: "Copy of " + (it.title || ""), publishAt: null, expiresAt: null }), true);
      state.snapshot = null;   // a copy is unsaved from the start
      say("A copy, not saved yet. Change what needs changing, then save it.");
    });
  }

  function boot() {
    $("logoutBtn").addEventListener("click", function () {
      api("/logout", { method: "POST" }).finally(function () { window.location.href = "/"; });
    });
    api("/session").then(function (s) {
      $("whoName").textContent = s.name || "";
      if (!s.built) {
        fail("The CRM does not have the Chapter News record types yet, so there is nothing to publish to. "
          + "Ask whoever looks after the CRM to apply cchapternews-entities-crm-handoff.md.");
        return;
      }
      state.teams = s.teams || [];
      state.pageTitle = document.title;
      $("pageView").hidden = false;
      ["fTitle", "fSummary", "fImportance", "fCtaLabel", "fCtaUrl", "fPublish", "fExpires"].forEach(function (id) {
        $(id).addEventListener("input", preview);
        $(id).addEventListener("change", preview);
      });
      $("fTeams").addEventListener("click", onTeamClick);
      $("tabClosed").addEventListener("click", function () { previewTab(false); });
      $("tabOpen").addEventListener("click", function () { previewTab(true); });
      $("editorClose").addEventListener("click", function () { closeEditor(false); });
      $("cancelBtn").addEventListener("click", function () { closeEditor(false); });
      $("discardYes").addEventListener("click", function () { closeEditor(true); });
      $("discardNo").addEventListener("click", function () { $("discardBar").hidden = true; $("fTitle").focus(); });
      $("ctaTest").addEventListener("click", testAddress);
      $("editorOverlay").addEventListener("keydown", trapFocus);
      $("createBtn").addEventListener("click", function () { listSay(""); openEditor(null, false); });
      $("viewEditBtn").addEventListener("click", function () {
        if (state.viewing) { var id = state.viewing.id; editItem(id); }
      });
      $("editBtn").addEventListener("click", function () {
        listSay("");
        var it = needSelection("Edit");
        if (it) editItem(it.id);
      });
      $("backBtn").addEventListener("click", function () {
        showGrid();
        var row = $("listBody").querySelector("tr.is-selected");
        if (row) row.focus();
      });
      $("filterBtn").addEventListener("click", function () { toggleFilters(); });
      var searchTimer = null;
      $("search").addEventListener("input", function () {
        clearTimeout(searchTimer); searchTimer = setTimeout(drawList, 150);
      });
      wireMenu("");
      wireMenu("view");
      document.addEventListener("click", function (ev) {
        if (!ev.target.closest(".nw__menuwrap")) closeMenus();
      });
      // Escape on the View screen goes back to the grid.
      document.addEventListener("keydown", function (ev) {
        if (ev.key !== "Escape" || $("workView").hidden || !$("editorOverlay").hidden) return;
        if (!$("viewActionsMenu").hidden || !$("confirmBar").hidden) return;
        showGrid();
        var row = $("listBody").querySelector("tr.is-selected");
        if (row) row.focus();
      });
      $("confirmNo").addEventListener("click", function () { $("confirmBar").hidden = true; });
      $("draftBtn").addEventListener("click", function () { save("Draft", $("draftBtn")); });
      $("publishBtn").addEventListener("click", function () { save("Published", $("publishBtn")); });
      $("reportRefresh").addEventListener("click", loadReport);
      loadList().then(function () {
        var id = (window.location.hash || "").slice(1);
        if (id) { select(id); viewItem(id); }
      });
    }).catch(function (e) {
      if (e.status === 403 || e.status === 404 || e.status === 503) fail(e.message);
      else fail("Chapter News could not be opened: " + e.message);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
