/* Address paste-parsing — fill Street / line 2 / City / State / ZIP from one
 * pasted string, so staff can copy an address off a website and drop it into
 * the first address input instead of retyping four fields.
 *
 * Plan + rulings: prds/address-paste-parsing-plan.md (Doug, 2026-08-13).
 *
 * Usage — the host supplies the input ELEMENTS and nothing else:
 *
 *   var detach = CBMAddress.attach({
 *     line1: a1, line2: a2, city: city, state: state,
 *     postalCode: zip, country: country,
 *   });
 *
 * Every target is optional. `source` (the watched input) defaults to `line1`;
 * a component with no target element is dropped, unless `foldUnmapped` is on,
 * in which case it is appended to the street value so nothing the user pasted
 * is lost. That is how the volunteer form — which has Street and ZIP but no
 * City or State — keeps the whole address.
 *
 * Design notes that are load-bearing:
 *
 *  - LOCAL ONLY. No network, no API key, no third party (Doug's ruling). No
 *    address VALIDATION either — this splits a string, it does not verify that
 *    the address exists.
 *  - It fires on paste and on blur, never per keystroke, and the blur path
 *    additionally requires `looksParseable` so someone typing "1234 Main St"
 *    by hand is never touched.
 *  - Refusing is the important half. A false positive rewrites four fields, so
 *    anything without a state or a ZIP, anything that looks non-US, and any
 *    single unpunctuated segment is left completely alone.
 *  - Writes go through `setValue`, which dispatches BUBBLING input+change
 *    events. This is not cosmetic: the directory binds its dirty-tracking to
 *    those events, and the session tools run the "Same as billing" mirror off
 *    a delegated `input` listener on the form. Setting `.value` alone would
 *    silently break both.
 *  - Nothing is ever blanked. A component the parse did not find leaves the
 *    existing value alone.
 */
(function () {
  "use strict";

  // The 50 states + DC, matching the State <select> the session tools build.
  var STATE_CODES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY"];

  var STATE_BY_NAME = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY"
  };

  // Checked at the END of the string only — that is the country slot. A street
  // named "India Hill Rd" must not disqualify an Ohio address.
  var NON_US_COUNTRY = new RegExp("(?:^|[,\\n]\\s*|\\s)(?:canada|united kingdom|england|scotland" +
    "|wales|northern ireland|great britain|australia|new zealand|ireland|france|germany|spain" +
    "|italy|netherlands|belgium|switzerland|austria|sweden|norway|denmark|finland|poland" +
    "|portugal|greece|mexico|brazil|argentina|chile|colombia|india|china|japan|south korea" +
    "|singapore|hong kong|israel|south africa|nigeria|kenya|egypt|united arab emirates|qatar" +
    "|saudi arabia|philippines|indonesia|malaysia|thailand|vietnam|pakistan|bangladesh|turkey" +
    "|russia|ukraine|czech republic|hungary|romania)\\s*$", "i");
  var CA_POSTCODE = /\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b/i;
  var UK_POSTCODE = /\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b/i;

  // A trailing US country marker is stripped and remembered, not treated as
  // foreign. The bare "US" form requires a comma so a street ending in "US"
  // (a US-route address) survives.
  var US_COUNTRY_COMMA = /[,\n]\s*(U\.?\s?S\.?\s?A?\.?|United States(?: of America)?)\s*$/i;
  var US_COUNTRY_SPACE = /\s+(U\.?S\.?A\.?|United States(?: of America)?)\s*$/i;

  var ZIP_TAIL = /(\d{5})(?:[-\s](\d{4}))?\s*$/;

  var UNIT_WORDS = "suite|ste|apt|apartment|unit|rm|room|fl|floor|bldg|building|dept|department" +
    "|trlr|lot|space|spc";
  // "PO Box 417" is deliberately absent — a box IS the street, not a unit.
  var UNIT_BODY = "(?:\\d+(?:st|nd|rd|th)\\s+)?(?:" + UNIT_WORDS + ")\\b\\.?\\s*#?\\s*[\\w-]*";
  var UNIT_TAIL = new RegExp("\\s+(" + UNIT_BODY + ")\\s*$", "i");
  var UNIT_HASH_TAIL = /\s+(#\s*[\w-]+)\s*$/;
  var UNIT_ONLY = new RegExp("^(?:" + UNIT_BODY + "|#\\s*[\\w-]+)$", "i");
  var UNIT_LEAD = new RegExp("^(" + UNIT_BODY + ")\\s+(.+)$", "i");

  var STREET_SUFFIX = "st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|way|ct|court" +
    "|pl|place|ter|terrace|pkwy|parkway|cir|circle|hwy|highway|sq|square|trl|trail|loop|run" +
    "|pike|row|expy|expressway|aly|alley|bnd|bend|xing|crossing";
  // Greedy `.*` so the LAST street suffix wins ("1234 Main St Suite 200 Cleveland"
  // splits after "St", not before it).
  var STREET_CITY_SPLIT = new RegExp("^(.*\\b(?:" + STREET_SUFFIX + ")\\b\\.?)\\s+(.+)$", "i");

  var EMAIL_ONLY = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var URL_ONLY = /^(?:https?:\/\/|www\.)\S+$/i;

  var LABELS = {
    street: "Street", line2: "Address line 2", city: "City",
    state: "State", postalCode: "ZIP", country: "Country"
  };
  var ORDER = ["street", "line2", "city", "state", "postalCode", "country"];

  var HIGHLIGHT_MS = 2000;

  // --- Parsing -------------------------------------------------------------

  function isPhoneSegment(s) {
    if (!/^[+\d\s().-]+$/.test(s)) return false;
    if (/^\d{5}-\d{4}$/.test(s)) return false;      // ZIP+4, not a phone
    return s.replace(/\D/g, "").length >= 10;       // a ZIP is 5 or 9 digits, never 10
  }

  function isNoise(s) {
    return EMAIL_ONLY.test(s) || URL_ONLY.test(s) || isPhoneSegment(s);
  }

  /* Title-case a city only when the source gives us no case information —
     an ALL CAPS or all-lowercase paste. Mixed case is the user's own and is
     left exactly as written ("McDonald", "DeWitt"). */
  function tidyCity(s) {
    if (!s) return s;
    if (s !== s.toUpperCase() && s !== s.toLowerCase()) return s;
    return s.toLowerCase().replace(/\b([a-z])/g, function (m, c) { return c.toUpperCase(); });
  }

  function looksParseable(text) {
    if (text == null) return false;
    var s = String(text);
    return /[,\n]/.test(s) || /\b\d{5}(?:-\d{4})?\b/.test(s);
  }

  /* Returns null when the text is not an address we are confident about —
     which is the common case for ordinary typing, and is the point. */
  function parse(raw) {
    if (raw == null) return null;
    var text = String(raw).replace(/[ \t]/g, " ").trim();
    if (!text) return null;

    if (CA_POSTCODE.test(text) || UK_POSTCODE.test(text)) return null;
    if (NON_US_COUNTRY.test(text)) return null;

    var country = "";
    var stripped = text.replace(US_COUNTRY_COMMA, "");
    if (stripped === text) stripped = text.replace(US_COUNTRY_SPACE, "");
    if (stripped !== text) country = "USA";
    text = stripped.trim().replace(/[,\s]+$/, "");

    var segs = text.split(/\s*[\n,]+\s*/).map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
    if (!segs.length) return null;

    // Trailing contact noise (a phone, a URL, an email copied along with the
    // address) is dropped BEFORE the tail scan, or it would hide the ZIP.
    while (segs.length && isNoise(segs[segs.length - 1])) segs.pop();
    if (!segs.length) return null;

    // ZIP, then state, then city — anchoring on the most reliably shaped
    // tokens and working backwards.
    var postalCode = "";
    var last = segs[segs.length - 1];
    var zm = last.match(ZIP_TAIL);
    if (zm) {
      postalCode = zm[2] ? zm[1] + "-" + zm[2] : zm[1];
      var rest = last.slice(0, zm.index).trim().replace(/[,\s]+$/, "");
      if (rest) segs[segs.length - 1] = rest; else segs.pop();
    }

    var state = "";
    if (segs.length) {
      last = segs[segs.length - 1];
      var words = last.split(/\s+/);
      var tail1 = words[words.length - 1] || "";
      if (tail1.length === 2 && STATE_CODES.indexOf(tail1.toUpperCase()) >= 0) {
        state = tail1.toUpperCase();
        words.pop();
      } else {
        // Full state names run to three words ("District of Columbia").
        for (var n = 3; n >= 1 && !state; n--) {
          if (words.length < n) continue;
          var cand = words.slice(words.length - n).join(" ").toLowerCase().replace(/\.$/, "");
          if (STATE_BY_NAME[cand]) { state = STATE_BY_NAME[cand]; words = words.slice(0, words.length - n); }
        }
      }
      if (state) {
        var left = words.join(" ").trim();
        if (left) segs[segs.length - 1] = left; else segs.pop();
      }
    }

    // Without a state AND without a ZIP this is not an address we understand.
    if (!state && !postalCode) return null;

    var city = "";
    var line2 = "";
    if (segs.length > 1) {
      city = segs.pop();
    } else if (segs.length === 1) {
      var one = segs[0];
      if (!/^\d/.test(one) && !UNIT_ONLY.test(one) && state) {
        // A bare place name — "Cleveland, OH 44113" with no street.
        city = one; segs = [];
      } else {
        // One unpunctuated segment: try to split street from city on the last
        // street-type suffix. If there is no suffix to split on, the whole
        // thing stays STREET — putting a street into the City field would be
        // the genuinely bad outcome, so the fallback errs that way.
        var sm = one.match(STREET_CITY_SPLIT);
        if (sm) {
          var tailPart = sm[2].trim();
          var um = tailPart.match(UNIT_LEAD);
          if (um) { line2 = um[1].trim(); tailPart = um[2].trim(); }
          if (tailPart) { segs = [sm[1].trim()]; city = tailPart; }
        }
      }
    }

    // A leading business name, as Google Maps copies it ("Acme Widgets, 1234
    // Main St, …") — dropped only when the NEXT segment starts with a house
    // number, and never when it is an addressee line.
    if (segs.length > 1 && !/^\d/.test(segs[0]) && /^\d/.test(segs[1]) &&
        !/^(attn|attention|c\/o)\b/i.test(segs[0])) {
      segs.shift();
    }

    // A whole segment that is only a unit designator becomes line 2.
    if (!line2) {
      for (var i = segs.length - 1; i >= 0; i--) {
        if (UNIT_ONLY.test(segs[i])) { line2 = segs.splice(i, 1)[0]; break; }
      }
    }

    var street = segs.join(", ").replace(/\s{2,}/g, " ").trim();

    // …otherwise peel a trailing unit off the street itself.
    if (!line2 && street) {
      var tm = street.match(UNIT_TAIL) || street.match(UNIT_HASH_TAIL);
      if (tm && tm.index > 0) { line2 = tm[1].trim(); street = street.slice(0, tm.index).trim(); }
    }

    city = tidyCity(city);

    if (!street && !city && !state && !postalCode) return null;
    return {
      street: street, line2: line2, city: city, state: state,
      postalCode: postalCode, country: country,
      confidence: (street && city && state && postalCode) ? "full" : "partial"
    };
  }

  // --- Writing -------------------------------------------------------------

  function setValue(el, v) {
    el.value = v;
    // Bubbling, because host apps listen for these to mark the form dirty and
    // to mirror billing onto shipping. See the header note.
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function hasOption(sel, v) {
    return Array.prototype.some.call(sel.options, function (o) { return o.value === v; });
  }

  function phrase(list) {
    if (list.length === 1) return list[0];
    if (list.length === 2) return list[0] + " and " + list[1];
    return list.slice(0, -1).join(", ") + " and " + list[list.length - 1];
  }

  // --- attach --------------------------------------------------------------

  function attach(opts) {
    opts = opts || {};
    var source = opts.source || opts.line1;
    if (!source) return function () {};

    var targets = {
      street: opts.line1 || null, line2: opts.line2 || null, city: opts.city || null,
      state: opts.state || null, postalCode: opts.postalCode || null,
      country: opts.country || null
    };
    var notice = null, undoSnapshot = null;

    // Removing the notice and forgetting how to undo are DIFFERENT things.
    // Folding them together nulls the snapshot on the way in (showNotice clears
    // any previous line first), which leaves Undo silently inert.
    function removeNotice() {
      if (notice && notice.parentNode) notice.parentNode.removeChild(notice);
      notice = null;
    }

    function dismiss() { removeNotice(); undoSnapshot = null; }

    function anchorEl() {
      if (opts.anchor) return opts.anchor;
      var wrap = source.closest ? source.closest(".cbm-field") : null;
      return wrap || source;
    }

    function showNotice(changedLabels) {
      removeNotice();
      var host = anchorEl();
      if (!host || !host.parentNode) return;
      notice = document.createElement("div");
      notice.className = "cbm-addrpaste";
      var msg = document.createElement("span");
      msg.className = "cbm-addrpaste__msg";
      msg.textContent = "Filled " + phrase(changedLabels) + " from what you pasted.";
      var undo = document.createElement("button");
      undo.type = "button"; undo.className = "cbm-addrpaste__undo"; undo.textContent = "Undo";
      undo.addEventListener("click", function () { revert(); });
      var x = document.createElement("button");
      x.type = "button"; x.className = "cbm-addrpaste__x";
      x.setAttribute("aria-label", "Dismiss"); x.textContent = "×";
      x.addEventListener("click", dismiss);
      notice.appendChild(msg); notice.appendChild(undo); notice.appendChild(x);
      host.parentNode.insertBefore(notice, host.nextSibling);
    }

    function revert() {
      if (!undoSnapshot) { dismiss(); return; }
      Object.keys(undoSnapshot).forEach(function (k) {
        var el = targets[k];
        if (el && !el.disabled) setValue(el, undoSnapshot[k]);
      });
      dismiss();
      if (source.focus) source.focus();
    }

    function apply(p) {
      var snapshot = {}, changed = [], any = false;

      // A component with nowhere to go is normally dropped; `foldUnmapped`
      // appends it to the street instead, so a form with Street + ZIP but no
      // City/State (the volunteer intake form) loses nothing.
      var street = p.street;
      var line2Merged = false;
      // No separate line 2, but a multi-line street textarea — which is exactly
      // how EspoCRM stores `addressStreet`, so the unit becomes its second line
      // rather than being dropped. (The mentor screens are shaped this way.)
      if (p.line2 && !targets.line2 && targets.street && targets.street.tagName === "TEXTAREA") {
        street = street ? street + "\n" + p.line2 : p.line2;
        line2Merged = true;
      }
      if (opts.foldUnmapped && targets.street) {
        var folded = [];
        if (p.line2 && !targets.line2 && !line2Merged) folded.push(p.line2);
        if (p.city && !targets.city) folded.push(p.city);
        if (p.state && !targets.state) folded.push(p.state);
        if (folded.length) street = [street].concat(folded).filter(Boolean).join(", ");
      }

      ORDER.forEach(function (k) {
        var el = targets[k];
        var v = k === "street" ? street : p[k];
        if (!el || el.disabled || !v) return;          // never blank an existing value
        if (el.tagName === "SELECT" && !hasOption(el, v)) return;
        if (String(el.value) === String(v)) return;
        snapshot[k] = el.value;
        setValue(el, v);
        changed.push(LABELS[k]);
        any = true;
      });

      if (!any) return;
      undoSnapshot = snapshot;
      if (changed.length) showNotice(changed); else removeNotice();
      Object.keys(snapshot).forEach(function (k) {
        var el = targets[k];
        if (!el) return;
        el.classList.add("cbm-addrpaste-hit");
        setTimeout(function () { el.classList.remove("cbm-addrpaste-hit"); }, HIGHLIGHT_MS);
      });
      if (typeof opts.onApply === "function") opts.onApply(p);
    }

    // True when the watched input is itself one of the fields we write — which
    // is what makes it safe to swallow the browser's own paste below.
    function sourceIsTarget() {
      return ORDER.some(function (k) { return targets[k] === source; });
    }

    /* The text the field WOULD hold if this paste were allowed through: the
       current value with the selection replaced.

       We work from the clipboard rather than reading the field afterwards
       because `maxlength` truncates ON PASTE — the intake ZIP field is
       maxlength="10", so a pasted address is cut to ten characters before any
       handler could see the ZIP in it. Reading after the fact would make ZIP
       rescue impossible on exactly the field that needs it most. */
    function prospective(pasted) {
      var v = String(source.value == null ? "" : source.value);
      var s = source.selectionStart, e = source.selectionEnd;
      if (typeof s !== "number" || typeof e !== "number") return pasted;
      return v.slice(0, s) + pasted + v.slice(e);
    }

    // A refused parse never calls preventDefault, so text we don't understand
    // pastes normally and lands exactly where the user put it.
    function onPasteLike(ev, pasted) {
      if (!pasted || !pasted.trim() || !sourceIsTarget()) return;
      var p = parse(prospective(pasted));
      if (!p) return;
      ev.preventDefault();
      apply(p);
    }

    function onPaste(ev) {
      var cd = ev.clipboardData || window.clipboardData;
      onPasteLike(ev, cd ? cd.getData("text") : "");
    }
    function onDrop(ev) {
      var dt = ev.dataTransfer;
      onPasteLike(ev, dt ? dt.getData("text") : "");
    }
    // The blur path catches text that arrived some other way (autofill, a
    // typed-out address). `looksParseable` is what keeps ordinary typing safe.
    function onBlur() {
      var text = source.value;
      if (!text || !text.trim() || !looksParseable(text)) return;
      var p = parse(text);
      if (p) apply(p);
    }

    source.addEventListener("paste", onPaste);
    source.addEventListener("drop", onDrop);
    source.addEventListener("blur", onBlur);

    return function detach() {
      source.removeEventListener("paste", onPaste);
      source.removeEventListener("drop", onDrop);
      source.removeEventListener("blur", onBlur);
      dismiss();
    };
  }

  /* Convenience for the flat `data-field` forms (Mentor Admin, My Mentor
     Profile, the directory edit modal): find `<prefix>Street` / `City` /
     `State` / `PostalCode` / `Country` under `root` and attach to them.
     The prefix varies across entities — `address`, `billingAddress`,
     `shippingAddress` — so callers match by suffix, never by exact name. */
  function attachByFields(root, prefix, extra) {
    if (!root) return function () {};
    prefix = prefix || "address";
    function q(suffix) { return root.querySelector('[data-field="' + prefix + suffix + '"]'); }
    var line1 = q("Street");
    if (!line1) return function () {};
    var o = {
      line1: line1, line2: null, city: q("City"), state: q("State"),
      postalCode: q("PostalCode"), country: q("Country")
    };
    if (extra) Object.keys(extra).forEach(function (k) { o[k] = extra[k]; });
    return attach(o);
  }

  window.CBMAddress = {
    parse: parse, looksParseable: looksParseable,
    attach: attach, attachByFields: attachByFields
  };
})();
