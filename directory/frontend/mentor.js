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
    document.title = "Cleveland Business Mentors — " + (p.name || "Mentor");

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

    // Personal lane
    var per = p.personal || {};
    var perBody = $("mpPersonalBody");
    if (String(per.interests || "").trim()) {
      var ib = el("div", "mp2__tagblock");
      ib.appendChild(el("h3", "mp2__sub", "Personal interests"));
      var pText = el("p", "mp2__interests"); pText.textContent = per.interests;
      ib.appendChild(pText);
      perBody.appendChild(ib);
    }
    factRow(perBody, "Birthday", fmtBirthday(per.birthday));
    factRow(perBody, "Spouse", per.spouse);
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
    } catch (e) { fail(e); }
  }

  boot();
})();
