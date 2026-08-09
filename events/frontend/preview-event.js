/* Per-event page preview.
 *
 * The counterpart to preview.html: what a visitor sees after clicking through
 * from the calendar. On the live site this page is rendered by the WordPress
 * plugin at /webinars/<slug> (Phase 4, not built) — this stands in for it so
 * the content and the registration path can be checked beforehand.
 *
 * Reads the public API only, so the publish gate applies: an unpublished event
 * 404s here exactly as it will on the site.
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

  function slugFromUrl() {
    var params = new URLSearchParams(window.location.search);
    return (params.get("slug") || "").trim();
  }

  /* The overview and syllabus are wysiwyg HTML authored by staff in the CRM.
     Render it as HTML — that is what the website does — but strip scripts and
     inline handlers first. Staff-authored is not the same as trusted. */
  function safeHtml(host, html) {
    host.innerHTML = html || "";
    Array.prototype.forEach.call(
      host.querySelectorAll("script,style,iframe,object,embed"),
      function (node) { node.remove(); }
    );
    Array.prototype.forEach.call(host.querySelectorAll("*"), function (node) {
      Array.prototype.slice.call(node.attributes).forEach(function (attr) {
        var name = attr.name.toLowerCase();
        if (name.indexOf("on") === 0 || (name === "href" && /^javascript:/i.test(attr.value))) {
          node.removeAttribute(attr.name);
        }
      });
    });
    host.hidden = !host.innerHTML.trim();
  }

  function fact(list, key, value) {
    if (!value) return;
    var dt = document.createElement("dt");
    dt.textContent = key;
    var dd = document.createElement("dd");
    dd.textContent = value;
    list.appendChild(dt);
    list.appendChild(dd);
  }

  async function getJson(path) {
    var resp = await fetch(path, { credentials: "omit" });
    if (resp.status === 404) {
      throw new Error(
        "That event is not published (or does not exist), so the public site "
        + "cannot see it either — which is the publish gate working."
      );
    }
    if (!resp.ok) throw new Error("Request failed (" + resp.status + ")");
    return resp.json();
  }

  async function load() {
    var slug = slugFromUrl();
    if (!slug) {
      message("No event given. Open this page from the calendar preview.", "error");
      return;
    }
    try {
      var health = await getJson("/healthz");
      $("envBadge").textContent = health.environment + " · v" + health.version;
    } catch (e) { $("envBadge").textContent = "unknown"; }

    var event;
    try {
      event = (await getJson("/api/events/" + encodeURIComponent(slug))).event;
    } catch (err) {
      message(err.message, "error");
      return;
    }

    $("realUrl").textContent = event.url || "(no public URL yet)";
    document.title = "CBM — " + (event.topic || "Event");

    if (event.imageUrl) {
      $("hero").src = event.imageUrl;
      $("hero").hidden = false;
    }
    $("eyebrow").textContent = [event.category, event.format].filter(Boolean).join(" · ");
    $("title").textContent = event.topic || "(untitled)";
    $("when").textContent = [event.month, event.day, event.time].filter(Boolean).join(" ")
      || "Date to be confirmed";
    $("summary").textContent = event.summary || "";

    var facts = $("facts");
    facts.innerHTML = "";
    fact(facts, "Location", event.location);
    fact(facts, "Type", event.eventType);
    fact(facts, "Seats remaining",
         event.seatsRemaining == null ? "Unlimited" : String(event.seatsRemaining));
    fact(facts, "Registration",
         event.registrationOpen ? "Open" : "Closed");

    safeHtml($("overview"), event.overview);
    safeHtml($("syllabus"), event.syllabus);

    $("signupBox").hidden = false;
    $("eventBody").hidden = false;

    $("registerBtn").addEventListener("click", function () { register(slug); });
  }

  async function register(slug) {
    var out = $("registerResult");
    out.hidden = false;
    var body = {
      // Every submission carries a client-generated idempotency token; without
      // one the endpoint 422s. A fresh token per click, so two deliberate test
      // registrations are two submissions rather than one deduplicated away.
      submission_token: (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : "preview-" + String(Math.floor(performance.now() * 1000)) + "-token",
      company_url: "",          // the honeypot; real users never fill it
      first_name: ($("firstName").value || "").trim(),
      last_name: ($("lastName").value || "").trim(),
      email: ($("email").value || "").trim(),
      phone: ($("phone").value || "").trim(),
      consent: false,
    };
    // Buttons are never disabled — validate on click and name what is missing.
    if (!body.first_name || !body.email) {
      out.textContent = "A first name and an email address are required.";
      out.className = "pv__result pv__result--error";
      return;
    }
    out.textContent = "Registering…";
    out.className = "pv__result";
    try {
      var resp = await fetch("/api/events/" + encodeURIComponent(slug) + "/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "omit",
      });
      var data = null;
      try { data = await resp.json(); } catch (e) { /* no body */ }
      if (!resp.ok) {
        throw new Error((data && (data.detail || data.message)) || ("HTTP " + resp.status));
      }
      out.textContent = "Registered. " + JSON.stringify(data);
      out.className = "pv__result pv__result--ok";
    } catch (err) {
      out.textContent = err.message;
      out.className = "pv__result pv__result--error";
    }
  }

  function applyWidth() {
    var value = $("widthSelect").value;
    $("stage").style.maxWidth = value === "full" ? "none" : value + "px";
  }

  document.addEventListener("DOMContentLoaded", function () {
    $("widthSelect").addEventListener("change", applyWidth);
    applyWidth();
    load();
  });
})();
