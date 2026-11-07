// Runs inside every public form (prds/chapter-website-plan.md, piece C;
// Association ruling 42). Served by /assets/frame.js, which fills in
// __ORIGINS__ with the chapter website addresses, or serves nothing at all
// while FORM_FRAMING is off.
//
// 1. Opened with ?embed=1, the form takes the website's colours and fonts and
//    drops its own heading, footer and background (/assets/embed.css).
// 2. Inside a frame, it tells the page holding the frame how tall it is, so the
//    frame grows and shrinks with it and never shows a scroll bar of its own.
//    The height goes only to the chapter website's own addresses.
(function () {
  var ORIGINS = __ORIGINS__;
  var params;
  try { params = new URLSearchParams(window.location.search); } catch (e) { params = null; }
  if (params && params.get("embed") === "1") {
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/assets/embed.css";
    document.head.appendChild(link);
    document.documentElement.classList.add("cbm-embedded");
  }
  if (window.parent === window || !ORIGINS.length) return;
  var last = 0;
  function report() {
    var h = Math.ceil(document.documentElement.getBoundingClientRect().height);
    if (h === last) return;
    last = h;
    ORIGINS.forEach(function (origin) {
      try { window.parent.postMessage({ type: "cmw:frame-height", height: h }, origin); } catch (e) { /* not that site */ }
    });
  }
  window.addEventListener("load", report);
  window.addEventListener("resize", report);
  document.addEventListener("DOMContentLoaded", function () {
    new MutationObserver(report).observe(document.documentElement,
      { childList: true, subtree: true, attributes: true });
    report();
  });
  setInterval(report, 1000);
})();
