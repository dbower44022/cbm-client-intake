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
  var state = { page: null, tab: "settings", editing: null, subtab: null, closed: {} };

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

  var RESTART_GROUP = "Restart required";
  var WEBSITE_GROUP = "Website";

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
    if (row.pendingRestart) {
      out += '<span class="su__chip su__chip--pending" title="Saved, but this process is '
           + 'still running the value it started with. It will take effect when the app '
           + 'restarts \u2014 a redeploy, or Restart from the DigitalOcean console.">'
           + 'Waiting for restart</span>';
    } else if (row.restart) {
      out += '<span class="su__chip su__chip--muted" title="Read once while the process '
           + 'starts. Saving a change here stores it; it takes effect on the next '
           + 'restart.">In force</span>';
    }
    if (row.editable === false) {
      out += '<span class="su__chip su__chip--muted" title="Shown so it is never hidden, '
           + 'but it cannot be set from here">Read-only</span>';
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
    // A restart-required setting that has been changed is running the OLD
    // value. Say both, plainly, rather than showing the stored one as if it
    // were live.
    if (row.pendingRestart) {
      disagree += '<div class="su__pending">Running <code>' + esc(row.inForce)
        + "</code> now \u2014 will become <code>" + esc(row.value)
        + "</code> when the app restarts.</div>";
    }
    return ''
      + '<tr class="su__row' + (row.overridden ? " is-overridden" : "") + '" data-key="' + esc(row.key) + '">'
      + '  <td class="su__namecell">'
      + (row.editable === false
          ? '    <span class="su__linkbtn su__linkbtn--off">' + esc(row.label) + "</span>"
          : '    <button type="button" class="su__linkbtn" data-edit="' + esc(row.key) + '">' + esc(row.label) + "</button>")
      + '    <div class="su__key">' + esc(row.key) + "</div>"
      + (row.help ? '<div class="su__rowhelp">' + esc(row.help) + "</div>" : "")
      + disagree
      + "  </td>"
      + '  <td class="su__valuecell">' + valueCell(row) + "</td>"
      + '  <td class="su__metacell">' + sourceChip(row) + badges(row) + "</td>"
      + "</tr>";
  }

  // Every setting is on this page, including the ones a running process cannot
  // pick up. Those say so here rather than being left off — a setting you
  // cannot see is a setting nobody can fix.
  function groupNote(name) {
    if (name !== RESTART_GROUP) return "";
    var r = (state.page && state.page.restart) || {};
    var note = '<p class="su__note">These are read <strong>once, while the app '
      + "starts</strong> \u2014 they decide which parts of the product are mounted, how "
      + "requests are limited and how much is logged. You can change any of them here "
      + "and the change is stored immediately, but <strong>the running app keeps the "
      + "value it started with until it restarts</strong>. Each row shows which value is "
      + "in force now. Restart from the DigitalOcean console, or redeploy.</p>";
    if (r.bootOutcome === "failed") {
      note += '<p class="su__note su__note--warn"><strong>Stored settings could not be '
        + "read when this app started</strong>, so none of them are in force here \u2014 "
        + "the app is running entirely on its deployment configuration. "
        + esc(r.bootDetail || "") + "</p>";
    }
    if (r.count) {
      note += '<p class="su__note su__note--warn"><strong>' + r.count + " change"
        + (r.count === 1 ? " is" : "s are") + " waiting for a restart:</strong> "
        + r.pending.map(function (x) { return "<code>" + esc(x.key) + "</code>"; }).join(", ")
        + ".</p>";
    }
    return note;
  }

  /* ---------- the shared grid (prds/shared-grid-plan.md § 12) ----------
   * A settings group is a form laid out in rows (a Change button per
   * setting, in the group's own order), so it resizes and shades but never
   * sorts; so does the run history, whose report opens as an extra row under
   * its run. The read-only lists — all settings, the environment diff and
   * the change history — sort in place. A table rebuilt by innerHTML is a new
   * element, so it is enhanced again; its widths and sort come back from the
   * grid's own store. */
  var SETTINGS_HEAD = '<thead><tr><th data-col="setting" data-sortable="false">Setting</th>'
    + '<th data-col="value" data-sortable="false">Value</th>'
    + '<th data-col="source" data-sortable="false">Source</th></tr></thead>';

  function fitGrid(table, key) {
    if (!table || !window.CBMGrid) return null;
    if (!table._grid) table._grid = window.CBMGrid.enhance(table, { key: key });
    return table._grid;
  }

  function gridRefresh(grid) { if (grid) grid.refresh(); }

  function busyOver(el, promise) {
    return el && window.CBMBusy && window.CBMBusy.loading ? window.CBMBusy.loading(el, promise) : promise;
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
            + groupNote(group.name)
            + '<table class="su__table su__table--settings">' + SETTINGS_HEAD + "<tbody>"
            + rows.map(settingRow).join("") + "</tbody></table>"
            + (group.name === WEBSITE_GROUP ? '<div id="websiteImages" class="su__images"></div>' : "")
            + "</section>";
    });
    $("groups").innerHTML = html || '<p class="su__hint">Nothing matches that filter.</p>';
    renderWebsiteImages();
    Array.prototype.forEach.call($("groups").querySelectorAll("table"), function (t) {
      fitGrid(t, "setup.settings");
    });

    $("otherRows").innerHTML = page.other.map(function (r) {
      return "<tr><td>" + esc(r.label) + '<div class="su__key">' + esc(r.key) + "</div></td>"
        + "<td>" + (r.secret ? (r.isSet ? "set" : "not set") : esc(r.value || "—")) + "</td>"
        + "<td>" + (r.denylisted ? '<span class="su__chip su__chip--muted">Never editable</span>' : "") + "</td></tr>";
    }).join("");
    gridRefresh(fitGrid($("otherTable"), "setup.allSettings"));

    text($("overrideStat"),
      page.overrideCount + " override" + (page.overrideCount === 1 ? "" : "s")
      + (page.scopedCount ? " · " + page.scopedCount + " scoped" : "")
      + (page.temporaryCount ? " · " + page.temporaryCount + " temporary" : ""));
  }

  // Confirm-or-revert. This banner is the entire safety net for the settings
  // that can lock an admin out, so it leads the page and counts down out loud.
  var confirmTimer = null;

  function renderConfirm() {
    var pending = (state.page && state.page.awaitingConfirmation) || [];
    var el = $("confirmBanner");
    if (confirmTimer) { clearInterval(confirmTimer); confirmTimer = null; }
    if (!pending.length) { el.hidden = true; return; }
    el.hidden = false;

    function paint() {
      var html = "<strong>" + pending.length + " change"
        + (pending.length === 1 ? "" : "s")
        + " will undo " + (pending.length === 1 ? "itself" : "themselves")
        + " unless you confirm the system still works.</strong> "
        + "Check that you can still sign in and use the app, then confirm. "
        + "Doing nothing is safe \u2014 it reverts.<ul class=\"su__confirmlist\">";
      pending.forEach(function (p) {
        var left = p.revertAt ? Math.max(0, Math.round((new Date(p.revertAt) - Date.now()) / 1000)) : null;
        var mins = left == null ? "" : Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0");
        html += "<li><code>" + esc(p.key) + "</code> \u2014 " + esc(p.label)
          + (left == null ? "" : ' <span class="su__countdown">' + mins + "</span> left")
          + ' <button type="button" class="cbm-button cbm-button--secondary" data-confirm="'
          + esc(p.key) + '">It works \u2014 keep it</button></li>';
      });
      el.innerHTML = html + "</ul>";
    }
    paint();
    confirmTimer = setInterval(paint, 1000);
  }

  async function confirmSetting(key) {
    try {
      var result = await api("/settings/" + encodeURIComponent(key) + "/confirm", { method: "POST" });
      state.page = result.page;
      renderAll();
    } catch (e) {
      window.console && window.console.warn("confirm failed", e);
    }
  }

  // One entry point, so a new banner cannot be forgotten by a call site.
  function renderAll() {
    renderSettings();
    renderIntegrations();
    renderOverdue();
    renderConfirm();
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
    // With the Integrations tab on, an integration's settings live on its
    // sub-tab and are edited by the same dialog and the same save path.
    (state.page.integrations || []).forEach(function (i) {
      integrationRows(i).forEach(function (r) { if (r.key === key) found = r; });
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
    // A secret is never sent to the browser, so there is nothing to prefill and
    // the box means "the NEW value" rather than "the current one".
    $("editValue").value = row.secret ? "" : row.value;
    if (row.secret) {
      $("editValue").setAttribute("placeholder",
        row.isSet ? "A value is set. Type a new one to replace it."
                  : "Not set. Type a value.");
    } else {
      $("editValue").removeAttribute("placeholder");
    }

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
      renderAll();
      if (result.reverted) {
        var rb = $("restartBanner");
        rb.hidden = false;
        rb.innerHTML = "<strong>" + esc(row.label) + " was undone.</strong> "
          + "It saved, but the system stopped working with it, so the previous "
          + "value was put back automatically: " + esc(result.reverted);
        return;
      }
      var v = result.verification || {};
      if (v.outcome === "unknown") {
        var ub = $("restartBanner");
        ub.hidden = false;
        ub.innerHTML = "<strong>" + esc(row.label) + " is saved, but could not be "
          + "checked.</strong> " + esc(v.detail || "")
          + " The value was stored because a check that cannot run must not block "
          + "you from fixing configuration during an outage \u2014 but nothing has "
          + "confirmed it works.";
      }
      if (result.restart) {
        // Not an alert(): a modal blocks the page to repeat what the row now
        // says next to the value. This states it once, in place, and stays put.
        var b = $("restartBanner");
        b.hidden = false;
        b.innerHTML = "<strong>" + esc(row.label) + " is saved and stored.</strong> "
          + "It is read while the app starts, so the running app keeps its current "
          + "value until it restarts \u2014 redeploy, or use Restart in the "
          + "DigitalOcean console. The row below shows which value is in force now.";
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
      renderAll();
    } catch (e) {
      $("editError").hidden = false;
      text($("editError"), e.message);
    }
  }

  // --- integrations (prds/integrations-tab-plan.md) ---------------------------
  // One sub-tab per outside service, shown only while INTEGRATIONS_TAB is on.
  // Its settings are rendered by settingRow, the Settings tab's own row, and
  // edited by the same dialog through the same checked save path.

  function integrationRows(i) {
    var rows = (i.settings || []).slice();
    (i.sections || []).forEach(function (s) { rows = rows.concat(s.settings || []); });
    return rows;
  }

  function findIntegration(key) {
    return ((state.page && state.page.integrations) || []).filter(function (i) { return i.key === key; })[0] || null;
  }

  function statusLine(i) {
    var st = i.status || {};
    var parts = [];
    if (st.alwaysInUse) parts.push("always in use");
    else parts.push(st.inUse ? "in use" : "Not used by this chapter");
    if (i.key === "espocrm") {
      parts.push(st.dryRun ? "dry run \u2014 nothing is written to the CRM" : "on \u2014 writing to the CRM");
    } else if (!st.hasSwitches) {
      parts.push("no feature switch");
    } else {
      parts.push(st.on ? "on (" + st.onSwitches.join(", ") + ")" : "off");
    }
    var missing = st.credentialsMissing || [];
    parts.push(missing.length ? "credentials missing: " + missing.join(", ") : "credentials set");
    parts.push("Not tested yet");
    return '<p class="su__status' + (st.inUse === false ? " su__status--unused" : "") + '"><strong>'
      + esc(i.name) + ":</strong> " + parts.map(esc).join(" \u00b7 ") + "</p>";
  }

  function placeholders(i) {
    var ph = i.phases || {};
    // Not buttons: nothing that looks clickable and does nothing.
    return '<ul class="su__placeholders">'
      + "<li><strong>Integration test</strong> \u2014 comes with phase " + esc(ph.test) + " of the Integrations tab build.</li>"
      + "<li><strong>Diagnosis</strong> \u2014 comes with phase " + esc(ph.diagnosis) + ".</li>"
      + "<li><strong>Setup checklist</strong> \u2014 comes with phase " + esc(ph.checklist) + ".</li>"
      + "</ul>";
  }

  function settingsTable(rows) {
    if (!rows.length) return "";
    return '<table class="su__table su__table--settings">' + SETTINGS_HEAD + "<tbody>"
      + rows.map(settingRow).join("") + "</tbody></table>";
  }

  function usedByBlock(i) {
    var list = i.usedBy || [];
    if (!list.length) return "";
    return '<section class="su__group"><h2 class="su__h2">Used by</h2>'
      + '<p class="su__note">These stay where they are and are changed there. '
      + "A row marked <em>needs " + esc(i.name) + "</em> cannot work without it.</p>"
      + '<table class="su__table su__table--usedby"><thead><tr>'
      + '<th data-col="setting" data-sortable="false">Setting</th>'
      + '<th data-col="value" data-sortable="false">Value</th>'
      + '<th data-col="where" data-sortable="false">Where it is changed</th></tr></thead><tbody>'
      + list.map(function (u) {
          return "<tr><td>" + esc(u.label) + '<div class="su__key">' + esc(u.key) + "</div></td>"
            + '<td class="su__valuecell">' + valueCell(u) + "</td>"
            + '<td><a href="#settings" class="su__goto" data-goto="' + esc(u.key) + '">'
            + (u.group ? "Settings tab, " + esc(u.group) : "Settings tab") + "</a>"
            + (u.blocks ? ' <span class="su__chip su__chip--warn">needs ' + esc(i.name) + "</span>" : "")
            + "</td></tr>";
        }).join("") + "</tbody></table></section>";
  }

  function renderIntegrations() {
    var page = state.page;
    var on = !!(page && page.integrationsTab);
    $("integrationsTabBtn").hidden = !on;
    if (!on) {
      if (state.tab === "integrations") selectTab("settings");
      return;
    }
    var list = page.integrations || [];
    if (!state.subtab || !findIntegration(state.subtab)) state.subtab = list.length ? list[0].key : null;
    $("integrationTabs").innerHTML = list.map(function (i) {
      var unused = i.status && i.status.inUse === false;
      return '<button type="button" class="su__subtab' + (i.key === state.subtab ? " is-active" : "")
        + (unused ? " is-unused" : "") + '" data-subtab="' + esc(i.key) + '" role="tab">'
        + esc(i.name) + "</button>";
    }).join("");
    var i = findIntegration(state.subtab);
    if (!i) { $("integrationBody").innerHTML = ""; return; }
    var html = statusLine(i);
    if (i.status && i.status.inUse === false) {
      html += '<p class="su__note su__note--warn"><strong>Not used by this chapter.</strong> '
        + "Its settings stay here and can still be changed. Its warnings are left out of "
        + "Feature readiness, and none of its features can be switched on until it is "
        + "marked in use.</p>";
    }
    html += placeholders(i);
    html += '<section class="su__group"><h2 class="su__h2">Settings</h2>' + settingsTable(i.settings || []);
    (i.sections || []).forEach(function (s) {
      var id = i.key + "/" + s.key;
      html += '<details class="su__section" data-section="' + esc(id) + '"'
        + (state.closed[id] ? "" : " open") + "><summary>" + esc(s.title) + "</summary>"
        + (settingsTable(s.settings || []) || '<p class="su__hint">Nothing here.</p>') + "</details>";
    });
    html += "</section>" + usedByBlock(i);
    if ((i.runbooks || []).length) {
      html += '<p class="su__hint">Runbook' + (i.runbooks.length === 1 ? "" : "s") + " in the repository: "
        + i.runbooks.map(function (r) { return "<code>" + esc(r) + "</code>"; }).join(", ") + "</p>";
    }
    $("integrationBody").innerHTML = html;
    Array.prototype.forEach.call($("integrationBody").querySelectorAll("table"), function (t) {
      fitGrid(t, t.classList.contains("su__table--usedby") ? "setup.usedBy" : "setup.settings");
    });
  }

  function selectSubtab(key) {
    if (!findIntegration(key)) return;
    state.subtab = key;
    if (state.tab !== "integrations") selectTab("integrations");
    else renderIntegrations();
    history.replaceState(null, "", window.location.pathname + "#integrations/" + key);
  }

  // A "Used by" link: the setting is changed on the Settings tab, so go there,
  // make sure no filter hides it, and bring its row into view.
  function gotoSetting(key) {
    $("filterBox").value = "";
    $("onlyOverridden").checked = false;
    selectTab("settings");
    renderSettings();
    var tr = document.querySelector('#groups tr[data-key="' + key + '"]');
    if (!tr) return;
    tr.scrollIntoView({ block: "center" });
    tr.classList.add("is-flash");
    setTimeout(function () { tr.classList.remove("is-flash"); }, 2500);
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
      + (data.workerStale ? " (stale)" : "")
      + (data.counts
          ? " \u00b7 " + data.counts.blocked + " blocked, " + data.counts.unknown + " unknown"
            + (data.counts.notUsed ? " (" + data.counts.notUsed + " left out: not used by this chapter)" : "")
          : ""));

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
        + (f.excludedNote ? '<p class="su__note su__note--warn">' + esc(f.excludedNote) + "</p>" : "")
        + (f.integration
            ? '<p class="su__rowhelp"><a href="#integrations/' + esc(f.integration) + '" data-subtab="'
              + esc(f.integration) + '">' + esc(f.integrationName) + " settings</a></p>"
            : "")
        + warn
        + (checks ? "<ul class=\"su__checks\">" + checks + "</ul>" : "")
        + (f.key === "mailing" ? renderMailing(data.mailing) : "")
        + "</section>";
    }).join("");
  }

  // --- mailing service connection (Phase C) -----------------------------------
  // The credential here is a GRANT: after the client ID and secret are set, an
  // administrator connects the account in a browser round trip. The redirect
  // address is computed server-side from APP_BASE_URL and shown here with a
  // copy button, so the value registered on the vendor's application is the
  // value used. Buttons are never hidden or disabled (convention): Connect
  // explains itself server-side with a 400 when something is missing.
  function renderMailing(mail) {
    if (!mail) return "";
    var conn = mail.connection;
    var line;
    if (conn && conn.status === "connected") {
      line = "Connected as <strong>" + esc(conn.accountLabel || "the mailing account") + "</strong>"
        + (conn.connectedBy ? " by " + esc(conn.connectedBy) : "")
        + (conn.connectedAt ? " on " + esc(conn.connectedAt.slice(0, 10)) : "")
        + (conn.lastRefreshAt ? " · token refreshed " + esc(conn.lastRefreshAt.slice(0, 16).replace("T", " ")) : "")
        + "."
        + (conn.lastPushSummary
            ? " Last push " + esc((conn.lastPushAt || "").slice(0, 16).replace("T", " "))
              + ": audience " + esc(String(conn.lastPushSummary.audience))
              + ", added " + esc(String(conn.lastPushSummary.added))
              + ", removed " + esc(String(conn.lastPushSummary.removed))
              + (conn.lastPushSummary.partial ? ' <span class="su__bad">(partial)</span>' : "")
              + "."
            : " No push has run yet.");
    } else if (conn) {
      line = '<span class="su__bad">Needs re-authorisation</span>'
        + (conn.lastError ? " — " + esc(conn.lastError) : "")
        + ". Connect again to restore the push and pull.";
    } else {
      line = "Not connected.";
    }
    var redirect = mail.redirectUri
      ? '<code class="su__code" id="mailingRedirect">' + esc(mail.redirectUri) + "</code> "
        + '<button type="button" class="cbm-button cbm-button--secondary su__mini" data-copy="mailingRedirect">Copy</button>'
      : '<span class="su__bad">APP_BASE_URL is not set, so the address cannot be built.</span>';
    return '<div class="su__mailing">'
      + '<p class="su__mailing-line">' + line + "</p>"
      + '<p class="su__rowhelp">Redirect address to register on the developer application: ' + redirect + "</p>"
      + '<p class="su__mailing-actions">'
      + '<a class="cbm-button" href="/api/setup/mailing/connect" data-mailing-connect="1">'
      + (conn ? "Reconnect" : "Connect") + "</a> "
      + '<button type="button" class="cbm-button cbm-button--secondary" data-mailing-disconnect="1">Disconnect</button>'
      + '<span class="su__muted" id="mailingMsg"></span>'
      + "</p></div>";
  }

  async function copyText(id, btn) {
    var el = $(id);
    if (!el) return;
    var value = el.textContent;
    try {
      await navigator.clipboard.writeText(value);
      var was = btn.textContent; btn.textContent = "Copied";
      setTimeout(function () { btn.textContent = was; }, 1200);
    } catch (e) {
      var range = document.createRange(); range.selectNodeContents(el);
      var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
    }
  }

  var mailingDisconnectArmed = 0;

  async function disconnectMailing(btn) {
    var msg = $("mailingMsg");
    // Two clicks inside five seconds: the page cannot show a confirm() dialog,
    // and the button must never be hidden. Reversible anyway — Connect again.
    var now = Date.now();
    if (now - mailingDisconnectArmed > 5000) {
      mailingDisconnectArmed = now;
      text(msg, "Click Disconnect again within five seconds to remove the connection.");
      return;
    }
    mailingDisconnectArmed = 0;
    try {
      var r = await fetch("/api/setup/mailing/disconnect", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
      });
      var body = null; try { body = await r.json(); } catch (e) { body = null; }
      if (!r.ok) throw new Error((body && body.detail) || ("HTTP " + r.status));
      text(msg, body.removed ? "Disconnected." : "There was no connection to remove.");
      loadReadiness().catch(function () {});
    } catch (e) {
      text(msg, e.message);
    }
  }

  async function connectMailing(ev) {
    // A plain link would land on a JSON 400 when something is missing; ask
    // first so the reason shows here, and only then let the browser go.
    ev.preventDefault();
    var msg = $("mailingMsg");
    text(msg, "");
    try {
      var r = await fetch("/api/setup/mailing/connect", { credentials: "same-origin", redirect: "manual" });
      if (r.status === 400) {
        var body = null; try { body = await r.json(); } catch (e) { body = null; }
        text(msg, (body && body.detail) || "Connect is not possible yet.");
        return;
      }
    } catch (e) { /* an opaque redirect response is the success case */ }
    window.location.href = "/api/setup/mailing/connect";
  }

  function announceMailingOutcome() {
    var q = new URLSearchParams(window.location.search);
    var outcome = q.get("mailing");
    if (!outcome) return false;
    var detail = q.get("detail") || "";
    var banner = $("restartBanner");
    var wording = {
      connected: "Mailing service connected" + (detail ? " as " + detail : "") + ".",
      declined: "The mailing service authorisation was declined" + (detail ? ": " + detail : "") + ".",
      failed: "The mailing service could not be connected" + (detail ? ": " + detail : "") + ".",
    }[outcome] || ("Mailing service: " + outcome);
    banner.textContent = wording;
    banner.hidden = false;
    // Never leave the outcome in the address bar — a reload would re-announce it.
    history.replaceState(null, "", window.location.pathname + "#readiness");
    return true;
  }

  // --- environment diff ------------------------------------------------------

  async function loadDiff() {
    var data = await busyOver($("diffRows"), api("/diff"));
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
    $("diffRows").innerHTML = '<table class="su__table"><thead><tr><th data-col="setting">Setting</th><th data-col="local">'
      + esc(data.localEnvironment || "here") + '</th><th data-col="peer">' + esc(data.peerEnvironment || "peer")
      + "</th></tr></thead><tbody>"
      + data.differences.map(function (d) {
        return "<tr><td>" + esc(d.label) + '<div class="su__key">' + esc(d.key) + "</div></td>"
          + "<td>" + esc(d.local == null ? "—" : d.local)
          + (d.localOverridden ? ' <span class="su__chip su__chip--override">override</span>' : "")
          + "</td><td>" + esc(d.peer == null ? "—" : d.peer)
          + (d.peerOverridden ? ' <span class="su__chip su__chip--override">override</span>' : "")
          + "</td></tr>";
      }).join("") + "</tbody></table>";
    fitGrid($("diffRows").querySelector("table"), "setup.diff");
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
    var data = await busyOver($("jobHistory"), api("/jobs"));
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
      ? '<table class="su__table su__table--runs"><thead><tr>'
        + ["When", "Job", "Mode", "Status", "Who", "Reason", "Report"].map(function (h) {
            return '<th data-col="' + h.toLowerCase() + '" data-sortable="false">' + h + "</th>";
          }).join("") + "</tr></thead><tbody>"
        + data.recent.map(function (r, i) {
            var has = !!(r.output || r.error);
            return "<tr" + (i % 2 ? ' class="su__alt"' : "") + "><td>" + esc((r.startedAt || "").replace("T", " ").slice(0, 16)) + "</td>"
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
    fitGrid($("jobHistory").querySelector("table"), "setup.runs");
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
    var data = await busyOver($("historyTable"), api("/history?limit=200" + (key ? "&key=" + encodeURIComponent(key) : "")));
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
    gridRefresh(fitGrid($("historyTable"), "setup.history"));
  }

  // --- tabs + boot -----------------------------------------------------------

  function selectTab(name) {
    if (name === "integrations" && !(state.page && state.page.integrationsTab)) name = "settings";
    state.tab = name;
    ["settings", "integrations", "readiness", "diff", "jobs", "history"].forEach(function (t) {
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
    if (name === "integrations") {
      renderIntegrations();
      history.replaceState(null, "", window.location.pathname + "#integrations/" + (state.subtab || ""));
    } else if (window.location.hash.indexOf("#integrations") === 0) {
      history.replaceState(null, "", window.location.pathname + (name === "settings" ? "" : "#" + name));
    }
  }

  /* ---------- Website images (prds/chapter-website-plan.md, decision 4.3) ----------
   * The logo and header graphic the chapter website shows. Each has an Upload
   * and a Remove button, never disabled: a click with nothing to act on says
   * why. The preview is admin-only and works before the website is connected. */
  var websiteImages = null;
  var websiteImagesNote = {};

  function imageCard(img) {
    var note = websiteImagesNote[img.name];
    var preview = img.set
      ? '<img class="su__imgpreview" alt="' + esc(img.label) + '" src="' + API + "/website/images/"
        + encodeURIComponent(img.name) + "?v=" + esc((img.sha256 || "").slice(0, 12)) + '">'
      : '<div class="su__imgempty">No image uploaded</div>';
    var facts = img.set
      ? esc(img.contentType) + " \u00b7 " + Math.ceil((img.size || 0) / 1024) + " KB"
        + (img.updatedBy ? " \u00b7 by " + esc(img.updatedBy) : "")
      : "PNG, JPEG or WebP, up to 2 MB.";
    return '<div class="su__imgcard">'
      + '<div class="su__imgname">' + esc(img.label) + "</div>" + preview
      + '<div class="su__hint">' + facts + "</div>"
      + '<div class="su__imgactions">'
      + '<button type="button" class="cbm-button cbm-button--secondary" data-img-upload="' + esc(img.name) + '">Upload\u2026</button> '
      + '<button type="button" class="cbm-button cbm-button--secondary" data-img-remove="' + esc(img.name) + '">Remove</button>'
      + "</div>"
      + (note ? '<p class="' + (note.error ? "form-error" : "su__hint") + '">' + esc(note.text) + "</p>" : "")
      + '<input type="file" accept="image/png,image/jpeg,image/webp" hidden data-img-file="' + esc(img.name) + '">'
      + "</div>";
  }

  function renderWebsiteImages() {
    var box = $("websiteImages");
    if (!box) return;
    if (!websiteImages) { box.innerHTML = '<p class="su__hint">Loading the website images\u2026</p>'; return; }
    if (websiteImagesNote._all) {
      box.innerHTML = '<p class="form-error">The website images could not be read: ' + esc(websiteImagesNote._all.text) + "</p>";
      return;
    }
    if (!websiteImages.available) {
      box.innerHTML = '<p class="su__note">Website images need a database, and this deployment has none.</p>';
      return;
    }
    box.innerHTML = '<h3 class="su__h3">Website images</h3>'
      + '<p class="su__note">The logo appears beside the website\u2019s name; the header graphic '
      + "under its header \u2014 tall on the home page, a narrow strip on other pages.</p>"
      + '<div class="su__imggrid">' + websiteImages.images.map(imageCard).join("") + "</div>";
  }

  async function loadWebsiteImages() {
    try {
      websiteImages = await api("/website/images");
      delete websiteImagesNote._all;
    } catch (e) {
      websiteImages = { available: true, images: [] };
      websiteImagesNote._all = { error: true, text: e.message };
    }
    renderWebsiteImages();
  }

  function findImage(name) {
    return ((websiteImages && websiteImages.images) || []).filter(function (i) { return i.name === name; })[0];
  }

  function uploadImage(input) {
    var name = input.dataset.imgFile;
    var file = input.files && input.files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      websiteImagesNote[name] = { error: true, text: "That file is larger than 2 MB. Save it smaller and try again." };
      renderWebsiteImages();
      return;
    }
    var reader = new FileReader();
    reader.onload = async function () {
      try {
        websiteImages = await api("/website/images/" + encodeURIComponent(name), {
          method: "PUT", body: JSON.stringify({ data: reader.result }),
        });
        websiteImagesNote[name] = { error: false, text: "Uploaded. The website shows it within a few minutes." };
      } catch (e) {
        websiteImagesNote[name] = { error: true, text: e.message };
      }
      renderWebsiteImages();
    };
    reader.readAsDataURL(file);
  }

  async function removeImage(name) {
    var img = findImage(name);
    if (!img || !img.set) {
      websiteImagesNote[name] = { error: true, text: "There is no image to remove." };
      renderWebsiteImages();
      return;
    }
    try {
      websiteImages = await api("/website/images/" + encodeURIComponent(name), { method: "DELETE" });
      websiteImagesNote[name] = { error: false, text: "Removed." };
    } catch (e) {
      websiteImagesNote[name] = { error: true, text: e.message };
    }
    renderWebsiteImages();
  }

  async function boot() {
    try {
      var page = await busyOver($("bodyView").hidden ? null : $("bodyView"), api("/settings"));
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
    renderAll();
    loadWebsiteImages();
    var hash = window.location.hash || "";
    if (announceMailingOutcome() || hash === "#readiness") selectTab("readiness");
    else if (hash.indexOf("#integrations") === 0 && state.page.integrationsTab) {
      // A deep link to one integration: /setup/#integrations/zoom
      var sub = hash.split("/")[1] || "";
      if (findIntegration(sub)) state.subtab = sub;
      selectTab("integrations");
    }
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (t.dataset && t.dataset.edit) { openEditor(t.dataset.edit); return; }
    if (t.dataset && t.dataset.subtab) { ev.preventDefault(); selectSubtab(t.dataset.subtab); return; }
    if (t.dataset && t.dataset.goto) { ev.preventDefault(); gotoSetting(t.dataset.goto); return; }
    if (t.dataset && t.dataset.confirm) { confirmSetting(t.dataset.confirm); return; }
    if (t.dataset && t.dataset.dry) { runJob(t.dataset.dry, false); return; }
    if (t.dataset && t.dataset.apply) { runJob(t.dataset.apply, true); return; }
    if (t.dataset && t.dataset.run) { toggleRunOutput(t.dataset.run); return; }
    if (t.dataset && t.dataset.copy) { copyText(t.dataset.copy, t); return; }
    if (t.dataset && t.dataset.mailingDisconnect) { disconnectMailing(t); return; }
    if (t.dataset && t.dataset.mailingConnect) { connectMailing(ev); return; }
    if (t.dataset && t.dataset.imgUpload) {
      var input = document.querySelector('input[data-img-file="' + t.dataset.imgUpload + '"]');
      if (input) { input.value = ""; input.click(); }
      return;
    }
    if (t.dataset && t.dataset.imgRemove) { removeImage(t.dataset.imgRemove); return; }
    if (t.classList && t.classList.contains("su__tab")) { selectTab(t.dataset.tab); return; }
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.addEventListener("change", function (ev) {
      if (ev.target && ev.target.dataset && ev.target.dataset.imgFile) uploadImage(ev.target);
    });
    $("filterBox").addEventListener("input", renderSettings);
    // Remember which Google sections were folded, so a save's re-render keeps them.
    document.addEventListener("toggle", function (ev) {
      var d = ev.target;
      if (d && d.dataset && d.dataset.section) state.closed[d.dataset.section] = !d.open;
    }, true);
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
