/* The survey page (surveys/router.py; ruling BE23). Any survey purpose uses it.
 *
 * The link's token is the last part of the address; it is the only key this page
 * holds. Answers save as the person goes (ruling BE13): on leaving a section, every
 * SAVE_EVERY_MS while something changed, and when the page is closed. Submit checks
 * the required answers here and again on the server. */
(function () {
  "use strict";

  var SAVE_EVERY_MS = 20000;
  var STATE_WORDS = { not_started: "Not started", in_progress: "In progress", submitted: "Submitted" };
  var token = decodeURIComponent(location.pathname.replace(/\/+$/, "").split("/").pop() || "");
  var api = "/api/survey/" + encodeURIComponent(token);

  var data = null;        // the last state from the server
  var current = null;     // the survey being answered
  var sectionIndex = 0;
  var answers = {};       // the current survey's answers, by question id
  var dirty = false;
  var saving = null;      // the save in flight, if any
  var submissionToken = null;
  // Once a submit has been refused for missing answers, Submit shows on every
  // section (Doug's choice B, 11-13-26) and the marks stay until answered.
  var submitTried = false;
  var marked = {};        // question id -> message, kept across section changes

  function $(id) { return document.getElementById(id); }
  function show(id) {
    ["consentView", "listView", "surveyView", "thanksView"].forEach(function (v) {
      $(v).hidden = v !== id;
    });
    window.scrollTo(0, 0);
  }
  function message(el, text) { el.textContent = text || ""; el.hidden = !text; }
  function newToken() {
    return (window.crypto && crypto.randomUUID && crypto.randomUUID()) ||
      (Date.now().toString(36) + Math.random().toString(36).slice(2));
  }

  function request(method, path, body, opts) {
    var init = { method: method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) init.body = JSON.stringify(body);
    if (opts && opts.keepalive) init.keepalive = true;
    return fetch(api + (path || ""), init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        return { ok: r.ok, status: r.status, body: j };
      });
    });
  }

  function gone() {
    // The link stopped being valid while the page was open: show the server's page.
    location.reload();
  }

  // --- loading and the list ---------------------------------------------------

  function load() {
    return request("GET").then(function (res) {
      $("loading").hidden = true;
      if (res.status === 404) return gone();
      if (!res.ok) {
        message($("pageError"), (res.body && res.body.detail) || "Your surveys could not be loaded. Please try again in a few minutes.");
        return;
      }
      data = res.body;
      if (data.displayName) {
        $("companyName").textContent = data.displayName;
        $("companyLine").hidden = false;
      }
      if (!data.consentGiven) show("consentView"); else renderList();
    }, function () {
      $("loading").hidden = true;
      message($("pageError"), "Your surveys could not be loaded. Please check your connection and try again.");
    });
  }

  function renderList() {
    var list = $("surveyList");
    list.innerHTML = "";
    var allDone = data.surveys.length > 0;
    data.surveys.forEach(function (s) {
      if (s.state !== "submitted") allDone = false;
      var li = document.createElement("li");
      li.className = "survey__item";
      var title = document.createElement("span");
      title.className = "survey__item-title";
      title.textContent = s.title;
      var chip = document.createElement("span");
      chip.className = "survey__chip survey__chip--" + s.state;
      chip.textContent = STATE_WORDS[s.state] || s.state;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cbm-button" + (s.state === "submitted" ? " cbm-button--secondary" : "");
      btn.textContent = s.state === "submitted" ? "View" : (s.state === "in_progress" ? "Continue" : "Start");
      btn.addEventListener("click", function () { openSurvey(s.key); });
      li.appendChild(title);
      li.appendChild(chip);
      li.appendChild(btn);
      list.appendChild(li);
    });
    $("allDone").hidden = !allDone;
    show("listView");
  }

  // --- consent ------------------------------------------------------------------

  $("consentForm").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!$("consentBox").checked) {
      message($("consentError"), "Please tick the box to give your consent before you start.");
      return;
    }
    message($("consentError"), "");
    request("POST", "/consent", { consent: true, company_url: $("consent_company_url").value })
      .then(function (res) {
        if (res.status === 404) return gone();
        if (!res.ok) {
          message($("consentError"), (res.body && res.body.detail) || "That did not work. Please try again.");
          return;
        }
        data.consentGiven = true;
        renderList();
      }, function () {
        message($("consentError"), "That did not reach us. Please check your connection and try again.");
      });
  });

  // --- one survey -----------------------------------------------------------------

  function openSurvey(key) {
    current = data.surveys.filter(function (s) { return s.key === key; })[0];
    if (!current) return;
    answers = JSON.parse(JSON.stringify(current.answers || {}));
    sectionIndex = 0;
    dirty = false;
    submitTried = false;
    marked = {};
    message($("surveyHint"), "");
    submissionToken = newToken();
    $("surveyTitle").textContent = current.title;
    $("surveyIntro").textContent = current.introduction;
    $("submittedNote").hidden = current.state !== "submitted";
    message($("surveyError"), "");
    $("savedNote").textContent = "";
    var progress = $("progress");
    progress.innerHTML = "";
    current.sections.forEach(function (s, i) {
      var li = document.createElement("li");
      li.textContent = s.title;
      li.dataset.step = String(i);
      progress.appendChild(li);
    });
    renderSection();
    show("surveyView");
  }

  function readOnly() { return current && current.state === "submitted"; }

  function renderSection() {
    var section = current.sections[sectionIndex];
    var host = $("sectionHost");
    host.innerHTML = "";
    var h = document.createElement("h3");
    h.textContent = section.title;
    host.appendChild(h);
    if (section.intro) {
      var p = document.createElement("p");
      p.className = "survey__section-intro";
      p.textContent = section.intro;
      host.appendChild(p);
    }
    section.questions.forEach(function (q) { host.appendChild(readOnly() ? answerView(q) : questionInput(q)); });
    Object.keys(marked).forEach(function (id) { showError(id, marked[id]); });
    Array.prototype.forEach.call($("progress").children, function (li, i) {
      li.classList.toggle("is-active", i === sectionIndex);
      li.classList.toggle("is-done", i < sectionIndex);
    });
    var last = sectionIndex === current.sections.length - 1;
    $("prevBtn").textContent = sectionIndex === 0 ? "Back to your surveys" : "Back";
    $("nextBtn").hidden = last;
    $("submitBtn").hidden = readOnly() || !(last || submitTried);
  }

  function shown(q, v) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) return "Not answered";
    if (Array.isArray(v)) return v.join("; ");
    if (q.type === "currency") return "$" + Number(v).toLocaleString();
    if (q.type === "scale") return v + " out of 5";
    return String(v);
  }

  function answerView(q) {
    var wrap = document.createElement("div");
    wrap.className = "survey__question";
    var label = document.createElement("label");
    label.textContent = q.label;
    var p = document.createElement("p");
    p.className = "survey__answer";
    p.textContent = shown(q, answers[q.id]);
    wrap.appendChild(label);
    wrap.appendChild(p);
    return wrap;
  }

  function changed(q, value) {
    if (value === "" || value === null || (Array.isArray(value) && !value.length)) delete answers[q.id];
    else answers[q.id] = value;
    dirty = true;
    clearError(q.id);
    if (marked[q.id] && answered(answers[q.id])) {
      delete marked[q.id];
      summarize();
    }
  }

  function answered(v) {
    return !(v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length));
  }

  // "2 questions still need an answer: 1 in About you, 1 in Where you want to go."
  function summarize() {
    if (!submitTried) return;
    var ids = Object.keys(marked);
    message($("surveyHint"), "");
    if (!ids.length) {
      message($("surveyError"), "");
      message($("surveyHint"), "Every question that needs an answer has one. You can submit the survey now.");
      return;
    }
    var bySection = [];
    current.sections.forEach(function (s) {
      var n = s.questions.filter(function (q) { return marked[q.id]; }).length;
      if (n) bySection.push(n + " in " + s.title);
    });
    message($("surveyError"), (ids.length === 1 ? "1 question still needs" : ids.length + " questions still need") +
      " an answer: " + bySection.join(", ") + ". Each one is marked. You can submit from any section.");
  }

  function sectionOf(qid) {
    var at = 0;
    current.sections.forEach(function (s, si) {
      s.questions.forEach(function (q) { if (q.id === qid) at = si; });
    });
    return at;
  }

  // After a refused submit: go to the first marked question and say what is left.
  function refuse(errors) {
    submitTried = true;
    marked = errors;
    var first = null;
    current.sections.forEach(function (s) {
      s.questions.forEach(function (q) { if (marked[q.id] && first === null) first = q.id; });
    });
    if (first === null) first = Object.keys(marked)[0];
    sectionIndex = sectionOf(first);
    renderSection();
    summarize();
    var el = $("q_" + first);
    if (el) el.scrollIntoView({ block: "center" });
  }

  function questionInput(q) {
    var choice = ["single_choice", "multiple_choice", "yes_no", "scale"].indexOf(q.type) >= 0;
    var wrap = document.createElement(choice ? "fieldset" : "div");
    wrap.className = "survey__question";
    wrap.id = "q_" + q.id;
    var inputId = "in_" + q.id;
    var title = document.createElement(choice ? "legend" : "label");
    title.textContent = q.label;
    if (!choice) title.htmlFor = inputId;
    if (q.required) {
      var star = document.createElement("span");
      star.className = "survey__required";
      star.textContent = "*";
      star.setAttribute("aria-label", "required");
      title.appendChild(star);
    }
    wrap.appendChild(title);
    var helpText = q.help || (q.type === "multiple_choice" && q.max ? "Choose up to " + q.max + "." : "");
    if (helpText) {
      var help = document.createElement("p");
      help.className = "survey__help";
      help.textContent = helpText;
      wrap.appendChild(help);
    }
    var value = answers[q.id];

    if (q.type === "short_text" || q.type === "long_text" || q.type === "number" || q.type === "currency") {
      var el = document.createElement(q.type === "long_text" ? "textarea" : "input");
      el.id = inputId;
      if (q.type !== "long_text") el.type = "text";
      if (q.type === "number" || q.type === "currency") el.inputMode = "decimal";
      el.value = value === undefined ? "" : String(value);
      el.addEventListener("input", function () { changed(q, el.value.trim()); });
      if (q.type === "currency") {
        var money = document.createElement("div");
        money.className = "survey__money";
        var sign = document.createElement("span");
        sign.textContent = "$";
        money.appendChild(sign);
        money.appendChild(el);
        wrap.appendChild(money);
      } else {
        wrap.appendChild(el);
      }
    } else if (q.type === "scale") {
      var scale = document.createElement("div");
      scale.className = "survey__scale";
      if (q.low) { var lo = document.createElement("span"); lo.className = "survey__scale-end"; lo.textContent = q.low; scale.appendChild(lo); }
      [1, 2, 3, 4, 5].forEach(function (n) {
        var lab = document.createElement("label");
        var r = document.createElement("input");
        r.type = "radio"; r.name = inputId; r.value = String(n);
        r.checked = Number(value) === n;
        r.addEventListener("change", function () { changed(q, n); });
        lab.appendChild(r);
        lab.appendChild(document.createTextNode(String(n)));
        scale.appendChild(lab);
      });
      if (q.high) { var hi = document.createElement("span"); hi.className = "survey__scale-end"; hi.textContent = q.high; scale.appendChild(hi); }
      wrap.appendChild(scale);
    } else {
      var options = q.type === "yes_no" ? ["Yes", "No"] : q.options;
      var multi = q.type === "multiple_choice";
      var box = document.createElement("div");
      box.className = "survey__choices";
      options.forEach(function (o) {
        var lab = document.createElement("label");
        var input = document.createElement("input");
        input.type = multi ? "checkbox" : "radio";
        input.name = inputId;
        input.value = o;
        input.checked = multi ? (Array.isArray(value) && value.indexOf(o) >= 0) : value === o;
        input.addEventListener("change", function () {
          if (!multi) return changed(q, o);
          var picked = Array.prototype.filter.call(box.querySelectorAll("input"), function (i) { return i.checked; })
            .map(function (i) { return i.value; });
          if (q.max && picked.length > q.max) {
            input.checked = false;
            showError(q.id, "Please choose no more than " + q.max + ".");
            return;
          }
          changed(q, picked);
        });
        lab.appendChild(input);
        lab.appendChild(document.createTextNode(o));
        box.appendChild(lab);
      });
      wrap.appendChild(box);
    }
    var err = document.createElement("p");
    err.className = "survey__qerror";
    err.id = "err_" + q.id;
    err.hidden = true;
    wrap.appendChild(err);
    return wrap;
  }

  function showError(qid, text) {
    var wrap = $("q_" + qid), err = $("err_" + qid);
    if (!wrap || !err) return;
    wrap.classList.add("survey__question--error");
    err.textContent = text;
    err.hidden = false;
  }
  function clearError(qid) {
    var wrap = $("q_" + qid), err = $("err_" + qid);
    if (!wrap || !err) return;
    wrap.classList.remove("survey__question--error");
    err.hidden = true;
  }

  // --- saving ---------------------------------------------------------------------

  function save(opts) {
    if (!current || readOnly() || !dirty) return Promise.resolve(true);
    if (saving) return saving.then(function () { return save(opts); });
    dirty = false;
    var key = current.key, sent = JSON.parse(JSON.stringify(answers));
    saving = request("PUT", "/answers/" + encodeURIComponent(key), { answers: sent }, opts)
      .then(function (res) {
        saving = null;
        if (res.status === 404) { gone(); return false; }
        if (!res.ok) {
          dirty = true;
          $("savedNote").textContent = (res.body && res.body.detail) || "Not saved yet. We will try again.";
          return false;
        }
        current.answers = sent;
        current.state = res.body.state || current.state;
        $("savedNote").textContent = "Saved.";
        return true;
      }, function () {
        saving = null;
        dirty = true;
        $("savedNote").textContent = "Not saved yet: no connection. We will try again.";
        return false;
      });
    return saving;
  }

  setInterval(function () { save(); }, SAVE_EVERY_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") save({ keepalive: true });
  });
  window.addEventListener("pagehide", function () { save({ keepalive: true }); });

  // --- moving around ----------------------------------------------------------------

  function backToList() {
    save().then(function () { return load(); });
  }

  $("backToList").addEventListener("click", function (e) { e.preventDefault(); backToList(); });
  $("thanksBtn").addEventListener("click", function () { load(); });
  $("prevBtn").addEventListener("click", function () {
    if (sectionIndex === 0) return backToList();
    save();
    sectionIndex -= 1;
    renderSection();
    window.scrollTo(0, 0);
  });
  $("nextBtn").addEventListener("click", function () {
    save();
    sectionIndex += 1;
    renderSection();
    window.scrollTo(0, 0);
  });

  function missing() {
    var gaps = {};
    current.sections.forEach(function (s) {
      s.questions.forEach(function (q) {
        if (q.required && !answered(answers[q.id])) gaps[q.id] = "This question needs an answer.";
      });
    });
    return gaps;
  }

  $("surveyForm").addEventListener("submit", function (e) {
    e.preventDefault();
    if (readOnly()) return;
    message($("surveyError"), "");
    var gaps = missing();
    if (Object.keys(gaps).length) {
      refuse(gaps);
      return;
    }
    request("POST", "/submit/" + encodeURIComponent(current.key), {
      answers: answers, submission_token: submissionToken, company_url: $("company_url").value,
    }).then(function (res) {
      if (res.status === 404) return gone();
      if (res.status === 422 && res.body && res.body.errors) {
        refuse(res.body.errors);
        return;
      }
      if (!res.ok) {
        message($("surveyError"), (res.body && res.body.detail) || "That did not work. Your answers are saved; please try again.");
        return;
      }
      dirty = false;
      current.state = "submitted";
      $("thanksText").textContent = res.body.delivered
        ? "Your " + current.title + " answers have been submitted. Thank you."
        : "Your " + current.title + " answers are submitted and safe with us. We will pass them on to your mentor shortly; there is nothing more you need to do.";
      show("thanksView");
      $("thanksView").focus();
    }, function () {
      message($("surveyError"), "That did not reach us. Your answers are saved; please check your connection and try again.");
    });
  });

  load();
})();
