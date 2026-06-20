/* Turns the policy phrases inside the consent checkbox into links.
 *
 * SINGLE SOURCE OF TRUTH for the policy document URLs — update them here and
 * every form's consent checkbox picks up the change. Only forms that have the
 * `#terms_accepted` checkbox (client-intake, volunteer) are affected.
 */
(function () {
  "use strict";

  var URLS = {
    conduct: "https://cbmentostagdev.wpenginepowered.com/client-code-of-conduct/",
    terms: "https://cbmentostagdev.wpenginepowered.com/legal-notices/",
    privacy: "https://cbmentostagdev.wpenginepowered.com/privacy-policy/",
  };

  // Phrases to linkify. "Client Code of Conduct" is listed before "Code of
  // Conduct" but matching is by earliest position, so the longer variant wins
  // wherever it appears.
  var PHRASES = [
    { text: "Client Code of Conduct", url: URLS.conduct },
    { text: "Code of Conduct", url: URLS.conduct },
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
