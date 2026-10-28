/* Shared divider between a grid and its preview pane (Doug's ruling
 * 10-27-26: "a divider bar to resize the preview pane"). Plan:
 * prds/shared-grid-plan.md.
 *
 *   var split = CBMSplit.attach(leftEl, rightEl, {
 *     key: "lists.preview",   // remembers the width per browser
 *     initial: 420, min: 280, max: 900   // the right pane's width, px
 *   });
 *
 * The bar goes between the two panes, which must be siblings in a flex row.
 * Drag it; with focus, the arrow keys move it 24px; a double-click puts it
 * back. The bar hides itself while the right pane is hidden, and when the
 * row wraps the panes onto separate lines (a narrow window). */
(function (root) {
  "use strict";
  var STORE = "cbm.split.";

  function load(key) {
    try { var v = parseInt(root.localStorage.getItem(STORE + key), 10); return isNaN(v) ? null : v; } catch (_) { return null; }
  }
  function save(key, v) {
    try { root.localStorage.setItem(STORE + key, String(Math.round(v))); } catch (_) { /* memory only */ }
  }

  function attach(left, right, opts) {
    opts = opts || {};
    var doc = root.document;
    var min = opts.min || 260, max = opts.max || 1000, initial = opts.initial || 420;
    var width = (opts.key && load(opts.key)) || initial;
    var bar = doc.createElement("div");
    bar.className = "cbm-split__bar";
    bar.setAttribute("role", "separator");
    bar.setAttribute("aria-orientation", "vertical");
    bar.setAttribute("aria-label", opts.label || "Resize the preview pane");
    bar.setAttribute("aria-valuemin", String(min));
    bar.setAttribute("aria-valuemax", String(max));
    bar.tabIndex = 0;
    bar.title = "Drag to resize. Double-click to reset.";
    right.parentNode.insertBefore(bar, right);
    left.classList.add("cbm-split__left");
    right.classList.add("cbm-split__right");

    function clamp(w) {
      var room = (right.parentNode.getBoundingClientRect().width || 0) - 320;
      return Math.max(min, Math.min(max, room > min ? Math.min(w, room) : w));
    }
    function apply() {
      right.style.boxSizing = "border-box";   // the width is the pane's outer width
      right.style.flex = "0 0 " + Math.round(width) + "px";
      right.style.maxWidth = "none";
      bar.setAttribute("aria-valuenow", String(Math.round(width)));
    }
    function set(w, keep) {
      width = clamp(w);
      apply();
      if (keep !== false && opts.key) save(opts.key, width);
    }
    function sync() {
      // Hidden right pane, or panes wrapped onto separate lines: no bar.
      var wrapped = right.hidden ? false : Math.abs(right.getBoundingClientRect().top - left.getBoundingClientRect().top) > 4;
      bar.hidden = right.hidden || wrapped;
    }

    bar.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      var startX = e.clientX, startW = right.getBoundingClientRect().width;
      bar.classList.add("is-dragging");
      if (bar.setPointerCapture) { try { bar.setPointerCapture(e.pointerId); } catch (_) {} }
      function move(ev) { set(startW - (ev.clientX - startX), false); }
      function up() {
        bar.classList.remove("is-dragging");
        bar.removeEventListener("pointermove", move);
        bar.removeEventListener("pointerup", up);
        bar.removeEventListener("pointercancel", up);
        if (opts.key) save(opts.key, width);
      }
      bar.addEventListener("pointermove", move);
      bar.addEventListener("pointerup", up);
      bar.addEventListener("pointercancel", up);
    });
    bar.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { e.preventDefault(); set(width + 24); }
      else if (e.key === "ArrowRight") { e.preventDefault(); set(width - 24); }
    });
    bar.addEventListener("dblclick", function () { set(initial); });

    if (root.MutationObserver) new root.MutationObserver(sync).observe(right, { attributes: true, attributeFilter: ["hidden"] });
    root.addEventListener("resize", sync);
    apply();
    sync();

    return { sync: sync, width: function () { return width; }, set: set, bar: bar };
  }

  root.CBMSplit = { attach: attach };
})(typeof window !== "undefined" ? window : globalThis);
