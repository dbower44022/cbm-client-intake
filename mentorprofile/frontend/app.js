/* My Mentor Profile — edit your own record with a live website preview. */
(function () {
  "use strict";

  var API = "/mentorprofile/api";
  var fieldSpec = [];      // [{name,label,type,group,row?,entity?,preview?}]
  var fieldOptions = {};   // {fieldName: [options]}
  var requiredNames = [];  // CRM-required editable fields
  var record = null;       // the loaded profile record
  var MAX_PHOTO_BYTES = 5 * 1024 * 1024;

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

  // Not signed in: hand off to the portal, which brings the user back here
  // after login (single sign-on — this app has no login form of its own).
  function showLogin() {
    location.href = "/?next=" + encodeURIComponent("/mentorprofile/");
  }
  function showMessage(text) {
    hide($("mainView")); $("msgText").textContent = text; show($("msgView"));
  }
  function bootFail(e) {
    if (e && e.status === 401) { showLogin(); return; }
    if (e && e.status === 403) { showMessage(e.message); return; }
    showMessage("The server isn't responding right now. Please try again in a moment.");
  }

  function notice(text, kind) {
    var n = $("noticeBox"); n.textContent = text;
    n.className = "mp__notice " + (kind === "error" ? "is-error" : kind === "warn" ? "is-warn" : "is-success");
    show(n); n.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  $("logoutBtn").addEventListener("click", async function () {
    try { await api("/logout", { method: "POST" }); } catch (e) {}
    location.href = "/";  // back to the portal sign-in
  });

  // --- boot ---
  async function boot() {
    try {
      var who = await api("/session");
      $("whoName").textContent = who.name || who.userName;
      var f = await api("/fields");
      fieldSpec = f.fields || []; fieldOptions = f.options || {}; requiredNames = f.required || [];
      var result = await api("/profile");
      if (!result.profileFound) {
        showMessage("We couldn't find a mentor profile linked to your login. Please contact CBM staff to have your profile connected.");
        return;
      }
      record = result.record || {};
      show($("mainView")); hide($("msgView"));
      renderForm(record);
      renderSince(record.mentorStartDate);  // fills the top-bar badge renderForm created
      refreshPreview();
      loadPhoto(record.profilePhotoId);
    } catch (e) { bootFail(e); }
  }

  // "Mentoring since mm/dd/yyyy" — the read-only badge between the photo and
  // the status toggles in the top bar (staff-set date; hidden when unset).
  function renderSince(dateStr) {
    var el = $("sinceBadge");
    if (!el) return;
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr || "");
    if (!m) { hide(el); return; }
    el.textContent = "Mentoring since " + m[2] + "/" + m[3] + "/" + m[1];
    show(el);
  }

  // Groups rendered side by side as one two-panel row (left, right).
  var GROUP_PAIRS = { "Contact information": "Personal details" };

  // --- form (stacked groups; `row` packs fields on one line, full width;
  //     the photo + `toggle` fields form the prominent TOP BAR) ---
  function renderForm(m) {
    var form = $("editForm"); form.innerHTML = "";
    // Top bar: photo control (left) + the prominent status toggles (right).
    var photoField = null, toggles = [];
    var rest = [];
    fieldSpec.forEach(function (f) {
      if (f.type === "image") photoField = f;
      else if (f.toggle) toggles.push(f);
      else rest.push(f);
    });
    if (photoField || toggles.length) {
      var top = document.createElement("div"); top.className = "mp__topbar";
      if (photoField) top.appendChild(buildPhotoControl());
      // The "Mentoring since" badge sits between the photo and the toggles
      // (renderSince fills it after load; stays hidden with no start date).
      var since = document.createElement("p");
      since.className = "mp__since"; since.id = "sinceBadge"; since.hidden = true;
      top.appendChild(since);
      if (toggles.length) {
        var panel = document.createElement("div"); panel.className = "mp__toggles";
        toggles.forEach(function (f) {
          var t = buildField(f, m[f.name]);
          t.classList.add("mp__toggle");
          panel.appendChild(t);
        });
        top.appendChild(panel);
      }
      form.appendChild(top);
    }
    // Grouped sections (in spec order), with paired groups side by side.
    var groups = {}, order = [];
    rest.forEach(function (f) {
      if (!groups[f.group]) { groups[f.group] = []; order.push(f.group); }
      groups[f.group].push(f);
    });
    function buildGroup(group) {
      var sec = document.createElement("section"); sec.className = "mp__group";
      var h = document.createElement("h2"); h.className = "mp__group-h"; h.textContent = group;
      sec.appendChild(h);
      var rows = {}, rowOrder = [];
      groups[group].forEach(function (f) {
        var r = f.row || "_" + f.name;   // no row => its own line
        if (!rows[r]) { rows[r] = []; rowOrder.push(r); }
        rows[r].push(f);
      });
      rowOrder.forEach(function (r) {
        var rowEl = document.createElement("div"); rowEl.className = "mp__row";
        rows[r].forEach(function (f) { rowEl.appendChild(buildField(f, m[f.name])); });
        sec.appendChild(rowEl);
      });
      return sec;
    }
    var consumed = {};
    order.forEach(function (group) {
      if (consumed[group]) return;
      var partner = GROUP_PAIRS[group];
      if (partner && groups[partner]) {
        var cols = document.createElement("div"); cols.className = "mp__cols";
        var left = buildGroup(group); left.classList.add("mp__cols-main");
        var right = buildGroup(partner); right.classList.add("mp__cols-side");
        cols.appendChild(left); cols.appendChild(right);
        form.appendChild(cols);
        consumed[partner] = true;
      } else {
        form.appendChild(buildGroup(group));
      }
    });
    // One delegated listener drives the live preview (checkboxes fire change,
    // text/wysiwyg fire input).
    form.addEventListener("input", refreshPreview);
    form.addEventListener("change", refreshPreview);
  }

  function buildField(f, value) {
    var wrap = document.createElement("div");
    wrap.className = "cbm-field field-" + f.type + " fname-" + f.name;
    var label = document.createElement("label"); label.setAttribute("for", "f_" + f.name);
    label.textContent = f.label;
    if (requiredNames.indexOf(f.name) >= 0) {
      var star = document.createElement("span"); star.className = "cbm-required"; star.textContent = " *";
      label.appendChild(star);
    }
    var input = makeInput(f, value);
    input.id = "f_" + f.name; input.dataset.field = f.name; input.dataset.type = f.type;
    // Snapshot the initial (normalized) value so Save can send only changed
    // fields — re-sending an unchanged value that has drifted out of its CRM
    // enum options would 400 the whole update.
    input.dataset.original = JSON.stringify(readField(input));
    if (f.type === "bool") {
      wrap.className += " cbm-field--check";
      var lab = document.createElement("label");
      lab.appendChild(input); lab.appendChild(document.createTextNode(" " + f.label));
      wrap.appendChild(lab); return wrap;
    }
    wrap.appendChild(label); wrap.appendChild(input); return wrap;
  }

  // --- WYSIWYG editor (contenteditable + minimal toolbar; no external deps) ---
  var WYSIWYG_BUTTONS = [
    { title: "Bold", label: "<b>B</b>", cmd: "bold" },
    { title: "Italic", label: "<i>I</i>", cmd: "italic" },
    { title: "Underline", label: "<u>U</u>", cmd: "underline" },
    { title: "Bulleted list", label: "&bull;", cmd: "insertUnorderedList" },
    { title: "Numbered list", label: "1.", cmd: "insertOrderedList" },
    { title: "Link", label: "Link", cmd: "createLink" },
    { title: "Remove formatting", label: "Clear", cmd: "removeFormat" },
  ];

  // Strip dangerous markup before loading CRM HTML into a contenteditable or
  // the preview (scripts won't run via innerHTML, but on* handlers /
  // javascript: URLs can).
  function sanitizeHtml(html) {
    var tmp = document.createElement("div"); tmp.innerHTML = html || "";
    Array.prototype.forEach.call(tmp.querySelectorAll("script,style,iframe,object,embed,link,meta"), function (n) { n.remove(); });
    Array.prototype.forEach.call(tmp.querySelectorAll("*"), function (n) {
      Array.prototype.slice.call(n.attributes).forEach(function (a) {
        var name = a.name.toLowerCase(), val = (a.value || "").replace(/\s/g, "").toLowerCase();
        if (name.indexOf("on") === 0) n.removeAttribute(a.name);
        else if ((name === "href" || name === "src") && val.indexOf("javascript:") === 0) n.removeAttribute(a.name);
      });
    });
    return tmp.innerHTML;
  }

  function makeWysiwyg(value) {
    var el = document.createElement("div"); el.className = "wysiwyg";
    var area = document.createElement("div");
    area.className = "wysiwyg__area"; area.contentEditable = "true";
    area.innerHTML = sanitizeHtml(value == null ? "" : String(value));
    var bar = document.createElement("div"); bar.className = "wysiwyg__toolbar";
    WYSIWYG_BUTTONS.forEach(function (b) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "wysiwyg__btn"; btn.title = b.title; btn.innerHTML = b.label;
      // mousedown preventDefault keeps the editor's selection while clicking.
      btn.addEventListener("mousedown", function (ev) { ev.preventDefault(); });
      btn.addEventListener("click", function () {
        if (b.cmd === "createLink") {
          var url = window.prompt("Link URL:", "https://");
          if (url) document.execCommand("createLink", false, url);
        } else {
          document.execCommand(b.cmd, false, null);
        }
      });
      bar.appendChild(btn);
    });
    el.appendChild(bar); el.appendChild(area);
    return el;
  }

  function makeInput(f, value) {
    var el;
    if (f.type === "enum") {
      el = document.createElement("select");
      var opts = (f.options || fieldOptions[f.name] || []).slice();
      // Keep an existing value selectable even if it's not in the list.
      if (value != null && value !== "" && opts.indexOf(value) < 0) opts.unshift(value);
      if (opts.indexOf("") < 0) opts.unshift("");  // allow clearing
      opts.forEach(function (o) { el.appendChild(new Option(o === "" ? "(none)" : o, o)); });
      el.value = value == null ? "" : value;
    } else if (f.type === "multiEnum") {
      el = document.createElement("div"); el.className = "checkgrid";
      var sel = value || [];
      var opts2 = (fieldOptions[f.name] || []).slice();
      // A stored value that drifted out of the options still renders selected,
      // so a save can't silently drop it.
      sel.forEach(function (v) { if (opts2.indexOf(v) < 0) opts2.push(v); });
      opts2.forEach(function (o) {
        var lab = document.createElement("label"); lab.className = "checkgrid__opt";
        var cb = document.createElement("input"); cb.type = "checkbox"; cb.value = o; cb.checked = sel.indexOf(o) >= 0;
        lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + o));
        el.appendChild(lab);
      });
    } else if (f.type === "bool") {
      el = document.createElement("input"); el.type = "checkbox"; el.checked = !!value;
    } else if (f.type === "int") {
      el = document.createElement("input"); el.type = "number"; el.value = (value == null) ? "" : value;
    } else if (f.type === "date") {
      el = document.createElement("input"); el.type = "date"; el.value = value || "";
    } else if (f.type === "wysiwyg") {
      el = makeWysiwyg(value);
    } else if (f.type === "text") {
      el = document.createElement("textarea"); el.rows = f.rows || 2; el.value = value == null ? "" : value;
    } else if (f.type === "url") {
      el = document.createElement("input"); el.type = "url"; el.value = value == null ? "" : value;
      el.placeholder = "https://www.linkedin.com/in/…";
    } else {
      el = document.createElement("input"); el.type = "text"; el.value = value == null ? "" : value;
    }
    return el;
  }

  function readField(el) {
    var t = el.dataset.type;
    if (t === "multiEnum") return Array.prototype.map.call(el.querySelectorAll("input:checked"), function (c) { return c.value; });
    if (t === "bool") return el.checked;
    if (t === "int") return el.value === "" ? null : Number(el.value);
    if (t === "date") return el.value || null;
    if (t === "wysiwyg") {
      var a = el.querySelector(".wysiwyg__area");
      if (!a) return "";
      return a.textContent.trim() === "" ? "" : a.innerHTML;  // empty -> "" not "<br>"
    }
    return el.value;
  }

  function currentFormValues() {
    var v = {};
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      v[el.dataset.field] = readField(el);
    });
    return v;
  }

  function rebaseline() {
    // Re-baseline the change snapshots to the just-saved state, so a later edit
    // that reverts a field to its render-time value is still sent.
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      el.dataset.original = JSON.stringify(readField(el));
    });
  }

  // --- save (diffed: only fields the user actually changed) ---
  function collectChanges() {
    var changes = {};
    Array.prototype.forEach.call($("editForm").querySelectorAll("[data-field]"), function (el) {
      var v = readField(el);
      if (JSON.stringify(v) !== el.dataset.original) changes[el.dataset.field] = v;
    });
    return changes;
  }

  function missingRequired(values) {
    var labels = [];
    requiredNames.forEach(function (name) {
      var v = values[name];
      var empty = v == null || v === "" || (Array.isArray(v) && !v.length);
      if (!empty) return;
      var spec = fieldSpec.filter(function (f) { return f.name === name; })[0];
      labels.push(spec ? spec.label : name);
    });
    return labels;
  }

  $("saveBtn").addEventListener("click", async function () {
    var missing = missingRequired(currentFormValues());
    if (missing.length) {
      notice("Please complete: " + missing.join(", ") + ".", "error");
      return;
    }
    var changes = collectChanges();
    if (!Object.keys(changes).length) { notice("Nothing to save — you haven't changed anything.", "success"); return; }
    $("saveBtn").disabled = true;
    try {
      var result = await api("/profile", { method: "PUT", body: JSON.stringify({ changes: changes }) });
      record = (result && result.record) || record;
      rebaseline();
      // Non-fatal server-side notes (e.g. a drifted option dropped rather than
      // failing the save) — the save succeeded, but the user should know.
      if (result.warnings && result.warnings.length) {
        notice("Saved, with a note: " + result.warnings.join(" "), "warn");
      } else {
        notice("Saved. Your profile is up to date.", "success");
      }
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    } finally { $("saveBtn").disabled = false; }
  });

  // --- photo (uploaded immediately, outside the Save diff) ---
  function buildPhotoControl() {
    var wrap = document.createElement("div"); wrap.className = "cbm-field mp__photo-field";
    var label = document.createElement("label"); label.textContent = "Profile photo";
    var box = document.createElement("div"); box.className = "mp__photo-box";
    var img = document.createElement("img");
    img.id = "photoThumb"; img.alt = "Your profile photo"; img.hidden = true;
    var ph = document.createElement("div"); ph.className = "mp__photo-ph"; ph.id = "photoPh";
    ph.textContent = "No photo yet";
    var controls = document.createElement("div"); controls.className = "mp__photo-controls";
    var file = document.createElement("input");
    file.type = "file"; file.id = "photoFile"; file.accept = "image/jpeg,image/png,image/webp,image/gif";
    var removeBtn = document.createElement("button");
    removeBtn.type = "button"; removeBtn.className = "cbm-button cbm-button--secondary mp__photo-remove";
    removeBtn.id = "photoRemove"; removeBtn.textContent = "Remove photo"; removeBtn.hidden = true;
    var help = document.createElement("span"); help.className = "cbm-help";
    help.textContent = "JPEG, PNG, WebP, or GIF up to 5 MB. The photo saves immediately when you choose it.";
    controls.appendChild(file); controls.appendChild(removeBtn);
    box.appendChild(img); box.appendChild(ph);
    wrap.appendChild(label); wrap.appendChild(box); wrap.appendChild(controls); wrap.appendChild(help);
    file.addEventListener("change", onPhotoPicked);
    removeBtn.addEventListener("click", onPhotoRemove);
    return wrap;
  }

  function setPhotoSrc(src) {
    // The hero photo circle keeps its gradient background when there is no
    // image — exactly what the live page's onerror fallback shows.
    ["photoThumb", "pvPhoto"].forEach(function (id) {
      var img = $(id); if (!img) return;
      if (src) { img.src = src; show(img); } else { img.removeAttribute("src"); hide(img); }
    });
    var thumbPh = $("photoPh"), removeBtn = $("photoRemove");
    if (thumbPh) thumbPh.hidden = !!src;
    if (removeBtn) removeBtn.hidden = !src;
  }

  function loadPhoto(photoId) {
    // ?v= busts the browser cache after an upload (the server sends no-store
    // anyway, but the query keeps the two <img> elements honest).
    setPhotoSrc(photoId ? API + "/photo?v=" + encodeURIComponent(photoId) : null);
  }

  async function onPhotoPicked(ev) {
    var input = ev.target;
    var f = input.files && input.files[0];
    if (!f) return;
    if (["image/jpeg", "image/png", "image/webp", "image/gif"].indexOf(f.type) < 0) {
      notice("Please choose a JPEG, PNG, WebP, or GIF image.", "error"); input.value = ""; return;
    }
    if (f.size > MAX_PHOTO_BYTES) {
      notice("That image is too large — please use one under 5 MB.", "error"); input.value = ""; return;
    }
    var prev = $("photoThumb").hidden ? null : $("photoThumb").src;
    var reader = new FileReader();
    reader.onload = async function () {
      var dataUrl = String(reader.result || "");
      setPhotoSrc(dataUrl);  // instant local preview while the upload runs
      var b64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
      try {
        var result = await api("/photo", {
          method: "POST",
          body: JSON.stringify({ filename: f.name, contentType: f.type, dataBase64: b64 }),
        });
        record.profilePhotoId = result.profilePhotoId;
        loadPhoto(result.profilePhotoId);
        notice("Photo saved.", "success");
      } catch (e) {
        if (e.status === 401) { showLogin(); return; }
        setPhotoSrc(prev);  // revert the optimistic preview
        notice(e.message, "error");
      } finally { input.value = ""; }
    };
    reader.readAsDataURL(f);
  }

  async function onPhotoRemove() {
    try {
      await api("/photo", { method: "DELETE" });
      record.profilePhotoId = null;
      setPhotoSrc(null);
      notice("Photo removed.", "success");
    } catch (e) {
      if (e.status === 401) { showLogin(); return; }
      notice(e.message, "error");
    }
  }

  // --- live website preview (an exact copy of the live page's markup/CSS;
  //     this fill logic mirrors the page's own rendering) ---
  // Absolute external URL for a stored link value — a bare "linkedin.com/…"
  // would otherwise resolve relative to this app's own path.
  function externalHref(v) {
    v = String(v || "").trim();
    return /^https?:\/\//i.test(v) ? v : "https://" + v;
  }

  // The website's expertise list: one row per value — gold dot + bold navy
  // label (the site splits "Label: description" on the first colon; plain
  // enum values have no description, which its script also handles).
  function buildExpertiseList(values) {
    var container = $("pvExpertise"); container.innerHTML = "";
    if (!values.length) return;
    var ul = document.createElement("ul");
    ul.className = "cbm-expertise-list";
    values.forEach(function (item) {
      var li = document.createElement("li");
      li.className = "cbm-expertise-item";
      var dot = document.createElement("div");
      dot.className = "cbm-expertise-dot"; dot.setAttribute("aria-hidden", "true");
      var textWrap = document.createElement("div");
      var colonIndex = item.indexOf(":");
      var label = colonIndex > -1 ? item.substring(0, colonIndex).trim() : item;
      var desc = colonIndex > -1 ? item.substring(colonIndex + 1).trim() : "";
      var labelEl = document.createElement("span");
      labelEl.className = "cbm-expertise-label";
      labelEl.textContent = label + (desc ? ":" : "");
      textWrap.appendChild(labelEl);
      if (desc) {
        var descEl = document.createElement("span");
        descEl.className = "cbm-expertise-desc";
        descEl.textContent = " " + desc;
        textWrap.appendChild(descEl);
      }
      li.appendChild(dot); li.appendChild(textWrap);
      ul.appendChild(li);
    });
    container.appendChild(ul);
  }

  // The About box: the wysiwyg's sanitized HTML; a plain-text value (no tags)
  // is wrapped in <p> so it takes the site's paragraph styling.
  function fillAbout(value) {
    var html = sanitizeHtml(value == null ? "" : String(value)).trim();
    if (html && html.indexOf("<") !== 0) html = "<p>" + html + "</p>";
    $("pvAbout").innerHTML = html;
  }

  function refreshPreview() {
    var v = currentFormValues();
    // Unpublished banner + dimmed page (the preview still renders).
    var published = !!v.publicProfile;
    $("pvUnpub").hidden = published;
    $("pvViewport").classList.toggle("is-unpublished", !published);
    // Hero: name + title
    var first = (v.firstName || "").trim();
    var name = (first + " " + (v.lastName || "").trim()).trim();
    $("pvName").textContent = name || "Your Name";
    $("pvHeadline").textContent = (v.mentorTitle || "").trim();
    // Left column: ABOUT {FIRST} label + short summary (feature-gated field —
    // no editor input until the CRM has it; fall back to the loaded record)
    var aboutWho = "About" + (first ? " " + first : "");
    $("pvAboutLabel").textContent = aboutWho;
    var summary = ("mentorSummary" in v ? v.mentorSummary : (record && record.mentorSummary)) || "";
    $("pvSummary").textContent = summary;
    $("pvSummary").hidden = !summary.trim();
    // LinkedIn: the site renders the button even without a URL — mirror that,
    // but only navigate when a real link is set.
    var li = (v.cLinkedInProfile || "").trim();
    var liBtn = $("pvLinkedin");
    if (li) liBtn.setAttribute("href", externalHref(li));
    else liBtn.setAttribute("href", "");
    // Industry Experience box (semicolon-joined, like the site's post meta)
    var ind = v.industryExperience || [];
    $("pvIndustries").textContent = ind.join("; ");
    $("pvIndustryBox").hidden = !ind.length;
    // Right column: expertise list + About box
    buildExpertiseList(v.areaOfExpertise || []);
    $("pvAboutHead").textContent = aboutWho;
    fillAbout(v.aboutMentor);
    // Bottom panel: "Ready to Connect with {first}?"
    $("pvConnectHead").textContent = "Ready to Connect" + (first ? " with " + first : "") + "?";
    fitPreview();
  }

  // Render the page at the site's 1200px desktop width, scaled to the pane.
  var PV_PAGE_WIDTH = 1200;
  function fitPreview() {
    var vp = $("pvViewport"), sc = $("pvScale");
    if (!vp || !sc) return;
    var w = vp.clientWidth;
    if (!w) return;
    var k = Math.min(1, w / PV_PAGE_WIDTH);
    sc.style.transform = "scale(" + k + ")";
    vp.style.height = Math.ceil(sc.offsetHeight * k) + "px";
  }
  window.addEventListener("resize", fitPreview);
  if (window.ResizeObserver) {
    new ResizeObserver(fitPreview).observe($("pvViewport"));
  }

  // The preview is a rendering, not a navigation surface: its links stay
  // inert, except a real LinkedIn URL (useful to verify) which opens new-tab.
  $("pvCard").addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a");
    if (!a) return;
    var isLinkedIn = a.id === "pvLinkedin" && (a.getAttribute("href") || "").trim();
    if (!isLinkedIn) ev.preventDefault();
  });

  // --- drag splitter (resize the form/preview split; full-width layout) ---
  (function setupSplitter() {
    var sp = $("splitter"), grid = $("splitGrid");
    if (!sp || !grid) return;
    var dragging = false;
    function clampedWidth(clientX) {
      var rect = grid.getBoundingClientRect();
      var min = 320, max = Math.max(min, rect.width * 0.75);
      return Math.min(max, Math.max(min, clientX - rect.left));
    }
    function onMove(e) {
      if (!dragging) return;
      grid.style.setProperty("--mp-left", clampedWidth(e.clientX) + "px");
      fitPreview();  // keep the scaled page fitted while the pane resizes
      e.preventDefault();
    }
    function stop() {
      if (!dragging) return;
      dragging = false; document.body.classList.remove("mp--resizing");
      fitPreview();
    }
    sp.addEventListener("pointerdown", function (e) {
      dragging = true; document.body.classList.add("mp--resizing"); e.preventDefault();
    });
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  })();

  boot();
})();
