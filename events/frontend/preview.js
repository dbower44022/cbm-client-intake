/* Website preview for the Events public API.
 *
 * Drives the real plugin renderer against this deployment's own public
 * endpoints, so staff can see what the website will show before the WordPress
 * cutover exists. Same-origin, so no CORS is involved — which is also why this
 * lives in the app rather than as a file you open from disk.
 *
 * It reads ONLY the public API, so it shows exactly what an anonymous visitor
 * would get: published, non-cancelled events and nothing else.
 */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  var signupModal = null;

  function message(text, kind) {
    var box = $("msg");
    box.textContent = text || "";
    box.className = "pv__msg" + (kind ? " pv__msg--" + kind : "");
    box.hidden = !text;
  }

  async function getJson(path) {
    var resp = await fetch(path, { credentials: "omit" });
    if (resp.status === 404) {
      throw new Error(
        "The public API is not switched on for this deployment (EVENTS_PUBLIC_API)."
      );
    }
    if (!resp.ok) throw new Error("Request failed (" + resp.status + ")");
    return resp.json();
  }

  async function loadEnvironment() {
    try {
      var health = await getJson("/healthz");
      $("envBadge").textContent = health.environment + " · v" + health.version;
    } catch (e) {
      $("envBadge").textContent = "unknown";
    }
  }

  /* The real registration POST, behind the modal's submit.
   *
   * This creates genuine CRM records on this deployment — the preview note and
   * the per-event page both say so, and this modal is the same door. Use
   * obvious test data. */
  async function register(item, fields) {
    var body = {
      // Every submission carries a client-generated idempotency token; without
      // one the endpoint 422s. A fresh token per submit, so two deliberate test
      // registrations are two submissions rather than one deduplicated away.
      submission_token: (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : "preview-" + String(Math.floor(performance.now() * 1000)) + "-token",
      company_url: "",          // the honeypot; real users never fill it
      first_name: fields.firstName,
      last_name: fields.lastName,
      email: fields.email,
      phone: fields.phone,
      zip_code: fields.zip,
      // The modal's consent line promises emails about webinars only, while
      // consent:true also records terms-of-use, privacy-policy and code-of-
      // conduct acceptance on the Contact. Sending false claims nothing the
      // visitor was not shown; see the note in the CHANGELOG entry.
      consent: false,
    };
    var resp = await fetch(
      "/api/events/" + encodeURIComponent(item.slug || "") + "/register",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "omit",
      }
    );
    var data = null;
    try { data = await resp.json(); } catch (e) { /* no body */ }
    if (!resp.ok) {
      throw new Error((data && (data.detail || data.message)) || ("HTTP " + resp.status));
    }
    return data || {};
  }

  async function loadCalendar() {
    var data = await getJson("/api/events/upcoming");
    var items = data.webinars || [];
    $("calendarCount").textContent =
      items.length + " published upcoming event" + (items.length === 1 ? "" : "s");
    window.CBMEvents.renderCalendar($("calendar"), items, {
      onSignUp: function (item) {
        if (!item.slug) {
          message("This event has no URL slug yet, so it cannot be registered for.", "error");
          return;
        }
        signupModal.open(item);
      },
    });
  }

  async function loadRecordings() {
    var q = ($("searchBox").value || "").trim();
    var data = await getJson(
      "/api/events/recordings?limit=24" + (q ? "&q=" + encodeURIComponent(q) : "")
    );
    var items = data.recordings || [];
    $("recordingsCount").textContent =
      items.length + " recording" + (items.length === 1 ? "" : "s")
      + (q ? " matching “" + q + "”" : "");
    window.CBMEvents.renderRecordings($("recordings"), items, {
      onPlay: function (item) {
        message("Play would open: " + (item.recordingUrl || "(no recording URL)"), "info");
      },
    });
  }

  async function loadAll() {
    message("");
    try {
      await Promise.all([loadCalendar(), loadRecordings()]);
    } catch (err) {
      message(err.message, "error");
    }
  }

  function applyWidth() {
    var value = $("widthSelect").value;
    var stage = $("stage");
    if (value === "full") {
      stage.style.maxWidth = "none";
    } else {
      stage.style.maxWidth = value + "px";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!window.CBMEvents) {
      message(
        "The plugin renderer did not load (/events-plugin/cbm-events.js). "
        + "It is served only when the Events feature is enabled.",
        "error"
      );
      return;
    }
    // The payload's `url` is always the LIVE site's /webinars/<slug>, which is
    // the Phase 4 rewrite rule and does not exist yet — clicking a title used
    // to leave the preview and 404. Point the renderer at our own stand-in
    // instead, which is what the plugin will do with its own page URL.
    window.CBMEvents.config.eventUrlBase = "preview-event.html?slug=";
    signupModal = window.CBMEvents.mountSignupModal(
      document.querySelector(".cbm-wb"), { register: register }
    );
    $("reloadBtn").addEventListener("click", loadAll);
    $("searchBtn").addEventListener("click", function () {
      loadRecordings().catch(function (e) { message(e.message, "error"); });
    });
    $("searchBox").addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") $("searchBtn").click();
    });
    $("widthSelect").addEventListener("change", applyWidth);
    applyWidth();
    loadEnvironment();
    loadAll();
  });
})();
