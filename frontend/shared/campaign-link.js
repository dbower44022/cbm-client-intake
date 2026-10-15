/* Campaign attribution on a public door (prds/prospect-marketing/build-plan.md
 * § 3.7, § 4, § 5). Loaded by every public intake form after its own inputs
 * exist and before its app.js builds a payload.
 *
 * Reads ?campaign=, ?link= and ?prospect= from the address, fills the hidden
 * inputs #campaign_id, #campaign_link and #prospect_id, shows the banner
 * "You arrived through <campaign>" from the public NAME-ONLY lookup (a 404 or
 * an outage leaves the ids riding silently — the submission still counts), and
 * prefills what a postcard printed: the business name and its mailing address,
 * from the prospect lookup (nothing about a person is ever served). The person's
 * own typed name, email and phone arrive from the landing page in the browser
 * only (sessionStorage, read once here and cleared).
 */
(function () {
  "use strict";
  var ID = /^[A-Za-z0-9]{1,32}$/;
  var TOKEN = /^[a-z0-9]{6,16}$/i;
  var params = new URLSearchParams(window.location.search);
  var campaign = (params.get("campaign") || "").trim();
  var link = (params.get("link") || "").trim().toLowerCase();
  var prospect = (params.get("prospect") || "").trim();

  function set(id, value) { var el = document.getElementById(id); if (el) el.value = value; return el; }
  function fill(id, value) {
    var el = document.getElementById(id);
    if (el && value && !el.value) { el.value = value; el.dispatchEvent(new Event("input", { bubbles: true })); }
  }

  if (ID.test(campaign)) set("campaign_id", campaign); else campaign = "";
  if (TOKEN.test(link)) set("campaign_link", link); else link = "";
  if (ID.test(prospect)) set("prospect_id", prospect); else prospect = "";

  if (campaign) {
    fetch("/api/campaigns/public/" + encodeURIComponent(campaign), { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (body) {
        var name = body && body.campaign && body.campaign.name;
        var banner = document.getElementById("campaign_banner");
        var slot = document.getElementById("campaign_banner_name");
        if (!name || !banner || !slot) return;
        slot.textContent = name;
        banner.hidden = false;
      })
      .catch(function () { /* the id still rides with the submission */ });
  }

  if (prospect) {
    fetch("/api/campaigns/prospect/" + encodeURIComponent(prospect), { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (body) {
        var p = body && body.prospect;
        if (!p) return;
        // Each form names its own inputs; fill whichever of the usual ids exist.
        fill("business_name", p.businessName); fill("company_name", p.businessName); fill("organization", p.businessName);
        fill("business_website", p.website); fill("website", p.website);
        fill("business_street", p.street); fill("street", p.street); fill("address_street", p.street);
        fill("business_city", p.city); fill("city", p.city); fill("address_city", p.city);
        fill("business_state", p.state); fill("state", p.state); fill("address_state", p.state);
        fill("business_zip", p.zip); fill("zip_code", p.zip); fill("zip", p.zip); fill("address_zip", p.zip);
      })
      .catch(function () {});
  }

  // The landing page's handoff: the person's details, in the browser only.
  try {
    var raw = sessionStorage.getItem("cbm-prospect-handoff");
    if (raw && (prospect || campaign)) {
      sessionStorage.removeItem("cbm-prospect-handoff");
      var h = JSON.parse(raw);
      if (h && Date.now() - (h.at || 0) < 15 * 60 * 1000) {
        fill("first_name", h.firstName); fill("last_name", h.lastName);
        fill("email", h.email); fill("confirm_email", h.email); fill("phone", h.phone);
        var mk = document.getElementById("marketing_consent");
        if (mk && h.marketing) mk.checked = true;
        var sms = document.getElementById("sms_consent");
        if (sms && h.sms) sms.checked = true;
      }
    }
  } catch (_) { /* a browser without storage still gets the form */ }
})();
