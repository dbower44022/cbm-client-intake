/* Populates the page footer: current year and the app version with the
 * environment name appended (e.g. "v0.18.0 (Production)"). Both the version and
 * the environment come from /healthz so they stay in sync with the deployed build
 * (single source of truth: pyproject.toml + core/config -> /healthz -> here). */
(function () {
  "use strict";
  var yearEl = document.querySelector("[data-cbm-year]");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // Canonical /healthz environment key -> display name. Unknown values (e.g. a
  // custom ENV_LABEL) are title-cased as-is.
  var ENV_NAMES = { production: "Production", test: "Test", dev: "Dev" };
  function envName(env) {
    if (!env) return "";
    return ENV_NAMES[env] || (env.charAt(0).toUpperCase() + env.slice(1));
  }

  var verEl = document.querySelector("[data-cbm-version]");
  if (!verEl) return;
  fetch("/healthz")
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d || !d.version) return;
      var name = envName(d.environment);
      verEl.textContent = "v" + d.version + (name ? " (" + name + ")" : "");
    })
    .catch(function () { /* leave version blank if /healthz is unavailable */ });
})();
