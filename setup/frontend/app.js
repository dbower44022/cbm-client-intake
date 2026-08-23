/* System Settings (/setup) — admin-only control panel over the runtime settings.
 *
 * Conventions this page follows deliberately:
 *   - buttons are never disabled and never hidden; validation happens on click
 *     and the message names what is missing;
 *   - no page width cap — density comes from packing the full width;
 *   - busy.js is loaded first and wraps fetch, so presses get feedback free.
 */
(function () {
  "use strict";

  var API = "/setup/api";
  var state = { page: null, tab: "settings", editing: null };

  function $(id) { return document.getElementById(id); }
  function text(el, value) { el.textContent = value == null ? "" : String(value); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  async function api(path, options) {
    var resp = await fetch(API + path, Object.assign({
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
    }, options || {}));
    if (resp.status === 401) {
      window.location.href = "/?next=setup";
      throw new Error("unauthenticated");
    }
    var body = null;
    try { body = await resp.json(); } catch (e) { body = null; }
    if (!resp.ok) {
      var detail = (body && (body.detail || body.error)) || ("HTTP " + resp.status);
      throw new Error(detail);
    }
    return body;
  }

  function showMessage(msg) {
    $("bodyView").hidden = true;
    $("msgView").hidden = false;
    text($("msgText"), msg);
  }

  // --- rendering: settings ---------------------------------------------------

  function sourceChip(row) {
    if (row.source === "override") return '<span class="su__chip su__chip--override">Override</span>';
    if (row.source === "overlay") return '<span class="su__chip">Deployment</span>';
    return '<span class="su__chip su__chip--muted">Default</span>';
  }

  function badges(row) {
    var out = "";
    if (row.restart) {
      out += '<span class="su__chip su__chip--warn" title="Router mounting and boot-time '
           + 'configuration are decided when the process starts">Takes effect on next deploy</span>';
    }
    if (row.component && row.component !== "web") {
      out += '<span class="su__chip su__chip--muted" title="Which process reads this setting">'
           + esc(row.component) + "</span>";
    }
    var o = row.override;
    if (o && o.scoped) {
      var who = (o.scopeTeams || []).concat(o.scopeUsers || []).join(", ");
      out += '<span class="su__chip su__chip--scope">Only: ' + esc(who) + "</span>";
    }
    if (o && o.temporary) {
      out += '<span class="su__chip su__chip--warn">Temporary'
           + (o.reviewAt ? " — review " + esc(o.reviewAt.slice(0, 10)) : "") + "</span>";
    }
    return out;
  }

  function valueCell(row) {
    if (row.secret) return row.isSet ? "set" : "not set";
    if (row.kind === "bool") return row.value === "true" ? "On" : "Off";
    return row.value === "" ? "—" : esc(row.value) + (row.unit ? " " + esc(row.unit) : "");
  }

  function settingRow(row) {
    // Ruling 2: when an override disagrees with the overlay, show BOTH so the
    // overlay never silently lies about what the app is doing.
    var disagree = row.differs
      ? '<div class="su__disagree">Deployment says <code>' + esc(row.envValue)
        + "</code> · override says <code>" + esc(row.value) + "</code></div>"
      : "";
    return ''
      + '<tr class="su__row' + (row.overridden ? " is-overridden" : "") + '" data-key="' + esc(row.key) + '">'
      + '  <td class="su__namecell">'
      + '    <button type="button" class="su__linkbtn" data-edit="' + esc(row.key) + '">' + esc(row.label) + "</button>"
      + '    <div class="su__key">' + esc(row.key) + "</div>"
      + (row.help ? '<div class="su__rowhelp">' + esc(row.help) + "</div>" : "")
      + disagree
      + "  </td>"
      + '  <td class="su__valuecell">' + valueCell(row) + "</td>"
      + '  <td class="su__metacell">' + sourceChip(row) + badges(row) + "</td>"
      + "</tr>";
  }

  function renderSettings() {
    var page = state.page;
    var filter = ($("filterBox").value || "").toLowerCase();
    var onlyOverridden = $("onlyOverridden").checked;
    var html = "";
    page.groups.forEach(function (group) {
      var rows = group.settings.filter(function (r) {
        if (onlyOverridden && !r.overridden) return false;
        if (!filter) return true;
        return (r.label + " " + r.key + " " + (r.help || "")).toLowerCase().indexOf(filter) >= 0;
      });
      if (!rows.length) return;
      html += '<section class="su__group"><h2 class="su__h2">' + esc(group.name) + "</h2>"
            + '<table class="su__table"><tbody>' + rows.map(settingRow).join("") + "</tbody></table></section>";
    });
    $("groups").innerHTML = html || '<p class="su__hint">Nothing matches that filter.</p>';

    $("otherRows").innerHTML = page.other.map(function (r) {
      return "<tr><td>" + esc(r.label) + '<div class="su__key">' + esc(r.key) + "</div></td>"
        + "<td>" + (r.secret ? (r.isSet ? "set" : "not set") : esc(r.value || "—")) + "</td>"
        + "<td>" + (r.denylisted ? '<span class="su__chip su__chip--muted">Never editable</span>' : "") + "</td></tr>";
    }).join("");

    text($("overrideStat"),
      page.overrideCount + " override" + (page.overrideCount === 1 ? "" : "s")
      + (page.scopedCount ? " · " + page.scopedCount + " scoped" : "")
      + (page.temporaryCount ? " · " + page.temporaryCount + " temporary" : ""));
  }

  function renderOverdue() {
    var overdue = (state.page && state.page.overdue) || [];
    var el = $("overdueBanner");
    if (!overdue.length) { el.hidden = true; return; }
    el.hidden = false;
    el.innerHTML = "<strong>" + overdue.length + " temporary change"
      + (overdue.length === 1 ? " is" : "s are") + " past review:</strong> "
      + overdue.map(function (o) { return "<code>" + esc(o.key) + "</code>"; }).join(", ")
      + ". Nothing reverts on its own — decide whether each should stay.";
  }

  // --- editing ---------------------------------------------------------------

  function findRow(key) {
    var found = null;
    state.page.groups.forEach(function (g) {
      g.settings.forEach(function (r) { if (r.key === key) found = r; });
    });
    return found;
  }

  function openEditor(key) {
    var row = findRow(key);
    if (!row) return;
    state.editing = row;
    text($("editTitle"), row.label);
    text($("editKey"), row.key);
    text($("editHelp"), row.help || "");
    $("editError").hidden = true;

    var control = $("editControl");
    if (row.kind === "bool") {
      control.innerHTML = '<select id="editValue"><option value="true">On</option>'
        + '<option value="false">Off</option></select>';
    } else if (row.kind === "choice") {
      control.innerHTML = '<select id="editValue">'
        + row.choices.map(function (c) { return '<option value="' + esc(c) + '">' + esc(c) + "</option>"; }).join("")
        + "</select>";
    } else {
      control.innerHTML = '<input type="text" id="editValue" />';
    }
    $("editValue").value = row.value;

    text($("editEnvNote"), row.overridden
      ? "This is currently overridden. The deployment overlay says \"" + row.envValue
        + "\" — resetting returns it to that."
      : "The deployment value is \"" + row.envValue + "\".");

    $("editReason").value = "";
    $("editTemporary").checked = !!(row.override && row.override.temporary);
    $("editReviewAt").disabled = !$("editTemporary").checked;
    $("editReviewAt").value = row.override && row.override.reviewAt
      ? row.override.reviewAt.slice(0, 10) : "";
    $("editScopeTeams").value = row.override ? (row.override.scopeTeams || []).join(", ") : "";
    $("editScopeUsers").value = row.override ? (row.override.scopeUsers || []).join(", ") : "";

    // Scoping needs a signed-in user to evaluate against, so it only exists for
    // web-side settings. Show why rather than hiding the control silently.
    $("scopeField").classList.toggle("is-disabled", !row.scopable);
    $("editScopeTeams").disabled = !row.scopable;
    $("editScopeUsers").disabled = !row.scopable;
    text($("scopeHint"), row.scopable
      ? "Leave blank to change it for everyone."
      : "This setting is read by the " + row.component + " process, which has no "
        + "signed-in user, so it cannot be rolled out to a subset.");

    $("editReset").hidden = !row.overridden;
    $("editOverlay").hidden = false;
  }

  function closeEditor() {
    $("editOverlay").hidden = true;
    state.editing = null;
  }

  function csv(value) {
    return (value || "").split(",").map(function (s) { return s.trim(); })
      .filter(function (s) { return s; });
  }

  async function saveEdit() {
    var row = state.editing;
    if (!row) return;
    var err = $("editError");
    err.hidden = true;
    var temporary = $("editTemporary").checked;
    var reviewAt = $("editReviewAt").value;
    if (temporary && !reviewAt) {
      err.hidden = false;
      text(err, "Pick a review date — that is what makes it temporary.");
      return;
    }
    try {
      var result = await api("/settings/" + encodeURIComponent(row.key), {
        method: "PUT",
        body: JSON.stringify({
          value: $("editValue").value,
          reason: $("editReason").value,
          temporary: temporary,
          reviewAt: temporary ? new Date(reviewAt + "T12:00:00Z").toISOString() : null,
          scopeTeams: row.scopable ? csv($("editScopeTeams").value) : [],
          scopeUsers: row.scopable ? csv($("editScopeUsers").value) : [],
        }),
      });
      state.page = result.page;
      closeEditor();
      renderSettings();
      renderOverdue();
      if (result.restart) {
        window.alert(row.label + " is saved, but it is read when the process starts — "
          + "it will not take effect until the next deploy.");
      }
    } catch (e) {
      err.hidden = false;
      text(err, e.message);
    }
  }

  async function resetEdit() {
    var row = state.editing;
    if (!row) return;
    try {
      var result = await api("/settings/" + encodeURIComponent(row.key), {
        method: "DELETE",
        body: JSON.stringify({ reason: $("editReason").value }),
      });
      state.page = result.page;
      closeEditor();
      renderSettings();
      renderOverdue();
    } catch (e) {
      $("editError").hidden = false;
      text($("editError"), e.message);
    }
  }

  // --- readiness -------------------------------------------------------------

  function checkIcon(ok) {
    if (ok === true) return '<span class="su__ok">✓</span>';
    if (ok === false) return '<span class="su__bad">✗</span>';
    return '<span class="su__unknown">?</span>';
  }

  async function loadReadiness() {
    var data = await api("/readiness");
    text($("readinessHint"),
      "CRM: " + data.crm + (data.dryRun ? " (dry-run)" : "")
      + (data.crmReachable ? "" : " — could not be read, so CRM checks show as unknown")
      + " · worker heartbeat: "
      + (data.workerHeartbeatAgeSeconds == null
          ? "never seen"
          : Math.round(data.workerHeartbeatAgeSeconds) + "s ago")
      + (data.workerStale ? " (stale)" : ""));

    $("readinessRows").innerHTML = data.features.map(function (f) {
      var checks = f.checks.map(function (c) {
        return "<li>" + checkIcon(c.ok) + " " + esc(c.label)
          + ' <span class="su__muted">' + esc(c.detail) + "</span></li>";
      }).join("");
      var warn = f.workerWarning
        ? '<p class="su__disagree">This runs on the worker, and the worker has not '
          + "checked in recently — the flag is on but nothing will happen.</p>"
        : "";
      return '<section class="su__feature su__feature--' + esc(f.status) + '">'
        + '<h3>' + esc(f.name) + ' <span class="su__chip su__chip--' + esc(f.status) + '">'
        + esc(f.status) + "</span>"
        + '<span class="su__chip su__chip--muted">' + esc(f.component) + "</span></h3>"
        + (f.note ? '<p class="su__rowhelp">' + esc(f.note) + "</p>" : "")
        + warn
        + (checks ? "<ul class=\"su__checks\">" + checks + "</ul>" : "")
        + "</section>";
    }).join("");
  }

  // --- environment diff ------------------------------------------------------

  async function loadDiff() {
    var data = await api("/diff");
    if (!data.ok) {
      $("diffRows").innerHTML = '<p class="su__hint">' + esc(data.error) + "</p>";
      text($("diffStat"), "");
      return;
    }
    text($("diffStat"), data.differences.length + " difference"
      + (data.differences.length === 1 ? "" : "s") + " · " + data.sameCount + " identical");
    if (!data.differences.length) {
      $("diffRows").innerHTML = '<p class="su__hint">The two environments agree on every '
        + "curated setting.</p>";
      return;
    }
    $("diffRows").innerHTML = '<table class="su__table"><thead><tr><th>Setting</th><th>'
      + esc(data.localEnvironment || "here") + "</th><th>" + esc(data.peerEnvironment || "peer")
      + "</th></tr></thead><tbody>"
      + data.differences.map(function (d) {
        return "<tr><td>" + esc(d.label) + '<div class="su__key">' + esc(d.key) + "</div></td>"
          + "<td>" + esc(d.local == null ? "—" : d.local)
          + (d.localOverridden ? ' <span class="su__chip su__chip--override">override</span>' : "")
          + "</td><td>" + esc(d.peer == null ? "—" : d.peer)
          + (d.peerOverridden ? ' <span class="su__chip su__chip--override">override</span>' : "")
          + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  // --- operations ------------------------------------------------------------

  // The last result per job, so a re-render of the job list cannot lose the
  // plan you are supposed to be reviewing. runJob used to write the output
  // into the job's panel and then call loadJobs(), which rebuilds the panel's
  // innerHTML — the plan flashed and vanished, leaving a history row saying
  // "done" and nothing to review. That defeated the point of dry-run-then-apply.
  var lastResult = {};

  function jobOutput(run) {
    if (!run) return "";
    var cls = run.status === "done" ? "" : " su__pre--warn";
    return '<pre class="su__pre' + cls + '">' + esc(run.error ? run.error + "\n\n" + run.output : run.output) + "</pre>";
  }

  async function loadJobs() {
    var data = await api("/jobs");
    if (!data.available) {
      $("jobRows").innerHTML = '<p class="su__hint">No database is attached, so jobs '
        + "cannot be run or recorded here.</p>";
      return;
    }
    $("jobRows").innerHTML = data.jobs.map(function (j) {
      var actions = j.runnable
        ? '<button type="button" class="cbm-button cbm-button--secondary" data-dry="' + esc(j.key) + '">'
          + (j.twoStep ? "Dry run" : "Run") + "</button>"
          + (j.twoStep ? '<button type="button" class="cbm-button" data-apply="' + esc(j.key) + '">Apply the plan</button>' : "")
        : '<p class="su__disagree">' + esc(j.unavailableReason) + "</p>";
      return '<section class="su__job" data-job="' + esc(j.key) + '">'
        + "<h3>" + esc(j.name)
        + (j.mutating ? ' <span class="su__chip su__chip--warn">changes data</span>'
                      : ' <span class="su__chip su__chip--muted">read-only</span>') + "</h3>"
        + "<p>" + esc(j.description) + "</p>"
        + '<div class="su__jobactions">'
        + (j.runnable && j.mutating
            ? '<input type="text" class="su__reason" data-reason="' + esc(j.key)
              + '" placeholder="Reason (required to apply)" />' : "")
        + actions + "</div>"
        + '<div class="su__joboutput" data-output="' + esc(j.key) + '"></div>'
        + "</section>";
    }).join("");

    Object.keys(lastResult).forEach(function (key) {
      var slot = document.querySelector('[data-output="' + key + '"]');
      if (slot) slot.innerHTML = resultBlock(lastResult[key]);
    });

    // Every past run keeps its report: a run that says "done" and shows nothing
    // is not a record of anything (and an apply is judged against the plan it
    // was applied from, which has to stay readable afterwards).
    jobRuns = {};
    data.recent.forEach(function (r) { jobRuns[r.id] = r; });
    $("jobHistory").innerHTML = data.recent.length
      ? '<table class="su__table"><thead><tr><th>When</th><th>Job</th><th>Mode</th><th>Status</th><th>Who</th><th>Reason</th><th>Report</th></tr></thead><tbody>'
        + data.recent.map(function (r) {
            var has = !!(r.output || r.error);
            return "<tr><td>" + esc((r.startedAt || "").replace("T", " ").slice(0, 16)) + "</td>"
              + "<td>" + esc(r.name) + "</td><td>" + esc(r.mode) + "</td>"
              + '<td><span class="su__chip su__chip--' + esc(r.status) + '">' + esc(r.status) + "</span></td>"
              + "<td>" + esc(r.actor) + "</td><td>" + esc(r.reason) + "</td>"
              + "<td>" + (has
                  ? '<button type="button" class="su__linkbtn" data-run="' + esc(r.id) + '">Show</button>'
                  : '<span class="su__hint">—</span>') + "</td></tr>"
              + '<tr class="su__runrow" data-runrow="' + esc(r.id) + '" hidden>'
              + '<td colspan="7"></td></tr>';
          }).join("") + "</tbody></table>"
      : '<p class="su__hint">No jobs have been run yet.</p>';
  }

  function resultBlock(result) {
    if (!result) return "";
    return (result.error ? '<p class="form-error">' + esc(result.error) + "</p>" : "")
      + jobOutput(result);
  }

  var lastPlan = {};
  var jobRuns = {};   // id -> the recent-run row, for the history "Show" toggle

  function toggleRunOutput(runId) {
    var row = document.querySelector('[data-runrow="' + runId + '"]');
    var run = jobRuns[runId];
    if (!row || !run) return;
    if (row.hidden) {
      row.cells[0].innerHTML = resultBlock(run);
      row.hidden = false;
    } else {
      row.hidden = true;
    }
  }

  async function runJob(key, apply) {
    var out = document.querySelector('[data-output="' + key + '"]');
    var reasonEl = document.querySelector('[data-reason="' + key + '"]');
    var reason = reasonEl ? reasonEl.value : "";
    out.innerHTML = '<p class="su__hint">Running…</p>';
    try {
      var result = await api("/jobs/" + encodeURIComponent(key) + (apply ? "/apply" : "/dry-run"), {
        method: "POST",
        body: JSON.stringify({ reason: reason, planId: apply ? (lastPlan[key] || "") : "" }),
      });
      if (!apply && result.id) lastPlan[key] = result.id;
      lastResult[key] = result;
      out.innerHTML = resultBlock(result);
      await loadJobs();   // restores the block above from lastResult
    } catch (e) {
      out.innerHTML = '<p class="form-error">' + esc(e.message) + "</p>";
    }
  }

  // --- history ---------------------------------------------------------------

  async function loadHistory() {
    var key = ($("historyKey").value || "").trim();
    var data = await api("/history?limit=200" + (key ? "&key=" + encodeURIComponent(key) : ""));
    $("historyRows").innerHTML = data.history.length
      ? data.history.map(function (h) {
          var change = h.action === "clear"
            ? "reset (was " + esc(h.oldValue) + ")"
            : esc(h.oldValue == null ? "—" : h.oldValue) + " → " + esc(h.newValue);
          return "<tr><td>" + esc((h.at || "").replace("T", " ").slice(0, 16)) + "</td>"
            + "<td>" + esc(h.key) + "</td><td>" + change + "</td>"
            + "<td>" + esc(h.actor) + "</td><td>" + esc(h.reason) + "</td></tr>";
        }).join("")
      : '<tr><td colspan="5">Nothing recorded yet.</td></tr>';
  }

  // --- tabs + boot -----------------------------------------------------------

  function selectTab(name) {
    state.tab = name;
    ["settings", "readiness", "diff", "jobs", "history"].forEach(function (t) {
      $("tab-" + t).hidden = t !== name;
    });
    Array.prototype.forEach.call(document.querySelectorAll(".su__tab"), function (b) {
      b.classList.toggle("is-active", b.dataset.tab === name);
    });
    if (name === "readiness") loadReadiness().catch(function (e) {
      $("readinessRows").innerHTML = '<p class="form-error">' + esc(e.message) + "</p>";
    });
    if (name === "jobs") loadJobs().catch(function (e) {
      $("jobRows").innerHTML = '<p class="form-error">' + esc(e.message) + "</p>";
    });
    if (name === "history") loadHistory().catch(function () {});
  }

  async function boot() {
    try {
      var page = await api("/settings");
      state.page = page;
    } catch (e) {
      showMessage(e.message);
      return;
    }
    $("bodyView").hidden = false;
    $("msgView").hidden = true;
    $("breakGlass").hidden = !state.page.breakGlass;
    text($("pageSubtitle"),
      "This deployment: " + state.page.environment
      + (state.page.writable ? "" : " · read-only (no database attached)"));
    renderSettings();
    renderOverdue();
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (t.dataset && t.dataset.edit) { openEditor(t.dataset.edit); return; }
    if (t.dataset && t.dataset.dry) { runJob(t.dataset.dry, false); return; }
    if (t.dataset && t.dataset.apply) { runJob(t.dataset.apply, true); return; }
    if (t.dataset && t.dataset.run) { toggleRunOutput(t.dataset.run); return; }
    if (t.classList && t.classList.contains("su__tab")) { selectTab(t.dataset.tab); return; }
  });

  document.addEventListener("DOMContentLoaded", function () {
    $("filterBox").addEventListener("input", renderSettings);
    $("onlyOverridden").addEventListener("change", renderSettings);
    $("reloadBtn").addEventListener("click", boot);
    $("editCancel").addEventListener("click", closeEditor);
    $("editSave").addEventListener("click", saveEdit);
    $("editReset").addEventListener("click", resetEdit);
    $("editTemporary").addEventListener("change", function () {
      $("editReviewAt").disabled = !this.checked;
    });
    $("diffBtn").addEventListener("click", function () {
      loadDiff().catch(function (e) {
        $("diffRows").innerHTML = '<p class="form-error">' + esc(e.message) + "</p>";
      });
    });
    $("historyBtn").addEventListener("click", function () { loadHistory().catch(function () {}); });
    $("logoutBtn").addEventListener("click", function () {
      fetch("/api/portal/logout", { method: "POST", credentials: "same-origin" })
        .finally(function () { window.location.href = "/"; });
    });
    boot();
  });
})();
