/* The postcard landing page (build plan § 4).
 *
 * Three actions, all always clickable, validated on click. Every action saves
 * the response first; a mentor or information request then opens the standard
 * form with the campaign, the link and the prospect id in the address and the
 * typed name, email and phone handed over IN THE BROWSER ONLY (sessionStorage,
 * read once by the form and cleared) — the server never serves a person's
 * details back to a public page (ruling 16).
 */
(function () {
  "use strict";
  var body = document.body;
  var scanToken = body.getAttribute("data-scan-token") || "";
  var campaignId = body.getAttribute("data-campaign-id") || "";
  var linkToken = body.getAttribute("data-link-token") || "";
  var prospectId = body.getAttribute("data-prospect-id") || "";
  // The person's lead code (build plan § 7d.3): the forms after this page
  // carry it instead of the CRM id. Empty on a CRM without the code fields.
  var leadCode = body.getAttribute("data-lead-code") || "";
  var preview = body.getAttribute("data-preview") === "1";
  var HANDOFF_KEY = "cbm-prospect-handoff";

  function $(id) { return document.getElementById(id); }
  function val(id) { var el = $(id); return el ? el.value.trim() : ""; }
  function checked(id) { var el = $(id); return !!(el && el.checked); }

  if (preview) { var note = $("previewNote"); if (note) note.hidden = false; }

  var hpKeystrokes = 0;
  var hp = $("company_url");
  if (hp) hp.addEventListener("input", function () { hpKeystrokes++; });

  if (window.CBMAddress && window.CBMAddress.attach) {
    window.CBMAddress.attach({
      line1: $("mailing_street"), city: $("mailing_city"),
      state: $("mailing_state"), postalCode: $("mailing_zip")
    });
  }

  function token() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "t-" + Date.now() + "-" + Math.random().toString(36).slice(2, 12);
  }
  var submissionToken = token();

  function message(text, kind) {
    var el = $("formMsg");
    if (!el) return;
    el.textContent = text;
    el.className = "lp__msg" + (kind ? " lp__msg--" + kind : "");
    el.hidden = !text;
  }

  function validate(action) {
    var email = val("email");
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return "That email address does not look complete.";
    if (checked("sms_consent") && !val("phone")) return "To allow texts, enter the phone number we may text.";
    if (action !== "update" && !email) return "Please enter an email address so we can follow up on your request.";
    return "";
  }

  function payload(action) {
    return {
      submission_token: submissionToken,
      company_url: hp && hpKeystrokes > 0 ? hp.value : "",
      action: action,
      business_name: val("business_name"),
      mailing_street: val("mailing_street"), mailing_city: val("mailing_city"),
      mailing_state: val("mailing_state").toUpperCase(), mailing_zip: val("mailing_zip"),
      website: val("website"),
      first_name: val("first_name"), last_name: val("last_name"),
      email: val("email"), phone: val("phone"),
      marketing_consent: checked("marketing_consent"),
      sms_consent: checked("sms_consent"),
      campaign_id: campaignId || null, campaign_link: linkToken || null, prospect_id: prospectId || null
    };
  }

  function nextUrl(action) {
    var slug = action === "mentor" ? "client-intake" : "info-request";
    var q = [];
    if (leadCode) q.push("lead=" + encodeURIComponent(leadCode));
    else if (prospectId) q.push("prospect=" + encodeURIComponent(prospectId));
    if (campaignId) q.push("campaign=" + encodeURIComponent(campaignId));
    if (linkToken) q.push("link=" + encodeURIComponent(linkToken));
    return "/" + slug + "/" + (q.length ? "?" + q.join("&") : "");
  }

  function handoff() {
    try {
      sessionStorage.setItem(HANDOFF_KEY, JSON.stringify({
        firstName: val("first_name"), lastName: val("last_name"),
        email: val("email"), phone: val("phone"),
        marketing: checked("marketing_consent"), sms: checked("sms_consent"),
        at: Date.now()
      }));
    } catch (_) { /* a browser without storage still gets the form */ }
  }

  var busy = false;
  async function act(action) {
    if (busy) return;
    var problem = validate(action);
    if (problem) { message(problem, "error"); return; }
    message("", "");
    if (preview) {
      message("This is a preview card; nothing is saved. The real card's page saves and continues.", "ok");
      return;
    }
    busy = true;
    try {
      var res = await fetch("/api/campaigns/landing/" + encodeURIComponent(scanToken), {
        method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload(action))
      });
      var data = null;
      try { data = await res.json(); } catch (_) { data = null; }
      if (!res.ok) {
        message((data && data.detail) || "We could not save that just now. Please try again.", "error");
        return;
      }
      if (action === "update") {
        $("landingForm").hidden = true;
        $("thanks").hidden = false;
        return;
      }
      handoff();
      window.location.assign(nextUrl(action));
    } catch (e) {
      message("We could not reach the server. Please check your connection and try again.", "error");
    } finally {
      busy = false;
    }
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-action]"), function (btn) {
    btn.addEventListener("click", function () { act(btn.getAttribute("data-action")); });
  });
  var form = $("landingForm");
  if (form) form.addEventListener("submit", function (e) { e.preventDefault(); act("update"); });
})();
