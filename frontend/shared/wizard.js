/*
 * Shared multi-step wizard controller.
 *
 * Handles the step/nav/progress plumbing and the submit envelope (idempotency
 * token + honeypot) common to every CBM intake form, so a form's own script
 * only wires its fields and supplies two callbacks.
 *
 * Expected DOM: form#intakeForm, .step[data-step], #progress li[data-step],
 *   #backBtn, #nextBtn, #submitBtn, #formError, #confirmation, and a hidden
 *   honeypot input#xtra_note (posted under the `company_url` payload key).
 *
 * Usage:
 *   CBMWizard.mount({
 *     slug: "volunteer",                 // POST /api/{slug}/intake
 *     validateStep: (n) => true | "error message",
 *     buildPayload: () => ({ ...formFields }),  // token + honeypot added here
 *     onShowStep: (n) => {},             // optional
 *   });
 */
window.CBMWizard = (function () {
  function mount(opts) {
    const slug = opts.slug;
    const form = document.getElementById("intakeForm");
    const steps = Array.from(document.querySelectorAll(".step"));
    const progressItems = Array.from(document.querySelectorAll("#progress li"));
    const backBtn = document.getElementById("backBtn");
    const nextBtn = document.getElementById("nextBtn");
    const submitBtn = document.getElementById("submitBtn");
    const formError = document.getElementById("formError");
    const TOTAL = steps.length;
    let current = 1;

    const token =
      (window.crypto && crypto.randomUUID && crypto.randomUUID()) ||
      "tok-" + Date.now() + "-" + Math.random().toString(36).slice(2);

    // Honeypot. Only count it as filled when actual keystrokes landed in it:
    // browser autofill / password managers set values on hidden fields without
    // typing, and flagging those lost two real submissions on 2026-06-12.
    const honeypot = document.getElementById("xtra_note");
    let honeypotKeystrokes = 0;
    if (honeypot) {
      honeypot.addEventListener("keydown", () => {
        honeypotKeystrokes += 1;
      });
    }

    function fail(msg) {
      formError.textContent = msg;
      formError.hidden = false;
    }

    function validate(n) {
      const r = opts.validateStep ? opts.validateStep(n) : true;
      if (r === true || r === undefined) return true;
      fail(typeof r === "string" ? r : "Please complete the highlighted fields.");
      return false;
    }

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
      if (opts.onShowStep) opts.onShowStep(n);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    nextBtn.addEventListener("click", () => {
      if (validate(current)) showStep(current + 1);
    });
    backBtn.addEventListener("click", () => showStep(current - 1));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!validate(TOTAL)) return;
      submitBtn.disabled = true;
      const originalLabel = submitBtn.textContent;
      submitBtn.textContent = "Submitting…";
      try {
        const payload = Object.assign({}, opts.buildPayload(), {
          submission_token: token,
          company_url:
            honeypot && honeypotKeystrokes > 0 ? honeypot.value : "",
        });
        const resp = await fetch(`/api/${slug}/intake`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          const msg =
            typeof body.detail === "string"
              ? body.detail
              : "Please check your entries and try again.";
          throw new Error(msg);
        }
        form.hidden = true;
        const progress = document.getElementById("progress");
        if (progress) progress.hidden = true;
        const confirmation = document.getElementById("confirmation");
        if (confirmation) confirmation.hidden = false;
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (err) {
        fail(err.message);
        submitBtn.disabled = false;
        submitBtn.textContent = originalLabel;
      }
    });

    showStep(1);
  }

  return { mount };
})();
