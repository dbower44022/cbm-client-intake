/* Rich mentor profile page — /directory/mentors/record/{id}. Its own tab
   (opened from the Mentors directory grid via a stable named window). A warm,
   read-only "get to know this colleague" view built from the CMentorProfile +
   its linked Contact — deliberately NOT the CRM-layout pop-up and NOT the
   external public-website look. Editing lives in My Profile; nothing here
   writes. Fresh single IIFE (its own page — no shared-scope collisions). */
(function () {
  "use strict";

  var segs = location.pathname.split("/"); // ["", "directory", "mentors", "record", "<id>"]
  var RECORD_ID = segs[4] || "";
  var API = "/directory/mentors/api";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  // The organisation's name, substituted into the page server-side
  // (core/branding.py). Read from the meta rather than /healthz so it is
  // available synchronously, with no fetch and no race.
  function orgName() { var m = document.querySelector('meta[name="cbm-org"]'); return (m && m.content) || ""; }
  function show(e) { if (e) e.hidden = false; }
  function hide(e) { if (e) e.hidden = true; }

  var R = window.CBMDirRender;   // emailLink (compose) + renderValue (html sanitize)

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
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

  function fail(e) {
    if (e && e.status === 401) {
      location.href = "/?next=" + encodeURIComponent("/directory/mentors/record/" + RECORD_ID);
      return;
    }
    hide($("mpMainView"));
    $("mpMsgText").textContent = (e && e.message) || "Something went wrong.";
    show($("mpMsgView"));
  }

  // ---- small renderers -----------------------------------------------------

  function initials(name) {
    var parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    var a = parts[0][0] || "";
    var b = parts.length > 1 ? parts[parts.length - 1][0] : "";
    return (a + b).toUpperCase();
  }

  function chipRow(values) {
    var wrap = el("div", "mp2__tags");
    values.forEach(function (v) { wrap.appendChild(el("span", "mp2__tag", v)); });
    return wrap;
  }

  // A labeled "Areas of expertise" style block: heading + chips. Skipped when
  // the list is empty (an empty block reads as a broken feature).
  function tagBlock(container, label, values) {
    if (!values || !values.length) return;
    var b = el("div", "mp2__tagblock");
    b.appendChild(el("h3", "mp2__sub", label));
    b.appendChild(chipRow(values));
    container.appendChild(b);
  }

  function factRow(container, label, value) {
    if (value == null || value === "") return;
    var row = el("div", "mp2__fact");
    row.appendChild(el("span", "mp2__fact-l", label));
    if (value instanceof Node) row.appendChild(value);
    else row.appendChild(el("span", "mp2__fact-v", String(value)));
    container.appendChild(row);
  }

  function fmtDate(iso) {
    if (!iso) return "";
    var s = String(iso).slice(0, 10);
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return s;
    var months = ["January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December"];
    return months[+m[2] - 1] + " " + (+m[3]) + ", " + m[1];
  }

  // Birthday with no year of interest — show month + day only (a colleague's
  // birthday is for wishing them well, not their age).
  function fmtBirthday(iso) {
    if (!iso) return "";
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
    if (!m) return String(iso);
    var months = ["January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December"];
    return months[+m[2] - 1] + " " + (+m[3]);
  }

  function emailNode(addr) {
    try { if (R && R.emailLink) return R.emailLink(addr); } catch (e) {}
    var a = el("a", null, addr); a.href = "mailto:" + addr; return a;
  }

  function richInto(node, html) {
    var clean = (window.CBMRichText && window.CBMRichText.sanitizeHtml)
      ? window.CBMRichText.sanitizeHtml(String(html || ""))
      : "";
    node.innerHTML = clean;
  }

  // ---- render --------------------------------------------------------------

  function render(p) {
    document.title = orgName() + " — " + (p.name || "Mentor");

    // Hero
    $("mpName").textContent = p.name || "(no name)";
    if (p.headline) { $("mpHeadline").textContent = p.headline; show($("mpHeadline")); }

    var ph = $("mpPhotoPh");
    ph.textContent = initials(p.name);
    if (p.hasPhoto) {
      var img = $("mpPhoto");
      img.alt = p.name || "";
      img.onload = function () { show(img); hide(ph); };
      img.onerror = function () { hide(img); show(ph); };
      img.src = API + "/photo/" + encodeURIComponent(p.id);
    }

    var chips = $("mpStatusChips");
    if (p.acceptingNewClients) chips.appendChild(el("span", "mp2__chip mp2__chip--go", "Accepting new clients"));
    else chips.appendChild(el("span", "mp2__chip mp2__chip--off", "Not accepting new clients"));
    if (p.status) chips.appendChild(el("span", "mp2__chip", p.status));
    if (p.mentorType) chips.appendChild(el("span", "mp2__chip", p.mentorType));

    // Stats strip — years mentoring + years in field
    var pr = p.professional || {};
    var stats = $("mpStats");
    if (pr.yearsMentoring != null || pr.mentoringSince) {
      var since = pr.mentoringSince ? String(pr.mentoringSince).slice(0, 4) : null;
      var big = pr.yearsMentoring != null ? String(pr.yearsMentoring) : "—";
      var sub = "years mentoring" + (since ? " (since " + since + ")" : "");
      stats.appendChild(statTile(big, sub));
    }
    if (pr.yearsExperience != null && pr.yearsExperience !== "") {
      stats.appendChild(statTile(String(pr.yearsExperience), "years in their field"));
    }
    if (stats.children.length) show($("mpStatCard"));

    // Expertise & focus
    var exBody = $("mpExpertiseBody");
    tagBlock(exBody, "Areas of expertise", pr.expertise);
    tagBlock(exBody, "Industries served", pr.industries);
    tagBlock(exBody, "Preferred business stages", pr.businessStages);
    tagBlock(exBody, "Languages", pr.languages);
    if (exBody.children.length) show($("mpExpertiseCard"));

    // About / bio (wysiwyg)
    if (String(pr.about || "").trim()) { richInto($("mpAbout"), pr.about); show($("mpAboutCard")); }
    if (String(pr.bio || "").trim()) { richInto($("mpBio"), pr.bio); show($("mpBioCard")); }

    // Mentoring availability (openings) — computed under the org-wide key.
    renderAvailability(p.availability, pr);

    // Personal lane ("Get to know them")
    var per = p.personal || {};
    var perBody = $("mpPersonalBody");
    if (String(per.interests || "").trim()) {
      perBody.appendChild(el("h3", "mp2__sub", "Personal interests"));
      var pText = el("p", "mp2__interests"); pText.textContent = per.interests;
      perBody.appendChild(pText);
    }
    var pg = el("dl", "mp2__pgrid");
    pgItem(pg, "Birthday", fmtBirthday(per.birthday));
    pgItem(pg, "Spouse", per.spouse);
    pgItem(pg, "City", per.city);
    if (pg.children.length) perBody.appendChild(pg);
    if (perBody.children.length) show($("mpPersonalCard"));

    // Contact lane
    var ct = p.contact || {};
    var ctBody = $("mpContactBody");
    if (ct.cbmEmail) factRow(ctBody, "CBM email", emailNode(ct.cbmEmail));
    if (ct.personalEmail && ct.personalEmail !== ct.cbmEmail) factRow(ctBody, "Personal email", emailNode(ct.personalEmail));
    if (ct.phone) {
      var disp = (window.CBM && CBM.formatPhone) ? CBM.formatPhone(ct.phone) : ct.phone;
      var tel = el("a", null, disp); tel.href = "tel:" + ct.phone;
      factRow(ctBody, "Phone", tel);
    }
    if (ct.linkedIn) {
      var u = String(ct.linkedIn);
      var li = el("a", null, "View LinkedIn profile");
      li.href = /^https?:\/\//i.test(u) ? u : "https://" + u;
      li.target = "_blank"; li.rel = "noopener";
      factRow(ctBody, "LinkedIn", li);
    }
    if (ctBody.children.length) show($("mpContactCard"));

    show($("mpMainView"));
  }

  function statTile(big, sub) {
    var t = el("div", "mp2__stat");
    t.appendChild(el("div", "mp2__stat-n", big));
    t.appendChild(el("div", "mp2__stat-s", sub));
    return t;
  }

  // One labeled item in the personal grid (dt/dd), skipped when empty.
  function pgItem(dl, label, value) {
    if (value == null || value === "") return;
    var d = el("div", "mp2__pg");
    d.appendChild(el("dt", null, label));
    d.appendChild(el("dd", null, String(value)));
    dl.appendChild(d);
  }

  // The availability card: how many mentoring openings this mentor has now, so
  // a browser can see whether they're fully committed even when still marked
  // "accepting". Falls back to the stated capacity when the openings number
  // couldn't be computed (av == null), and is hidden entirely when there's no
  // capacity information at all.
  function renderAvailability(av, pr) {
    var body = $("mpAvailBody");
    var maxCap = pr && pr.maxCapacity;
    if (av && av.unlimited) {
      body.appendChild(bigAvail("∞", "No set client limit"));
      body.appendChild(el("p", "mp2__avail-note mp2__avail-note--go", "Open to new clients"));
    } else if (av && av.available != null) {
      var full = av.available === 0;
      body.appendChild(bigAvail(String(av.available), "of " + av.max + " openings open"));
      body.appendChild(availBar(av.active, av.max));
      body.appendChild(el("p",
        "mp2__avail-note " + (full ? "mp2__avail-note--full" : "mp2__avail-note--go"),
        full ? "Fully committed" : (av.available + " opening" + (av.available === 1 ? "" : "s") + " available")));
    } else if (maxCap != null && maxCap !== "" && Number(maxCap) >= 0) {
      // Openings couldn't be computed — show the stated capacity only.
      body.appendChild(bigAvail(String(maxCap), "client capacity"));
      body.appendChild(el("p", "mp2__avail-note", "Current openings unavailable"));
    } else {
      return;  // nothing meaningful to show
    }
    show($("mpAvailCard"));
  }

  function bigAvail(n, sub) {
    var w = el("div", "mp2__avail");
    w.appendChild(el("div", "mp2__avail-n", n));
    w.appendChild(el("div", "mp2__avail-s", sub));
    return w;
  }

  // A small filled/empty slot bar (active clients filled, openings empty).
  function availBar(active, max) {
    var bar = el("div", "mp2__slots");
    var total = Math.max(0, Number(max) || 0);
    for (var i = 0; i < total; i++) {
      bar.appendChild(el("span", "mp2__slot" + (i < active ? " mp2__slot--on" : "")));
    }
    return bar;
  }

  // ---- splitter (resize the side lane) -------------------------------------
  // Mirrors the sessions Overview --ov-right handle: the side width is measured
  // from the grid's RIGHT edge, clamped, keyboard-adjustable, and persisted.
  var SIDE_KEY = "cbmMentorSideW";

  function setupSplitter() {
    var grid = document.querySelector(".mp2__cols");
    var sp = $("mpSplit");
    if (!grid || !sp) return;

    function clampPx(px, rect) {
      var min = 340;
      var max = Math.max(min, (rect || grid.getBoundingClientRect()).width - 320);
      return Math.min(max, Math.max(min, px));
    }
    function apply(px) { grid.style.setProperty("--mp-side", Math.round(px) + "px"); }
    function save() {
      try { localStorage.setItem(SIDE_KEY, getComputedStyle(grid).getPropertyValue("--mp-side").trim()); } catch (e) {}
    }

    // Restore a saved width (clamped to the current viewport so it can't overflow).
    try {
      var saved = parseInt(localStorage.getItem(SIDE_KEY), 10);
      if (saved) apply(clampPx(saved));
    } catch (e) {}

    var dragging = false;
    function onMove(e) { if (dragging) { apply(clampPx(grid.getBoundingClientRect().right - e.clientX)); e.preventDefault(); } }
    function stop() { if (dragging) { dragging = false; document.body.classList.remove("mp2--resizing"); save(); } }
    sp.addEventListener("pointerdown", function (e) { dragging = true; document.body.classList.add("mp2--resizing"); e.preventDefault(); });
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    sp.addEventListener("keydown", function (e) {
      var cur = parseInt(getComputedStyle(grid).getPropertyValue("--mp-side"), 10) || 544;
      if (e.key === "ArrowLeft") { apply(clampPx(cur + 24)); e.preventDefault(); save(); }   // grow the side
      else if (e.key === "ArrowRight") { apply(clampPx(cur - 24)); e.preventDefault(); save(); }
    });
  }

  // ---- boot ----------------------------------------------------------------

  async function boot() {
    $("mpLogoutBtn").addEventListener("click", async function () {
      try { await api("/logout", { method: "POST" }); } catch (e) {}
      location.href = "/";
    });
    try { if (window.CBMQuickMail) window.CBMQuickMail.apiBase = API; } catch (e) {}

    try {
      var sess = await api("/session");
      $("mpWhoName").textContent = sess.name || sess.userName || "";
    } catch (e) { return fail(e); }

    try {
      var p = await api("/profile/" + encodeURIComponent(RECORD_ID));
      render(p);
      // After the view is shown (the grid now has real width, so a restored
      // width clamps correctly).
      setupSplitter();
    } catch (e) { fail(e); }
  }

  boot();
})();
