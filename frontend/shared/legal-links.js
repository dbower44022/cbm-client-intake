/* Legal/policy document links shown in each form's footer — the documents
 * referenced by the consent checkbox. SINGLE SOURCE OF TRUTH: update the URLs
 * (or labels) here and every form picks up the change.
 */
(function () {
  "use strict";

  var LINKS = [
    { label: "Client Code of Conduct", href: "https://cbmentostagdev.wpenginepowered.com/client-code-of-conduct/" },
    { label: "Privacy Policy", href: "https://cbmentostagdev.wpenginepowered.com/privacy-policy/" },
    { label: "Terms and Conditions", href: "https://cbmentostagdev.wpenginepowered.com/legal-notices/" },
  ];

  var footer = document.querySelector(".cbm-footer");
  if (!footer) return;

  var nav = document.createElement("nav");
  nav.className = "cbm-legal";
  nav.setAttribute("aria-label", "Policies");
  LINKS.forEach(function (l) {
    var a = document.createElement("a");
    a.href = l.href;
    a.textContent = l.label;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    nav.appendChild(a);
  });

  // Place the policy links above the copyright line at the bottom of the form.
  footer.insertBefore(nav, footer.firstChild);
})();
