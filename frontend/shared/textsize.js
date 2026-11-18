/* The member's text size on every application page (Doug, 11-18-26,
 * option A: "Most of our mentors are older so will probably like a larger
 * font"). Chosen on the home page; kept as the member's preference
 * `ui.textSize`, so it follows them to any computer.
 *
 * Load it right after /shared/busy.js on every signed-in page; a test fails
 * on a staff page that forgets it. Public pages (the intake forms, the
 * webinars, the surveys) do not load it.
 *
 * How: the whole page is scaled with CSS `zoom`, the way the browser's own
 * zoom does, because the pages size their text partly in px and partly in
 * rem, and raising one base size would enlarge only half of it. Zoom also
 * enlarges lengths measured against the window, so every height or width
 * written in vh / vw is written `calc(N * var(--cbm-vh, 1vh))`, and this
 * script sets --cbm-vh to 1vh divided by the zoom: a dialog of 90vh still
 * fits the window at Larger. Standard sets nothing at all.
 *
 *   CBMTextSize.get()        -> "standard" | "large" | "larger"
 *   CBMTextSize.set("large") -> applies at once; resolves when saved
 *   CBMTextSize.sizes        -> [{key, label}, ...]
 */
(function () {
  "use strict";
  var ZOOM = { standard: 1, large: 1.15, larger: 1.3 };
  var SIZES = [
    { key: "standard", label: "Standard" },
    { key: "large", label: "Large" },
    { key: "larger", label: "Larger" },
  ];
  var LOCAL = "cbm.textSize";
  var PREF = "/api/portal/preferences/ui.textSize";
  var current = "standard";

  function valid(v) { return Object.prototype.hasOwnProperty.call(ZOOM, v); }

  function apply(v) {
    current = valid(v) ? v : "standard";
    var root = document.documentElement, z = ZOOM[current];
    if (z === 1) {
      root.style.removeProperty("zoom");
      root.style.removeProperty("--cbm-vh");
      root.style.removeProperty("--cbm-vw");
    } else {
      root.style.zoom = String(z);
      root.style.setProperty("--cbm-vh", "calc(1vh / " + z + ")");
      root.style.setProperty("--cbm-vw", "calc(1vw / " + z + ")");
    }
    root.setAttribute("data-text-size", current);
  }
  function remember(v) {
    try { localStorage.setItem(LOCAL, v); } catch (e) { /* this browser keeps nothing */ }
  }

  // At once, from this browser's copy, so the page does not jump.
  try { apply(localStorage.getItem(LOCAL)); } catch (e) { apply("standard"); }

  // Then the member's saved choice, which wins (it may have been made on
  // another computer). Signed out, or no database: the copy stands.
  if (window.fetch) {
    fetch(PREF, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && valid(d.value) && d.value !== current) { apply(d.value); remember(d.value); }
      })
      .catch(function () { /* the copy stands */ });
  }

  function set(v) {
    if (!valid(v)) return Promise.reject(new Error("unknown text size"));
    apply(v);
    remember(v);
    return fetch(PREF, {
      method: "PUT", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value: v }),
    }).then(function (r) {
      if (r.ok) return v;
      return r.json().catch(function () { return null; }).then(function (d) {
        throw new Error((d && d.detail) || ("the server answered " + r.status));
      });
    }, function () { throw new Error("the server did not answer"); });
  }

  window.CBMTextSize = { get: function () { return current; }, set: set, sizes: SIZES };
})();
