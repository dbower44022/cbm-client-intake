/* Turns the policy phrases inside the consent checkbox into links.
 *
 * The URLs are SETTINGS, substituted server-side as this file is served
 * (core/branding.py; policy_* in core/config.py) — so a deployment points at
 * its own policy documents without a code change. Only forms carrying the
 * `#terms_accepted` checkbox are affected.
 *
 * These are the documents a member of the public is told they are agreeing to.
 * Three of the four used to be hardcoded to the WPEngine STAGING host; see
 * CHANGELOG v0.206.0.
 */
(function () {
  "use strict";

  var URLS = {
    conduct: "{{policyClientConduct}}",
    mentorConduct: "{{policyMentorEthics}}",
    terms: "{{policyTerms}}",
    privacy: "{{policyPrivacy}}",
  };

  // The volunteer (mentor intake) form's "Code of Conduct" is the *mentor* code
  // of ethics — a different document from the client code the other forms cite.
  var conductUrl = location.pathname.indexOf("/volunteer/") === 0
    ? URLS.mentorConduct : URLS.conduct;

  // Phrases to linkify. "Client Code of Conduct" is listed before "Code of
  // Conduct" but matching is by earliest position, so the longer variant wins
  // wherever it appears.
  var PHRASES = [
    { text: "Client Code of Conduct", url: URLS.conduct },
    { text: "Code of Conduct", url: conductUrl },
    { text: "Terms of Use", url: URLS.terms },
    { text: "Privacy Policy", url: URLS.privacy },
  ];

  var input = document.getElementById("terms_accepted");
  if (!input) return;
  var label = input.closest("label");
  if (!label) return;

  function linkify(textNode) {
    var text = textNode.nodeValue;
    var frag = document.createDocumentFragment();
    var idx = 0;
    while (idx < text.length) {
      var best = null;
      PHRASES.forEach(function (p) {
        var pos = text.indexOf(p.text, idx);
        if (pos >= 0 && (best === null || pos < best.pos)) best = { pos: pos, p: p };
      });
      if (!best) { frag.appendChild(document.createTextNode(text.slice(idx))); break; }
      if (best.pos > idx) frag.appendChild(document.createTextNode(text.slice(idx, best.pos)));
      var a = document.createElement("a");
      a.href = best.p.url;
      a.textContent = best.p.text;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "cbm-policy-link";
      // Keep Tab moving field-to-field: the policy links are reference material,
      // not data entry, so they stay clickable but out of the tab order.
      a.tabIndex = -1;
      frag.appendChild(a);
      idx = best.pos + best.p.text.length;
    }
    textNode.parentNode.replaceChild(frag, textNode);
  }

  // Only the label's direct text nodes carry the phrases (alongside the checkbox
  // input and the required-asterisk span).
  Array.prototype.slice.call(label.childNodes).forEach(function (n) {
    if (n.nodeType === 3 && n.nodeValue && n.nodeValue.trim()) linkify(n);
  });
})();
