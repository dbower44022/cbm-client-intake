/* CBM Client Intake — four-step wizard (Requirements Specification §4). */
(function () {
  "use strict";

  const OPT = window.CBM_OPTIONS;
  const form = document.getElementById("intakeForm");
  const steps = Array.from(document.querySelectorAll(".step"));
  const progressItems = Array.from(document.querySelectorAll("#progress li"));
  const backBtn = document.getElementById("backBtn");
  const nextBtn = document.getElementById("nextBtn");
  const submitBtn = document.getElementById("submitBtn");
  const formError = document.getElementById("formError");
  const TOTAL = steps.length;
  let current = 1;

  // Stable per-load token so retries are idempotent (Technical Design §4.2).
  const submissionToken =
    (window.crypto && crypto.randomUUID && crypto.randomUUID()) ||
    "tok-" + Date.now() + "-" + Math.random().toString(36).slice(2);

  // Honeypot — only count it filled when actual keystrokes landed in it;
  // browser autofill sets hidden-field values without typing (false positives).
  const honeypot = document.getElementById("xtra_note");
  let honeypotKeystrokes = 0;
  if (honeypot) {
    honeypot.addEventListener("keydown", () => {
      honeypotKeystrokes += 1;
    });
  }

  // Alphabetize a value list, but always sink a literal "Other" to the bottom.
  // ("Please select…" is added separately as the placeholder and stays on top.)
  function sortOptions(values) {
    const rest = [];
    const other = [];
    values.forEach((v) => (v === "Other" ? other : rest).push(v));
    rest.sort((a, b) => a.localeCompare(b));
    return rest.concat(other);
  }

  // --- Populate option-driven controls ---
  function fillSelect(id, values, { placeholder, sort } = {}) {
    const sel = document.getElementById(id);
    if (!sel) return;
    if (placeholder !== undefined) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = placeholder;
      sel.appendChild(o);
    }
    (sort ? sortOptions(values) : values).forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      sel.appendChild(o);
    });
  }

  // Reference lists are alphabetized (Other last); the three with a meaningful
  // order — business stage, meeting/notification preference — are left as-is.
  fillSelect("how_did_you_hear", OPT.howDidYouHear, { placeholder: "Please select…", sort: true });
  fillSelect("meeting_preference", OPT.meetingPreference, { placeholder: "Please select…" });
  fillSelect("notification_preference", OPT.notificationPreference, { placeholder: "Please select…" });
  fillSelect("business_stage", OPT.businessStage, { placeholder: "Please select…" });
  fillSelect("industry_sector", OPT.industrySector, { placeholder: "Please select…", sort: true });

  // Multi-select focus areas as checkboxes
  const focusWrap = document.getElementById("mentoring_focus_areas");
  const focusLabels = [];
  sortOptions(OPT.mentoringFocusAreas).forEach((area) => {
    const label = document.createElement("label");
    label.dataset.search = area.toLowerCase();
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.name = "mentoring_focus_areas";
    cb.value = area;
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + area));
    focusWrap.appendChild(label);
    focusLabels.push(label);
  });

  // Type-to-filter the focus-area list. Filtering only hides labels — a checked
  // box that scrolls out of view stays selected, so prior choices are kept.
  const focusFilter = document.getElementById("focus_filter");
  const focusNoMatch = document.getElementById("focus_no_match");
  const focusQuery = document.getElementById("focus_query");
  if (focusFilter) {
    focusFilter.addEventListener("input", () => {
      const q = focusFilter.value.trim().toLowerCase();
      let shown = 0;
      focusLabels.forEach((label) => {
        const match = !q || label.dataset.search.indexOf(q) !== -1;
        label.hidden = !match;
        if (match) shown += 1;
      });
      if (focusNoMatch) focusNoMatch.hidden = shown !== 0;
      if (focusQuery) focusQuery.textContent = focusFilter.value.trim();
    });
  }

  // --- BR-1: Business Stage reveals the business-profile block ---
  const stageSel = document.getElementById("business_stage");
  const businessProfile = document.getElementById("businessProfile");
  stageSel.addEventListener("change", () => {
    const show = stageSel.value && stageSel.value !== "Pre-Startup";
    businessProfile.hidden = !show;
  });

  // --- BR-2: Industry Subsector depends on Industry Sector ---
  const sectorSel = document.getElementById("industry_sector");
  const subsectorSel = document.getElementById("industry_subsector");
  sectorSel.addEventListener("change", () => {
    subsectorSel.innerHTML = "";
    const list = (OPT.industrySubsector && OPT.industrySubsector[sectorSel.value]) || [];
    if (!sectorSel.value) {
      subsectorSel.disabled = true;
      return;
    }
    const opts = list.length ? list : ["Other"];
    fillSelectEl(subsectorSel, sortOptions(opts), "Please select…");
    subsectorSel.disabled = false;
  });

  function fillSelectEl(sel, values, placeholder) {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = placeholder;
    sel.appendChild(o);
    values.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
  }

  // --- Step navigation ---
  function showStep(n) {
    current = n;
    steps.forEach((s) => (s.hidden = Number(s.dataset.step) !== n));
    progressItems.forEach((li) => {
      const step = Number(li.dataset.step);
      li.classList.toggle("is-active", step === n);
      li.classList.toggle("is-done", step < n);
    });
    backBtn.hidden = n === 1;
    nextBtn.hidden = n === TOTAL;
    submitBtn.hidden = n !== TOTAL;
    formError.hidden = true;
    if (n === TOTAL) buildReview();
    window.scrollTo({ top: 0, behavior: "smooth" });
    // Put the cursor in the step's first data-entry field (skipping the hidden
    // honeypot / anything out of the tab order). preventScroll vs the scrollTo.
    const field = steps[n - 1].querySelector(
      'input:not([type=hidden]):not([disabled]):not([tabindex="-1"]),' +
        " select:not([disabled]), textarea:not([disabled])"
    );
    if (field) field.focus({ preventScroll: true });
  }

  function validateStep(n) {
    const step = steps[n - 1];
    const fields = Array.from(step.querySelectorAll("input, select, textarea")).filter(
      (el) => el.offsetParent !== null // visible only
    );
    let ok = true;
    fields.forEach((el) => {
      el.classList.add("touched");
      if (!el.checkValidity()) ok = false;
    });

    if (n === 1) {
      const email = document.getElementById("email").value.trim().toLowerCase();
      const confirm = document.getElementById("confirm_email").value.trim().toLowerCase();
      if (email && confirm && email !== confirm) {
        ok = false;
        return fail("The two email addresses do not match.");
      }
    }
    if (n === 2) {
      const anyArea = form.querySelectorAll('input[name="mentoring_focus_areas"]:checked').length > 0;
      if (!anyArea) {
        ok = false;
        return fail("Please select at least one area of mentoring.");
      }
    }
    if (n === 4) {
      if (!document.getElementById("terms_accepted").checked) {
        ok = false;
        return fail("You must accept the terms to submit.");
      }
    }
    if (!ok) fail("Please complete the highlighted fields before continuing.");
    return ok;

    function fail(msg) {
      showError(msg);
      return false;
    }
  }

  // Surface an error: announce it (role="alert"), move focus to it, scroll it
  // into view. A <p> needs a tabindex before it can take focus.
  function showError(msg) {
    formError.textContent = msg;
    formError.hidden = false;
    formError.tabIndex = -1;
    formError.focus();
    formError.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  nextBtn.addEventListener("click", () => {
    if (validateStep(current)) showStep(current + 1);
  });
  backBtn.addEventListener("click", () => showStep(current - 1));

  // --- Review summary ---
  function val(id) {
    const el = document.getElementById(id);
    return el && el.value ? el.value : "—";
  }
  function buildReview() {
    const areas = Array.from(
      form.querySelectorAll('input[name="mentoring_focus_areas"]:checked')
    ).map((c) => c.value);
    const rows = [
      ["Name", `${val("first_name")} ${val("last_name")}`],
      ["Email", val("email")],
      ["Phone", val("phone")],
      ["Zip", val("zip_code")],
      ["How heard", val("how_did_you_hear")],
      ["Areas of mentoring", areas.length ? areas.join(", ") : "—"],
      ["Needs", val("mentoring_needs_description")],
      ["Meeting preference", val("meeting_preference")],
      ["Notification preference", val("notification_preference")],
      ["Business stage", val("business_stage")],
    ];
    if (stageSel.value && stageSel.value !== "Pre-Startup") {
      rows.push(
        ["Business name", val("business_name")],
        ["Website", val("business_website")],
        ["Industry sector", val("industry_sector")],
        ["Industry subsector", val("industry_subsector")],
        ["Year formed", val("year_formed")],
        ["Employees", val("number_of_employees")]
      );
    }
    const dl = document.createElement("dl");
    rows.forEach(([k, v]) => {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      dl.appendChild(dt);
      dl.appendChild(dd);
    });
    const review = document.getElementById("review");
    review.innerHTML = "";
    review.appendChild(dl);
  }

  // --- Submit ---
  function numOrNull(id) {
    const v = document.getElementById(id).value.trim();
    return v === "" ? null : Number(v);
  }
  function strOrNull(id) {
    const v = document.getElementById(id).value.trim();
    return v === "" ? null : v;
  }

  function buildPayload() {
    const preStartup = stageSel.value === "Pre-Startup";
    return {
      first_name: document.getElementById("first_name").value.trim(),
      last_name: document.getElementById("last_name").value.trim(),
      email: document.getElementById("email").value.trim(),
      confirm_email: document.getElementById("confirm_email").value.trim(),
      phone: document.getElementById("phone").value.trim(),
      zip_code: document.getElementById("zip_code").value.trim(),
      how_did_you_hear: strOrNull("how_did_you_hear"),
      mentoring_focus_areas: Array.from(
        form.querySelectorAll('input[name="mentoring_focus_areas"]:checked')
      ).map((c) => c.value),
      mentoring_needs_description: document
        .getElementById("mentoring_needs_description")
        .value.trim(),
      meeting_preference: strOrNull("meeting_preference"),
      notification_preference: strOrNull("notification_preference"),
      business_stage: stageSel.value,
      business_name: preStartup ? null : strOrNull("business_name"),
      business_website: preStartup ? null : strOrNull("business_website"),
      industry_sector: preStartup ? null : strOrNull("industry_sector"),
      industry_subsector: preStartup ? null : strOrNull("industry_subsector"),
      year_formed: preStartup ? null : numOrNull("year_formed"),
      number_of_employees: preStartup ? null : numOrNull("number_of_employees"),
      marketing_consent: document.getElementById("marketing_consent").checked,
      terms_accepted: document.getElementById("terms_accepted").checked,
      submission_token: submissionToken,
      company_url: honeypot && honeypotKeystrokes > 0 ? honeypot.value : "",
    };
  }

  // Show the submission reference number on the confirmation screen so the user
  // can quote it when following up (and staff can correlate it in the ops
  // console). Only present in async-delivery mode.
  function showReference(reference) {
    const confirmation = document.getElementById("confirmation");
    const existing = confirmation.querySelector(".confirmation__ref");
    if (existing) existing.remove();
    if (!reference) return;
    const p = document.createElement("p");
    p.className = "confirmation__ref";
    p.append("Your reference number is ");
    const code = document.createElement("strong");
    code.textContent = reference;
    p.append(code, ". Please keep it for your records.");
    confirmation.appendChild(p);
  }

  let submitting = false;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (submitting) return; // guard against a double-fire (e.g. Enter + click)
    if (!validateStep(TOTAL)) return;
    submitting = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";
    // Abort a hung request after 30s rather than leave the user stuck on
    // "Submitting…" with no feedback.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const resp = await fetch("/api/client-intake/intake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
        signal: controller.signal,
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        // Surface the exact server-reported reason (string detail, or a
        // structured error list formatted field-by-field) — never a generic
        // "try again" that hides what actually failed.
        let msg = typeof body.detail === "string" && body.detail ? body.detail : "";
        if (!msg) {
          const errs = Array.isArray(body.detail) ? body.detail
            : Array.isArray(body.errors) ? body.errors : null;
          msg = errs && errs.length
            ? errs.map((e) => ((e.loc || []).join(".") || "submission") + ": " + e.msg).join("; ")
            : "The server rejected the submission (HTTP " + resp.status + ") without a reason. Please try again or contact CBM.";
        }
        throw new Error(msg);
      }
      form.hidden = true;
      document.getElementById("progress").hidden = true;
      const confirmation = document.getElementById("confirmation");
      showReference(body.reference);
      confirmation.hidden = false;
      confirmation.tabIndex = -1;
      confirmation.focus();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      showError(
        err.name === "AbortError"
          ? "This is taking longer than expected — your connection may be slow. Please try again."
          : err.message
      );
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit Request";
      submitting = false;
    } finally {
      clearTimeout(timeout);
    }
  });

  showStep(1);
})();
