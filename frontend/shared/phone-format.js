/* Shared phone display formatting for the CBM frontends.

   The CRM stores phone numbers in E.164 (+12165551234); for reading we render
   the standard US format (216)-555-1234 everywhere a phone is DISPLAYED.
   Values that aren't a 10-digit US number (after dropping a leading +1/1) —
   international numbers, extensions, legacy free text — render as-is rather
   than being mangled. Edit inputs and tel: hrefs keep the raw stored value.

   Python twin: core/phone.format_us (keep the two in sync). */
(function () {
  "use strict";
  window.CBM = window.CBM || {};
  window.CBM.formatPhone = function (raw) {
    if (raw == null || raw === "") return "";
    var digits = String(raw).replace(/\D/g, "");
    if (digits.length === 11 && digits.charAt(0) === "1") digits = digits.slice(1);
    if (digits.length !== 10) return String(raw);
    return "(" + digits.slice(0, 3) + ")-" + digits.slice(3, 6) + "-" + digits.slice(6);
  };
})();
