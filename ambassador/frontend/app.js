/* Ambassador Activity — the member's page (prds/Ambassador Program/
   ambassador-program-prd.md § 3; decisions AM1, AM3a, AM7).

   1. Ask the server who is signed in. No valid sign-in: draw the shared
      sign-in box here (frontend/shared/signin.js), then the form.
   2. The form: date, one of six activities, who it was (filled in from our
      records when the email or name is known; every field editable, a
      correction saved on the report only), this person is…, follow-up, note.
   3. Save: the same thank-you every time. It never says whether, or where,
      the contact was found.
   4. My activity: the member's own reports, with Correct inside the window.

   Buttons are never disabled for validation: a click says what is missing. */
(function () {
  "use strict";

  var API = "/ambassador/api";
  var $ = function (id) { return document.getElementById(id); };
  var S = {
    session: null, activity: "", kind: "", agree: null, followUp: null,
    found: null,        // {field: value} filled from our records
    lookedUp: "",       // the email last looked up
    companyId: "", contactId: "", token: "", editing: null, mine: [], grid: null
  };
  var CONTACT_FIELDS = { cEmail: "email", cFirst: "firstName", cLast: "lastName",
                         cOrg: "organization", cTitle: "title", cPhone: "phone" };
  var FIELD_WORDS = { email: "Email", firstName: "First name", lastName: "Last name",
                      organization: "Organization", title: "Title", phone: "Phone" };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function newToken() {
    var a = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(a);
    return Array.prototype.map.call(a, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }

  function api(path, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    if (opts.body && !opts.headers) opts.headers = { "Content-Type": "application/json" };
    return fetch(API + path, opts).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) {
          var detail = d && d.detail;
          if (Array.isArray(detail)) detail = "Something in the form was not accepted. Check each answer.";
          var e = new Error(detail || ("The server answered " + r.status + "."));
          e.status = r.status;
          throw e;
        }
        return d;
      });
    });
  }

  function say(p, text) { p.textContent = text || ""; p.hidden = !text; }

  function fail(text) {
    say($("msgText"), text);
    $("msgView").hidden = false;
    ["formView", "mineView", "doneView", "signin"].forEach(function (id) { $(id).hidden = true; });
  }

  // --- start: who is signed in ------------------------------------------------

  function start() {
    var p = api("/session").then(function (s) {
      S.session = s;
      $("signin").hidden = true;
      $("userBar").hidden = false;
      $("whoName").textContent = s.user.name || s.user.userName;
      $("reviewLink").hidden = !s.isReviewer;
      if (!s.canLog) {
        fail("Your account is not set up to log ambassador activities. Ask the program team to add you.");
        return;
      }
      if (!s.built) {
        fail("The Ambassador Program is not set up in the CRM yet. Ask the program team.");
        return;
      }
      buildForm();
      resetForm();
      $("formView").hidden = false;
      loadMine();
    }).catch(function (e) {
      if (e.status === 401) {
        $("userBar").hidden = true;
        $("signin").hidden = false;
        CBMSignIn.mount($("signin"), {
          title: "Sign in to log an activity",
          onSignedIn: start
        });
        return;
      }
      if (e.status === 404) { fail("The Ambassador Program is not switched on."); return; }
      fail(e.message);
    });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading(document.querySelector(".am"), p);
  }

  // --- the form ------------------------------------------------------------

  function choiceButton(label, value, attr) {
    var b = el("button", "am__choice", label);
    b.type = "button";
    b.setAttribute("aria-pressed", "false");
    b.setAttribute(attr, value);
    return b;
  }

  function press(container, selector, value, attr) {
    Array.prototype.forEach.call(container.querySelectorAll(selector), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute(attr) === value ? "true" : "false");
    });
  }

  var built = false;
  function buildForm() {
    if (built) return;
    built = true;
    var acts = $("actChoices");
    S.session.activities.forEach(function (a) {
      acts.appendChild(choiceButton(a.label, a.value, "data-act"));
    });
    acts.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-act]");
      if (!b) return;
      S.activity = b.getAttribute("data-act");
      press(acts, "[data-act]", S.activity, "data-act");
      showContact();
    });
    var kinds = $("kindChoices");
    S.session.personKinds.forEach(function (k) {
      kinds.appendChild(choiceButton(k.label, k.value, "data-kind"));
    });
    kinds.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-kind]");
      if (!b) return;
      setKind(b.getAttribute("data-kind"));
    });
    document.querySelector("[data-agree]").parentNode.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-agree]");
      if (!b) return;
      S.agree = b.getAttribute("data-agree") === "yes";
      press(b.parentNode, "[data-agree]", b.getAttribute("data-agree"), "data-agree");
    });
    document.querySelector("[data-fu]").parentNode.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-fu]");
      if (!b) return;
      S.followUp = b.getAttribute("data-fu") === "yes";
      press(b.parentNode, "[data-fu]", b.getAttribute("data-fu"), "data-fu");
      $("noteHelp").textContent = S.followUp
        ? "Tell us what help you need. An event or organization name helps."
        : "An event or organization name helps. Keep client details and confidential mentoring information out of this form.";
    });
    var editType = $("editType");
    S.session.activities.forEach(function (a) {
      var o = el("option", null, a.label); o.value = a.value; editType.appendChild(o);
    });

    $("cEmail").addEventListener("change", lookupEmail);
    $("cEmail").addEventListener("blur", lookupEmail);
    $("cFirst").addEventListener("input", searchPeople);
    $("cLast").addEventListener("input", searchPeople);
    $("cOrg").addEventListener("input", function () { S.companyId = ""; $("companyPick").hidden = true; });
    $("notThisPerson").addEventListener("click", notThisPerson);
    $("reportForm").addEventListener("submit", save);
    $("anotherBtn").addEventListener("click", function () {
      resetForm(); $("doneView").hidden = true; $("formView").hidden = false;
      window.scrollTo(0, 0);
    });
    $("editCancel").addEventListener("click", function () { $("editDialog").hidden = true; });
    $("editSave").addEventListener("click", saveCorrection);
    document.addEventListener("click", function (ev) {
      if (!ev.target.closest("#peopleList") && ev.target.id !== "cFirst" && ev.target.id !== "cLast") {
        $("peopleList").hidden = true;
      }
    });
  }

  function activityDef() {
    var a = null;
    S.session.activities.forEach(function (x) { if (x.value === S.activity) a = x; });
    return a;
  }

  function showContact() {
    var a = activityDef();
    var show = a && a.contact !== "none";
    $("contactBlock").hidden = !show;
    $("contactLegend").textContent = a && a.contact === "required"
      ? "Who did you refer?" : "Who did you talk to? (optional)";
  }

  function setKind(kind) {
    S.kind = kind;
    press($("kindChoices"), "[data-kind]", kind, "data-kind");
    var referral = S.session.referralKinds.indexOf(kind) !== -1;
    $("agreeQ").hidden = !referral;
    if (!referral) S.agree = null;
  }

  function resetForm() {
    S.activity = ""; S.kind = ""; S.agree = null; S.followUp = null;
    S.found = null; S.lookedUp = ""; S.companyId = ""; S.contactId = "";
    S.token = newToken();
    $("actDate").value = S.session.today;
    $("actDate").max = S.session.today;
    Object.keys(CONTACT_FIELDS).forEach(function (id) {
      $(id).value = ""; $(id).classList.remove("am__filled");
    });
    $("note").value = "";
    ["actChoices", "kindChoices"].forEach(function (id) {
      Array.prototype.forEach.call($(id).querySelectorAll(".am__choice"), function (b) {
        b.setAttribute("aria-pressed", "false");
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-agree],[data-fu]"), function (b) {
      b.setAttribute("aria-pressed", "false");
    });
    $("contactBlock").hidden = true; $("agreeQ").hidden = true;
    $("foundNote").hidden = true; $("memberNote").hidden = true;
    $("companyPick").hidden = true; $("peopleList").hidden = true;
    say($("formError"), "");
  }

  // --- the lookups (AM3a) ----------------------------------------------------

  function fill(values, fields) {
    S.found = S.found || {};
    fields.forEach(function (f) {
      var id = null;
      Object.keys(CONTACT_FIELDS).forEach(function (k) { if (CONTACT_FIELDS[k] === f) id = k; });
      if (!id) return;
      var v = values[f] || "";
      if (!v) return;
      $(id).value = v;
      $(id).classList.add("am__filled");
      S.found[f] = v;
    });
  }

  function clearFound(keepEmail) {
    Object.keys(CONTACT_FIELDS).forEach(function (id) {
      if (S.found && S.found[CONTACT_FIELDS[id]] !== undefined && !(keepEmail && id === "cEmail")) {
        $(id).value = "";
      }
      $(id).classList.remove("am__filled");
    });
    S.found = null; S.contactId = ""; S.companyId = "";
    $("foundNote").hidden = true;
  }

  function showFound(text) {
    $("foundText").textContent = text;
    $("foundNote").hidden = false;
  }

  function usePerson(res) {
    var p = res.person;
    S.contactId = p.contactId || "";
    S.companyId = p.companyId || "";
    fill(p, ["email", "firstName", "lastName", "organization", "title", "phone"]);
    showFound("From our records.");
    if (res.isPartner && !S.kind) setKind("Existing organization");
  }

  function lookupEmail() {
    var email = $("cEmail").value.trim();
    if (!email || email === S.lookedUp) return;
    S.lookedUp = email;
    $("memberNote").hidden = true;
    $("companyPick").hidden = true;
    if (S.found) clearFound(true);
    api("/lookup/email?email=" + encodeURIComponent(email)).then(function (res) {
      if ($("cEmail").value.trim() !== email) return;
      if (res.kind === "member") { $("memberNote").hidden = false; return; }
      if (res.kind === "person") { usePerson(res); return; }
      if (res.kind === "company") {
        if (res.companies.length === 1) { useCompany(res.companies[0]); return; }
        var box = $("companyChoices"); box.textContent = "";
        res.companies.forEach(function (c) {
          var b = choiceButton(c.organization + (c.website ? " (" + c.website + ")" : ""), c.companyId, "data-company");
          b.addEventListener("click", function () { useCompany(c); $("companyPick").hidden = true; });
          box.appendChild(b);
        });
        var none = choiceButton("None of these", "", "data-company");
        none.addEventListener("click", function () { $("companyPick").hidden = true; });
        box.appendChild(none);
        $("companyPick").hidden = false;
      }
    }).catch(function () { /* a lookup that fails leaves the form as typed */ });
  }

  function useCompany(c) {
    S.companyId = c.companyId;
    fill(c, ["organization"]);
    showFound("Company from our records.");
    if (c.isPartner && !S.kind) setKind("Existing organization");
  }

  var searchTimer = null;
  function searchPeople() {
    if (S.contactId) return;   // a person is already filled in
    clearTimeout(searchTimer);
    var q = ($("cFirst").value.trim() + " " + $("cLast").value.trim()).trim();
    if (q.length < 3) { $("peopleList").hidden = true; return; }
    searchTimer = setTimeout(function () {
      api("/lookup/people?q=" + encodeURIComponent(q)).then(function (res) {
        var list = $("peopleList"); list.textContent = "";
        if (!res.people.length) { list.hidden = true; return; }
        res.people.forEach(function (p) {
          var li = el("li");
          var b = el("button", "am__suggestbtn");
          b.type = "button";
          b.appendChild(el("strong", null, (p.firstName + " " + p.lastName).trim()));
          var sub = [p.organization, p.email].filter(Boolean).join(" · ");
          if (sub) b.appendChild(el("span", null, sub));
          b.addEventListener("click", function () {
            list.hidden = true;
            api("/lookup/person/" + encodeURIComponent(p.contactId)).then(function (res2) {
              S.lookedUp = res2.person.email || "";
              usePerson(res2);
            }).catch(function () { /* left as typed */ });
          });
          li.appendChild(b);
          list.appendChild(li);
        });
        list.hidden = false;
      }).catch(function () { $("peopleList").hidden = true; });
    }, 250);
  }

  function notThisPerson() {
    clearFound(false);
    S.lookedUp = $("cEmail").value.trim();
  }

  function contactValues() {
    var out = { contactId: S.contactId, companyId: S.companyId };
    Object.keys(CONTACT_FIELDS).forEach(function (id) { out[CONTACT_FIELDS[id]] = $(id).value.trim(); });
    // A company name edited away from the one we filled in is a new name.
    if (S.found && S.found.organization !== undefined && out.organization !== S.found.organization) {
      out.companyId = "";
    }
    return out;
  }

  function corrections(values) {
    var out = [];
    if (!S.found || !S.contactId) return out;
    Object.keys(S.found).forEach(function (f) {
      if ((values[f] || "") !== (S.found[f] || "")) {
        out.push({ field: FIELD_WORDS[f] || f, ours: S.found[f] || "", theirs: values[f] || "" });
      }
    });
    return out;
  }

  // --- save -----------------------------------------------------------------

  function save(ev) {
    ev.preventDefault();
    var err = $("formError");
    say(err, "");
    var a = activityDef();
    if (!$("actDate").value) { say(err, "Enter the date you did it."); $("actDate").focus(); return; }
    if ($("actDate").value > S.session.today) { say(err, "The date cannot be in the future."); return; }
    if (!a) { say(err, "Choose what you did."); return; }
    var values = a.contact === "none" ? null : contactValues();
    var named = values && (values.contactId || values.email || values.firstName || values.lastName);
    if (a.contact === "required" && !named) {
      say(err, "Say who you referred: their email address, or their name."); $("cEmail").focus(); return;
    }
    if (!$("memberNote").hidden && values && values.email) {
      say(err, "That is a member's address: clear it, or log the activity without a contact."); return;
    }
    if (named && !S.kind) { say(err, "Answer “This person is…”."); return; }
    if (S.followUp === null) { say(err, "Answer “Does {{abbr}} need to follow up?”"); return; }
    if (S.followUp && !$("note").value.trim()) {
      say(err, "You asked for follow-up: say in “Anything we should know?” what help you need.");
      $("note").focus(); return;
    }
    var body = {
      submissionToken: S.token,
      activityDate: $("actDate").value,
      activityType: S.activity,
      contact: named ? values : null,
      personKind: named ? S.kind : "",
      marketingAgreed: !!S.agree,
      followUp: S.followUp,
      note: $("note").value.trim(),
      corrections: named ? corrections(values) : []
    };
    var btn = $("saveBtn");
    var done = window.CBMBusy ? CBMBusy.start(btn) : function () {};
    api("/reports", { method: "POST", body: JSON.stringify(body) }).then(function (res) {
      $("doneRef").textContent = res.reference;
      $("doneFollowUp").hidden = !res.followUp;
      $("formView").hidden = true;
      $("doneView").hidden = false;
      window.scrollTo(0, 0);
      loadMine();
    }).catch(function (e) {
      if (e.status === 401) { start(); return; }
      say(err, e.message);
    }).then(done, done);
  }

  // --- My activity (AM7) -------------------------------------------------------

  function shownDate(iso) {
    if (!iso) return "";
    var d = new Date(iso + "T12:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function labelFor(value) {
    var label = value;
    (S.session.activities || []).forEach(function (a) { if (a.value === value) label = a.label; });
    return label;
  }

  function loadMine() {
    var p = api("/mine").then(function (res) {
      S.mine = res.rows || [];
      $("mineHelp").textContent = "You can correct the date, activity and note of a report for "
        + (res.editDays || S.session.editDays) + " days after you save it.";
      drawMine();
      $("mineView").hidden = false;
    }).catch(function (e) {
      if (e.status === 401) return;
      $("mineView").hidden = false;
      $("mineHelp").textContent = "Your activity could not be read just now: " + e.message;
    });
    if (window.CBMBusy && CBMBusy.loading) CBMBusy.loading($("mineView"), p);
  }

  function drawMine() {
    var body = $("mineBody"); body.textContent = "";
    $("mineEmpty").hidden = S.mine.length > 0;
    $("mineTable").hidden = S.mine.length === 0;
    S.mine.forEach(function (r) {
      var tr = el("tr");
      var td = el("td", null, shownDate(r.activityDate)); td.setAttribute("data-sort", r.activityDate); tr.appendChild(td);
      tr.appendChild(el("td", null, labelFor(r.activityType)));
      tr.appendChild(el("td", null, r.contact || "—"));
      var fu = el("td", null, r.followUp || "—");
      if (r.followUp === "Done" && r.followUpNote) fu.title = r.followUpNote;
      tr.appendChild(fu);
      tr.appendChild(el("td", null, r.outcome || "—"));
      var act = el("td");
      if (r.saving) {
        act.appendChild(el("span", "am__saving", r.failed ? "Not recorded yet — the program team has been told" : "Saving…"));
      } else {
        var b = el("button", "cbm-action--second", "Correct");
        b.type = "button";
        b.addEventListener("click", function () { openCorrection(r); });
        act.appendChild(b);
      }
      tr.appendChild(act);
      body.appendChild(tr);
    });
    if (window.CBMGrid && !S.grid && S.mine.length) {
      S.grid = CBMGrid.enhance($("mineTable"), { key: "ambassador.mine", sort: [{ col: "date", dir: "desc" }] });
    } else if (S.grid) {
      S.grid.refresh();
    }
  }

  function openCorrection(r) {
    if (!r.editable) {
      // Never a hidden or disabled button: the click says why.
      alertBox("This report can no longer be changed: corrections are open for "
        + S.session.editDays + " days after a report is saved. Ask the program team to change it.");
      return;
    }
    S.editing = r;
    $("editDate").value = r.activityDate;
    $("editDate").max = S.session.today;
    $("editType").value = r.activityType;
    $("editNote").value = r.note || "";
    say($("editError"), "");
    $("editDialog").hidden = false;
    $("editDate").focus();
  }

  function alertBox(text) {
    S.editing = null;
    say($("editError"), text);
    ["editDate", "editType", "editNote"].forEach(function (id) { $(id).parentNode.hidden = true; });
    $("editSave").hidden = true;
    $("editDialog").hidden = false;
    var restore = function () {
      ["editDate", "editType", "editNote"].forEach(function (id) { $(id).parentNode.hidden = false; });
      $("editSave").hidden = false;
      $("editCancel").removeEventListener("click", restore);
    };
    $("editCancel").addEventListener("click", restore);
  }

  function saveCorrection() {
    var r = S.editing;
    if (!r) return;
    var err = $("editError");
    if (!$("editDate").value) { say(err, "Enter the date you did it."); return; }
    var body = { activityDate: $("editDate").value, activityType: $("editType").value,
                 note: $("editNote").value };
    var done = window.CBMBusy ? CBMBusy.start($("editSave")) : function () {};
    api("/mine/" + encodeURIComponent(r.id), { method: "PUT", body: JSON.stringify(body) })
      .then(function () { $("editDialog").hidden = true; loadMine(); })
      .catch(function (e) { say(err, e.message); })
      .then(done, done);
  }

  $("logoutBtn").addEventListener("click", function () {
    api("/logout", { method: "POST" }).then(function () { window.location.reload(); },
                                            function () { window.location.reload(); });
  });

  start();
})();
