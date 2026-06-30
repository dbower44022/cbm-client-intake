/* Become-a-Sponsor form — field wiring on the shared CBMWizard. */
(function () {
  "use strict";

  const O = window.SPONSOR_OPTIONS;

  const sel = document.getElementById("how_did_you_hear");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Please select…";
  sel.appendChild(placeholder);
  O.howDidYouHear.forEach((v) => {
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
      message: val("message"),
      how_did_you_hear: strOrNull("how_did_you_hear"),
      terms_accepted: document.getElementById("terms_accepted").checked,
    };
  }

  window.CBMWizard.mount({
    slug: "sponsor",
    validateStep: validateStep,
    buildPayload: buildPayload,
  });
})();
