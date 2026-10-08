/* The member page for ONE event, at /portal/events/<id> (F5-1).
 *
 * The body — hero, eyebrow, title, when-line, summary, facts, overview and
 * syllabus — is rendered by /shared/event-body.js, the same code the public
 * event page runs, so the two read alike. What this file owns is the read
 * (GET /api/portal/events/<id>, as the signed-in member), the sign-in redirect,
 * the title, and the action box: Register / Registered + Cancel for an Internal
 * event that takes registrations (F5-4), or the two website links for a Public
 * webinar (F5-6). The join link comes already decided by the server (D2).
 *
 * Design: prds/events/CBM_Events_Portal_Calendar_Design.md § 5.
 */
(function () {
  "use strict";

  var API = "/api/portal/events/";

  function $(id) { return document.getElementById(id); }
  function eventId() {
    var parts = location.pathname.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  }
  function orgName() {
    var m = document.querySelector('meta[name="cbm-org"]');
    return (m && m.getAttribute("content")) || "";
  }
  function goLogin() {
    location.href = "/?next=" + encodeURIComponent(location.pathname);
  }
  function message(text, kind) {
    var box = $("msg");
    box.textContent = text || "";
    box.className = "pev__msg" + (kind ? " pev__msg--" + kind : "");
    box.hidden = !text;
  }

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    opts.credentials = "same-origin";
    var resp = await (window.CBMBusy && CBMBusy.fetch
      ? CBMBusy.fetch(API + path, opts)
      : fetch(API + path, opts));
    var data = null;
    try { data = await resp.json(); } catch (e) {}
    if (!resp.ok) {
      var msg = (data && data.detail) || ("Request failed (" + resp.status + ")");
      var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function button(text, cls) {
    var b = el("button", cls || "cbm-button", text);
    b.type = "button";
    return b;
  }
  function result(text, kind) {
    var box = $("actionBox");
    var old = box.querySelector(".pev__result");
    if (old) old.remove();
    if (!text) return;
    box.appendChild(el("p", "pev__result" + (kind ? " pev__result--" + kind : ""), text));
  }
  // One-line confirmation in place of the control that was clicked (F5-4),
  // the same shape the rail uses.
  function confirmInline(host, question, onYes, onNo) {
    var box = el("div", "portal__confirm");
    box.appendChild(el("span", null, question));
    var yes = button("Yes", "cbm-button portal__btn-sm");
    var no = button("No", "portal__link-act");
    box.appendChild(yes); box.appendChild(no);
    host.replaceWith(box);
    no.addEventListener("click", onNo);
    yes.addEventListener("click", function () { onYes(box); });
  }

  // The action box, per state (design § 5).
  function renderAction(ev) {
    var box = $("actionBox");
    box.innerHTML = "";
    var internal = ev.audience !== "Public";
    if (!internal) {
      box.appendChild(el("h3", null, "This is a public webinar"));
      if (ev.publicUrl) {
        box.appendChild(el("p", null, "Sign-up for public webinars happens on the website, where the details and the sign-up form live."));
        var links = el("div", "pev__links");
        var view = el("a", "cbm-button cbm-button--secondary", "View on the website");
        view.href = ev.publicUrl; view.target = "_blank"; view.rel = "noopener";
        var join = el("a", "cbm-button", "Sign up on the website");
        join.href = ev.publicUrl; join.target = "_blank"; join.rel = "noopener";
        links.appendChild(view); links.appendChild(join);
        box.appendChild(links);
      } else if (ev.publicPagesActive === false) {
        box.appendChild(el("p", null, "The public webinar pages are not switched on in this deployment, so there is no website page to link to."));
      } else {
        // The pages are on, but this event has no web address (slug) — it was
        // created outside Event Administration. Saving it there gives it one.
        box.appendChild(el("p", null, "This event has no web address yet, so there is no website page to link to. Opening it in Event Administration and saving it gives it one."));
      }
      box.hidden = false;
      return;
    }
    var reg = ev.myRegistration;
    if (reg) {
      var waitlisted = reg.status === "Waitlisted";
      box.appendChild(el("h3", null, waitlisted ? "You are on the waiting list" : "You are registered"));
      box.appendChild(el("p", null, waitlisted
        ? "We will let you know if a place opens up."
        : "We have your place. If your plans change, cancel below so someone else can take it."));
      var cancel = button("Cancel my registration", "portal__link-act");
      cancel.addEventListener("click", function () {
        confirmInline(cancel, "Cancel your registration for " + (ev.topic || "this event") + "?",
          async function (cbox) {
            cbox.textContent = "Cancelling…";
            try {
              await api(encodeURIComponent(ev.id) + "/cancel", { method: "POST", body: "{}" });
              ev.myRegistration = null;
              await load();          // the join link may change under D2
            } catch (e) { renderAction(ev); result(e.message, "error"); }
          },
          function () { renderAction(ev); });
      });
      box.appendChild(cancel);
      box.hidden = false;
      return;
    }
    if (!ev.canRegister) {
      // Takes registrations but closed: say so. Takes none: no box at all —
      // an event everyone is simply expected at needs no sign-up.
      if (ev.takesRegistrations) {
        box.appendChild(el("p", null, "Registration for this event has closed."));
        box.hidden = false;
      } else {
        box.hidden = true;
      }
      return;
    }
    box.appendChild(el("h3", null, "Register"));
    box.appendChild(el("p", null, "One click — we record it against your own contact record."));
    var reg_btn = button("Register for this event");
    reg_btn.addEventListener("click", function () {
      confirmInline(reg_btn, "Register for " + (ev.topic || "this event") + "?",
        async function (cbox) {
          cbox.textContent = "Registering…";
          try {
            var data = await api(encodeURIComponent(ev.id) + "/register", { method: "POST", body: "{}" });
            ev.myRegistration = { id: data.registrationId, status: data.status || "Registered" };
            await load();          // the join link may appear under D2
          } catch (e) { renderAction(ev); result(e.message, "error"); }
        },
        function () { renderAction(ev); });
    });
    box.appendChild(reg_btn);
    box.hidden = false;
  }

  async function load() {
    var id = eventId();
    if (!id) { message("That event could not be found.", "error"); return; }
    var ev;
    try {
      ev = (await api(encodeURIComponent(id))).event;
    } catch (e) {
      if (e && e.status === 401) { goLogin(); return; }
      message(e && e.status === 404
        ? "That event could not be found."
        : "We could not load this event just now. Please try again shortly.", "error");
      return;
    }
    message("");
    var org = orgName();
    document.title = (ev.topic || "Event") + (org ? " — " + org : "");

    var extra = [];
    if (ev.joinUrl) {
      var a = el("a", null, "Join online");
      a.href = ev.joinUrl; a.target = "_blank"; a.rel = "noopener";
      extra.push(["Join online", a]);
    }
    CBMEventBody.fill(ev, extra);
    renderAction(ev);
    $("eventBody").hidden = false;
  }

  document.addEventListener("DOMContentLoaded", load);
})();
