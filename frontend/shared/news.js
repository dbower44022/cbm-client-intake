/* CBMNews — one Chapter News item as a member sees it (prds/home-page-plan.md
   § 6.1). The home page's News section and past news draw with it, and the
   Chapter News page's live preview draws with the same function, so the
   preview is the member's view, not a copy of it. Look: /shared/panel.css
   (rows, chips, buttons) and /shared/news.css.

     CBMNews.item(it, opts) -> <li>
       it:   {id, title, summary, body (safe HTML), importance, publishAt,
              expiresAt, cta: {label, url} | null, state}
       opts: {open: bool,                 start opened
              past: bool,                 a past-news row: its state, no actions
              onAct: function (it, action, button) -> Promise | undefined}
              action is "dismiss" or "acknowledge". Without onAct (the
              preview) the buttons say what they would do and do nothing.

   Opening is a click on the title; the body is shown below the summary. */
(function () {
  "use strict";

  var ACK = "Must acknowledge", PINNED = "Pinned";
  var DOUBLE_MS = 600;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function utc(stamp) {
    if (!stamp) return null;
    var s = String(stamp);
    var d = new Date(s.length <= 10 ? s + "T00:00:00" : s.replace(" ", "T") + "Z");
    return isNaN(d.getTime()) ? null : d;
  }
  function dateText(stamp) {
    var d = utc(stamp);
    return d ? d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "";
  }

  //: The chip for each importance (plan § 5.3: amber for must acknowledge,
  //: navy for pinned and for the rest).
  function chip(it) {
    if (it.importance === ACK) return el("span", "cbm-kind-chip cbm-tone--amber", "Read & confirm");
    if (it.importance === PINNED) return el("span", "cbm-kind-chip cbm-tone--navy", "Pinned");
    return el("span", "cbm-kind-chip cbm-tone--navy", "News");
  }
  //: Past news says how each item stands, in words and colour.
  var STATE_TONE = { "Acknowledged": "green", "Dismissed": "navy", "Unread": "amber",
                     "Not acknowledged": "red", "Expired": "navy" };

  function item(it, opts) {
    opts = opts || {};
    var li = el("li", "cbm-row news-item" + (it.importance === ACK && !opts.past ? " news-item--ack" : ""));
    li.dataset.newsId = it.id || "";
    li.appendChild(chip(it));

    var what = el("div", "news-item__what");
    var title = el("button", "news-item__title", it.title || "(no title)");
    title.type = "button";
    var bodyId = "news-body-" + (it.id || "preview") + (opts.past ? "-past" : "");
    title.setAttribute("aria-controls", bodyId);
    what.appendChild(title);

    var sub = [it.summary || "", dateText(it.publishAt)].filter(function (x) { return x; });
    if (sub.length) what.appendChild(el("div", "news-item__sub", sub.join(" · ")));

    var body = el("div", "news-item__body");
    body.id = bodyId;
    var html = el("div", "news-item__html");
    html.innerHTML = it.body || "";     // made safe by the server (news/service.member_body)
    body.appendChild(html);
    if (it.cta && it.cta.label && it.cta.url) {
      var go = el("a", "cbm-action news-item__cta", it.cta.label);
      go.href = it.cta.url; go.target = "_blank"; go.rel = "noopener";
      body.appendChild(go);
    }
    what.appendChild(body);
    li.appendChild(what);

    function setOpen(open) {
      body.hidden = !open;
      title.setAttribute("aria-expanded", open ? "true" : "false");
      li.classList.toggle("news-item--open", open);
    }
    setOpen(!!opts.open);
    // A click or double click anywhere on the row opens it (Doug, 11-20-26),
    // as the title does. A second click within DOUBLE_MS is the same gesture,
    // so a double click leaves the item open rather than closing it again.
    // Clicks on the buttons and links, and inside the opened body (to select
    // text or follow a link), are left to themselves.
    var lastToggle = 0;
    li.addEventListener("click", function (ev) {
      var t = ev.target;
      if (t.closest && t !== title && (t.closest("a, input, select, textarea, label")
          || (t.closest("button") && t.closest("button") !== title)
          || t.closest(".news-item__body"))) return;
      var now = Date.now();
      if (now - lastToggle < DOUBLE_MS) return;
      lastToggle = now;
      setOpen(body.hidden);
    });

    var acts = el("div", "news-item__acts");
    if (opts.past) {
      acts.appendChild(el("span", "cbm-pill cbm-tone--" + (STATE_TONE[it.state] || "navy"), it.state || ""));
    } else {
      var ack = it.importance === ACK;
      var btn = el("button", ack ? "cbm-action" : "cbm-action--second", ack ? "I have read this" : "Dismiss");
      btn.type = "button";
      btn.setAttribute("aria-label", (ack ? "I have read " : "Dismiss ") + (it.title || "this item"));
      btn.addEventListener("click", function () {
        if (!opts.onAct) return;
        opts.onAct(it, ack ? "acknowledge" : "dismiss", btn);
      });
      acts.appendChild(btn);
    }
    li.appendChild(acts);
    return li;
  }

  window.CBMNews = { item: item, utc: utc, dateText: dateText };
})();
