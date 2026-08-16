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
    options: {},
    session: {},
    current: null,      // { event, counts, registrations }
    sort: { key: "startsAtUtc", dir: -1 },
    scope: "published",
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

  function notice(message, kind) {
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

  function visibleEvents() {
    var now = new Date().toISOString();
    var rows = state.events.filter(function (e) {
      if (state.scope === "published") return e.publishToWebsite;
      if (state.scope === "upcoming") return e.startsAtUtc && e.startsAtUtc >= now;
      if (state.scope === "past") return e.startsAtUtc && e.startsAtUtc < now;
      return true;
    });
    var needle = state.search.trim().toLowerCase();
    if (needle) {
      rows = rows.filter(function (e) {
        return [e.topic, e.summary, e.category, e.status, e.format, e.location]
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
    if (key === "published") return row.publishToWebsite ? 1 : 0;
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
      if (item.category) {
        var chip = document.createElement("span");
        chip.className = "ev__chip";
        chip.textContent = item.category;
        nameCell.appendChild(chip);
      }
      cell(fmtWhen(item));
      cell(item.format || "—");
      cell(item.status || "—");
      cell(counts.registered == null ? "—" : counts.registered, "num");
      cell(counts.attended == null ? "—" : counts.attended, "num");
      cell(pct(counts.showRate), "num");
      cell(item.publishToWebsite ? "Live" : "—");
      cell(item.recordingUrl ? "Yes" : "—");
      body.appendChild(tr);
    });
    $("listEmpty").hidden = rows.length > 0;
    $("listCount").textContent =
      rows.length + " of " + state.events.length + " event" + (state.events.length === 1 ? "" : "s");
  }

  async function loadEvents() {
    var data = await api("/events");
    state.events = data.events || [];
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

  function renderOverview() {
    var event = state.current.event, counts = state.current.counts || {};
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

    // The website card image. Served through the app's staff proxy, so it also
    // shows for an unpublished event — the public route is gated on publishing.
    var graphicId = (event.raw && event.raw.eventGraphicId) || "";
    var graphicWrap = $("overviewGraphicWrap");
    if (graphicId && event.raw && event.raw.id) {
      $("overviewGraphic").src = API + "/events/" + encodeURIComponent(event.raw.id)
        + "/graphic?v=" + encodeURIComponent(graphicId);
      graphicWrap.hidden = false;
    } else {
      $("overviewGraphic").removeAttribute("src");
      graphicWrap.hidden = true;
    }

    var facts = [
      ["When", fmtWhen(event)],
      ["Format", event.format || "—"],
      ["Status", event.status || "—"],
      ["Topic", event.category || "—"],
      ["Location", event.location || "—"],
      ["On the website", event.raw && event.raw.publishToWebsite ? "Yes" : "No"],
      ["Public page", event.url || "—"],
      ["Zoom webinar", event.webinarId || "not created"],
      ["Join URL", event.joinUrl || "—"],
      ["Recording", event.recordingUrl || "not published"],
      // Named even when absent: a missing row reads as a missing feature, and
      // "none" is the answer to "why has the website card got no picture?".
      ["Website graphic", graphicId ? "uploaded" : "none — the card falls back "
        + "to the recording thumbnail"],
      ["Summary", event.summary || "—"],
    ];
    var host = $("overviewFacts");
    host.innerHTML = "";
    facts.forEach(function (pair) {
      var row = document.createElement("div");
      row.className = "ev__fact";
      var key = document.createElement("span");
      key.className = "ev__fact-key";
      key.textContent = pair[0];
      var val = document.createElement("span");
      val.className = "ev__fact-value";
      if (/^https?:\/\//.test(pair[1])) {
        var link = document.createElement("a");
        link.href = pair[1]; link.textContent = pair[1];
        link.target = "_blank"; link.rel = "noopener";
        val.appendChild(link);
      } else {
        val.textContent = pair[1];
      }
      row.appendChild(key); row.appendChild(val);
      host.appendChild(row);
    });
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

  function openModal(title, bodyBuilder, onSave, saveLabel) {
    $("modalTitle").textContent = title;
    $("modalBody").innerHTML = "";
    $("modalMsg").textContent = "";
    bodyBuilder($("modalBody"));
    $("modalSave").textContent = saveLabel || "Save";
    modalSave = onSave;
    $("modal").hidden = false;
  }

  function closeModal() { $("modal").hidden = true; modalSave = null; }

  function field(host, name, label, type, value, options, help) {
    var wrap = document.createElement("label");
    wrap.className = "ev__field";
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
        node.value = option; node.textContent = option;
        if (option === value) node.selected = true;
        input.appendChild(node);
      });
    } else if (type === "bool") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = !!value;
      wrap.classList.add("ev__field--check");
    } else if (type === "text" || type === "wysiwyg") {
      input = document.createElement("textarea");
      input.rows = type === "wysiwyg" ? 6 : 3;
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

    var file = document.createElement("input");
    file.type = "file";
    file.accept = "image/png,image/jpeg,image/webp,image/gif";
    wrap.appendChild(file);

    var actions = document.createElement("div");
    actions.className = "ev__graphicactions";
    var upload = document.createElement("button");
    upload.type = "button";
    upload.className = "cbm-button cbm-button--secondary";
    upload.textContent = "Upload graphic";
    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "cbm-button cbm-button--secondary";
    remove.textContent = "Remove graphic";
    actions.appendChild(upload);
    actions.appendChild(remove);
    wrap.appendChild(actions);

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
      // graphic, which is app-managed only because it uploads separately.
      if (spec.hidden) return;   // derived, not entered (dateEnd)
      if (spec.appManaged && spec.type !== "image") return;
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
        var value = raw[spec.name];
        if (spec.type === "duration") {
          // `duration` is VIRTUAL in EspoCRM (dateEnd - dateStart) and is often
          // null on the record, so derive it rather than trusting the field.
          value = window.CBMDateTime.durationBetween(raw.dateStart, raw.dateEnd);
        }
        field(section, spec.name, spec.label, spec.type, value,
              state.options[spec.name], spec.help);
      });
      host.appendChild(section);
    });
  }

  function collectForm() {
    var changes = {};
    Array.prototype.forEach.call($("modalBody").querySelectorAll("[name]"), function (input) {
      var type = input.dataset.type;
      var value;
      if (type === "bool") value = input.checked;
      else if (type === "int") value = input.value === "" ? null : parseInt(input.value, 10);
      else if (type === "duration") value = window.CBMDateTime.readDuration(input);
      else if (type === "datetime") value = window.CBMDateTime.read(input);
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

  /* ---------- actions ---------- */

  function newEvent() {
    openModal("New event", function (host) { eventForm(host, {}); }, async function () {
      var changes = collectForm();
      if (!changes.name || !changes.name.trim()) {
        $("modalMsg").textContent = "An event needs a title.";
        return false;
      }
      var result = await api("/events", {
        method: "POST", body: JSON.stringify({ changes: changes }),
      });
      closeModal();
      notice("Event created.", "ok");
      await loadEvents();
      await openEvent(result.raw.id);
    }, "Create event");
  }

  function editEvent() {
    var raw = state.current.event.raw || {};
    openModal("Edit event", function (host) { eventForm(host, raw); }, async function () {
      var changes = collectForm();
      if (!changes.name || !changes.name.trim()) {
        $("modalMsg").textContent = "An event needs a title.";
        return false;
      }
      var result = await api("/events/" + raw.id, {
        method: "PUT", body: JSON.stringify({ changes: changes }),
      });
      closeModal();
      var zoom = result.zoom || {};
      notice(zoom.ok && zoom.action && zoom.action !== "skipped"
        ? "Saved. Zoom webinar " + zoom.action + "."
        : "Saved.", "ok");
      await refreshDetail();
    });
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
      state.options = fieldData.options || {};
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
