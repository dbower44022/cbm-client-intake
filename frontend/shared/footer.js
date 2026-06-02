/* Populates the page footer: current year and the app version.
 * The version comes from /healthz so it stays in sync with the deployed build
 * (single source of truth: pyproject.toml -> /healthz -> here). */
(function () {
  "use strict";
  var yearEl = document.querySelector("[data-cbm-year]");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  var verEl = document.querySelector("[data-cbm-version]");
  if (!verEl) return;
  fetch("/healthz")
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d && d.version) verEl.textContent = "v" + d.version;
    })
    .catch(function () { /* leave version blank if unavailable */ });
})();
