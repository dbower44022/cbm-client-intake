/* Button busy indicator — product-wide press feedback (Doug's ruling
 * 2026-07-20: "immediately after any button press a spinner is displayed so
 * the user knows the press worked").
 *
 * Why: a button whose action goes to the server looked identical before and
 * after the click. On a slow request the user got no spinner, no progress and
 * nothing to cancel, so a save that was actually in flight read as "nothing
 * happened" — the condition that produced three identical sessions on one
 * engagement (2026-07-17; see CHANGELOG 0.112.0).
 *
 * Usage: include this script. That is all — it wires itself up.
 *
 *   <script src="/shared/busy.js"></script>
 *
 * How it decides: a spinner is for waiting on the SERVER, so this module
 * shows one on the clicked button only when that click actually starts a
 * request. It instruments fetch + XMLHttpRequest (quickmail sends via XHR for
 * upload progress) and attributes any request opened within
 * ``ATTRIBUTION_MS`` of a click to that button; the spinner stays until every
 * request attributed to the click has settled. A button that only changes the
 * page locally (tab switch, modal close) starts no request and so gets no
 * spinner — it already gives instant visual feedback, and a flicker there
 * would be noise.
 *
 * Deliberately VISUAL ONLY: it never sets `disabled`. Apps own their own
 * in-flight guards (e.g. the session editor's), the product rule is that
 * action buttons stay clickable and validate on click, and touching
 * `disabled` here would fight both.
 *
 * Manual control, for a wait this module cannot see (a long local computation,
 * or work started outside a click):
 *
 *   var done = CBMBusy.start(buttonEl);   // spinner on
 *   ...                                   // do the work
 *   done();                               // spinner off (safe to call twice)
 */
(function () {
  "use strict";

  // A request opened within this long after a click is treated as that click's
  // work. Handlers normally call fetch synchronously; the allowance covers a
  // handler that awaits something trivial first (a snapshot, a confirm) before
  // reaching the network.
  var ATTRIBUTION_MS = 150;

  var pendingClick = null;   // {el, until, count, release} — the click being attributed
  var injected = false;

  function injectCss() {
    if (injected) return;
    injected = true;
    var css = [
      /* The spinner sits INSIDE the button, so the button keeps its size and */
      /* the label stays readable — no layout shift on press. */
      ".cbm-busy{position:relative;}",
      ".cbm-busy::after{",
      "  content:'';position:absolute;top:50%;right:.6em;width:.85em;height:.85em;",
      "  margin-top:-.425em;border-radius:50%;",
      "  border:2px solid currentColor;border-right-color:transparent;",
      "  opacity:.85;animation:cbm-busy-spin .6s linear infinite;",
      "}",
      /* Keep the label clear of the spinner while it shows. */
      ".cbm-busy{padding-right:2.2em !important;}",
      "@keyframes cbm-busy-spin{to{transform:rotate(360deg);}}",
      /* Respect the OS "reduce motion" setting: still show a mark, don't spin. */
      "@media (prefers-reduced-motion: reduce){",
      "  .cbm-busy::after{animation:none;border-right-color:currentColor;opacity:.5;}",
      "}",
    ].join("\n");
    var tag = document.createElement("style");
    tag.setAttribute("data-cbm-busy", "1");
    tag.appendChild(document.createTextNode(css));
    (document.head || document.documentElement).appendChild(tag);
  }

  // Put the spinner on an element; returns an idempotent stop function.
  function start(el) {
    if (!el || !el.classList) return function () {};
    injectCss();
    el.classList.add("cbm-busy");
    var stopped = false;
    return function stop() {
      if (stopped) return;
      stopped = true;
      // The button may have been re-rendered away mid-request (a save that
      // re-opens the record replaces the toolbar) — removing the class from a
      // detached node is harmless, so no isConnected guard is needed.
      el.classList.remove("cbm-busy");
    };
  }

  // --- click attribution ---------------------------------------------------

  function clickable(target) {
    if (!target || !target.closest) return null;
    // Buttons, plus anchors/elements styled as buttons (the apps use both).
    return target.closest("button, .cbm-button, [role='button']");
  }

  document.addEventListener("click", function (e) {
    var el = clickable(e.target);
    if (!el) return;
    // A fresh click supersedes any still-open attribution window.
    if (pendingClick && pendingClick.count === 0) pendingClick.release();
    pendingClick = {
      el: el,
      until: Date.now() + ATTRIBUTION_MS,
      count: 0,
      release: function () { /* replaced below once a request attaches */ },
    };
  }, true);  // capture: run before the app's own handler starts its request

  // Attach the in-flight request to the open click, if there is one.
  function attach() {
    var p = pendingClick;
    if (!p || Date.now() > p.until) return null;
    if (p.count === 0) p.release = start(p.el);
    p.count += 1;
    var settled = false;
    return function done() {
      if (settled) return;
      settled = true;
      p.count -= 1;
      if (p.count <= 0) p.release();
    };
  }

  // --- transport instrumentation ------------------------------------------

  if (window.fetch) {
    var realFetch = window.fetch;
    window.fetch = function () {
      var done = attach();
      var out;
      try {
        out = realFetch.apply(this, arguments);
      } catch (err) {
        if (done) done();
        throw err;
      }
      if (done && out && out.then) {
        // Settle on BOTH outcomes; never swallow the result or the rejection.
        out.then(done, done);
      } else if (done) {
        done();
      }
      return out;
    };
  }

  if (window.XMLHttpRequest) {
    var realSend = window.XMLHttpRequest.prototype.send;
    window.XMLHttpRequest.prototype.send = function () {
      var done = attach();
      if (done) {
        // loadend fires for success, error, abort and timeout alike.
        this.addEventListener("loadend", done);
      }
      return realSend.apply(this, arguments);
    };
  }

  window.CBMBusy = { start: start };
})();
