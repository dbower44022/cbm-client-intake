/* The Feedback panel (feedback surveys, phases 8 and 9; decisions 3 and 4,
 * 11-20-26): the responses about an engagement, a mentor or an event, one
 * response's answers, and Mark follow-up done. One drawing, three hosts:
 * Client Management's Feedback tab (a mentor: read only), Mentor
 * Administration's Feedback tab and Event Administration's (staff: they
 * close follow-ups).
 *
 *   var panel = CBMFeedback.mount(hostEl, {
 *     key: "mentorsessions.feedback",      // the shared grid's memory key
 *     load: function () { return fetch… }, // -> {available, reason, responses}
 *     detail: function (id) { … },         // -> one response, with sections
 *     markDone: function (id, note) { … }, // staff only; omit for a mentor
 *     about: "engagement" | "mentor" | "event",  // which "About" column
 *     toolbar: [buttonEl, …],              // the host's own buttons (Send …)
 *     openId: "<response id>",             // open at once (an alert's link)
 *   });
 *   panel.reload();
 *
 * Answers stand out from questions (Doug 11-16-26): each question a small
 * grey label, each answer dark in a tinted box. Buttons are never disabled:
 * Mark follow-up done with no note says what is missing. Every text is set
 * with textContent. */
(function (root) {
  "use strict";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function fmtDate(v) {
    if (!v) return "";
    var d = new Date(String(v).replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(v) ? "" : "Z"));
    if (isNaN(d)) return String(v);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function scoreClass(s) {
    if (s === null || s === undefined || s === "") return "fb__score is-none";
    if (s <= 6) return "fb__score is-low";
    if (s <= 8) return "fb__score is-mid";
    return "fb__score is-high";
  }

  // Net promoter score: % of 9-10 minus % of 0-6, over answered scores.
  function summary(rows) {
    var scores = rows.map(function (r) { return r.score; })
      .filter(function (s) { return typeof s === "number"; });
    var open = rows.filter(function (r) { return r.needsFollowUp && !r.followUpDone; }).length;
    if (!scores.length) return { count: rows.length, open: open };
    var sum = scores.reduce(function (a, b) { return a + b; }, 0);
    var pro = scores.filter(function (s) { return s >= 9; }).length;
    var det = scores.filter(function (s) { return s <= 6; }).length;
    return { count: rows.length, open: open, avg: sum / scores.length,
             nps: Math.round(100 * (pro - det) / scores.length), scored: scores.length };
  }

  function followText(r) {
    if (!r.needsFollowUp) return "";
    return r.followUpDone ? "Done" + (r.followUpDoneAt ? " " + fmtDate(r.followUpDoneAt) : "")
                          : "Needs follow-up";
  }

  function answers(sections) {
    var wrap = el("div", "fb__answers");
    (sections || []).forEach(function (sec) {
      var block = el("section", "fb__section");
      block.appendChild(el("h4", "fb__sectitle", sec.title));
      (sec.items || []).forEach(function (it) {
        var qa = el("div", "fb__qa");
        qa.appendChild(el("p", "fb__q", it.label));
        var a = el("div", "fb__a" + (it.answered ? "" : " is-blank"));
        a.textContent = it.answered ? (it.values || []).join(", ") : "Not answered";
        qa.appendChild(a);
        block.appendChild(qa);
      });
      wrap.appendChild(block);
    });
    return wrap;
  }

  function mount(host, opts) {
    opts = opts || {};
    host.innerHTML = "";
    host.classList.add("fb");
    var head = el("div", "fb__head");
    var sumEl = el("p", "fb__summary");
    var tools = el("div", "fb__tools");
    (opts.toolbar || []).forEach(function (b) { tools.appendChild(b); });
    head.appendChild(sumEl); head.appendChild(tools);
    var note = el("p", "fb__notice"); note.hidden = true; note.setAttribute("role", "status");
    var empty = el("p", "fb__empty", "No feedback yet."); empty.hidden = true;
    var table = el("table", "fb__table");
    var thead = el("thead"); var trh = el("tr");
    var aboutLabel = { engagement: "", mentor: "Client", event: "" }[opts.about || ""] || "";
    var cols = [["submitted", "Received"], ["survey", "Survey"], ["moment", "Moment"],
                ["score", "Score"], ["from", "From"]];
    if (aboutLabel) cols.splice(4, 0, ["about", aboutLabel]);
    cols.push(["follow", "Follow-up"]);
    cols.forEach(function (c) { var th = el("th", "", c[1]); th.setAttribute("data-col", c[0]); trh.appendChild(th); });
    thead.appendChild(trh); table.appendChild(thead);
    var tbody = el("tbody"); table.appendChild(tbody);
    table.hidden = true;
    host.appendChild(head); host.appendChild(note); host.appendChild(empty); host.appendChild(table);
    var grid = null;
    var rows = [];
    var dialog = null;

    function say(text, kind) {
      note.textContent = text || "";
      note.className = "fb__notice" + (kind ? " is-" + kind : "");
      note.hidden = !text;
    }

    function paintSummary() {
      var s = summary(rows);
      if (!s.count) { sumEl.textContent = ""; return; }
      var parts = [s.count + (s.count === 1 ? " response" : " responses")];
      if (s.scored) {
        parts.push("average " + s.avg.toFixed(1) + " out of 10");
        parts.push("net promoter score " + (s.nps > 0 ? "+" : "") + s.nps);
      }
      if (s.open) parts.push(s.open + " to follow up");
      sumEl.textContent = parts.join(" · ");
    }

    function paint() {
      tbody.innerHTML = "";
      rows.forEach(function (r) {
        var tr = el("tr", r.needsFollowUp && !r.followUpDone ? "fb__row is-open" : "fb__row");
        tr.tabIndex = 0;
        var cells = {
          submitted: fmtDate(r.submittedAt), survey: r.survey, moment: r.moment,
          score: r.score === null || r.score === undefined ? "—" : String(r.score),
          about: opts.about === "mentor" ? r.engagementName : "",
          from: r.contactName, follow: followText(r),
        };
        cols.forEach(function (c) {
          var td = el("td");
          if (c[0] === "score") {
            td.appendChild(el("span", scoreClass(r.score), cells.score));
            td.setAttribute("data-sort", r.score === null || r.score === undefined ? "" : String(r.score));
          } else if (c[0] === "submitted") {
            td.textContent = cells.submitted || "—";
            td.setAttribute("data-sort", r.submittedAt || "");
          } else {
            td.textContent = cells[c[0]] || "—";
          }
          tr.appendChild(td);
        });
        tr.addEventListener("click", function () { open(r.id); });
        tr.addEventListener("keydown", function (e) { if (e.key === "Enter") open(r.id); });
        tbody.appendChild(tr);
      });
      table.hidden = !rows.length;
      empty.hidden = !!rows.length;
      paintSummary();
      if (root.CBMGrid) {
        if (!grid) grid = root.CBMGrid.enhance(table, { key: opts.key || "feedback" });
        else grid.refresh();
      }
    }

    function closeDialog() { if (dialog) { dialog.close(); dialog.remove(); dialog = null; } }

    async function open(id) {
      closeDialog();
      dialog = el("dialog", "fb__dialog");
      dialog.setAttribute("aria-label", "Feedback response");
      var body = el("div", "fb__dbody", "Loading…");
      var foot = el("div", "fb__dfoot");
      var close = el("button", "cbm-button cbm-button--secondary", "Close");
      close.type = "button";
      close.addEventListener("click", closeDialog);
      foot.appendChild(close);
      dialog.appendChild(body); dialog.appendChild(foot);
      document.body.appendChild(dialog);
      dialog.addEventListener("cancel", function () { setTimeout(closeDialog, 0); });
      dialog.showModal();
      var r;
      try {
        r = await opts.detail(id);
      } catch (e) {
        body.textContent = (e && e.message) || "The response could not be loaded.";
        return;
      }
      body.textContent = "";
      var h = el("h3", "fb__dtitle", r.survey + (r.contactName ? " — " + r.contactName : ""));
      body.appendChild(h);
      var facts = el("p", "fb__facts");
      var bits = [];
      if (r.submittedAt) bits.push("Received " + fmtDate(r.submittedAt));
      if (r.moment) bits.push(r.moment);
      if (r.engagementName) bits.push(r.engagementName);
      if (r.eventName) bits.push(r.eventName);
      if (r.mentorName && opts.about !== "engagement") bits.push("Mentor: " + r.mentorName);
      facts.textContent = bits.join(" · ");
      body.appendChild(facts);
      var scoreLine = el("p", "fb__scoreline");
      scoreLine.appendChild(el("span", "", "Recommendation score "));
      scoreLine.appendChild(el("span", scoreClass(r.score),
        r.score === null || r.score === undefined ? "—" : r.score + " out of 10"));
      body.appendChild(scoreLine);
      if (r.needsFollowUp) {
        var box = el("div", "fb__follow" + (r.followUpDone ? " is-done" : ""));
        box.appendChild(el("p", "fb__follow-head",
          r.followUpDone ? "Follow-up done" + (r.followUpDoneAt ? " " + fmtDate(r.followUpDoneAt) : "")
                         : "Needs follow-up"));
        if (r.reasons && r.reasons.length) {
          box.appendChild(el("p", "fb__follow-why", "Why: " + r.reasons.join("; ") + "."));
        }
        if (r.followUpDone && r.followUpNote) box.appendChild(el("p", "fb__follow-note", r.followUpNote));
        if (!r.followUpDone && opts.markDone) {
          var label = el("label", "fb__label", "What was done");
          var ta = el("textarea", "fb__note");
          ta.rows = 3;
          var id2 = "fbNote" + Date.now();
          ta.id = id2; label.htmlFor = id2;
          var err = el("p", "fb__notice is-error"); err.hidden = true;
          var done = el("button", "cbm-button", "Mark follow-up done");
          done.type = "button";
          done.addEventListener("click", async function () {
            if (!ta.value.trim()) {
              err.textContent = "Say what was done in the note, then mark the follow-up done.";
              err.hidden = false; ta.focus(); return;
            }
            var stop = root.CBMBusy ? root.CBMBusy.start(done) : function () {};
            try {
              await opts.markDone(id, ta.value.trim());
              closeDialog();
              say("Follow-up marked done.", "success");
              reload();
            } catch (e) {
              err.textContent = (e && e.message) || "The follow-up could not be marked done.";
              err.hidden = false;
            } finally { stop(); }
          });
          box.appendChild(label); box.appendChild(ta); box.appendChild(err); box.appendChild(done);
        }
        body.appendChild(box);
      }
      body.appendChild(answers(r.sections));
    }

    async function reload() {
      var p = opts.load();
      if (root.CBMBusy && root.CBMBusy.loading) root.CBMBusy.loading(host, p);
      try {
        var res = await p;
        if (res.available === false) {
          rows = []; table.hidden = true; empty.hidden = true; sumEl.textContent = "";
          say(res.reason || "Feedback is not available here yet.", "");
          return res;
        }
        rows = res.responses || [];
        paint();
        if (opts.openId) { var want = opts.openId; opts.openId = null; open(want); }
        return res;
      } catch (e) {
        if (opts.onError && opts.onError(e) === true) return null;
        say((e && e.message) || "The feedback could not be loaded.", "error");
        return null;
      }
    }

    reload();
    return { reload: reload, open: open, say: say };
  }

  root.CBMFeedback = { mount: mount, summary: summary };
})(typeof window !== "undefined" ? window : this);
