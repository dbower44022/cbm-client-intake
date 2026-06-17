/* Become-a-Partner form — field wiring on the shared CBMWizard. */
(function () {
  "use strict";

  const O = window.PARTNER_OPTIONS;
  const form = document.getElementById("intakeForm");

  // --- populate the selects ---
  function fillSelect(id, values, placeholder) {
    const sel = document.getElementById(id);
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = placeholder;
    sel.appendChild(ph);
    values.forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      sel.appendChild(o);
    });
  }
  fillSelect("partnership_type", O.partnershipType, "Please select…");
  fillSelect("how_did_you_hear", O.howDidYouHear, "Please select…");

  // --- "what could you offer" checkbox grid ---
  function fillCheckgrid(id, values) {
    const wrap = document.getElementById(id);
    values.forEach((v) => {
      const label = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.name = id;
      cb.value = v;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + v));
      wrap.appendChild(label);
    });
  }
  fillCheckgrid("partnership_value", O.partnershipValue);

  function checked(name) {
    return Array.from(
      form.querySelectorAll('input[name="' + name + '"]:checked')
    ).map((c) => c.value);
  }

  const val = (id) => {
    const el = document.getElementById(id);
    return el && el.value.trim() ? el.value.trim() : "";
  };
  const strOrNull = (id) => val(id) || null;

  function validateStep(n) {
    const step = document.querySelector('.step[data-step="' + n + '"]');
    const fields = Array.from(step.querySelectorAll("input, select, textarea")).filter(
      (el) => el.offsetParent !== null
    );
    for (const el of fields) {
      el.classList.add("touched");
      if (!el.checkValidity()) return "Please complete the highlighted fields before continuing.";
    }
    return true;
  }

  function buildPayload() {
    return {
      company: val("company"),
      business_website: strOrNull("business_website"),
      first_name: val("first_name"),
      last_name: val("last_name"),
      email: val("email"),
      phone: strOrNull("phone"),
      partnership_type: strOrNull("partnership_type"),
      partnership_value: checked("partnership_value"),
      how_did_you_hear: strOrNull("how_did_you_hear"),
    };
  }

  window.CBMWizard.mount({
    slug: "partner",
    validateStep: validateStep,
    buildPayload: buildPayload,
  });
})();
