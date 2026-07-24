/* CBMRichText — the standard rich-text editor for every wysiwyg field
 * product-wide (see CLAUDE.md Conventions). Wraps the vendored Jodit build;
 * a page using it must load, in order:
 *   <link rel="stylesheet" href="/shared/vendor/jodit/jodit.min.css" />
 *   <script src="/shared/vendor/jodit/jodit.min.js"></script>
 *   <script src="/shared/richtext.js"></script>
 *
 * Contract:
 *   var el = CBMRichText.create(initialHtml, { onInput: fn });
 *   el is a plain container the caller can insert/style; read/write via
 *   el._cbmRichText.getValue() / .setValue(html). create() returns null when
 *   Jodit isn't loaded, so callers keep their legacy editor as a fallback.
 *
 * CRM-sourced HTML stays untrusted: it is stripped on the way in AND the
 * editor's output is stripped again on getValue() — Jodit's own filtering is
 * not a substitute for the apps' sanitize pass.
 */
(function () {
  "use strict";

  function sanitizeHtml(html) {
    var tmp = document.createElement("div"); tmp.innerHTML = html || "";
    Array.prototype.forEach.call(tmp.querySelectorAll("script,style,iframe,object,embed,link,meta"), function (n) { n.remove(); });
    Array.prototype.forEach.call(tmp.querySelectorAll("*"), function (n) {
      Array.prototype.slice.call(n.attributes).forEach(function (a) {
        var name = a.name.toLowerCase(), val = (a.value || "").replace(/\s/g, "").toLowerCase();
        if (name.indexOf("on") === 0) n.removeAttribute(a.name);
        else if ((name === "href" || name === "src") && val.indexOf("javascript:") === 0) n.removeAttribute(a.name);
      });
    });
    return tmp.innerHTML;
  }

  // Empty-content test: Jodit's blank document is "<p><br></p>", which must
  // read back as "" so the save-diff doesn't see a phantom change.
  function isEmptyHtml(html) {
    var tmp = document.createElement("div"); tmp.innerHTML = html || "";
    return tmp.textContent.trim() === "" && !tmp.querySelector("img,table,hr");
  }

  var BUTTONS = [
    "bold", "italic", "underline", "strikethrough", "|",
    "brush", "paragraph", "|",
    "ul", "ol", "|",
    "link", "table", "hr", "|",
    "eraser", "|",
    "undo", "redo",
  ];

  function create(value, opts) {
    if (typeof window.Jodit === "undefined" || !window.Jodit.make) return null;
    opts = opts || {};
    var host = document.createElement("div");
    host.className = "cbm-richtext";
    var area = document.createElement("textarea");
    host.appendChild(area);
    var editor = window.Jodit.make(area, {
      buttons: BUTTONS,
      toolbarAdaptive: false,     // same toolbar at every width
      statusbar: false,
      spellcheck: true,
      minHeight: opts.minHeight || 160,
      // Paste keeps formatting without the confirm dialog; the sanitize pass
      // on getValue() is the safety net.
      askBeforePasteHTML: false,
      askBeforePasteFromWord: false,
      defaultActionOnPaste: "insert_as_html",
      disablePlugins: ["add-new-line"],
    });
    var initial = sanitizeHtml(value == null ? "" : String(value));
    if (isEmptyHtml(initial)) initial = "";
    editor.value = initial;
    // Jodit normalizes loaded HTML asynchronously after init (<b> -> <strong>,
    // paragraph wrapping, …), which would make an untouched editor read back a
    // different string than the caller's render-time snapshot — a phantom
    // "unsaved change". So getValue() returns the caller's own initial value
    // until the user has actually edited: a change event that follows a real
    // gesture (pointer/key) inside the editor. Init normalization fires change
    // with no gesture; clicking without editing is a gesture with no change —
    // neither flips it.
    var gestured = false, touched = false;
    host.addEventListener("pointerdown", function () { gestured = true; }, true);
    host.addEventListener("keydown", function () { gestured = true; }, true);
    // A pasted/dropped image lands as a base64 data: URI — megabytes of text
    // that the CRM's text columns cannot store (a session-notes save 500'd on
    // exactly this, 2026-07-24). Remove it the moment it appears and tell the
    // user, instead of letting the save fail later with a server error.
    var imgNote = null;
    function blockedImageNotice() {
      if (!imgNote) {
        imgNote = document.createElement("div");
        imgNote.className = "cbm-richtext-note";
        imgNote.style.cssText = "background:#fdf3dc;border:1px solid #b58113;" +
          "color:#5b4708;padding:6px 10px;font-size:13px;border-radius:4px;margin:0 0 4px;";
        host.insertBefore(imgNote, host.firstChild);
      }
      imgNote.textContent = opts.imageBlockedMessage ||
        "Pasted images can't be stored in this text and were removed — " +
        "attach the image as a file instead (e.g. on the Documents tab).";
      imgNote.hidden = false;
      clearTimeout(imgNote._t);
      imgNote._t = setTimeout(function () { imgNote.hidden = true; }, 10000);
    }
    function stripEmbeddedImages() {
      var html = editor.value;
      if (!/src\s*=\s*["']data:/i.test(html)) return false;
      var tmp = document.createElement("div");
      tmp.innerHTML = html;
      var imgs = tmp.querySelectorAll('img[src^="data:"]');
      if (!imgs.length) return false;
      Array.prototype.forEach.call(imgs, function (n) { n.remove(); });
      editor.value = tmp.innerHTML;  // re-fires change; next pass finds nothing
      blockedImageNotice();
      return true;
    }
    editor.events.on("change", function () {
      if (gestured && stripEmbeddedImages()) return;
      if (gestured) touched = true;
      if (touched && typeof opts.onInput === "function") opts.onInput();
    });
    host._cbmRichText = {
      getValue: function () {
        if (!touched) return initial;
        var html = editor.value;
        return isEmptyHtml(html) ? "" : sanitizeHtml(html);
      },
      setValue: function (html) {
        initial = sanitizeHtml(html == null ? "" : String(html));
        if (isEmptyHtml(initial)) initial = "";
        editor.value = initial;
        touched = false;  // programmatic reload = a fresh baseline
      },
      focus: function () { editor.s.focus(); },
      editor: editor,
    };
    return host;
  }

  window.CBMRichText = { create: create, sanitizeHtml: sanitizeHtml };
})();
