/*
 * CBMDateTime — the project's standard date + time control.
 *
 * A Date input beside a time field that opens a half-hour slot grid ("Morning"
 * 8:00–11:30 AM, "Afternoon & evening" 12:00–7:30 PM, four columns, one click
 * to pick) with a free-entry "Other time" escape hatch. No 60-item minute
 * dropdowns anywhere. Extracted from the session editor, where it was proven,
 * so every app gets the same control instead of a plain `datetime-local`.
 *
 * IT OWNS THE TIMEZONE CONVERSION, and that is the main reason to use it.
 * EspoCRM stores datetimes as UTC with no offset on the wire. A raw
 * `datetime-local` input hands you LOCAL wall time, so sending its value
 * straight to the CRM stores the wrong instant — the Events editor did exactly
 * that and every event it created was four hours early (v0.192.2). Here,
 * `create()` takes a CRM UTC stamp and shows local; `read()` returns a CRM UTC
 * stamp. Callers never do the arithmetic.
 *
 * Usage:
 *     var el = CBMDateTime.create({ value: crmStamp });    // put el in the DOM
 *     var stamp = CBMDateTime.read(el);                    // "YYYY-MM-DD HH:MM:SS" UTC, or null
 *
 * Options: `value` (CRM UTC stamp), `busyFetch` (see below), `startHour` /
 * `endHour` to widen the grid, `placeholder`.
 *
 * `busyFetch(dateStr) -> Promise<[{start, end, summary}]>` is optional. When
 * given, slots overlapping something already on the user's calendar are tinted
 * and titled. Advisory ONLY — a shaded slot stays clickable; deconflicting is
 * the user's business. Any failure means no shading, never an error.
 */
(function (window, document) {
  "use strict";

  var CBMDateTime = {};

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  /* A CRM datetime ("YYYY-MM-DD HH:MM:SS", UTC, no offset) as a local Date.
     A date-only value is taken as local midnight, not UTC midnight. */
  function parseCrmStamp(v) {
    if (!v) return null;
    var m = String(v).replace("T", " ").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ ](\d{2}):(\d{2}))?/);
    if (!m) return null;
    if (m[4] == null) return new Date(+m[1], +m[2] - 1, +m[3]);
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]));
  }

  /* "YYYY-MM-DDTHH:MM" of LOCAL wall time → the CRM's UTC stamp. */
  function toCrmStamp(localValue) {
    var m = localValue ? String(localValue).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/) : null;
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
    return d.getUTCFullYear() + "-" + pad2(d.getUTCMonth() + 1) + "-" + pad2(d.getUTCDate()) +
           " " + pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes()) + ":00";
  }

  function formatTime(h, m) {
    var mer = h < 12 ? "AM" : "PM";
    var hh = h % 12; if (hh === 0) hh = 12;
    return hh + ":" + pad2(m) + " " + mer;
  }

  /* Accepts "2:45 PM", "2 pm", "14:45", "9:30am"; null when unparseable. */
  function parseTime(s) {
    var m = String(s || "").trim().match(/^(\d{1,2})(?::(\d{2}))?\s*([AaPp])?\.?\s*[Mm]?\.?$/);
    if (!m) return null;
    var h = +m[1], mm = m[2] ? +m[2] : 0;
    if (mm > 59) return null;
    if (m[3]) {
      if (h < 1 || h > 12) return null;
      h = (h % 12) + (/p/i.test(m[3]) ? 12 : 0);
    } else if (h > 23) return null;
    return { h: h, m: mm };
  }

  function slotsBetween(fromH, toH) {
    var out = [];
    for (var h = fromH; h < toH; h++) { out.push(formatTime(h, 0)); out.push(formatTime(h, 30)); }
    return out;
  }

  function closeAll(except) {
    Array.prototype.forEach.call(document.querySelectorAll(".cbm-dt__pop.open"), function (p) {
      if (p !== except) p.classList.remove("open");
    });
  }
  document.addEventListener("click", function () { closeAll(null); });

  CBMDateTime.create = function (options) {
    var opts = options || {};
    var busyFetch = opts.busyFetch || null;
    var startHour = opts.startHour == null ? 8 : opts.startHour;
    var endHour = opts.endHour == null ? 20 : opts.endHour;

    var wrap = document.createElement("div");
    wrap.className = "cbm-dt";
    var initial = parseCrmStamp(opts.value);

    var dateEl = document.createElement("input");
    dateEl.type = "date";
    dateEl.className = "cbm-dt__date";
    if (initial) {
      dateEl.value = initial.getFullYear() + "-" + pad2(initial.getMonth() + 1)
        + "-" + pad2(initial.getDate());
    }

    var tw = document.createElement("div");
    tw.className = "cbm-dt__timewrap";
    var timeEl = document.createElement("input");
    timeEl.type = "text";
    timeEl.className = "cbm-dt__time";
    timeEl.readOnly = true;
    timeEl.placeholder = opts.placeholder || "Time";
    if (initial) timeEl.value = formatTime(initial.getHours(), initial.getMinutes());

    var pop = document.createElement("div");
    pop.className = "cbm-dt__pop";

    var conflictNote = null;
    if (busyFetch) {
      conflictNote = document.createElement("div");
      conflictNote.className = "cbm-dt__conflictnote";
      conflictNote.textContent =
        "Shaded times conflict with your calendar. You can still choose one — "
        + "you'll need to resolve the overlap yourself.";
      conflictNote.hidden = true;
      pop.appendChild(conflictNote);
    }

    function markConflicts() {
      if (!busyFetch) return;
      var buttons = pop.querySelectorAll(".cbm-dt__grid button");
      Array.prototype.forEach.call(buttons, function (b) {
        b.classList.remove("conflict"); b.removeAttribute("title");
      });
      conflictNote.hidden = true;
      var dm = (dateEl.value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!dm) return;
      var dateAtCall = dateEl.value;
      Promise.resolve(busyFetch(dateAtCall)).then(function (busy) {
        // Stale by the time it returns (date changed / popover closed) — skip.
        if (!busy || !busy.length || dateEl.value !== dateAtCall ||
            !pop.classList.contains("open")) return;
        var any = false;
        Array.prototype.forEach.call(buttons, function (b) {
          var t = parseTime(b.textContent);
          if (!t) return;
          var s = new Date(+dm[1], +dm[2] - 1, +dm[3], t.h, t.m).getTime();
          var e = s + 30 * 60000;   // each slot claims its half-hour block
          var hits = busy.filter(function (iv) {
            var bs = parseCrmStamp(iv.start), be = parseCrmStamp(iv.end);
            return bs && be && bs.getTime() < e && be.getTime() > s;
          });
          if (hits.length) {
            any = true;
            b.classList.add("conflict");
            b.title = "Busy: " + hits.map(function (iv) { return iv.summary; }).join("; ");
          }
        });
        conflictNote.hidden = !any;
      }, function () { /* shading is decoration — never surface a failure */ });
    }

    function slotGrid(labelText, slots) {
      var lab = document.createElement("div");
      lab.className = "cbm-dt__label";
      lab.textContent = labelText;
      pop.appendChild(lab);
      var grid = document.createElement("div");
      grid.className = "cbm-dt__grid";
      slots.forEach(function (t) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = t;
        b.addEventListener("click", function () {
          timeEl.value = t;
          pop.classList.remove("open");
          timeEl.dispatchEvent(new Event("input", { bubbles: true }));
        });
        grid.appendChild(b);
      });
    pop.appendChild(grid);
    }

    var midday = Math.min(12, endHour);
    if (startHour < midday) slotGrid("Morning", slotsBetween(startHour, midday));
    if (endHour > midday) slotGrid("Afternoon & evening", slotsBetween(midday, endHour));

    var foot = document.createElement("div");
    foot.className = "cbm-dt__foot";
    var span = document.createElement("span");
    span.textContent = "Other time:";
    var other = document.createElement("input");
    other.type = "text";
    other.placeholder = "e.g. 2:45 PM";
    other.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      var t = parseTime(other.value);
      if (!t) { other.classList.add("cbm-dt__bad"); return; }
      other.classList.remove("cbm-dt__bad");
      timeEl.value = formatTime(t.h, t.m);
      pop.classList.remove("open");
      timeEl.dispatchEvent(new Event("input", { bubbles: true }));
    });
    other.addEventListener("input", function () { other.classList.remove("cbm-dt__bad"); });
    foot.appendChild(span); foot.appendChild(other);
    pop.appendChild(foot);

    timeEl.addEventListener("click", function (e) {
      e.stopPropagation();
      closeAll(pop);
      var opening = !pop.classList.contains("open");
      pop.classList.toggle("open", opening);
      if (opening) {
        Array.prototype.forEach.call(pop.querySelectorAll(".cbm-dt__grid button"), function (b) {
          b.classList.toggle("sel", b.textContent === timeEl.value);
        });
        other.value = "";
        markConflicts();
      }
    });
    dateEl.addEventListener("change", function () {
      if (pop.classList.contains("open")) markConflicts();
    });
    pop.addEventListener("click", function (e) { e.stopPropagation(); });

    tw.appendChild(timeEl); tw.appendChild(pop);
    wrap.appendChild(dateEl); wrap.appendChild(tw);

    wrap.getValue = function () { return CBMDateTime.read(wrap); };
    wrap.setValue = function (crmStamp) {
      var d = parseCrmStamp(crmStamp);
      dateEl.value = d
        ? d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) : "";
      timeEl.value = d ? formatTime(d.getHours(), d.getMinutes()) : "";
    };
    return wrap;
  };

  /* The CRM UTC stamp for a control built by create(), or null when either half
     is unset. Static so a caller holding only the element (a generic field
     reader, say) does not need the handle create() returned. */
  CBMDateTime.read = function (el) {
    if (!el) return null;
    var dateEl = el.querySelector(".cbm-dt__date");
    var timeEl = el.querySelector(".cbm-dt__time");
    if (!dateEl || !timeEl) return null;
    var t = parseTime(timeEl.value);
    if (!dateEl.value || !t) return null;
    return toCrmStamp(dateEl.value + "T" + pad2(t.h) + ":" + pad2(t.m));
  };

  // Exposed because callers legitimately need them outside the control —
  // rendering a stored stamp, or validating typed input.
  CBMDateTime.parseCrmStamp = parseCrmStamp;
  CBMDateTime.toCrmStamp = toCrmStamp;
  CBMDateTime.formatTime = formatTime;
  CBMDateTime.parseTime = parseTime;

  window.CBMDateTime = CBMDateTime;
})(window, document);
