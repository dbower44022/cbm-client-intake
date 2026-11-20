/* Chapter News — the publishers' page (prds/home-page-plan.md § 6.2;
   phase 5). The list of every item, the editor (CBMRichText with images),
   a live preview drawn by /shared/news.js exactly as a member sees it, and
   Withdraw. Everything is stored in the CRM through /news/api. */
(function () {
  "use strict";

  var API = "/news/api";
  var $ = function (id) { return document.getElementById(id); };
  var state = { teams: [], items: [], current: null, body: null, publishEl: null, expiresEl: null,
                grid: null, saving: false };

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

  // --- the list -----------------------------------------------------------------
  var STATUS_TONE = { "Draft": "navy", "Published": "green", "Withdrawn": "red" };

  function when(stamp) {
    var d = CBMNews.utc(stamp);
    if (!d) return "—";
    var o = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" };
    if (d.getFullYear() !== new Date().getFullYear()) o.year = "numeric";
    return d.toLocaleString(undefined, o);
  }
  function cell(tr, content, sortValue) {
    var td = el("td");
    if (typeof content === "string") td.textContent = content; else td.appendChild(content);
    if (sortValue !== undefined) td.dataset.sort = sortValue;
    tr.appendChild(td);
  }

  function drawList() {
    var body = $("listBody");
    body.innerHTML = "";
    if (!state.items.length) {
      body.appendChild(el("p", "cbm-panel__note", "No news yet. Choose New item to write the first."));
      return;
    }
    var wrap = el("div", "nw__tablewrap");
    var table = el("table", "nw__table");
    var hr = el("tr");
    [["title", "Title"], ["status", "Status"], ["importance", "Importance"], ["audience", "Audience"],
     ["publish", "Publish at"], ["expires", "Expires"], ["read", "Read"]].forEach(function (h) {
      var th = el("th", null, h[1]); th.dataset.col = h[0]; th.scope = "col"; hr.appendChild(th);
    });
    var thead = el("thead"); thead.appendChild(hr); table.appendChild(thead);
    var tbody = el("tbody");
    state.items.forEach(function (it) {
      var tr = el("tr", "nw__itemrow");
      if (state.current && state.current.id === it.id) tr.classList.add("nw__itemrow--on");
      var a = el("a", "nw__itemlink", it.title || "(no title)");
      a.href = "#" + it.id;
      a.addEventListener("click", function (ev) { ev.preventDefault(); open(it.id); });
      tr.addEventListener("click", function (ev) { if (!ev.target.closest("a")) open(it.id); });
      cell(tr, a, it.title || "");
      cell(tr, el("span", "cbm-pill cbm-tone--" + (STATUS_TONE[it.status] || "navy"), it.status || "Draft"), it.status || "");
      cell(tr, it.importance || "Normal");
      cell(tr, (it.audienceTeams || []).length ? it.audienceTeams.join(", ") : "Every member");
      cell(tr, el("span", "nw__nowrap", when(it.publishAt)), it.publishAt || "");
      cell(tr, el("span", "nw__nowrap", it.expiresAt ? when(it.expiresAt) : "—"), it.expiresAt || "");
      var rc = it.readCount;
      cell(tr, el("span", "nw__nowrap", rc ? rc.read + " of " + rc.of : (state.readUnavailable && it.status !== "Draft" ? "?" : "—")),
           rc ? String(rc.of ? rc.read / rc.of : 0) : "");
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    body.appendChild(wrap);
    if (window.CBMGrid && CBMGrid.enhance) {
      CBMGrid.enhance(table, { key: "news.items", sort: [{ col: "publish", dir: "desc" }] });
    }
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
      $("listBody").appendChild(el("p", "cbm-panel__note", "The news could not be read just now: " + e.message + "."));
    });
  }

  // --- the editor ---------------------------------------------------------------
  function drawTeams(chosen) {
    var box = $("fTeams");
    box.innerHTML = "";
    if (!state.teams.length) {
      box.appendChild(el("p", "nw__hint", "The CRM offers no teams, so the item goes to every member."));
      return;
    }
    state.teams.forEach(function (t) {
      var lab = el("label", "nw__team");
      var cb = el("input"); cb.type = "checkbox"; cb.value = t; cb.checked = chosen.indexOf(t) >= 0;
      cb.addEventListener("change", preview);
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + t));
      box.appendChild(lab);
    });
  }

  function dateControl(hostId, value) {
    var host = $(hostId);
    host.innerHTML = "";
    var c = CBMDateTime.create({ value: value || null });
    host.appendChild(c);
    host.addEventListener("change", preview);
    host.addEventListener("input", preview);
    return c;
  }

  function fill(item) {
    state.current = item;
    var it = item || {};
    $("editorTitle").textContent = item ? "Edit item" : "New item";
    var st = it.status || "Draft";
    $("editorStatus").textContent = st;
    $("editorStatus").className = "cbm-pill cbm-tone--" + (STATUS_TONE[st] || "navy");
    $("fTitle").value = it.title || "";
    $("fSummary").value = it.summary || "";
    $("fImportance").value = it.importance || "Normal";
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
    preview();
    drawList();
    loadReport();
  }

  function bodyValue() {
    var b = state.body;
    if (!b) return "";
    return b._cbmRichText ? b._cbmRichText.getValue() : b.value;
  }

  function read() {
    var teams = [];
    $("fTeams").querySelectorAll("input:checked").forEach(function (cb) { teams.push(cb.value); });
    return {
      title: $("fTitle").value.trim(),
      summary: $("fSummary").value.trim(),
      body: toStored(bodyValue()),
      importance: $("fImportance").value,
      audienceTeams: teams,
      publishAt: state.publishEl ? CBMDateTime.read(state.publishEl) : null,
      expiresAt: state.expiresEl ? CBMDateTime.read(state.expiresEl) : null,
      ctaLabel: $("fCtaLabel").value.trim(),
      ctaUrl: $("fCtaUrl").value.trim(),
    };
  }

  // The preview is the member's own drawing (CBMNews.item), closed and opened.
  function preview() {
    var d = read();
    var it = {
      id: "preview", title: d.title || "(no title yet)", summary: d.summary,
      body: toDisplay(d.body), importance: d.importance,
      publishAt: d.publishAt || null,
      cta: d.ctaLabel && d.ctaUrl ? { label: d.ctaLabel, url: d.ctaUrl } : null,
    };
    var closed = $("previewClosed"), opened = $("previewOpen");
    closed.innerHTML = ""; opened.innerHTML = "";
    closed.appendChild(CBMNews.item(it, {}));
    var o = CBMNews.item(it, { open: true });
    o.querySelector(".news-item__body").id = "news-body-preview-open";
    opened.appendChild(o);
  }

  function save(status, btn) {
    if (state.saving) return;
    var d = read();
    if (!d.title) { say("Give the item a title.", true); $("fTitle").focus(); return; }
    d.status = status;
    state.saving = true;
    var done = window.CBMBusy && CBMBusy.start ? CBMBusy.start(btn) : function () {};
    var cur = state.current;
    var call = cur ? api("/items/" + encodeURIComponent(cur.id), { method: "PUT", body: JSON.stringify(d) })
                   : api("/items", { method: "POST", body: JSON.stringify(d) });
    call.then(function (saved) {
      done(); state.saving = false;
      return loadList().then(function () {
        fill(saved);
        say(status === "Published" ? "Published. Members see it on their home page." : "Saved as a draft. Members do not see it.");
      });
    }).catch(function (e) {
      done(); state.saving = false;
      say("Not saved: " + e.message, true);
    });
  }

  function withdraw(btn) {
    var cur = state.current;
    if (!cur) { say("Open a saved item first: a new item has nothing to withdraw.", true); return; }
    if (cur.status === "Withdrawn") { say("This item is already withdrawn.", true); return; }
    var done = window.CBMBusy && CBMBusy.start ? CBMBusy.start(btn) : function () {};
    api("/items/" + encodeURIComponent(cur.id) + "/withdraw", { method: "POST" }).then(function (saved) {
      done();
      return loadList().then(function () {
        fill(saved);
        say("Withdrawn. It has gone from every member's home page and past news.");
      });
    }).catch(function (e) { done(); say("Not withdrawn: " + e.message, true); });
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
    var cur = state.current, panel = $("reportPanel"), body = $("reportBody");
    if (!cur || cur.status === "Draft") { panel.hidden = true; return; }
    panel.hidden = false;
    var read = api("/items/" + encodeURIComponent(cur.id) + "/report");
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(body, read);
    read.then(function (r) {
      if (state.current !== cur) return;
      body.innerHTML = "";
      var line = el("p", "nw__readline");
      line.appendChild(el("strong", null, r.read + " of " + r.of));
      line.appendChild(document.createTextNode(
        " in the audience have " + (r.mustAcknowledge ? "read or acknowledged" : "read") + " this item."));
      body.appendChild(line);
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

  function open(id) {
    var read = api("/items/" + encodeURIComponent(id)).then(fill);
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading($("editor"), read);
    read.catch(function (e) { say("That item could not be opened: " + e.message, true); });
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
      $("pageView").hidden = false;
      ["fTitle", "fSummary", "fImportance", "fCtaLabel", "fCtaUrl"].forEach(function (id) {
        $(id).addEventListener("input", preview);
        $(id).addEventListener("change", preview);
      });
      $("newBtn").addEventListener("click", function () { fill(null); $("fTitle").focus(); });
      $("draftBtn").addEventListener("click", function () { save("Draft", $("draftBtn")); });
      $("publishBtn").addEventListener("click", function () { save("Published", $("publishBtn")); });
      $("withdrawBtn").addEventListener("click", function () { withdraw($("withdrawBtn")); });
      $("reportRefresh").addEventListener("click", loadReport);
      $("testDigestBtn").addEventListener("click", function () { testDigest($("testDigestBtn")); });
      fill(null);
      loadList().then(function () {
        var id = (window.location.hash || "").slice(1);
        if (id) open(id);
      });
    }).catch(function (e) {
      if (e.status === 403 || e.status === 404 || e.status === 503) fail(e.message);
      else fail("Chapter News could not be opened: " + e.message);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
