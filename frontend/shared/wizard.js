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
      // role="alert" announces the text to screen readers; move keyboard/visual
      // focus to it too so the error isn't missed (a <p> needs a tabindex first).
      formError.tabIndex = -1;
      formError.focus();
      formError.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function validate(n) {
      const r = opts.validateStep ? opts.validateStep(n) : true;
      if (r === true || r === undefined) return true;
      fail(typeof r === "string" ? r : "Please complete the highlighted fields.");
      return false;
    }

    // The first data-entry control of a step (text/select/textarea/checkbox),
    // skipping the hidden honeypot and anything pulled out of the tab order.
    function firstField(step) {
      return step.querySelector(
        'input:not([type=hidden]):not([disabled]):not([tabindex="-1"]),' +
          " select:not([disabled]), textarea:not([disabled])"
      );
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
      // Put the cursor in the step's first data-entry field (on initial load and
      // when moving between steps). preventScroll so it doesn't fight scrollTo.
      const active = steps.find((s) => Number(s.dataset.step) === n);
      const field = active && firstField(active);
      if (field) field.focus({ preventScroll: true });
    }

    nextBtn.addEventListener("click", () => {
      if (validate(current)) showStep(current + 1);
    });
    backBtn.addEventListener("click", () => showStep(current - 1));

    let submitting = false;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (submitting) return; // guard against a double-fire (e.g. Enter + click)
      if (!validate(TOTAL)) return;
      submitting = true;
      submitBtn.disabled = true;
      const originalLabel = submitBtn.textContent;
      submitBtn.textContent = "Submitting…";
      // Don't leave the user staring at "Submitting…" forever if the network
      // (or server) hangs — abort after 30s with a clear, retryable message.
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30000);
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
          signal: controller.signal,
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(errorMessage(body, resp.status));
        }
        form.hidden = true;
        const progress = document.getElementById("progress");
        if (progress) progress.hidden = true;
        const confirmation = document.getElementById("confirmation");
        if (confirmation) {
          showReference(confirmation, body.reference);
          confirmation.hidden = false;
          confirmation.tabIndex = -1;
          confirmation.focus();
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (err) {
        const msg =
          err.name === "AbortError"
            ? "This is taking longer than expected — your connection may be slow. Please try again."
            : err.message;
        fail(msg);
        submitBtn.disabled = false;
        submitBtn.textContent = originalLabel;
        submitting = false;
      } finally {
        clearTimeout(timeout);
      }
    });

    // Always surface the exact server-reported reason. The server sends
    // ``detail`` as a readable string; a structured error list (older deploys,
    // FastAPI-default 422s) is formatted field-by-field; only a completely
    // bodyless failure falls back to naming the HTTP status.
    function errorMessage(body, status) {
      if (typeof body.detail === "string" && body.detail) return body.detail;
      const errs = Array.isArray(body.detail)
        ? body.detail
        : Array.isArray(body.errors)
          ? body.errors
          : null;
      if (errs && errs.length) {
        return errs
          .map((e) => ((e.loc || []).join(".") || "submission") + ": " + e.msg)
          .join("; ");
      }
      return "The server rejected the submission (HTTP " + status + ") without a reason. Please try again or contact CBM.";
    }

    // Show the submission reference number on the confirmation screen so the
    // user has something to quote when following up (and staff can correlate it
    // in the operations console). Only present in async-delivery mode.
    function showReference(confirmation, reference) {
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

    showStep(1);
  }

  return { mount };
})();
