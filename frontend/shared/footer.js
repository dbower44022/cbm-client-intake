/* Populates the page footer (current year + app version) and renders the
 * environment badge in the top-right corner. Both the version and the
 * environment come from /healthz so they stay in sync with the deployed build
 * (single source of truth: pyproject.toml + core/config -> /healthz -> here). */
(function () {
  "use strict";
  var yearEl = document.querySelector("[data-cbm-year]");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // Map the canonical /healthz environment key to a label + style variant.
  // Unknown values (e.g. a custom ENV_LABEL) fall back to a neutral badge.
  var ENVS = {
    production: { label: "PRODUCTION", variant: "prod" },
    test: { label: "TEST", variant: "test" },
    dev: { label: "DEV · DRY-RUN", variant: "dev" }
  };

  function renderBadge(env) {
    if (!env) return;
    var meta = ENVS[env] || { label: String(env).toUpperCase(), variant: "neutral" };
    var badge = document.createElement("div");
    badge.className = "cbm-env-badge cbm-env-badge--" + meta.variant;
    badge.textContent = meta.label;
    badge.setAttribute("role", "status");
    badge.setAttribute("title", "Environment: " + meta.label);
    document.body.appendChild(badge);
  }

  var verEl = document.querySelector("[data-cbm-version]");
  fetch("/healthz")
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d) return;
      if (verEl && d.version) verEl.textContent = "v" + d.version;
      renderBadge(d.environment);
    })
    .catch(function () { /* leave version/badge off if /healthz is unavailable */ });
})();
