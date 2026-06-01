/* Volunteer / Become-a-Mentor form — field wiring on the shared CBMWizard. */
(function () {
  "use strict";

  const O = window.VOL_OPTIONS;
  const form = document.getElementById("intakeForm");
  const MAX = O.maxChoices;

  // --- populate selects ---
  function fillSelect(id, values, placeholder) {
    const sel = document.getElementById(id);
    if (placeholder !== undefined) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = placeholder;
      sel.appendChild(o);
    }
    values.forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      sel.appendChild(o);
    });
  }
  fillSelect("phone_type", O.phoneType, "Please select…");
  fillSelect("contact_preference", O.contactPreference, "Please select…");
  fillSelect("currently_employed", O.employment, "Please select…");
  fillSelect("how_did_you_hear", O.howDidYouHear, "Please select…");

  // --- checkbox grids, each with a type-to-filter search box ---
  function fillCheckgrid(id, values) {
    const wrap = document.getElementById(id);
    const labels = [];
    values.forEach((v) => {
      const label = document.createElement("label");
      label.dataset.search = v.toLowerCase();
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.name = id;
      cb.value = v;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + v));
      wrap.appendChild(label);
      labels.push(label);
    });
    wireFilter(id, labels);
  }

  // Filtering only hides labels — a checked box scrolled out of view stays
  // checked, so selections (and the up-to-N cap) survive a search.
  function wireFilter(id, labels) {
    const filter = document.getElementById(id + "_filter");
    if (!filter) return;
    const noMatch = document.getElementById(id + "_no_match");
    const queryEl = noMatch && noMatch.querySelector("span");
    filter.addEventListener("input", () => {
      const q = filter.value.trim().toLowerCase();
      let shown = 0;
      labels.forEach((label) => {
        const match = !q || label.dataset.search.indexOf(q) !== -1;
        label.hidden = !match;
        if (match) shown += 1;
      });
      if (noMatch) noMatch.hidden = shown !== 0;
      if (queryEl) queryEl.textContent = filter.value.trim();
    });
  }
  fillCheckgrid("industry_experience", O.industryExperience);
  fillCheckgrid("areas_of_expertise", O.areasOfExpertise);
  fillCheckgrid("fluent_languages", O.fluentLanguages);

  function checked(name) {
    return Array.from(
      form.querySelectorAll('input[name="' + name + '"]:checked')
    ).map((c) => c.value);
  }

  // Enforce "choose up to N" live by disabling unchecked boxes at the cap.
  ["industry_experience", "areas_of_expertise"].forEach((name) => {
    const wrap = document.getElementById(name);
    wrap.addEventListener("change", () => {
      const boxes = Array.from(wrap.querySelectorAll('input[type="checkbox"]'));
      const atCap = boxes.filter((b) => b.checked).length >= MAX;
      boxes.forEach((b) => {
        if (!b.checked) b.disabled = atCap;
      });
    });
  });

  // --- resume file -> base64 (read once on change) ---
  let resume = null;
  const resumeInput = document.getElementById("resume");
  const resumeStatus = document.getElementById("resume_status");
  const MAX_BYTES = 5 * 1024 * 1024;
  resumeInput.addEventListener("change", () => {
    resume = null;
    const file = resumeInput.files && resumeInput.files[0];
    if (!file) {
      resumeStatus.textContent = "";
      return;
    }
    if (file.size > MAX_BYTES) {
      resumeStatus.textContent = "That file is larger than 5 MB. Please choose a smaller file.";
      resumeInput.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result);
      const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
      resume = {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        data_base64: base64,
      };
      resumeStatus.textContent = "Attached: " + file.name;
    };
    reader.readAsDataURL(file);
  });

  // --- helpers ---
  const val = (id) => {
    const el = document.getElementById(id);
    return el && el.value.trim() ? el.value.trim() : "";
  };
  const strOrNull = (id) => val(id) || null;

  // --- validation per step ---
  function validateStep(n) {
    const step = document.querySelector('.step[data-step="' + n + '"]');
    const fields = Array.from(step.querySelectorAll("input, select, textarea")).filter(
      (el) => el.offsetParent !== null && el.type !== "file"
    );
    for (const el of fields) {
      el.classList.add("touched");
      if (!el.checkValidity()) return "Please complete the highlighted fields before continuing.";
    }
    if (n === 1) {
      const a = val("email").toLowerCase();
      const b = val("confirm_email").toLowerCase();
      if (a && b && a !== b) return "The two email addresses do not match.";
    }
    if (n === 3) {
      if (checked("areas_of_expertise").length < 1) return "Please select at least one area of expertise.";
      if (checked("areas_of_expertise").length > MAX) return "Please select no more than " + MAX + " areas of expertise.";
      if (checked("industry_experience").length > MAX) return "Please select no more than " + MAX + " industries.";
    }
    if (n === 4) {
      if (!document.getElementById("terms_accepted").checked) return "You must accept the terms to submit.";
    }
    return true;
  }

  // --- review summary ---
  function onShowStep(n) {
    if (n !== 4) return;
    const rows = [
      ["Name", [val("first_name"), val("middle_initial"), val("last_name")].filter(Boolean).join(" ")],
      ["Email", val("email") || "—"],
      ["Phone", val("phone") || "—"],
      ["Zip", val("zip_code") || "—"],
      ["Why volunteer", val("why_volunteer") || "—"],
      ["Employed", val("currently_employed") || "—"],
      ["Resume", resume ? resume.filename : "—"],
      ["Industries", checked("industry_experience").join(", ") || "—"],
      ["Areas of expertise", checked("areas_of_expertise").join(", ") || "—"],
      ["Languages", checked("fluent_languages").join(", ") || "—"],
      ["How heard", val("how_did_you_hear") || "—"],
    ];
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

  // --- payload (token + honeypot added by the wizard) ---
  function buildPayload() {
    return {
      first_name: val("first_name"),
      middle_initial: strOrNull("middle_initial"),
      last_name: val("last_name"),
      preferred_name: strOrNull("preferred_name"),
      email: val("email"),
      confirm_email: val("confirm_email"),
      street: strOrNull("street"),
      zip_code: val("zip_code"),
      phone: val("phone"),
      phone_type: strOrNull("phone_type"),
      contact_preference: strOrNull("contact_preference"),
      why_volunteer: val("why_volunteer"),
      work_experience: strOrNull("work_experience"),
      resume: resume,
      currently_employed: strOrNull("currently_employed"),
      linkedin_profile: strOrNull("linkedin_profile"),
      industry_experience: checked("industry_experience"),
      areas_of_expertise: checked("areas_of_expertise"),
      fluent_languages: checked("fluent_languages"),
      how_did_you_hear: strOrNull("how_did_you_hear"),
      felony_conviction: val("felony_conviction") === "Yes",
      terms_accepted: document.getElementById("terms_accepted").checked,
    };
  }

  window.CBMWizard.mount({
    slug: "volunteer",
    validateStep: validateStep,
    buildPayload: buildPayload,
    onShowStep: onShowStep,
  });
})();
