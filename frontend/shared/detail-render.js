/* Shared type-aware value/panel renderers for CRM-layout-driven detail panels.
   Served at /shared/detail-render.js; used by the Workspace Directory grid SPA
   (preview pane + detail pop-up), the View Contact page (Overview tab), and
   Client Administration's mentor detail popup. Load before the page's own JS. */
(function () {
  "use strict";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function fmtDate(v) { if (!v) return ""; return String(v).slice(0, 10); }

  function fmtDateTime(v) {
    if (!v) return "";
    var d = new Date(String(v).replace(" ", "T") + (/[Zz]|[+\-]\d\d:?\d\d$/.test(String(v)) ? "" : "Z"));
    if (isNaN(d)) return String(v);
    return d.toLocaleString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function fmtPhone(v) {
    try { return (window.CBM && window.CBM.formatPhone) ? window.CBM.formatPhone(v) : v; }
    catch (e) { return v; }
  }

  function emailLink(addr) {
    try {
      if (window.CBMQuickMail && window.CBMQuickMail.emailLink) return window.CBMQuickMail.emailLink(addr);
    } catch (e) {}
    var a = el("a", null, addr); a.href = "mailto:" + addr; return a;
  }

  // Render a value into a container node (preview + view modal + Overview).
  function renderValue(node, type, value) {
    if (value == null || value === "" || (Array.isArray(value) && !value.length)) { node.textContent = "—"; return; }
    if (type === "email") { node.appendChild(emailLink(String(value))); return; }
    if (type === "phone") { var a = el("a", null, fmtPhone(String(value))); a.href = "tel:" + String(value).replace(/[^0-9+]/g, ""); node.appendChild(a); return; }
    if (type === "url") { var u = String(value); var href = /^https?:\/\//i.test(u) ? u : "https://" + u; var l = el("a", null, u); l.href = href; l.target = "_blank"; l.rel = "noopener"; node.appendChild(l); return; }
    if (type === "array") { var wrap = el("div", "dir__cell-chips"); (Array.isArray(value) ? value : [value]).forEach(function (v) { wrap.appendChild(el("span", "dir__pill", String(v))); }); node.appendChild(wrap); return; }
    if (type === "bool") { node.textContent = value ? "Yes" : "No"; return; }
    if (type === "date") { node.textContent = fmtDate(value); return; }
    if (type === "datetime") { node.textContent = fmtDateTime(value); return; }
    if (type === "html") { var d = el("div", "dir__val-html"); d.innerHTML = (window.CBMRichText && window.CBMRichText.sanitizeHtml) ? window.CBMRichText.sanitizeHtml(String(value)) : ""; node.appendChild(d); return; }
    if (type === "address") { node.style.whiteSpace = "pre-line"; node.textContent = String(value); return; }
    node.textContent = String(value);   // text / longtext / int / currency
  }

  // The CRM-arranged detail panels. View mode hides empty values by default;
  // pass {showEmpty:true} to render them as "\u2014" instead (the mentor detail
  // popup promises every field a visible slot — an absent row reads as a bug).
  function panelsInto(container, panels, opts) {
    var showEmpty = !!(opts && opts.showEmpty);
    (panels || []).forEach(function (p) {
      var block = el("div", "dir__panel");
      if (p.title) block.appendChild(el("h3", null, p.title));
      var dl = el("dl", "dir__kv");
      p.fields.forEach(function (f) {
        var empty = f.value == null || f.value === "" || (Array.isArray(f.value) && !f.value.length);
        if (empty && !showEmpty) return;
        dl.appendChild(el("dt", null, f.label));
        var dd = el("dd"); renderValue(dd, f.type, f.value); dl.appendChild(dd);
      });
      if (dl.children.length) { block.appendChild(dl); container.appendChild(block); }
    });
  }

  window.CBMDirRender = {
    el: el,
    fmtDate: fmtDate,
    fmtDateTime: fmtDateTime,
    fmtPhone: fmtPhone,
    emailLink: emailLink,
    renderValue: renderValue,
    panelsInto: panelsInto,
  };
})();
