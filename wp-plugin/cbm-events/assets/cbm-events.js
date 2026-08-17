/*
 * CBM Events — website renderer.
 *
 * Renders the upcoming-webinar calendar and the recorded-webinar library from
 * the CBM app's API, emitting EXACTLY the DOM the existing page already styles.
 * The class contract below was read off the live page; Elementor's CSS keys on
 * it, so changing a class name silently unstyles the section:
 *
 *   calendar   .cbm-wb .panel .panel__body > p.month-label + ul.event-list
 *              li.event-item > div.event-date > span.event-date__month
 *                                             + span.event-date__day
 *                            > div.event-info > div.event-info__time
 *                                             + div.event-info__title
 *                                             + div.event-info__meta > span.cbm-meta-text
 *                                                                    + button.cbm-meta-more
 *                                             + button.event-signup-btn
 *   signup     .cbm-wb > div.cbm-modal-overlay > div.cbm-modal
 *                            > button.cbm-modal-close + h3 + p.cbm-modal-sub
 *                            + form > div.cbm-field ×5 + p.cbm-consent-text
 *                                   + button.cbm-submit-btn
 *                            + div.cbm-status
 *   recordings .cbm-yt .panel .panel__body > ul.video-list > li.video-item
 *              > button.video-thumb-btn > img + span.cbm-play-overlay > svg
 *              + div.video-info > div.video-info__date
 *                               + div.video-info__title
 *                               + div.video-info__meta > span.cbm-meta-text
 *                                                      + button.cbm-meta-more
 *
 * The stylesheet that contract keys on ships beside this file as
 * cbm-events.css — copied verbatim from the page's Elementor widgets, because
 * the cutover replaces those widgets (markup, CSS and script together) with the
 * plugin's shortcodes.
 *
 * Data comes from the WordPress proxy (same origin, server-side cached), never
 * straight from the app — so there is no CORS surface and the page survives the
 * app being unreachable by serving the last good copy.
 */
(function (window, document) {
  "use strict";

  var CBMEvents = {};

  /*
   * Thumbnails go through a SAME-ORIGIN proxy, not a hotlink to i.ytimg.com.
   * Verified in the preview pass (2026-07-25): hotlinked i.ytimg.com URLs
   * returned HTTP 503 on this page while the site's own proxied thumbnails
   * loaded fine — which is why the existing page already ships a
   * /wp-json/cbm-yt/v1/thumbnails endpoint. Proxying also keeps visitors from
   * making third-party requests just to view the library.
   *
   * config.thumbnailProxy is a URL prefix the video id is appended to; leave it
   * null only for local previews where no proxy exists.
   *
   * config.eventUrlBase is the prefix a slug is appended to for an event's own
   * page. The payload also carries an absolute `url`, but that is always the
   * LIVE site's address — correct on the website, a 404 anywhere else — so a
   * host that renders somewhere other than the website (the app's preview) sets
   * this and gets links that resolve where it is actually running.
   */
  CBMEvents.config = {
    thumbnailProxy: null,
    imageProxy: null,
    eventUrlBase: null,
  };

  /* The live page truncates both summaries at 140 characters and offers an
     inline More/Less toggle. Same number here so the two agree. */
  var SUMMARY_MAX_LEN = 140;

  /* Card image, in preference order:
   *
   *   1. an uploaded event graphic (payload `imageUrl`) — the only image an
   *      UPCOMING event can have, since there is no recording to derive a
   *      frame from yet;
   *   2. the recording's YouTube thumbnail, proxied by video id;
   *   3. whatever the payload's thumbnailUrl says (local previews only).
   *
   * config.imageProxy, when set, is a URL prefix the app's own image URL is
   * appended to, so the graphic is served same-origin like the thumbnails.
   */
  function thumbnailSrc(item) {
    if (item.imageUrl) {
      return CBMEvents.config.imageProxy
        ? CBMEvents.config.imageProxy + encodeURIComponent(item.imageUrl)
        : item.imageUrl;
    }
    if (CBMEvents.config.thumbnailProxy && item.videoId) {
      return CBMEvents.config.thumbnailProxy + encodeURIComponent(item.videoId);
    }
    return item.thumbnailUrl || "";
  }

  /* Where this event's own page lives, or "" when it has none. */
  function eventUrl(item) {
    if (CBMEvents.config.eventUrlBase) {
      return item.slug
        ? CBMEvents.config.eventUrlBase + encodeURIComponent(item.slug)
        : "";
    }
    return item.url || "";
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text; // textContent: never inject HTML
    return node;
  }

  function truncate(str, maxLen) {
    if (!str || str.length <= maxLen) return null;
    var cut = str.slice(0, maxLen);
    var lastSpace = cut.lastIndexOf(" ");
    return (lastSpace > 40 ? cut.slice(0, lastSpace) : cut) + "…";
  }

  /* The site's summary treatment: the text in a .cbm-meta-text span, plus a
     More/Less button when it was cut. Appended to `host` (.event-info__meta or
     .video-info__meta), which is the element the CSS sizes. */
  function appendSummary(host, summary) {
    var full = summary || "";
    var short = truncate(full, SUMMARY_MAX_LEN);
    var span = el("span", "cbm-meta-text", short == null ? full : short);
    host.appendChild(span);
    if (short == null) return;
    var more = el("button", "cbm-meta-more", "More");
    more.type = "button";
    var expanded = false;
    more.addEventListener("click", function () {
      expanded = !expanded;
      span.textContent = expanded ? full : short;
      more.textContent = expanded ? "Less" : "More";
    });
    host.appendChild(more);
  }

  /* ---- upcoming calendar ------------------------------------------------ */

  CBMEvents.renderCalendar = function (container, webinars, handlers) {
    container.innerHTML = "";
    if (!webinars || !webinars.length) {
      container.appendChild(
        el("p", "cbm-empty", "No upcoming webinars are scheduled right now. Check back soon!")
      );
      return;
    }
    var currentMonth = null;
    var list = null;

    webinars.forEach(function (item) {
      if (item.month !== currentMonth) {
        currentMonth = item.month;
        // The site's CSS uppercases the label; leave the text as sent.
        container.appendChild(el("p", "month-label", item.month || ""));
        list = el("ul", "event-list");
        container.appendChild(list);
      }

      var row = el("li", "event-item");

      var date = el("div", "event-date");
      date.setAttribute("aria-hidden", "true");
      date.appendChild(el("span", "event-date__month", (item.monthShort || "").toUpperCase()));
      date.appendChild(el("span", "event-date__day", item.day || ""));
      row.appendChild(date);

      var info = el("div", "event-info");
      info.appendChild(el("div", "event-info__time", item.time || ""));

      // The title links to the event's own page when it has one (per-event
      // pages are new; a slugless event simply renders as plain text).
      var title = el("div", "event-info__title");
      var href = eventUrl(item);
      if (href) {
        var link = el("a", null, item.topic || "");
        link.href = href;
        title.appendChild(link);
      } else {
        title.textContent = item.topic || "";
      }
      info.appendChild(title);

      var meta = el("div", "event-info__meta");
      appendSummary(meta, item.summary);
      info.appendChild(meta);

      var button = el("button", "event-signup-btn", "Sign Up");
      button.type = "button";
      if (item.registrationOpen === false) {
        button.textContent = "Registration closed";
        button.disabled = true;
      } else if (typeof item.seatsRemaining === "number" && item.seatsRemaining === 0) {
        // Full is not closed: the app puts these people on the waitlist.
        button.textContent = "Join the waitlist";
      }
      button.addEventListener("click", function () {
        if (handlers && handlers.onSignUp) handlers.onSignUp(item);
      });
      info.appendChild(button);

      row.appendChild(info);
      list.appendChild(row);
    });
  };

  /* ---- sign-up modal ----------------------------------------------------- */

  /*
   * Registration stays a one-click modal on the calendar (Doug, 2026-08-16) —
   * the same interaction visitors already know, rather than a trip to the
   * event's page. The event page is for reading about the event; this is for
   * signing up from the list.
   *
   * `host` must be the .cbm-wb element, because that is what the CSS scopes the
   * overlay to. `handlers.register(item, fields)` does the actual POST — the
   * WordPress plugin sends it through its own proxy, the app's preview posts
   * straight to /api/events/{slug}/register — and resolves with the response
   * body, so a `joinUrl` in it becomes the "join here" link the live page shows.
   *
   * Returns { open(item), close() }.
   */
  CBMEvents.mountSignupModal = function (host, handlers) {
    var overlay = el("div", "cbm-modal-overlay");
    var modal = el("div", "cbm-modal");

    var close = el("button", "cbm-modal-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close");
    modal.appendChild(close);

    modal.appendChild(el("h3", null, "Sign Up"));
    var sub = el("p", "cbm-modal-sub");
    modal.appendChild(sub);

    var form = document.createElement("form");
    var inputs = {};
    [
      ["firstName", "First Name", "text", true],
      ["lastName", "Last Name", "text", false],
      ["email", "Email", "email", true],
      ["phone", "Phone", "tel", false],
      ["zip", "Zip Code", "text", false],
    ].forEach(function (spec) {
      var field = el("div", "cbm-field");
      var input = document.createElement("input");
      input.type = spec[2];
      input.id = "cbm-signup-" + spec[0];
      if (spec[3]) input.required = true;
      var label = el("label", null, spec[1]);
      label.htmlFor = input.id;
      field.appendChild(label);
      field.appendChild(input);
      form.appendChild(field);
      inputs[spec[0]] = input;
    });

    form.appendChild(el(
      "p", "cbm-consent-text",
      "By registering, you are agreeing to receive emails about our webinars."
    ));

    var submit = el("button", "cbm-submit-btn", "Register");
    submit.type = "submit";
    form.appendChild(submit);
    modal.appendChild(form);

    var status = el("div", "cbm-status");
    modal.appendChild(status);

    overlay.appendChild(modal);
    host.appendChild(overlay);

    var active = null;

    function setStatus(kind, text, joinUrl) {
      status.className = "cbm-status" + (kind ? " show " + kind : "");
      status.textContent = text || "";
      if (joinUrl) {
        status.appendChild(document.createTextNode(" "));
        var link = el("a", null, "Join here");
        link.href = joinUrl;
        link.target = "_blank";
        link.rel = "noopener";
        status.appendChild(link);
        status.appendChild(document.createTextNode("."));
      }
    }

    function open(item) {
      active = item;
      sub.textContent = (item && item.topic) || "";
      form.reset();
      setStatus("", "");
      // Buttons are never disabled at rest — only while a submit is in flight.
      submit.disabled = false;
      submit.textContent = "Register";
      overlay.classList.add("open");
      inputs.firstName.focus();
    }

    function hide() {
      overlay.classList.remove("open");
      active = null;
    }

    close.addEventListener("click", hide);
    overlay.addEventListener("click", function (ev) {
      if (ev.target === overlay) hide();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && overlay.classList.contains("open")) hide();
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (!active || !handlers || !handlers.register) return;
      var fields = {
        firstName: inputs.firstName.value.trim(),
        lastName: inputs.lastName.value.trim(),
        email: inputs.email.value.trim(),
        phone: inputs.phone.value.trim(),
        zip: inputs.zip.value.trim(),
      };
      // Validate on click and name what is missing, rather than sitting there
      // disabled with no explanation.
      if (!fields.firstName || !fields.email) {
        setStatus("error", "A first name and an email address are required.");
        return;
      }
      submit.disabled = true;
      submit.textContent = "Submitting…";
      setStatus("", "");
      Promise.resolve(handlers.register(active, fields)).then(
        function (result) {
          setStatus(
            "success",
            "You're registered! Check your email for the confirmation.",
            result && result.joinUrl
          );
          form.reset();
          submit.textContent = "Registered";
        },
        function (err) {
          setStatus(
            "error",
            (err && err.message) || "Something went wrong. Please try again."
          );
          submit.disabled = false;
          submit.textContent = "Register";
        }
      );
    });

    return { open: open, close: hide };
  };

  /* ---- recorded library -------------------------------------------------- */

  CBMEvents.renderRecordings = function (container, recordings, handlers) {
    container.innerHTML = "";
    if (!recordings || !recordings.length) {
      container.appendChild(el("p", "cbm-empty", "No recordings matched."));
      return;
    }
    var list = el("ul", "video-list");
    recordings.forEach(function (item) {
      var row = el("li", "video-item");

      var thumb = el("button", "video-thumb-btn");
      thumb.type = "button";
      thumb.setAttribute("aria-label", "Play " + (item.title || "recording"));
      var src = thumbnailSrc(item);
      if (src) {
        var img = document.createElement("img");
        img.src = src;
        img.alt = "";
        img.loading = "lazy";
        thumb.appendChild(img);
      }
      // The overlay's play glyph is an inline SVG on the live page — the CSS
      // sizes `.cbm-play-overlay svg`, so an empty span shows a tint and no
      // triangle.
      var overlay = el("span", "cbm-play-overlay");
      overlay.setAttribute("aria-hidden", "true");
      overlay.innerHTML =
        '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
      thumb.appendChild(overlay);
      thumb.addEventListener("click", function () {
        if (handlers && handlers.onPlay) handlers.onPlay(item);
      });
      row.appendChild(thumb);

      var info = el("div", "video-info");
      info.appendChild(el("div", "video-info__date", item.dateLabel || ""));

      var title = el("div", "video-info__title", item.title || "");
      title.addEventListener("click", function () {
        if (handlers && handlers.onPlay) handlers.onPlay(item);
      });
      info.appendChild(title);

      var meta = el("div", "video-info__meta");
      appendSummary(meta, item.summary);
      info.appendChild(meta);

      row.appendChild(info);
      list.appendChild(row);
    });
    container.appendChild(list);
  };

  window.CBMEvents = CBMEvents;
})(window, document);
