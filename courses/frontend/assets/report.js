/* The training report (prds/training-app-plan.md TR5, § 5.4; phase 3):
   a course picker, one shared grid of people with their status, and a pane
   with one person's checkpoint answers. Read only. Download gives the
   grid's statuses as a CSV file, never the answers (Doug's option B at stop
   3a, 11-21-26). Built with DOM calls, never innerHTML from data. */
(function () {
  "use strict";

  var API = "/api/courses/report";
  var ORDER = ["completed", "due_again", "in_progress", "dismissed", "not_started"];
  var WORDS = { completed: "completed", due_again: "due again", in_progress: "in progress",
                dismissed: "dismissed", not_started: "not started" };
  var st = { course: "", data: null, filter: "", grid: null, open: "" };
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
    $("reportView").hidden = true;
    $("signin").hidden = true;
  }

  function say(text) { $("barMsg").textContent = text || ""; }

  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }

  // --- the counts line: each count filters the grid; a second click clears it ---------
  function drawCounts() {
    var box = $("counts");
    box.textContent = "";
    var people = st.data.people;
    var all = el("button", "tr__count" + (st.filter ? "" : " is-on"), plural(people.length, "person", "people"));
    all.type = "button";
    all.addEventListener("click", function () { st.filter = ""; drawRows(); drawCounts(); });
    box.appendChild(all);
    ORDER.forEach(function (s) {
      var n = st.data.counts[s] || 0;
      box.appendChild(document.createTextNode(" · "));
      var b = el("button", "tr__count tr__count--" + s + (st.filter === s ? " is-on" : ""), n + " " + WORDS[s]);
      b.type = "button";
      b.title = "Show only the people " + WORDS[s] + " (click again for everyone)";
      b.addEventListener("click", function () {
        st.filter = st.filter === s ? "" : s;
        drawRows(); drawCounts();
      });
      box.appendChild(b);
    });
  }

  function drawRows() {
    var body = $("rows");
    body.textContent = "";
    var rows = st.data.people.filter(function (p) { return !st.filter || p.state === st.filter; });
    rows.forEach(function (p) {
      var tr = el("tr");
      var name = el("td", "", p.name);
      if (p.note) name.appendChild(el("span", "tr__note", p.note));
      tr.appendChild(name);
      tr.appendChild(el("td", "", p.teams.join(", ")));
      var status = el("td", "tr__status tr__status--" + p.state, p.words);
      status.setAttribute("data-sort", p.rank + " " + p.words);
      tr.appendChild(status);
      var last = el("td", "", p.last || "—");
      last.setAttribute("data-sort", p.lastAt || "");
      tr.appendChild(last);
      var cell = el("td");
      var b = el("button", "cbm-action--second tr__open", "Answers");
      b.type = "button";
      b.addEventListener("click", function () { openAnswers(p); });
      cell.appendChild(b);
      tr.appendChild(cell);
      if (p.userId === st.open) tr.className = "is-open";
      tr.setAttribute("data-user", p.userId);
      body.appendChild(tr);
    });
    $("grid").hidden = !st.data.people.length;
    $("noneText").hidden = st.data.people.length > 0;
    if (window.CBMGrid) {
      if (!st.grid) st.grid = CBMGrid.enhance($("grid"), { key: "courses.report", sort: [{ col: "name", dir: "asc" }] });
      else st.grid.refresh();
    }
  }

  // --- one person's answers: the question small and grey, the answer dark in a box ----
  function answerList(list) {
    var box = el("div", "tr__answers");
    list.forEach(function (a) {
      var item = el("div", "tr__qa");
      item.appendChild(el("div", "tr__q", (a.section ? a.section + ": " : "") + a.question));
      var ans = el("div", "tr__a" + (a.answer ? "" : " tr__a--none"), a.answer || "Not answered");
      item.appendChild(ans);
      box.appendChild(item);
    });
    return box;
  }

  function openAnswers(p) {
    st.open = p.userId;
    Array.prototype.forEach.call($("rows").children, function (tr) {
      tr.className = tr.getAttribute("data-user") === p.userId ? "is-open" : "";
    });
    $("paneHead").textContent = "Answers: " + p.name;
    var body = $("paneBody");
    body.textContent = "";
    $("pane").hidden = false;
    var read = api("/answers?course=" + encodeURIComponent(st.course) + "&user=" + encodeURIComponent(p.userId));
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(body, read);
    read.then(function (d) {
      body.textContent = "";
      if (d.current) {
        body.appendChild(el("h3", "tr__when", "Saved so far, revision " + d.current.revision));
        body.appendChild(answerList(d.current.answers));
      }
      d.completions.forEach(function (c) {
        body.appendChild(el("h3", "tr__when", "Completed at " + c.revision + " on " + c.date));
        body.appendChild(c.answers.length ? answerList(c.answers)
          : el("p", "tr__a--none", "This revision had no checkpoints."));
      });
      if (!d.current && !d.completions.length) {
        body.appendChild(el("p", "tr__a--none", p.name + " has not answered any checkpoint in this course yet."));
      }
    }).catch(function (e) {
      body.textContent = "";
      body.appendChild(el("p", "tc__error", "The answers could not be read: " + e.message));
    });
  }

  function loadCourse(id) {
    st.course = id;
    st.filter = "";
    st.open = "";
    $("pane").hidden = true;
    say("");
    try { history.replaceState(null, "", "?course=" + encodeURIComponent(id)); } catch (_) { /* the address only */ }
    var read = api("/people?course=" + encodeURIComponent(id));
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading($("gridBox"), read);
    return read.then(function (d) {
      st.data = d;
      drawCounts();
      drawRows();
    }).catch(function (e) {
      $("rows").textContent = "";
      $("counts").textContent = "";
      say("This course's people could not be read: " + e.message);
    });
  }

  function download() {
    if (!st.course || !st.data) { say("Pick a course first, then press Download."); return; }
    var url = API + "/download?course=" + encodeURIComponent(st.course)
      + (st.filter ? "&state=" + encodeURIComponent(st.filter) : "");
    var done = window.CBMBusy && CBMBusy.start ? CBMBusy.start($("downloadBtn")) : function () {};
    fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return null; }).then(function (d) {
        throw new Error((d && d.detail) || ("The server answered " + r.status + "."));
      });
      var name = (r.headers.get("Content-Disposition") || "").replace(/^.*filename="([^"]+)".*$/, "$1") || "training.csv";
      return r.blob().then(function (b) {
        var a = el("a");
        a.href = URL.createObjectURL(b);
        a.download = name;
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
        say("Downloaded " + name + (st.filter ? ", the people " + WORDS[st.filter] + " only." : ".")
          + " The checkpoint answers stay on this page.");
      });
    }).catch(function (e) { say("The file could not be made: " + e.message); })
      .then(function () { done(); });
  }

  function start() {
    var p = api("/courses").then(function (d) {
      $("signin").hidden = true;
      $("userBar").hidden = false;
      $("whoName").textContent = d.user.name;
      var pick = $("coursePick");
      pick.textContent = "";
      d.courses.forEach(function (c) {
        var o = el("option", "", c.title + " — " + c.revision + (c.draft ? " (Draft)" : ""));
        o.value = c.id;
        pick.appendChild(o);
      });
      $("reportView").hidden = false;
      if (!d.courses.length) { say("This deployment offers no courses yet."); return; }
      var want = new URLSearchParams(window.location.search).get("course");
      if (want && d.courses.some(function (c) { return c.id === want; })) pick.value = want;
      return loadCourse(pick.value);
    }).catch(function (e) {
      if (e.status === 401) {
        $("userBar").hidden = true;
        $("signin").hidden = false;
        CBMSignIn.mount($("signin"), { title: "Sign in to read the training report", onSignedIn: start });
        return;
      }
      if (e.status === 404) { fail("Training courses are not switched on."); return; }
      fail(e.message);
    });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(document.querySelector(".tc"), p);
  }

  $("coursePick").addEventListener("change", function () { loadCourse(this.value); });
  $("downloadBtn").addEventListener("click", download);
  $("paneClose").addEventListener("click", function () {
    $("pane").hidden = true;
    st.open = "";
    Array.prototype.forEach.call($("rows").children, function (tr) { tr.className = ""; });
  });
  if (window.CBMSplit) CBMSplit.attach($("gridBox"), $("pane"), { key: "courses.report", initial: 460, min: 300, max: 900, label: "Resize the answers pane" });

  start();
})();
