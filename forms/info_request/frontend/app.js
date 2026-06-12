/* Request Information form — single-step field wiring on the shared CBMWizard. */
(function () {
  "use strict";

  // Maps to a free-text CRM field, so this list is presentational only
  // (kept in step with the volunteer form's wording).
  const HOW_DID_YOU_HEAR = [
    "Friend or relative", "Newspaper", "Online search", "Radio", "SBA",
    "CBM client or volunteer", "Social media", "TV", "Workshop/Event", "Other",
  ];

  const sel = document.getElementById("how_did_you_hear");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Please select…";
  sel.appendChild(placeholder);
  HOW_DID_YOU_HEAR.forEach((v) => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    sel.appendChild(o);
  });

  const val = (id) => {
    const el = document.getElementById(id);
    return el && el.value.trim() ? el.value.trim() : "";
  };
  const strOrNull = (id) => val(id) || null;

  function validateStep() {
    const step = document.querySelector(".step");
    const fields = Array.from(step.querySelectorAll("input, select, textarea"));
    for (const el of fields) {
      el.classList.add("touched");
      if (!el.checkValidity()) return "Please complete the highlighted fields.";
    }
    return true;
  }

  function buildPayload() {
    return {
      first_name: val("first_name"),
      last_name: val("last_name"),
      email: val("email"),
      phone: strOrNull("phone"),
      company: strOrNull("company"),
      message: val("message"),
      how_did_you_hear: strOrNull("how_did_you_hear"),
    };
  }

  window.CBMWizard.mount({
    slug: "info-request",
    validateStep: validateStep,
    buildPayload: buildPayload,
  });
})();
