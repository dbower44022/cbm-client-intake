/* The Training button and the course reminder (prds/training-app-plan.md
 * § 5.1, phase 2). One script, loaded right after textsize.js by every
 * application a course lists:
 *
 *   <script src="/shared/busy.js"></script>
 *   <script src="/shared/textsize.js"></script>
 *   <script src="/shared/training.js"></script>
 *
 * and one empty slot in the application's header, where the button goes:
 *
 *   <span class="cbm-training-slot" data-training-slot></span>
 *
 * ``data-training-class`` on the slot adds the application's own classes to
 * the button, so it matches the header's other buttons (Client Management's
 * small ``sx__sm``).
 *
 * It reads GET /api/courses/mine?app=<route> once per page open, where the
 * route is the first part of the page's address (assignments,
 * mentorsessions, mentoradmin…).
 *
 * - Training courses switched off, signed out, no database, or no course
 *   listing this application: it draws nothing at all.
 * - A course listing this application: the Training button, which opens
 *   /courses/?app=<route> in its own named tab.
 * - A course due (the server's rule, never re-decided here): a bar under
 *   the header with the course's name and length, Start or Continue, and
 *   Don't remind me again. A course due again after a significant revision
 *   shows that revision's change log entry. The bar sits in the page's flow,
 *   so it pushes the application down and never covers a control (TR2).
 *
 * Don't remind me again writes the dismissal (POST …/dismiss, carrying the
 * person the page was opened for, like every course save) and removes the
 * row here and in any other open application tab of this browser. The
 * dismissal belongs to the course, so every application the course lists
 * stops showing it (TR3).
 */
(function () {
  "use strict";

  var route = (location.pathname.split("/")[1] || "").trim();
  if (!route || !window.fetch) return;

  var channel = null;
  try { channel = new BroadcastChannel("cbm-training"); } catch (e) { channel = null; }

  var me = null;          // {id, name}: the person this page was opened for
  var bar = null;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function injectCss() {
    if (document.getElementById("cbm-training-css")) return;
    var link = document.createElement("link");
    link.id = "cbm-training-css";
    link.rel = "stylesheet";
    link.href = "/shared/training.css";
    document.head.appendChild(link);
  }

  function slot() {
    return document.querySelector("[data-training-slot]");
  }

  function header() {
    var s = slot();
    return (s && s.closest("header")) || document.querySelector("header");
  }

  function drawButton() {
    var s = slot();
    if (!s || s.querySelector(".cbm-training-btn")) return;
    var a = el("a", "cbm-button cbm-button--secondary cbm-training-btn", "Training");
    a.href = "/courses/?app=" + encodeURIComponent(route);
    a.target = "cbm-courses";
    a.rel = "noopener";
    a.title = "This application's training courses";
    (s.getAttribute("data-training-class") || "").split(/\s+/).forEach(function (c) {
      if (c) a.classList.add(c);
    });
    s.appendChild(a);
  }

  function minutes(n) {
    return n ? "about " + n + " minutes" : "";
  }

  function removeRow(courseId) {
    if (!bar) return;
    var row = bar.querySelector('[data-course="' + courseId + '"]');
    if (row) row.remove();
    if (!bar.querySelector(".cbm-training-bar__row")) { bar.remove(); bar = null; }
  }

  function dismiss(course, row, btn) {
    var msg = row.querySelector(".cbm-training-bar__msg");
    msg.textContent = "";
    fetch("/api/courses/" + encodeURIComponent(course.id) + "/dismiss", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asUser: me && me.id, asName: me && me.name })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) throw new Error(body.detail || ("The reminder could not be dismissed (" + r.status + ")."));
        removeRow(course.id);
        if (channel) channel.postMessage({ dismissed: course.id });
      });
    }).catch(function (err) {
      msg.textContent = err.message || "The reminder could not be dismissed. Please try again.";
      btn.focus();
    });
  }

  function drawRow(course) {
    var r = course.reminder || {};
    var started = course.status && course.status.state === "in_progress";
    var row = el("div", "cbm-training-bar__row");
    row.setAttribute("data-course", course.id);

    var text = el("div", "cbm-training-bar__text");
    var lead = el("strong", null, r.again ? "This course has changed. Please take it again: " : "Training to complete: ");
    text.appendChild(lead);
    text.appendChild(document.createTextNode(course.title));
    var len = minutes(course.minutes);
    if (len) text.appendChild(el("span", "cbm-training-bar__len", " · " + len));
    if (started) text.appendChild(el("span", "cbm-training-bar__len", " · " + course.status.words));
    if (r.again && r.change) {
      var change = el("div", "cbm-training-bar__change");
      change.appendChild(el("span", "cbm-training-bar__label", "What changed in revision " + course.revision + ": "));
      change.appendChild(document.createTextNode(r.change));
      text.appendChild(change);
    }
    row.appendChild(text);

    var acts = el("div", "cbm-training-bar__acts");
    var go = el("a", "cbm-button cbm-training-bar__go", started ? "Continue" : "Start");
    go.href = course.url;
    go.target = "cbm-course-" + course.id;
    go.rel = "noopener";
    acts.appendChild(go);
    var no = el("button", "cbm-button cbm-button--secondary", "Don't remind me again");
    no.type = "button";
    no.addEventListener("click", function () { dismiss(course, row, no); });
    acts.appendChild(no);
    row.appendChild(acts);

    var msg = el("p", "cbm-training-bar__msg");
    msg.setAttribute("role", "alert");
    row.appendChild(msg);
    return row;
  }

  function drawBar(due) {
    var h = header();
    if (!h || !due.length) return;
    bar = el("section", "cbm-training-bar");
    bar.setAttribute("aria-label", "Training reminder");
    due.forEach(function (c) { bar.appendChild(drawRow(c)); });
    h.insertAdjacentElement("afterend", bar);
  }

  function start() {
    fetch("/api/courses/mine?app=" + encodeURIComponent(route), { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (body) {
        if (!body || !body.courses) return;
        var mine = body.courses.filter(function (c) { return c.forApp; });
        if (!mine.length) return;
        me = body.user || null;
        injectCss();
        drawButton();
        drawBar(mine.filter(function (c) { return c.reminder && c.reminder.due; }));
      })
      .catch(function () { /* Training is never allowed to break the application. */ });
  }

  if (channel) {
    channel.onmessage = function (ev) {
      if (ev && ev.data && ev.data.dismissed) removeRow(ev.data.dismissed);
    };
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
