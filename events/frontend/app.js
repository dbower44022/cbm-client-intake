/*
 * Event Administration — /events
 *
 * One page, two views: a sortable/searchable grid of every event, and a record
 * detail with Overview / Registrants / Check-in tabs.
 *
 * House conventions honoured here:
 *  - Action buttons are NEVER disabled and never hidden. They validate on click
 *    and say what is missing (product-wide ruling) — a greyed-out button reads
 *    as a bug and generates support calls.
 *  - Counts are whatever the server computed; nothing is derived twice.
 *  - Every write goes through api(), which surfaces the server's own message
 *    rather than a generic failure.
 */
(function () {
  "use strict";

  var API = "/events/api";
  var state = {
    events: [],
    fields: [],
    links: [],         // Phase B: the partner / funder pickers the live CRM supports
    presenters: { enabled: false, available: false },  // F4: the switch, and whether this CRM has CEventPresenter
    options: {},
    optionLabels: {},   // { field: { storedValue: displayLabel } } from the CRM
    chapterKey: "",
    session: {},
    current: null,      // { event, counts, registrations }
    sort: { key: "startsAtUtc", dir: -1 },
    scope: "published",
    scopeChosen: false, // set once the user picks for themselves
    search: "",
  };

  /* ---------- plumbing ---------- */

  function $(id) { return document.getElementById(id); }

  async function api(path, opts) {
    var options = Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {});
    var resp = await fetch(API + path, options);
    if (resp.status === 401) {
      window.location.href = "/?next=/events/";
      throw new Error("Not signed in.");
    }
    var data = null;
    try { data = await resp.json(); } catch (e) { /* empty body is fine */ }
    if (!resp.ok) {
      throw new Error((data && data.detail) || ("Request failed (" + resp.status + ")"));
    }
    return data;
  }

  /* A save that succeeded but deserves a second look (a display time on an
     unticked event, a display time after the start) — never blocking. */
  function noticeWithWarnings(message, warnings) {
    if (warnings && warnings.length) notice(message + " " + warnings.join(" "), "warn");
    else notice(message, "ok");
  }

  function notice(message, kind) {
    // The page banner sits BEHIND the modal overlay, so a message raised while
    // the editor is open (an upload that failed, a graphic saved) went unseen
    // — "the upload does not seem to work" was a CRM error nobody could read.
    // While the modal is up, the modal's own message slot carries it.
    if (!$("modal").hidden) {
      $("modalMsg").textContent = message || "";
      $("modalMsg").className = "ev__modal-msg" + (kind ? " ev__modal-msg--" + kind : "");
      return;
    }
    var box = $("notice");
    box.textContent = message;
    box.className = "ev__notice" + (kind ? " ev__notice--" + kind : "");
    box.hidden = !message;
    if (message) window.clearTimeout(notice._t);
    if (message) notice._t = window.setTimeout(function () { box.hidden = true; }, 8000);
  }

  function esc(value) { return (value == null ? "" : String(value)); }

  function fmtWhen(item) {
    if (!item.date) return "—";
    return (item.monthShort || "") + " " + (item.day || "") + " · " + (item.time || "");
  }

  function pct(rate) {
    return rate == null ? "—" : Math.round(rate * 100) + "%";
  }

  /* ---------- list ---------- */

  /* An event waiting for a human before it can go on the website.
   *
   * A recording link with the website flag off is exactly what the YouTube
   * import creates, and nothing else in this CRM looks like that — the entity
   * doubles as the organisation's internal calendar, and a team meeting has no
   * recording link. That precision is what makes the automatic switch below
   * safe: it can never land the grid on ninety internal meetings.
   *
   * Why this exists: the import creates events UNPUBLISHED on purpose, so a
   * person can check the date (a video's upload date is not the event date).
   * The grid then opened on "Published to the website" and hid every one of
   * them, so an import looked like it had done nothing. */
  function needsReview(e) {
    return !e.publishToWebsite && !!e.recordingUrl;
  }

  function visibleEvents() {
    var now = new Date().toISOString();
    var rows = state.events.filter(function (e) {
      if (state.scope === "review") return needsReview(e);
      if (state.scope === "published") return (e.state || {}).key !== "hidden";
      if (state.scope === "upcoming") return e.startsAtUtc && e.startsAtUtc >= now;
      if (state.scope === "past") return e.startsAtUtc && e.startsAtUtc < now;
      return true;
    });
    var needle = state.search.trim().toLowerCase();
    if (needle) {
      rows = rows.filter(function (e) {
        return [e.topic, e.summary, e.category, (e.categories || []).join(" "), e.status, e.format, e.location]
          .join(" ").toLowerCase().indexOf(needle) !== -1;
      });
    }
    var key = state.sort.key, dir = state.sort.dir;
    return rows.sort(function (a, b) {
      var av = sortValue(a, key), bv = sortValue(b, key);
      if (av === bv) return 0;
      return (av > bv ? 1 : -1) * dir;
    });
  }

  function sortValue(row, key) {
    var counts = row.summary_counts || {};
    if (key === "registered") return counts.registered || 0;
    if (key === "attended") return counts.attended || 0;
    if (key === "showRate") return counts.showRate == null ? -1 : counts.showRate;
    if (key === "published") return (row.state || {}).label || "";
    if (key === "recording") return row.recordingUrl ? 1 : 0;
    if (key === "name") return (row.topic || "").toLowerCase();
    return (row[key] || "").toString().toLowerCase();
  }

  function renderList() {
    var rows = visibleEvents();
    var body = $("eventRows");
    body.innerHTML = "";
    rows.forEach(function (item) {
      var counts = item.summary_counts || {};
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.addEventListener("click", function () { openEvent(item.id); });

      function cell(text, className) {
        var td = document.createElement("td");
        if (className) td.className = className;
        td.textContent = text;
        tr.appendChild(td);
        return td;
      }
      var nameCell = cell("");
      var strong = document.createElement("strong");
      strong.textContent = item.topic || "(untitled)";
      nameCell.appendChild(strong);
      // One chip per topic (F1-2); `category` alone is a row from a CRM that
      // still holds the single topic.
      var subjects = (item.categories && item.categories.length)
        ? item.categories : (item.category ? [item.category] : []);
      subjects.forEach(function (subject) {
        var chip = document.createElement("span");
        chip.className = "ev__chip";
        chip.textContent = subject;
        nameCell.appendChild(chip);
      });
      cell(fmtWhen(item));
      cell(item.format || "—");
      cell(item.status || "—");
      cell(counts.registered == null ? "—" : counts.registered, "num");
      cell(counts.attended == null ? "—" : counts.attended, "num");
      cell(pct(counts.showRate), "num");
      // Hidden · Appears <date> · Public · Internal · Internal, limited (F2/F3).
      cell((item.state || {}).label || (item.publishToWebsite ? "Shown" : "Hidden"));
      cell(item.recordingUrl ? "Yes" : "—");
      body.appendChild(tr);
    });
    $("listEmpty").hidden = rows.length > 0;
    $("listCount").textContent =
      rows.length + " of " + state.events.length + " event" + (state.events.length === 1 ? "" : "s");
    var waiting = state.events.filter(needsReview).length;
    var option = document.querySelector('#scopeFilter option[value="review"]');
    if (option) {
      option.textContent = waiting ? "Needs review (" + waiting + ")" : "Needs review";
    }
  }

  async function loadEvents() {
    var data = await api("/events");
    state.events = data.events || [];
    // Open on the work, when there is any — once, and only before the user has
    // chosen for themselves. Reloading the grid later must not yank them back
    // out of the view they picked.
    if (!state.scopeChosen && state.events.some(needsReview)) {
      state.scope = "review";
      $("scopeFilter").value = "review";
    }
    renderList();
  }

  /* ---------- detail ---------- */

  async function openEvent(id) {
    var data = await api("/events/" + id);
    state.current = data;
    $("listPanel").hidden = true;
    $("detailPanel").hidden = false;
    $("detailTitle").textContent = data.event.topic || "(untitled)";
    showTab("overview");
    renderOverview();
    renderRegistrants();
    renderRoster();
  }

  function backToList() {
    state.current = null;
    $("detailPanel").hidden = true;
    $("listPanel").hidden = false;
    loadEvents().catch(function (e) { notice(e.message, "error"); });
  }

  function showTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll(".ev__tab"), function (t) {
      t.classList.toggle("is-active", t.dataset.tab === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".ev__tabpanel"), function (p) {
      p.hidden = p.dataset.panel !== name;
    });
  }

  /* ---------- overview: the whole record, read-only ----------
   *
   * Staff check an event here without opening the editor (Doug, 2026-09-16):
   * everything the record holds is on this one screen. The facts column is
   * driven by the SAME field spec the editor is built from (/fields), in the
   * editor's group order, so a field added to the spec appears here without a
   * second edit — and one left out of the spec is not on the record at all.
   * The content column carries what the website shows: the graphic, the
   * Summary, the Full description and the Syllabus. */

  var CONTENT_GROUP = "Content";

  /* The stored value of one spec field, formatted for reading. Every type the
     spec uses has a case; "—" is the empty value everywhere, never a blank. */
  function factValue(spec, raw, event) {
    var value = raw[spec.name];
    if (spec.name === "audience" && !value) {
      // The carry-over rule (design § 3.1): an empty audience reads from the tick.
      return ((event.visibility || {}).audience || "—") + " (not set — read from Show this event)";
    }
    switch (spec.type) {
      case "datetime": return fmtStamp(value);
      case "duration":
        return window.CBMDateTime.formatDuration(
          window.CBMDateTime.durationBetween(raw.dateStart, raw.dateEnd)) || "—";
      case "bool": return value ? "Yes" : "No";
      case "multiEnum": {
        var picked = Array.isArray(value) ? value : [];
        if (!picked.length) {
          return spec.name === "internalTeams" ? "Every signed-in member" : "—";
        }
        return picked.map(function (v) { return optionLabel(spec.name, v); }).join(", ");
      }
      case "int":
        if (spec.name === "venueCapacity") return value ? String(value) : "Unlimited";
        return value == null || value === "" ? "—" : String(value);
      case "image":
        // Named even when absent: "none" is the answer to "why has the website
        // card got no picture?".
        return raw.eventGraphicId ? "uploaded (shown at right)"
          : "none — the card falls back to the recording thumbnail";
      case "url":
        if (spec.name === "recordingUrl" && !value) return "not published";
        return value || "—";
      case "varchar":
        if (spec.name === "zoomWebinarId" && !value) return "not created";
        return value || "—";
      default:
        return value == null || String(value).trim() === "" ? "—" : String(value);
    }
  }

  /* The CRM's display label for a stored option value (a chapter's full name
     for its short label), or the value itself when the CRM has none. */
  function optionLabel(fieldName, value) {
    var labels = state.optionLabels[fieldName] || {};
    return labels[value] || value;
  }

  /* The value a control starts with. An empty audience is read by the
     carry-over rule (ticked = Public, unticked = Internal), so the editor shows
     what the record effectively is rather than a blank (design § 3.1). A new
     event starts Public, reach this chapter — the server applies the same. */
  function initialValue(spec, raw) {
    var value = raw[spec.name];
    var isNew = !raw.id;
    if (spec.name === "audience" && !value) {
      var vis = (state.current && !isNew && state.current.event.visibility) || {};
      return vis.audience || "Public";
    }
    if (spec.name === "publicReach" && !value) return "This chapter";
    if (spec.name === "reachChapters") {
      var list = Array.isArray(value) ? value.slice() : [];
      if (state.chapterKey && list.indexOf(state.chapterKey) === -1) list.push(state.chapterKey);
      return list;
    }
    return value;
  }

  /* A CRM UTC stamp as local wall time, the way the editor's date control
     would show it. */
  function fmtStamp(stamp) {
    if (!stamp) return "—";
    var d = window.CBMDateTime.parseCrmStamp(stamp);
    if (!d) return String(stamp);
    return d.toLocaleDateString(undefined, { weekday: "short", year: "numeric",
                                             month: "short", day: "numeric" })
      + " · " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }

  function factRow(host, label, value) {
    var row = document.createElement("div");
    row.className = "ev__fact";
    var key = document.createElement("span");
    key.className = "ev__fact-key";
    key.textContent = label;
    var val = document.createElement("span");
    val.className = "ev__fact-value";
    if (/^https?:\/\//.test(value)) {
      var link = document.createElement("a");
      link.href = value; link.textContent = value;
      link.target = "_blank"; link.rel = "noopener";
      val.appendChild(link);
    } else {
      val.textContent = value;
    }
    row.appendChild(key); row.appendChild(val);
    host.appendChild(row);
  }

  function factGroup(host, label) {
    var head = document.createElement("h4");
    head.className = "ev__fact-group";
    head.textContent = label;
    host.appendChild(head);
  }

  /* Rich text authored in the CRM is HTML, and the website renders it as HTML
     — so this does too, through the shared sanitizer, because staff-authored
     is not the same as trusted. An empty field shows "—" rather than nothing. */
  function setRich(host, html) {
    var clean = window.CBMRichText ? window.CBMRichText.sanitizeHtml(html || "") : "";
    var probe = document.createElement("div");
    probe.innerHTML = clean;
    var empty = probe.textContent.trim() === "" && !probe.querySelector("img,table,hr");
    host.classList.toggle("ev__prose--empty", empty);
    if (empty) { host.textContent = "—"; return; }
    if (!window.CBMRichText) { host.textContent = html || ""; return; }
    host.innerHTML = clean;
  }

  function renderOverview() {
    var event = state.current.event, counts = state.current.counts || {};
    var raw = event.raw || {};
    var tiles = [
      ["Registered", counts.registered == null ? "—" : counts.registered],
      ["Attended", counts.attended == null ? "—" : counts.attended],
      ["Show rate", pct(counts.showRate)],
      ["Waitlisted", counts.waitlisted || 0],
      ["Seats left", counts.seatsRemaining == null ? "Unlimited" : counts.seatsRemaining],
    ];
    $("overviewTiles").innerHTML = "";
    tiles.forEach(function (pair) {
      var box = document.createElement("div");
      box.className = "ev__tile";
      var value = document.createElement("span");
      value.className = "ev__tile-value";
      value.textContent = pair[1];
      var label = document.createElement("span");
      label.className = "ev__tile-label";
      label.textContent = pair[0];
      box.appendChild(value); box.appendChild(label);
      $("overviewTiles").appendChild(box);
    });

    // --- facts: every spec field, in the editor's groups and order ---
    var host = $("overviewFacts");
    host.innerHTML = "";
    var lastGroup = null;
    state.fields.forEach(function (spec) {
      // The long-form content has its own column; the Summary goes with it.
      if (spec.group === CONTENT_GROUP && spec.type !== "image") return;
      if (spec.name === "description") return;
      if (spec.group !== lastGroup) {
        factGroup(host, spec.group);
        lastGroup = spec.group;
        if (spec.group === "Event") {
          // Not in the spec because it is the CRM's own workflow field, not
          // something the editor writes — but it is on the record.
          factRow(host, "Status", raw.status || "—");
        }
      }
      factRow(host, spec.label, factValue(spec, raw, event));
    });
    // What the app derives from the record, after what the record stores.
    factGroup(host, "On the website");
    factRow(host, "Public page", event.url || "—");
    factRow(host, "Registration", event.registrationOpen ? "Open" : "Closed");
    factRow(host, "When (as shown)", fmtWhen(event));
    // Phase B: who sponsors it. Every live link renders, "—" when empty, and
    // an unreadable link is "—" too rather than a false "none".
    if (state.links.length) {
      factGroup(host, state.links[0].group || "Sponsorship");
      var sponsors = state.current.sponsors || {};
      state.links.forEach(function (link) {
        var rows = sponsors[link.name];
        factRow(host, link.label, rows && rows.length
          ? rows.map(function (r) { return r.name; }).join(", ") : "—");
      });
    }
    // F4: who presents it, in order. null = the feature is off or the CRM
    // lacks the record type (no group at all); [] = none ("—").
    if (state.presenters.enabled && Array.isArray(state.current.presenters)) {
      factGroup(host, "Presenters");
      var people = state.current.presenters;
      if (!people.length) factRow(host, "Presenters", "—");
      people.forEach(function (p, i) {
        factRow(host, i === 0 ? "Presenters" : "",
          p.name + (p.title ? " — " + p.title : "") + (p.company ? ", " + p.company : ""));
      });
    }

    // --- content: what the website shows, read the way the website reads it ---
    var graphicId = raw.eventGraphicId || "";
    var img = $("overviewGraphic");
    if (graphicId && raw.id) {
      // Served through the app's staff proxy, so it also shows for an
      // unpublished event — the public route is gated on publishing.
      img.src = API + "/events/" + encodeURIComponent(raw.id)
        + "/graphic?v=" + encodeURIComponent(graphicId);
      img.hidden = false;
      $("overviewGraphicEmpty").hidden = true;
    } else {
      img.removeAttribute("src");
      img.hidden = true;
      $("overviewGraphicEmpty").hidden = false;
    }
    $("overviewSummary").textContent = event.summary || "—";
    setRich($("overviewDescription"), event.overview);
    setRich($("overviewSyllabus"), event.syllabus);
  }

  function registrantRows() {
    var needle = ($("regSearch").value || "").trim().toLowerCase();
    return (state.current.registrations || []).filter(function (r) {
      if (!needle) return true;
      return [r.firstName, r.lastName, r.email].join(" ").toLowerCase().indexOf(needle) !== -1;
    });
  }

  function renderRegistrants() {
    var rows = registrantRows();
    var body = $("regRows");
    body.innerHTML = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      function cell(text, className) {
        var td = document.createElement("td");
        if (className) td.className = className;
        td.textContent = text;
        tr.appendChild(td);
        return td;
      }
      cell(((r.firstName || "") + " " + (r.lastName || "")).trim() || "—");
      cell(r.email || "—");
      cell(r.attendanceStatus || "—");
      cell(r.registrationSource || "—");
      cell(r.minutesAttended == null ? "—" : r.minutesAttended, "num");

      var actions = document.createElement("td");
      actions.appendChild(rowButton("Attended", function () {
        setAttendance(r.id, "Attended");
      }));
      actions.appendChild(rowButton("No-show", function () {
        setAttendance(r.id, "No-Show");
      }));
      actions.appendChild(rowButton("Cancel", function () {
        cancelRegistration(r.id);
      }));
      tr.appendChild(actions);
      body.appendChild(tr);
    });
    $("regEmpty").hidden = rows.length > 0;
  }

  function rowButton(label, onClick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "ev__rowbtn";
    button.textContent = label;
    button.addEventListener("click", function (e) { e.stopPropagation(); onClick(); });
    return button;
  }

  function renderRoster() {
    var needle = ($("checkinSearch").value || "").trim().toLowerCase();
    var host = $("roster");
    host.innerHTML = "";
    (state.current.registrations || [])
      .filter(function (r) {
        if (!needle) return true;
        return [r.firstName, r.lastName, r.email].join(" ").toLowerCase().indexOf(needle) !== -1;
      })
      .forEach(function (r) {
        var li = document.createElement("li");
        li.className = "ev__rosteritem" + (r.attendanceStatus === "Attended" ? " is-in" : "");
        var who = document.createElement("span");
        who.className = "ev__rostername";
        who.textContent = ((r.firstName || "") + " " + (r.lastName || "")).trim() || r.email || "—";
        li.appendChild(who);
        var action = document.createElement("button");
        action.type = "button";
        action.className = "cbm-button" + (r.attendanceStatus === "Attended" ? " cbm-button--secondary" : "");
        action.textContent = r.attendanceStatus === "Attended" ? "Here ✓" : "Check in";
        action.addEventListener("click", function () { checkIn(r.id); });
        li.appendChild(action);
        host.appendChild(li);
      });
  }

  function activeTab() {
    var tab = document.querySelector(".ev__tab.is-active");
    return tab ? tab.dataset.tab : "overview";
  }

  async function refreshDetail() {
    if (!state.current) return;
    // Keep the operator where they were. Bouncing back to Overview after every
    // check-in means re-clicking the tab for each person in the queue.
    var tab = activeTab();
    await openEvent(state.current.event.id);
    showTab(tab);
  }

  /* ---------- writes ---------- */

  async function setAttendance(id, status) {
    try {
      await api("/registrations/" + id + "/attendance", {
        method: "PUT", body: JSON.stringify({ status: status }),
      });
      notice("Attendance recorded.", "ok");
      await refreshDetail();
    } catch (e) { notice(e.message, "error"); }
  }

  async function checkIn(id) {
    try {
      await api("/registrations/" + id + "/checkin", { method: "POST" });
      await refreshDetail();
    } catch (e) { notice(e.message, "error"); }
  }

  async function cancelRegistration(id) {
    try {
      var result = await api("/registrations/" + id + "/cancel", { method: "POST" });
      notice(result.promoted
        ? "Cancelled — the next person on the waitlist has been given the seat."
        : "Registration cancelled.", "ok");
      await refreshDetail();
    } catch (e) { notice(e.message, "error"); }
  }

  /* ---------- modal ---------- */

  var modalSave = null;

  function openModal(title, bodyBuilder, onSave, saveLabel, opts) {
    opts = opts || {};
    $("modalTitle").textContent = title;
    $("modalBody").innerHTML = "";
    $("modalMsg").textContent = "";
    // A record editor opens as a full workspace; a four-field dialog does not.
    // Clear any size the user dragged onto the card last time, or the compact
    // dialog inherits the editor's 80vw.
    var card = document.querySelector(".ev__modal");
    card.classList.toggle("ev__modal--wide", !!opts.wide);
    card.style.width = ""; card.style.height = "";
    bodyBuilder($("modalBody"));
    $("modalSave").textContent = saveLabel || "Save";
    modalSave = onSave;
    $("modal").hidden = false;
    $("modalBody").scrollTop = 0;
  }

  function closeModal() { $("modal").hidden = true; modalSave = null; }

  /* One control per field spec. `opts.big` marks a field the spec wants to give
     room to; the layout classes carry that through to the stylesheet. */
  function field(host, name, label, type, value, options, help, opts) {
    opts = opts || {};
    // A group of checkboxes cannot sit inside one <label>: a click anywhere in
    // it would toggle the first box.
    var wrap = document.createElement(type === "multiEnum" ? "div" : "label");
    wrap.className = "ev__field ev__field--" + type;
    if (opts.big) wrap.classList.add("ev__field--wide");
    var caption = document.createElement("span");
    caption.textContent = label;
    wrap.appendChild(caption);
    var input;
    if (type === "enum") {
      input = document.createElement("select");
      var blank = document.createElement("option");
      blank.value = ""; blank.textContent = "—";
      input.appendChild(blank);
      (options || []).forEach(function (option) {
        var node = document.createElement("option");
        node.value = option; node.textContent = optionLabel(name, option);
        if (option === value) node.selected = true;
        input.appendChild(node);
      });
    } else if (type === "multiEnum") {
      // A row of checkboxes. The group carries the name; the boxes do not, so
      // collectForm reads the group once and gets a list.
      input = document.createElement("div");
      input.className = "ev__multi";
      var chosen = Array.isArray(value) ? value : [];
      var known = (options || []).slice();
      // A stored value no longer offered stays visible (and is dropped by the
      // server on save, because the CRM would refuse the whole save for it).
      chosen.forEach(function (v) { if (known.indexOf(v) === -1) known.push(v); });
      known.forEach(function (option) {
        var item = document.createElement("label");
        item.className = "ev__multi-item";
        var box = document.createElement("input");
        box.type = "checkbox";
        box.value = option;
        box.checked = chosen.indexOf(option) !== -1;
        var text = document.createElement("span");
        var gone = (options || []).indexOf(option) === -1;
        text.textContent = optionLabel(name, option) + (gone ? " (no longer an option)" : "");
        item.appendChild(box); item.appendChild(text);
        input.appendChild(item);
      });
      if (!known.length) {
        var none = document.createElement("small");
        none.textContent = "The CRM offers no options for this field yet.";
        input.appendChild(none);
      }
    } else if (type === "bool") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = !!value;
      wrap.classList.add("ev__field--check");
    } else if (type === "wysiwyg") {
      // The standard rich-text editor product-wide (CBMRichText/Jodit) — these
      // fields hold the website's own event copy, and staff were typing raw
      // HTML into a textarea. create() returns null when the vendor bundle
      // hasn't loaded, so the plain textarea stays as the fallback.
      input = window.CBMRichText
        && window.CBMRichText.create(value == null ? "" : String(value), { minHeight: 280 });
      if (!input) {
        input = document.createElement("textarea");
        input.rows = 14;
        input.value = value == null ? "" : value;
        type = "text";   // read back as a plain value below
      }
    } else if (type === "text") {
      input = document.createElement("textarea");
      input.rows = opts.big ? 5 : 3;
      input.value = value == null ? "" : value;
    } else if (type === "duration") {
      // The shared Duration control — human-labelled presets, matching the
      // session editor. `value` arrives already in seconds (see eventForm).
      input = window.CBMDateTime.createDuration({ value: value, options: options });
    } else if (type === "datetime") {
      // The shared CBMDateTime control (frontend/shared/datetime.js). It owns
      // the local<->UTC conversion; a raw datetime-local input does not, which
      // is how every event created before v0.192.2 was stored four hours early.
      input = window.CBMDateTime.create({ value: value });
    } else {
      input = document.createElement("input");
      input.type = type === "int" ? "number" : "text";
      input.value = value == null ? "" : value;
    }
    // setAttribute, not `.name =` — the datetime control is a <div>, where the
    // property is inert and querySelectorAll("[name]") would never see it.
    input.setAttribute("name", name);
    input.dataset.type = type;
    wrap.appendChild(input);
    if (help) {
      var hint = document.createElement("small");
      hint.textContent = help;
      wrap.appendChild(hint);
    }
    host.appendChild(wrap);
    return input;
  }

  /* The website card image. A CRM file field can't ride the generic field PUT,
     so it gets its own control and its own endpoint — and, since the browser
     can't reach EspoCRM, the preview is proxied by the app. */
  function graphicField(host, raw, spec) {
    var wrap = document.createElement("div");
    wrap.className = "ev__field ev__field--graphic";
    var caption = document.createElement("span");
    caption.textContent = spec.label;
    wrap.appendChild(caption);

    if (!raw.id) {
      var later = document.createElement("small");
      later.textContent = "Save the event first, then add its graphic here.";
      wrap.appendChild(later);
      host.appendChild(wrap);
      return;
    }

    var preview = document.createElement("img");
    preview.className = "ev__graphic";
    preview.alt = "";
    function showPreview() {
      if (raw.eventGraphicId) {
        preview.src = API + "/events/" + encodeURIComponent(raw.id)
          + "/graphic?v=" + encodeURIComponent(raw.eventGraphicId);
        preview.hidden = false;
      } else {
        preview.removeAttribute("src");
        preview.hidden = true;
      }
    }
    showPreview();
    wrap.appendChild(preview);

    // The browser's own file input is the one control here that can't be made
    // to look like CBM, so it is hidden and driven by a real CBM button; the
    // chosen filename is reported beside it so nothing is lost by hiding it.
    var file = document.createElement("input");
    file.type = "file";
    file.className = "ev__filepick";
    file.accept = "image/png,image/jpeg,image/webp,image/gif";
    file.tabIndex = -1;
    wrap.appendChild(file);

    var actions = document.createElement("div");
    actions.className = "ev__graphicactions";
    function button(label) {
      var node = document.createElement("button");
      node.type = "button";
      node.className = "cbm-button cbm-button--secondary";
      node.textContent = label;
      actions.appendChild(node);
      return node;
    }
    var choose = button("Choose image…");
    var upload = button("Upload graphic");
    var remove = button("Remove graphic");
    var chosenName = document.createElement("span");
    chosenName.className = "ev__filename";
    chosenName.textContent = "No image chosen";
    actions.appendChild(chosenName);
    wrap.appendChild(actions);

    choose.addEventListener("click", function () { file.click(); });
    file.addEventListener("change", function () {
      var picked = file.files && file.files[0];
      chosenName.textContent = picked ? picked.name : "No image chosen";
    });

    // Never disabled — validate on click and say what is missing.
    upload.addEventListener("click", function () {
      var chosen = file.files && file.files[0];
      if (!chosen) { notice("Choose an image file first.", "warn"); return; }
      var reader = new FileReader();
      reader.onload = async function () {
        var base64 = String(reader.result || "").split(",")[1] || "";
        try {
          var result = await api("/events/" + encodeURIComponent(raw.id) + "/graphic", {
            method: "POST",
            body: JSON.stringify({
              filename: chosen.name,
              contentType: chosen.type,
              dataBase64: base64,
            }),
          });
          raw.eventGraphicId = (result.raw || {}).eventGraphicId || "";
          showPreview();
          // Refresh the record behind the modal so the Overview tab shows the
          // new picture immediately, whether or not the form is then saved.
          if (state.current) renderOverview();
          notice("Graphic saved.", "ok");
        } catch (err) { notice(err.message, "error"); }
      };
      reader.readAsDataURL(chosen);
    });

    remove.addEventListener("click", async function () {
      if (!raw.eventGraphicId) { notice("This event has no graphic.", "warn"); return; }
      try {
        await api("/events/" + encodeURIComponent(raw.id) + "/graphic", { method: "DELETE" });
        raw.eventGraphicId = "";
        file.value = "";
        chosenName.textContent = "No image chosen";
        showPreview();
        if (state.current) renderOverview();
        notice("Graphic removed.", "ok");
      } catch (err) { notice(err.message, "error"); }
    });

    if (spec.help) {
      var hint = document.createElement("small");
      hint.textContent = spec.help;
      wrap.appendChild(hint);
    }
    host.appendChild(wrap);
  }

  function eventForm(host, raw) {
    raw = raw || {};
    var groups = {};
    state.fields.forEach(function (spec) {
      // App-managed fields (slug, Zoom ids) are the app's business — except the
      // graphic, which is app-managed only because it uploads separately, and a
      // field the spec unlocks under a condition (the Join URL, Internal events
      // only), which renders as a control shown under that condition.
      if (spec.hidden) return;   // derived, not entered (dateEnd)
      if (spec.appManaged && spec.type !== "image" && !spec.editableWhen) return;
      (groups[spec.group] = groups[spec.group] || []).push(spec);
    });
    Object.keys(groups).forEach(function (groupName) {
      var section = document.createElement("fieldset");
      section.className = "ev__group";
      var legend = document.createElement("legend");
      legend.textContent = groupName;
      section.appendChild(legend);
      groups[groupName].forEach(function (spec) {
        if (spec.type === "image") { graphicField(section, raw, spec); return; }
        var value = initialValue(spec, raw);
        if (spec.type === "duration") {
          // `duration` is VIRTUAL in EspoCRM (dateEnd - dateStart) and is often
          // null on the record, so derive it rather than trusting the field.
          value = window.CBMDateTime.durationBetween(raw.dateStart, raw.dateEnd);
        }
        var control = field(section, spec.name, spec.label, spec.type, value,
                            state.options[spec.name], spec.help, { big: spec.big });
        var rule = spec.showWhen || spec.editableWhen;
        if (rule) control.closest(".ev__field").dataset.showWhen = JSON.stringify(rule);
      });
      host.appendChild(section);
    });
    sponsorshipGroup(host, raw);
    presentersGroup(host, raw);
    applyShowWhen(host);
    host.addEventListener("change", function () { applyShowWhen(host); });
  }

  /* Phase B — who sponsors this event. One checkbox list per link the live CRM
     has (Partners, Funders), with a filter box because a chapter can hold a
     few dozen partners. These are RELATIONSHIPS: collectForm skips them and
     saveSponsors() sends the exact set to its own endpoint. A role that may
     not list the far entity (options === null) gets the current names and an
     explanation rather than an empty list that reads as "no partners". */
  function sponsorshipGroup(host, raw) {
    if (!state.links.length) return;
    var current = (state.current && raw.id && state.current.sponsors) || {};
    var section = document.createElement("fieldset");
    section.className = "ev__group";
    var legend = document.createElement("legend");
    legend.textContent = state.links[0].group || "Sponsorship";
    section.appendChild(legend);
    state.links.forEach(function (link) {
      var chosen = (current[link.name] || []).map(function (r) { return r.id; });
      var wrap = document.createElement("div");
      wrap.className = "ev__field ev__field--link ev__field--wide";
      var caption = document.createElement("span");
      caption.textContent = link.label;
      wrap.appendChild(caption);
      var box = document.createElement("div");
      box.className = "ev__linkpick";
      box.setAttribute("name", link.name);
      box.dataset.type = "link";
      if (link.options === null) {
        // Read-only: the user's CRM role cannot list the far entity.
        box.dataset.readonly = "1";
        var names = (current[link.name] || []).map(function (r) { return r.name; });
        var note = document.createElement("small");
        note.textContent = (names.length ? names.join(", ") + ". " : "")
          + "Your CRM role cannot list " + link.label.toLowerCase()
          + ", so this cannot be changed here.";
        box.appendChild(note);
      } else {
        var filter = document.createElement("input");
        filter.type = "search";
        filter.placeholder = "Filter " + link.label.toLowerCase() + "…";
        filter.className = "ev__linkpick-filter";
        filter.setAttribute("aria-label", "Filter " + link.label.toLowerCase());
        box.appendChild(filter);
        var list = document.createElement("div");
        list.className = "ev__multi ev__linkpick-list";
        var known = link.options.slice();
        // A linked record the list no longer offers stays visible (and selected),
        // the same rule as a multi-choice value that has drifted out of its enum.
        (current[link.name] || []).forEach(function (r) {
          if (!known.some(function (o) { return o.id === r.id; })) known.push(r);
        });
        known.forEach(function (option) {
          var item = document.createElement("label");
          item.className = "ev__multi-item";
          var check = document.createElement("input");
          check.type = "checkbox";
          check.value = option.id;
          check.checked = chosen.indexOf(option.id) !== -1;
          var text = document.createElement("span");
          text.textContent = option.name;
          item.appendChild(check); item.appendChild(text);
          list.appendChild(item);
        });
        if (!known.length) {
          var none = document.createElement("small");
          none.textContent = "The CRM has no " + link.label.toLowerCase() + " yet.";
          list.appendChild(none);
        }
        filter.addEventListener("input", function () {
          var needle = filter.value.trim().toLowerCase();
          Array.prototype.forEach.call(list.querySelectorAll(".ev__multi-item"), function (item) {
            var hit = !needle || item.textContent.toLowerCase().indexOf(needle) !== -1;
            // A ticked item never hides, or the filter would silently drop it from view.
            item.hidden = !(hit || item.querySelector("input").checked);
          });
        });
        box.appendChild(list);
      }
      wrap.appendChild(box);
      section.appendChild(wrap);
    });
    host.appendChild(section);
  }

  /* The exact set per EDITABLE link, or null when the form has no pickers. */
  function collectLinks() {
    var picks = $("modalBody").querySelectorAll('[data-type="link"]');
    if (!picks.length) return null;
    var out = {};
    Array.prototype.forEach.call(picks, function (box) {
      if (box.dataset.readonly) return;
      out[box.getAttribute("name")] = Array.prototype.filter.call(
        box.querySelectorAll('input[type="checkbox"]'), function (b) { return b.checked; }
      ).map(function (b) { return b.value; });
    });
    return out;
  }

  function sameIds(a, b) {
    var x = (a || []).slice().sort(), y = (b || []).slice().sort();
    return x.length === y.length && x.every(function (v, i) { return v === y[i]; });
  }

  /* Send the pickers' sets when they differ from what the record held. Its own
     request: a relationship cannot ride the record PUT. Errors surface as the
     notice — the event itself has already saved. */
  async function saveSponsors(eventId, picked, before) {
    if (!picked) return null;
    var changed = {};
    Object.keys(picked).forEach(function (name) {
      var had = ((before || {})[name] || []).map(function (r) { return r.id; });
      if (!sameIds(had, picked[name])) changed[name] = picked[name];
    });
    if (!Object.keys(changed).length) return null;
    return api("/events/" + encodeURIComponent(eventId) + "/sponsors", {
      method: "PUT", body: JSON.stringify({ links: changed }),
    });
  }

  /* Conditional fields (F2/F3): Reach only for a Public event, Chapters only
     for a Selected reach, the team limit and Takes registrations only for an
     Internal one. A field is shown when the field it depends on is itself shown
     and holds one of the listed values — so Chapters disappears with Reach when
     the event turns Internal. Hidden controls keep their values and are still
     posted; the server applies the rules. */
  function applyShowWhen(host) {
    var wraps = Array.prototype.slice.call(host.querySelectorAll("[data-show-when]"));
    function controlOf(name) { return host.querySelector('[name="' + name + '"]'); }
    function isShown(wrap) {
      var rule = JSON.parse(wrap.dataset.showWhen);
      var parent = controlOf(rule.field);
      if (!parent) return false;
      var parentWrap = parent.closest(".ev__field");
      if (parentWrap && parentWrap.dataset.showWhen && !isShown(parentWrap)) return false;
      return rule.values.indexOf(parent.value) !== -1;
    }
    wraps.forEach(function (wrap) { wrap.hidden = !isShown(wrap); });
  }

  function collectForm() {
    var changes = {};
    Array.prototype.forEach.call($("modalBody").querySelectorAll("[name]"), function (input) {
      var type = input.dataset.type;
      var value;
      if (type === "link") return;   // relationships go through saveSponsors()
      if (type === "bool") value = input.checked;
      else if (type === "multiEnum") {
        value = Array.prototype.filter.call(
          input.querySelectorAll('input[type="checkbox"]'), function (b) { return b.checked; }
        ).map(function (b) { return b.value; });
      }
      else if (type === "int") value = input.value === "" ? null : parseInt(input.value, 10);
      else if (type === "duration") value = window.CBMDateTime.readDuration(input);
      else if (type === "datetime") value = window.CBMDateTime.read(input);
      // The rich-text host is a <div>: its value lives on the control, and
      // getValue() re-sanitizes and returns "" for an untouched empty editor.
      else if (type === "wysiwyg") {
        value = input._cbmRichText ? input._cbmRichText.getValue() : input.value;
      }
      else value = input.value;
      changes[input.getAttribute("name")] = value;
    });
    // `duration` is VIRTUAL in the CRM (dateEnd - dateStart), so sending it
    // stores nothing — which is why every event kept a null duration AND a null
    // dateEnd until v0.192.4. Translate it into the recomputed dateEnd, the same
    // way the session editor does, and drop the virtual field.
    if (changes.duration != null && changes.dateStart) {
      var end = window.CBMDateTime.endStamp(changes.dateStart, changes.duration);
      if (end) changes.dateEnd = end;
    }
    delete changes.duration;
    return changes;
  }

  /* ---------- reports (EV-73 / EV-74) ---------- */

  function tile(host, label, value) {
    var box = document.createElement("div");
    box.className = "ev__tile";
    var v = document.createElement("span");
    v.className = "ev__tile-value";
    v.textContent = value;
    var l = document.createElement("span");
    l.className = "ev__tile-label";
    l.textContent = label;
    box.appendChild(v); box.appendChild(l);
    host.appendChild(box);
  }

  function pctOrDash(rate) {
    return rate == null ? "—" : Math.round(rate * 100) + "%";
  }

  function showReports() {
    $("listPanel").hidden = true;
    $("detailPanel").hidden = true;
    $("reportsPanel").hidden = false;
    if (!$("repFrom").value) {
      // Default to the last twelve months — the period staff actually ask about.
      var to = new Date();
      var from = new Date(to.getFullYear() - 1, to.getMonth(), to.getDate());
      $("repFrom").value = from.toISOString().slice(0, 10);
      $("repTo").value = to.toISOString().slice(0, 10);
    }
    runReports();
  }

  async function runReports() {
    var qs = "?start=" + encodeURIComponent($("repFrom").value || "")
           + "&end=" + encodeURIComponent($("repTo").value || "");
    $("repStatus").textContent = "Working…";
    try {
      var totals = await api("/reports/program" + qs);
      var host = $("repTotals");
      host.innerHTML = "";
      tile(host, "Events held", totals.eventsHeld);
      tile(host, "Unique attendees", totals.uniqueAttendees);
      tile(host, "Total attendances", totals.totalAttendances);
      tile(host, "Came more than once", totals.repeatAttendees);
      tile(host, "Repeat rate", pctOrDash(totals.repeatRate));

      var conv = await api("/reports/conversion" + qs);
      var chost = $("repConvTiles");
      chost.innerHTML = "";
      tile(chost, "Attendees", conv.attendees);
      tile(chost, "Became clients", conv.converted);
      tile(chost, "Conversion rate", pctOrDash(conv.conversionRate));

      var body = $("repConvRows");
      body.innerHTML = "";
      (conv.rows || []).forEach(function (r) {
        var tr = document.createElement("tr");
        [r.engagement || "(unnamed)", r.status || "—",
         (r.firstAttendedUtc || "").slice(0, 10),
         (r.engagementCreatedUtc || "").slice(0, 10)].forEach(function (text) {
          var td = document.createElement("td");
          td.textContent = text;
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
      $("repConvTable").hidden = !(conv.rows || []).length;
      $("repConvEmpty").hidden = !!(conv.rows || []).length;
      $("repStatus").textContent = "";
    } catch (e) {
      $("repStatus").textContent = "";
      notice(e.message, "error");
    }
  }

  /* ---------- presenters (Track F, F4) ----------
     Who presents this event. Entries are RECORDS (CEventPresenter) saved as
     they are edited through their own endpoints, independent of the event
     form's Save — the graphic's pattern, not the sponsors'. Nothing in this
     group carries a [name] attribute: collectForm must never read these as
     event fields. Design: prds/events/CBM_Events_Presenters_Design.md § 4. */

  function presentersGroup(host, raw) {
    var info = state.presenters || {};
    if (!info.enabled) return;
    var section = document.createElement("fieldset");
    section.className = "ev__group ev__group--presenters";
    var legend = document.createElement("legend");
    legend.textContent = "Presenters";
    section.appendChild(legend);
    var note = document.createElement("small");
    note.className = "ev__presenters-note";
    if (!info.available) {
      note.textContent = "Presenters need the CEventPresenter record type in this CRM — see the Events CRM handoff.";
      section.appendChild(note); host.appendChild(section); return;
    }
    if (!raw.id) {
      note.textContent = "Save the event first, then add its presenters here.";
      section.appendChild(note); host.appendChild(section); return;
    }
    var list = document.createElement("div");
    list.className = "ev__presenters";
    section.appendChild(list);
    renderPresenterList(list, raw);
    presenterAdd(section, raw, list);
    host.appendChild(section);
  }

  function presenterRows() {
    return (state.current && Array.isArray(state.current.presenters)) ? state.current.presenters : [];
  }

  async function reloadPresenters(raw, list) {
    var data = await api("/events/" + encodeURIComponent(raw.id) + "/presenters");
    if (state.current) state.current.presenters = data.presenters || [];
    renderPresenterList(list, raw);
    if (state.current) renderOverview();
  }

  function renderPresenterList(list, raw) {
    list.innerHTML = "";
    var rows = presenterRows();
    if (!rows.length) {
      var empty = document.createElement("small");
      empty.textContent = "No presenters yet.";
      list.appendChild(empty);
      return;
    }
    rows.forEach(function (p, i) { list.appendChild(presenterCard(p, i, rows.length, raw, list)); });
  }

  function presenterMedia(p, size) {
    var media = document.createElement("div");
    media.className = "ev__presenter-media";
    if (p.photoUrl) {
      var img = document.createElement("img");
      img.className = "ev__presenter-photo";
      img.alt = "";
      img.src = p.photoUrl;
      media.appendChild(img);
    } else {
      var initials = document.createElement("span");
      initials.className = "ev__presenter-initials";
      var parts = String(p.name || "").trim().split(/\s+/).filter(Boolean);
      initials.textContent = (parts.length ? parts[0][0] : "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
      media.appendChild(initials);
    }
    return media;
  }

  function smallButton(label, cls) {
    var node = document.createElement("button");
    node.type = "button";
    node.className = "cbm-button cbm-button--secondary ev__presenter-btn" + (cls ? " " + cls : "");
    node.textContent = label;
    return node;
  }

  function presenterCard(p, index, total, raw, list) {
    var card = document.createElement("div");
    card.className = "ev__presenter";
    card.appendChild(presenterMedia(p));
    var body = document.createElement("div");
    body.className = "ev__presenter-body";
    var name = document.createElement("strong");
    name.textContent = p.name || "(unnamed)";
    body.appendChild(name);
    var role = [p.title, p.company].filter(Boolean).join(" · ");
    var roleLine = document.createElement("div");
    roleLine.className = "ev__presenter-role";
    roleLine.textContent = role || "—";
    body.appendChild(roleLine);
    var bioLine = document.createElement("div");
    bioLine.className = "ev__presenter-biopreview";
    var tmp = document.createElement("div");
    tmp.innerHTML = p.biography || "";
    var text = (tmp.textContent || "").trim();
    bioLine.textContent = text ? (text.length > 140 ? text.slice(0, 140) + "…" : text) : "No biography yet.";
    body.appendChild(bioLine);
    card.appendChild(body);

    var actions = document.createElement("div");
    actions.className = "ev__presenter-actions";
    var up = smallButton("Up"), down = smallButton("Down"), edit = smallButton("Edit"), remove = smallButton("Remove");
    [up, down, edit, remove].forEach(function (b) { actions.appendChild(b); });
    card.appendChild(actions);

    // Never disabled: an edge move explains itself.
    async function move(delta) {
      var ids = presenterRows().map(function (r) { return r.id; });
      var to = index + delta;
      if (to < 0 || to >= ids.length) { notice(delta < 0 ? "Already first." : "Already last.", "warn"); return; }
      ids.splice(to, 0, ids.splice(index, 1)[0]);
      try {
        await api("/events/" + encodeURIComponent(raw.id) + "/presenters/order", {
          method: "PUT", body: JSON.stringify({ ids: ids }),
        });
        await reloadPresenters(raw, list);
      } catch (err) { notice(err.message, "error"); }
    }
    up.addEventListener("click", function () { move(-1); });
    down.addEventListener("click", function () { move(1); });
    edit.addEventListener("click", function () { presenterEditor(card, p, raw, list); });
    remove.addEventListener("click", function () {
      // One-line confirmation in place, the rail's pattern.
      actions.innerHTML = "";
      var q = document.createElement("span");
      q.className = "ev__presenter-confirm";
      q.textContent = "Remove " + (p.name || "this presenter") + " from this event?";
      var yes = smallButton("Yes"), no = smallButton("No");
      actions.appendChild(q); actions.appendChild(yes); actions.appendChild(no);
      no.addEventListener("click", function () { renderPresenterList(list, raw); });
      yes.addEventListener("click", async function () {
        try {
          await api("/events/" + encodeURIComponent(raw.id) + "/presenters/" + encodeURIComponent(p.id), { method: "DELETE" });
          notice("Presenter removed.", "ok");
          await reloadPresenters(raw, list);
        } catch (err) { notice(err.message, "error"); }
      });
    });
    return card;
  }

  /* Edit in place: title, company, the biography in the shared rich-text
     editor WITHOUT an uploadImage hook (public text; its readers cannot reach
     the attachment proxy — the mentor-biography rule), and the photo, which
     uploads at once like the event graphic. */
  function presenterEditor(card, p, raw, list) {
    card.innerHTML = "";
    card.classList.add("ev__presenter--editing");
    var base = "/events/" + encodeURIComponent(raw.id) + "/presenters/" + encodeURIComponent(p.id);

    var photoWrap = document.createElement("div");
    photoWrap.className = "ev__presenter-photoedit";
    var media = presenterMedia(p);
    photoWrap.appendChild(media);
    var file = document.createElement("input");
    file.type = "file"; file.className = "ev__filepick";
    file.accept = "image/png,image/jpeg,image/webp,image/gif"; file.tabIndex = -1;
    photoWrap.appendChild(file);
    var choose = smallButton("Choose photo…"), uploadBtn = smallButton("Upload photo"), clearBtn = smallButton("Remove photo");
    var chosenName = document.createElement("span");
    chosenName.className = "ev__filename"; chosenName.textContent = "No image chosen";
    var photoActions = document.createElement("div");
    photoActions.className = "ev__graphicactions";
    [choose, uploadBtn, clearBtn, chosenName].forEach(function (n) { photoActions.appendChild(n); });
    photoWrap.appendChild(photoActions);
    choose.addEventListener("click", function () { file.click(); });
    file.addEventListener("change", function () {
      var picked = file.files && file.files[0];
      chosenName.textContent = picked ? picked.name : "No image chosen";
    });
    uploadBtn.addEventListener("click", function () {
      var chosen = file.files && file.files[0];
      if (!chosen) { notice("Choose an image file first.", "warn"); return; }
      var reader = new FileReader();
      reader.onload = async function () {
        var base64 = String(reader.result || "").split(",")[1] || "";
        try {
          var result = await api(base + "/photo", {
            method: "POST",
            body: JSON.stringify({ filename: chosen.name, contentType: chosen.type, dataBase64: base64 }),
          });
          p = result.presenter || p;
          photoWrap.replaceChild(presenterMedia(p), media); media = photoWrap.firstChild;
          notice("Photo saved. The mentor's own profile photo is unchanged.", "ok");
        } catch (err) { notice(err.message, "error"); }
      };
      reader.readAsDataURL(chosen);
    });
    clearBtn.addEventListener("click", async function () {
      if (!p.photoUrl) { notice("This presenter has no photo.", "warn"); return; }
      try {
        var result = await api(base + "/photo", { method: "DELETE" });
        p = result.presenter || p;
        photoWrap.replaceChild(presenterMedia(p), media); media = photoWrap.firstChild;
        notice("Photo removed.", "ok");
      } catch (err) { notice(err.message, "error"); }
    });
    card.appendChild(photoWrap);

    var form = document.createElement("div");
    form.className = "ev__presenter-form";
    var heading = document.createElement("strong");
    heading.textContent = p.name || "(unnamed)";
    form.appendChild(heading);
    function textInput(label, value) {
      var wrap = document.createElement("label");
      wrap.className = "ev__field";
      var cap = document.createElement("span"); cap.textContent = label; wrap.appendChild(cap);
      var input = document.createElement("input");
      input.type = "text"; input.value = value || "";
      wrap.appendChild(input); form.appendChild(wrap);
      return input;
    }
    var title = textInput("Title", p.title);
    var company = textInput("Company", p.company);
    var bioWrap = document.createElement("div");
    bioWrap.className = "ev__field ev__field--wide";
    var bioCap = document.createElement("span"); bioCap.textContent = "Biography (for this event)"; bioWrap.appendChild(bioCap);
    var bio = window.CBMRichText && window.CBMRichText.create(p.biography || "", { minHeight: 180 });
    if (!bio) { bio = document.createElement("textarea"); bio.rows = 8; bio.value = p.biography || ""; }
    bioWrap.appendChild(bio);
    var hint = document.createElement("small");
    hint.textContent = "Copied once from a mentor's profile when they were added; edit it for this event. It is never updated from the profile, and images are not allowed here.";
    bioWrap.appendChild(hint);
    form.appendChild(bioWrap);

    var buttons = document.createElement("div");
    buttons.className = "ev__presenter-actions";
    var save = smallButton("Save presenter", "cbm-button--primary"), cancel = smallButton("Cancel");
    buttons.appendChild(save); buttons.appendChild(cancel);
    form.appendChild(buttons);
    card.appendChild(form);

    cancel.addEventListener("click", function () { renderPresenterList(list, raw); });
    save.addEventListener("click", async function () {
      var changes = {
        presenterTitle: title.value,
        presenterCompany: company.value,
        biography: bio._cbmRichText ? bio._cbmRichText.getValue() : bio.value,
      };
      try {
        await api(base, { method: "PUT", body: JSON.stringify({ changes: changes }) });
        notice("Presenter saved.", "ok");
        await reloadPresenters(raw, list);
      } catch (err) { notice(err.message, "error"); }
    });
  }

  /* Add a presenter: search the CRM's Contacts by name or email, or add a
     new person — found by email and reused, else created (F4-3). */
  function presenterAdd(section, raw, list) {
    var box = document.createElement("div");
    box.className = "ev__presenters-add";
    var cap = document.createElement("span");
    cap.className = "ev__presenters-addcap";
    cap.textContent = "Add a presenter";
    box.appendChild(cap);
    var search = document.createElement("input");
    search.type = "search"; search.className = "ev__presenters-search";
    search.placeholder = "Search contacts by name or email…";
    box.appendChild(search);
    var results = document.createElement("div");
    results.className = "ev__presenters-results";
    box.appendChild(results);

    var timer = null;
    search.addEventListener("input", function () {
      clearTimeout(timer);
      var q = search.value.trim();
      if (q.length < 2) { results.innerHTML = ""; return; }
      timer = setTimeout(async function () {
        try {
          var data = await api("/presenters/search?q=" + encodeURIComponent(q));
          results.innerHTML = "";
          var rows = data.contacts || [];
          if (!rows.length) {
            var none = document.createElement("small");
            none.textContent = "No contact matches. Add them as a new presenter below.";
            results.appendChild(none);
          }
          rows.forEach(function (c) {
            var hit = document.createElement("button");
            hit.type = "button"; hit.className = "ev__presenters-hit";
            hit.textContent = c.name + (c.email ? " — " + c.email : "") + (c.company ? " · " + c.company : "") + (c.isMentor ? "  [Mentor]" : "");
            hit.addEventListener("click", function () { addPresenter({ contactId: c.id }); });
            results.appendChild(hit);
          });
        } catch (err) { notice(err.message, "error"); }
      }, 250);
    });

    var newToggle = smallButton("+ New presenter");
    box.appendChild(newToggle);
    var form = document.createElement("div");
    form.className = "ev__presenters-newform";
    form.hidden = true;
    function input(label, type) {
      var wrap = document.createElement("label");
      wrap.className = "ev__field";
      var c = document.createElement("span"); c.textContent = label; wrap.appendChild(c);
      var i = document.createElement("input"); i.type = type || "text"; wrap.appendChild(i);
      form.appendChild(wrap); return i;
    }
    var first = input("First name"), last = input("Last name"), email = input("Email", "email"),
        title = input("Title"), company = input("Company");
    var addBtn = smallButton("Add presenter", "cbm-button--primary");
    form.appendChild(addBtn);
    box.appendChild(form);
    newToggle.addEventListener("click", function () { form.hidden = !form.hidden; });
    addBtn.addEventListener("click", function () {
      // Validate on click and name what is missing — never a disabled button.
      if (!first.value.trim() || !last.value.trim()) { notice("A new presenter needs a first and last name.", "warn"); return; }
      if (!email.value.trim() || email.value.indexOf("@") === -1) { notice("A new presenter needs an email address.", "warn"); return; }
      addPresenter({ firstName: first.value, lastName: last.value, email: email.value, title: title.value, company: company.value });
    });

    async function addPresenter(payload) {
      try {
        await api("/events/" + encodeURIComponent(raw.id) + "/presenters", {
          method: "POST", body: JSON.stringify(payload),
        });
        search.value = ""; results.innerHTML = "";
        [first, last, email, title, company].forEach(function (i) { i.value = ""; });
        form.hidden = true;
        notice("Presenter added.", "ok");
        await reloadPresenters(raw, list);
      } catch (err) { notice(err.message, "error"); }
    }
    section.appendChild(box);
  }

  /* ---------- actions ---------- */

  function newEvent() {
    openModal("New event", function (host) { eventForm(host, {}); }, async function () {
      var changes = collectForm();
      if (!changes.name || !changes.name.trim()) {
        $("modalMsg").textContent = "An event needs a title.";
        return false;
      }
      var picked = collectLinks();
      var result = await api("/events", {
        method: "POST", body: JSON.stringify({ changes: changes }),
      });
      var sponsorError = null;
      try { await saveSponsors(result.raw.id, picked, {}); }
      catch (e) { sponsorError = e; }
      closeModal();
      noticeWithWarnings("Event created.", result.warnings);
      if (sponsorError) notice("The event was created, but its partners and funders were not saved: " + sponsorError.message, "error");
      await loadEvents();
      await openEvent(result.raw.id);
    }, "Create event", { wide: true });
  }

  function editEvent() {
    var raw = state.current.event.raw || {};
    openModal("Edit event", function (host) { eventForm(host, raw); }, async function () {
      var changes = collectForm();
      if (!changes.name || !changes.name.trim()) {
        $("modalMsg").textContent = "An event needs a title.";
        return false;
      }
      var picked = collectLinks();
      var result = await api("/events/" + raw.id, {
        method: "PUT", body: JSON.stringify({ changes: changes }),
      });
      var sponsorError = null;
      try { await saveSponsors(raw.id, picked, state.current.sponsors); }
      catch (e) { sponsorError = e; }
      closeModal();
      if (sponsorError) notice("Saved, but the partners and funders were not: " + sponsorError.message, "error");
      var zoom = result.zoom || {};
      noticeWithWarnings(zoom.ok && zoom.action && zoom.action !== "skipped"
        ? "Saved. Zoom webinar " + zoom.action + "."
        : "Saved.", result.warnings);
      await refreshDetail();
    }, "Save", { wide: true });
  }

  function addRegistrant(walkIn) {
    openModal(walkIn ? "Add walk-in" : "Add registrant", function (host) {
      field(host, "firstName", "First name", "varchar", "");
      field(host, "lastName", "Last name", "varchar", "");
      field(host, "email", "Email", "varchar", "",
            null, "Optional, but without it they cannot become a CRM contact.");
      field(host, "phone", "Phone", "varchar", "");
    }, async function () {
      var values = collectForm();
      if (!values.firstName || !values.firstName.trim()) {
        $("modalMsg").textContent = "A first name is required.";
        return false;
      }
      values.walkIn = !!walkIn;
      await api("/events/" + state.current.event.raw.id + "/registrants", {
        method: "POST", body: JSON.stringify(values),
      });
      closeModal();
      notice(walkIn ? "Walk-in checked in." : "Registrant added.", "ok");
      await refreshDetail();
    }, walkIn ? "Add and check in" : "Add");
  }

  function addRecording() {
    var raw = state.current.event.raw || {};
    openModal("Recording", function (host) {
      field(host, "url", "YouTube URL", "varchar", raw.recordingUrl || "",
            null, "Upload the recording to YouTube, then paste the watch link here. Leave blank to remove.");
    }, async function () {
      await api("/events/" + raw.id + "/recording", {
        method: "POST", body: JSON.stringify({ url: collectForm().url || "" }),
      });
      closeModal();
      notice("Recording updated.", "ok");
      await refreshDetail();
    });
  }

  async function syncZoom() {
    // Never disabled: explain rather than grey out (product-wide ruling).
    if (!state.session.zoomEnabled) {
      notice("Zoom is not connected yet, so no webinar can be created. "
           + "Ask an administrator to finish the Zoom setup.", "error");
      return;
    }
    try {
      var result = await api("/events/" + state.current.event.raw.id + "/zoom",
                             { method: "POST" });
      var zoom = result.zoom || {};
      notice(zoom.ok ? "Zoom webinar " + zoom.action + "."
                     : (zoom.error || zoom.reason || "Zoom did nothing."),
             zoom.ok ? "ok" : "error");
      await refreshDetail();
    } catch (e) { notice(e.message, "error"); }
  }

  /* ---------- boot ---------- */

  function wire() {
    $("reportsBtn").addEventListener("click", showReports);
    $("reportsBack").addEventListener("click", function () {
      $("reportsPanel").hidden = true;
      $("listPanel").hidden = false;
    });
    $("repRun").addEventListener("click", runReports);
    $("refreshBtn").addEventListener("click", function () {
      loadEvents().then(function () { notice("Refreshed.", "ok"); })
                  .catch(function (e) { notice(e.message, "error"); });
    });
    $("newEventBtn").addEventListener("click", newEvent);
    $("backBtn").addEventListener("click", backToList);
    $("editBtn").addEventListener("click", editEvent);
    $("zoomBtn").addEventListener("click", syncZoom);
    $("recordingBtn").addEventListener("click", addRecording);
    $("addRegBtn").addEventListener("click", function () { addRegistrant(false); });
    $("walkInBtn").addEventListener("click", function () { addRegistrant(true); });

    $("searchBox").addEventListener("input", function () {
      state.search = this.value; renderList();
    });
    $("scopeFilter").addEventListener("change", function () {
      state.scopeChosen = true;
      state.scope = this.value; renderList();
    });
    $("regSearch").addEventListener("input", renderRegistrants);
    $("checkinSearch").addEventListener("input", renderRoster);

    Array.prototype.forEach.call(document.querySelectorAll(".ev__tab"), function (tab) {
      tab.addEventListener("click", function () { showTab(tab.dataset.tab); });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-sort]"), function (th) {
      th.addEventListener("click", function () {
        var key = th.dataset.sort;
        state.sort = state.sort.key === key
          ? { key: key, dir: -state.sort.dir }
          : { key: key, dir: key === "startsAtUtc" ? -1 : 1 };
        renderList();
      });
    });

    $("modalClose").addEventListener("click", closeModal);
    $("modalCancel").addEventListener("click", closeModal);
    $("modalSave").addEventListener("click", async function () {
      if (!modalSave) return;
      try { await modalSave(); }
      catch (e) { $("modalMsg").textContent = e.message; }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !$("modal").hidden) closeModal();
    });
  }

  async function boot() {
    wire();
    try {
      state.session = await api("/session");
      $("whoName").textContent = state.session.name || state.session.userName || "";
      $("userCorner").hidden = false;
      var fieldData = await api("/fields");
      state.fields = fieldData.fields || [];
      state.links = fieldData.links || [];
      state.presenters = fieldData.presenters || { enabled: false, available: false };
      state.options = fieldData.options || {};
      state.optionLabels = fieldData.optionLabels || {};
      state.chapterKey = fieldData.chapterKey || "";
      await loadEvents();
      if (!state.session.websiteLive) {
        notice("The public website is not reading from this app yet — events "
             + "here are not visible on clevelandbusinessmentors.org.", "warn");
      }
    } catch (e) {
      notice(e.message, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
