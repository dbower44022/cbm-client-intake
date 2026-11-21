/* The member's courses (prds/training-app-plan.md, decision 8):
   /courses/?app=<route> lists that application's courses first, then the
   member's other courses, each with its status. Built with DOM calls, never
   innerHTML from data. */
(function () {
  "use strict";

  var API = "/api/courses";
  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function api(path) {
    return fetch(API + path, { credentials: "same-origin" }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) {
          var e = new Error((d && d.detail) || ("The server answered " + r.status + "."));
          e.status = r.status;
          throw e;
        }
        return d;
      });
    });
  }

  function fail(text) {
    $("msgText").textContent = text;
    $("msgView").hidden = false;
    $("listView").hidden = true;
    $("signin").hidden = true;
  }

  function card(c) {
    var box = el("article", "tc__card");
    var h = el("h3");
    var a = el("a", "", c.title);
    a.href = c.url;
    h.appendChild(a);
    if (c.draft) h.appendChild(el("span", "tc__draft", "Draft"));
    box.appendChild(h);
    var meta = "Revision " + c.revision;
    if (c.minutes) meta += " · about " + c.minutes + " minutes";
    box.appendChild(el("p", "tc__meta", meta));
    box.appendChild(el("p", "tc__state tc__state--" + c.status.state, c.status.words));
    var go = el("a", "cbm-button", c.status.state === "in_progress" ? "Continue"
      : (c.status.state === "completed" ? "Open" : "Start"));
    go.href = c.url;
    box.appendChild(go);
    return box;
  }

  function start() {
    var app = new URLSearchParams(window.location.search).get("app") || "";
    var p = api("/mine?app=" + encodeURIComponent(app)).then(function (d) {
      $("signin").hidden = true;
      $("userBar").hidden = false;
      $("whoName").textContent = d.user.name;
      var first = d.courses.filter(function (c) { return c.forApp; });
      var rest = d.courses.filter(function (c) { return !c.forApp; });
      $("appList").textContent = "";
      $("otherList").textContent = "";
      first.forEach(function (c) { $("appList").appendChild(card(c)); });
      rest.forEach(function (c) { $("otherList").appendChild(card(c)); });
      $("appHeading").hidden = !first.length;
      $("appHeading").textContent = "Courses for this application";
      $("otherHeading").hidden = !rest.length;
      $("otherHeading").textContent = first.length ? "Your other courses" : "Your courses";
      $("noneText").hidden = d.courses.length > 0;
      $("listView").hidden = false;
    }).catch(function (e) {
      if (e.status === 401) {
        $("userBar").hidden = true;
        $("signin").hidden = false;
        CBMSignIn.mount($("signin"), { title: "Sign in to see your courses", onSignedIn: start });
        return;
      }
      if (e.status === 404) { fail("Training courses are not switched on."); return; }
      fail(e.message);
    });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(document.querySelector(".tc"), p);
  }

  start();
})();
