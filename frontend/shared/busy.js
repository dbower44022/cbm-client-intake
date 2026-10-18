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

  if (window.fetch) {
    var wrappedFetch = window.fetch;
    window.fetch = function (input, init) {
      var done = attach();
      var started = Date.now();
      var method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
      var path = pathOf(input && input.url ? input.url : input);
      var out;
      try {
        out = wrappedFetch.apply(this, arguments);
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

  window.CBMBusy = { start: start, fetch: fetchWithTimeout };
})();
