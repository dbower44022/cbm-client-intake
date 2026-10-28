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
      /* A grid or panel waiting on the server (CBMBusy.loading): its content */
      /* dimmed, a spinner over it, nothing disabled. */
      ".cbm-loading{position:relative;}",
      ".cbm-loading>*{opacity:.45;transition:opacity .15s;}",
      ".cbm-loading::after{content:'';position:absolute;z-index:5;top:min(45%,6rem);left:50%;",
      "  width:1.8rem;height:1.8rem;margin:-.9rem 0 0 -.9rem;border-radius:50%;",
      "  border:3px solid #173B60;border-right-color:transparent;animation:cbm-busy-spin .7s linear infinite;}",
      /* A link that opens another page: a small spinner after its text. */
      ".cbm-busy-link::after{content:'';display:inline-block;width:.8em;height:.8em;margin-left:.4em;",
      "  vertical-align:-.1em;border-radius:50%;border:2px solid currentColor;border-right-color:transparent;",
      "  animation:cbm-busy-spin .6s linear infinite;}",
      /* A page opening: a pill at the top until its first data has arrived. */
      ".cbm-pageload{position:fixed;z-index:9999;top:calc(.6rem + env(safe-area-inset-top,0px));left:50%;transform:translateX(-50%);",
      "  display:flex;align-items:center;gap:.5rem;padding:.35rem .8rem .35rem .6rem;border-radius:999px;",
      "  background:#173B60;color:#fff;font:500 13px/1.2 system-ui,sans-serif;box-shadow:0 4px 14px rgba(23,59,96,.25);pointer-events:none;}",
      ".cbm-pageload::before{content:'';width:.9rem;height:.9rem;border-radius:50%;border:2px solid #fff;",
      "  border-right-color:transparent;animation:cbm-busy-spin .6s linear infinite;}",
      "@media (prefers-reduced-motion: reduce){",
      "  .cbm-loading::after,.cbm-busy-link::after,.cbm-pageload::before{animation:none;border-right-color:currentColor;opacity:.6;}",
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

  // --- failure reports (v0.260.0) -------------------------------------------
  // A request that never reaches the server leaves no trace in any server log
  // ("Failed to fetch" on the Phase 2 live pass, 10-17-26). Every page loads
  // this file first and every request passes through it, so this is where the
  // browser reports its own failures: a request that got no answer, a timeout,
  // a 5xx, an uncaught script error. POST /api/client-errors writes each as a
  // WARNING "client-error" line (core/client_errors.py). Never a body, never a
  // form field, never a query string — the path, the method, the status, the
  // time and the message. Silent by design: a report never shows the user
  // anything, never blocks a page, never reports itself.
  var REPORT_PATH = "/api/client-errors";
  var REPORT_MAX = 20;            // per page load
  var QUEUE_KEY = "cbm-client-errors";
  var reportsSent = 0;
  var realFetch = window.fetch ? window.fetch.bind(window) : null;

  function pathOf(url) {
    try {
      var u = new URL(String(url), location.href);
      if (u.origin !== location.origin) return null;   // our own requests only
      return u.pathname;
    } catch (_) { return null; }
  }

  function readQueue() {
    try { return JSON.parse(sessionStorage.getItem(QUEUE_KEY) || "[]") || []; } catch (_) { return []; }
  }
  function writeQueue(q) {
    try {
      if (q.length) sessionStorage.setItem(QUEUE_KEY, JSON.stringify(q.slice(-10)));
      else sessionStorage.removeItem(QUEUE_KEY);
    } catch (_) { /* storage blocked: the report is simply lost */ }
  }

  function send(reports) {
    if (!realFetch || !reports.length) return;
    var now = Date.now();
    var body = JSON.stringify({ reports: reports.map(function (r) {
      var out = {}; for (var k in r) out[k] = r[k];
      if (r.at) out.queued = Math.round((now - r.at) / 1000);
      delete out.at;
      return out;
    }) });
    try {
      realFetch(REPORT_PATH, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: body, credentials: "same-origin", keepalive: true,
      }).then(function (resp) {
        if (!resp.ok && resp.status !== 204) writeQueue(readQueue().concat(reports));
      }, function () {
        // The connection is the thing that failed — keep it for the next try.
        writeQueue(readQueue().concat(reports));
      });
    } catch (_) { writeQueue(readQueue().concat(reports)); }
  }

  function report(r) {
    if (reportsSent >= REPORT_MAX) return;
    reportsSent += 1;
    r.page = location.pathname;
    r.at = Date.now();
    send([r]);
  }

  // Reports a broken connection could not deliver go with the next request
  // that worked — the connection is back, so this is when they get through.
  function flushQueue() {
    var q = readQueue();
    if (!q.length) return;
    writeQueue([]);
    send(q);
  }

  function watch(promise, method, path, started) {
    if (!path || path === REPORT_PATH) return;
    promise.then(function (resp) {
      if (resp && resp.status >= 500) {
        report({ kind: "http", method: method, url: path, status: resp.status,
                 ms: Date.now() - started, message: resp.statusText || "" });
      } else {
        flushQueue();
      }
    }, function (err) {
      var ms = Date.now() - started;
      var aborted = err && err.name === "AbortError";
      // An abort the page asked for a moment after starting is the page
      // moving on, not a failure; a long one is a timeout.
      if (aborted && ms < 10000) return;
      report({ kind: aborted ? "timeout" : "network", method: method, url: path,
               status: 0, ms: ms, message: (err && (err.message || err.name)) || "" });
    });
  }

  window.addEventListener("error", function (e) {
    if (!e || !e.message) return;
    report({ kind: "script", url: e.filename ? (pathOf(e.filename) || "-") : "-",
             message: e.message + (e.lineno ? " (line " + e.lineno + ")" : "") });
  });
  window.addEventListener("unhandledrejection", function (e) {
    var reason = e && e.reason;
    var msg = reason && (reason.message || String(reason));
    if (!msg) return;
    // A request failure already reported itself above; don't count it twice.
    if (reason && (reason.name === "TypeError" && /fetch/i.test(msg))) return;
    report({ kind: "rejection", message: msg });
  });

  // --- the page-opening spinner ------------------------------------------
  // Every request since the page began is counted; the pill shows from the
  // start and goes once the page has loaded and nothing has been in flight
  // for a moment — that is, once its first data has arrived. Only the
  // opening: later requests are shown on their button or their panel.
  var inflight = 0, opening = true, pill = null, quietTimer = null, PAGE_CAP_MS = 30000;
  function showPill() {
    if (!opening || pill || !document.body) return;
    injectCss();
    pill = document.createElement("div");
    pill.className = "cbm-pageload";
    pill.setAttribute("role", "status");
    pill.textContent = "Loading…";
    document.body.appendChild(pill);
  }
  function endOpening() {
    if (!opening) return;
    opening = false;
    clearTimeout(quietTimer);
    if (pill) { pill.remove(); pill = null; }
  }
  function maybeEnd() {
    if (!opening || inflight > 0 || document.readyState !== "complete") return;
    clearTimeout(quietTimer);
    quietTimer = setTimeout(function () { if (inflight === 0) endOpening(); }, 250);
  }
  function track() {
    inflight += 1;
    clearTimeout(quietTimer);
    var settled = false;
    return function () { if (settled) return; settled = true; inflight -= 1; maybeEnd(); };
  }
  // Shown only when the opening takes long enough to notice: a fast page
  // never flashes it.
  setTimeout(function () {
    if (document.body) showPill();
    else document.addEventListener("DOMContentLoaded", showPill);
  }, 400);
  window.addEventListener("load", maybeEnd);
  setTimeout(endOpening, PAGE_CAP_MS);
  if (document.readyState === "complete") maybeEnd();

  if (window.fetch) {
    var wrappedFetch = window.fetch;
    window.fetch = function (input, init) {
      var untrack = track();
      var done = attach();
      var started = Date.now();
      var method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
      var path = pathOf(input && input.url ? input.url : input);
      var out;
      try {
        out = wrappedFetch.apply(this, arguments);
      } catch (err) {
        if (done) done();
        untrack();
        throw err;
      }
      if (out && out.then) out.then(untrack, untrack); else untrack();
      if (done && out && out.then) {
        // Settle on BOTH outcomes; never swallow the result or the rejection.
        out.then(done, done);
      } else if (done) {
        done();
      }
      if (out && out.then) watch(out, method, path, started);
      return out;
    };
  }

  if (window.XMLHttpRequest) {
    var realOpen = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = function (method, url) {
      this._cbmMethod = String(method || "GET").toUpperCase();
      this._cbmPath = pathOf(url);
      return realOpen.apply(this, arguments);
    };
    var realSend = window.XMLHttpRequest.prototype.send;
    window.XMLHttpRequest.prototype.send = function () {
      var done = attach();
      var xhr = this, started = Date.now();
      this.addEventListener("loadend", track());
      if (done) {
        // loadend fires for success, error, abort and timeout alike.
        this.addEventListener("loadend", done);
      }
      if (xhr._cbmPath && xhr._cbmPath !== REPORT_PATH) {
        xhr.addEventListener("error", function () {
          report({ kind: "network", method: xhr._cbmMethod, url: xhr._cbmPath, status: 0,
                   ms: Date.now() - started, message: "The request got no answer" });
        });
        xhr.addEventListener("timeout", function () {
          report({ kind: "timeout", method: xhr._cbmMethod, url: xhr._cbmPath, status: 0,
                   ms: Date.now() - started, message: "The request timed out" });
        });
        xhr.addEventListener("load", function () {
          if (xhr.status >= 500) {
            report({ kind: "http", method: xhr._cbmMethod, url: xhr._cbmPath, status: xhr.status,
                     ms: Date.now() - started, message: xhr.statusText || "" });
          }
        });
      }
      return realSend.apply(this, arguments);
    };
  }

  // A page that opens after a broken connection sends what the last one queued.
  setTimeout(flushQueue, 2000);

  // --- request timeout -----------------------------------------------------
  // A request that hangs forever is what made a save look like it had failed
  // (no spinner, no end, nothing to cancel) — the user then acted again. The
  // sessions app has its own tailored timeout (its message can promise no
  // duplicate, because its creates carry an idempotency token); this is the
  // shared one for every other app's api() helper. AbortController aborts a
  // stuck request so it ends in a readable message instead of silence.
  //
  //   var resp = await CBMBusy.fetch(url, opts);   // 60s default
  //
  // Calls the busy-wrapped window.fetch, so the spinner still applies. Throws a
  // timeout Error (``.timeout === true``, ``.status === 0``) that propagates
  // out of api() to the caller's catch, exactly as a network error does today.
  var DEFAULT_TIMEOUT_MS = 60000;

  function fetchWithTimeout(url, opts, timeoutMs) {
    opts = opts || {};
    timeoutMs = timeoutMs || DEFAULT_TIMEOUT_MS;
    // No AbortController, or the caller supplied its own signal => don't
    // interfere; just pass through (still spinner-wrapped).
    if (!window.AbortController || opts.signal) return window.fetch(url, opts);
    var ctl = new AbortController();
    opts.signal = ctl.signal;
    var timedOut = false;
    var timer = setTimeout(function () { timedOut = true; ctl.abort(); }, timeoutMs);
    return window.fetch(url, opts).then(
      function (resp) { clearTimeout(timer); return resp; },
      function (err) {
        clearTimeout(timer);
        if (timedOut) {
          var e = new Error(
            "The server took too long to respond. Nothing you typed has been "
            + "lost — check whether your change was saved before trying again."
          );
          e.status = 0;
          e.timeout = true;
          throw e;
        }
        throw err;
      }
    );
  }

  // --- a grid or panel loading --------------------------------------------
  // Doug's ruling 10-27-26: "Should always show a spinning icon while another
  // page or function is loading" (prds/shared-grid-plan.md).
  //
  //   CBMBusy.loading(gridBox, api("/lists"));   // spinner until it settles
  //   var stop = CBMBusy.loading(panel); ...; stop();
  //
  // Returns the promise it was given (so it can be awaited in place), or a
  // stop function. Visual only: nothing is disabled.
  function loading(el, promise) {
    if (!el || !el.classList) return promise || function () {};
    injectCss();
    el.classList.add("cbm-loading");
    el.setAttribute("aria-busy", "true");
    var count = (el._cbmLoading || 0) + 1;
    el._cbmLoading = count;
    var stopped = false;
    function stop() {
      if (stopped) return;
      stopped = true;
      el._cbmLoading = (el._cbmLoading || 1) - 1;
      if (el._cbmLoading <= 0) { el.classList.remove("cbm-loading"); el.removeAttribute("aria-busy"); }
    }
    if (promise && promise.then) { promise.then(stop, stop); return promise; }
    return stop;
  }

  // --- a link that opens another page --------------------------------------
  // Runs after the page's own handlers (bubble phase). Same tab: the spinner
  // stays until the browser leaves. A new tab, or a link the page handled
  // itself (window.open): a moment, so the press is seen.
  function opensPage(a, e) {
    var href = a.getAttribute("href");
    if (!href || href.charAt(0) === "#" || /^(javascript|mailto|tel|sms|data|blob):/i.test(href) || a.hasAttribute("download")) return false;
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return false;
    try {
      var u = new URL(a.href, location.href);
      if (!/^https?:$/.test(u.protocol)) return false;
      var here = location.href.split("#")[0];
      if (u.href.split("#")[0] === here && !a.target) return false;   // a hash on this page
    } catch (_) { return false; }
    return true;
  }
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || !opensPage(a, e)) return;
    var stop = start(a);
    if (!a.classList.contains("cbm-button")) {
      // An inline link keeps its size: the spinner sits after the text.
      a.classList.remove("cbm-busy");
      a.classList.add("cbm-busy-link");
      stop = function () { a.classList.remove("cbm-busy-link"); };
    }
    var sameTab = !e.defaultPrevented && (!a.target || a.target === "_self");
    setTimeout(stop, sameTab ? 20000 : 1200);
    if (sameTab) window.addEventListener("pagehide", stop, { once: true });
  });

  window.CBMBusy = { start: start, fetch: fetchWithTimeout, loading: loading };
})();
