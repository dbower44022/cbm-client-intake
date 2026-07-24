/* Shared email-conversation thread rendering — window.CBMConversation.

   One builder for every conversation window in the product so a thread reads
   identically everywhere (directory View Contact, session tools' Communications
   tab, My Email, Submission Admin). See conversation.css for the visual system.

   Message shape (both the Gmail-thread shape and the /ops submission shape):
     { direction, from|fromName|fromAddress, to, sentAt|date, bounce, bodyHtml,
       rfcMessageId, gmailMessageId, sourceMailbox, attachments }
   direction is normalised — "Inbound"/"Outbound" and "received"/"sent" both work.

   messageCard(m, opts) -> HTMLElement
     opts.sanitizeHtml(html)     required-ish; falls back to a tag stripper
     opts.fmtWhen(sentAt)        format the timestamp; falls back to the raw value
     opts.onViewOriginal(m)      if given AND m has the ids, adds "View original"
     opts.gmailMailbox           if given AND m.rfcMessageId, adds "Open in Gmail"
     opts.attachmentsNode(m)     optional Node appended under the body (chips)
     opts.bodyHtml               override body html (e.g. an /ops snippet)

   startedDivider(m, opts) -> HTMLElement  — the "X started this conversation"
     rule the caller inserts once, above the first message. */
(function () {
  "use strict";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // "Name <a@b.com>" / "Name" / "a@b.com" -> display name
  function partyName(addr) {
    var m = /^\s*"?([^"<]+?)"?\s*</.exec(addr || "");
    var name = (m ? m[1] : (addr || "")).trim();
    return name || "(unknown)";
  }
  function extractEmail(addr) {
    var m = /<([^>]+)>/.exec(addr || "");
    return (m ? m[1] : String(addr || "")).trim();
  }

  function initials(name) {
    var parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  // Stable per-person colour from an accessible palette (WCAG-safe with white
  // text). Keyed on the email so the same person is always the same colour.
  var AVATAR_COLORS = [
    "#1D9E75", "#046BD2", "#7F5AD5", "#C7522A", "#0E7C86",
    "#B54A8A", "#4B6BB7", "#8A6D1F", "#2E7D46", "#9C3D54"
  ];
  function avatarColor(key) {
    var s = String(key || "").toLowerCase(), h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return AVATAR_COLORS[h % AVATAR_COLORS.length];
  }

  function normDir(m) {
    if (m && m.bounce) return "bounce";
    var d = String(m && m.direction || "").toLowerCase();
    return (d === "outbound" || d === "sent" || d === "out") ? "out" : "in";
  }

  function stripTags(html) {
    var d = el("div"); d.textContent = String(html || "").replace(/<[^>]*>/g, " ");
    return d.innerHTML;
  }

  // The direction pill: "▼ Received" / "▲ Sent" / "Delivery failed".
  function badge(dir) {
    var d = (dir === "bounce" || dir === "out" || dir === "in") ? dir : normDir({ direction: dir });
    var b = el("span", "cbmc-badge cbmc-badge--" + d);
    if (d === "bounce") { b.textContent = "Delivery failed"; return b; }
    b.appendChild(el("span", "cbmc-arrow", d === "out" ? "▲" : "▼"));
    b.appendChild(document.createTextNode(d === "out" ? "Sent" : "Received"));
    return b;
  }

  function startedDivider(m, opts) {
    opts = opts || {};
    var who = partyName(m && (m.from || m.fromName || m.fromAddress));
    var when = opts.fmtWhen ? opts.fmtWhen(m && (m.sentAt || m.date)) : "";
    var wrap = el("div", "cbmc-started");
    wrap.appendChild(el("span", "cbmc-started-line"));
    wrap.appendChild(el("span", "cbmc-started-txt",
      who + " started this conversation" + (when ? " · " + when : "")));
    wrap.appendChild(el("span", "cbmc-started-line"));
    return wrap;
  }

  function messageCard(m, opts) {
    opts = opts || {};
    var dir = normDir(m);
    var senderRaw = m.from || m.fromName || m.fromAddress || "";
    var senderName = partyName(senderRaw);
    var senderEmail = extractEmail(senderRaw) || senderName;

    // dir is "bounce" for a bounced message, so the modifier already covers it.
    var card = el("div", "cbmc-msg cbmc-msg--" + dir);

    var avatar = el("div", "cbmc-avatar", m.bounce ? "!" : initials(senderName));
    avatar.style.background = m.bounce ? "#c0392b" : avatarColor(senderEmail);
    card.appendChild(avatar);

    var main = el("div", "cbmc-main");
    var head = el("div", "cbmc-head");

    head.appendChild(el("span", "cbmc-name", m.bounce ? "Delivery failed" : senderName));

    head.appendChild(badge(dir));

    // recipient on outbound so "who is being replied to" is explicit
    if (dir === "out" && m.to) head.appendChild(el("span", "cbmc-to", "to " + partyName(m.to)));

    var when = opts.fmtWhen ? opts.fmtWhen(m.sentAt || m.date) : (m.sentAt || m.date || "");
    head.appendChild(el("span", "cbmc-when", when));

    var actions = el("div", "cbmc-actions");
    if (opts.onViewOriginal && m.id && m.gmailMessageId && m.sourceMailbox) {
      var orig = el("a", null, "View original"); orig.href = "#";
      orig.title = "The complete message as it arrived — real formatting, inline images.";
      orig.addEventListener("click", function (e) { e.preventDefault(); opts.onViewOriginal(m); });
      actions.appendChild(orig);
    }
    if (opts.gmailMailbox !== undefined && m.rfcMessageId) {
      var g = el("a", null, "Open in Gmail");
      g.href = "https://mail.google.com/mail/u/" +
        (opts.gmailMailbox ? encodeURIComponent(opts.gmailMailbox) : "0") +
        "/#search/rfc822msgid:" + encodeURIComponent(m.rfcMessageId);
      g.target = "_blank"; g.rel = "noopener";
      g.title = "Opens your own Gmail. If the message isn't in your mailbox, use View original instead.";
      actions.appendChild(g);
    }
    if (actions.childNodes.length) head.appendChild(actions);

    main.appendChild(head);

    if (m.bounce) {
      main.appendChild(el("div", "cbmc-bounce-note",
        "✕ Delivery failed — the address rejected the message. The email was not delivered."));
    }

    var san = opts.sanitizeHtml || stripTags;
    var body = el("div", "cbmc-html");
    body.innerHTML = san(opts.bodyHtml != null ? opts.bodyHtml : (m.bodyHtml || ""));
    main.appendChild(body);

    if (opts.attachmentsNode) {
      var att = opts.attachmentsNode(m);
      if (att) { var wrap = el("div", "cbmc-attach"); wrap.appendChild(att); main.appendChild(wrap); }
    }

    card.appendChild(main);
    return card;
  }

  window.CBMConversation = {
    el: el,
    partyName: partyName,
    extractEmail: extractEmail,
    initials: initials,
    avatarColor: avatarColor,
    normDir: normDir,
    badge: badge,
    messageCard: messageCard,
    startedDivider: startedDivider,
  };
})();
