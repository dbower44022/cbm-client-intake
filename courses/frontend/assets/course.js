/* One training course (prds/training-app-plan.md § 5.2).

   The course's sections come from the server, drawn by courses/render.py
   from the repository's Markdown with every text escaped. A tick saves as it
   is made and an answer as it is typed (decision 6), so the course can be
   stopped and resumed on another computer. Ticking collapses the step and
   brings the next open step or checkpoint to the top of the window, below
   the sticky bar (Step-by-Step Instructions, rule 1). Complete course is
   never disabled: pressed early it names what is missing (decision 7).

   Each step is section.step[data-key] with id "step-<key>", the anchor the
   phase 5 help button will use.

   Every save names the person the page was opened for (asUser). If this
   browser has since signed in as someone else, the server refuses with 409
   and the page says so and offers a reload (v0.362.2): one browser holds one
   sign-in per site, and on the Association the exercises are this same site. */
(function () {
  "use strict";

  var API = "/api/courses";
  var courseId = decodeURIComponent(window.location.pathname.replace(/^\/courses\//, "").replace(/\/.*$/, ""));
  var S = { data: null, progress: {} };
  var SAVE_DELAY_MS = 700;

  function $(id) { return document.getElementById(id); }

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", credentials: "same-origin" };
    if (opts.body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(opts.body);
    }
    return fetch(API + path, init).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) {
          var detail = d && d.detail;
          if (Array.isArray(detail)) detail = "That answer is too long (2,000 characters at most).";
          var e = new Error(detail || ("The server answered " + r.status + "."));
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
    $("courseView").hidden = true;
    $("signin").hidden = true;
  }

  function barMsg(text) { $("barMsg").textContent = text || ""; }

  /* The body of every save: who the page is for (see the header comment). */
  function who(extra) {
    var body = { asUser: S.data.user.id, asName: S.data.user.name };
    Object.keys(extra || {}).forEach(function (k) { body[k] = extra[k]; });
    return body;
  }

  /* A save refused because the browser's sign-in changed: say so, offer a reload. */
  function wrongPerson(e) {
    if (e.status !== 409) return false;
    var bar = $("barMsg");
    bar.textContent = e.message + " ";
    var b = document.createElement("button");
    b.type = "button";
    b.className = "cbm-action--second";
    b.textContent = "Reload this page";
    b.addEventListener("click", function () { window.location.reload(); });
    bar.appendChild(b);
    return true;
  }

  function steps() { return Array.prototype.slice.call(document.querySelectorAll("#course .step")); }
  function checkpoints() { return Array.prototype.slice.call(document.querySelectorAll("#course .checkpoint")); }

  function paint() {
    var st = steps(), cp = checkpoints();
    var ticked = st.filter(function (s) { return s.querySelector(".step-tick").checked; }).length;
    var answered = cp.filter(function (c) { return c.classList.contains("answered"); }).length;
    var text = ticked + " of " + st.length + " steps";
    if (cp.length) text += " · " + answered + " of " + cp.length + " checkpoints";
    $("count").textContent = text;
  }

  function barHeight() {
    var h = $("bar").getBoundingClientRect().height + 8;
    document.documentElement.style.setProperty("--tc-bar-h", h + "px");
  }

  function isOpen(node) {
    if (node.classList.contains("step")) return !node.querySelector(".step-tick").checked;
    return !node.classList.contains("answered");
  }

  /* The next open step or checkpoint after ``from``, else the first open one. */
  function nextOpen(from) {
    var all = Array.prototype.slice.call(document.querySelectorAll("#course .step, #course .checkpoint"));
    var i = all.indexOf(from);
    var after = all.slice(i + 1).filter(isOpen)[0];
    return after || all.filter(isOpen)[0] || null;
  }

  function bringToTop(node) {
    if (!node) return;
    barHeight();
    node.scrollIntoView({ block: "start",
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function wireStep(card) {
    var key = card.getAttribute("data-key"), box = card.querySelector(".step-tick");
    box.checked = !!S.progress[key];
    card.classList.toggle("done", box.checked);
    box.addEventListener("change", function () {
      var on = box.checked;
      card.classList.toggle("done", on);
      paint();
      barMsg("");
      if (on) bringToTop(nextOpen(card));
      api("/" + encodeURIComponent(courseId) + "/items/" + encodeURIComponent(key),
          { method: "PUT", body: who({ done: on }) }).then(function () {
        if (on) S.progress[key] = {}; else delete S.progress[key];
      }).catch(function (e) {
        box.checked = !on;
        card.classList.toggle("done", !on);
        paint();
        if (!wrongPerson(e)) barMsg("Step " + key + " was not saved: " + e.message + " Tick it again.");
      });
    });
  }

  function wireCheckpoint(cp) {
    var key = cp.getAttribute("data-key"), area = cp.querySelector(".checkpoint-a"),
        said = cp.querySelector(".checkpoint-saved"), timer = null, sent = "";
    var have = S.progress[key];
    area.value = (have && have.answer) || "";
    sent = area.value.trim();
    cp.classList.toggle("answered", !!sent);

    function save() {
      timer = null;
      var value = area.value.trim();
      if (value === sent) return;
      said.textContent = "Saving…";
      api("/" + encodeURIComponent(courseId) + "/items/" + encodeURIComponent(key),
          { method: "PUT", body: who({ answer: value }) }).then(function () {
        sent = value;
        cp.classList.toggle("answered", !!value);
        said.textContent = value ? "Saved." : "Answer cleared.";
        paint();
      }).catch(function (e) {
        said.textContent = "Not saved.";
        if (!wrongPerson(e)) said.textContent = "Not saved: " + e.message;
      });
    }
    area.addEventListener("input", function () {
      said.textContent = "";
      if (timer) clearTimeout(timer);
      timer = setTimeout(save, SAVE_DELAY_MS);
    });
    area.addEventListener("blur", function () {
      if (timer) { clearTimeout(timer); }
      save();
    });
  }

  function wireCopy() {
    Array.prototype.forEach.call(document.querySelectorAll("#course .copybtn"), function (b) {
      b.addEventListener("click", function () {
        var code = b.previousElementSibling, text = code.textContent;
        var ok = function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1500); };
        var pick = function () {
          var r = document.createRange(); r.selectNodeContents(code);
          var s = getSelection(); s.removeAllRanges(); s.addRange(r);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, pick);
        else pick();
      });
    });
  }

  function showDone(completion) {
    var b = $("doneBanner");
    b.hidden = !completion;
    if (completion) {
      b.textContent = "You completed this course, revision " + completion.revision + ", on " + completion.date + ".";
    }
  }

  function li(text, href) {
    var item = document.createElement("li");
    var a = document.createElement("a");
    a.href = href;
    a.textContent = text;
    item.appendChild(a);
    return item;
  }

  function showMissing(m) {
    var box = $("missing");
    box.textContent = "";
    var p = document.createElement("p");
    p.textContent = "The course is not complete yet. Still to do:";
    box.appendChild(p);
    if (m.steps.length) {
      var h = document.createElement("strong");
      h.textContent = m.steps.length === 1 ? "1 step not ticked" : m.steps.length + " steps not ticked";
      box.appendChild(h);
      var ul = document.createElement("ul");
      m.steps.forEach(function (s) { ul.appendChild(li(s.label, "#step-" + s.key)); });
      box.appendChild(ul);
    }
    if (m.checkpoints.length) {
      var h2 = document.createElement("strong");
      h2.textContent = m.checkpoints.length === 1 ? "1 checkpoint not answered"
        : m.checkpoints.length + " checkpoints not answered";
      box.appendChild(h2);
      var ul2 = document.createElement("ul");
      m.checkpoints.forEach(function (c) { ul2.appendChild(li("The checkpoint of " + c.label, "#" + c.key)); });
      box.appendChild(ul2);
    }
    box.hidden = false;
    var n = m.steps.length + m.checkpoints.length;
    barMsg(n === 1 ? "1 thing still to do: see the list at the end." : n + " things still to do: see the list at the end.");
  }

  function complete(btn) {
    // A checkpoint answer still waiting for its pause is sent first.
    Array.prototype.forEach.call(document.querySelectorAll("#course .checkpoint-a"), function (a) {
      a.dispatchEvent(new Event("blur"));
    });
    var done = window.CBMBusy ? CBMBusy.start(btn) : function () {};
    setTimeout(function () {
      api("/" + encodeURIComponent(courseId) + "/complete", { method: "POST", body: who() }).then(function (d) {
        done();
        if (!d.completed) {
          showMissing(d.missing);
          if (btn.id === "completeTop") $("missing").scrollIntoView({ block: "center" });
          return;
        }
        $("missing").hidden = true;
        barMsg("");
        showDone(d.completion);
        window.scrollTo(0, 0);
      }).catch(function (e) {
        done();
        if (!wrongPerson(e)) barMsg("The course was not completed: " + e.message);
      });
    }, 300);
  }

  function start() {
    if (!courseId) { fail("No course was named in the address."); return; }
    var p = api("/" + encodeURIComponent(courseId)).then(function (d) {
      S.data = d;
      S.progress = d.progress || {};
      $("signin").hidden = true;
      $("userBar").hidden = false;
      $("whoName").textContent = d.user.name;
      document.title = d.title;
      $("courseTitle").textContent = d.heading;
      if (d.draft) {
        var tag = document.createElement("span");
        tag.className = "tc__draft";
        tag.textContent = "Draft";
        $("courseTitle").appendChild(tag);
      }
      $("revisionLine").innerHTML = d.revisionLine;   // escaped server-side by courses/render.py
      $("course").innerHTML = d.html;                   // escaped server-side by courses/render.py
      $("notice").hidden = !d.notice;
      $("notice").textContent = d.notice || "";
      steps().forEach(wireStep);
      checkpoints().forEach(wireCheckpoint);
      wireCopy();
      showDone(d.completion);
      $("courseView").hidden = false;
      paint();
      barHeight();
      if (!d.completion) {
        var first = document.querySelector("#course .step, #course .checkpoint");
        var open = first && (isOpen(first) ? first : nextOpen(first));
        if (open && Object.keys(S.progress).length) bringToTop(open);
      }
    }).catch(function (e) {
      if (e.status === 401) {
        $("userBar").hidden = true;
        $("signin").hidden = false;
        CBMSignIn.mount($("signin"), { title: "Sign in to take this course", onSignedIn: start });
        return;
      }
      fail(e.message);
    });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(document.querySelector(".tc"), p);
  }

  $("completeTop").addEventListener("click", function () { complete($("completeTop")); });
  $("completeEnd").addEventListener("click", function () { complete($("completeEnd")); });
  window.addEventListener("resize", barHeight);
  start();
})();
