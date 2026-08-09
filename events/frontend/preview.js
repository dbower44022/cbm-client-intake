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

  async function loadCalendar() {
    var data = await getJson("/api/events/upcoming");
    var items = data.webinars || [];
    $("calendarCount").textContent =
      items.length + " published upcoming event" + (items.length === 1 ? "" : "s");
    window.CBMEvents.renderCalendar($("calendar"), items, {
      onSignUp: function (item) {
        // The plugin will navigate to the per-event page; here we just show
        // where it would go, so a click doesn't leave the preview.
        message("Sign-up would open: " + (item.url || "(no public URL — the event has no slug)"), "info");
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
