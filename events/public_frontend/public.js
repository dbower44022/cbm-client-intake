/* The public workshops-and-webinars programme, at /webinars/.
 *
 * This is the page the marketing site redirects to. It drives the SAME renderer
 * the website preview drives (/events-plugin/cbm-events.js) against this
 * deployment's own public API, so what a visitor sees here and what staff see
 * in the preview are one code path, not two that have to be kept in step.
 *
 * Public and unauthenticated: it reads only /api/events/*, which serves
 * published, non-cancelled events and nothing else. The publish gate is the
 * whole boundary to this page.
 */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  var signupModal = null;

  function message(text, kind) {
    var box = $("msg");
    if (!box) return;
    box.textContent = text || "";
    box.className = "pub__msg" + (kind ? " pub__msg--" + kind : "");
    box.hidden = !text;
  }

  async function getJson(path) {
    var resp = await fetch(path, { credentials: "omit" });
    if (!resp.ok) throw new Error("Request failed (" + resp.status + ")");
    return resp.json();
  }

  /* The real registration POST behind the modal's submit.
   *
   * `consent` is now what the visitor actually TICKED (Doug, 2026-09-13). The
   * dialog names the three documents and links them, and refuses to submit
   * until the box is ticked, so a true here means a person agreed to the three
   * things the record is about to claim they agreed to. It used to be hardcoded
   * false — the old line mentioned only emails, so recording three acceptances
   * would have been untrue, and recording none was the lesser wrong. */
  async function register(item, fields) {
    var body = {
      submission_token: (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : "web-" + String(Date.now()) + "-" + String(Math.floor(Math.random() * 1e9)),
      company_url: "",          // the honeypot; real visitors never fill it
      first_name: fields.firstName,
      last_name: fields.lastName,
      email: fields.email,
      phone: fields.phone,
      zip_code: fields.zip,
      consent: !!fields.consent,
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
    window.CBMEvents.renderCalendar($("calendar"), items, {
      onSignUp: function (item) {
        // Buttons are never disabled — say what is wrong on click. An event
        // with no slug has no registration address, which is a staff-side data
        // gap, not something the visitor did.
        if (!item.slug) {
          message(
            "This session cannot be registered for online yet. Please contact us and we will sign you up.",
            "error"
          );
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
    // The site labels its default list "Most Recent". A search result is not
    // that, so the label goes away while one is showing.
    $("recordingsLabel").hidden = !!q || !items.length;
    window.CBMEvents.renderRecordings($("recordings"), items, {
      onPlay: function (item) {
        if (item.recordingUrl) window.open(item.recordingUrl, "_blank", "noopener");
      },
    });
  }

  async function loadAll() {
    message("");
    try {
      await Promise.all([loadCalendar(), loadRecordings()]);
    } catch (err) {
      message(
        "We could not load the programme just now. Please try again in a moment.",
        "error"
      );
    }
  }

  function wireContact() {
    // The address is substituted server-side into the markup; with none
    // configured the invitation still reads sensibly, it just has no mailto.
    var link = $("contactLink");
    var address = link ? (link.textContent || "").trim() : "";
    var looksLikeAddress = address.indexOf("@") > 0;
    if (looksLikeAddress) {
      link.href = "mailto:" + address;
      $("contactLine").hidden = false;
      $("contactBtn").href = "mailto:" + address;
    } else {
      // No address: the button falls back to the website's own contact page
      // rather than sitting there doing nothing.
      var back = document.querySelector(".pub__back");
      $("contactBtn").href = back ? back.getAttribute("href") : "#";
    }
  }

  function wireLogo() {
    var img = $("brandLogo");
    if (!img) return;
    var src = (img.getAttribute("src") || "").trim();
    if (src && src.indexOf("{{") !== 0) {
      img.hidden = false;
      img.addEventListener("error", function () { img.hidden = true; });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireLogo();
    wireContact();
    if (!window.CBMEvents) {
      message("The programme could not be loaded. Please try again shortly.", "error");
      return;
    }
    // Each event's own page is served by this app at /webinars/<slug>.
    window.CBMEvents.config.eventUrlBase = "/webinars/";
    // The three documents the consent tick names. Substituted server-side as
    // this file is served, so a chapter points at its own without a code
    // change; the renderer itself is served without substitution, which is why
    // it takes them from here rather than carrying them.
    window.CBMEvents.config.policies = {
      terms: "{{policyTerms}}",
      privacy: "{{policyPrivacy}}",
      conduct: "{{policyClientConduct}}",
    };
    signupModal = window.CBMEvents.mountSignupModal(
      document.querySelector(".cbm-wb"), { register: register }
    );
    $("searchBtn").addEventListener("click", function () {
      loadRecordings().catch(function () {
        message("The recording search did not work just now.", "error");
      });
    });
    $("searchBox").addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") { ev.preventDefault(); $("searchBtn").click(); }
    });
    loadAll();
  });
})();
