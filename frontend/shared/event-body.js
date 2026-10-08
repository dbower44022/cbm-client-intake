/* CBMEventBody — the body of ONE event, shared by the public event page
 * (/webinars/<slug>) and the portal's member page (/portal/events/<id>).
 *
 * F5-1 ruled that the member page renders the same body the public page does:
 * hero graphic, eyebrow, title, when-line, summary, facts, overview, syllabus.
 * Keeping that body in one file is what makes "the same" true rather than two
 * copies kept in step. Each page keeps its own chrome and its own action box
 * (the public sign-up form; the member's Register / website links).
 *
 * The host page supplies elements with these ids: hero, eyebrow, title, when,
 * summary, facts, presenters, overview, syllabus. Nothing here reads the URL
 * or fetches. The presenter cards (Track F, F4) are styled by
 * /shared/event-body.css, which both pages load — their classes are the
 * pages' own, not the website stylesheet's contract classes.
 */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  /* Overview and syllabus are wysiwyg HTML authored by staff in the CRM. Render
     it as HTML — that is the point of a rich-text field — but strip scripts,
     embedded objects and inline handlers first. Staff-authored is not the same
     as trusted, and the public page is served to the public. */
  function safeHtml(host, html) {
    if (!host) return;
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

  /* "26 September 2026 · 2:00 PM - 3:00 PM | WEBINAR".
   *
   * The payload's `month` is the full "September 2026" and `day` is the bare
   * "26", because the calendar renders them as a two-line date chip. Joined in
   * payload order they read "September 2026 26", which is what the public page
   * did until it was looked at in a browser. */
  function whenLine(event) {
    var month = (event.month || "").trim();
    var day = String(event.day || "").trim();
    var date = (day && month) ? day + " " + month : (month || "");
    var time = (event.time || "").trim();
    var parts = [date, time].filter(Boolean);
    return parts.join(" · ") || "Date to be confirmed";
  }

  /* One row of the facts list. `value` is text, or an element (a link). */
  function fact(list, key, value) {
    if (!value) return;
    var dt = document.createElement("dt");
    dt.textContent = key;
    var dd = document.createElement("dd");
    if (typeof value === "string") dd.textContent = value; else dd.appendChild(value);
    list.appendChild(dt);
    list.appendChild(dd);
  }

  /* Presenter cards (F4): name, title · company, photo, and the biography
     when the payload carries one — the server omits it when the event's
     "Show presenter biographies" switch is off, so this never decides. */
  function presenters(host, list) {
    if (!host) return;
    host.innerHTML = "";
    var rows = Array.isArray(list) ? list : [];
    if (!rows.length) { host.hidden = true; return; }
    var heading = document.createElement("h2");
    heading.className = "evb-presenters__heading";
    heading.textContent = rows.length === 1 ? "Presenter" : "Presenters";
    host.appendChild(heading);
    var grid = document.createElement("div");
    grid.className = "evb-presenters__list" + (rows.length > 1 ? " evb-presenters__list--many" : "");
    rows.forEach(function (p) {
      var card = document.createElement("article");
      card.className = "evb-presenter";
      var media = document.createElement("div");
      media.className = "evb-presenter__media";
      if (p.photoUrl) {
        var img = document.createElement("img");
        img.className = "evb-presenter__photo";
        img.src = p.photoUrl;
        img.alt = p.name || "";
        img.addEventListener("error", function () { media.replaceChildren(initials(p.name)); });
        media.appendChild(img);
      } else {
        media.appendChild(initials(p.name));
      }
      card.appendChild(media);
      var body = document.createElement("div");
      body.className = "evb-presenter__body";
      var name = document.createElement("h3");
      name.className = "evb-presenter__name";
      name.textContent = p.name || "";
      body.appendChild(name);
      var role = [p.title, p.company].filter(Boolean).join(" \u00b7 ");
      if (role) {
        var line = document.createElement("p");
        line.className = "evb-presenter__role";
        line.textContent = role;
        body.appendChild(line);
      }
      if (p.biography) {
        var bio = document.createElement("div");
        bio.className = "evb-presenter__bio";
        safeHtml(bio, p.biography);
        body.appendChild(bio);
      }
      card.appendChild(body);
      grid.appendChild(card);
    });
    host.appendChild(grid);
    host.hidden = false;
  }

  function initials(name) {
    var node = document.createElement("span");
    node.className = "evb-presenter__initials";
    var parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    node.textContent = (parts.length ? parts[0][0] : "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
    node.setAttribute("aria-hidden", "true");
    return node;
  }

  /* Fill the body from an event payload. `extraFacts` is an array of
     [key, value] pairs appended after Location and Format — the public page
     adds Seats remaining, the member page adds Join online. */
  function fill(event, extraFacts) {
    var hero = $("hero");
    if (hero && event.imageUrl) {
      hero.src = event.imageUrl;
      hero.hidden = false;
      hero.addEventListener("error", function () { hero.hidden = true; });
    }
    if ($("eyebrow")) $("eyebrow").textContent = [event.category, event.format].filter(Boolean).join(" · ");
    if ($("title")) $("title").textContent = event.topic || "Workshop";
    if ($("when")) $("when").textContent = whenLine(event);
    if ($("summary")) $("summary").textContent = event.summary || "";

    var facts = $("facts");
    if (facts) {
      facts.innerHTML = "";
      fact(facts, "Location", event.location);
      fact(facts, "Format", event.eventType);
      (extraFacts || []).forEach(function (pair) { fact(facts, pair[0], pair[1]); });
    }
    presenters($("presenters"), event.presenters);
    safeHtml($("overview"), event.overview);
    safeHtml($("syllabus"), event.syllabus);
  }

  window.CBMEventBody = {
    fill: fill, whenLine: whenLine, safeHtml: safeHtml, fact: fact, presenters: presenters,
  };
})();
