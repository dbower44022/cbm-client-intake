/* One event's public page, at /webinars/<slug>.
 *
 * The head of this document — title, description, Open Graph tags — is filled
 * SERVER-SIDE before the page is sent, because a social crawler runs no
 * JavaScript. What this script does is fill the body and run the registration
 * form. The slug is on <body data-event-slug>, put there by the same server
 * render, so this page never has to parse its own URL.
 *
 * Reads the public API only, so the publish gate applies: an unpublished event
 * never reaches here — the server 404s first.
 */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function message(text, kind) {
    var box = $("msg");
    box.textContent = text || "";
    box.className = "pub__msg" + (kind ? " pub__msg--" + kind : "");
    box.hidden = !text;
  }

  function slug() {
    return (document.body.getAttribute("data-event-slug") || "").trim();
  }

  /* Overview and syllabus are wysiwyg HTML authored by staff in the CRM. Render
     it as HTML — that is the point of a rich-text field — but strip scripts,
     embedded objects and inline handlers first. Staff-authored is not the same
     as trusted, and this page is served to the public. */
  function safeHtml(host, html) {
    host.innerHTML = html || "";
    Array.prototype.forEach.call(
      host.querySelectorAll("script,style,iframe,object,embed,form"),
      function (node) { node.remove(); }
    );
    Array.prototype.forEach.call(host.querySelectorAll("*"), function (node) {
      Array.prototype.slice.call(node.attributes).forEach(function (attr) {
        var name = attr.name.toLowerCase();
        var isUrlAttr = name === "href" || name === "src";
        if (name.indexOf("on") === 0
            || (isUrlAttr && /^\s*javascript:/i.test(attr.value))) {
          node.removeAttribute(attr.name);
        }
      });
    });
    host.hidden = !host.innerHTML.trim();
  }

  /* "26 September 2026 - 2:00 PM - 3:00 PM | WEBINAR".
   *
   * The payload's `month` is the full "September 2026" and `day` is the bare
   * "26", because the calendar renders them as a two-line date chip. Joined in
   * payload order they read "September 2026 26", which is what this page did
   * until it was looked at in a browser. */
  function whenLine(event) {
    var month = (event.month || "").trim();
    var day = String(event.day || "").trim();
    var date = (day && month) ? day + " " + month : (month || "");
    var time = (event.time || "").trim();
    var parts = [date, time].filter(Boolean);
    return parts.join(" \u00b7 ") || "Date to be confirmed";
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
    if (!resp.ok) throw new Error("Request failed (" + resp.status + ")");
    return resp.json();
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

  async function load() {
    var s = slug();
    if (!s) {
      message("This event could not be found.", "error");
      return;
    }
    var event;
    try {
      event = (await getJson("/api/events/" + encodeURIComponent(s))).event;
    } catch (err) {
      message("We could not load this session just now. Please try again shortly.", "error");
      return;
    }

    if (event.imageUrl) {
      $("hero").src = event.imageUrl;
      $("hero").hidden = false;
      $("hero").addEventListener("error", function () { $("hero").hidden = true; });
    }
    $("eyebrow").textContent = [event.category, event.format].filter(Boolean).join(" · ");
    $("title").textContent = event.topic || "Workshop";
    $("when").textContent = whenLine(event);
    $("summary").textContent = event.summary || "";

    var facts = $("facts");
    facts.innerHTML = "";
    fact(facts, "Location", event.location);
    fact(facts, "Format", event.eventType);
    if (event.seatsRemaining != null) fact(facts, "Seats remaining", String(event.seatsRemaining));

    safeHtml($("overview"), event.overview);
    safeHtml($("syllabus"), event.syllabus);

    // Registration closed is a fact about the event, not an error — say so
    // where the form would have been, and keep the page readable.
    if (!event.registrationOpen) {
      $("signupSub").textContent =
        "Registration for this session is closed. Browse what else is coming up.";
      var grid = document.querySelector(".pub__signupgrid");
      if (grid) grid.hidden = true;
      $("registerBtn").textContent = "See other sessions";
      $("registerBtn").addEventListener("click", function () {
        window.location.href = "/webinars/";
      });
    } else {
      $("registerBtn").addEventListener("click", submit);
    }

    $("eventBody").hidden = false;
  }

  async function submit() {
    var out = $("registerResult");
    out.hidden = false;
    var body = {
      submission_token: (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : "web-" + String(Date.now()) + "-" + String(Math.floor(Math.random() * 1e9)),
      company_url: ($("companyUrl").value || ""),   // honeypot
      first_name: ($("firstName").value || "").trim(),
      last_name: ($("lastName").value || "").trim(),
      email: ($("email").value || "").trim(),
      phone: ($("phone").value || "").trim(),
      zip_code: ($("zip").value || "").trim(),
      // What the visitor actually ticked. The label names the three documents
      // and links them, so a true here is a real agreement rather than an
      // assumption drawn from small print.
      consent: !!$("consent").checked,
    };
    // Never disable the button — validate on click and name what is missing.
    if (!body.first_name || !body.email) {
      out.textContent = "Please give at least your first name and email address.";
      out.className = "pub__result pub__result--error";
      return;
    }
    if (!body.consent) {
      out.textContent = "Please tick the box to agree before registering.";
      out.className = "pub__result pub__result--error";
      return;
    }
    out.textContent = "Registering…";
    out.className = "pub__result";
    try {
      var resp = await fetch("/api/events/" + encodeURIComponent(slug()) + "/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "omit",
      });
      var data = null;
      try { data = await resp.json(); } catch (e) { /* no body */ }
      if (!resp.ok) {
        throw new Error((data && (data.detail || data.message))
          || "We could not complete your registration.");
      }
      // With async delivery the response returns before the orchestrator has
      // run, so whether this became a seat or a waiting-list place is NOT
      // known here (capacity is evaluated at delivery time, EV-15). Say the
      // one thing that is true either way; the confirmation email carries
      // which it was.
      out.textContent = (data && data.waitlisted)
        ? "You are on the waiting list. We will email you if a place opens up."
        : "Thanks \u2014 we have your registration. Check your email for the details.";
      out.className = "pub__result pub__result--ok";
    } catch (err) {
      out.textContent = err.message;
      out.className = "pub__result pub__result--error";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireLogo();
    load();
  });
})();
