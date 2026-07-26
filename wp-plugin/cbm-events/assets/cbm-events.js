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
 *                                             + button.event-signup-btn
 *   recordings .cbm-yt ... ul.video-list > li.video-item
 *                            > button.video-thumb-btn + div.video-info
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
   */
  CBMEvents.config = { thumbnailProxy: null };

  function thumbnailSrc(item) {
    if (CBMEvents.config.thumbnailProxy && item.videoId) {
      return CBMEvents.config.thumbnailProxy + encodeURIComponent(item.videoId);
    }
    return item.thumbnailUrl || "";
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text; // textContent: never inject HTML
    return node;
  }

  /* ---- upcoming calendar ------------------------------------------------ */

  CBMEvents.renderCalendar = function (container, webinars, handlers) {
    container.innerHTML = "";
    if (!webinars || !webinars.length) {
      container.appendChild(
        el("p", "month-label", "No upcoming webinars are scheduled just now.")
      );
      return;
    }
    var currentMonth = null;
    var list = null;

    webinars.forEach(function (item) {
      if (item.month !== currentMonth) {
        currentMonth = item.month;
        container.appendChild(el("p", "month-label", (item.month || "").toUpperCase()));
        list = el("ul", "event-list");
        container.appendChild(list);
      }

      var row = el("li", "event-item");

      var date = el("div", "event-date");
      date.appendChild(el("span", "event-date__month", (item.monthShort || "").toUpperCase()));
      date.appendChild(el("span", "event-date__day", item.day || ""));
      row.appendChild(date);

      var info = el("div", "event-info");
      info.appendChild(el("div", "event-info__time", item.time || ""));

      // The title links to the event's own page when it has one (per-event
      // pages are new; a slugless event simply renders as plain text).
      var title = el("div", "event-info__title");
      if (item.url) {
        var link = el("a", null, item.topic || "");
        link.href = item.url;
        title.appendChild(link);
      } else {
        title.textContent = item.topic || "";
      }
      info.appendChild(title);

      var meta = el("div", "event-info__meta");
      meta.appendChild(el("span", "cbm-meta-text", item.summary || ""));
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

  /* ---- recorded library -------------------------------------------------- */

  CBMEvents.renderRecordings = function (container, recordings, handlers) {
    container.innerHTML = "";
    if (!recordings || !recordings.length) {
      container.appendChild(el("p", "cbm-search-msg", "No recordings matched."));
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
      thumb.appendChild(el("span", "cbm-play-overlay"));
      thumb.addEventListener("click", function () {
        if (handlers && handlers.onPlay) handlers.onPlay(item);
      });
      row.appendChild(thumb);

      var info = el("div", "video-info");
      info.appendChild(el("p", "video-date", item.dateLabel || ""));
      var title = el("p", "video-title", item.title || "");
      info.appendChild(title);

      var summary = el("p", "video-summary");
      summary.textContent = (item.summary || "").slice(0, 150);
      if ((item.summary || "").length > 150) {
        summary.appendChild(document.createTextNode("… "));
        var more = el("a", "cbm-meta-more", "More");
        more.href = item.url || item.recordingUrl || "#";
        summary.appendChild(more);
      }
      info.appendChild(summary);

      row.appendChild(info);
      list.appendChild(row);
    });
    container.appendChild(list);
  };

  window.CBMEvents = CBMEvents;
})(window, document);
