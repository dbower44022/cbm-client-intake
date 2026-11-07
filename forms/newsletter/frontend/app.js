/* Newsletter signup — single-step field wiring on the shared CBMWizard. */
(function () {
  "use strict";

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
      if (!el.checkValidity()) {
        return el.id === "marketing_consent"
          ? "Tick the box to say yes to the newsletter."
          : "Please complete the highlighted fields.";
      }
    }
    return true;
  }

  function buildPayload() {
    return {
      first_name: val("first_name"),
      last_name: val("last_name"),
      email: val("email"),
      marketing_consent: !!document.getElementById("marketing_consent").checked,
      campaign_id: strOrNull("campaign_id"),
      campaign_link: strOrNull("campaign_link"),
      button_placement: strOrNull("button_placement"),
      prospect_id: strOrNull("prospect_id"),
      lead_code: strOrNull("lead_code"),
    };
  }

  window.CBMWizard.mount({
    slug: "newsletter",
    validateStep: validateStep,
    buildPayload: buildPayload,
  });
})();
